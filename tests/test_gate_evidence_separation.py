from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_detects_post_boundary_co_edit_and_ignores_history(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "harness_checks" / "gate_evidence_separation.py"
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return result.stdout.strip()

    git("init", "-q")
    (tmp_path / "gate-map.json").write_text(
        json.dumps({"gates": {"release_gate": {"gate_code": ["gate.py"], "evidence": ["evidence.json"]}}}),
        encoding="utf-8",
    )
    (tmp_path / "gate.py").write_text("GATE = 1\n", encoding="utf-8")
    (tmp_path / "evidence.json").write_text("{}\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "init")

    (tmp_path / "gate.py").write_text("GATE = 0\n", encoding="utf-8")
    (tmp_path / "evidence.json").write_text('{"historical": true}\n', encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "historical co-edit")
    boundary = git("rev-parse", "HEAD")
    gate_map = json.loads((tmp_path / "gate-map.json").read_text(encoding="utf-8"))
    gate_map["separation_enforced_after"] = boundary
    (tmp_path / "gate-map.json").write_text(json.dumps(gate_map), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "start enforcement")

    historical = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--range", f"{boundary}^..{boundary}"],
        capture_output=True,
        text=True,
    )
    assert historical.returncode == 0, historical.stdout + historical.stderr
    assert "historical commit" in historical.stdout

    (tmp_path / "gate.py").write_text("GATE = 3\n", encoding="utf-8")
    (tmp_path / "evidence.json").write_text('{"post_boundary": true}\n', encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "post-boundary co-edit")
    violation = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--range", "HEAD"],
        capture_output=True,
        text=True,
    )
    assert violation.returncode == 1, violation.stdout + violation.stderr
    assert "d7fc1df" in violation.stdout


def test_gate_only_edit_passes(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "harness_checks" / "gate_evidence_separation.py"
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True, env=env)
    (tmp_path / "gate-map.json").write_text(
        json.dumps({"gates": {"release_gate": {"gate_code": ["gate.py"], "evidence": ["evidence.json"]}}}),
        encoding="utf-8",
    )
    (tmp_path / "gate.py").write_text("GATE = 1\n", encoding="utf-8")
    (tmp_path / "evidence.json").write_text("{}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True, env=env)
    (tmp_path / "gate.py").write_text("GATE = 2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "gate.py"], check=True, env=env)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "gate only"], check=True, env=env)
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--range", "HEAD"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
