from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spark_cli.cli import main
from spark_cli.system_map import write_compiled_outputs


class CliOutputPathAuthorityTests(unittest.TestCase):
    def test_os_compile_validates_each_output_against_runtime_write_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            safe_root = root / "allowed"
            outside = root / "outside"
            safe_root.mkdir()

            def guarded_write(out_dir: Path, compiled: dict[str, object], *, validate_path) -> dict[str, str]:
                validate_path(out_dir / "system-map.json")
                return {}

            with patch.dict(os.environ, {"SPARK_WRITE_SAFE_ROOT": str(safe_root)}, clear=False), \
                 patch("spark_cli.cli.compile_system_map", return_value={}), \
                 patch("spark_cli.cli.write_compiled_outputs", side_effect=guarded_write):
                with self.assertRaisesRegex(SystemExit, "outside Spark write boundary"):
                    main(["os", "compile", "--out", str(outside)])

    def test_system_map_validates_all_destinations_before_the_first_write(self) -> None:
        compiled = {
            "system_map": {"gaps": []},
            "authority_view": {},
            "capability_catalog": {},
            "trace_index": {},
            "memory_movement_index": {},
            "repo_board": {},
            "voice_surface_view": {},
            "operating_cockpit": {},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "system-map"
            checked: list[str] = []

            def reject_trace(path: Path) -> None:
                checked.append(path.name)
                if path.name == "trace-index.json":
                    raise SystemExit("blocked trace destination")

            with self.assertRaisesRegex(SystemExit, "blocked trace destination"):
                write_compiled_outputs(out_dir, compiled, validate_path=reject_trace)

            self.assertEqual(
                checked,
                ["system-map.json", "authority-view.json", "capability-catalog.json", "trace-index.json"],
            )
            self.assertFalse(out_dir.exists())

    def test_doctor_prompt_output_rejects_runtime_write_boundary_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            safe_root = root / "allowed"
            outside = root / "outside" / "doctor.md"
            safe_root.mkdir()
            with patch.dict(os.environ, {"SPARK_WRITE_SAFE_ROOT": str(safe_root)}, clear=False), \
                 patch("spark_cli.cli.collect_llm_doctor_context", return_value={}):
                with self.assertRaisesRegex(SystemExit, "outside Spark write boundary"):
                    main(["doctor", "llm", "Telegram is quiet", "--prompt-out", str(outside)])
            self.assertFalse(outside.exists())

    def test_doctor_upstream_output_rejects_runtime_write_boundary_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            safe_root = root / "allowed"
            outside = root / "outside" / "upstream.md"
            safe_root.mkdir()
            with patch.dict(os.environ, {"SPARK_WRITE_SAFE_ROOT": str(safe_root)}, clear=False), \
                 patch("spark_cli.cli.collect_llm_doctor_context", return_value={}), \
                 patch("spark_cli.cli.resolve_llm_doctor_target", return_value={"provider": "test", "role": "builder"}), \
                 patch("spark_cli.cli.call_llm_doctor", return_value="Use spark status."), \
                 patch("builtins.print"):
                with self.assertRaisesRegex(SystemExit, "outside Spark write boundary"):
                    main(
                        [
                            "doctor",
                            "llm",
                            "Telegram is quiet",
                            "--upstream-report",
                            "--upstream-out",
                            str(outside),
                        ]
                    )
            self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main()
