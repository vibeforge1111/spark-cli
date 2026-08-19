from pathlib import Path
from unittest.mock import patch

import pytest

import spark_cli.cli as cli


def test_pr71_sensitive_path_finding_is_superseded_by_spark_home_allowlist(tmp_path: Path) -> None:
    spark_home = tmp_path / "spark-home"
    spark_home.mkdir()
    sensitive = tmp_path / ".ssh" / "id_rsa"
    sensitive.parent.mkdir()
    sensitive.write_text("sensitive\n", encoding="utf-8")
    ordinary_outside = tmp_path / "ordinary-secret.txt"
    ordinary_outside.write_text("ordinary\n", encoding="utf-8")

    with patch("spark_cli.cli.SPARK_HOME", spark_home):
        for candidate in (sensitive, ordinary_outside):
            with pytest.raises(SystemExit, match="must stay inside SPARK_HOME"):
                cli.resolve_secret_input(f"@file:{candidate}")


def test_secret_file_reference_cannot_swap_to_outside_target_after_boundary_check(tmp_path: Path) -> None:
    spark_home = tmp_path / "spark-home"
    spark_home.mkdir()
    candidate = spark_home / "secret.txt"
    candidate.write_text("inside-secret\n", encoding="utf-8")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("outside-secret\n", encoding="utf-8")
    original_check = cli.secret_file_path_inside_spark_home

    def approve_then_swap(path: Path, home: Path) -> bool:
        allowed = original_check(path, home)
        candidate.unlink()
        try:
            candidate.symlink_to(outside)
        except (NotImplementedError, OSError) as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")
        return allowed

    with patch("spark_cli.cli.SPARK_HOME", spark_home), patch(
        "spark_cli.cli.secret_file_path_inside_spark_home",
        side_effect=approve_then_swap,
    ):
        with pytest.raises(SystemExit, match="could not be read safely"):
            cli.resolve_secret_input(f"@file:{candidate}")


def test_secret_file_read_errors_do_not_reflect_attacker_controlled_path(tmp_path: Path) -> None:
    spark_home = tmp_path / "spark-home"
    spark_home.mkdir()
    attacker_path = spark_home / "missing-secret-\x1b[31m.txt"

    with patch("spark_cli.cli.SPARK_HOME", spark_home):
        with pytest.raises(SystemExit) as raised:
            cli.resolve_secret_input(f"@file:{attacker_path}")

    message = str(raised.value)
    assert str(attacker_path) not in message
    assert "\x1b[31m" not in message
    assert "could not be read safely" in message


def test_secret_file_reference_rejects_existing_nested_symlink_escape(tmp_path: Path) -> None:
    spark_home = tmp_path / "spark-home"
    spark_home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_secret = outside / "secret.txt"
    outside_secret.write_text("outside-secret\n", encoding="utf-8")
    linked = spark_home / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with patch("spark_cli.cli.SPARK_HOME", spark_home):
        with pytest.raises(SystemExit, match="must stay inside SPARK_HOME"):
            cli.resolve_secret_input(f"@file:{linked / 'secret.txt'}")


def test_secret_file_reference_cannot_swap_parent_after_resolution(tmp_path: Path) -> None:
    spark_home = tmp_path / "spark-home"
    nested = spark_home / "nested"
    nested.mkdir(parents=True)
    candidate = nested / "secret.txt"
    candidate.write_text("inside-secret\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside-secret\n", encoding="utf-8")
    original_resolver = cli._resolved_secret_file_parts

    def resolve_then_swap(path: Path, home: Path) -> tuple[Path, tuple[str, ...], tuple[int, int]]:
        result = original_resolver(path, home)
        candidate.unlink()
        nested.rmdir()
        try:
            nested.symlink_to(outside, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")
        return result

    with patch("spark_cli.cli.SPARK_HOME", spark_home), patch(
        "spark_cli.cli._resolved_secret_file_parts",
        side_effect=resolve_then_swap,
    ):
        with pytest.raises(SystemExit, match="could not be read safely"):
            cli.resolve_secret_input(f"@file:{candidate}")


def test_secret_file_reference_requires_regular_bounded_file(tmp_path: Path) -> None:
    spark_home = tmp_path / "spark-home"
    spark_home.mkdir()
    oversized = spark_home / "oversized.txt"
    oversized.write_bytes(b"x" * (cli.MAX_SECRET_FILE_BYTES + 1))

    with patch("spark_cli.cli.SPARK_HOME", spark_home):
        with pytest.raises(SystemExit, match="could not be read safely"):
            cli.resolve_secret_input(f"@file:{oversized}")
        with pytest.raises(SystemExit, match="could not be read safely"):
            cli.resolve_secret_input(f"@file:{spark_home}")


def test_windows_opened_handle_path_must_remain_inside_spark_home(tmp_path: Path) -> None:
    spark_home = tmp_path / "spark-home"
    spark_home.mkdir()
    candidate = spark_home / "secret.txt"
    candidate.write_text("inside-secret\n", encoding="utf-8")
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("outside-secret\n", encoding="utf-8")

    with patch("spark_cli.cli._path_is_reparse_point", return_value=False), patch(
        "spark_cli.cli._windows_final_path_for_fd",
        return_value=outside,
    ):
        with pytest.raises(SystemExit, match="could not be read safely"):
            cli._read_secret_file_windows(spark_home, ("secret.txt",))
