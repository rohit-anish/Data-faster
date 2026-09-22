"""
Database Performance Advisor
Benchmark Runner

Runs SQL queries using PostgreSQL EXPLAIN (ANALYZE, BUFFERS),
collects execution statistics, and calculates benchmark metrics.

Uses psycopg 3.
"""

import os
import re
import statistics
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

import psycopg
from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

# Load variables from the project's .env file.
load_dotenv()


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv(
        "DB_NAME",
        "db_performance_advisor"
    ),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
class BenchmarkResult:
    """
    Stores the result of one EXPLAIN ANALYZE execution.
    """

    execution_time_ms: float
    planning_time_ms: float

    rows_returned: Optional[float]
    estimated_rows: Optional[float]

    scan_type: str
    index_used: Optional[str]

    shared_hit: int
    shared_read: int

    total_cost: Optional[float]
    startup_cost: Optional[float]

    raw_plan: List[str]


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection() -> psycopg.Connection:
    """
    Create and return a PostgreSQL database connection.
    """

    try:
        conn = psycopg.connect(**DB_CONFIG)

        return conn

    except psycopg.Error as exc:
        raise RuntimeError(
            f"Could not connect to PostgreSQL: {exc}"
        ) from exc


# ============================================================
# EXPLAIN ANALYZE EXECUTION
# ============================================================

def run_explain(
    conn: psycopg.Connection,
    query: str,
) -> List[str]:
    """
    Execute EXPLAIN (ANALYZE, BUFFERS) for the supplied query.

    Returns:
        PostgreSQL query-plan lines.
    """

    cleaned_query = query.strip().rstrip(";")

    # Prevent accidental execution of an empty query.
    if not cleaned_query:
        raise ValueError("Query cannot be empty.")

    explain_query = f"""
EXPLAIN (ANALYZE, BUFFERS)
{cleaned_query};
"""

    try:

        with conn.cursor() as cursor:

            cursor.execute(explain_query)

            rows = cursor.fetchall()

        return [row[0] for row in rows]

    except psycopg.Error as exc:

        raise RuntimeError(
            f"Failed to execute EXPLAIN ANALYZE: {exc}"
        ) from exc


# ============================================================
# PLAN PARSER
# ============================================================

def parse_plan(plan_lines: List[str]) -> BenchmarkResult:
    """
    Parse PostgreSQL EXPLAIN output.

    Extracts:

    - execution time
    - planning time
    - estimated rows
    - actual rows
    - scan type
    - index used
    - shared buffer hits
    - shared buffer reads
    - estimated costs
    """

    if not plan_lines:
        raise ValueError(
            "PostgreSQL returned an empty query plan."
        )

    plan_text = "\n".join(plan_lines)

    # --------------------------------------------------------
    # Execution Time
    # --------------------------------------------------------

    execution_match = re.search(
        r"Execution Time:\s*([\d.]+)\s*ms",
        plan_text,
        re.IGNORECASE,
    )

    if not execution_match:
        raise ValueError(
            "Could not find Execution Time in PostgreSQL plan."
        )

    execution_time = float(
        execution_match.group(1)
    )

    # --------------------------------------------------------
    # Planning Time
    # --------------------------------------------------------

    planning_match = re.search(
        r"Planning Time:\s*([\d.]+)\s*ms",
        plan_text,
        re.IGNORECASE,
    )

    planning_time = (
        float(planning_match.group(1))
        if planning_match
        else 0.0
    )

    # --------------------------------------------------------
    # Find the main scan node
    # --------------------------------------------------------

    scan_type = "Unknown"

    scan_patterns = [
        r"^\s*(?:->\s*)?(Parallel Seq Scan[^\n(]*)",
        r"^\s*(?:->\s*)?(Seq Scan[^\n(]*)",
        r"^\s*(?:->\s*)?(Bitmap Heap Scan[^\n(]*)",
        r"^\s*(?:->\s*)?(Bitmap Index Scan[^\n(]*)",
        r"^\s*(?:->\s*)?(Index Only Scan[^\n(]*)",
        r"^\s*(?:->\s*)?(Index Scan[^\n(]*)",
    ]

    for pattern in scan_patterns:

        scan_match = re.search(
            pattern,
            plan_text,
            re.IGNORECASE | re.MULTILINE,
        )

        if scan_match:

            scan_type = scan_match.group(1).strip()

            break

    # --------------------------------------------------------
    # Cost
    # --------------------------------------------------------

    startup_cost = None
    total_cost = None

    cost_match = re.search(
        r"\(cost=([\d.]+)\.\.([\d.]+)",
        plan_text,
        re.IGNORECASE,
    )

    if cost_match:

        startup_cost = float(
            cost_match.group(1)
        )

        total_cost = float(
            cost_match.group(2)
        )

    # --------------------------------------------------------
    # Estimated rows
    # --------------------------------------------------------

    estimated_rows = None

    rows_estimate_match = re.search(
        r"\(cost=[^)]+?\s+rows=(\d+)",
        plan_text,
        re.IGNORECASE,
    )

    if rows_estimate_match:

        estimated_rows = float(
            rows_estimate_match.group(1)
        )

    # --------------------------------------------------------
    # Actual rows
    # --------------------------------------------------------

    actual_rows = None

    actual_rows_match = re.search(
        r"actual time=[\d.]+\.\.[\d.]+"
        r"\s+rows=([\d.]+)",
        plan_text,
        re.IGNORECASE,
    )

    if actual_rows_match:

        actual_rows = float(
            actual_rows_match.group(1)
        )

    # --------------------------------------------------------
    # Index used
    # --------------------------------------------------------

    index_used = None

    index_patterns = [
        r"Index Scan on .*?\s+using\s+([^\s]+)",
        r"Index Only Scan on .*?\s+using\s+([^\s]+)",
        r"Bitmap Index Scan on\s+([^\s(]+)",
    ]

    for pattern in index_patterns:

        index_match = re.search(
            pattern,
            plan_text,
            re.IGNORECASE,
        )

        if index_match:

            index_used = index_match.group(1)

            break

    # --------------------------------------------------------
    # Buffer statistics
    # --------------------------------------------------------

    shared_hit = 0
    shared_read = 0

    # PostgreSQL can report:
    #
    # Buffers: shared hit=29 read=10
    #
    # or:
    #
    # Buffers: shared hit=29
    #
    # or:
    #
    # Buffers: shared read=10

    hit_matches = re.findall(
        r"shared\s+hit=(\d+)",
        plan_text,
        re.IGNORECASE,
    )

    read_matches = re.findall(
        r"shared\s+read=(\d+)",
        plan_text,
        re.IGNORECASE,
    )

    if hit_matches:

        shared_hit = max(
            int(value)
            for value in hit_matches
        )

    if read_matches:

        shared_read = max(
            int(value)
            for value in read_matches
        )

    # --------------------------------------------------------
    # Return structured result
    # --------------------------------------------------------

    return BenchmarkResult(
        execution_time_ms=execution_time,
        planning_time_ms=planning_time,
        rows_returned=actual_rows,
        estimated_rows=estimated_rows,
        scan_type=scan_type,
        index_used=index_used,
        shared_hit=shared_hit,
        shared_read=shared_read,
        total_cost=total_cost,
        startup_cost=startup_cost,
        raw_plan=plan_lines,
    )


# ============================================================
# SINGLE BENCHMARK RUN
# ============================================================

def benchmark_once(
    conn: psycopg.Connection,
    query: str,
) -> BenchmarkResult:
    """
    Execute one EXPLAIN ANALYZE benchmark.
    """

    plan = run_explain(
        conn,
        query,
    )

    return parse_plan(plan)


# ============================================================
# MULTI-RUN BENCHMARK
# ============================================================

def benchmark_query(
    query: str,
    runs: int = 5,
    warmup_runs: int = 0,
) -> Dict[str, Any]:
    """
    Benchmark a query multiple times.

    Args:
        query:
            SQL SELECT query to benchmark.

        runs:
            Number of measured executions.

        warmup_runs:
            Number of executions performed before
            collecting measurements.

    Returns:
        Dictionary containing individual runs and
        aggregated statistics.
    """

    if runs < 1:

        raise ValueError(
            "runs must be at least 1."
        )

    if warmup_runs < 0:

        raise ValueError(
            "warmup_runs cannot be negative."
        )

    conn = get_connection()

    try:

        # ----------------------------------------------------
        # Warmup
        # ----------------------------------------------------

        for _ in range(warmup_runs):

            benchmark_once(
                conn,
                query,
            )

        # ----------------------------------------------------
        # Measured runs
        # ----------------------------------------------------

        results: List[BenchmarkResult] = []

        for _ in range(runs):

            result = benchmark_once(
                conn,
                query,
            )

            results.append(result)

        # ----------------------------------------------------
        # Execution times
        # ----------------------------------------------------

        execution_times = [
            result.execution_time_ms
            for result in results
        ]

        # ----------------------------------------------------
        # Planning times
        # ----------------------------------------------------

        planning_times = [
            result.planning_time_ms
            for result in results
        ]

        # ----------------------------------------------------
        # Median
        # ----------------------------------------------------

        median_execution = statistics.median(
            execution_times
        )

        median_planning = statistics.median(
            planning_times
        )

        # ----------------------------------------------------
        # Average
        # ----------------------------------------------------

        average_execution = statistics.mean(
            execution_times
        )

        average_planning = statistics.mean(
            planning_times
        )

        # ----------------------------------------------------
        # Minimum / maximum
        # ----------------------------------------------------

        best_execution = min(
            execution_times
        )

        worst_execution = max(
            execution_times
        )

        # ----------------------------------------------------
        # Dominant scan type
        # ----------------------------------------------------

        scan_types = [
            result.scan_type
            for result in results
            if result.scan_type != "Unknown"
        ]

        dominant_scan = None

        if scan_types:

            dominant_scan = max(
                set(scan_types),
                key=scan_types.count,
            )

        # ----------------------------------------------------
        # Dominant index
        # ----------------------------------------------------

        indexes = [
            result.index_used
            for result in results
            if result.index_used
        ]

        dominant_index = None

        if indexes:

            dominant_index = max(
                set(indexes),
                key=indexes.count,
            )

        # ----------------------------------------------------
        # Return structured result
        # ----------------------------------------------------

        return {
            "query": query.strip(),

            "runs": runs,

            "warmup_runs": warmup_runs,

            "execution_time_ms": {
                "median": median_execution,
                "average": average_execution,
                "minimum": best_execution,
                "maximum": worst_execution,
                "individual": execution_times,
            },

            "planning_time_ms": {
                "median": median_planning,
                "average": average_planning,
                "individual": planning_times,
            },

            "scan_type": dominant_scan,

            "index_used": dominant_index,

            "results": [
                asdict(result)
                for result in results
            ],
        }

    finally:

        conn.close()


# ============================================================
# BENCHMARK COMPARISON
# ============================================================

def compare_benchmarks(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compare two benchmark results.

    Typically:

        before = query without optimization
        after  = query with optimization
    """

    before_time = before[
        "execution_time_ms"
    ]["median"]

    after_time = after[
        "execution_time_ms"
    ]["median"]

    if before_time <= 0:

        improvement_percent = 0.0

    else:

        improvement_percent = (
            (before_time - after_time)
            / before_time
        ) * 100

    if after_time > 0:

        speedup = (
            before_time
            / after_time
        )

    else:

        speedup = None

    return {
        "before_median_ms": before_time,
        "after_median_ms": after_time,
        "improvement_percent": improvement_percent,
        "speedup_factor": speedup,
    }


# ============================================================
# COMMAND-LINE TEST
# ============================================================

if __name__ == "__main__":

    TEST_QUERY = """
SELECT *
FROM orders
WHERE customer_id = 75992;
"""

    print("=" * 60)
    print("DATABASE PERFORMANCE ADVISOR")
    print("Benchmark Runner Test")
    print("=" * 60)

    print()
    print("Database:")
    print(
        f"  Host     : {DB_CONFIG['host']}"
    )
    print(
        f"  Port     : {DB_CONFIG['port']}"
    )
    print(
        f"  Database : {DB_CONFIG['dbname']}"
    )
    print(
        f"  User     : {DB_CONFIG['user']}"
    )

    print()
    print("Query:")
    print(TEST_QUERY.strip())

    print()
    print("Running benchmark...")

    try:

        result = benchmark_query(
            query=TEST_QUERY,
            runs=5,
        )

        print()
        print("Benchmark completed successfully.")
        print()

        print(
            f"Median execution time : "
            f"{result['execution_time_ms']['median']:.3f} ms"
        )

        print(
            f"Average execution time: "
            f"{result['execution_time_ms']['average']:.3f} ms"
        )

        print(
            f"Minimum execution time: "
            f"{result['execution_time_ms']['minimum']:.3f} ms"
        )

        print(
            f"Maximum execution time: "
            f"{result['execution_time_ms']['maximum']:.3f} ms"
        )

        print(
            f"Median planning time  : "
            f"{result['planning_time_ms']['median']:.3f} ms"
        )

        print(
            f"Scan type             : "
            f"{result['scan_type']}"
        )

        print(
            f"Index used            : "
            f"{result['index_used']}"
        )

        print()
        print("Individual execution times:")

        for number, time in enumerate(
            result[
                "execution_time_ms"
            ]["individual"],
            start=1,
        ):

            print(
                f"  Run {number}: "
                f"{time:.3f} ms"
            )

    except Exception as exc:

        print()
        print("Benchmark failed.")
        print()
        print(f"Error: {exc}")