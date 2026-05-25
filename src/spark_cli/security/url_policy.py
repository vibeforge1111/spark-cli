from __future__ import annotations

import ipaddress
import urllib.parse
from dataclasses import dataclass


METADATA_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
}

UNSAFE_BIND_HOSTS = {
    "0.0.0.0",
    "::",
}

LOCAL_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "127.0.0.1",
    "::1",
}


@dataclass(frozen=True)
class UrlPolicy:
    allow_local: bool = True
    allow_private_networks: bool = False
    require_https_for_remote: bool = True


def _parse_url(raw_url: str) -> urllib.parse.ParseResult:
    value = raw_url.strip()
    if "://" not in value:
        value = f"http://{value}"
    return urllib.parse.urlparse(value)


def _host_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def _has_url_space_or_control(value: str) -> bool:
    return any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)


def validate_url_safety(raw_url: str, *, label: str = "URL", policy: UrlPolicy | None = None) -> list[str]:
    active_policy = policy or UrlPolicy()
    value = str(raw_url or "").strip()
    if not value or value.startswith("${"):
        return []

    errors: list[str] = []
    if _has_url_space_or_control(value):
        errors.append(f"{label} contains whitespace or control characters.")
    parsed = _parse_url(value)
    if parsed.scheme not in {"http", "https"}:
        return [f"{label} uses unsupported URL scheme `{parsed.scheme}`."]

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return [f"{label} has a URL without a hostname."]
    if _has_url_space_or_control(urllib.parse.unquote(host)):
        errors.append(f"{label} hostname contains encoded whitespace or control characters.")
    if host in METADATA_HOSTS:
        errors.append(f"{label} points at cloud metadata service `{host}`.")
    if host in UNSAFE_BIND_HOSTS:
        errors.append(f"{label} points at unsafe bind host `{host}`.")

    ip = _host_ip(host)
    is_local = host in LOCAL_HOSTS or bool(ip and ip.is_loopback)
    if is_local and not active_policy.allow_local:
        errors.append(f"{label} points at local-only host `{host}`.")
    if ip is not None:
        if ip.is_unspecified or ip.is_multicast or ip.is_link_local:
            errors.append(f"{label} points at unsafe network address `{host}`.")
        elif ip.is_private and not ip.is_loopback and not active_policy.allow_private_networks:
            errors.append(f"{label} points at private network address `{host}`.")
    if active_policy.require_https_for_remote and not is_local and parsed.scheme != "https":
        errors.append(f"{label} uses non-HTTPS remote endpoint `{value}`.")
    return errors
