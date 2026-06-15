from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spark_cli.trace_command import build_trace_payload, cmd_trace


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def _fixture(tmp_path):
    spark_home = tmp_path / ".spark"
    builder_home = spark_home / "state" / "spark-intelligence"
    state_db = builder_home / "state.db"
    state_db.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(state_db)
    conn.execute(
        """
        CREATE TABLE tool_call_ledger (
            ledger_id TEXT,
            turn_id TEXT,
            action_id TEXT,
            capability_id TEXT,
            authorization_decision_id TEXT,
            tool_name TEXT,
            status TEXT,
            request_id TEXT,
            trace_ref TEXT,
            ledger_json TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE builder_events (
            event_id TEXT,
            turn_id TEXT,
            request_id TEXT,
            trace_ref TEXT,
            component TEXT,
            event_type TEXT,
            status TEXT,
            payload_json TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE event_log (
            event_id TEXT,
            turn_id TEXT,
            request_id TEXT,
            trace_ref TEXT,
            component TEXT,
            event_type TEXT,
            status TEXT,
            payload_json TEXT,
            recorded_at TEXT
        )
        """
    )
    ledger_json = {
        "schema": "spark.tool_call_ledger.v1",
        "ledger_id": "ledger-1",
        "turn_id": "turn:trace-1",
        "action_id": "action-1",
        "capability_id": "capability-1",
        "tool_name": "safe_tool",
        "authorization": {
            "decision_id": "decision-1",
            "turn_id": "turn:trace-1",
        },
        "result": {"status": "success", "private_detail": "private fixture text"},
    }
    conn.execute(
        """
        INSERT INTO tool_call_ledger
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ledger-1",
            "turn:trace-1",
            "action-1",
            "capability-1",
            "decision-1",
            "safe_tool",
            "success",
            "request-1",
            "trace-1",
            json.dumps(ledger_json),
            "2026-06-13T00:00:00Z",
        ),
    )
    conn.execute(
        "INSERT INTO builder_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "builder-event-1",
            "turn:trace-1",
            "request-1",
            "trace-1",
            "harness",
            "decision_recorded",
            "ok",
            json.dumps({"private_detail": "private fixture text"}),
            "2026-06-13T00:00:01Z",
        ),
    )
    conn.execute(
        "INSERT INTO event_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "event-log-1",
            "turn:trace-1",
            "request-1",
            "trace-1",
            "builder",
            "ledger_written",
            "ok",
            json.dumps({"private_detail": "private fixture text"}),
            "2026-06-13T00:00:02Z",
        ),
    )
    conn.commit()
    conn.close()

    _write_jsonl(
        spark_home / "state" / "spark-telegram-bot" / "turn-trace.jsonl",
        [
            {
                "schema": "spark.turn_trace.v1",
                "turn_id": "turn:trace-1",
                "telegram_update_id": "123",
                "sib_request_id": "request-1",
                "sib_trace_ref": "trace-1",
                "mission_id": "mission-abc",
                "build_request_id": "tg-build-abc",
                "route": "builder",
                "reply_kind": "final",
                "status": "ok",
                "message_text": "private fixture text",
            }
        ],
    )
    _write_jsonl(
        spark_home / "state" / "spawner-ui" / "prd-auto-trace.jsonl",
        [
            {
                "schema": "spark.prd_auto_trace.v1",
                "missionId": "mission-abc",
                "requestId": "tg-build-abc",
                "traceRef": "trace-1",
                "status": "ok",
                "prompt": "private fixture text",
            }
        ],
    )
    _write_jsonl(
        spark_home / "state" / "spawner-ui" / "agent-events.jsonl",
        [
            {
                "eventType": "mission_status",
                "missionId": "mission-abc",
                "requestId": "tg-build-abc",
                "traceRef": "trace-1",
                "status": "ok",
                "payload": "private fixture text",
            }
        ],
    )
    return spark_home


def test_trace_reconstructs_all_four_planes_without_raw_payloads(tmp_path):
    spark_home = _fixture(tmp_path)

    payload = build_trace_payload("turn:trace-1", spark_home=spark_home)

    assert payload["schema_version"] == "spark.trace_reconstruction.v1"
    assert payload["target"]["resolved_turn_ids"] == ["turn:trace-1"]
    assert payload["planes"]["turn"]["count"] == 1
    assert payload["planes"]["authority"]["count"] == 1
    assert payload["planes"]["state"]["builder_event_count"] == 1
    assert payload["planes"]["state"]["event_log_count"] == 1
    assert payload["planes"]["health"]["prd_auto_trace_count"] == 1
    assert payload["planes"]["health"]["agent_event_count"] == 1
    assert payload["replayability"]["ledger_replayable_count"] == 1
    assert "private fixture text" not in json.dumps(payload)


def test_trace_resolves_telegram_update_id_to_turn(tmp_path):
    spark_home = _fixture(tmp_path)

    payload = build_trace_payload("telegram:123", spark_home=spark_home)

    assert payload["target"]["resolved_turn_ids"] == ["turn:trace-1"]
    assert payload["planes"]["authority"]["count"] == 1


def test_trace_retains_recent_jsonl_records(tmp_path):
    spark_home = _fixture(tmp_path)
    turn_trace = spark_home / "state" / "spark-telegram-bot" / "turn-trace.jsonl"
    stale_records = [
        {
            "schema": "spark.turn_trace.v1",
            "turn_id": f"turn:stale-{index}",
            "telegram_update_id": f"stale-{index}",
            "status": "ok",
        }
        for index in range(5)
    ]
    recent_record = {
        "schema": "spark.turn_trace.v1",
        "turn_id": "turn:trace-1",
        "telegram_update_id": "123",
        "sib_request_id": "request-1",
        "sib_trace_ref": "trace-1",
        "mission_id": "mission-abc",
        "build_request_id": "tg-build-abc",
        "status": "ok",
    }
    _write_jsonl(turn_trace, stale_records + [recent_record])

    payload = build_trace_payload("telegram:123", spark_home=spark_home, limit=1)

    assert payload["target"]["resolved_turn_ids"] == ["turn:trace-1"]
    assert payload["sources"]["bot_turn_trace"]["records_retained"] == 1


def test_trace_expands_ledger_id_to_state_rows(tmp_path):
    spark_home = _fixture(tmp_path)

    payload = build_trace_payload("ledger-1", spark_home=spark_home)

    assert payload["target"]["resolved_turn_ids"] == ["turn:trace-1"]
    assert payload["planes"]["state"]["builder_event_count"] == 1
    assert payload["planes"]["state"]["event_log_count"] == 1


def test_cmd_trace_emits_json_metadata(tmp_path, capsys):
    spark_home = _fixture(tmp_path)
    args = argparse.Namespace(
        target="mission-abc",
        spark_home=str(spark_home),
        builder_home=None,
        state_db=None,
        bot_turn_trace=None,
        spawner_prd_trace=None,
        spawner_agent_events=None,
        limit=100,
        json=True,
    )

    assert cmd_trace(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["target"]["resolved_turn_ids"] == ["turn:trace-1"]
    assert output["planes"]["health"]["prd_auto_trace_count"] == 1


def test_cli_parser_exposes_trace_command(tmp_path):
    from spark_cli.cli import build_parser

    args = build_parser().parse_args(["trace", "turn:trace-1", "--spark-home", str(tmp_path), "--json"])

    assert args.func is cmd_trace
