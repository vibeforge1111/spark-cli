from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from spark_cli.cli import atomic_write_text, cmd_fix, redact_secret_surface_logs


SECRET_LINE = "BOT_TOKEN=1234567890:AAabcdefghijklmnopqrstuvwxyz1234567890\n"


def test_log_redaction_refuses_to_replace_files_while_spark_is_running(tmp_path: Path) -> None:
    log_path = tmp_path / "process.log"
    log_path.write_text(SECRET_LINE, encoding="utf-8")
    with (
        patch("spark_cli.cli.LOG_DIR", tmp_path),
        patch("spark_cli.cli.load_pids", return_value={"telegram": {"pid": 123}}),
        patch("spark_cli.cli.pid_is_running", return_value=True),
    ):
        result = redact_secret_surface_logs()
    assert result["blocked"] is True
    assert result["changed"] == []
    assert log_path.read_text(encoding="utf-8") == SECRET_LINE


def test_log_redaction_uses_hardened_atomic_writer(tmp_path: Path) -> None:
    log_path = tmp_path / "process.log"
    log_path.write_text(SECRET_LINE, encoding="utf-8")
    with (
        patch("spark_cli.cli.LOG_DIR", tmp_path),
        patch("spark_cli.cli.load_pids", return_value={}),
        patch("spark_cli.cli.atomic_write_text", wraps=atomic_write_text) as atomic_write,
    ):
        result = redact_secret_surface_logs()
    atomic_write.assert_called_once()
    assert result["failed_files"] == 0
    assert "[REDACTED]" in log_path.read_text(encoding="utf-8")


def test_log_redaction_skips_linked_log_without_touching_target(tmp_path: Path) -> None:
    if not hasattr(Path, "symlink_to"):
        pytest.skip("symlinks unavailable")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    target = tmp_path / "outside.log"
    target.write_text(SECRET_LINE, encoding="utf-8")
    link = log_dir / "process.log"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with (
        patch("spark_cli.cli.LOG_DIR", log_dir),
        patch("spark_cli.cli.load_pids", return_value={}),
    ):
        result = redact_secret_surface_logs()
    assert result["changed"] == []
    assert result["failed_files"] == 1
    assert target.read_text(encoding="utf-8") == SECRET_LINE


def test_fix_secrets_reports_running_process_block_as_failure() -> None:
    args = argparse.Namespace(target="secrets", redact_logs=True, json=False)
    output = StringIO()
    with (
        patch(
            "spark_cli.cli.redact_secret_surface_logs",
            return_value={"changed": [], "scanned_files": 0, "failed_files": 0, "blocked": True},
        ),
        patch("sys.stdout", output),
    ):
        assert cmd_fix(args) == 1
    rendered = output.getvalue()
    assert "[FIX]" in rendered
    assert "Stop Spark" in rendered
    assert "[OK] No log files needed redaction" not in rendered
