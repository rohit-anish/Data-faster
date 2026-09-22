"""
Database Performance Advisor
Index Advisor

Analyzes SQL queries and PostgreSQL metadata to determine
whether useful indexes already exist and whether new indexes
should be recommended.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from backend.app.analyzers.query_analyzer import (
    QueryAnalysis,
    FilterCondition,
)

from backend.app.database.metadata import (
    IndexMetadata,
    find_index_for_columns,
)


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class IndexRecommendation:

    table: str

    columns: List[str]

    index_type: str

    create_sql: str

    reason: str

    priority: str = "MEDIUM"

    already_exists: bool = False

    existing_index_name: Optional[str] = None


@dataclass
class IndexAnalysis:

    recommendations: List[IndexRecommendation] = field(
        default_factory=list
    )

    existing_indexes: List[IndexRecommendation] = field(
        default_factory=list
    )

    @property
    def recommendation_count(self) -> int:

        return len(self.recommendations)

    @property
    def existing_index_count(self) -> int:

        return len(self.existing_indexes)


# ============================================================
# INDEX ADVISOR
# ============================================================

class IndexAdvisor:
    """
    Generates index recommendations and checks existing
    PostgreSQL indexes before recommending a new one.
    """

    def recommend(
        self,
        analysis: QueryAnalysis,
    ) -> IndexAnalysis:

        recommendations = []

        existing_indexes = []

        # ----------------------------------------------------
        # 1. WHERE filters
        # ----------------------------------------------------

        for filter_condition in analysis.filters:

            recommendation = (
                self._recommend_for_filter(
                    filter_condition
                )
            )

            if recommendation:

                if recommendation.already_exists:

                    existing_indexes.append(
                        recommendation
                    )

                else:

                    recommendations.append(
                        recommendation
                    )

        # ----------------------------------------------------
        # 2. JOIN conditions
        # ----------------------------------------------------

        for join in analysis.joins:

            join_recommendations = (
                self._recommend_for_join(
                    join,
                    analysis,
                )
            )

            for recommendation in (
                join_recommendations
            ):

                if recommendation.already_exists:

                    existing_indexes.append(
                        recommendation
                    )

                else:

                    recommendations.append(
                        recommendation
                    )

        # ----------------------------------------------------
        # 3. Composite index
        # ----------------------------------------------------

        if (
            analysis.has_where
            and analysis.has_order_by
        ):

            composite = (
                self._recommend_composite_index(
                    analysis
                )
            )

            if composite:

                if composite.already_exists:

                    existing_indexes.append(
                        composite
                    )

                else:

                    recommendations.append(
                        composite
                    )

        # ----------------------------------------------------
        # Remove duplicate recommendations
        # ----------------------------------------------------

        recommendations = (
            self._remove_duplicates(
                recommendations
            )
        )

        existing_indexes = (
            self._remove_duplicates(
                existing_indexes
            )
        )

        return IndexAnalysis(
            recommendations=recommendations,
            existing_indexes=existing_indexes,
        )

    # ========================================================
    # FILTER ANALYSIS
    # ========================================================

    def _recommend_for_filter(
        self,
        condition: FilterCondition,
    ) -> Optional[IndexRecommendation]:

        table = condition.table

        column = condition.column

        operator = condition.operator

        if not table or not column:

            return None

        # ----------------------------------------------------
        # Currently supported index recommendation operators
        # ----------------------------------------------------

        if operator == "=":

            index_type = "B-Tree"

            priority = "HIGH"

            reason = (
                f"The column '{column}' in table "
                f"'{table}' is used in an equality "
                f"WHERE filter. A B-Tree index can "
                f"allow PostgreSQL to locate matching "
                f"rows without scanning the entire table."
            )

        elif operator in {
            ">",
            "<",
            ">=",
            "<=",
        }:

            index_type = "B-Tree"

            priority = "MEDIUM"

            reason = (
                f"The column '{column}' in table "
                f"'{table}' is used in a range filter "
                f"({operator}). B-Tree indexes support "
                f"efficient range searches."
            )

        elif operator == "LIKE":

            index_type = "B-Tree"

            priority = "MEDIUM"

            reason = (
                f"The column '{column}' in table "
                f"'{table}' is used with LIKE. "
                f"An index may help depending on "
                f"the search pattern."
            )

        else:

            return None

        # ----------------------------------------------------
        # Check existing index
        # ----------------------------------------------------

        existing_index = (
            find_index_for_columns(
                table,
                [column],
            )
        )

        if existing_index:

            return IndexRecommendation(

                table=table,

                columns=[column],

                index_type=index_type,

                create_sql=(
                    f"CREATE INDEX "
                    f"idx_{table}_{column} "
                    f"ON {table}({column});"
                ),

                reason=(
                    f"An appropriate index already "
                    f"exists on '{table}.{column}'."
                ),

                priority=priority,

                already_exists=True,

                existing_index_name=(
                    existing_index.index_name
                ),
            )

        # ----------------------------------------------------
        # New recommendation
        # ----------------------------------------------------

        return IndexRecommendation(

            table=table,

            columns=[column],

            index_type=index_type,

            create_sql=(
                f"CREATE INDEX "
                f"idx_{table}_{column} "
                f"ON {table}({column});"
            ),

            reason=reason,

            priority=priority,

            already_exists=False,
        )

    # ========================================================
    # JOIN ANALYSIS
    # ========================================================

    def _recommend_for_join(
        self,
        join,
        analysis: QueryAnalysis,
    ) -> List[IndexRecommendation]:

        recommendations = []

        actual_tables = set(
            analysis.tables
        )

        left_table = (
            self._resolve_join_table(
                join.left_table,
                actual_tables,
            )
        )

        right_table = (
            self._resolve_join_table(
                join.right_table,
                actual_tables,
            )
        )

        # ----------------------------------------------------
        # Left JOIN column
        # ----------------------------------------------------

        if left_table:

            recommendation = (
                self._create_join_index_recommendation(
                    left_table,
                    join.left_column,
                )
            )

            if recommendation:

                recommendations.append(
                    recommendation
                )

        # ----------------------------------------------------
        # Right JOIN column
        # ----------------------------------------------------

        if right_table:

            recommendation = (
                self._create_join_index_recommendation(
                    right_table,
                    join.right_column,
                )
            )

            if recommendation:

                recommendations.append(
                    recommendation
                )

        return recommendations

    # ========================================================
    # JOIN INDEX
    # ========================================================

    def _create_join_index_recommendation(
        self,
        table: str,
        column: str,
    ) -> Optional[IndexRecommendation]:

        existing_index = (
            find_index_for_columns(
                table,
                [column],
            )
        )

        if existing_index:

            return IndexRecommendation(

                table=table,

                columns=[column],

                index_type="B-Tree",

                create_sql=(
                    f"CREATE INDEX "
                    f"idx_{table}_{column} "
                    f"ON {table}({column});"
                ),

                reason=(
                    f"An appropriate index already "
                    f"exists on the JOIN column "
                    f"'{table}.{column}'."
                ),

                priority="MEDIUM",

                already_exists=True,

                existing_index_name=(
                    existing_index.index_name
                ),
            )

        return IndexRecommendation(

            table=table,

            columns=[column],

            index_type="B-Tree",

            create_sql=(
                f"CREATE INDEX "
                f"idx_{table}_{column} "
                f"ON {table}({column});"
            ),

            reason=(
                f"The column '{column}' in table "
                f"'{table}' is used in a JOIN "
                f"condition. An index can help "
                f"PostgreSQL efficiently locate "
                f"matching rows."
            ),

            priority="MEDIUM",

            already_exists=False,
        )

    # ========================================================
    # JOIN TABLE RESOLUTION
    # ========================================================

    def _resolve_join_table(
        self,
        reference: str,
        actual_tables: set,
    ) -> Optional[str]:

        if reference in actual_tables:

            return reference

        alias_map = {

            "o": "orders",

            "c": "customers",

            "p": "products",

            "oi": "order_items",

        }

        resolved = alias_map.get(
            reference
        )

        if resolved in actual_tables:

            return resolved

        return None

    # ========================================================
    # COMPOSITE INDEX
    # ========================================================

    def _recommend_composite_index(
        self,
        analysis: QueryAnalysis,
    ) -> Optional[IndexRecommendation]:

        if not analysis.filters:

            return None

        if not analysis.order_by:

            return None

        filter_condition = (
            analysis.filters[0]
        )

        order_condition = (
            analysis.order_by[0]
        )

        table = filter_condition.table

        filter_column = (
            filter_condition.column
        )

        order_column = (
            order_condition.column
        )

        if not table:

            return None

        if not filter_column:

            return None

        if not order_column:

            return None

        if filter_column == order_column:

            return None

        # ----------------------------------------------------
        # ORDER BY must belong to same table
        # ----------------------------------------------------

        if (
            order_condition.table
            and
            order_condition.table != table
        ):

            return None

        columns = [
            filter_column,
            order_column,
        ]

        existing_index = (
            find_index_for_columns(
                table,
                columns,
            )
        )

        direction = (
            order_condition.direction
        )

        # ----------------------------------------------------
        # Existing composite index
        # ----------------------------------------------------

        if existing_index:

            return IndexRecommendation(

                table=table,

                columns=columns,

                index_type="B-Tree Composite",

                create_sql=(
                    f"CREATE INDEX "
                    f"idx_{table}_"
                    f"{filter_column}_"
                    f"{order_column} "
                    f"ON {table}("
                    f"{filter_column}, "
                    f"{order_column} {direction}"
                    f");"
                ),

                reason=(
                    f"An appropriate composite index "
                    f"already exists for "
                    f"'{filter_column}' and "
                    f"'{order_column}'."
                ),

                priority="HIGH",

                already_exists=True,

                existing_index_name=(
                    existing_index.index_name
                ),
            )

        # ----------------------------------------------------
        # New composite recommendation
        # ----------------------------------------------------

        return IndexRecommendation(

            table=table,

            columns=columns,

            index_type="B-Tree Composite",

            create_sql=(
                f"CREATE INDEX "
                f"idx_{table}_"
                f"{filter_column}_"
                f"{order_column} "
                f"ON {table}("
                f"{filter_column}, "
                f"{order_column} {direction}"
                f");"
            ),

            reason=(
                f"The query filters by "
                f"'{filter_column}' and sorts by "
                f"'{order_column}'. A composite "
                f"index may help PostgreSQL locate "
                f"filtered rows and reduce sorting work."
            ),

            priority="HIGH",

            already_exists=False,
        )

    # ========================================================
    # DUPLICATE REMOVAL
    # ========================================================

    def _remove_duplicates(
        self,
        recommendations: List[
            IndexRecommendation
        ],
    ) -> List[IndexRecommendation]:

        unique = {}

        for recommendation in recommendations:

            key = (

                recommendation.table,

                tuple(
                    recommendation.columns
                ),

            )

            if key not in unique:

                unique[key] = recommendation

        return list(
            unique.values()
        )


# ============================================================
# PRINTING
# ============================================================

def print_index_analysis(
    result: IndexAnalysis,
) -> None:

    print()

    print("=" * 60)

    print("INDEX ADVISOR")

    print("=" * 60)

    # --------------------------------------------------------
    # Existing indexes
    # --------------------------------------------------------

    if result.existing_indexes:

        print()

        print(
            "EXISTING SUITABLE INDEXES"
        )

        for index in result.existing_indexes:

            print()

            print("-" * 60)

            print(
                f"Table       : "
                f"{index.table}"
            )

            print(
                f"Columns     : "
                f"{', '.join(index.columns)}"
            )

            print(
                f"Index type  : "
                f"{index.index_type}"
            )

            print(
                f"Index name  : "
                f"{index.existing_index_name}"
            )

            print()

            print(
                "Status      : "
                "ALREADY EXISTS"
            )

            print(
                f"Reason      : "
                f"{index.reason}"
            )

    # --------------------------------------------------------
    # New recommendations
    # --------------------------------------------------------

    if result.recommendations:

        print()

        print(
            "NEW INDEX RECOMMENDATIONS"
        )

        for number, recommendation in enumerate(
            result.recommendations,
            start=1,
        ):

            print()

            print("-" * 60)

            print(
                f"Recommendation #{number}"
            )

            print(
                f"Table       : "
                f"{recommendation.table}"
            )

            print(
                f"Columns     : "
                f"{', '.join(recommendation.columns)}"
            )

            print(
                f"Index type  : "
                f"{recommendation.index_type}"
            )

            print(
                f"Priority    : "
                f"{recommendation.priority}"
            )

            print()

            print(
                "Suggested SQL:"
            )

            print(
                f"  {recommendation.create_sql}"
            )

            print()

            print(
                "Reason:"
            )

            print(
                f"  {recommendation.reason}"
            )

    elif not result.existing_indexes:

        print()

        print(
            "No index recommendations."
        )

    print()

    print("=" * 60)


# ============================================================
# TEST
# ============================================================

def main():

    from backend.app.analyzers.query_analyzer import (
        analyze_query,
    )

    test_queries = [

        """
        SELECT *
        FROM orders
        WHERE customer_id = 75992;
        """,

        """
        SELECT *
        FROM orders
        WHERE total_amount > 50000
        AND total_amount < 100000;
        """,

        """
        SELECT *
        FROM orders
        WHERE customer_id = 75992
        ORDER BY total_amount DESC
        LIMIT 10;
        """,

        """
        SELECT
            o.order_id,
            c.name,
            o.total_amount
        FROM orders o
        JOIN customers c
            ON o.customer_id = c.customer_id
        WHERE c.city = 'Chennai';
        """,

        """
        SELECT
            customer_id,
            COUNT(*) AS order_count
        FROM orders
        GROUP BY customer_id
        ORDER BY order_count DESC
        LIMIT 20;
        """,
    ]

    print("=" * 60)

    print(
        "DATABASE PERFORMANCE ADVISOR"
    )

    print(
        "Index Advisor Test"
    )

    print("=" * 60)

    for number, query in enumerate(
        test_queries,
        start=1,
    ):

        print()

        print(
            f"TEST QUERY {number}"
        )

        print(
            "-" * 60
        )

        print(
            query.strip()
        )

        analysis = analyze_query(
            query
        )

        result = IndexAdvisor().recommend(
            analysis
        )

        print_index_analysis(
            result
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()