import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, "src")


def test_collect_status_payload_skips_missing_module(tmp_path, monkeypatch):
    """collect_status_payload must not crash when a registered module path is missing."""
    from spark_cli import cli

    fake_registry = {
        "good-mod": {"path": str(tmp_path / "good")},
        "bad-mod": {"path": str(tmp_path / "nonexistent")},
    }

    # Create a valid module for good-mod
    good_mod_dir = tmp_path / "good"
    good_mod_dir.mkdir()
    (good_mod_dir / "spark.toml").write_text(
        '[module]\nname = "good-mod"\nversion = "1.0"\nkind = "service"\nplane = "execution"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "REGISTRY_PATH", tmp_path / "registry.json")
    (tmp_path / "registry.json").write_text(json.dumps(fake_registry), encoding="utf-8")

    monkeypatch.setattr(cli, "CONFIG_PATH", tmp_path / "setup.json")
    (tmp_path / "setup.json").write_text(json.dumps({}), encoding="utf-8")

    # Should NOT crash — should skip bad-mod and continue
    payload = cli.collect_status_payload()
    assert isinstance(payload, dict)
    module_names = [m["name"] for m in payload.get("modules", []) if isinstance(m, dict)]
    assert "good-mod" in module_names
    assert "bad-mod" not in module_names


def test_collect_status_payload_skips_corrupt_toml(tmp_path, monkeypatch):
    """collect_status_payload must not crash on a module with corrupt spark.toml."""
    from spark_cli import cli

    bad_dir = tmp_path / "corrupt-mod"
    bad_dir.mkdir()
    (bad_dir / "spark.toml").write_text("this is not valid toml [[[", encoding="utf-8")

    fake_registry = {"corrupt-mod": {"path": str(bad_dir)}}

    monkeypatch.setattr(cli, "REGISTRY_PATH", tmp_path / "registry.json")
    (tmp_path / "registry.json").write_text(json.dumps(fake_registry), encoding="utf-8")

    monkeypatch.setattr(cli, "CONFIG_PATH", tmp_path / "setup.json")
    (tmp_path / "setup.json").write_text(json.dumps({}), encoding="utf-8")

    payload = cli.collect_status_payload()
    assert isinstance(payload, dict)
    # corrupt module should be silently skipped
    module_names = [m["name"] for m in payload.get("modules", []) if isinstance(m, dict)]
    assert "corrupt-mod" not in module_names
