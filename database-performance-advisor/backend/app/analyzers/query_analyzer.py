"""
Database Performance Advisor
Query Analyzer

Analyzes SQL SELECT queries and extracts useful information
for the optimization and indexing components.

Current version focuses on:
    - SELECT queries
    - WHERE conditions
    - equality conditions
    - comparison/range conditions
    - AND conditions
    - ORDER BY
    - GROUP BY
    - JOIN conditions

This module intentionally performs lightweight SQL analysis.
It does not execute the user's query.
"""

import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class FilterCondition:
    """
    Represents one WHERE condition.
    """

    table: Optional[str]
    column: str
    operator: str
    value: str


@dataclass
class OrderCondition:
    """
    Represents one ORDER BY column.
    """

    table: Optional[str]
    column: str
    direction: str


@dataclass
class GroupCondition:
    """
    Represents one GROUP BY column.
    """

    table: Optional[str]
    column: str


@dataclass
class JoinCondition:
    """
    Represents one JOIN condition.
    """

    left_table: str
    left_column: str
    right_table: str
    right_column: str


@dataclass
class QueryAnalysis:
    """
    Complete analysis of a SQL SELECT query.
    """

    query_type: str

    tables: List[str]

    filters: List[FilterCondition]

    order_by: List[OrderCondition]

    group_by: List[GroupCondition]

    joins: List[JoinCondition]

    has_where: bool

    has_order_by: bool

    has_group_by: bool

    has_join: bool


# ============================================================
# QUERY CLEANING
# ============================================================

def clean_query(query: str) -> str:
    """
    Clean whitespace and remove the trailing semicolon.
    """

    if not query or not query.strip():
        raise ValueError("SQL query cannot be empty.")

    cleaned = re.sub(
        r"\s+",
        " ",
        query.strip(),
    )

    cleaned = cleaned.rstrip(";").strip()

    return cleaned


# ============================================================
# QUERY TYPE
# ============================================================

def detect_query_type(query: str) -> str:
    """
    Detect the main SQL operation.
    """

    match = re.match(
        r"^\s*(SELECT|INSERT|UPDATE|DELETE)",
        query,
        re.IGNORECASE,
    )

    if not match:
        return "UNKNOWN"

    return match.group(1).upper()


# ============================================================
# TABLE + ALIAS EXTRACTION
# ============================================================

def extract_table_aliases(
    query: str,
) -> Dict[str, str]:
    """
    Extract table aliases.

    Example:

        FROM orders o
        JOIN customers c
            ON o.customer_id = c.customer_id

    Returns:

        {
            "o": "orders",
            "c": "customers"
        }

    Tables without aliases are also mapped to themselves.
    """

    aliases: Dict[str, str] = {}

    # --------------------------------------------------------
    # FROM
    # --------------------------------------------------------

    from_pattern = re.compile(
        r"\bFROM\s+"
        r"([a-zA-Z_][a-zA-Z0-9_.]*)"
        r"(?:\s+(?:AS\s+)?"
        r"([a-zA-Z_][a-zA-Z0-9_]*))?",
        re.IGNORECASE,
    )

    from_match = from_pattern.search(query)

    if from_match:

        table = from_match.group(1)

        possible_alias = from_match.group(2)

        # Avoid treating SQL keywords as aliases.
        if possible_alias and possible_alias.upper() not in {
            "WHERE",
            "JOIN",
            "INNER",
            "LEFT",
            "RIGHT",
            "FULL",
            "CROSS",
            "ON",
            "GROUP",
            "ORDER",
            "LIMIT",
            "OFFSET",
            "HAVING",
        }:
            aliases[possible_alias] = table

        aliases[table] = table

    # --------------------------------------------------------
    # JOIN
    # --------------------------------------------------------

    join_pattern = re.compile(
        r"\bJOIN\s+"
        r"([a-zA-Z_][a-zA-Z0-9_.]*)"
        r"(?:\s+(?:AS\s+)?"
        r"([a-zA-Z_][a-zA-Z0-9_]*))?",
        re.IGNORECASE,
    )

    for match in join_pattern.finditer(query):

        table = match.group(1)

        possible_alias = match.group(2)

        if possible_alias and possible_alias.upper() not in {
            "ON",
            "WHERE",
            "JOIN",
            "INNER",
            "LEFT",
            "RIGHT",
            "FULL",
            "CROSS",
            "GROUP",
            "ORDER",
            "LIMIT",
            "OFFSET",
            "HAVING",
        }:
            aliases[possible_alias] = table

        aliases[table] = table

    return aliases


# ============================================================
# TABLE EXTRACTION
# ============================================================

def extract_tables(query: str) -> List[str]:
    """
    Extract actual table names referenced by FROM and JOIN.
    """

    tables = []

    aliases = extract_table_aliases(query)

    for table in aliases.values():

        if table not in tables:
            tables.append(table)

    return tables


# ============================================================
# RESOLVE TABLE
# ============================================================

def resolve_table(
    qualifier: Optional[str],
    aliases: Dict[str, str],
    tables: List[str],
) -> Optional[str]:
    """
    Resolve a column qualifier to its actual table.

    Examples:

        c.city
        -> customers

        o.customer_id
        -> orders

    For an unqualified column in a single-table query,
    the only table is returned.
    """

    if qualifier:

        return aliases.get(
            qualifier,
            qualifier,
        )

    if len(tables) == 1:

        return tables[0]

    return None


# ============================================================
# WHERE CLAUSE EXTRACTION
# ============================================================

def extract_where_clause(
    query: str,
) -> Optional[str]:
    """
    Extract the WHERE clause without executing it.

    Stops at:
        GROUP BY
        ORDER BY
        LIMIT
        OFFSET
        HAVING
    """

    match = re.search(
        r"\bWHERE\s+(.+?)"
        r"(?=\bGROUP\s+BY\b"
        r"|\bORDER\s+BY\b"
        r"|\bLIMIT\b"
        r"|\bOFFSET\b"
        r"|\bHAVING\b"
        r"|$)",
        query,
        re.IGNORECASE,
    )

    if not match:
        return None

    return match.group(1).strip()


# ============================================================
# WHERE CONDITION PARSER
# ============================================================

def extract_filters(
    query: str,
) -> List[FilterCondition]:
    """
    Extract simple WHERE conditions.

    Supports:

        =
        >
        <
        >=
        <=
        <>
        !=
        LIKE
        IN

    Supports both:

        customer_id = 75992

    and:

        c.city = 'Chennai'
    """

    where_clause = extract_where_clause(query)

    if not where_clause:
        return []

    filters = []

    tables = extract_tables(query)

    aliases = extract_table_aliases(query)

    # --------------------------------------------------------
    # Split simple AND conditions.
    # --------------------------------------------------------

    conditions = re.split(
        r"\s+AND\s+",
        where_clause,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Condition pattern
    # --------------------------------------------------------

    condition_pattern = re.compile(
        r"""
        ^\s*
        (?:
            ([a-zA-Z_][a-zA-Z0-9_]*)\.
        )?
        ([a-zA-Z_][a-zA-Z0-9_]*)
        \s*
        (>=|<=|<>|!=|=|>|<|LIKE|IN)
        \s*
        (.+?)
        \s*$
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    for condition in conditions:

        match = condition_pattern.match(
            condition.strip()
        )

        if not match:
            continue

        qualifier = match.group(1)

        column = match.group(2)

        operator = match.group(3).upper()

        value = match.group(4).strip()

        table = resolve_table(
            qualifier,
            aliases,
            tables,
        )

        filters.append(
            FilterCondition(
                table=table,
                column=column,
                operator=operator,
                value=value,
            )
        )

    return filters


# ============================================================
# ORDER BY
# ============================================================

def extract_order_by(
    query: str,
) -> List[OrderCondition]:
    """
    Extract ORDER BY columns and directions.
    """

    match = re.search(
        r"\bORDER\s+BY\s+(.+?)"
        r"(?=\bLIMIT\b|\bOFFSET\b|$)",
        query,
        re.IGNORECASE,
    )

    if not match:
        return []

    order_clause = match.group(1).strip()

    tables = extract_tables(query)

    aliases = extract_table_aliases(query)

    conditions = []

    for expression in order_clause.split(","):

        expression = expression.strip()

        match = re.match(
            r"""
            ^
            (?:
                ([a-zA-Z_][a-zA-Z0-9_]*)\.
            )?
            ([a-zA-Z_][a-zA-Z0-9_]*)
            (?:\s+(ASC|DESC))?
            $
            """,
            expression,
            re.IGNORECASE | re.VERBOSE,
        )

        if not match:
            continue

        qualifier = match.group(1)

        column = match.group(2)

        direction = (
            match.group(3).upper()
            if match.group(3)
            else "ASC"
        )

        table = resolve_table(
            qualifier,
            aliases,
            tables,
        )

        conditions.append(
            OrderCondition(
                table=table,
                column=column,
                direction=direction,
            )
        )

    return conditions


# ============================================================
# GROUP BY
# ============================================================

def extract_group_by(
    query: str,
) -> List[GroupCondition]:
    """
    Extract GROUP BY columns.
    """

    match = re.search(
        r"\bGROUP\s+BY\s+(.+?)"
        r"(?=\bHAVING\b|\bORDER\s+BY\b|\bLIMIT\b|$)",
        query,
        re.IGNORECASE,
    )

    if not match:
        return []

    group_clause = match.group(1).strip()

    tables = extract_tables(query)

    aliases = extract_table_aliases(query)

    groups = []

    for expression in group_clause.split(","):

        expression = expression.strip()

        match = re.match(
            r"""
            ^
            (?:
                ([a-zA-Z_][a-zA-Z0-9_]*)\.
            )?
            ([a-zA-Z_][a-zA-Z0-9_]*)
            $
            """,
            expression,
            re.IGNORECASE | re.VERBOSE,
        )

        if not match:
            continue

        qualifier = match.group(1)

        column = match.group(2)

        table = resolve_table(
            qualifier,
            aliases,
            tables,
        )

        groups.append(
            GroupCondition(
                table=table,
                column=column,
            )
        )

    return groups


# ============================================================
# JOIN EXTRACTION
# ============================================================

def extract_joins(
    query: str,
) -> List[JoinCondition]:
    """
    Extract simple JOIN equality conditions.

    Example:

        JOIN customers c
            ON o.customer_id = c.customer_id
    """

    joins = []

    join_pattern = re.compile(
        r"""
        \bJOIN\s+
        ([a-zA-Z_][a-zA-Z0-9_]*)
        (?:\s+(?:AS\s+)?[a-zA-Z_][a-zA-Z0-9_]*)?
        \s+
        ON\s+
        ([a-zA-Z_][a-zA-Z0-9_]*)\.
        ([a-zA-Z_][a-zA-Z0-9_]*)
        \s*=\s*
        ([a-zA-Z_][a-zA-Z0-9_]*)\.
        ([a-zA-Z_][a-zA-Z0-9_]*)
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    for match in join_pattern.finditer(query):

        joins.append(
            JoinCondition(
                left_table=match.group(2),
                left_column=match.group(3),
                right_table=match.group(4),
                right_column=match.group(5),
            )
        )

    return joins


# ============================================================
# COMPLETE QUERY ANALYSIS
# ============================================================

def analyze_query(
    query: str,
) -> QueryAnalysis:
    """
    Analyze a SQL query and return structured information.
    """

    cleaned = clean_query(query)

    query_type = detect_query_type(
        cleaned
    )

    tables = extract_tables(
        cleaned
    )

    filters = extract_filters(
        cleaned
    )

    order_by = extract_order_by(
        cleaned
    )

    group_by = extract_group_by(
        cleaned
    )

    joins = extract_joins(
        cleaned
    )

    return QueryAnalysis(
        query_type=query_type,

        tables=tables,

        filters=filters,

        order_by=order_by,

        group_by=group_by,

        joins=joins,

        has_where=len(filters) > 0,

        has_order_by=len(order_by) > 0,

        has_group_by=len(group_by) > 0,

        has_join=len(joins) > 0,
    )


# ============================================================
# DICTIONARY CONVERSION
# ============================================================

def analysis_to_dict(
    analysis: QueryAnalysis,
) -> Dict[str, Any]:
    """
    Convert QueryAnalysis into a JSON-friendly dictionary.
    """

    return asdict(analysis)


# ============================================================
# DISPLAY HELPER
# ============================================================

def print_analysis(
    analysis: QueryAnalysis,
) -> None:
    """
    Print a human-readable analysis.
    """

    print()
    print("=" * 60)
    print("QUERY ANALYSIS")
    print("=" * 60)

    print()

    print(
        f"Query type : {analysis.query_type}"
    )

    print(
        f"Tables     : "
        f"{', '.join(analysis.tables) or 'None'}"
    )

    print()

    print("Filters:")

    if analysis.filters:

        for filter_condition in analysis.filters:

            table_prefix = (
                f"{filter_condition.table}."
                if filter_condition.table
                else ""
            )

            print(
                f"  {table_prefix}"
                f"{filter_condition.column} "
                f"{filter_condition.operator} "
                f"{filter_condition.value}"
            )

    else:

        print("  None")

    print()

    print("ORDER BY:")

    if analysis.order_by:

        for condition in analysis.order_by:

            table_prefix = (
                f"{condition.table}."
                if condition.table
                else ""
            )

            print(
                f"  {table_prefix}"
                f"{condition.column} "
                f"{condition.direction}"
            )

    else:

        print("  None")

    print()

    print("GROUP BY:")

    if analysis.group_by:

        for condition in analysis.group_by:

            table_prefix = (
                f"{condition.table}."
                if condition.table
                else ""
            )

            print(
                f"  {table_prefix}"
                f"{condition.column}"
            )

    else:

        print("  None")

    print()

    print("JOINS:")

    if analysis.joins:

        for join in analysis.joins:

            print(
                f"  {join.left_table}."
                f"{join.left_column}"
                f" = "
                f"{join.right_table}."
                f"{join.right_column}"
            )

    else:

        print("  None")

    print()

    print(
        f"Has WHERE    : "
        f"{analysis.has_where}"
    )

    print(
        f"Has ORDER BY : "
        f"{analysis.has_order_by}"
    )

    print(
        f"Has GROUP BY : "
        f"{analysis.has_group_by}"
    )

    print(
        f"Has JOIN     : "
        f"{analysis.has_join}"
    )

    print("=" * 60)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    TEST_QUERIES = [

        # ----------------------------------------------------
        # Query 1: Equality filter
        # ----------------------------------------------------

        """
        SELECT *
        FROM orders
        WHERE customer_id = 75992;
        """,

        # ----------------------------------------------------
        # Query 2: Range filter
        # ----------------------------------------------------

        """
        SELECT *
        FROM orders
        WHERE total_amount > 50000
        AND total_amount < 100000;
        """,

        # ----------------------------------------------------
        # Query 3: Filter + ORDER BY
        # ----------------------------------------------------

        """
        SELECT *
        FROM orders
        WHERE customer_id = 75992
        ORDER BY total_amount DESC
        LIMIT 10;
        """,

        # ----------------------------------------------------
        # Query 4: JOIN
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Query 5: GROUP BY
        # ----------------------------------------------------

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
    print("DATABASE PERFORMANCE ADVISOR")
    print("Query Analyzer Test")
    print("=" * 60)

    for number, query in enumerate(
        TEST_QUERIES,
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

        try:

            analysis = analyze_query(
                query
            )

            print_analysis(
                analysis
            )

        except Exception as exc:

            print()

            print(
                f"Analysis failed: {exc}"
            )