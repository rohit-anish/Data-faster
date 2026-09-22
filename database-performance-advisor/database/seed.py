import argparse
import os
import random
import time
from datetime import datetime, timedelta

import psycopg
from dotenv import load_dotenv
from faker import Faker


# ============================================================
# DATABASE PERFORMANCE ADVISOR
# Synthetic Database Generator
# ============================================================

load_dotenv()

fake = Faker()
Faker.seed(42)
random.seed(42)


# ============================================================
# CONFIGURATION
# ============================================================

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "db_performance_advisor"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

BATCH_SIZE = 5000

CATEGORIES = [
    "Electronics",
    "Computers",
    "Mobile",
    "Accessories",
    "Home",
    "Kitchen",
    "Gaming",
    "Books",
    "Sports",
    "Fashion",
]

STATES_AND_CITIES = {
    "Tamil Nadu": [
        "Chennai",
        "Coimbatore",
        "Madurai",
        "Salem",
        "Trichy",
    ],
    "Maharashtra": [
        "Mumbai",
        "Pune",
        "Nagpur",
        "Nashik",
        "Thane",
    ],
    "Karnataka": [
        "Bangalore",
        "Mysore",
        "Mangalore",
        "Hubli",
        "Belgaum",
    ],
    "Delhi": [
        "New Delhi",
        "Delhi",
    ],
    "Telangana": [
        "Hyderabad",
        "Warangal",
        "Nizamabad",
    ],
    "Kerala": [
        "Kochi",
        "Thiruvananthapuram",
        "Kozhikode",
        "Thrissur",
    ],
    "West Bengal": [
        "Kolkata",
        "Howrah",
        "Durgapur",
    ],
    "Gujarat": [
        "Ahmedabad",
        "Surat",
        "Vadodara",
        "Rajkot",
    ],
    "Rajasthan": [
        "Jaipur",
        "Jodhpur",
        "Udaipur",
        "Kota",
    ],
    "Uttar Pradesh": [
        "Lucknow",
        "Kanpur",
        "Agra",
        "Varanasi",
    ],
}


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    return psycopg.connect(**DB_CONFIG)


# ============================================================
# RESET DATABASE DATA
# ============================================================

def reset_tables(conn):
    print("\nResetting existing data...")

    with conn.cursor() as cursor:
        cursor.execute(
            """
            TRUNCATE TABLE
                order_items,
                orders,
                products,
                customers
            RESTART IDENTITY CASCADE;
            """
        )

    conn.commit()

    print("Existing data removed.")
    print("Sequences reset.")


# ============================================================
# GENERATE CUSTOMERS
# ============================================================

def generate_customers(conn, count):
    print(f"\nGenerating {count:,} customers...")

    start_time = time.perf_counter()

    with conn.cursor() as cursor:
        with cursor.copy(
            """
            COPY customers
            (name, email, city, state)
            FROM STDIN
            """
        ) as copy:

            for customer_id in range(1, count + 1):
                name = fake.name()

                # Deterministic unique email.
                email = f"user{customer_id}@example.com"

                state = random.choice(list(STATES_AND_CITIES.keys()))
                city = random.choice(STATES_AND_CITIES[state])

                copy.write_row(
                    (
                        name,
                        email,
                        city,
                        state,
                    )
                )

    conn.commit()

    elapsed = time.perf_counter() - start_time

    print(
        f"Customers inserted: {count:,} "
        f"in {elapsed:.2f} seconds"
    )


# ============================================================
# GENERATE PRODUCTS
# ============================================================

def generate_products(conn, count):
    print(f"\nGenerating {count:,} products...")

    start_time = time.perf_counter()

    # Keep prices in memory so order_items can use
    # the exact product price later.
    product_prices = {}

    product_names = [
        "Laptop",
        "Smartphone",
        "Wireless Mouse",
        "Mechanical Keyboard",
        "Monitor",
        "Headphones",
        "Smart Watch",
        "Tablet",
        "Gaming Console",
        "Bluetooth Speaker",
        "Power Bank",
        "USB Cable",
        "Webcam",
        "Router",
        "External SSD",
    ]

    with conn.cursor() as cursor:
        with cursor.copy(
            """
            COPY products
            (name, category, price, stock)
            FROM STDIN
            """
        ) as copy:

            for product_id in range(1, count + 1):
                base_name = random.choice(product_names)
                category = random.choice(CATEGORIES)

                price = round(
                    random.uniform(299, 150000),
                    2,
                )

                stock = random.randint(0, 500)

                product_prices[product_id] = price

                name = f"{base_name} {product_id}"

                copy.write_row(
                    (
                        name,
                        category,
                        price,
                        stock,
                    )
                )

    conn.commit()

    elapsed = time.perf_counter() - start_time

    print(
        f"Products inserted: {count:,} "
        f"in {elapsed:.2f} seconds"
    )

    return product_prices


# ============================================================
# GENERATE ORDERS + ORDER ITEMS
# ============================================================

def generate_orders(
    conn,
    order_count,
    customer_count,
    product_prices,
    items_per_order,
):
    print(f"\nGenerating {order_count:,} orders...")
    print(
        f"Average items per order: "
        f"{items_per_order}"
    )

    start_time = time.perf_counter()

    product_ids = list(product_prices.keys())

    # We generate dates over approximately the last 2 years.
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)

    total_items = 0

    order_batch = []
    item_batch = []

    def flush_batches(cursor):
        nonlocal order_batch
        nonlocal item_batch

        if order_batch:
            with cursor.copy(
                """
                COPY orders
                (
                    order_id,
                    customer_id,
                    order_date,
                    total_amount
                )
                FROM STDIN
                """
            ) as copy:
                for row in order_batch:
                    copy.write_row(row)

            order_batch.clear()

        if item_batch:
            with cursor.copy(
                """
                COPY order_items
                (
                    order_id,
                    product_id,
                    quantity,
                    unit_price
                )
                FROM STDIN
                """
            ) as copy:
                for row in item_batch:
                    copy.write_row(row)

            item_batch.clear()

    with conn.cursor() as cursor:

        for order_id in range(1, order_count + 1):

            customer_id = random.randint(
                1,
                customer_count,
            )

            random_seconds = random.randint(
                0,
                int(
                    (
                        end_date - start_date
                    ).total_seconds()
                ),
            )

            order_date = (
                start_date
                + timedelta(seconds=random_seconds)
            )

            # Random number of products in this order.
            item_count = random.randint(
                1,
                items_per_order,
            )

            selected_products = random.sample(
                product_ids,
                item_count,
            )

            total_amount = 0.0

            for product_id in selected_products:

                quantity = random.randint(1, 5)

                unit_price = product_prices[
                    product_id
                ]

                total_amount += (
                    quantity * unit_price
                )

                item_batch.append(
                    (
                        order_id,
                        product_id,
                        quantity,
                        unit_price,
                    )
                )

                total_items += 1

            total_amount = round(
                total_amount,
                2,
            )

            order_batch.append(
                (
                    order_id,
                    customer_id,
                    order_date,
                    total_amount,
                )
            )

            if len(order_batch) >= BATCH_SIZE:
                flush_batches(cursor)
                conn.commit()

                if order_id % 50000 == 0:
                    print(
                        f"  Progress: "
                        f"{order_id:,}/{order_count:,} "
                        f"orders"
                    )

        # Flush remaining records.
        flush_batches(cursor)
        conn.commit()

    elapsed = time.perf_counter() - start_time

    print(
        f"Orders inserted: {order_count:,}"
    )

    print(
        f"Order items inserted: {total_items:,}"
    )

    print(
        f"Orders + items generated "
        f"in {elapsed:.2f} seconds"
    )

    return total_items


# ============================================================
# VERIFY DATA
# ============================================================

def verify_database(conn):
    print("\nVerifying database...")

    tables = [
        "customers",
        "products",
        "orders",
        "order_items",
    ]

    with conn.cursor() as cursor:

        for table in tables:
            cursor.execute(
                f"SELECT COUNT(*) FROM {table};"
            )

            count = cursor.fetchone()[0]

            print(
                f"{table:<15} {count:>12,} rows"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Generate synthetic data for "
            "Database Performance Advisor."
        )
    )

    parser.add_argument(
        "--customers",
        type=int,
        default=10_000,
        help="Number of customers.",
    )

    parser.add_argument(
        "--products",
        type=int,
        default=10_000,
        help="Number of products.",
    )

    parser.add_argument(
        "--orders",
        type=int,
        default=10_000,
        help="Number of orders.",
    )

    parser.add_argument(
        "--items-per-order",
        type=int,
        default=3,
        help=(
            "Maximum number of items "
            "per order."
        ),
    )

    args = parser.parse_args()

    if args.customers <= 0:
        raise ValueError(
            "customers must be greater than 0"
        )

    if args.products <= 0:
        raise ValueError(
            "products must be greater than 0"
        )

    if args.orders <= 0:
        raise ValueError(
            "orders must be greater than 0"
        )

    if args.items_per_order <= 0:
        raise ValueError(
            "items-per-order must be greater than 0"
        )

    print("=" * 60)
    print("DATABASE PERFORMANCE ADVISOR")
    print("Synthetic Data Generator")
    print("=" * 60)

    print("\nConfiguration:")
    print(f"  Customers : {args.customers:,}")
    print(f"  Products  : {args.products:,}")
    print(f"  Orders    : {args.orders:,}")
    print(
        f"  Max items : "
        f"{args.items_per_order}"
    )

    start_time = time.perf_counter()

    try:
        with get_connection() as conn:

            reset_tables(conn)

            generate_customers(
                conn,
                args.customers,
            )

            product_prices = generate_products(
                conn,
                args.products,
            )

            generate_orders(
                conn,
                args.orders,
                args.customers,
                product_prices,
                args.items_per_order,
            )

            verify_database(conn)

    except Exception as error:
        print("\nERROR:")
        print(error)
        raise

    total_time = (
        time.perf_counter() - start_time
    )

    print("\n" + "=" * 60)
    print(
        "DATA GENERATION COMPLETED SUCCESSFULLY"
    )
    print(
        f"Total time: {total_time:.2f} seconds"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()