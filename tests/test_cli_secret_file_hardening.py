from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import spark_cli.cli as cli


def test_windows_grantee_uses_os_identity_instead_of_spoofable_environment() -> None:
    completed = subprocess.CompletedProcess(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        0,
        '"DOMAIN\\real-user","S-1-5-21-1234"\n',
        "",
    )

    with (
        patch.dict(cli.os.environ, {"USERNAME": "attacker-selected"}, clear=False),
        patch("spark_cli.cli.subprocess.run", return_value=completed) as run,
    ):
        assert cli.windows_current_user_grantee() == "*S-1-5-21-1234"

    assert run.call_args.kwargs["timeout"] == cli.SECRET_FILE_HARDENING_TIMEOUT_SECONDS


def test_windows_grantee_falls_back_without_emitting_malformed_grant() -> None:
    with (
        patch.dict(cli.os.environ, {"USERNAME": "attacker-selected"}, clear=False),
        patch("spark_cli.cli.subprocess.run", side_effect=subprocess.TimeoutExpired("whoami", 1)),
        patch("spark_cli.cli.os.getlogin", return_value="trusted-login"),
    ):
        assert cli.windows_current_user_grantee() == "trusted-login"

    with (
        patch.dict(cli.os.environ, {"USERNAME": "attacker-selected"}, clear=False),
        patch("spark_cli.cli.subprocess.run", side_effect=OSError("private-path")),
        patch("spark_cli.cli.os.getlogin", side_effect=OSError("no-login")),
    ):
        assert cli.windows_current_user_grantee() == ""


def test_windows_hardening_bounds_acl_and_shapes_timeout_warning(
    tmp_path: Path, capsys: object
) -> None:
    target = tmp_path / "private-secret.json"
    target.write_text("secret-value", encoding="utf-8")
    platform = SimpleNamespace(name="nt", chmod=Mock())

    with (
        patch.object(cli, "os", platform),
        patch("spark_cli.cli.windows_current_user_grantee", return_value="*S-1-5-21-1234"),
        patch(
            "spark_cli.cli.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["icacls", str(target)], 1, stderr="secret-value"),
        ) as run,
    ):
        cli.harden_secret_file(target)

    assert run.call_args.kwargs["timeout"] == cli.SECRET_FILE_HARDENING_TIMEOUT_SECONDS
    warning = capsys.readouterr().err  # type: ignore[attr-defined]
    assert warning == cli.SECRET_FILE_HARDENING_WARNING
    assert str(target) not in warning
    assert "secret-value" not in warning
    assert "TimeoutExpired" not in warning


def test_windows_hardening_reports_acl_failure_without_reflecting_output(
    tmp_path: Path, capsys: object
) -> None:
    target = tmp_path / "private-secret.json"
    target.write_text("secret-value", encoding="utf-8")
    platform = SimpleNamespace(name="nt", chmod=Mock())

    with (
        patch.object(cli, "os", platform),
        patch("spark_cli.cli.windows_current_user_grantee", return_value="*S-1-5-21-1234"),
        patch(
            "spark_cli.cli.subprocess.run",
            return_value=SimpleNamespace(returncode=5, stderr="private-path secret-value"),
        ),
    ):
        cli.harden_secret_file(target)

    warning = capsys.readouterr().err  # type: ignore[attr-defined]
    assert warning == cli.SECRET_FILE_HARDENING_WARNING
    assert str(target) not in warning
    assert "private-path" not in warning
    assert "secret-value" not in warning


def test_posix_hardening_reports_chmod_failure_without_reflecting_path(
    tmp_path: Path, capsys: object
) -> None:
    target = tmp_path / "private-secret.json"
    target.write_text("secret-value", encoding="utf-8")
    platform = SimpleNamespace(name="posix", chmod=Mock(side_effect=OSError("private-path secret-value")))

    with patch.object(cli, "os", platform):
        cli.harden_secret_file(target)

    warning = capsys.readouterr().err  # type: ignore[attr-defined]
    assert warning == cli.SECRET_FILE_HARDENING_WARNING
    assert str(target) not in warning
    assert "private-path" not in warning
    assert "secret-value" not in warning


def test_state_directory_hardening_warns_once_without_reflecting_paths(
    tmp_path: Path, capsys: object
) -> None:
    spark_home = tmp_path / "private-spark-home"
    paths = {
        "SPARK_HOME": spark_home,
        "STATE_DIR": spark_home / "state",
        "CONFIG_DIR": spark_home / "config",
        "MODULE_CONFIG_DIR": spark_home / "config" / "modules",
        "LOG_DIR": spark_home / "logs",
    }

    with (
        patch.multiple(cli, **paths),
        patch("spark_cli.cli.os.chmod", side_effect=OSError("private-path secret-value")),
    ):
        cli.ensure_state_dirs()

    warning = capsys.readouterr().err  # type: ignore[attr-defined]
    assert warning == cli.STATE_DIRECTORY_HARDENING_WARNING
    assert str(spark_home) not in warning
    assert "private-path" not in warning
    assert "secret-value" not in warning
