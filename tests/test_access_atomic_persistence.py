from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from spark_cli.sandbox.access import probe_workspace_writable, write_env_file


def test_write_env_file_preserves_existing_content_when_atomic_replace_fails(tmp_path: Path) -> None:
    target = tmp_path / "spark-telegram-bot.env"
    target.write_text("BOT_TOKEN=preserve-me\n", encoding="utf-8")

    with patch("spark_cli.cli.os.replace", side_effect=OSError("simulated replace failure")):
        with pytest.raises(OSError, match="simulated replace failure"):
            write_env_file(target, {"BOT_TOKEN": "replacement"})

    assert target.read_text(encoding="utf-8") == "BOT_TOKEN=preserve-me\n"
    assert list(tmp_path.iterdir()) == [target]


def test_workspace_preflight_cleans_partial_marker_after_write_failure(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    original_write_text = Path.write_text

    def fail_after_partial_write(path: Path, content: str, **kwargs: object) -> int:
        written = original_write_text(path, content[:4], **kwargs)
        raise OSError("simulated interrupted marker write")

    with patch.object(Path, "write_text", autospec=True, side_effect=fail_after_partial_write):
        result = probe_workspace_writable(workspace)

    assert result["writable"] is False
    assert result["detail"] == "Workspace write/delete preflight failed: OSError."
    assert list(workspace.iterdir()) == []
