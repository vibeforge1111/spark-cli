from __future__ import annotations

import ipaddress
import urllib.parse
import urllib.request
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
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def _validate_parsed_url(value: str, label: str, active_policy: UrlPolicy) -> list[str]:
    """Pure static validation of a single URL string. No I/O, no network."""
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
        if ip.is_unspecified or ip.is_multicast or ip.is_link_local:
            errors.append(f"{label} points at unsafe network address `{host}`.")
        elif ip.is_private and not ip.is_loopback and not active_policy.allow_private_networks:
            errors.append(f"{label} points at private network address `{host}`.")
    if active_policy.require_https_for_remote and not is_local and parsed.scheme != "https":
        errors.append(f"{label} uses non-HTTPS remote endpoint `{value}`.")
    return errors


def validate_url_safety(raw_url: str, *, label: str = "URL", policy: UrlPolicy | None = None) -> list[str]:
    """
    Pure static URL safety validator.

    No network I/O, no exceptions, no hidden side effects. Safe to call from
    static config-time scans (``spark doctor``, ``endpoint_security_errors``)
    and any other context where reaching the URL would be inappropriate.

    For runtime fetchers that need redirect-chain awareness (so a 302 to
    169.254.169.254 cannot bypass the gate), use
    :func:`validate_url_safety_with_redirect_check` instead.
    """
    active_policy = policy or UrlPolicy()
    value = str(raw_url or "").strip()
    if not value or value.startswith("${"):
        return []
    return _validate_parsed_url(value, label, active_policy)


def _resolve_redirects(url: str, max_redirects: int = 5) -> str:
    """
    Follow HTTP redirects with a hard depth bound and HEAD-only requests.

    Internal helper for :func:`validate_url_safety_with_redirect_check`. Falls
    back to the last-known URL on any network error so the wrapper always has
    something concrete to scan. NOT exposed as part of the static validator
    surface.
    """
    current_url = url
    for _ in range(max_redirects):
        try:
            req = urllib.request.Request(current_url, method='HEAD')
            req.add_header('User-Agent', 'Spark-CLI-Security-Check/1.0')
            with urllib.request.urlopen(req, timeout=3) as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get('Location')
                    if location:
                        current_url = urllib.parse.urljoin(current_url, location)
                        continue
                return current_url
        except Exception:
            return current_url
    return current_url


def validate_url_safety_with_redirect_check(
    raw_url: str,
    *,
    label: str = "URL",
    policy: UrlPolicy | None = None,
) -> list[str]:
    """
    Runtime-only variant that emits a HEAD request to follow redirect chains.

    Use this from a runtime fetcher (e.g. immediately before issuing a real
    request to a user-supplied URL) where the cost of one HEAD round-trip is
    acceptable and the static gate alone is insufficient (a malicious origin
    could 302 to ``169.254.169.254`` or ``127.0.0.1`` and bypass the gate
    that only inspected the configured first hop).

    Steps:

    1. Run the pure static validator on the input URL. If it already
       fails, return those errors without emitting any network traffic.
    2. Otherwise, walk the redirect chain HEAD-only with a depth bound.
       Re-run the pure static validator on the final destination so an
       attacker-controlled redirect to a forbidden host is reported as
       a normal validation error.

    This function is the only network-emitting code path in this module
    and MUST NOT be called from static config-time scans (``spark doctor``,
    ``endpoint_security_errors``, registry verifiers, etc.). Static callers
    must use :func:`validate_url_safety`.
    """
    active_policy = policy or UrlPolicy()
    value = str(raw_url or "").strip()
    if not value or value.startswith("${"):
        return []

    static_errors = _validate_parsed_url(value, label, active_policy)
    if static_errors:
        return static_errors

    final_url = _resolve_redirects(value)
    if final_url == value:
        return []
    return _validate_parsed_url(final_url, label, active_policy)
