from pathlib import Path
import tempfile

import pytest

from spark_cli.cli import read_generated_env, update_env_file, write_generated_env
from spark_cli.sandbox.access import read_env_file, write_env_file


@pytest.mark.parametrize("writer", [write_generated_env, write_env_file])
@pytest.mark.parametrize("value", ["safe\ninjected=1", "safe\rinjected=1", "safe\x00tail"])
def test_whole_file_writers_reject_control_character_injection_before_write(
    writer: object,
    value: str,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "module.env"
        with pytest.raises(SystemExit) as raised:
            writer(path, {"SAFE_KEY": value})  # type: ignore[operator]

        assert not path.exists()
    assert str(raised.value) == "Environment file values must be single-line text. Nothing was written."
    assert value not in str(raised.value)


def test_managed_block_writer_rejects_injection_without_touching_existing_file() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "module.env"
        original = "OWNER_VALUE=preserve-me\n"
        path.write_text(original, encoding="utf-8")

        with pytest.raises(SystemExit) as raised:
            update_env_file(path, {"SAFE_KEY": "safe\nINJECTED=1"})

        assert path.read_text(encoding="utf-8") == original
    assert str(raised.value) == "Environment file values must be single-line text. Nothing was written."


@pytest.mark.parametrize("reader", [read_generated_env, read_env_file])
def test_env_readers_preserve_notepad_ansi_bytes_without_replacement(reader: object) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "module.env"
        path.write_bytes("DISPLAY_NAME=café\n".encode("cp1252"))

        assert reader(path) == {"DISPLAY_NAME": "café"}  # type: ignore[operator]


@pytest.mark.parametrize("writer,reader", [(write_generated_env, read_generated_env), (write_env_file, read_env_file)])
def test_env_writers_preserve_literal_backslashes_without_escape_reinterpretation(
    writer: object,
    reader: object,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "module.env"
        value = r"C:\spark\new\runtime"
        writer(path, {"WINDOWS_PATH": value})  # type: ignore[operator]

        assert reader(path) == {"WINDOWS_PATH": value}  # type: ignore[operator]


@pytest.mark.parametrize("writer", [write_generated_env, write_env_file])
def test_env_writers_reject_invalid_keys_without_reflection(writer: object) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "module.env"
        with pytest.raises(SystemExit) as raised:
            writer(path, {"BAD\nKEY": "value"})  # type: ignore[operator]

        assert not path.exists()
    assert str(raised.value) == (
        "Environment file keys must use letters, numbers, and underscores and cannot start with a number. "
        "Nothing was written."
    )
    assert "BAD" not in str(raised.value)
