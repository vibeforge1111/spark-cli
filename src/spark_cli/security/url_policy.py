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
        addr = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None
    # Unwrap IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return addr.ipv4_mapped
    return addr


def _resolve_host_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a hostname via DNS and return the resulting IP addresses.

    This catches non-canonical IP representations (octal, hex, decimal,
    shortened forms) that ``ipaddress.ip_address()`` rejects but the OS
    resolver still accepts — e.g. ``0177.0.0.1``, ``0x7f000001``,
    ``127.1``, ``2130706433``.
    """
    try:
        results = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except (socket.gaierror, OSError, ValueError):
        return []
    seen: set[str] = set()
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for family, _type, _proto, _canon, sockaddr in results:
        raw = sockaddr[0]
        if raw in seen:
            continue
        seen.add(raw)
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        ips.append(addr)
    return ips


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

    # When the host is not a literal IP accepted by ipaddress, resolve it
    # via DNS so that non-canonical forms (octal, hex, decimal, shortened)
    # that still resolve to loopback/private addresses are caught.
    if ip is None and host not in LOCAL_HOSTS:
        resolved_ips = _resolve_host_ips(host)
        for rip in resolved_ips:
            if rip.is_loopback:
                is_local = True
                break

    if is_local and not active_policy.allow_local:
        errors.append(f"{label} points at local-only host `{host}`.")

    # Build the set of IP addresses to check for network-level safety.
    # Prefer the literal IP from _host_ip(); fall back to resolved IPs.
    check_ips = [ip] if ip is not None else _resolve_host_ips(host)
    for check_ip in check_ips:
        if check_ip.is_unspecified or check_ip.is_multicast or check_ip.is_link_local:
            errors.append(f"{label} points at unsafe network address `{host}`.")
        elif check_ip.is_private and not check_ip.is_loopback and not active_policy.allow_private_networks:
            errors.append(f"{label} points at private network address `{host}`.")

    if active_policy.require_https_for_remote and not is_local and parsed.scheme != "https":
        errors.append(f"{label} uses non-HTTPS remote endpoint `{value}`.")
    return errors
