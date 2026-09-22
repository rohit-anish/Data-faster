import os

import psycopg
from dotenv import load_dotenv


load_dotenv()


def main():
    connection_string = (
        f"host={os.getenv('DB_HOST')} "
        f"port={os.getenv('DB_PORT')} "
        f"dbname={os.getenv('DB_NAME')} "
        f"user={os.getenv('DB_USER')} "
        f"password={os.getenv('DB_PASSWORD')}"
    )

    try:
        with psycopg.connect(connection_string) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]

                print("Connected successfully!")
                print()
                print("PostgreSQL version:")
                print(version)

    except Exception as error:
        print("Connection failed.")
        print()
        print(error)


if __name__ == "__main__":
    main()