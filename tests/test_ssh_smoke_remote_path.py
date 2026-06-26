from __future__ import annotations

import re
import unittest

from spark_cli.sandbox.ssh import (
    SshTarget,
    ssh_smoke_probe_hash,
    ssh_smoke_remote_path,
)


def _make_target(name: str = "testhost") -> SshTarget:
    return SshTarget(
        name=name,
        host="example.com",
        user="deploy",
        port=22,
        identity_file="~/.ssh/id_ed25519",
        remote_workspace="~/spark",
        host_key_status="accepted",
        host_key_fingerprint="aa:bb:cc",
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )


class SshSmokeRemotePathTests(unittest.TestCase):
    """Verify that ssh_smoke_remote_path generates unpredictable paths."""

    def test_path_matches_expected_format(self) -> None:
        target = _make_target()
        probe_hash = ssh_smoke_probe_hash()
        path = ssh_smoke_remote_path(target, probe_hash)
        pattern = re.compile(r"^/tmp/spark-sandbox-smoke-[a-z_][a-z0-9_-]{0,31}-[0-9a-f]{12}\.sh$")
        self.assertRegex(path, pattern, f"Path does not match expected format: {path}")

    def test_path_differs_across_calls(self) -> None:
        """The same target and hash must produce different paths on each call."""
        target = _make_target()
        probe_hash = ssh_smoke_probe_hash()
        paths = {ssh_smoke_remote_path(target, probe_hash) for _ in range(10)}
        self.assertGreater(len(paths), 1, "Remote path is deterministic — expected random variation")

    def test_path_does_not_contain_full_hash(self) -> None:
        """The path must not embed the full probe hash or its prefix."""
        target = _make_target()
        probe_hash = ssh_smoke_probe_hash()
        path = ssh_smoke_remote_path(target, probe_hash)
        self.assertNotIn(probe_hash, path, "Full probe hash should not appear in path")
        self.assertNotIn(probe_hash[:12], path, "Hash prefix should not appear in path")

    def test_invalid_probe_hash_raises(self) -> None:
        target = _make_target()
        with self.assertRaises(ValueError):
            ssh_smoke_remote_path(target, "not-a-valid-hash")

    def test_path_respects_target_name(self) -> None:
        target = _make_target(name="myserver")
        probe_hash = ssh_smoke_probe_hash()
        path = ssh_smoke_remote_path(target, probe_hash)
        self.assertIn("myserver", path)


if __name__ == "__main__":
    unittest.main()
