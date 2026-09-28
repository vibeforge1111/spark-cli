"""Enforces the R-21 god-file ratchet in CI (Spark Harness Discipline).

Runs the vendored line-count gate so a file growing past its baseline fails
`pytest` (which test-and-audit invokes). Automatic; no human review. See
docs/harness-discipline/07_FLEET_DISCIPLINE.md.
"""
import subprocess
import sys
from pathlib import Path


def test_god_file_ratchet_r21() -> None:
    root = Path(__file__).resolve().parent.parent
    gate = root / "scripts" / "harness_checks" / "line_count_gate.py"
    if not gate.exists():
        return
    result = subprocess.run(
        [sys.executable, str(gate), "--root", str(root)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "R-21 god-file gate failed (a file grew past its baseline):\n"
        f"{result.stdout}\n{result.stderr}"
    )
