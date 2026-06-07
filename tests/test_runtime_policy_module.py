from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from spark_cli.runtime_policy import (
    npm_runtime_command_argv,
    resolve_runtime_executable,
    runtime_command_argv,
    split_single_argv_command,
)


def test_split_single_argv_command_parses_quoted_arguments() -> None:
    parts = split_single_argv_command('python script.py "with spaces"', subject="Runtime command")
    assert parts == ["python", "script.py", "with spaces"]


def test_split_single_argv_command_rejects_empty_input() -> None:
    with pytest.raises(SystemExit, match="cannot be empty"):
        split_single_argv_command("", subject="Runtime command")


def test_split_single_argv_command_rejects_shell_chain_tokens() -> None:
    for chain in ("foo && bar", "foo || bar", "foo ; bar", "foo | bar", "foo > out"):
        with pytest.raises(SystemExit, match="single argv command"):
            split_single_argv_command(chain, subject="Runtime command")


def test_resolve_runtime_executable_returns_path_when_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("spark_cli.runtime_policy.shutil.which", lambda name: f"/fake/bin/{name}")
    assert resolve_runtime_executable("node") == "/fake/bin/node"


def test_resolve_runtime_executable_exits_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("spark_cli.runtime_policy.shutil.which", lambda name: None)
    monkeypatch.setattr("spark_cli.runtime_policy.os.name", "posix")
    with pytest.raises(SystemExit, match="Missing required runtime tool"):
        resolve_runtime_executable("node")


def test_runtime_command_argv_routes_python_to_current_interpreter() -> None:
    argv = runtime_command_argv("python -c 'print(1)'")
    assert argv[0] == str(Path(sys.executable))
    assert argv[1:] == ["-c", "print(1)"]


def test_runtime_command_argv_routes_node_via_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("spark_cli.runtime_policy.shutil.which", lambda name: f"/fake/bin/{name}")
    argv = runtime_command_argv("node server.js --port 3000")
    assert argv == ["/fake/bin/node", "server.js", "--port", "3000"]


def test_runtime_command_argv_rejects_unknown_executable() -> None:
    with pytest.raises(SystemExit, match="Unsupported runtime command"):
        runtime_command_argv("rm -rf /")


def test_runtime_command_argv_uv_requires_run_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("spark_cli.runtime_policy.shutil.which", lambda name: f"/fake/bin/{name}")
    argv = runtime_command_argv("uv run script.py")
    assert argv == ["/fake/bin/uv", "run", "script.py"]
    with pytest.raises(SystemExit, match="Unsupported runtime command"):
        runtime_command_argv("uv pip install x")


def test_npm_runtime_command_argv_passes_through_on_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("spark_cli.runtime_policy.os.name", "posix")
    monkeypatch.setattr("spark_cli.runtime_policy.shutil.which", lambda name: f"/fake/bin/{name}")
    argv = npm_runtime_command_argv(["install", "lodash"])
    assert argv == ["/fake/bin/npm", "install", "lodash"]
