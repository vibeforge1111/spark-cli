from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from spark_cli import cli


ROOT = Path(__file__).resolve().parents[1]


def test_git_source_boundary_rejects_missing_and_option_like_values_without_reflection() -> None:
    for source in ("", " \t ", "-c", "--upload-pack=private-secret"):
        with pytest.raises(SystemExit) as raised:
            cli.normalize_git_url(source)
        message = str(raised.value)
        assert source.strip() not in message or not source.strip()
        assert "private-secret" not in message


def test_clone_places_separator_before_remote_source() -> None:
    with patch.object(cli, "clone_target_for_module", return_value=Path("target")), patch.object(
        cli.subprocess,
        "run",
        return_value=type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})(),
    ) as run:
        cli.clone_module_source("module", "https://example.test/repo.git")

    argv = run.call_args.args[0]
    source_index = argv.index("https://example.test/repo.git")
    assert argv[source_index - 1] == "--"


def test_ls_remote_command_owns_separator_and_source_normalization() -> None:
    argv = cli.git_ls_remote_command("github.com/example/repo", "HEAD")
    separator = argv.index("--")
    assert argv[separator + 1 :] == ["https://github.com/example/repo", "HEAD"]


def test_no_ls_remote_call_site_bypasses_central_argument_authority() -> None:
    tree = ast.parse((ROOT / "src" / "spark_cli" / "cli.py").read_text(encoding="utf-8"))
    owners: list[str] = []
    for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "git_command" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and first.value == "ls-remote":
                owners.append(function.name)
    assert owners == ["git_ls_remote_command"]
