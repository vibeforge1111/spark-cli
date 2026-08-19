from __future__ import annotations

import os
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from spark_cli.cli import ALLOW_INSECURE_FILE_SECRETS_ENV, INSECURE_FILE_SECRET_PREFIX, dpapi_protect


def test_insecure_file_secret_warning_is_once_nonreflecting_and_actionable() -> None:
    from spark_cli.secret_storage_notice import warn_insecure_file_secret_storage

    warn_insecure_file_secret_storage.cache_clear()
    stderr = StringIO()
    try:
        with patch("spark_cli.cli.os.name", "posix"), patch.dict(
            os.environ, {ALLOW_INSECURE_FILE_SECRETS_ENV: "1"}, clear=False
        ), redirect_stderr(stderr):
            first = dpapi_protect("first-sensitive-value")
            second = dpapi_protect("second-sensitive-value")
    finally:
        warn_insecure_file_secret_storage.cache_clear()

    assert first.startswith(INSECURE_FILE_SECRET_PREFIX)
    assert second.startswith(INSECURE_FILE_SECRET_PREFIX)
    warning = stderr.getvalue()
    assert warning.count("Insecure local secret storage is active") == 1
    assert "encoded, not encrypted" in warning
    assert "disposable local testing" in warning
    assert "first-sensitive-value" not in warning
    assert "second-sensitive-value" not in warning
    assert "secrets.local.json" not in warning
