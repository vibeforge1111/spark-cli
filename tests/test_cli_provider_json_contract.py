from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from spark_cli.cli import main


class CliProviderJsonContractTests(unittest.TestCase):
    def test_provider_catalog_and_recommendation_routes_report_success(self) -> None:
        routes = (
            ["providers", "list", "--json"],
            ["providers", "recommend", "--json"],
            ["recommend", "llms", "--json"],
        )
        with patch("spark_cli.cli.detect_codex_cli", return_value={"present": False}), \
             patch("spark_cli.cli.detect_claude_code", return_value={"present": False}), \
             patch("spark_cli.cli.stdin_is_tty", return_value=False):
            for route in routes:
                with self.subTest(route=route):
                    stdout = StringIO()
                    with redirect_stdout(stdout):
                        exit_code = main(route)

                    payload = json.loads(stdout.getvalue())
                    self.assertEqual(exit_code, 0)
                    self.assertIs(payload["ok"], True)


if __name__ == "__main__":
    unittest.main()
