from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


TRACE_SCHEMA_VERSION = "spark.trace_reconstruction.v1"


def _safe_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _read_jsonl(path: Path, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    valid_lines = 0
    invalid_lines = 0
    line_count = 0
    exists = path.exists()
    if exists:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line_count += 1
                parsed = _parse_json(line)
                if isinstance(parsed, dict):
                    valid_lines += 1
                    records.append(parsed)
                    if len(records) > limit:
                        records.pop(0)
                else:
                    invalid_lines += 1
    return records, {
        "path": str(path),
        "exists": exists,
        "line_count": line_count,
        "valid_line_count": valid_lines,
        "records_retained": len(records),
        "invalid_lines": invalid_lines,
    }


def _compact(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _target_aliases(target: str) -> set[str]:
    aliases = {_safe_str(target) or ""}
    for prefix in ("turn:", "telegram:", "telegram-update:", "update:", "mission:", "request:", "trace:"):
        if target.startswith(prefix):
            aliases.add(target.removeprefix(prefix))
    return {alias for alias in aliases if alias}


def _matches(record: dict[str, Any], aliases: set[str], fields: tuple[str, ...]) -> bool:
    for field in fields:
        value = _safe_str(record.get(field))
        if value and value in aliases:
            return True
    return False


def _add_ids_from_record(ids: set[str], record: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        value = _safe_str(record.get(field))
        if value:
            ids.add(value)


TURN_FIELDS = (
    "turn_id",
    "telegram_update_id",
    "update_id",
    "sib_request_id",
    "sib_trace_ref",
    "mission_id",
    "build_request_id",
    "trace_ref",
    "request_id",
)
SPAWNER_FIELDS = (
    "turn_id",
    "mission_id",
    "missionId",
    "request_id",
    "requestId",
    "trace_ref",
    "traceRef",
    "build_request_id",
    "buildRequestId",
)
SAFE_TURN_FIELDS = (
    "schema",
    "schema_version",
    "turn_id",
    "telegram_update_id",
    "sib_request_id",
    "sib_trace_ref",
    "mission_id",
    "build_request_id",
    "route",
    "reply_kind",
    "status",
    "dedupe_key",
)
SAFE_SPAWNER_FIELDS = (
    "schema",
    "schema_version",
    "turn_id",
    "mission_id",
    "missionId",
    "request_id",
    "requestId",
    "trace_ref",
    "traceRef",
    "build_request_id",
    "buildRequestId",
    "event_type",
    "eventType",
    "status",
    "outcome",
    "result",
    "reason_code",
    "reasonCode",
)
SAFE_DB_FIELDS = (
    "ledger_id",
    "event_id",
    "turn_id",
    "action_id",
    "capability_id",
    "authorization_decision_id",
    "tool_name",
    "owner_system",
    "mutation_class",
    "outcome",
    "status",
    "surface",
    "component",
    "event_type",
    "severity",
    "request_id",
    "trace_ref",
    "parent_event_id",
    "created_at",
    "updated_at",
    "recorded_at",
)


def _sanitize(record: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for field in fields:
        value = record.get(field)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            continue
        text = _safe_str(value)
        if text is not None:
            sanitized[field] = text
    return sanitized


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.DatabaseError:
        return []
    return [str(row[1]) for row in rows]


def _query_table(
    conn: sqlite3.Connection,
    table: str,
    match_columns: tuple[str, ...],
    ids: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    columns = _table_columns(conn, table)
    if not columns or not ids:
        return []
    usable_match_columns = [column for column in match_columns if column in columns]
    if not usable_match_columns:
        return []

    clauses = []
    params: list[Any] = []
    id_values = sorted(ids)
    placeholders = ",".join("?" for _ in id_values)
    for column in usable_match_columns:
        clauses.append(f"{column} IN ({placeholders})")
        params.extend(id_values)

    order_columns = [column for column in ("created_at", "updated_at", "recorded_at") if column in columns]
    order_clause = f" ORDER BY {order_columns[0]} DESC" if order_columns else ""
    query = f"SELECT * FROM {table} WHERE {' OR '.join(clauses)}{order_clause} LIMIT ?"
    params.append(limit)
    try:
        rows = conn.execute(query, params).fetchall()
    except sqlite3.DatabaseError:
        return []
    return [{columns[index]: row[index] for index in range(len(columns))} for row in rows]


def _read_state_rows(state_db: Path, ids: set[str], limit: int) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    meta = {"path": str(state_db), "exists": state_db.exists()}
    rows = {"tool_call_ledger": [], "builder_events": [], "event_log": []}
    if not state_db.exists():
        return rows, meta

    conn = sqlite3.connect(str(state_db))
    try:
        rows["tool_call_ledger"] = _query_table(
            conn,
            "tool_call_ledger",
            ("turn_id", "request_id", "trace_ref", "ledger_id", "action_id", "authorization_decision_id"),
            ids,
            limit,
        )
        rows["builder_events"] = _query_table(
            conn,
            "builder_events",
            ("turn_id", "request_id", "trace_ref", "event_id", "parent_event_id"),
            ids,
            limit,
        )
        rows["event_log"] = _query_table(
            conn,
            "event_log",
            ("turn_id", "request_id", "trace_ref", "event_id", "parent_event_id"),
            ids,
            limit,
        )
    finally:
        conn.close()
    return rows, meta


def _merge_rows(existing: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str | None, ...]] = set()
    merged: list[dict[str, Any]] = []
    for row in existing + new_rows:
        key = tuple(
            _safe_str(row.get(field))
            for field in (
                "ledger_id",
                "event_id",
                "turn_id",
                "request_id",
                "trace_ref",
                "created_at",
                "updated_at",
                "recorded_at",
            )
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def _merge_state_rows(
    existing: dict[str, list[dict[str, Any]]],
    new_rows: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        "tool_call_ledger": _merge_rows(existing["tool_call_ledger"], new_rows["tool_call_ledger"]),
        "builder_events": _merge_rows(existing["builder_events"], new_rows["builder_events"]),
        "event_log": _merge_rows(existing["event_log"], new_rows["event_log"]),
    }


def _extract_ledger_metadata(row: dict[str, Any]) -> dict[str, Any]:
    ledger_json = _safe_mapping(_parse_json(row.get("ledger_json")))
    authorization = _safe_mapping(ledger_json.get("authorization"))
    result = _safe_mapping(ledger_json.get("result"))
    metadata = _sanitize(row, SAFE_DB_FIELDS)
    metadata.update(
        {
            key: value
            for key, value in {
                "schema": _safe_str(ledger_json.get("schema") or ledger_json.get("schema_version")),
                "ledger_id": _safe_str(row.get("ledger_id") or ledger_json.get("ledger_id")),
                "turn_id": _safe_str(row.get("turn_id") or ledger_json.get("turn_id")),
                "action_id": _safe_str(row.get("action_id") or ledger_json.get("action_id")),
                "capability_id": _safe_str(row.get("capability_id") or ledger_json.get("capability_id")),
                "tool_name": _safe_str(row.get("tool_name") or ledger_json.get("tool_name")),
                "authorization_decision_id": _safe_str(
                    row.get("authorization_decision_id")
                    or authorization.get("decision_id")
                    or authorization.get("authorization_decision_id")
                ),
                "authorization_turn_id": _safe_str(authorization.get("turn_id")),
                "result_status": _safe_str(row.get("status") or row.get("outcome") or result.get("status")),
            }.items()
            if value is not None
        }
    )
    return metadata


def _ledger_replayability(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _extract_ledger_metadata(row)
    turn_id = metadata.get("turn_id")
    authorization_turn_id = metadata.get("authorization_turn_id")
    checks = {
        "ledger_id_present": bool(metadata.get("ledger_id")),
        "turn_id_present": bool(turn_id),
        "action_id_present": bool(metadata.get("action_id")),
        "authorization_decision_id_present": bool(metadata.get("authorization_decision_id")),
        "authorization_turn_id_matches": bool(turn_id and authorization_turn_id and authorization_turn_id == turn_id),
        "result_status_present": bool(metadata.get("result_status")),
    }
    return {
        "ledger_id": metadata.get("ledger_id"),
        "turn_id": turn_id,
        "authorization_decision_id": metadata.get("authorization_decision_id"),
        "replayable": all(checks.values()),
        "checks": checks,
    }


def _trace_paths(args: argparse.Namespace) -> dict[str, Path]:
    spark_home = Path(args.spark_home).expanduser()
    builder_home = Path(args.builder_home).expanduser() if args.builder_home else spark_home / "state" / "spark-intelligence"
    return {
        "spark_home": spark_home,
        "builder_home": builder_home,
        "state_db": Path(args.state_db).expanduser() if args.state_db else builder_home / "state.db",
        "bot_turn_trace": Path(args.bot_turn_trace).expanduser()
        if args.bot_turn_trace
        else spark_home / "state" / "spark-telegram-bot" / "turn-trace.jsonl",
        "spawner_prd_trace": Path(args.spawner_prd_trace).expanduser()
        if args.spawner_prd_trace
        else spark_home / "state" / "spawner-ui" / "prd-auto-trace.jsonl",
        "spawner_agent_events": Path(args.spawner_agent_events).expanduser()
        if args.spawner_agent_events
        else spark_home / "state" / "spawner-ui" / "agent-events.jsonl",
    }


def build_trace_payload(
    target: str,
    *,
    spark_home: Path,
    builder_home: Path | None = None,
    state_db: Path | None = None,
    bot_turn_trace: Path | None = None,
    spawner_prd_trace: Path | None = None,
    spawner_agent_events: Path | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    builder_home = builder_home or spark_home / "state" / "spark-intelligence"
    state_db = state_db or builder_home / "state.db"
    bot_turn_trace = bot_turn_trace or spark_home / "state" / "spark-telegram-bot" / "turn-trace.jsonl"
    spawner_prd_trace = spawner_prd_trace or spark_home / "state" / "spawner-ui" / "prd-auto-trace.jsonl"
    spawner_agent_events = spawner_agent_events or spark_home / "state" / "spawner-ui" / "agent-events.jsonl"

    aliases = _target_aliases(target)
    ids = set(aliases)
    turn_records, turn_meta = _read_jsonl(bot_turn_trace, limit)
    prd_records, prd_meta = _read_jsonl(spawner_prd_trace, limit)
    agent_records, agent_meta = _read_jsonl(spawner_agent_events, limit)

    for record in turn_records:
        if _matches(record, ids, TURN_FIELDS):
            _add_ids_from_record(ids, record, TURN_FIELDS)
    for record in prd_records + agent_records:
        if _matches(record, ids, SPAWNER_FIELDS):
            _add_ids_from_record(ids, record, SPAWNER_FIELDS)

    state_rows, state_meta = _read_state_rows(state_db, ids, limit)
    for row in state_rows["tool_call_ledger"] + state_rows["builder_events"] + state_rows["event_log"]:
        _add_ids_from_record(ids, row, ("turn_id", "request_id", "trace_ref", "ledger_id", "action_id", "authorization_decision_id", "event_id"))
    expanded_state_rows, state_meta = _read_state_rows(state_db, ids, limit)
    state_rows = _merge_state_rows(state_rows, expanded_state_rows)

    matching_turn_records = [record for record in turn_records if _matches(record, ids, TURN_FIELDS)]
    matching_prd_records = [record for record in prd_records if _matches(record, ids, SPAWNER_FIELDS)]
    matching_agent_records = [record for record in agent_records if _matches(record, ids, SPAWNER_FIELDS)]

    ledger_rows = [_extract_ledger_metadata(row) for row in state_rows["tool_call_ledger"]]
    replayability = [_ledger_replayability(row) for row in state_rows["tool_call_ledger"]]
    resolved_turn_ids = _compact(
        [_safe_str(record.get("turn_id")) for record in matching_turn_records]
        + [_safe_str(row.get("turn_id")) for row in ledger_rows]
        + [_safe_str(row.get("turn_id")) for row in state_rows["builder_events"]]
        + [_safe_str(row.get("turn_id")) for row in state_rows["event_log"]]
        + [_safe_str(record.get("turn_id")) for record in matching_prd_records + matching_agent_records]
    )

    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "target": {
            "query": target,
            "aliases": sorted(aliases),
            "resolved_ids": sorted(ids),
            "resolved_turn_ids": resolved_turn_ids,
        },
        "planes": {
            "turn": {
                "count": len(matching_turn_records),
                "records": [_sanitize(record, SAFE_TURN_FIELDS) for record in matching_turn_records],
            },
            "authority": {
                "count": len(ledger_rows),
                "tool_call_ledgers": ledger_rows,
            },
            "state": {
                "builder_event_count": len(state_rows["builder_events"]),
                "event_log_count": len(state_rows["event_log"]),
                "builder_events": [_sanitize(row, SAFE_DB_FIELDS) for row in state_rows["builder_events"]],
                "event_log": [_sanitize(row, SAFE_DB_FIELDS) for row in state_rows["event_log"]],
            },
            "health": {
                "prd_auto_trace_count": len(matching_prd_records),
                "agent_event_count": len(matching_agent_records),
                "prd_auto_trace": [_sanitize(record, SAFE_SPAWNER_FIELDS) for record in matching_prd_records],
                "agent_events": [_sanitize(record, SAFE_SPAWNER_FIELDS) for record in matching_agent_records],
            },
        },
        "replayability": {
            "ledger_count": len(replayability),
            "ledger_replayable_count": sum(1 for item in replayability if item["replayable"]),
            "checks": replayability,
        },
        "sources": {
            "state_db": state_meta,
            "bot_turn_trace": turn_meta,
            "spawner_prd_trace": prd_meta,
            "spawner_agent_events": agent_meta,
        },
        "redaction": "metadata only; raw ledger JSON, event payloads, prompt text, chat text, and traces are omitted",
    }


def cmd_trace(args: argparse.Namespace) -> int:
    paths = _trace_paths(args)
    payload = build_trace_payload(
        args.target,
        spark_home=paths["spark_home"],
        builder_home=paths["builder_home"],
        state_db=paths["state_db"],
        bot_turn_trace=paths["bot_turn_trace"],
        spawner_prd_trace=paths["spawner_prd_trace"],
        spawner_agent_events=paths["spawner_agent_events"],
        limit=max(1, int(args.limit or 100)),
    )
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if payload["target"]["resolved_turn_ids"] or payload["replayability"]["ledger_count"] else 1

    planes = payload["planes"]
    replayability = payload["replayability"]
    print(f"Spark trace: {payload['target']['query']}")
    turn_ids = payload["target"]["resolved_turn_ids"]
    print(f"- resolved turn ids: {', '.join(turn_ids) if turn_ids else 'none'}")
    print(f"- turn plane records: {planes['turn']['count']}")
    print(f"- authority ledger rows: {planes['authority']['count']}")
    print(f"- state plane records: {planes['state']['builder_event_count'] + planes['state']['event_log_count']}")
    print(f"- health plane records: {planes['health']['prd_auto_trace_count'] + planes['health']['agent_event_count']}")
    print(f"- replayable ledger rows: {replayability['ledger_replayable_count']}/{replayability['ledger_count']}")
    print("Redaction: metadata only; raw traces, payloads, prompt text, and chat text are omitted.")
    return 0 if turn_ids or replayability["ledger_count"] else 1
