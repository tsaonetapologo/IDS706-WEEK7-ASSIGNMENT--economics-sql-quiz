from decimal import Decimal
from numbers import Number
from typing import Any

import psycopg
from pglast import parse_sql
from pglast.ast import SelectStmt


MAX_QUERY_LENGTH = 10_000
MAX_RESULT_ROWS = 500
QUERY_TIMEOUT_MS = 5_000

COUNTRY_FLAGS = {
    "Botswana": "🇧🇼",
    "Ghana": "🇬🇭",
    "Kenya": "🇰🇪",
    "Mauritius": "🇲🇺",
    "Namibia": "🇳🇦",
    "Nigeria": "🇳🇬",
    "Rwanda": "🇷🇼",
    "South Africa": "🇿🇦",
    "Uganda": "🇺🇬",
    "Zambia": "🇿🇲",
}


def add_country_flags(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"Flag": COUNTRY_FLAGS.get(str(row.get("country", "")), ""), **row}
        if "country" in row
        else row
        for row in rows
    ]


def results_match_expected(
    columns: list[str],
    rows: list[tuple[Any, ...]],
    expected_rows: list[dict[str, Any]],
) -> bool:
    if not expected_rows:
        return not rows

    expected_columns = set(expected_rows[0])
    if len(columns) != len(expected_columns) or set(columns) != expected_columns:
        return False
    if len(rows) != len(expected_rows):
        return False

    remaining_expected = list(expected_rows)
    for row in rows:
        actual = dict(zip(columns, row))
        matching_index = next(
            (
                index
                for index, expected in enumerate(remaining_expected)
                if all(
                    _values_match(actual[column], expected[column])
                    for column in expected_columns
                )
            ),
            None,
        )
        if matching_index is None:
            return False
        remaining_expected.pop(matching_index)

    return not remaining_expected


def _values_match(actual: Any, expected: Any) -> bool:
    if (
        isinstance(actual, Number)
        and not isinstance(actual, bool)
        and isinstance(expected, Number)
        and not isinstance(expected, bool)
    ):
        return Decimal(str(actual)) == Decimal(str(expected))
    return actual == expected


QUESTIONS: list[dict[str, Any]] = [
    {
        "number": 1,
        "points": 4,
        "prompt": (
            "Write a query that returns the three countries with the highest "
            "GDP per capita. Show `country` and `gdp_per_capita`, highest first."
        ),
        "sql": """SELECT country, gdp_per_capita
FROM public.economic_indicators
ORDER BY gdp_per_capita DESC
LIMIT 3;""",
        "expected_rows": [
            {"country": "Mauritius", "gdp_per_capita": 12500},
            {"country": "Botswana", "gdp_per_capita": 7200},
            {"country": "South Africa", "gdp_per_capita": 6500},
        ],
    },
    {
        "number": 2,
        "points": 4,
        "prompt": (
            "Write a query that lists each country with inflation above 5%. "
            "Show `country` and `inflation_rate`, highest inflation first."
        ),
        "sql": """SELECT country, inflation_rate
FROM public.economic_indicators
WHERE inflation_rate > 5
ORDER BY inflation_rate DESC;""",
        "expected_rows": [
            {"country": "Nigeria", "inflation_rate": 24.5},
            {"country": "Ghana", "inflation_rate": 22.8},
            {"country": "Zambia", "inflation_rate": 15.0},
        ],
    },
    {
        "number": 3,
        "points": 4,
        "prompt": (
            "Write a query that calculates the average inflation rate across "
            "all countries. Name the result column `average_inflation`."
        ),
        "sql": """SELECT AVG(inflation_rate) AS average_inflation
FROM public.economic_indicators;""",
        "expected_rows": [{"average_inflation": 9.07}],
    },
    {
        "number": 4,
        "points": 4,
        "prompt": (
            "Write a query that counts countries with unemployment above 10%. "
            "Name the result column `high_unemployment_countries`."
        ),
        "sql": """SELECT COUNT(*) AS high_unemployment_countries
FROM public.economic_indicators
WHERE unemployment_rate > 10;""",
        "expected_rows": [{"high_unemployment_countries": 6}],
    },
    {
        "number": 5,
        "points": 4,
        "prompt": (
            "Write a query that finds countries with a population above 30 "
            "million. Show `country` and `population`, largest population first."
        ),
        "sql": """SELECT country, population
FROM public.economic_indicators
WHERE population > 30000000
ORDER BY population DESC;""",
        "expected_rows": [
            {"country": "Nigeria", "population": 232000000},
            {"country": "South Africa", "population": 64000000},
            {"country": "Kenya", "population": 56400000},
            {"country": "Uganda", "population": 50000000},
            {"country": "Ghana", "population": 34100000},
        ],
    },
]


def validate_read_only_query(query: str) -> None:
    if not query.strip():
        raise ValueError("Enter a SQL query.")
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"Queries must be {MAX_QUERY_LENGTH:,} characters or fewer.")

    try:
        statements = parse_sql(query)
    except Exception as error:
        raise ValueError(f"Could not parse SQL: {error}") from error

    if len(statements) != 1 or not isinstance(statements[0].stmt, SelectStmt):
        raise ValueError("Run one SELECT query only. Changes to the database are blocked.")


def run_read_only_query(
    database_url: str, query: str
) -> tuple[list[str], list[tuple[Any, ...]], bool]:
    validate_read_only_query(query)

    with psycopg.connect(
        database_url,
        sslmode="require",
        connect_timeout=10,
    ) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL ROLE quiz_reader")
            connection.execute(f"SET LOCAL statement_timeout = {QUERY_TIMEOUT_MS}")
            cursor = connection.execute(query)
            columns = [column.name for column in cursor.description or []]
            rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)

    truncated = len(rows) > MAX_RESULT_ROWS
    return columns, rows[:MAX_RESULT_ROWS], truncated
