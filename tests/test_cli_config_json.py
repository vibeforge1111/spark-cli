from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from spark_cli.cli import main


class CliConfigJsonTests(unittest.TestCase):
    def run_config_get(self, key: str, config: dict) -> tuple[int, dict]:
        stdout = StringIO()
        with patch("spark_cli.cli.load_user_config", return_value=config), redirect_stdout(stdout):
            exit_code = main(["config", "get", key, "--json"])
        return exit_code, json.loads(stdout.getvalue())

    def test_config_get_json_reports_missing_key_without_conflating_null(self) -> None:
        exit_code, payload = self.run_config_get("feature.missing", {"feature": {"flag": None}})

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            payload,
            {"ok": False, "key": "feature.missing", "value": None, "set": False},
        )

    def test_config_get_json_preserves_stored_null_as_set(self) -> None:
        exit_code, payload = self.run_config_get("feature.flag", {"feature": {"flag": None}})

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload,
            {"ok": True, "key": "feature.flag", "value": None, "set": True},
        )

    def test_config_get_json_preserves_nested_json_value(self) -> None:
        value = {"models": ["fast", "deep"], "enabled": True}
        exit_code, payload = self.run_config_get("runtime", {"runtime": value})

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload, {"ok": True, "key": "runtime", "value": value, "set": True})


if __name__ == "__main__":
    unittest.main()
