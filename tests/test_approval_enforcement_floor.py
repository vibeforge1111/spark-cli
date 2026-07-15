from __future__ import annotations

import os
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import spark_cli.cli
from spark_cli.cli import main


class ApprovalEnforcementFloorTests(unittest.TestCase):
    def test_cli_approval_has_no_environment_bypass(self) -> None:
        source = Path(spark_cli.cli.__file__).read_text(encoding="utf-8")
        self.assertNotIn("SPARK_APPROVAL_ENFORCE", source)

    def test_runtime_environment_mutation_cannot_bypass_secret_reveal_gate(self) -> None:
        with patch.dict(os.environ, {"SPARK_APPROVAL_ENFORCE": "0"}), \
             patch("spark_cli.cli.ensure_state_dirs"), \
             patch("spark_cli.cli.stdin_is_tty", return_value=False), \
             patch("spark_cli.cli.cmd_secrets_get", return_value=0) as get_secret_command, \
             patch("sys.stdout", new_callable=StringIO) as stdout:
            self.assertEqual(main(["secrets", "get", "telegram.bot_token", "--reveal"]), 2)

        get_secret_command.assert_not_called()
        self.assertIn("Spark blocked a sensitive action", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
