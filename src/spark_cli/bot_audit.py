from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BOT_AUDIT_SCHEMA_VERSION = "spark.bot_audit.v1"
BOT_AUDIT_STATE_DIR = Path("state") / "spark-telegram-bot"
DEFAULT_BOT_AUDIT_LIMIT = 200


@dataclass(frozen=True)
class BotAuditSpec:
    name: str
    filename: str
    identifier_fields: tuple[str, ...]
    legacy_idless_events: tuple[str, ...] = ()


BOT_AUDIT_SPECS: tuple[BotAuditSpec, ...] = (
    BotAuditSpec(
        name="final_answer_gate",
        filename="final-answer-gate-audit.jsonl",
        identifier_fields=(
            "request_id",
            "requestId",
            "trace_ref",
            "traceRef",
            "mission_id",
            "missionId",
            "turn_id",
            "turnId",
            "telegram_update_id",
            "update_id",
            "legacy_audit_ref",
        ),
    ),
    BotAuditSpec(
        name="node_outbound",
        filename="node-outbound-audit.jsonl",
        identifier_fields=(
            "request_id",
            "requestId",
            "trace_ref",
            "traceRef",
            "mission_id",
            "missionId",
            "turn_id",
            "turnId",
            "telegram_update_id",
            "update_id",
            "legacy_audit_ref",
        ),
        legacy_idless_events=("telegram_node_delivered",),
    ),
    BotAuditSpec(
        name="route_confidence",
        filename="route-confidence-audit.jsonl",
        identifier_fields=(
            "request_ref",
            "request_id",
            "requestId",
            "trace_ref",
            "traceRef",
            "mission_id",
            "missionId",
            "turn_id",
            "turnId",
            "telegram_update_id",
            "update_id",
            "legacy_audit_ref",
        ),
    ),
)


def _truthy_identifier(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _is_legacy_idless_row(payload: dict[str, Any], spec: BotAuditSpec) -> bool:
    """Classify pre-schema metadata-only rows as legacy warnings, not current failures."""
    if not spec.legacy_idless_events:
        return False
    if _truthy_identifier(payload.get("schema_version")):
        return False
    if str(payload.get("event") or "") not in spec.legacy_idless_events:
        return False
    if payload.get("privacy") != "metadata_only":
        return False
    if not _truthy_identifier(payload.get("chat_ref")):
        return False
    return _truthy_identifier(payload.get("text_length"))


def _read_tail(path: Path, limit: int) -> tuple[list[tuple[int, str]], dict[str, Any]]:
    tail: deque[tuple[int, str]] = deque(maxlen=max(1, int(limit)))
    nonempty_lines = 0
    exists = path.exists()
    if exists:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                nonempty_lines += 1
                tail.append((line_number, line))
    return list(tail), {
        "path": str(path),
        "exists": exists,
        "line_count": nonempty_lines,
        "tail_line_count": len(tail),
    }


def inspect_bot_audit_file(path: Path, spec: BotAuditSpec, *, limit: int) -> dict[str, Any]:
    rows, meta = _read_tail(path, limit)
    parsed_count = 0
    parse_errors: list[dict[str, Any]] = []
    missing_id_rows: list[dict[str, Any]] = []
    legacy_idless_rows: list[dict[str, Any]] = []
    identifier_presence = {field: 0 for field in spec.identifier_fields}

    for line_number, line in rows:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            parse_errors.append({"line_number": line_number, "error": type(exc).__name__})
            continue
        if not isinstance(payload, dict):
            parse_errors.append({"line_number": line_number, "error": "non_object_json"})
            continue
        parsed_count += 1
        present = [field for field in spec.identifier_fields if _truthy_identifier(payload.get(field))]
        for field in present:
            identifier_presence[field] += 1
        if not present and _is_legacy_idless_row(payload, spec):
            legacy_idless_rows.append(
                {
                    "line_number": line_number,
                    "event": str(payload.get("event") or payload.get("schema_version") or "unknown")[:80],
                    "outcome": str(payload.get("outcome") or payload.get("decision") or "unknown")[:80],
                }
            )
            continue
        if not present:
            missing_id_rows.append(
                {
                    "line_number": line_number,
                    "event": str(payload.get("event") or payload.get("schema_version") or "unknown")[:80],
                    "outcome": str(payload.get("outcome") or payload.get("decision") or "unknown")[:80],
                }
            )

    return {
        "name": spec.name,
        "filename": spec.filename,
        **meta,
        "parsed_count": parsed_count,
        "parse_error_count": len(parse_errors),
        "parse_errors": parse_errors[:20],
        "required_identifier_fields": list(spec.identifier_fields),
        "identifier_presence": {key: value for key, value in identifier_presence.items() if value},
        "missing_id_count": len(missing_id_rows),
        "missing_id_rows": missing_id_rows[:20],
        "legacy_idless_count": len(legacy_idless_rows),
        "legacy_idless_rows": legacy_idless_rows[:20],
    }


def build_bot_audit_payload(*, spark_home: Path, limit: int = DEFAULT_BOT_AUDIT_LIMIT) -> dict[str, Any]:
    safe_limit = max(1, int(limit))
    state_dir = spark_home / BOT_AUDIT_STATE_DIR
    sources = [
        inspect_bot_audit_file(state_dir / spec.filename, spec, limit=safe_limit)
        for spec in BOT_AUDIT_SPECS
    ]
    missing_files = [source["filename"] for source in sources if not source["exists"]]
    missing_id_count = sum(int(source["missing_id_count"]) for source in sources)
    parse_error_count = sum(int(source["parse_error_count"]) for source in sources)
    legacy_idless_count = sum(int(source["legacy_idless_count"]) for source in sources)
    return {
        "schema_version": BOT_AUDIT_SCHEMA_VERSION,
        "ok": not missing_files and missing_id_count == 0 and parse_error_count == 0,
        "spark_home": str(spark_home),
        "state_dir": str(state_dir),
        "limit": safe_limit,
        "summary": {
            "source_count": len(sources),
            "missing_file_count": len(missing_files),
            "missing_id_count": missing_id_count,
            "parse_error_count": parse_error_count,
            "legacy_idless_count": legacy_idless_count,
        },
        "sources": sources,
        "redaction": "metadata only; raw audit payloads, chat text, previews, prompts, and identifiers are omitted",
    }


def cmd_bot_audit(args: argparse.Namespace) -> int:
    spark_home = Path(args.spark_home).expanduser() if args.spark_home else Path.home() / ".spark"
    payload = build_bot_audit_payload(spark_home=spark_home, limit=args.limit)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if payload["ok"] else 1

    print("Spark bot audit")
    print(f"- state dir: {payload['state_dir']}")
    print(f"- scanned tail lines per file: {payload['limit']}")
    for source in payload["sources"]:
        status = "missing" if not source["exists"] else "ok"
        if source["missing_id_count"]:
            status = "missing_ids"
        if source["parse_error_count"]:
            status = "parse_errors"
        print(
            f"- {source['filename']}: {status}; "
            f"parsed={source['parsed_count']} missing_ids={source['missing_id_count']} "
            f"parse_errors={source['parse_error_count']} "
            f"legacy_idless={source['legacy_idless_count']}"
        )
        for row in source["missing_id_rows"][:5]:
            print(
                f"  - missing id at line {row['line_number']}: "
                f"event={row['event']} outcome={row['outcome']}"
            )
        for row in source["legacy_idless_rows"][:3]:
            print(
                f"  - legacy idless row at line {row['line_number']}: "
                f"event={row['event']} outcome={row['outcome']}"
            )
    print("Redaction: metadata only; raw audit payloads, chat text, previews, prompts, and ids are omitted.")
    return 0 if payload["ok"] else 1
