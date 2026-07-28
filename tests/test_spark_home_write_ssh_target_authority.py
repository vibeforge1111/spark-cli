from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from spark_cli.cli import path_is_write_denied
from spark_cli.sandbox.access import access_lane_payload
from spark_cli.sandbox.ssh import SshTarget


def test_default_root_spark_home_allows_owned_state_but_not_secret_store() -> None:
    spark_home = Path("/root/.spark")
    secrets_file = spark_home / "config" / "secrets.local.json"

    with (
        patch("spark_cli.cli.Path.home", return_value=Path("/root")),
        patch("spark_cli.cli.SPARK_HOME", spark_home),
        patch("spark_cli.cli.SECRETS_FILE_PATH", secrets_file),
    ):
        assert path_is_write_denied(spark_home / "state" / "runtime.json") == (False, "")
        denied, reason = path_is_write_denied(secrets_file)

    assert denied
    assert "secrets.local.json" in reason


def test_spark_home_exception_never_bypasses_sensitive_home_prefixes() -> None:
    spark_home = Path("/root/.ssh/spark")

    with (
        patch("spark_cli.cli.Path.home", return_value=Path("/root")),
        patch("spark_cli.cli.SPARK_HOME", spark_home),
        patch("spark_cli.cli.SECRETS_FILE_PATH", spark_home / "config" / "secrets.local.json"),
    ):
        denied, reason = path_is_write_denied(spark_home / "state.json")

    assert denied
    assert ".ssh" in reason


def test_spark_home_parent_traversal_remains_denied() -> None:
    spark_home = Path("/root/.spark")

    with (
        patch("spark_cli.cli.Path.home", return_value=Path("/root")),
        patch("spark_cli.cli.SPARK_HOME", spark_home),
        patch("spark_cli.cli.SECRETS_FILE_PATH", spark_home / "config" / "secrets.local.json"),
    ):
        denied, reason = path_is_write_denied(spark_home / ".." / ".ssh" / "authorized_keys")

    assert denied
    assert ".ssh" in reason


def test_access_lane_counts_trusted_ssh_target_values() -> None:
    target = SshTarget(
        name="trusted",
        host="example.test",
        user="spark",
        port=22,
        identity_file="/safe/id_ed25519",
        remote_workspace="~/spark",
        host_key_status="trusted",
        host_key_fingerprint="SHA256:synthetic",
        created_at="2026-07-16T00:00:00Z",
        updated_at="2026-07-16T00:00:00Z",
    )

    with (
        patch("spark_cli.sandbox.access.load_ssh_targets", return_value={"trusted": target}),
        patch("spark_cli.sandbox.access.modal_auth_markers", return_value={}),
        patch("spark_cli.sandbox.access.modal_sdk_available", return_value=False),
        patch("spark_cli.sandbox.access.docker_doctor_readiness", return_value={}),
        patch("spark_cli.sandbox.access.generated_level5_env", return_value={}),
        patch("spark_cli.sandbox.access.level5_env_file_state", return_value={}),
        patch("spark_cli.sandbox.access.level5_service_guardrail_state", return_value={"enabled": False}),
    ):
        payload = access_lane_payload(level=4, home=Path("/tmp/spark-home"), env={})

    ssh_lane = next(lane for lane in payload["lanes"] if lane["id"] == "ssh")
    assert ssh_lane["configured"] is True
    assert ssh_lane["available"] is True
    assert ssh_lane["trusted_targets"] == 1
