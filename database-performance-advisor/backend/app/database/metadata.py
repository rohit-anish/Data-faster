"""
Database Performance Advisor
PostgreSQL Metadata Reader

Reads database schema metadata from PostgreSQL.

This module provides information about:

    - Tables
    - Columns
    - Primary keys
    - Foreign keys
    - Indexes
    - Index types
    - Indexed columns

It does not modify the database.
"""

from dataclasses import dataclass
from typing import List, Optional

import psycopg
from dotenv import load_dotenv

import os


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class ColumnMetadata:
    table_name: str
    column_name: str
    data_type: str
    is_nullable: bool
    default_value: Optional[str]


@dataclass
class PrimaryKeyMetadata:
    table_name: str
    column_name: str


@dataclass
class ForeignKeyMetadata:
    table_name: str
    column_name: str
    referenced_table: str
    referenced_column: str


@dataclass
class IndexMetadata:
    table_name: str
    index_name: str
    index_type: str
    columns: List[str]
    is_unique: bool
    is_primary: bool


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
# TABLES
# ============================================================

def get_tables() -> List[str]:
    """
    Return all user-created tables in the public schema.
    """

    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """

    with get_connection() as conn:

        with conn.cursor() as cursor:

            cursor.execute(query)

            rows = cursor.fetchall()

    return [
        row[0]
        for row in rows
    ]


# ============================================================
# COLUMNS
# ============================================================

def get_columns(
    table_name: Optional[str] = None,
) -> List[ColumnMetadata]:
    """
    Return column metadata.

    If table_name is supplied, only that table is returned.
    """

    query = """
        SELECT
            table_name,
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
    """

    parameters = []

    if table_name:

        query += """
            AND table_name = %s
        """

        parameters.append(
            table_name
        )

    query += """
        ORDER BY
            table_name,
            ordinal_position;
    """

    with get_connection() as conn:

        with conn.cursor() as cursor:

            cursor.execute(
                query,
                parameters,
            )

            rows = cursor.fetchall()

    return [
        ColumnMetadata(
            table_name=row[0],
            column_name=row[1],
            data_type=row[2],
            is_nullable=(
                row[3].upper() == "YES"
            ),
            default_value=row[4],
        )
        for row in rows
    ]


# ============================================================
# PRIMARY KEYS
# ============================================================

def get_primary_keys(
    table_name: Optional[str] = None,
) -> List[PrimaryKeyMetadata]:
    """
    Return primary key columns.
    """

    query = """
        SELECT
            tc.table_name,
            kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name =
               kcu.constraint_name
            AND tc.table_schema =
               kcu.table_schema
            AND tc.table_name =
               kcu.table_name
        WHERE tc.table_schema = 'public'
        AND tc.constraint_type = 'PRIMARY KEY'
    """

    parameters = []

    if table_name:

        query += """
            AND tc.table_name = %s
        """

        parameters.append(
            table_name
        )

    query += """
        ORDER BY
            tc.table_name,
            kcu.ordinal_position;
    """

    with get_connection() as conn:

        with conn.cursor() as cursor:

            cursor.execute(
                query,
                parameters,
            )

            rows = cursor.fetchall()

    return [
        PrimaryKeyMetadata(
            table_name=row[0],
            column_name=row[1],
        )
        for row in rows
    ]


# ============================================================
# FOREIGN KEYS
# ============================================================

def get_foreign_keys(
    table_name: Optional[str] = None,
) -> List[ForeignKeyMetadata]:
    """
    Return foreign key relationships.
    """

    query = """
        SELECT
            tc.table_name,
            kcu.column_name,
            ccu.table_name AS referenced_table,
            ccu.column_name AS referenced_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name =
               kcu.constraint_name
            AND tc.table_schema =
               kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name =
               ccu.constraint_name
            AND tc.table_schema =
               ccu.table_schema
        WHERE tc.table_schema = 'public'
        AND tc.constraint_type = 'FOREIGN KEY'
    """

    parameters = []

    if table_name:

        query += """
            AND tc.table_name = %s
        """

        parameters.append(
            table_name
        )

    query += """
        ORDER BY
            tc.table_name,
            kcu.column_name;
    """

    with get_connection() as conn:

        with conn.cursor() as cursor:

            cursor.execute(
                query,
                parameters,
            )

            rows = cursor.fetchall()

    return [
        ForeignKeyMetadata(
            table_name=row[0],
            column_name=row[1],
            referenced_table=row[2],
            referenced_column=row[3],
        )
        for row in rows
    ]


# ============================================================
# INDEXES
# ============================================================

def get_indexes(
    table_name: Optional[str] = None,
) -> List[IndexMetadata]:
    """
    Return index metadata from PostgreSQL.

    Uses PostgreSQL's pg_catalog instead of
    information_schema because PostgreSQL-specific
    index information is required.
    """

    query = """
        SELECT
            t.relname AS table_name,
            i.relname AS index_name,
            am.amname AS index_type,
            ix.indisunique,
            ix.indisprimary,
            ARRAY_AGG(
                a.attname
                ORDER BY k.ordinality
            ) AS columns
        FROM pg_index ix

        JOIN pg_class i
            ON i.oid = ix.indexrelid

        JOIN pg_class t
            ON t.oid = ix.indrelid

        JOIN pg_namespace n
            ON n.oid = t.relnamespace

        JOIN pg_am am
            ON i.relam = am.oid

        JOIN LATERAL unnest(
            ix.indkey
        ) WITH ORDINALITY AS k(attnum, ordinality)
            ON TRUE

        JOIN pg_attribute a
            ON a.attrelid = t.oid
            AND a.attnum = k.attnum

        WHERE n.nspname = 'public'
    """

    parameters = []

    if table_name:

        query += """
            AND t.relname = %s
        """

        parameters.append(
            table_name
        )

    query += """
        GROUP BY
            t.relname,
            i.relname,
            am.amname,
            ix.indisunique,
            ix.indisprimary

        ORDER BY
            t.relname,
            i.relname;
    """

    with get_connection() as conn:

        with conn.cursor() as cursor:

            cursor.execute(
                query,
                parameters,
            )

            rows = cursor.fetchall()

    return [
        IndexMetadata(
            table_name=row[0],
            index_name=row[1],
            index_type=row[2],
            columns=list(row[5]),
            is_unique=row[3],
            is_primary=row[4],
        )
        for row in rows
    ]


# ============================================================
# FIND INDEX
# ============================================================

def find_index_for_columns(
    table_name: str,
    columns: List[str],
) -> Optional[IndexMetadata]:
    """
    Find an existing index whose leading columns match
    the requested columns.

    Example:

        Existing index:
            (customer_id, total_amount)

        Requested:
            (customer_id)

        Result:
            Existing index is considered usable.

    But:

        Existing:
            (total_amount, customer_id)

        Requested:
            (customer_id)

        Result:
            No match.
    """

    indexes = get_indexes(
        table_name
    )

    requested = [
        column.lower()
        for column in columns
    ]

    for index in indexes:

        existing = [
            column.lower()
            for column in index.columns
        ]

        if (
            len(existing) >= len(requested)
            and existing[:len(requested)]
            == requested
        ):

            return index

    return None


# ============================================================
# PRINT DATABASE METADATA
# ============================================================

def print_metadata():

    print("=" * 60)

    print(
        "DATABASE PERFORMANCE ADVISOR"
    )

    print(
        "PostgreSQL Metadata Test"
    )

    print("=" * 60)

    # --------------------------------------------------------
    # Tables
    # --------------------------------------------------------

    tables = get_tables()

    print()

    print("TABLES:")

    for table in tables:

        print(
            f"  {table}"
        )

    # --------------------------------------------------------
    # Columns
    # --------------------------------------------------------

    print()

    print("COLUMNS:")

    columns = get_columns()

    for column in columns:

        print(
            f"  {column.table_name}."
            f"{column.column_name}"
            f" : {column.data_type}"
        )

    # --------------------------------------------------------
    # Primary keys
    # --------------------------------------------------------

    print()

    print("PRIMARY KEYS:")

    primary_keys = get_primary_keys()

    for key in primary_keys:

        print(
            f"  {key.table_name}."
            f"{key.column_name}"
        )

    # --------------------------------------------------------
    # Foreign keys
    # --------------------------------------------------------

    print()

    print("FOREIGN KEYS:")

    foreign_keys = get_foreign_keys()

    for key in foreign_keys:

        print(
            f"  {key.table_name}."
            f"{key.column_name}"
            f" -> "
            f"{key.referenced_table}."
            f"{key.referenced_column}"
        )

    # --------------------------------------------------------
    # Indexes
    # --------------------------------------------------------

    print()

    print("INDEXES:")

    indexes = get_indexes()

    for index in indexes:

        print(
            f"  {index.table_name}."
            f"{index.index_name}"
        )

        print(
            f"    Type    : "
            f"{index.index_type}"
        )

        print(
            f"    Columns : "
            f"{', '.join(index.columns)}"
        )

        print(
            f"    Unique  : "
            f"{index.is_unique}"
        )

        print(
            f"    Primary : "
            f"{index.is_primary}"
        )

    print()

    print("=" * 60)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    try:

        print_metadata()

    except Exception as exc:

        print()

        print(
            "Metadata test failed:"
        )

        print(
            f"  {exc}"
        )