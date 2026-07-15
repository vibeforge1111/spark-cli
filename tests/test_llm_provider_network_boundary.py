from __future__ import annotations

import socket
import urllib.parse
import urllib.request
from unittest.mock import patch

import pytest

from spark_cli.cli import (
    _open_pinned_provider_request,
    _validated_llm_provider_endpoint,
    read_llm_provider_json,
)


def _resolver(*addresses: str):
    def resolve(_host: str, _port: object, *_args: object) -> list[tuple[int, int, int, str, tuple[object, ...]]]:
        records = []
        for address in addresses:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            records.append((family, socket.SOCK_STREAM, 6, "", (address, 0)))
        return records

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.test/v1/chat/completions",
        "https://user:secret@api.example.test/v1/chat/completions",
        "https://api.example.test/v1/chat/completions?redirect=https://attacker.example",
        "https://api.example.test/v1/chat/completions#attacker",
        "https://127.0.0.1/v1/chat/completions",
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_credential_provider_rejects_unsafe_endpoint_before_transport(url: str) -> None:
    with pytest.raises(SystemExit, match="LLM provider URL rejected"):
        _validated_llm_provider_endpoint(
            url,
            label="LLM provider",
            allow_local=False,
            resolver=_resolver("8.8.8.8"),
        )


def test_credential_provider_rejects_any_private_dns_answer() -> None:
    with pytest.raises(SystemExit, match="private network"):
        _validated_llm_provider_endpoint(
            "https://api.example.test/v1/chat/completions",
            label="LLM provider",
            allow_local=False,
            resolver=_resolver("8.8.8.8", "10.0.0.8"),
        )


def test_credential_provider_returns_public_address_for_pinned_transport() -> None:
    parsed, address = _validated_llm_provider_endpoint(
        "https://api.example.test/v1/chat/completions",
        label="LLM provider",
        allow_local=False,
        resolver=_resolver("8.8.8.8"),
    )

    assert parsed.hostname == "api.example.test"
    assert str(address) == "8.8.8.8"


def test_ollama_can_use_canonical_loopback_but_not_other_private_hosts() -> None:
    parsed, address = _validated_llm_provider_endpoint(
        "http://localhost:11434/api/chat",
        label="Ollama",
        allow_local=True,
        resolver=_resolver("127.0.0.1"),
    )
    assert parsed.hostname == "localhost"
    assert str(address) == "127.0.0.1"

    with pytest.raises(SystemExit, match="URL rejected"):
        _validated_llm_provider_endpoint(
            "http://ollama.internal:11434/api/chat",
            label="Ollama",
            allow_local=True,
            resolver=_resolver("10.0.0.9"),
        )


def test_provider_request_pins_validated_address_and_preserves_logical_host() -> None:
    request = urllib.request.Request(
        "https://api.example.test/v1/chat/completions",
        data=b"{}",
        headers={"Authorization": "Bearer fake-test-key"},
        method="POST",
    )
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200
        reason = "OK"

        def read(self, size: int = -1) -> bytes:
            return b'{"choices":[]}' if size != 1 else b""

    class FakeConnection:
        def request(self, method: str, path: str, *, body: bytes | None, headers: dict[str, str]) -> None:
            captured.update(method=method, path=path, body=body, headers=headers)

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            captured["closed"] = True

    def connection_factory(parsed, address, timeout):
        captured.update(host=parsed.hostname, address=str(address), timeout=timeout)
        return FakeConnection()

    payload, status, _reason = _open_pinned_provider_request(
        request,
        address="8.8.8.8",
        timeout=60,
        connection_factory=connection_factory,
    )

    assert payload == b'{"choices":[]}'
    assert status == 200
    assert captured["host"] == "api.example.test"
    assert captured["address"] == "8.8.8.8"
    assert captured["path"] == "/v1/chat/completions"
    assert captured["closed"] is True


def test_provider_redirect_is_reported_without_following_location() -> None:
    request = urllib.request.Request(
        "https://api.example.test/v1/chat/completions",
        data=b"{}",
        method="POST",
    )
    with patch(
        "spark_cli.cli._validated_llm_provider_endpoint",
        return_value=(urllib.parse.urlparse(request.full_url), "8.8.8.8"),
    ), patch(
        "spark_cli.cli._open_pinned_provider_request",
        return_value=(b"", 302, "Found"),
    ) as transport:
        with pytest.raises(SystemExit, match="HTTP 302"):
            read_llm_provider_json(request, "LLM provider", allow_local=False)

    transport.assert_called_once()
