from __future__ import annotations

from typing import Any


def with_configuration_readiness_scope(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "readiness_scope": "configuration",
        "live_probe": {
            "performed": False,
            "verified": False,
            "command": "spark providers test --role chat",
        },
    }


def render_provider_status_heading(summary: str) -> str:
    return (
        f"{summary}\n"
        "Configuration only; no live provider request was sent. "
        "Verify chat with `spark providers test --role chat`."
    )
