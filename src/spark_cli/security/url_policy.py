from __future__ import annotations

import ipaddress
import socket
import urllib.parse
from dataclasses import dataclass


METADATA_HOSTS = {
    "169.254.169.254",
    "169.254.170.2",
    "metadata.amazonaws.com",
    "metadata.azure.com",
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

_DNS_RESOLVE_TIMEOUT = 2  # seconds


@dataclass(frozen=True)
class UrlPolicy:
    allow_local: bool = True
    allow_private_networks: bool = False
    require_https_for_remote: bool = True
    resolve_dns: bool = True


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


def _resolve_host_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Resolve a hostname to an IP address via DNS with a short timeout."""
    try:
        addrinfo = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if addrinfo:
            return ipaddress.ip_address(addrinfo[0][4][0])
    except (socket.gaierror, OSError, ValueError):
        pass
    return None


def _check_ip_safety(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, host: str, label: str, *, allow_local: bool, allow_private_networks: bool) -> list[str]:
    errors: list[str] = []
    if ip.is_unspecified or ip.is_multicast or ip.is_link_local:
        errors.append(f"{label} points at unsafe network address `{host}`.")
    elif ip.is_private and not ip.is_loopback and not allow_private_networks:
        errors.append(f"{label} points at private network address `{host}`.")
    if ip.is_loopback and not allow_local:
        errors.append(f"{label} points at local-only address `{host}`.")
    return errors


def validate_url_safety(raw_url: str, *, label: str = "URL", policy: UrlPolicy | None = None) -> list[str]:
    active_policy = policy or UrlPolicy()
    value = str(raw_url or "").strip()
    if not value or value.startswith("${"):
        return []

    errors: list[str] = []
    parsed = _parse_url(value)
    if parsed.scheme not in {"http", "https"}:
        return [f"{label} uses unsupported URL scheme `{parsed.scheme}`."]

    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return [f"{label} has a URL without a hostname."]
    if host in METADATA_HOSTS:
        errors.append(f"{label} points at cloud metadata service `{host}`.")
    if host in UNSAFE_BIND_HOSTS:
        errors.append(f"{label} points at unsafe bind host `{host}`.")

    ip = _host_ip(host)
    is_local = host in LOCAL_HOSTS or bool(ip and ip.is_loopback)
    if is_local and not active_policy.allow_local:
        errors.append(f"{label} points at local-only host `{host}`.")
    if ip is not None:
        errors.extend(_check_ip_safety(ip, host, label, allow_local=active_policy.allow_local, allow_private_networks=active_policy.allow_private_networks))
    elif active_policy.resolve_dns and host not in LOCAL_HOSTS:
        resolved_ip = _resolve_host_ip(host)
        if resolved_ip is not None:
            errors.extend(_check_ip_safety(resolved_ip, host, label, allow_local=active_policy.allow_local, allow_private_networks=active_policy.allow_private_networks))
            if resolved_ip.is_loopback:
                is_local = True
    if active_policy.require_https_for_remote and not is_local and parsed.scheme != "https":
        errors.append(f"{label} uses non-HTTPS remote endpoint `{value}`.")
    return errors
