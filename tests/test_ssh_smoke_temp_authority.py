from __future__ import annotations

import pytest

from spark_cli.sandbox.ssh import (
    SshTarget,
    ssh_smoke_execute_argv,
    ssh_smoke_probe_hash,
    ssh_smoke_remote_path,
    ssh_smoke_upload_argv,
)


def target() -> SshTarget:
    return SshTarget(
        name="odyssey-vps",
        host="example.test",
        user="spark",
        port=22,
        identity_file="/tmp/key",
        remote_workspace="~/spark-live",
        host_key_status="trusted",
        host_key_fingerprint="SHA256:test",
        created_at="2026-05-22T00:00:00Z",
        updated_at="2026-05-22T00:00:00Z",
    )


def test_remote_path_uses_private_random_directory() -> None:
    probe_hash = ssh_smoke_probe_hash()
    path = ssh_smoke_remote_path(target(), probe_hash, nonce="0123456789abcdef0123456789abcdef")
    assert path == "/tmp/spark-sandbox-smoke-odyssey-vps-0123456789abcdef0123456789abcdef/probe.sh"
    assert probe_hash not in path


def test_upload_atomically_claims_private_directory() -> None:
    path = ssh_smoke_remote_path(
        target(), ssh_smoke_probe_hash(), nonce="0123456789abcdef0123456789abcdef"
    )
    command = ssh_smoke_upload_argv(target(), path)[-1]
    assert "mkdir -m 700 -- \"$dir\"" in command
    assert "SPARK_SSH_REMOTE_DIR_EXISTS" in command
    assert "umask 077" in command
    assert "cat > \"$file\"" in command


def test_execute_cleans_private_directory_and_rejects_foreign_path() -> None:
    probe_hash = ssh_smoke_probe_hash()
    path = ssh_smoke_remote_path(
        target(), probe_hash, nonce="0123456789abcdef0123456789abcdef"
    )
    command = ssh_smoke_execute_argv(target(), path, probe_hash)[-1]
    assert "rm -rf -- \"$dir\"" in command
    with pytest.raises(ValueError, match="SSH smoke remote path"):
        ssh_smoke_execute_argv(target(), "/tmp/foreign.sh", probe_hash)
