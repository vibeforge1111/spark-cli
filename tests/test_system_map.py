from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from spark_cli.cli import build_parser
from spark_cli.system_map import (
    build_authority_view,
    build_capability_catalog,
    build_memory_movement_index,
    collect_repo_metadata,
    count_safe_jsonl,
    inspect_builder_event_samples,
    inspect_builder_trace_health,
    inspect_builder_trace_groups,
    inspect_spawner_prd_auto_trace,
    inspect_telegram_final_answer_gate,
    safe_builder_event_value,
    summarize_pids,
    summarize_setup,
)


class SparkSystemMapTests(unittest.TestCase):
    def test_setup_summary_redacts_secret_names_and_profile_details(self) -> None:
        summary = summarize_setup(
            {
                "bundle": "telegram-starter",
                "modules": ["spark-telegram-bot"],
                "secret_keys": ["telegram.bot_token", "llm.zai.api_key"],
                "telegram_profiles": {
                    "main": {
                        "bot_token_secret": "telegram.bot_token",
                        "webhook_url": "http://127.0.0.1:9999/spawner-events",
                    }
                },
                "llm": {"roles": {"builder": {"provider": "zai", "auth_mode": "api_key"}}},
            }
        )

        encoded = json.dumps(summary)
        self.assertEqual(summary["secret_key_count"], 2)
        self.assertEqual(summary["telegram_profile_count"], 1)
        self.assertIn("key_based", encoded)
        self.assertNotIn("telegram.bot_token", encoded)
        self.assertNotIn("api_key", encoded)
        self.assertNotIn("webhook_url", encoded)

    def test_jsonl_counter_only_keeps_allowlisted_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"event_type": "route_selected", "summary": "private text"}),
                        json.dumps({"event_type": "route_selected", "token": "secret"}),
                        "{not-json",
                    ]
                ),
                encoding="utf-8",
            )
            summary = count_safe_jsonl(path)

        encoded = json.dumps(summary)
        self.assertEqual(summary["line_count"], 3)
        self.assertEqual(summary["parsed_count"], 2)
        self.assertEqual(summary["parse_errors"], 1)
        self.assertEqual(summary["safe_value_counts"]["event_type"]["route_selected"], 2)
        self.assertIn("summary", summary["top_keys"])
        self.assertNotIn("private text", encoded)
        self.assertNotIn("secret", encoded)

    def test_cross_system_trace_samples_keep_join_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            builder_home = root / "spark-intelligence"
            builder_home.mkdir()
            conn = sqlite3.connect(builder_home / "state.db")
            try:
                conn.execute("create table builder_events(request_id text, trace_ref text)")
                conn.execute(
                    "insert into builder_events(request_id, trace_ref) values (?, ?)",
                    ("req-1", "trace:spawner-prd:mission-1"),
                )
                conn.commit()
            finally:
                conn.close()

            final_gate = root / "final-answer-gate-audit.jsonl"
            final_gate.write_text(
                json.dumps(
                    {
                        "ts": "2026-05-10T13:00:00Z",
                        "event": "final_answer_gate",
                        "outcome": "delivered",
                        "builder_bridge_mode": "builder",
                        "builder_reply_preview": "private answer with token=secret",
                        "chat_id": "telegram:123456789",
                        "user_id": "telegram:987654321",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            spawner_trace = root / "prd-auto-trace.jsonl"
            spawner_trace.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "ts": "2026-05-10T13:00:01Z",
                                "event": "mission_started",
                                "requestId": "req-1",
                                "missionId": "mission-1",
                                "provider": "codex",
                                "stateDirectory": "C:/private/path",
                                "projectName": "private project",
                            }
                        ),
                        json.dumps(
                            {
                                "ts": "2026-05-10T13:00:02Z",
                                "event": "mission_waiting",
                                "requestId": "req-2",
                                "timeoutMs": 1000,
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            final_summary = inspect_telegram_final_answer_gate(final_gate)
            spawner_summary = inspect_spawner_prd_auto_trace(spawner_trace, builder_home=builder_home)

        encoded = json.dumps({"final": final_summary, "spawner": spawner_summary})
        self.assertEqual(final_summary["sample_count"], 1)
        self.assertEqual(final_summary["samples"][0]["outcome"], "delivered")
        self.assertEqual(final_summary["trace_join"]["status"], "missing_join_key")
        self.assertEqual(spawner_summary["join_keys"]["request_id_count"], 2)
        self.assertEqual(spawner_summary["join_keys"]["mission_id_count"], 1)
        self.assertEqual(spawner_summary["join_keys"]["trace_ref_count"], 0)
        self.assertEqual(spawner_summary["join_keys"]["derived_trace_ref_count"], 1)
        self.assertEqual(spawner_summary["derived_trace_contract"]["status"], "derived_available")
        self.assertEqual(spawner_summary["builder_request_overlap"]["matched_builder_request_id_count"], 1)
        self.assertEqual(spawner_summary["builder_trace_ref_overlap"]["matched_builder_trace_ref_count"], 1)
        self.assertEqual(spawner_summary["samples"][0]["requestId"], "req-1")
        self.assertNotIn("private answer", encoded)
        self.assertNotIn("token=secret", encoded)
        self.assertNotIn("telegram:123456789", encoded)
        self.assertNotIn("C:/private/path", encoded)
        self.assertNotIn("private project", encoded)

    def test_process_summary_omits_raw_command_args(self) -> None:
        summary = summarize_pids(
            {
                "spark-example": {
                    "module": "spark-example",
                    "pid": 123,
                    "command": ["python", "server.py", "--token", "secret-value"],
                }
            }
        )

        encoded = json.dumps(summary)
        self.assertEqual(summary[0]["command_arg_count"], 4)
        self.assertTrue(summary[0]["command_configured"])
        self.assertNotIn("secret-value", encoded)
        self.assertNotIn("--token", encoded)

    def test_memory_movement_index_uses_status_allowlist_and_counts_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder_home = Path(tmp) / "spark-intelligence"
            status_dir = builder_home / "artifacts" / "memory-movement-index"
            current_state = builder_home / "artifacts" / "spark-memory-kb" / "wiki" / "current-state"
            status_dir.mkdir(parents=True)
            current_state.mkdir(parents=True)
            (status_dir / "memory-movement-status.json").write_text(
                json.dumps(
                    {
                        "status": "supported",
                        "movement_counts": {"accepted": 3, "quarantined": 1},
                        "row_count": 4,
                        "authority": "current_state_authoritative",
                        "rows": [{"raw_text": "My private fact", "token": "telegram-token-value"}],
                        "subject": "human private subject",
                        "value": "private value",
                    }
                ),
                encoding="utf-8",
            )
            (current_state / "human-telegram-123-profile-preferred-name.md").write_text(
                "My private fact",
                encoding="utf-8",
            )

            index = build_memory_movement_index(builder_home)

        encoded = json.dumps(index)
        self.assertEqual(index["safe_status_export"]["status"]["status"], "supported")
        self.assertEqual(index["safe_status_export"]["status"]["movement_counts"]["accepted"], 3)
        self.assertEqual(index["memory_kb_artifacts"]["lane_counts"]["current_state"]["file_count"], 1)
        self.assertGreater(index["safe_status_export"]["raw_hint_key_count"], 0)
        self.assertNotIn("My private fact", encoded)
        self.assertNotIn("telegram-token-value", encoded)
        self.assertNotIn("human-telegram-123-profile-preferred-name", encoded)

    def test_capability_catalog_projects_labs_and_swarm_surfaces_without_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labs = root / "spark-domain-chip-labs"
            swarm = root / "spark-swarm"
            (labs / "docs" / "creator_system" / "schemas").mkdir(parents=True)
            (labs / "src" / "chip_labs").mkdir(parents=True)
            (labs / "runs" / "demo" / "benchmark").mkdir(parents=True)
            (labs / "runs" / "demo" / "swarm").mkdir(parents=True)
            (swarm / "config").mkdir(parents=True)
            (swarm / "schemas").mkdir(parents=True)
            (swarm / "packages" / "contracts" / "src").mkdir(parents=True)
            (swarm / "apps" / "api" / "src" / "collective").mkdir(parents=True)
            (swarm / "collective" / "demo").mkdir(parents=True)

            (labs / "spark-chip.json").write_text(
                json.dumps({"schema_version": "spark-chip.v1", "chip_name": "labs", "capabilities": []}),
                encoding="utf-8",
            )
            (labs / "docs" / "creator_system" / "schemas" / "creator-release-gate.schema.json").write_text(
                '{"private": "schema body should stay out"}',
                encoding="utf-8",
            )
            (labs / "src" / "chip_labs" / "creator_release_gate.py").write_text("# private implementation", encoding="utf-8")
            (labs / "runs" / "demo" / "created-artifact-manifest.json").write_text(
                '{"private": "run body should stay out"}',
                encoding="utf-8",
            )
            (labs / "runs" / "demo" / "benchmark" / "manifest.json").write_text(
                '{"private": "benchmark body should stay out"}',
                encoding="utf-8",
            )

            (swarm / "spark-chip.json").write_text(
                json.dumps({"schema_version": "spark-chip.v1", "chip_name": "swarm", "capabilities": []}),
                encoding="utf-8",
            )
            (swarm / "schemas" / "spark-specialization-path-agent-gate.schema.json").write_text(
                '{"private": "schema body should stay out"}',
                encoding="utf-8",
            )
            (swarm / "config" / "specialization-paths.json").write_text(
                json.dumps(
                    {
                        "paths": [
                            {
                                "key": "secret-key-should-stay-out",
                                "label": "Private label should stay out",
                                "category": "startup",
                                "primary_command": "secret command should stay out",
                                "specialization_defaults": {"evolution_mode": "review_required"},
                                "runtime": {"loop_kind": "benchmark"},
                                "benchmark": {"adapter": "startup-bench"},
                                "mutation": {"rollback_policy": "single_round_git_revert"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (swarm / "packages" / "contracts" / "src" / "index.ts").write_text("// private contracts", encoding="utf-8")
            (swarm / "apps" / "api" / "src" / "collective" / "sync-validation.ts").write_text(
                "// private validation",
                encoding="utf-8",
            )
            (swarm / "collective" / "demo" / "promotion-packet.json").write_text(
                '{"private": "packet body should stay out"}',
                encoding="utf-8",
            )

            catalog = build_capability_catalog([collect_repo_metadata(labs), collect_repo_metadata(swarm)])

        encoded = json.dumps(catalog)
        self.assertEqual(len(catalog["creator_system_surfaces"]), 1)
        self.assertEqual(len(catalog["specialization_path_surfaces"]), 1)
        labs_surface = catalog["creator_system_surfaces"][0]
        swarm_surface = catalog["specialization_path_surfaces"][0]
        cards_by_id = {card["id"]: card for card in catalog["capability_cards"]}
        self.assertEqual(labs_surface["schema_inventory"]["schema_count"], 1)
        self.assertEqual(labs_surface["creator_run_artifacts"]["run_count"], 1)
        self.assertEqual(labs_surface["creator_run_artifacts"]["artifact_presence_counts"]["created_manifest"], 1)
        self.assertEqual(swarm_surface["config"]["path_count"], 1)
        self.assertEqual(swarm_surface["config"]["category_counts"]["startup"], 1)
        self.assertEqual(swarm_surface["config"]["benchmark_adapter_counts"]["startup-bench"], 1)
        self.assertTrue(swarm_surface["publication_governance_sources"]["contract_types"]["exists"])
        self.assertEqual(swarm_surface["collective_artifacts"]["promotion_packet_count"], 1)
        self.assertEqual(cards_by_id["creator-system:spark-domain-chip-labs"]["status"], "local-artifacts")
        self.assertEqual(cards_by_id["specialization-path:spark-swarm"]["status"], "local-artifacts")
        self.assertIn("Network publication approval", cards_by_id["creator-system:spark-domain-chip-labs"]["blockers"][2])
        self.assertNotIn("schema body should stay out", encoded)
        self.assertNotIn("run body should stay out", encoded)
        self.assertNotIn("secret command should stay out", encoded)
        self.assertNotIn("secret-key-should-stay-out", encoded)

    def test_authority_view_projects_policy_contracts_without_secret_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            desktop = Path(tmp)
            cli_sandbox = desktop / "spark-cli" / "src" / "spark_cli" / "sandbox"
            telegram = desktop / "spark-telegram-bot" / "src"
            spawner_server = desktop / "spawner-ui" / "src" / "lib" / "server"
            browser_protocol = desktop / "spark-browser-extension" / "src" / "protocol"
            swarm_collective = desktop / "spark-swarm" / "apps" / "api" / "src" / "collective"
            labs_src = desktop / "spark-domain-chip-labs" / "src" / "chip_labs"
            for path in (cli_sandbox, telegram, spawner_server, browser_protocol, swarm_collective, labs_src):
                path.mkdir(parents=True)

            (cli_sandbox / "access.py").write_text(
                """
LEVEL5_ENV = {
    "SPARK_ALLOW_HIGH_AGENCY_WORKERS": "1",
    "SPARK_ALLOW_EXTERNAL_PROJECT_PATHS": "1",
    "SPARK_CODEX_SANDBOX": "danger-full-access",
}
DEFAULT_ACCESS_LEVEL = 4
DEFAULT_SANDBOX_LANE = "spark_workspace"
DEFAULT_CODEX_SANDBOX = "workspace-write"
LOWER_ACCESS_PROFILES = {
    1: {"id": "chat_memory", "label": "Chat", "activation_state": "chat"},
    2: {"id": "requested_missions", "label": "Missions", "activation_state": "missions"},
}
""",
                encoding="utf-8",
            )
            (cli_sandbox / "capabilities.py").write_text(
                """
FilesystemCapability = Literal["none", "workspace", "host"]
TOXIC_CAPABILITY_PAIRS = (
    ("secret_access", "network_write", "Secret access plus network write can exfiltrate credentials."),
)
""",
                encoding="utf-8",
            )
            (telegram / "accessPolicy.ts").write_text(
                """
export type SparkAccessProfile = 'chat' | 'builder' | 'agent' | 'developer' | 'operator';
export type SparkAccessRequirement = 'spawner_build' | 'external_research' | 'operating_system';
export function sparkAccessAllowsExternalResearch(profile: SparkAccessProfile): boolean {
  return profile === 'agent' || profile === 'developer' || profile === 'operator';
}
export function sparkAccessAllowsSpawnerBuilds(profile: SparkAccessProfile): boolean {
  return profile !== 'chat';
}
export function sparkAccessAllowsOperatingSystemWork(profile: SparkAccessProfile): boolean {
  return profile === 'developer' || profile === 'operator';
}
export function sparkAccessLevel(profile: SparkAccessProfile): number {
  switch (profile) {
    case 'chat': return 1;
    case 'agent': return 3;
    case 'developer': return 4;
    case 'operator': return 5;
    case 'builder':
    default: return 2;
  }
}
export function sparkLevel5RuntimeGuardrailsActive(): boolean { return true; }
const secretExample = 'telegram.bot_token';
""",
                encoding="utf-8",
            )
            (spawner_server / "access-execution-lanes.ts").write_text(
                """
export type AccessExecutionLaneId = 'spark_workspace' | 'docker' | 'level5_operator';
export type AccessRunPolicy = 'auto_safe' | 'auto_read_only' | 'confirm_once' | 'explicit_opt_in';
""",
                encoding="utf-8",
            )
            (spawner_server / "access-execution-actions.ts").write_text(
                """
export const ACCESS_EXECUTION_ACTIONS = {
  workspace_setup: {
    id: 'workspace_setup',
    laneId: 'spark_workspace',
    displayCommand: 'spark access setup',
    runPolicy: 'auto_safe',
  },
  level5_enable: {
    id: 'level5_enable',
    laneId: 'level5_operator',
    displayCommand: 'spark access setup --level 5 --enable-high-agency',
    runPolicy: 'explicit_opt_in',
    confirmation: 'Enable whole-computer operator mode',
    rollback: 'spark access disable-level5',
  }
};
""",
                encoding="utf-8",
            )
            (spawner_server / "high-agency-workers.ts").write_text(
                "const keys = ['SPARK_ALLOW_HIGH_AGENCY_WORKERS', 'SPARK_CODEX_SANDBOX'];\n",
                encoding="utf-8",
            )
            (spawner_server / "mission-control-access.ts").write_text(
                """
export type MissionControlAccessMode = 'hosted' | 'lan' | 'local-only';
const defaults = { defaultPayload: 'status-metadata', privatePayloadsStayLocal: true };
""",
                encoding="utf-8",
            )
            (browser_protocol / "constants.js").write_text(
                """
export const RISK_CLASSES = { READ_ONLY: "read_only", HIGH_RISK_ACTION: "high_risk_action" };
export const APPROVAL_MODES = { NOT_REQUIRED: "not_required", ASK_ONCE: "ask_once" };
export const HOOK_DEFINITIONS = {
  status: { risk_class: RISK_CLASSES.READ_ONLY, approval_mode: APPROVAL_MODES.NOT_REQUIRED, requires_origin_scope: false },
  click: { risk_class: RISK_CLASSES.HIGH_RISK_ACTION, approval_mode: APPROVAL_MODES.ASK_ONCE, requires_origin_scope: true }
};
""",
                encoding="utf-8",
            )
            (browser_protocol / "policy.js").write_text(
                "export function classifySensitiveSurface() {}\n",
                encoding="utf-8",
            )
            (swarm_collective / "sync-validation.ts").write_text(
                """
const REQUIRED_PUBLICATION_WORKFLOW = "spark-insight-review"
const REQUIRED_PUBLICATION_CHECKS = ["spark-insight-schema", "spark-insight-secrets"] as const
""",
                encoding="utf-8",
            )
            for rel_path in (
                "creator_release_gate.py",
                "creator_swarm_collective.py",
                "operator_review.py",
                "product_runtime_review.py",
            ):
                (labs_src / rel_path).write_text("# gate\n", encoding="utf-8")

            view = build_authority_view(
                desktop,
                {"telegram_profile_count": 1, "primary_telegram_profile": "main"},
            )
            encoded = json.dumps(view)

            self.assertEqual(view["default_access_level_hint"], 4)
            self.assertEqual(view["cli_access"]["default_sandbox_lane"], "spark_workspace")
            self.assertEqual(view["cli_capability_policy"]["toxic_pair_count"], 1)
            self.assertEqual(view["telegram_profile_count"], 5)
            self.assertEqual(view["configured_telegram_profile_count"], 1)
            self.assertIn("developer", view["telegram_access_policy"]["allow_matrix"]["operating_system"])
            self.assertEqual(view["spawner_execution_policy"]["confirmation_gated_action_count"], 1)
            self.assertEqual(view["browser_authority"]["risk_class_counts"]["high_risk_action"], 1)
            self.assertEqual(
                view["public_output_authority"]["required_publication_checks"],
                ["spark-insight-schema", "spark-insight-secrets"],
            )
            self.assertEqual(view["guardrail_summary"]["publication_checks_required"], 2)
            self.assertNotIn("telegram.bot_token", encoded)

    def test_builder_event_samples_omit_event_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder_home = Path(tmp) / "spark-intelligence"
            builder_home.mkdir()
            conn = sqlite3.connect(builder_home / "state.db")
            try:
                conn.execute(
                    """
                    create table builder_events(
                        event_id text,
                        created_at text,
                        event_type text,
                        status text,
                        severity text,
                        component text,
                        request_id text,
                        trace_ref text,
                        correlation_id text,
                        parent_event_id text,
                        target_surface text,
                        evidence_lane text,
                        truth_kind text,
                        summary text,
                        facts_json text,
                        provenance_json text
                    )
                    """
                )
                conn.execute(
                    """
                    insert into builder_events(
                        event_id, created_at, event_type, status, severity, component,
                        request_id, trace_ref, correlation_id, parent_event_id,
                        target_surface, evidence_lane, truth_kind, summary, facts_json, provenance_json
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "evt-1",
                        "2026-05-10T13:00:00Z",
                        "route_selected",
                        "succeeded",
                        "info",
                        "router",
                        "req-1",
                        "trace-1",
                        "corr-1",
                        None,
                        "telegram",
                        "route",
                        "observed",
                        "private user message",
                        json.dumps({"token": "secret", "message": "private"}),
                        json.dumps({"source": "private"}),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            samples = inspect_builder_event_samples(builder_home)

        encoded = json.dumps(samples)
        self.assertEqual(samples["sample_count"], 1)
        self.assertEqual(samples["events"][0]["event_id"], "evt-1")
        self.assertEqual(samples["events"][0]["trace_ref"], "trace-1")
        self.assertEqual(samples["top_trace_refs"][0]["trace_ref"], "trace-1")
        self.assertNotIn("private user message", encoded)
        self.assertNotIn("secret", encoded)
        self.assertNotIn("facts_json", encoded)

    def test_builder_trace_groups_omit_event_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder_home = Path(tmp) / "spark-intelligence"
            builder_home.mkdir()
            conn = sqlite3.connect(builder_home / "state.db")
            try:
                conn.execute(
                    """
                    create table builder_events(
                        event_id text,
                        created_at text,
                        event_type text,
                        status text,
                        severity text,
                        component text,
                        request_id text,
                        trace_ref text,
                        correlation_id text,
                        parent_event_id text,
                        target_surface text,
                        evidence_lane text,
                        truth_kind text,
                        summary text,
                        facts_json text,
                        provenance_json text
                    )
                    """
                )
                rows = [
                    (
                        "evt-1",
                        "2026-05-10T13:00:00Z",
                        "intent_committed",
                        "recorded",
                        "info",
                        "frame",
                        "req-1",
                        "trace-1",
                        "corr",
                        None,
                    ),
                    (
                        "evt-2",
                        "2026-05-10T13:01:00Z",
                        "route_selected",
                        "succeeded",
                        "info",
                        "router",
                        "req-1",
                        "trace-1",
                        "corr",
                        "evt-1",
                    ),
                    (
                        "evt-3",
                        "2026-05-10T13:02:00Z",
                        "final_answer_checked",
                        "succeeded",
                        "info",
                        "answer",
                        "req-2",
                        "trace-2",
                        "corr",
                        "missing-parent",
                    ),
                ]
                for row in rows:
                    conn.execute(
                        """
                        insert into builder_events(
                            event_id, created_at, event_type, status, severity, component,
                            request_id, trace_ref, correlation_id, parent_event_id,
                            target_surface, evidence_lane, truth_kind, summary, facts_json, provenance_json
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            *row,
                            "telegram",
                            "route",
                            "observed",
                            "private trace summary",
                            json.dumps({"message": "private trace body"}),
                            json.dumps({"source": "private provenance"}),
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

            groups = inspect_builder_trace_groups(builder_home, group_limit=2, events_per_trace=5)

        encoded = json.dumps(groups)
        by_trace = {group["trace_ref"]: group for group in groups["groups"]}
        self.assertEqual(groups["group_count"], 2)
        self.assertEqual(by_trace["trace-1"]["event_count"], 2)
        self.assertEqual([event["event_id"] for event in by_trace["trace-1"]["events"]], ["evt-1", "evt-2"])
        self.assertEqual(by_trace["trace-1"]["topology"]["root_event_count"], 1)
        self.assertEqual(by_trace["trace-1"]["topology"]["parent_link_count"], 1)
        self.assertEqual(by_trace["trace-1"]["topology"]["orphan_parent_event_count"], 0)
        self.assertEqual(by_trace["trace-1"]["topology"]["edge_sample"][0]["parent_event_id"], "evt-1")
        self.assertEqual(by_trace["trace-1"]["topology"]["edge_sample"][0]["child_event_id"], "evt-2")
        self.assertEqual(by_trace["trace-2"]["topology"]["orphan_parent_event_count"], 1)
        self.assertFalse(by_trace["trace-2"]["topology"]["edge_sample"][0]["parent_exists"])
        self.assertNotIn("private trace summary", encoded)
        self.assertNotIn("private trace body", encoded)
        self.assertNotIn("provenance_json", encoded)

    def test_builder_event_identifiers_redact_identity_bearing_refs(self) -> None:
        raw = "trace:agent:human:telegram:8319079055:telegram:13152322"
        redacted = safe_builder_event_value("trace_ref", raw)

        self.assertIsInstance(redacted, str)
        self.assertTrue(str(redacted).startswith("trace_ref:redacted:"))
        self.assertNotIn("8319079055", str(redacted))
        self.assertEqual(safe_builder_event_value("trace_ref", "trace-1"), "trace-1")

    def test_builder_trace_health_reports_counts_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder_home = Path(tmp) / "spark-intelligence"
            builder_home.mkdir()
            conn = sqlite3.connect(builder_home / "state.db")
            try:
                conn.execute(
                    """
                    create table builder_events(
                        event_id text,
                        created_at text,
                        event_type text,
                        status text,
                        severity text,
                        component text,
                        target_surface text,
                        request_id text,
                        trace_ref text,
                        parent_event_id text,
                        summary text,
                        facts_json text
                    )
                    """
                )
                rows = [
                    ("evt-parent", "recorded", "medium", "router", "telegram", "req-1", "trace-1", None),
                    ("evt-child", "recorded", "medium", "router", "telegram", "req-1", "trace-1", "evt-parent"),
                    ("evt-orphan", "recorded", "medium", "router", "telegram", "req-2", "trace-2", "missing-parent"),
                    ("evt-open", "open", "high", "answer", "telegram", None, None, None),
                ]
                created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                for event_id, status, severity, component, target_surface, request_id, trace_ref, parent_id in rows:
                    conn.execute(
                        """
                        insert into builder_events(
                            event_id, created_at, event_type, status, severity,
                            component, target_surface, request_id, trace_ref, parent_event_id, summary, facts_json
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            created_at,
                            "route_selected",
                            status,
                            severity,
                            component,
                            target_surface,
                            request_id,
                            trace_ref,
                            parent_id,
                            "private health summary",
                            json.dumps({"message": "private health body"}),
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

            health = inspect_builder_trace_health(builder_home)

        encoded = json.dumps(health)
        self.assertEqual(health["row_count"], 4)
        self.assertEqual(health["missing_trace_ref_count"], 1)
        self.assertEqual(health["trace_group_count"], 2)
        self.assertEqual(health["orphan_parent_event_id_count"], 1)
        self.assertEqual(health["high_severity_open_count"], 1)
        self.assertEqual(health["orphan_parent_event_sources"]["rows"][0]["component"], "router")
        self.assertEqual(health["orphan_parent_event_sources"]["rows"][0]["event_count"], 1)
        self.assertEqual(health["missing_trace_ref_sources"]["rows"][0]["component"], "answer")
        self.assertEqual(health["missing_trace_ref_sources"]["rows"][0]["event_count"], 1)
        self.assertEqual(health["recent_windows"][0]["row_count"], 4)
        self.assertEqual(health["recent_windows"][0]["missing_trace_ref_count"], 1)
        self.assertIn("missing_trace_refs", health["health_flags"])
        self.assertNotIn("private health summary", encoded)
        self.assertNotIn("private health body", encoded)

    def test_os_compile_command_writes_redacted_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = root / "Desktop"
            spark_home = root / ".spark"
            state = spark_home / "state"
            repo = desktop / "spark-example"
            out = root / "out"
            desktop.mkdir()
            state.mkdir(parents=True)
            repo.mkdir()

            registry = root / "registry.json"
            registry.write_text(
                json.dumps(
                    {
                        "modules": {
                            "spark-example": {
                                "source": "https://example.test/spark-example",
                                "summary": "Example module",
                                "blessed": True,
                            }
                        },
                        "bundles": {"starter": {"modules": ["spark-example"]}},
                    }
                ),
                encoding="utf-8",
            )
            (state / "installed.json").write_text(
                json.dumps({"spark-example": {"path": str(repo), "kind": "runtime", "plane": "runtime"}}),
                encoding="utf-8",
            )
            (state / "setup.json").write_text(
                json.dumps(
                    {
                        "bundle": "starter",
                        "modules": ["spark-example"],
                        "secret_keys": ["telegram.bot_token"],
                        "telegram_profiles": {"main": {"webhook_url": "http://127.0.0.1/hook"}},
                    }
                ),
                encoding="utf-8",
            )
            (state / "pids.json").write_text("{}", encoding="utf-8")
            (repo / "spark.toml").write_text(
                """
[module]
name = "spark-example"
version = "0.1.0"
kind = "runtime"
plane = "runtime"
description = "Example module"

[provides]
capabilities = ["spark.example"]

[needs]
modules = []
capabilities = []
secrets = ["example.secret"]

[claims]
secrets = []
ports = []
routes = []
""".strip(),
                encoding="utf-8",
            )

            args = build_parser().parse_args(
                [
                    "os",
                    "compile",
                    "--desktop",
                    str(desktop),
                    "--spark-home",
                    str(spark_home),
                    "--registry",
                    str(registry),
                    "--out",
                    str(out),
                    "--json",
                ]
            )
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = args.func(args)

            summary = json.loads(stdout.getvalue())
            system_map = json.loads((out / "system-map.json").read_text(encoding="utf-8"))
            output_text = "\n".join(path.read_text(encoding="utf-8") for path in out.glob("*") if path.is_file())

            self.assertEqual(exit_code, 0)
            self.assertEqual(summary["modules"], 1)
            self.assertEqual(system_map["setup"]["secret_key_count"], 1)
            self.assertTrue((out / "authority-view.json").exists())
            self.assertTrue((out / "capability-catalog.json").exists())
            self.assertTrue((out / "trace-index.json").exists())
            self.assertTrue((out / "memory-movement-index.json").exists())
            self.assertNotIn("telegram.bot_token", output_text)
            self.assertNotIn("webhook_url", output_text)

            capability_args = build_parser().parse_args(
                [
                    "os",
                    "capabilities",
                    "--desktop",
                    str(desktop),
                    "--spark-home",
                    str(spark_home),
                    "--registry",
                    str(registry),
                    "--json",
                ]
            )
            capability_stdout = StringIO()
            with redirect_stdout(capability_stdout):
                capability_exit_code = capability_args.func(capability_args)
            capability_summary = json.loads(capability_stdout.getvalue())

            self.assertEqual(capability_exit_code, 0)
            self.assertEqual(capability_summary["schema_version"], "spark.os_capabilities.summary.v0")
            self.assertEqual(capability_summary["card_count"], 0)

            authority_args = build_parser().parse_args(
                [
                    "os",
                    "authority",
                    "--desktop",
                    str(desktop),
                    "--spark-home",
                    str(spark_home),
                    "--registry",
                    str(registry),
                    "--json",
                ]
            )
            authority_stdout = StringIO()
            with redirect_stdout(authority_stdout):
                authority_exit_code = authority_args.func(authority_args)
            authority_summary = json.loads(authority_stdout.getvalue())

            self.assertEqual(authority_exit_code, 0)
            self.assertEqual(authority_summary["schema_version"], "spark.os_authority.summary.v0")
            self.assertIn("guardrail_summary", authority_summary)


if __name__ == "__main__":
    unittest.main()
