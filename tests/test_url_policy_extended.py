from __future__ import annotations

from spark_cli.security.url_policy import UrlPolicy, validate_url_safety


def test_validate_url_safety_ignores_blank_and_template_values() -> None:
    assert validate_url_safety("", label="endpoint") == []
    assert validate_url_safety("   ", label="endpoint") == []
    assert validate_url_safety("${OLLAMA_HOST}", label="endpoint") == []


def test_validate_url_safety_rejects_unsupported_schemes() -> None:
    errors = validate_url_safety("ftp://example.com", label="endpoint")
    assert errors and "unsupported URL scheme" in errors[0]


def test_validate_url_safety_rejects_missing_hostname() -> None:
    errors = validate_url_safety("http://", label="endpoint")
    assert errors and "without a hostname" in errors[0]


def test_validate_url_safety_flags_metadata_hosts() -> None:
    errors = validate_url_safety(
        "https://metadata.google.internal/v1",
        label="provider",
    )
    assert any("cloud metadata service" in error for error in errors)


def test_validate_url_safety_flags_unsafe_bind_host() -> None:
    errors = validate_url_safety("http://0.0.0.0:8080", label="provider")
    assert any("unsafe bind host" in error for error in errors)


def test_validate_url_safety_flags_link_local_address() -> None:
    errors = validate_url_safety("http://169.254.0.5/", label="provider")
    assert any("unsafe network address" in error for error in errors)


def test_validate_url_safety_requires_https_for_remote_hosts() -> None:
    errors = validate_url_safety("http://example.com/v1", label="endpoint")
    assert any("non-HTTPS remote endpoint" in error for error in errors)
    permissive = validate_url_safety(
        "http://example.com/v1",
        label="endpoint",
        policy=UrlPolicy(require_https_for_remote=False),
    )
    assert permissive == []


def test_validate_url_safety_accepts_https_remote_host() -> None:
    errors = validate_url_safety("https://api.example.com/v1", label="endpoint")
    assert errors == []


def test_validate_url_safety_infers_scheme_when_missing() -> None:
    # values without :// are treated as http:// and validated normally
    errors = validate_url_safety("example.com", label="endpoint")
    assert any("non-HTTPS remote endpoint" in error for error in errors)


def test_validate_url_safety_rejects_private_when_disallowed() -> None:
    errors = validate_url_safety(
        "http://10.0.0.5:9000",
        label="provider",
        policy=UrlPolicy(allow_private_networks=False, require_https_for_remote=False),
    )
    assert any("private network address" in error for error in errors)
