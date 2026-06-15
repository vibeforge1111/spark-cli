from __future__ import annotations

import argparse
import json
from pathlib import Path

from spark_cli.bot_audit import build_bot_audit_payload, cmd_bot_audit
from spark_cli.cli import build_parser
from spark_cli.security.approval import CommandContext, approval_required_for_command


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_bot_audit_tails_three_sources_and_flags_idless_rows(tmp_path: Path) -> None:
    spark_home = tmp_path / ".spark"
    state_dir = spark_home / "state" / "spark-telegram-bot"
    _write_jsonl(
        state_dir / "final-answer-gate-audit.jsonl",
        [
            {"event": "stale_legacy", "outcome": "ignored", "builder_reply_preview": "private fixture text"},
            {"event": "final_answer_checked", "outcome": "ok", "request_id": "request-1"},
            {"event": "telegram_command_reply", "outcome": "missing", "builder_reply_preview": "private fixture text"},
        ],
    )
    _write_jsonl(
        state_dir / "node-outbound-audit.jsonl",
        [
            {"event": "telegram_node_delivered", "request_id": "request-2", "delivered_text": "private fixture text"},
            {"schema_version": "spark.node_outbound_audit.v1", "event": "telegram_node_delivered", "text_preview": "private fixture text"},
        ],
    )
    _write_jsonl(
        state_dir / "route-confidence-audit.jsonl",
        [
            {"schema_version": "spark.route_confidence_gate.v1", "request_ref": "request-3"},
            {"schema_version": "spark.route_confidence_gate.v1", "decision": "missing"},
        ],
    )

    payload = build_bot_audit_payload(spark_home=spark_home, limit=2)

    assert payload["schema_version"] == "spark.bot_audit.v1"
    assert payload["ok"] is False
    assert payload["summary"]["source_count"] == 3
    assert payload["summary"]["missing_file_count"] == 0
    assert payload["summary"]["missing_id_count"] == 3
    assert payload["summary"]["legacy_idless_count"] == 0
    sources = {source["name"]: source for source in payload["sources"]}
    assert sources["final_answer_gate"]["missing_id_rows"][0]["line_number"] == 3
    assert sources["node_outbound"]["missing_id_rows"][0]["line_number"] == 2
    assert sources["route_confidence"]["missing_id_rows"][0]["line_number"] == 2
    assert "private fixture text" not in json.dumps(payload)


def test_bot_audit_reports_pre_schema_node_outbound_idless_rows_as_legacy_warnings(tmp_path: Path) -> None:
    spark_home = tmp_path / ".spark"
    state_dir = spark_home / "state" / "spark-telegram-bot"
    _write_jsonl(state_dir / "final-answer-gate-audit.jsonl", [{"event": "ok", "request_id": "request-1"}])
    _write_jsonl(
        state_dir / "node-outbound-audit.jsonl",
        [
            {
                "event": "telegram_node_delivered",
                "privacy": "metadata_only",
                "chat_ref": "chat_abc123",
                "text_length": 42,
            }
        ],
    )
    _write_jsonl(state_dir / "route-confidence-audit.jsonl", [{"event": "ok", "request_ref": "request-2"}])

    payload = build_bot_audit_payload(spark_home=spark_home, limit=10)

    assert payload["ok"] is True
    assert payload["summary"]["missing_id_count"] == 0
    assert payload["summary"]["legacy_idless_count"] == 1
    sources = {source["name"]: source for source in payload["sources"]}
    assert sources["node_outbound"]["legacy_idless_rows"][0]["line_number"] == 1


def test_bot_audit_still_fails_current_schema_node_outbound_idless_rows(tmp_path: Path) -> None:
    spark_home = tmp_path / ".spark"
    state_dir = spark_home / "state" / "spark-telegram-bot"
    _write_jsonl(state_dir / "final-answer-gate-audit.jsonl", [{"event": "ok", "request_id": "request-1"}])
    _write_jsonl(
        state_dir / "node-outbound-audit.jsonl",
        [
            {
                "schema_version": "spark.node_outbound_audit.v1",
                "event": "telegram_node_delivered",
                "privacy": "metadata_only",
                "chat_ref": "chat_abc123",
                "text_length": 42,
            }
        ],
    )
    _write_jsonl(state_dir / "route-confidence-audit.jsonl", [{"event": "ok", "request_ref": "request-2"}])

    payload = build_bot_audit_payload(spark_home=spark_home, limit=10)

    assert payload["ok"] is False
    assert payload["summary"]["missing_id_count"] == 1
    assert payload["summary"]["legacy_idless_count"] == 0


def test_cmd_bot_audit_emits_json_metadata(tmp_path: Path, capsys) -> None:
    spark_home = tmp_path / ".spark"
    state_dir = spark_home / "state" / "spark-telegram-bot"
    for filename in (
        "final-answer-gate-audit.jsonl",
        "node-outbound-audit.jsonl",
        "route-confidence-audit.jsonl",
    ):
        _write_jsonl(state_dir / filename, [{"event": "ok", "request_id": "request-1"}])

    args = argparse.Namespace(spark_home=str(spark_home), limit=10, json=True)

    assert cmd_bot_audit(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["summary"]["missing_id_count"] == 0


def test_bot_audit_accepts_explicit_legacy_audit_refs(tmp_path: Path) -> None:
    spark_home = tmp_path / ".spark"
    state_dir = spark_home / "state" / "spark-telegram-bot"
    for filename in (
        "final-answer-gate-audit.jsonl",
        "node-outbound-audit.jsonl",
        "route-confidence-audit.jsonl",
    ):
        _write_jsonl(
            state_dir / filename,
            [{"event": "legacy", "legacy_audit_ref": f"legacy:{filename}:1"}],
        )

    payload = build_bot_audit_payload(spark_home=spark_home, limit=10)

    assert payload["ok"] is True
    assert payload["summary"]["missing_id_count"] == 0
    for source in payload["sources"]:
        assert source["identifier_presence"]["legacy_audit_ref"] == 1


def test_cli_parser_exposes_bot_audit_command(tmp_path: Path) -> None:
    args = build_parser().parse_args(["bot", "audit", "--spark-home", str(tmp_path), "--json"])

    assert args.func is cmd_bot_audit
    assert args.bot_command == "audit"


def test_approval_classifier_treats_bot_audit_as_read_only() -> None:
    decision = approval_required_for_command(["spark", "bot", "audit"], CommandContext(non_interactive=True))

    assert decision.requires_approval is False
    assert decision.risk == "none"
