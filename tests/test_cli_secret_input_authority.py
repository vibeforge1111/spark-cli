import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest

from spark_cli.cli import (
    extract_telegram_bot_token,
    harden_secret_file,
    is_telegram_bot_token_secret,
    load_secrets_index,
    module_secret_env_bindings,
    split_secret_bindings,
    validate_telegram_bot_token,
)


@pytest.mark.parametrize("value", [None, 7, b"token"])
def test_telegram_token_input_rejects_non_text_without_reflection(value: object) -> None:
    with pytest.raises(SystemExit) as raised:
        extract_telegram_bot_token(value)  # type: ignore[arg-type]

    assert str(raised.value) == "Telegram bot token input must be text. Nothing was changed."
    assert repr(value) not in str(raised.value)


@pytest.mark.parametrize("secret_id", [None, 7, b"telegram.bot_token"])
def test_telegram_secret_classifier_treats_non_text_ids_as_not_tokens(secret_id: object) -> None:
    assert is_telegram_bot_token_secret(secret_id) is False  # type: ignore[arg-type]


def test_telegram_validation_rejects_non_object_response_without_token_reflection() -> None:
    token = "123456:secret_token_abcdefghijkl"

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b"[]"

    with patch("spark_cli.cli.urllib.request.urlopen", return_value=FakeResponse()):
        with pytest.raises(SystemExit) as raised:
            validate_telegram_bot_token(token)

    assert str(raised.value) == "Telegram returned an unexpected token-validation response. Nothing was changed."
    assert token not in str(raised.value)


def test_secrets_index_rejects_non_object_state_instead_of_discarding_it() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        index_path = Path(tmp_dir) / "secrets_index.json"
        index_path.write_text(json.dumps(["telegram.bot_token"]), encoding="utf-8")
        with patch("spark_cli.cli.SECRETS_INDEX_PATH", index_path):
            with pytest.raises(SystemExit) as raised:
                load_secrets_index()

    assert str(raised.value) == "Secrets index must be a JSON object. Nothing was changed."


@pytest.mark.parametrize("function", [module_secret_env_bindings, split_secret_bindings])
def test_secret_binding_resolution_rejects_missing_module_authority(function: object) -> None:
    with pytest.raises(SystemExit) as raised:
        function(None)  # type: ignore[operator]

    assert str(raised.value) == "Secret binding resolution requires a valid module manifest."


@pytest.mark.parametrize("path", [None, 7, object()])
def test_secret_file_hardening_rejects_invalid_paths_instead_of_skipping(path: object) -> None:
    with pytest.raises(SystemExit) as raised:
        harden_secret_file(path)  # type: ignore[arg-type]

    assert str(raised.value) == "Secret file hardening requires a valid filesystem path."
