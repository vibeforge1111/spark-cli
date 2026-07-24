from __future__ import annotations

import subprocess
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from spark_cli.cli import main


class AutostartUninstallFailureTruthTests(unittest.TestCase):
    def test_windows_preserves_task_delete_failure_through_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            startup_path = Path(tmp_dir) / "spark-telegram-agent.vbs"
            legacy_path = Path(tmp_dir) / "spark-telegram-agent.cmd"
            startup_path.write_text("startup", encoding="utf-8")
            legacy_path.write_text("legacy", encoding="utf-8")

            def fake_helper(command: list[str]) -> subprocess.CompletedProcess[str]:
                return_code = 1 if command[0] == "schtasks" else 0
                return subprocess.CompletedProcess(command, return_code, "", "task delete failed")

            with patch("spark_cli.cli.ensure_state_dirs"), \
                 patch("spark_cli.cli.stdin_is_tty", return_value=True), \
                 patch("builtins.input", return_value="approve autostart change"), \
                 patch("spark_cli.cli.sys.platform", "win32"), \
                 patch("spark_cli.cli.windows_startup_script_path", return_value=startup_path), \
                 patch("spark_cli.cli.windows_startup_legacy_cmd_path", return_value=legacy_path), \
                 patch("spark_cli.cli.run_autostart_helper", side_effect=fake_helper), \
                 patch("sys.stdout", new_callable=StringIO) as output:
                self.assertEqual(main(["autostart", "uninstall"]), 1)

        self.assertFalse(startup_path.exists())
        self.assertFalse(legacy_path.exists())
        self.assertIn("Spark needs confirmation before continuing.", output.getvalue())
        self.assertIn("task delete failed", output.getvalue())
        self.assertIn("Removed Windows Run-key fallback", output.getvalue())


if __name__ == "__main__":
    unittest.main()
