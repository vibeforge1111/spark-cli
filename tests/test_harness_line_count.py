"""Enforces the R-21 god-file ratchet in CI (Spark Harness Discipline).

The vendored line-count gate must pass: no source file over 3,000 lines beyond
its baseline (baselined files may only shrink). See
docs/harness-discipline/07_FLEET_DISCIPLINE.md. Runs automatically as part of
`pytest` (which CI's test-and-audit invokes) — no human review involved.
"""
import subprocess
import sys
from pathlib import Path


def test_god_file_ratchet_r21() -> None:
    root = Path(__file__).resolve().parent.parent
    gate = root / "scripts" / "harness_checks" / "line_count_gate.py"
    if not gate.exists():
        return  # gate not vendored here; nothing to enforce
    result = subprocess.run(
        [sys.executable, str(gate), "--root", str(root)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "R-21 god-file gate failed (a file grew past its baseline):\n"
        f"{result.stdout}\n{result.stderr}"
    )
