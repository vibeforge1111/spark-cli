from __future__ import annotations

import ast
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from spark_cli.cli import clone_module_source, pull_module_source, run_git_or_exit


def test_direct_git_subprocess_calls_are_bounded() -> None:
    source_path = Path(__file__).parents[1] / "src" / "spark_cli" / "cli.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    unbounded: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "run":
            continue
        call_source = ast.get_source_segment(source, node) or ""
        if "git_command" not in call_source:
            continue
        if not any(keyword.arg == "timeout" for keyword in node.keywords):
            unbounded.append(node.lineno)
    assert unbounded == [], f"direct git subprocess calls lack a timeout at lines {unbounded}"


def test_run_git_or_exit_shapes_timeout_without_command_reflection() -> None:
    timeout = subprocess.TimeoutExpired(["git", "fetch", "secret-ref"], 60)
    with (
        patch("spark_cli.cli.subprocess.run", side_effect=timeout),
        pytest.raises(SystemExit) as raised,
    ):
        run_git_or_exit("domain-chip-memory", ["fetch", "secret-ref"])

    message = str(raised.value)
    assert "timed out after 60s" in message
    assert "secret-ref" not in message


def test_clone_timeout_is_shaped_and_partial_target_is_removed(tmp_path: Path) -> None:
    target = tmp_path / "module" / "source"
    timeout = subprocess.TimeoutExpired(["git", "clone"], 300)
    with (
        patch("spark_cli.cli.clone_target_for_module", return_value=target),
        patch("spark_cli.cli.subprocess.run", side_effect=timeout),
        pytest.raises(SystemExit, match="git clone failed.*timed out after 300s"),
    ):
        clone_module_source("module", "https://example.invalid/module.git")
    assert not target.exists()


def test_pull_timeout_returns_fixed_failure_without_path_reflection() -> None:
    timeout = subprocess.TimeoutExpired(["git", "pull"], 60)
    with patch("spark_cli.cli.subprocess.run", side_effect=timeout):
        ok, detail = pull_module_source(Path("/private/operator/module"))
    assert ok is False
    assert detail == "git operation timed out after 60s"
    assert "operator" not in detail
