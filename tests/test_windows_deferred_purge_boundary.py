from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spark_cli.cli import schedule_deferred_windows_purge


class WindowsDeferredPurgeBoundaryTests(unittest.TestCase):
    def test_target_is_passed_out_of_band_instead_of_interpolated_into_cmd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "spark-%TEMP%-&-home"
            temp_root = Path(tmp_dir) / "temp"
            target.mkdir()

            with patch.dict(os.environ, {"TEMP": str(temp_root)}), \
                 patch("spark_cli.cli.subprocess.Popen") as popen:
                schedule_deferred_windows_purge(target)

            scripts = list(temp_root.glob("spark-purge-home-*.cmd"))
            self.assertEqual(len(scripts), 1)
            script = scripts[0].read_text(encoding="utf-8")
            self.assertNotIn(str(target), script)
            self.assertNotIn('set "SPARK_PURGE_TARGET=', script)
            self.assertIn("if not defined SPARK_PURGE_TARGET exit /b 1", script)

            popen.assert_called_once()
            command = popen.call_args.args[0]
            options = popen.call_args.kwargs
            self.assertEqual(command[:3], ["cmd.exe", "/d", "/c"])
            self.assertEqual(options["env"]["SPARK_PURGE_TARGET"], str(target))


if __name__ == "__main__":
    unittest.main()
