from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from spark_cli.cli import PRIVATE_FILE_MODE, atomic_write_json, load_json


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes only")
def test_atomic_write_json_never_chmods_a_published_temp_file() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "state.json"
        chmod_targets: list[str] = []
        real_chmod = os.chmod

        def tracking_chmod(target: object, mode: int, *args: object, **kwargs: object) -> None:
            chmod_targets.append(str(target))
            real_chmod(target, mode, *args, **kwargs)

        old_umask = os.umask(0o000)
        try:
            with patch("spark_cli.cli.os.chmod", side_effect=tracking_chmod):
                atomic_write_json(path, {"ok": True})
        finally:
            os.umask(old_umask)

        assert not [target for target in chmod_targets if ".tmp" in target]
        assert path.stat().st_mode & 0o777 == PRIVATE_FILE_MODE


@pytest.mark.skipif(os.name == "nt", reason="symlink collision proof requires POSIX semantics")
def test_atomic_write_json_does_not_follow_a_prepositioned_temp_symlink() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        path = root / "state.json"
        victim = root / "victim.txt"
        victim.write_text("preserve me\n", encoding="utf-8")
        claimed = root / f".{path.name}.{os.getpid()}.claimed.tmp"
        claimed.symlink_to(victim)

        with patch("spark_cli.cli.py_secrets.token_hex", side_effect=("claimed", "fresh")):
            atomic_write_json(path, {"ok": True})

        assert victim.read_text(encoding="utf-8") == "preserve me\n"
        assert claimed.is_symlink()
        assert load_json(path, {}) == {"ok": True}
