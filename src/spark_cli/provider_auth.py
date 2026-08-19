from __future__ import annotations


def effective_provider_auth_mode(
    provider: str,
    *,
    configured_auth_mode: str = "not_configured",
    api_key_configured: bool = False,
    stored_secret_configured: bool = False,
    base_url_kind: str = "default",
    codex_cli_present: bool = False,
    claude_cli_present: bool = False,
) -> str:
    """Resolve one provider auth mode from persisted and observed evidence."""
    auth_mode = configured_auth_mode or "not_configured"
    if auth_mode != "not_configured":
        return auth_mode
    if api_key_configured or stored_secret_configured:
        return "api_key"
    if provider == "codex" and codex_cli_present:
        return "codex_oauth"
    if provider == "openai" and base_url_kind == "local":
        return "local"
    if provider == "anthropic" and claude_cli_present:
        return "claude_oauth"
    if provider in {"lmstudio", "ollama"}:
        return "local"
    return "not_configured"
