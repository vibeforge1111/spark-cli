from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from spark_cli.cli import read_clipboard_text


def test_clipboard_missing_helper_degrades_to_shaped_guidance() -> None:
    with (
        patch("spark_cli.cli.sys.platform", "darwin"),
        patch("spark_cli.cli.subprocess.run", side_effect=FileNotFoundError("pbpaste")),
        pytest.raises(SystemExit, match="Could not read a secret from the system clipboard"),
    ):
        read_clipboard_text()


def test_clipboard_invalid_utf8_tries_next_helper_without_replacement() -> None:
    available = {"wl-paste": "/bin/wl-paste", "xclip": "/bin/xclip"}
    results = [
        subprocess.CompletedProcess(["/bin/wl-paste"], 0, stdout=b"secret-\xff", stderr=b""),
        subprocess.CompletedProcess(["/bin/xclip"], 0, stdout="sëcret-token\n".encode(), stderr=b""),
    ]

    with (
        patch("spark_cli.cli.sys.platform", "linux"),
        patch("spark_cli.cli.shutil.which", side_effect=lambda name: available.get(name)),
        patch("spark_cli.cli.subprocess.run", side_effect=results) as run,
    ):
        assert read_clipboard_text() == "sëcret-token"

    assert len(run.call_args_list) == 2
    for call in run.call_args_list:
        assert call.kwargs["text"] is False
        assert "errors" not in call.kwargs


def test_clipboard_all_invalid_utf8_degrades_without_reflecting_bytes() -> None:
    with (
        patch("spark_cli.cli.sys.platform", "darwin"),
        patch(
            "spark_cli.cli.subprocess.run",
            return_value=subprocess.CompletedProcess(["pbpaste"], 0, stdout=b"token-\xff", stderr=b""),
        ),
        pytest.raises(SystemExit) as raised,
    ):
        read_clipboard_text()

    message = str(raised.value)
    assert "Could not read a secret from the system clipboard" in message
    assert "token" not in message.lower()
