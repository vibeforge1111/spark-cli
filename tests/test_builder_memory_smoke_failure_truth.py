from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from spark_cli.cli import collect_builder_memory_direct_smoke


INSTALLED = {
    "spark-intelligence-builder": {"path": "/synthetic/builder"},
    "domain-chip-memory": {"path": "/synthetic/memory"},
}


def collect_with(**run_patch: object) -> dict[str, object]:
    with patch("spark_cli.cli.Path.exists", return_value=True), patch("spark_cli.cli.subprocess.run", **run_patch):
        return collect_builder_memory_direct_smoke(
            installed=INSTALLED,
            builder_home="/private/spark/state/spark-intelligence",
            builder_env={},
        )


def test_builder_memory_smoke_nonzero_exit_never_relays_child_output() -> None:
    raw = (
        "subprocess.CalledProcessError: Command ['icacls', "
        "'/Users/private/.spark/state/.env', 'private-user:(R,W)'] failed; token=private-token"
    )
    completed = subprocess.CompletedProcess(args=["private-command"], returncode=5, stdout=raw, stderr="")

    payload = collect_with(return_value=completed)

    assert payload["ok"] is False
    assert payload["ran"] is True
    assert payload["detail"] == "Builder memory direct smoke failed with exit 5. No Builder or Memory state was accepted."
    for leaked in ("icacls", "CalledProcessError", "private-user", "/Users/private", "private-token", "private-command"):
        assert leaked not in str(payload)


def test_builder_memory_smoke_launch_error_reports_only_error_type() -> None:
    payload = collect_with(side_effect=PermissionError("private-user /Users/private/.spark token=private-token"))

    assert payload["detail"] == "Builder memory direct smoke could not start (error type: PermissionError)."
    assert "private-user" not in str(payload)
    assert "/Users/private" not in str(payload)
    assert "private-token" not in str(payload)


def test_builder_memory_smoke_timeout_has_stable_nonreflecting_truth() -> None:
    timeout = subprocess.TimeoutExpired(
        cmd=["private-command", "token=private-token"],
        timeout=30,
        output="/Users/private/.spark",
    )

    payload = collect_with(side_effect=timeout)

    assert payload["detail"] == "Builder memory direct smoke timed out after 30 seconds."
    assert "private-command" not in str(payload)
    assert "private-token" not in str(payload)
    assert "/Users/private" not in str(payload)
