from __future__ import annotations

from pathlib import Path

import pytest

from spark_cli.sandbox.paths import (
    is_windows_reserved_name,
    resolve_safe_output_path,
    sandbox_config_dir,
    sandbox_log_dir,
    ssh_known_hosts_path,
    ssh_targets_path,
    validate_target_name,
)


def test_validate_target_name_accepts_basic_lowercase_names() -> None:
    assert validate_target_name("prod-server") == "prod-server"
    assert validate_target_name("box1") == "box1"


def test_validate_target_name_rejects_uppercase_and_invalid_chars() -> None:
    for value in ("BadName", "has_under", "1leading", "-leading", "x" * 41):
        with pytest.raises(ValueError):
            validate_target_name(value)


def test_validate_target_name_rejects_windows_reserved_stems() -> None:
    with pytest.raises(ValueError, match="Windows reserved"):
        validate_target_name("aux")
    with pytest.raises(ValueError, match="Windows reserved"):
        validate_target_name("com1")


def test_is_windows_reserved_name_handles_suffix_and_trailing_dot() -> None:
    assert is_windows_reserved_name("AUX")
    assert is_windows_reserved_name("nul.txt")
    assert is_windows_reserved_name("lpt1.")
    assert not is_windows_reserved_name("notes.txt")


def test_resolve_safe_output_path_keeps_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "out"
    root.mkdir()
    resolved = resolve_safe_output_path("nested/file.txt", root=root)
    assert resolved == (root / "nested" / "file.txt").resolve()


def test_resolve_safe_output_path_rejects_traversal_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "out"
    root.mkdir()
    with pytest.raises(ValueError, match="must stay inside"):
        resolve_safe_output_path("../escape.txt", root=root)


def test_resolve_safe_output_path_rejects_windows_unsafe_chars(tmp_path: Path) -> None:
    root = tmp_path / "out"
    root.mkdir()
    with pytest.raises(ValueError, match="Windows-unsafe"):
        resolve_safe_output_path("bad|name.txt", root=root)


def test_resolve_safe_output_path_rejects_windows_reserved_segments(tmp_path: Path) -> None:
    root = tmp_path / "out"
    root.mkdir()
    with pytest.raises(ValueError, match="Windows reserved"):
        resolve_safe_output_path("aux/notes.txt", root=root)


def test_sandbox_config_and_log_directories_anchor_on_home(tmp_path: Path) -> None:
    config = sandbox_config_dir(tmp_path)
    log = sandbox_log_dir(tmp_path)
    assert config == tmp_path / "config"
    assert log == tmp_path / "logs" / "remote"


def test_ssh_target_helpers_compose_paths(tmp_path: Path) -> None:
    assert ssh_targets_path(tmp_path) == tmp_path / "config" / "ssh_targets.json"
    assert ssh_known_hosts_path(tmp_path) == tmp_path / "config" / "ssh_known_hosts"
