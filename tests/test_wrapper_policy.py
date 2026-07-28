from __future__ import annotations

import pytest

from spark_cli.security.wrapper_policy import transparent_wrapper_command


@pytest.mark.parametrize(
    ("command", "inner", "env_names"),
    [
        (["env", "--unset", "TOKEN", "FOO=bar", "curl", "https://example.test"], ["curl", "https://example.test"], {"FOO"}),
        (["nohup", "curl", "https://example.test"], ["curl", "https://example.test"], set()),
        (["timeout", "--signal", "TERM", "1m", "curl", "https://example.test"], ["curl", "https://example.test"], set()),
        (["nice", "-n", "10", "curl", "https://example.test"], ["curl", "https://example.test"], set()),
        (["setsid", "--wait", "curl", "https://example.test"], ["curl", "https://example.test"], set()),
        (["stdbuf", "-oL", "curl", "https://example.test"], ["curl", "https://example.test"], set()),
    ],
)
def test_transparent_wrapper_command_extracts_inner_argv(
    command: list[str], inner: list[str], env_names: set[str]
) -> None:
    parsed, assignments, read_only = transparent_wrapper_command(command)
    assert parsed == inner
    assert assignments == env_names
    assert read_only is False


@pytest.mark.parametrize(
    "command",
    [
        ["env", "--unknown", "curl"],
        ["timeout", "--signal", "TERM", "1m"],
        ["nice", "--unknown", "curl"],
        ["setsid", "--unknown", "curl"],
        ["stdbuf", "--unknown", "curl"],
    ],
)
def test_transparent_wrapper_command_fails_closed_for_unknown_or_incomplete_grammar(command: list[str]) -> None:
    parsed, _assignments, read_only = transparent_wrapper_command(command)
    assert parsed is None
    assert read_only is False


def test_transparent_wrapper_command_allows_nohup_help() -> None:
    parsed, assignments, read_only = transparent_wrapper_command(["nohup", "--help"])
    assert parsed == []
    assert assignments == set()
    assert read_only is True
