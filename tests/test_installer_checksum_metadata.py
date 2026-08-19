from __future__ import annotations

from unittest.mock import patch

from spark_cli.cli import hosted_installer_checksums


class FakeResponse:
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return b"malformed-line-without-a-path\n\n" + (b"a" * 64) + b"  install.sh\n"


def test_hosted_installer_checksums_skip_malformed_lines() -> None:
    with patch("spark_cli.cli.installer_urlopen", return_value=FakeResponse()):
        assert hosted_installer_checksums() == {"install.sh": "a" * 64}
