from __future__ import annotations

import unittest
from io import StringIO
from unittest.mock import patch

from spark_cli.cli import main


class LiveStatusUnhealthyCountTests(unittest.TestCase):
    def test_reports_unhealthy_module_count_through_main(self) -> None:
        payload = {
            "ok": False,
            "modules": [
                {"name": "spawner-ui", "healthy": False, "detail": "not ready"},
                {"name": "spark-telegram-bot", "healthy": False, "detail": "not ready"},
                {"name": "spark-character", "healthy": True, "detail": "ready"},
                {"name": "spark-researcher", "healthy": None, "detail": "not checked"},
                "malformed-module-record",
            ],
            "repair_hints": [],
        }

        with patch("spark_cli.cli.ensure_state_dirs"), \
             patch("spark_cli.cli.collect_status_payload", return_value=payload), \
             patch("sys.stdout", new_callable=StringIO) as stdout:
            self.assertEqual(main(["live", "status"]), 1)

        self.assertIn("[FIX] Spark Live needs attention (2 module(s) unhealthy).", stdout.getvalue())

    def test_does_not_count_unknown_or_malformed_health(self) -> None:
        payload = {
            "ok": False,
            "modules": [
                {"name": "spark-researcher", "healthy": None, "detail": "not checked"},
                {"name": "spark-character", "healthy": "false", "detail": "invalid health shape"},
                "malformed-module-record",
            ],
            "repair_hints": [],
        }

        with patch("spark_cli.cli.ensure_state_dirs"), \
             patch("spark_cli.cli.collect_status_payload", return_value=payload), \
             patch("sys.stdout", new_callable=StringIO) as stdout:
            self.assertEqual(main(["live", "status"]), 1)

        self.assertIn("[FIX] Spark Live needs attention.", stdout.getvalue())
        self.assertNotIn("module(s) unhealthy", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
