from __future__ import annotations

import json
from pathlib import Path

import pytest

from spark_cli.env_files import normalize_env_file_value
from spark_cli.sandbox.ssh import load_ssh_targets, validate_remote_workspace, validate_ssh_host


def test_persisted_ssh_port_zero_is_invalid_not_default(tmp_path: Path) -> None:
    root = tmp_path
    config = root / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "ssh_targets.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "targets": {
                    "remote": {
                        "host": "example.test",
                        "user": "spark",
                        "port": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="between 1 and 65535"):
        load_ssh_targets(home=root)


@pytest.mark.parametrize(
    "host",
    [":", "example.test:", "g:bad", "example..test", "good.-bad", "bad-.example"],
)
def test_malformed_ssh_hosts_are_rejected(host: str) -> None:
    with pytest.raises(ValueError, match="valid hostname or IP address"):
        validate_ssh_host(host)


def test_quoted_env_values_unescape_only_the_matching_delimiter() -> None:
    assert normalize_env_file_value(r'"say \"hello\""') == 'say "hello"'
    assert normalize_env_file_value(r"'it\'s fine'") == "it's fine"
    assert normalize_env_file_value(r'"hello \'world\'"') == r"hello \'world\'"


def test_remote_workspace_keeps_valid_percent_and_equals_characters() -> None:
    assert validate_remote_workspace("~/release%20cache") == "~/release%20cache"
    assert validate_remote_workspace("/srv/build=blue") == "/srv/build=blue"
