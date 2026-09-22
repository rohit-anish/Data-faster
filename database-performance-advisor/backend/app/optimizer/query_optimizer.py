"""
Database Performance Advisor
Query Optimization Engine

This module executes PostgreSQL EXPLAIN ANALYZE and interprets
the resulting execution plan.

The module does NOT replace PostgreSQL's query optimizer.

Instead, it:
    1. Executes EXPLAIN (ANALYZE, BUFFERS)
    2. Reads PostgreSQL's actual execution plan
    3. Extracts important performance information
    4. Diagnoses possible performance problems
    5. Produces human-readable optimization suggestions
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import psycopg
from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class PlanNode:

    node_type: str

    relation_name: Optional[str] = None

    index_name: Optional[str] = None

    estimated_rows: Optional[int] = None

    actual_rows: Optional[int] = None

    startup_cost: Optional[float] = None

    total_cost: Optional[float] = None

    actual_startup_time: Optional[float] = None

    actual_total_time: Optional[float] = None

    loops: Optional[int] = None

    shared_hit_blocks: int = 0

    shared_read_blocks: int = 0


@dataclass
class OptimizationResult:

    query: str

    execution_time_ms: float

    planning_time_ms: float

    root_node: str

    scan_types: List[str]

    indexes_used: List[str]

    rows_examined: Optional[int]

    rows_returned: Optional[int]

    shared_hit_blocks: int

    shared_read_blocks: int

    diagnosis: List[str] = field(
        default_factory=list
    )

    recommendations: List[str] = field(
        default_factory=list
    )

    plan: Optional[Dict[str, Any]] = None


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    return psycopg.connect(
        host=os.getenv(
            "DB_HOST",
            "localhost",
        ),
        port=os.getenv(
            "DB_PORT",
            "5432",
        ),
        dbname=os.getenv(
            "DB_NAME",
            "db_performance_advisor",
        ),
        user=os.getenv(
            "DB_USER",
            "postgres",
        ),
        password=os.getenv(
            "DB_PASSWORD",
        ),
    )


# ============================================================
# EXPLAIN ANALYZE
# ============================================================

def run_explain(
    query: str,
) -> Dict[str, Any]:
    """
    Execute EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON).

    PostgreSQL returns the execution plan as JSON,
    which is much easier to analyze programmatically.
    """

    cleaned_query = query.strip()

    if cleaned_query.endswith(";"):

        cleaned_query = (
            cleaned_query[:-1]
        )

    explain_query = (
        "EXPLAIN "
        "(ANALYZE, BUFFERS, FORMAT JSON) "
        + cleaned_query
    )

    with get_connection() as conn:

        with conn.cursor() as cursor:

            cursor.execute(
                explain_query
            )

            result = cursor.fetchone()

    if not result:

        raise RuntimeError(
            "PostgreSQL returned no execution plan."
        )

    # PostgreSQL psycopg may already decode JSON.
    raw_plan = result[0]

    if isinstance(raw_plan, str):

        raw_plan = json.loads(
            raw_plan
        )

    # EXPLAIN FORMAT JSON normally returns:
    #
    # [
    #   {
    #       "Plan": {...},
    #       "Planning Time": ...,
    #       "Execution Time": ...
    #   }
    # ]

    if isinstance(raw_plan, list):

        return raw_plan[0]

    return raw_plan


# ============================================================
# PLAN NODE WALKER
# ============================================================

def walk_plan(
    node: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Recursively walk the PostgreSQL execution plan tree.
    """

    nodes = [node]

    for child in node.get(
        "Plans",
        [],
    ):

        nodes.extend(
            walk_plan(child)
        )

    return nodes


# ============================================================
# PLAN EXTRACTION
# ============================================================

def extract_plan_information(
    explain_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Extract useful information from PostgreSQL's plan.

    Rows examined is based on the most relevant scan node
    rather than summing all nodes. This avoids double-counting
    rows when a plan contains multiple related nodes such as:

        Bitmap Index Scan
                ↓
        Bitmap Heap Scan
    """

    root_plan = explain_result.get(
        "Plan",
        {},
    )

    nodes = walk_plan(
        root_plan
    )

    scan_types = []

    indexes_used = []

    shared_hit_blocks = 0

    shared_read_blocks = 0

    # --------------------------------------------------------
    # Find the most relevant scan node
    # --------------------------------------------------------

    scan_nodes = []

    for node in nodes:

        node_type = node.get(
            "Node Type",
            "",
        )

        if (
            "Seq Scan" in node_type
            or "Index Scan" in node_type
            or "Bitmap Heap Scan" in node_type
        ):

            scan_nodes.append(
                node
            )

    # --------------------------------------------------------
    # Collect node information
    # --------------------------------------------------------

    for node in nodes:

        node_type = node.get(
            "Node Type"
        )

        if node_type:

            scan_types.append(
                node_type
            )

        index_name = node.get(
            "Index Name"
        )

        if index_name:

            if index_name not in indexes_used:

                indexes_used.append(
                    index_name
                )

        shared_hit_blocks += node.get(
            "Shared Hit Blocks",
            0,
        )

        shared_read_blocks += node.get(
            "Shared Read Blocks",
            0,
        )

    # --------------------------------------------------------
    # Determine rows examined
    # --------------------------------------------------------

    rows_examined = None

    if scan_nodes:

        # Prefer the outermost / highest-level table scan.
        #
        # In a Bitmap plan this will normally be:
        #
        # Bitmap Heap Scan
        #
        # rather than the Bitmap Index Scan.

        selected_scan = scan_nodes[0]

        rows_examined = (
            selected_scan.get(
                "Actual Rows"
            )
        )

        if rows_examined is not None:

            loops = selected_scan.get(
                "Actual Loops",
                1,
            )

            rows_examined = (
                rows_examined * loops
            )

    # --------------------------------------------------------
    # Rows returned by the root node
    # --------------------------------------------------------

    rows_returned = (
        root_plan.get(
            "Actual Rows"
        )
    )

    if rows_returned is not None:

        loops = root_plan.get(
            "Actual Loops",
            1,
        )

        rows_returned = (
            rows_returned * loops
        )

    return {
        "root_node": root_plan.get(
            "Node Type",
            "Unknown",
        ),

        "scan_types": scan_types,

        "indexes_used": indexes_used,

        "rows_examined": rows_examined,

        "rows_returned": rows_returned,

        "shared_hit_blocks": (
            shared_hit_blocks
        ),

        "shared_read_blocks": (
            shared_read_blocks
        ),
    }


# ============================================================
# PERFORMANCE DIAGNOSIS
# ============================================================

def diagnose_plan(
    explain_result: Dict[str, Any],
    plan_info: Dict[str, Any],
) -> tuple[List[str], List[str]]:
    """
    Generate human-readable diagnosis and recommendations.
    """

    diagnosis = []

    recommendations = []

    scan_types = plan_info[
        "scan_types"
    ]

    indexes_used = plan_info[
        "indexes_used"
    ]

    rows_examined = plan_info[
        "rows_examined"
    ]

    rows_returned = plan_info[
        "rows_returned"
    ]

    # --------------------------------------------------------
    # Sequential scan
    # --------------------------------------------------------

    sequential_scan = any(
        "Seq Scan" in scan
        for scan in scan_types
    )

    if sequential_scan:

        diagnosis.append(
            "PostgreSQL performed a sequential scan."
        )

        recommendations.append(
            "Check whether a suitable index exists "
            "for the query's filtering or join columns."
        )

    # --------------------------------------------------------
    # Parallel sequential scan
    # --------------------------------------------------------

    parallel_seq_scan = any(
        "Parallel Seq Scan" in scan
        for scan in scan_types
    )

    if parallel_seq_scan:

        diagnosis.append(
            "PostgreSQL used a parallel sequential scan, "
            "indicating that a substantial amount of table "
            "data was scanned."
        )

        recommendations.append(
            "Evaluate whether a selective B-Tree index "
            "could reduce the amount of data scanned."
        )

    # --------------------------------------------------------
    # Index scan
    # --------------------------------------------------------

    index_scan = any(
        "Index Scan" in scan
        for scan in scan_types
    )

    bitmap_scan = any(
        "Bitmap" in scan
        for scan in scan_types
    )

    if index_scan or bitmap_scan:

        if indexes_used:

            diagnosis.append(
                "PostgreSQL is using an index for "
                "the query."
            )

            recommendations.append(
                "The current index access strategy "
                "is working. Compare execution time "
                "before and after indexing for validation."
            )

    # --------------------------------------------------------
    # Rows examined vs returned
    # --------------------------------------------------------

    if (
        rows_examined is not None
        and rows_returned is not None
        and rows_returned > 0
    ):

        ratio = (
            rows_examined
            /
            rows_returned
        )

        if ratio >= 100:

            diagnosis.append(
                f"The execution plan processed approximately "
                f"{ratio:.0f} times more rows than it returned."
            )

            recommendations.append(
                "Investigate indexes and filter selectivity "
                "to reduce unnecessary row processing."
            )

    # --------------------------------------------------------
    # No index used
    # --------------------------------------------------------

    if (
        not indexes_used
        and not sequential_scan
    ):

        diagnosis.append(
            "No index was reported in the execution plan."
        )

    # --------------------------------------------------------
    # Shared disk reads
    # --------------------------------------------------------

    shared_read_blocks = plan_info[
        "shared_read_blocks"
    ]

    if shared_read_blocks > 0:

        diagnosis.append(
            f"The query required "
            f"{shared_read_blocks} shared disk block reads."
        )

        recommendations.append(
            "Repeated execution may benefit from "
            "PostgreSQL's buffer cache. Benchmark "
            "multiple runs to separate cold-cache and "
            "warm-cache behavior."
        )

    return (
        diagnosis,
        recommendations,
    )


# ============================================================
# COMPLETE OPTIMIZATION
# ============================================================

def optimize_query(
    query: str,
) -> OptimizationResult:
    """
    Run EXPLAIN ANALYZE and generate an optimization result.
    """

    explain_result = run_explain(
        query
    )

    plan_info = (
        extract_plan_information(
            explain_result
        )
    )

    diagnosis, recommendations = (
        diagnose_plan(
            explain_result,
            plan_info,
        )
    )

    return OptimizationResult(

        query=query.strip(),

        execution_time_ms=float(
            explain_result.get(
                "Execution Time",
                0.0,
            )
        ),

        planning_time_ms=float(
            explain_result.get(
                "Planning Time",
                0.0,
            )
        ),

        root_node=(
            plan_info["root_node"]
        ),

        scan_types=(
            plan_info["scan_types"]
        ),

        indexes_used=(
            plan_info["indexes_used"]
        ),

        rows_examined=(
            plan_info["rows_examined"]
        ),

        rows_returned=(
            plan_info["rows_returned"]
        ),

        shared_hit_blocks=(
            plan_info[
                "shared_hit_blocks"
            ]
        ),

        shared_read_blocks=(
            plan_info[
                "shared_read_blocks"
            ]
        ),

        diagnosis=diagnosis,

        recommendations=recommendations,

        plan=explain_result,
    )


# ============================================================
# PRINT RESULT
# ============================================================

def print_optimization_result(
    result: OptimizationResult,
) -> None:

    print()

    print("=" * 60)

    print(
        "QUERY OPTIMIZATION ANALYSIS"
    )

    print("=" * 60)

    print()

    print("Query:")

    print(
        result.query
    )

    print()

    print(
        f"Planning time   : "
        f"{result.planning_time_ms:.3f} ms"
    )

    print(
        f"Execution time  : "
        f"{result.execution_time_ms:.3f} ms"
    )

    print()

    print(
        f"Root node       : "
        f"{result.root_node}"
    )

    print(
        f"Rows examined   : "
        f"{result.rows_examined}"
    )

    print(
        f"Rows returned   : "
        f"{result.rows_returned}"
    )

    print()

    print("Scan types:")

    for scan in result.scan_types:

        print(
            f"  - {scan}"
        )

    print()

    print("Indexes used:")

    if result.indexes_used:

        for index in result.indexes_used:

            print(
                f"  - {index}"
            )

    else:

        print(
            "  None"
        )

    print()

    print(
        f"Shared hit blocks : "
        f"{result.shared_hit_blocks}"
    )

    print(
        f"Shared read blocks: "
        f"{result.shared_read_blocks}"
    )

    print()

    print(
        "DIAGNOSIS"
    )

    print(
        "-" * 60
    )

    if result.diagnosis:

        for item in result.diagnosis:

            print(
                f"  • {item}"
            )

    else:

        print(
            "  No significant problems detected."
        )

    print()

    print(
        "RECOMMENDATIONS"
    )

    print(
        "-" * 60
    )

    if result.recommendations:

        for item in result.recommendations:

            print(
                f"  • {item}"
            )

    else:

        print(
            "  No additional recommendations."
        )

    print()

    print("=" * 60)


# ============================================================
# TEST
# ============================================================

def main():

    test_query = """
        SELECT *
        FROM orders
        WHERE customer_id = 75992;
    """

    print("=" * 60)

    print(
        "DATABASE PERFORMANCE ADVISOR"
    )

    print(
        "Query Optimization Engine Test"
    )

    print("=" * 60)

    try:

        result = optimize_query(
            test_query
        )

        print_optimization_result(
            result
        )

    except Exception as exc:

        print()

        print(
            "Optimization test failed:"
        )

        print(
            f"  {exc}"
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()