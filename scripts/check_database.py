import os

import psycopg


def main() -> None:
    database_url = os.environ.get("SUPABASE_DATABASE_URL")
    if not database_url:
        raise SystemExit("SUPABASE_DATABASE_URL must be configured as a GitHub Secret.")

    with psycopg.connect(
        database_url,
        sslmode="require",
        connect_timeout=10,
    ) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL ROLE quiz_reader")
            row = connection.execute(
                "SELECT COUNT(*) FROM public.economic_indicators"
            ).fetchone()

    row_count = row[0] if row else 0
    if row_count < 1:
        raise SystemExit("The hosted economic_indicators table is empty.")
    print(f"Database connection and quiz_reader access verified ({row_count} rows).")


if __name__ == "__main__":
    main()
