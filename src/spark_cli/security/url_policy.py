from __future__ import annotations

import ipaddress
import socket
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass


METADATA_HOSTS = {
    "169.254.169.254",
    "169.254.170.2",
    "fd00:ec2::254",
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
    candidate = host.strip("[]")
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        address = _legacy_ipv4_address(candidate)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _legacy_ipv4_part(value: str) -> int | None:
    try:
        if value.lower().startswith("0x"):
            return int(value[2:], 16)
        if len(value) > 1 and value.startswith("0"):
            return int(value[1:] or "0", 8)
        return int(value, 10)
    except ValueError:
        return None


def _legacy_ipv4_address(host: str) -> ipaddress.IPv4Address | None:
    if not host or not all(character in "0123456789abcdefABCDEFxX." for character in host):
        return None
    parts = host.split(".")
    if len(parts) > 4 or any(not part for part in parts):
        return None
    numbers = [_legacy_ipv4_part(part) for part in parts]
    if any(number is None for number in numbers):
        return None
    values = [int(number) for number in numbers if number is not None]
    try:
        if len(values) == 1:
            if values[0] > 0xFFFFFFFF:
                return None
            packed = values[0]
        elif len(values) == 2:
            if values[0] > 0xFF or values[1] > 0xFFFFFF:
                return None
            packed = (values[0] << 24) | values[1]
        elif len(values) == 3:
            if values[0] > 0xFF or values[1] > 0xFF or values[2] > 0xFFFF:
                return None
            packed = (values[0] << 24) | (values[1] << 16) | values[2]
        else:
            if any(value > 0xFF for value in values):
                return None
            packed = (values[0] << 24) | (values[1] << 16) | (values[2] << 8) | values[3]
        return ipaddress.IPv4Address(packed)
    except (ValueError, OverflowError):
        return None


Address = ipaddress.IPv4Address | ipaddress.IPv6Address
AddressResolver = Callable[..., list[tuple[int, int, int, str, tuple[object, ...]]]]


def _normalized_address(value: str) -> Address | None:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def resolve_host_addresses(host: str, *, resolver: AddressResolver = socket.getaddrinfo) -> tuple[Address, ...]:
    literal = _host_ip(host)
    if literal is not None:
        return (literal,)
    records = resolver(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    addresses: list[Address] = []
    seen: set[str] = set()
    for _family, _kind, _protocol, _canonical_name, socket_address in records:
        if not socket_address:
            continue
        address = _normalized_address(str(socket_address[0]))
        if address is None or str(address) in seen:
            continue
        seen.add(str(address))
        addresses.append(address)
    return tuple(addresses)


def _address_safety_errors(address: Address, *, host: str, label: str, policy: UrlPolicy) -> list[str]:
    errors: list[str] = []
    if address.is_loopback and not policy.allow_local:
        errors.append(f"{label} points at local-only host `{host}`.")
    if address.is_unspecified or address.is_multicast or address.is_link_local:
        errors.append(f"{label} points at unsafe network address `{host}`.")
    elif address.is_private and not address.is_loopback and not policy.allow_private_networks:
        errors.append(f"{label} points at private network address `{host}`.")
    return errors


def validate_url_resolution(
    raw_url: str,
    *,
    label: str = "URL",
    policy: UrlPolicy | None = None,
    resolver: AddressResolver = socket.getaddrinfo,
) -> list[str]:
    active_policy = policy or UrlPolicy()
    errors = validate_url_safety(raw_url, label=label, policy=active_policy)
    if errors:
        return errors
    parsed = _parse_url(str(raw_url or "").strip())
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    try:
        addresses = resolve_host_addresses(host, resolver=resolver)
    except (socket.gaierror, OSError, ValueError):
        return [f"{label} hostname `{host}` could not be resolved safely."]
    if not addresses:
        return [f"{label} hostname `{host}` did not resolve to an IP address."]
    for address in addresses:
        errors.extend(_address_safety_errors(address, host=host, label=label, policy=active_policy))
    return list(dict.fromkeys(errors))


def validate_local_health_url(raw_url: str, *, label: str = "health check URL") -> list[str]:
    value = str(raw_url or "").strip()
    if not value:
        return [f"{label} is empty."]
    try:
        parsed = urllib.parse.urlparse(value)
        port = parsed.port
    except ValueError:
        return [f"{label} is malformed."]
    if parsed.scheme not in {"http", "https"}:
        return [f"{label} must use HTTP or HTTPS."]
    if parsed.username is not None or parsed.password is not None:
        return [f"{label} must not contain URL credentials."]
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return [f"{label} has no hostname."]
    if port is None:
        return [f"{label} must declare an explicit loopback port."]
    canonical_literal = _normalized_address(host.strip("[]"))
    if host != "localhost" and (canonical_literal is None or not canonical_literal.is_loopback):
        return [f"{label} must target a canonical loopback address or `localhost`, not `{host}`."]
    return []


def validate_url_safety(raw_url: str, *, label: str = "URL", policy: UrlPolicy | None = None) -> list[str]:
    active_policy = policy or UrlPolicy()
    value = str(raw_url or "").strip()
    if not value:
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
        errors.extend(_address_safety_errors(ip, host=host, label=label, policy=active_policy))
    if active_policy.require_https_for_remote and not is_local and parsed.scheme != "https":
        errors.append(f"{label} uses non-HTTPS remote endpoint `{value}`.")
    return errors
