"""
Database Performance Advisor
Central Advisor Engine

Combines:
    1. Query Analyzer
    2. Database Metadata
    3. Query Optimization Engine
    4. Index Advisor

The Central Advisor analyzes a query and produces a
combined performance diagnosis and recommendation.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from backend.app.analyzers.query_analyzer import (
    analyze_query as analyze_sql_query,
)

from backend.app.database.metadata import (
    get_indexes,
    get_tables,
)

from backend.app.indexing.advisor import (
    IndexAdvisor,
    IndexRecommendation,
)

from backend.app.optimizer.query_optimizer import (
    OptimizationResult,
    optimize_query,
)


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class AdvisorResult:
    """Complete result produced by the Central Advisor."""

    query: str

    # Query analysis
    query_type: str
    tables: List[str] = field(default_factory=list)
    filters: List[str] = field(default_factory=list)
    order_by: List[str] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    joins: List[str] = field(default_factory=list)

    # Database information
    database_tables: List[str] = field(default_factory=list)
    index_count: int = 0

    # PostgreSQL optimization analysis
    optimization: Optional[OptimizationResult] = None

    # Index Advisor
    index_recommendations: List[IndexRecommendation] = field(
        default_factory=list
    )

    existing_indexes: List[IndexRecommendation] = field(
        default_factory=list
    )

    # Final output
    diagnosis: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


# ============================================================
# FORMATTING HELPERS
# ============================================================

def format_filter(condition) -> str:
    """Convert a FilterCondition into readable text."""

    if getattr(condition, "table", None):
        column = f"{condition.table}.{condition.column}"
    else:
        column = condition.column

    return f"{column} {condition.operator} {condition.value}"


def format_order(condition) -> str:
    """Convert an OrderCondition into readable text."""

    if getattr(condition, "table", None):
        column = f"{condition.table}.{condition.column}"
    else:
        column = condition.column

    return f"{column} {condition.direction}"


def format_group(condition) -> str:
    """Convert a GroupCondition into readable text."""

    if getattr(condition, "table", None):
        column = f"{condition.table}.{condition.column}"
    else:
        column = condition.column

    return column


def format_join(condition) -> str:
    """Convert a JoinCondition into readable text."""

    return (
        f"{condition.left_table}.{condition.left_column} = "
        f"{condition.right_table}.{condition.right_column}"
    )


# ============================================================
# DATABASE SUMMARY
# ============================================================

def get_database_summary():
    """
    Retrieve basic database metadata.
    """

    tables = get_tables()
    indexes = get_indexes()

    return tables, indexes


# ============================================================
# DIAGNOSIS
# ============================================================

def build_diagnosis(
    query_analysis,
    optimization: OptimizationResult,
    index_analysis,
) -> List[str]:
    """
    Build high-level diagnosis by combining:
        Query Analyzer
        Query Optimizer
        Index Advisor
    """

    diagnosis = []

    # --------------------------------------------------------
    # Query type
    # --------------------------------------------------------

    diagnosis.append(
        f"The query is a {query_analysis.query_type} query."
    )

    # --------------------------------------------------------
    # Tables
    # --------------------------------------------------------

    if query_analysis.tables:
        diagnosis.append(
            "The query accesses: "
            + ", ".join(query_analysis.tables)
            + "."
        )

    # --------------------------------------------------------
    # Execution plan
    # --------------------------------------------------------

    if optimization.scan_types:

        scan_text = ", ".join(
            optimization.scan_types
        )

        diagnosis.append(
            f"PostgreSQL used the following scan operation(s): "
            f"{scan_text}."
        )

    # --------------------------------------------------------
    # Index usage
    # --------------------------------------------------------

    if optimization.indexes_used:

        diagnosis.append(
            "PostgreSQL is using an index: "
            + ", ".join(optimization.indexes_used)
            + "."
        )

    else:

        diagnosis.append(
            "No index was used by PostgreSQL for this query."
        )

    # --------------------------------------------------------
    # Disk reads
    # --------------------------------------------------------

    if optimization.shared_read_blocks > 0:

        diagnosis.append(
            f"The query required "
            f"{optimization.shared_read_blocks} "
            f"shared disk block reads."
        )

    # --------------------------------------------------------
    # Buffer cache
    # --------------------------------------------------------

    if optimization.shared_hit_blocks > 0:

        diagnosis.append(
            f"{optimization.shared_hit_blocks} shared blocks "
            f"were served from PostgreSQL's buffer cache."
        )

    # --------------------------------------------------------
    # Index recommendations
    # --------------------------------------------------------

    if index_analysis.recommendations:

        diagnosis.append(
            f"The Index Advisor identified "
            f"{len(index_analysis.recommendations)} "
            f"new index recommendation(s)."
        )

    else:

        diagnosis.append(
            "No new index is currently required based on "
            "the detected query conditions."
        )

    # --------------------------------------------------------
    # Existing suitable indexes
    # --------------------------------------------------------

    if index_analysis.existing_indexes:

        diagnosis.append(
            f"{len(index_analysis.existing_indexes)} "
            f"suitable existing index(es) were identified."
        )

    return diagnosis


# ============================================================
# RECOMMENDATIONS
# ============================================================

def build_recommendations(
    optimization: OptimizationResult,
    index_analysis,
) -> List[str]:
    """
    Combine recommendations from PostgreSQL plan analysis
    and Index Advisor.
    """

    recommendations = []

    # --------------------------------------------------------
    # PostgreSQL optimizer recommendations
    # --------------------------------------------------------

    for recommendation in optimization.recommendations:

        if recommendation not in recommendations:

            recommendations.append(
                recommendation
            )

    # --------------------------------------------------------
    # Index Advisor recommendations
    # --------------------------------------------------------

    for recommendation in index_analysis.recommendations:

        message = (
            f"Create a {recommendation.index_type.upper()} "
            f"index on "
            f"{recommendation.table}"
            f"({', '.join(recommendation.columns)}). "
            f"Reason: {recommendation.reason}"
        )

        if message not in recommendations:

            recommendations.append(
                message
            )

    # --------------------------------------------------------
    # Existing index information
    # --------------------------------------------------------

    if (
        not index_analysis.recommendations
        and index_analysis.existing_indexes
    ):

        recommendations.append(
            "The query already has suitable index coverage "
            "for the detected conditions."
        )

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    if not recommendations:

        recommendations.append(
            "No additional optimization recommendation "
            "was identified."
        )

    return recommendations


# ============================================================
# MAIN ADVISOR FUNCTION
# ============================================================

def analyze_query(query: str) -> AdvisorResult:
    """
    Run the complete Database Performance Advisor pipeline.

    Pipeline:

        SQL Query
            ↓
        Query Analyzer
            ↓
        Database Metadata
            ↓
        PostgreSQL EXPLAIN ANALYZE
            ↓
        Index Advisor
            ↓
        Final Diagnosis
            ↓
        Recommendations
    """

    if not query or not query.strip():

        raise ValueError(
            "Query cannot be empty."
        )

    query = query.strip()

    # ========================================================
    # 1. QUERY ANALYSIS
    # ========================================================

    query_analysis = analyze_sql_query(
        query
    )

    # ========================================================
    # 2. DATABASE METADATA
    # ========================================================

    database_tables, database_indexes = (
        get_database_summary()
    )

    # ========================================================
    # 3. QUERY OPTIMIZATION
    # ========================================================

    optimization = optimize_query(
        query
    )

    # ========================================================
    # 4. INDEX ANALYSIS
    # ========================================================

    index_analysis = IndexAdvisor().recommend(
        query_analysis
    )

    # ========================================================
    # 5. DIAGNOSIS
    # ========================================================

    diagnosis = build_diagnosis(
        query_analysis=query_analysis,
        optimization=optimization,
        index_analysis=index_analysis,
    )

    # ========================================================
    # 6. RECOMMENDATIONS
    # ========================================================

    recommendations = build_recommendations(
        optimization=optimization,
        index_analysis=index_analysis,
    )

    # ========================================================
    # 7. FORMAT QUERY ANALYSIS
    # ========================================================

    filters = [
        format_filter(condition)
        for condition in query_analysis.filters
    ]

    order_by = [
        format_order(condition)
        for condition in query_analysis.order_by
    ]

    group_by = [
        format_group(condition)
        for condition in query_analysis.group_by
    ]

    joins = [
        format_join(condition)
        for condition in query_analysis.joins
    ]

    # ========================================================
    # 8. CREATE RESULT
    # ========================================================

    return AdvisorResult(

        query=query,

        query_type=query_analysis.query_type,

        tables=query_analysis.tables,

        filters=filters,

        order_by=order_by,

        group_by=group_by,

        joins=joins,

        database_tables=database_tables,

        index_count=len(database_indexes),

        optimization=optimization,

        index_recommendations=(
            index_analysis.recommendations
        ),

        existing_indexes=(
            index_analysis.existing_indexes
        ),

        diagnosis=diagnosis,

        recommendations=recommendations,
    )


# ============================================================
# PRINT RESULT
# ============================================================

def print_advisor_result(
    result: AdvisorResult,
):
    """Pretty-print the complete advisor result."""

    print()
    print("=" * 60)
    print("DATABASE PERFORMANCE ADVISOR")
    print("=" * 60)

    # --------------------------------------------------------
    # Query
    # --------------------------------------------------------

    print()
    print("QUERY")
    print("-" * 60)
    print(result.query)

    # --------------------------------------------------------
    # Query Analysis
    # --------------------------------------------------------

    print()
    print("QUERY ANALYSIS")
    print("-" * 60)

    print(
        f"Query type : {result.query_type}"
    )

    if result.tables:

        print(
            f"Tables     : "
            f"{', '.join(result.tables)}"
        )

    if result.filters:

        print("Filters:")

        for item in result.filters:

            print(
                f"  • {item}"
            )

    if result.order_by:

        print("Order By:")

        for item in result.order_by:

            print(
                f"  • {item}"
            )

    if result.group_by:

        print("Group By:")

        for item in result.group_by:

            print(
                f"  • {item}"
            )

    if result.joins:

        print("Joins:")

        for item in result.joins:

            print(
                f"  • {item}"
            )

    # --------------------------------------------------------
    # Database Summary
    # --------------------------------------------------------

    print()
    print("DATABASE SUMMARY")
    print("-" * 60)

    print(
        f"Tables in database : "
        f"{len(result.database_tables)}"
    )

    print(
        f"Indexes            : "
        f"{result.index_count}"
    )

    # --------------------------------------------------------
    # Current Execution Plan
    # --------------------------------------------------------

    if result.optimization:

        optimization = result.optimization

        print()
        print("CURRENT EXECUTION PLAN")
        print("-" * 60)

        print(
            f"Planning time   : "
            f"{optimization.planning_time_ms:.3f} ms"
        )

        print(
            f"Execution time  : "
            f"{optimization.execution_time_ms:.3f} ms"
        )

        print(
            f"Root node       : "
            f"{optimization.root_node}"
        )

        if optimization.rows_examined is not None:

            print(
                f"Rows examined   : "
                f"{optimization.rows_examined}"
            )

        if optimization.rows_returned is not None:

            print(
                f"Rows returned   : "
                f"{optimization.rows_returned}"
            )

        print()
        print("Scan types:")

        for scan in optimization.scan_types:

            print(
                f"  • {scan}"
            )

        if optimization.indexes_used:

            print()
            print("Indexes used:")

            for index in optimization.indexes_used:

                print(
                    f"  • {index}"
                )

        print()

        print(
            f"Shared hit blocks : "
            f"{optimization.shared_hit_blocks}"
        )

        print(
            f"Shared read blocks: "
            f"{optimization.shared_read_blocks}"
        )

    # --------------------------------------------------------
    # Diagnosis
    # --------------------------------------------------------

    print()
    print("DIAGNOSIS")
    print("-" * 60)

    for item in result.diagnosis:

        print(
            f"  • {item}"
        )

    # --------------------------------------------------------
    # Index Analysis
    # --------------------------------------------------------

    print()
    print("INDEX ANALYSIS")
    print("-" * 60)

    if result.existing_indexes:

        print()
        print("EXISTING SUITABLE INDEXES")

        for index in result.existing_indexes:

            print(
                f"  ✓ "
                f"{index.table}"
                f"({', '.join(index.columns)})"
                f" -> "
                f"{index.existing_index_name}"
            )

    if result.index_recommendations:

        print()
        print("NEW INDEX RECOMMENDATIONS")

        for number, recommendation in enumerate(
            result.index_recommendations,
            start=1,
        ):

            print()
            print(
                f"Recommendation #{number}"
            )

            print(
                f"  Table       : "
                f"{recommendation.table}"
            )

            print(
                f"  Columns     : "
                f"{', '.join(recommendation.columns)}"
            )

            print(
                f"  Index type  : "
                f"{recommendation.index_type}"
            )

            print(
                f"  Priority    : "
                f"{recommendation.priority}"
            )

            print(
                f"  SQL         : "
                f"{recommendation.create_sql}"
            )

            print(
                f"  Reason      : "
                f"{recommendation.reason}"
            )

    if (
        not result.existing_indexes
        and not result.index_recommendations
    ):

        print(
            "  No index recommendations."
        )

    # --------------------------------------------------------
    # Final Recommendations
    # --------------------------------------------------------

    print()
    print("RECOMMENDATIONS")
    print("-" * 60)

    for recommendation in result.recommendations:

        print(
            f"  • {recommendation}"
        )

    print()
    print("=" * 60)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    test_query = """
SELECT
    o.order_id,
    c.name,
    o.total_amount
FROM orders o
JOIN customers c
    ON o.customer_id = c.customer_id
WHERE c.city = 'Chennai';
"""

    result = analyze_query(
        test_query
    )

    print_advisor_result(
        result
    )