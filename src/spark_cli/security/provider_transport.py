from __future__ import annotations

import http.client
import socket
import ssl
import urllib.parse
import urllib.request
from collections.abc import Callable

from .url_policy import Address, AddressResolver, UrlPolicy, resolve_url_addresses


LLM_PROVIDER_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def validated_llm_provider_endpoint(
    raw_url: str,
    *,
    label: str,
    allow_local: bool,
    resolver: AddressResolver = socket.getaddrinfo,
) -> tuple[urllib.parse.ParseResult, Address]:
    try:
        parsed = urllib.parse.urlparse(str(raw_url or "").strip())
        _port = parsed.port
    except ValueError as exc:
        raise SystemExit(f"{label} URL rejected: malformed endpoint.") from exc
    structural_errors: list[str] = []
    if parsed.username is not None or parsed.password is not None:
        structural_errors.append(f"{label} URL must not contain URL credentials.")
    if parsed.query:
        structural_errors.append(f"{label} URL must not contain a query string.")
    if parsed.fragment:
        structural_errors.append(f"{label} URL must not contain a fragment.")
    if structural_errors:
        raise SystemExit(f"{label} URL rejected: {' '.join(structural_errors)}")
    addresses, errors = resolve_url_addresses(
        raw_url,
        label=f"{label} URL",
        policy=UrlPolicy(
            allow_local=allow_local,
            allow_private_networks=False,
            require_https_for_remote=True,
        ),
        resolver=resolver,
    )
    if errors or not addresses:
        detail = " ".join(errors) if errors else f"{label} URL did not resolve safely."
        raise SystemExit(f"{label} URL rejected: {detail}")
    return parsed, addresses[0]


class _PinnedProviderHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, pinned_address: str, *, port: int, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._pinned_address = pinned_address

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )


class _PinnedProviderHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, pinned_address: str, *, port: int, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = pinned_address

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except BaseException:
            raw_socket.close()
            raise


def provider_connection_factory(
    parsed: urllib.parse.ParseResult,
    address: Address | str,
    timeout: float,
) -> http.client.HTTPConnection:
    host = str(parsed.hostname or "")
    if parsed.scheme == "https":
        return _PinnedProviderHTTPSConnection(
            host,
            str(address),
            port=parsed.port or 443,
            timeout=timeout,
        )
    return _PinnedProviderHTTPConnection(
        host,
        str(address),
        port=parsed.port or 80,
        timeout=timeout,
    )


def open_pinned_provider_request(
    request: urllib.request.Request,
    *,
    address: Address | str,
    timeout: float,
    connection_factory: Callable[[urllib.parse.ParseResult, Address | str, float], http.client.HTTPConnection] = provider_connection_factory,
) -> tuple[bytes, int, str]:
    parsed = urllib.parse.urlparse(request.full_url)
    connection = connection_factory(parsed, address, timeout)
    path = urllib.parse.urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
    try:
        connection.request(
            request.get_method(),
            path,
            body=request.data,
            headers=dict(request.header_items()),
        )
        response = connection.getresponse()
        payload = response.read(LLM_PROVIDER_MAX_RESPONSE_BYTES + 1)
        if len(payload) > LLM_PROVIDER_MAX_RESPONSE_BYTES:
            raise SystemExit(
                f"LLM provider response exceeded {LLM_PROVIDER_MAX_RESPONSE_BYTES} bytes."
            )
        return payload, int(response.status), str(response.reason or "")
    finally:
        connection.close()
