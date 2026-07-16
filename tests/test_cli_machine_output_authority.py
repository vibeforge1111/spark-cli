from __future__ import annotations

import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from spark_cli.cli import main


@pytest.mark.parametrize("command", ["authority", "trace"])
def test_os_json_output_requires_json_before_collecting_state(command: str) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir, patch("spark_cli.cli.compile_system_map") as compile_map:
        output = Path(tmp_dir) / "report.json"
        with pytest.raises(SystemExit) as raised:
            main(["os", command, "--output", str(output)])

        assert str(raised.value) == "--output requires --json for Spark OS authority and trace reports."
        compile_map.assert_not_called()
        assert not output.exists()


@pytest.mark.parametrize("command", ["authority", "trace"])
def test_os_json_output_respects_runtime_write_boundary(command: str) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        safe_root = root / "allowed"
        output = root / "outside" / "report.json"
        safe_root.mkdir()
        with patch.dict(os.environ, {"SPARK_WRITE_SAFE_ROOT": str(safe_root)}, clear=False), patch(
            "spark_cli.cli.compile_system_map"
        ) as compile_map:
            with pytest.raises(SystemExit, match="outside Spark write boundary"):
                main(["os", command, "--json", "--output", str(output)])

        compile_map.assert_not_called()
        assert not output.exists()


@pytest.mark.parametrize(
    "command,expected_schema",
    [
        ("authority", "spark.os_authority.summary.v0"),
        ("trace", "spark.os_trace.summary.v0"),
    ],
)
def test_os_json_output_is_atomic_structured_and_quiet(command: str, expected_schema: str) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        output = Path(tmp_dir) / "nested" / "report.json"
        with patch("spark_cli.cli.compile_system_map", return_value={}), patch(
            "sys.stdout", new_callable=StringIO
        ) as stdout:
            assert main(["os", command, "--json", "--output", str(output)]) == 0

        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["ok"] is True
        assert payload["schema_version"] == expected_schema
        assert stdout.getvalue() == ""
        assert not list(output.parent.glob(".*.tmp"))


def test_list_json_is_structured_and_does_not_expose_module_paths() -> None:
    module = SimpleNamespace(
        name="spark-telegram-bot",
        version="1.2.3",
        kind="bot",
        plane="agent",
        path=Path("/private/runtime/source"),
    )
    with patch("spark_cli.cli.load_registry_definition", return_value={"modules": {module.name: {"blessed": True}}}), patch(
        "spark_cli.cli.load_json", return_value={module.name: {}}
    ), patch("spark_cli.cli.discover_modules", return_value={module.name: module}), patch(
        "sys.stdout", new_callable=StringIO
    ) as stdout:
        assert main(["list", "--json"]) == 0

    payload = json.loads(stdout.getvalue())
    assert payload == {
        "ok": True,
        "count": 1,
        "modules": [
            {
                "name": "spark-telegram-bot",
                "version": "1.2.3",
                "kind": "bot",
                "plane": "agent",
                "blessed": True,
                "installed": True,
            }
        ],
    }
    assert "/private/runtime/source" not in stdout.getvalue()
