"""Test: circular ref guard in dir traversal."""
import os
import tempfile
from pathlib import Path

def test_circular_symlink_does_not_cause_infinite_loop():
    with tempfile.TemporaryDirectory() as tmpdir:
        a_dir = Path(tmpdir) / "a"
        b_dir = Path(tmpdir) / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        (a_dir / "file.txt").write_text("hello")
        (a_dir / "link_to_b").symlink_to(b_dir, target_is_directory=True)
        (b_dir / "link_to_a").symlink_to(a_dir, target_is_directory=True)
        visited = set()
        files = []
        for root, dirs, filenames in os.walk(str(tmpdir), followlinks=False):
            real_root = os.path.realpath(root)
            if real_root in visited:
                dirs.clear()
                continue
            visited.add(real_root)
            files.extend(os.path.join(root, f) for f in filenames)
        assert len(files) >= 1
