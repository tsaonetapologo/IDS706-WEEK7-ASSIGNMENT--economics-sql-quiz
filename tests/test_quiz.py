import unittest
from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pglast import parse_sql
from pglast.ast import SelectStmt

from quiz import (
    COUNTRY_FLAGS,
    QUESTIONS,
    add_country_flags,
    results_match_expected,
    run_read_only_query,
    validate_read_only_query,
)


class QuizContentTests(unittest.TestCase):
    def test_questions_are_code_prompts_worth_twenty_points(self) -> None:
        self.assertEqual(len(QUESTIONS), 5)
        self.assertEqual(sum(question["points"] for question in QUESTIONS), 20)
        self.assertTrue(all("prompt" in question for question in QUESTIONS))
        self.assertTrue(all("expected_rows" in question for question in QUESTIONS))

    def test_flags_cover_all_dataset_countries_and_appear_in_result_rows(self) -> None:
        self.assertEqual(
            set(COUNTRY_FLAGS),
            {
                "Botswana",
                "Ghana",
                "Kenya",
                "Mauritius",
                "Namibia",
                "Nigeria",
                "Rwanda",
                "South Africa",
                "Uganda",
                "Zambia",
            },
        )
        rows = add_country_flags([{"country": "Botswana", "year": 2024}])
        self.assertEqual(rows, [{"Flag": "🇧🇼", "country": "Botswana", "year": 2024}])
        self.assertEqual(add_country_flags([{"year": 2024}]), [{"year": 2024}])

    def test_expected_sql_is_select_and_matches_one_statement(self) -> None:
        for question in QUESTIONS:
            with self.subTest(question=question["number"]):
                statements = parse_sql(question["sql"])
                self.assertEqual(len(statements), 1)
                self.assertIsInstance(statements[0].stmt, SelectStmt)
                validate_read_only_query(question["sql"])

    def test_results_match_expected_ignoring_column_and_row_order(self) -> None:
        expected = [
            {"country": "Mauritius", "gdp_per_capita": 12500},
            {"country": "Botswana", "gdp_per_capita": 7200},
        ]
        self.assertTrue(
            results_match_expected(
                ["gdp_per_capita", "country"],
                [(7200, "Botswana"), (12500, "Mauritius")],
                expected,
            )
        )
        self.assertFalse(
            results_match_expected(
                ["country", "gdp_per_capita"],
                [("Botswana", 7100), ("Mauritius", 12500)],
                expected,
            )
        )
        self.assertFalse(
            results_match_expected(
                ["country"],
                [("Botswana",), ("Mauritius",)],
                expected,
            )
        )

    def test_results_match_expected_handles_postgres_decimal_values(self) -> None:
        self.assertTrue(
            results_match_expected(
                ["average_inflation"],
                [(Decimal("9.07"),)],
                [{"average_inflation": 9.07}],
            )
        )

    def test_supabase_setup_sql_parses(self) -> None:
        schema = Path(__file__).resolve().parents[1] / "schema.sql"
        schema_sql = schema.read_text()
        statements = parse_sql(schema_sql)
        self.assertGreater(len(statements), 0)
        self.assertIn("ALTER COLUMN year SET DEFAULT 2024", schema_sql)
        self.assertIn("WHERE year IS NULL", schema_sql)


class QuerySafetyTests(unittest.TestCase):
    def test_rejects_empty_query(self) -> None:
        with self.assertRaisesRegex(ValueError, "Enter a SQL query"):
            validate_read_only_query("  ")

    def test_rejects_non_select_statements(self) -> None:
        for query in (
            "DELETE FROM public.economic_indicators",
            "UPDATE public.economic_indicators SET population = 0",
            "INSERT INTO public.economic_indicators VALUES ('X', 1, 1, 1, 1)",
            "DROP TABLE public.economic_indicators",
        ):
            with self.subTest(query=query):
                with self.assertRaisesRegex(ValueError, "one SELECT query only"):
                    validate_read_only_query(query)

    def test_rejects_multiple_statements(self) -> None:
        with self.assertRaisesRegex(ValueError, "one SELECT query only"):
            validate_read_only_query(
                "SELECT country FROM public.economic_indicators; COMMIT"
            )

    def test_rejects_invalid_sql_and_oversized_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "Could not parse SQL"):
            validate_read_only_query("SELECT FROM")
        with self.assertRaisesRegex(ValueError, "10,000 characters"):
            validate_read_only_query("x" * 10_001)

    def test_runner_uses_restricted_read_only_connection_and_caps_results(self) -> None:
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.transaction.return_value = nullcontext()
        cursor = MagicMock()
        cursor.description = [SimpleNamespace(name="country")]
        cursor.fetchmany.return_value = [(str(row),) for row in range(501)]
        connection.execute.side_effect = [None, None, None, cursor]

        with patch("quiz.psycopg.connect", return_value=connection) as connect:
            columns, rows, truncated = run_read_only_query(
                "postgresql://example.test/postgres",
                "SELECT country FROM public.economic_indicators",
            )

        connect.assert_called_once_with(
            "postgresql://example.test/postgres",
            sslmode="require",
            connect_timeout=10,
        )
        self.assertEqual(
            [call.args[0] for call in connection.execute.call_args_list[:3]],
            [
                "SET TRANSACTION READ ONLY",
                "SET LOCAL ROLE quiz_reader",
                "SET LOCAL statement_timeout = 5000",
            ],
        )
        self.assertEqual(columns, ["country"])
        self.assertEqual(len(rows), 500)
        self.assertTrue(truncated)


if __name__ == "__main__":
    unittest.main()
