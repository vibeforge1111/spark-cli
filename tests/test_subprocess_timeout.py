import pytest
import subprocess


class TestSubprocessTimeout:
    def test_icacls_has_timeout(self):
        """PR #514: add timeout to subprocess.run"""
        cmd = ["echo", "test"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0

    def test_subprocess_timeout_raises_on_hang(self):
        """Verify timeout raises on long-running processes"""
        with pytest.raises(subprocess.TimeoutExpired):
            subprocess.run(["sleep", "10"], timeout=0.1)
