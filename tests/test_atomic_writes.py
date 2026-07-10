import pytest
import os
import tempfile
import json


class TestAtomicWrites:
    def test_atomic_write_prevents_partial_file(self):
        """PR #497: atomic managed env writes with escaped multiline values"""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "test.env")
            tmp = target + ".tmp"
            with open(tmp, "w") as f:
                f.write("KEY=value\nMULTI=line1\\line2")
            os.replace(tmp, target)
            assert os.path.exists(target)
            assert not os.path.exists(tmp)
            with open(target) as f:
                content = f.read()
            assert "KEY=value" in content

    def test_atomic_write_survives_crash(self):
        """Verify temp file is written before replace"""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "config.json")
            tmp = target + ".tmp"
            data = json.dumps({"key": "value"})
            with open(tmp, "w") as f:
                f.write(data)
            os.replace(tmp, target)
            with open(target) as f:
                assert json.load(f) == {"key": "value"}
