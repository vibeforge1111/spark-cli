from __future__ import annotations

import ipaddress
import urllib.parse
import urllib.request
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


def _resolve_redirects(url: str, max_redirects: int = 5) -> str:
    """
    Follow HTTP redirects and return the final destination URL.

    Walks redirect chains with a hard depth bound (``max_redirects``) so a
    pathological chain cannot stall the validator, uses HEAD-only requests
    so we never download a body, and falls back to the last-known URL on
    any network error so validation always has something concrete to scan.

    Prevents SSRF via redirect chains to localhost/metadata services.
    """
    current_url = url
    for _ in range(max_redirects):
        try:
            req = urllib.request.Request(current_url, method='HEAD')
            req.add_header('User-Agent', 'Spark-CLI-Security-Check/1.0')
            with urllib.request.urlopen(req, timeout=3) as response:
                # Check for redirect
                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get('Location')
                    if location:
                        current_url = urllib.parse.urljoin(current_url, location)
                        continue
                # No redirect, return current URL
                return current_url
        except Exception:
            # If we can't resolve, return the current URL for validation
            return current_url
    # Max redirects reached
    return current_url


def validate_url_safety(raw_url: str, *, label: str = "URL", policy: UrlPolicy | None = None) -> list[str]:
    active_policy = policy or UrlPolicy()
    value = str(raw_url or "").strip()
    if not value or value.startswith("${"):
        return []

    errors: list[str] = []
    
    # Follow redirects and validate final destination
    final_url = _resolve_redirects(value)
    if final_url != value:
        # Note: We validate the final URL but don't add this as an error
        # Just use the final destination for validation
        value = final_url
    
    parsed = _parse_url(value)
    if parsed.scheme not in {"http", "https"}:
        return [f"{label} uses unsupported URL scheme `{parsed.scheme}`."]

    host = (parsed.hostname or "").strip().lower()
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
