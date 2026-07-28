from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def classify_telegram_module_health(
    result: dict[str, Any] | None,
    *,
    process_running: bool,
    token_recorded: bool,
) -> dict[str, Any]:
    healthy = bool(result and result.get("healthy") is True)
    if healthy:
        return {
            "ok": True,
            "level": "ok",
            "detail": str(result.get("detail") or "Telegram runtime health is verified."),
            "repair": "spark status",
        }

    detail = str(result.get("detail") or "spark-telegram-bot is not installed.") if result else "spark-telegram-bot is not installed."
    lowered = detail.lower()
    secret_session_declined = (
        "bot_token" in lowered
        and "approved spark secret session" in lowered
    )
    if secret_session_declined and process_running and token_recorded:
        return {
            "ok": False,
            "level": "warning",
            "detail": (
                "Live Telegram health could not be verified in this shell. Spark supervision is running "
                "and the selected bot token is recorded, but those facts do not prove Telegram delivery."
            ),
            "repair": "Run `spark status` from an approved Spark secret session before treating Telegram as healthy.",
        }
    return {"ok": False, "level": "error", "detail": detail, "repair": "spark status"}


def resolve_telegram_fix_health(
    result: dict[str, Any] | None,
    pids: dict[str, Any],
    process_keys: Iterable[str],
    pid_is_running: Callable[[int], bool],
    secret_keys: set[str],
    selected_token_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
    process_record = next(
        (
            candidate
            for key in process_keys
            if isinstance((candidate := pids.get(key)), dict)
            and pid_is_running(int(candidate.get("pid", 0)))
        ),
        None,
    )
    token_recorded = bool({"telegram.bot_token", selected_token_id} & secret_keys)
    health = classify_telegram_module_health(
        result,
        process_running=process_record is not None,
        token_recorded=token_recorded,
    )
    return health, process_record, token_recorded
