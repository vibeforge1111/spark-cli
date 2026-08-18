import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spark_cli.codex_cli import detect_codex_cli


class CodexCliDetectionTests(unittest.TestCase):
    def test_prefers_explicit_native_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_path = Path(tmpdir) / "codex.exe"
            codex_path.touch()
            with patch.dict(os.environ, {"SPARK_CODEX_PATH": str(codex_path)}, clear=False), \
                 patch("spark_cli.codex_cli.shutil.which", return_value="/inaccessible/codex"):
                detected = detect_codex_cli()

        self.assertEqual(detected, {"present": True, "path": str(codex_path)})

    def test_prefers_npm_native_binary_over_path_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            codex_path = (
                home
                / ".npm-global/node_modules/@openai/codex/node_modules/@openai"
                / "codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
            )
            codex_path.parent.mkdir(parents=True)
            codex_path.touch()
            with patch("spark_cli.codex_cli.IS_WINDOWS", True), \
                 patch("spark_cli.codex_cli.Path.home", return_value=home), \
                 patch("spark_cli.codex_cli.shutil.which", return_value="/inaccessible/codex"):
                detected = detect_codex_cli()

        self.assertEqual(detected, {"present": True, "path": str(codex_path)})


if __name__ == "__main__":
    unittest.main()
