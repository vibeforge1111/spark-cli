from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from spark_cli.cli import build_parser


class CliWorkStateStatusTests(unittest.TestCase):
    def test_autostart_status_json_uses_typed_health_contract(self) -> None:
        payload = {
            "ok": False,
            "summary": "Spark autostart repair",
            "checks": [{"name": "login hook", "ok": False, "detail": "missing", "repair": "spark autostart on"}],
            "hooks": [],
            "next_commands": ["spark autostart on"],
        }
        with patch("spark_cli.cli.collect_autostart_fix_payload", return_value=payload):
            args = build_parser().parse_args(["autostart", "status", "--json"])
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = args.func(args)

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(stdout.getvalue()), payload)

    def test_telegram_status_json_uses_fresh_diagnostic_contract(self) -> None:
        payload = {
            "ok": True,
            "summary": "Spark Telegram repair",
            "checks": [{"name": "telegram process", "ok": True, "detail": "running", "repair": ""}],
            "status_repair_hints": [],
            "next_commands": ["spark status"],
        }
        with patch("spark_cli.cli.collect_telegram_fix_payload", return_value=payload):
            args = build_parser().parse_args(["telegram", "status", "--json"])
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = args.func(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), payload)

    def test_telegram_status_human_surface_is_conversational_and_nonreflecting(self) -> None:
        payload = {
            "ok": False,
            "summary": "Spark Telegram repair",
            "checks": [{"name": "telegram process", "ok": False, "detail": "not running", "repair": "spark restart telegram-starter"}],
            "status_repair_hints": [],
            "next_commands": ["spark status"],
        }
        with patch("spark_cli.cli.collect_telegram_fix_payload", return_value=payload):
            args = build_parser().parse_args(["telegram", "status"])
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = args.func(args)

        rendered = stdout.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("needs attention", rendered)
        self.assertNotIn("Spark Telegram repair", rendered)
        self.assertNotIn("Mission\n", rendered)
        self.assertNotIn("Provider\n", rendered)
        self.assertNotIn("Move\n", rendered)


if __name__ == "__main__":
    unittest.main()
