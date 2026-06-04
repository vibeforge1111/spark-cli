from __future__ import annotations

import hashlib
import ast
import json
import re
import sqlite3
import subprocess
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import tomllib

SYSTEM_MAP_SCHEMA = "spark.system_map.compiled.v0"
AUTHORITY_VIEW_SCHEMA = "spark.authority_view.compiled.v0"
CAPABILITY_CATALOG_SCHEMA = "spark.capability_catalog.compiled.v0"
CAPABILITY_CARD_SCHEMA = "spark.capability_card.v1"
CAPABILITY_PROOF_VERDICTS_SCHEMA = "spark.capability_proof_verdicts.v1"
TRACE_INDEX_SCHEMA = "spark.trace_index.compiled.v0"
REVIEW_CANDIDATES_SCHEMA = "spark.os_review_candidates.compiled.v0"
MEMORY_MOVEMENT_INDEX_SCHEMA = "spark.memory_movement_index.compiled.v0"
MEMORY_REVIEW_QUEUE_SCHEMA = "spark.memory_review_queue.v1"
REPO_BOARD_SCHEMA = "spark.repo_board.compiled.v0"
VOICE_SURFACE_SCHEMA = "spark.voice_surface_view.compiled.v0"
OPERATING_COCKPIT_SCHEMA = "spark.operating_cockpit.compiled.v0"
DUPLICATE_TRUTHS_SCHEMA = "spark.duplicate_truths.compiled.v0"

SPARK_REPO_NAME_HINTS = ("spark", "domain-chip", "spawner-ui")

CONTRACT_FILE_HINTS = (
    "docs/AGENT_OPERATING_CONTEXT_AND_DRIFT_CONTROL.md",
    "docs/SPARK_UPGRADE_LEDGER.yaml",
    "docs/SPARK_INTEGRATION_CONTRACT.md",
    "docs/BROWSER_HOOK_CONTRACT_V1.md",
    "docs/reference/SPARK_PROVENANCE_AND_MUTATION_LEDGER_DOCTRINE.md",
    "SPARK_AGENT_HARNESS_V1.md",
    "docs/wiki/02_SPARK_SYSTEM_MAP.md",
    "docs/SPARK_SKILL_GRAPH_STANDARD.md",
    "schemas/spark-skill-manifest.v1.schema.json",
    "spark-skill-manifest.json",
    "spark-chip.json",
    "spark.toml",
)

BUILDER_TABLES_OF_INTEREST = (
    "builder_events",
    "event_log",
    "delivery_registry",
    "config_mutation_audit",
    "config_mutation_log",
    "provenance_mutation_log",
    "quarantine_records",
    "contradiction_records",
    "policy_gate_records",
    "memory_lane_records",
    "pending_task_records",
    "procedural_lesson_records",
    "observer_packet_records",
    "observer_handoff_records",
)

SAFE_JSONL_COUNT_KEYS = (
    "schema_version",
    "event_type",
    "type",
    "kind",
    "status",
    "drift_type",
    "decision",
    "route",
    "surface",
)

SENSITIVE_KEY_NAME_HINTS = (
    "api_key",
    "authorization",
    "bot_token",
    "chat_id",
    "cookie",
    "secret",
    "token",
    "transcript",
    "user_id",
)

OWNER_SURFACES = {
    "spark-cli": "installer, compiler, authority, browser-use, release metadata",
    "spark-intelligence-builder": "AOC, black box, memory orchestration, operating-panel read model",
    "spark-telegram-bot": "Telegram field console",
    "spawner-ui": "mission execution and mission trace",
    "spark-command-center": "Spark Operating Cockpit shell",
    "spark-memory-quality-dashboard": "Cockpit memory review source module",
    "domain-chip-memory": "durable memory substrate and movement discipline",
    "spark-voice-comms": "voice ingress/egress surface",
    "spark-domain-chip-labs": "capability lab, benchmark packets, review gates",
    "spark-swarm": "specialization paths and publication governance",
    "spark-skill-graphs": "specialist library and routing substrate",
    "spark-intelligence-systems": "doctrine, runbook, prototype read model",
}

CORE_REPOS = set(OWNER_SURFACES)

TRACE_REPAIR_COMPONENT_OWNERS = {
    "agent_operating_context": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "Agent Operating Context event emission",
    },
    "attachment_snapshot": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "attachment snapshot event emission",
    },
    "attachments_cli": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "attachments CLI event emission",
    },
    "browser_cli": {
        "owner_repo": "spark-cli",
        "source_module": "browser-use CLI event emission",
    },
    "config_manager": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "config manager event emission",
    },
    "direct_provider": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "direct provider bridge event emission",
    },
    "doctor_cli": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "doctor CLI event emission",
    },
    "memory_doctor": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "memory doctor event emission",
    },
    "memory_orchestrator": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "memory orchestrator event emission",
    },
    "researcher_bridge": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "researcher bridge event emission",
    },
    "stop_ship_checks": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "stop-ship check event emission",
    },
    "swarm_bridge": {
        "owner_repo": "spark-intelligence-builder",
        "source_module": "Swarm bridge event emission",
    },
    "telegram_runtime": {
        "owner_repo": "spark-telegram-bot",
        "source_module": "Telegram runtime event emission",
    },
}

SAFE_TELEGRAM_FINAL_ANSWER_FIELDS = (
    "ts",
    "event",
    "outcome",
    "builder_bridge_mode",
    "builder_routing_decision",
    "fallback_route",
    "latest_intent_preserved",
    "builder_reply_length",
    "suppression_reason",
)

SAFE_TELEGRAM_OUTBOUND_FIELDS = (
    "ts",
    "event",
    "text_length",
)

SAFE_SPAWNER_PRD_TRACE_FIELDS = (
    "ts",
    "event",
    "requestId",
    "missionId",
    "traceRef",
    "trace_ref",
    "provider",
    "buildMode",
    "timeoutMs",
)

SAFE_MEMORY_STATUS_KEYS = {
    "status",
    "reason",
    "configured_module",
    "contract_name",
    "authority",
    "movement_states",
    "movement_counts",
    "row_count",
    "record_counts",
    "source_family_counts",
    "authority_counts",
    "non_override_rules",
}

LABS_CREATOR_SURFACE_FILES = {
    "release_gate": "src/chip_labs/creator_release_gate.py",
    "swarm_collective": "src/chip_labs/creator_swarm_collective.py",
    "operator_review": "src/chip_labs/operator_review.py",
    "product_runtime_review": "src/chip_labs/product_runtime_review.py",
}

LABS_CREATOR_RUN_ARTIFACTS = {
    "created_manifest": "created-artifact-manifest.json",
    "domain_chip_manifest": "domain-chip/chip.manifest.json",
    "benchmark_manifest": "benchmark/manifest.json",
    "specialization_path_manifest": "specialization-path/path.manifest.json",
    "loop_policy": "autoloop/policy.json",
    "swarm_contribution": "swarm/contribution_packet.json",
}

CREATOR_REQUIRED_PROOF_LABELS = {
    "gate": "normalized_gate_verdict",
    "benchmark": "benchmark_pass_fail_verdict",
    "privacy": "privacy_review_verdict",
    "rollback": "rollback_ref",
    "authority": "authority_scope_verdict",
    "publication": "publication_approval",
}

SWARM_PUBLICATION_GOVERNANCE_FILES = {
    "contract_types": "packages/contracts/src/index.ts",
    "service_reads": "apps/api/src/collective/service-reads.ts",
    "sync_validation": "apps/api/src/collective/sync-validation.ts",
    "publication_signatures": "apps/api/src/collective/publication-proof-signatures.ts",
    "github_delivery_support": "apps/api/src/collective/delivery-github-support.ts",
    "pull_request_delivery": "apps/api/src/collective/pull-request-delivery.ts",
    "github_insight_review_template": "templates/github-insight-review/README.md",
}

SWARM_CAPABILITY_VERDICT_FILES = {
    "publication_approval": "templates/creator-system-network-proposal/publication-approval.placeholder.json",
    "github_ruleset_review": "templates/creator-system-network-proposal/github-ruleset-review.current.json",
    "hosted_runtime_ui_proof": "templates/creator-system-network-proposal/hosted-runtime-ui-proof.template.json",
}

SPECIALIZATION_REQUIRED_PROOF_LABELS = {
    "benchmark": "benchmark_pass_fail_verdict",
    "publication": "publication_approval_verdict",
    "privacy": "privacy_review_verdict",
    "rollback": "rollback_ref",
    "authority": "authority_scope_verdict",
    "trace": "trace_or_proof_ref",
}

SAFE_BUILDER_EVENT_SAMPLE_COLUMNS = (
    "event_id",
    "created_at",
    "event_type",
    "status",
    "severity",
    "component",
    "request_id",
    "trace_ref",
    "correlation_id",
    "parent_event_id",
    "target_surface",
    "evidence_lane",
    "truth_kind",
)

BUILDER_EVENT_IDENTIFIER_COLUMNS = {
    "request_id",
    "trace_ref",
    "correlation_id",
    "parent_event_id",
}

RAW_MEMORY_KEY_HINTS = (
    "content",
    "evidence",
    "fact",
    "message",
    "object",
    "predicate",
    "prompt",
    "raw",
    "response",
    "row",
    "secret",
    "subject",
    "text",
    "token",
    "value",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"read_json_failed: {type(exc).__name__}: {exc}"


def read_toml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")), None
    except (tomllib.TOMLDecodeError, OSError) as exc:
        return None, f"read_toml_failed: {type(exc).__name__}: {exc}"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_string(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def safe_auth_mode(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.lower() in {"api_key", "api-key", "apikey"}:
        return "key_based"
    return value


def summarize_setup(setup: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(setup, dict):
        return {"available": False}

    llm = as_dict(setup.get("llm"))
    roles: dict[str, Any] = {}
    for role, payload in as_dict(llm.get("roles")).items():
        role_payload = as_dict(payload)
        roles[str(role)] = {
            "provider": role_payload.get("provider"),
            "bot_provider": role_payload.get("bot_provider"),
            "model": role_payload.get("model"),
            "auth_mode": safe_auth_mode(role_payload.get("auth_mode")),
            "base_url_configured": bool(role_payload.get("base_url")),
        }

    telegram_profiles = as_dict(setup.get("telegram_profiles"))
    return {
        "available": True,
        "bundle": setup.get("bundle"),
        "modules": as_list(setup.get("modules")),
        "configured_at": setup.get("configured_at"),
        "builder_home": setup.get("builder_home"),
        "secret_key_count": len(as_list(setup.get("secret_keys"))),
        "telegram_profile_count": len(telegram_profiles),
        "primary_telegram_profile": setup.get("primary_telegram_profile"),
        "llm_roles": roles,
        "redaction": "secret names, token values, env paths, webhooks, and raw profile metadata omitted",
    }


def summarize_pids(pids: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(pids, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key, payload in sorted(pids.items()):
        item = as_dict(payload)
        command = item.get("command")
        rows.append(
            {
                "id": key,
                "module": item.get("module"),
                "profile": item.get("profile"),
                "pid": item.get("pid"),
                "command_configured": bool(command),
                "command_arg_count": len(command) if isinstance(command, list) else None,
                "path": item.get("path"),
                "started_at": item.get("started_at"),
                "ready_check": item.get("ready_check"),
            }
        )
    return rows


def discover_repo_paths(desktop: Path, installed: dict[str, Any] | None) -> list[Path]:
    candidates: dict[str, Path] = {}
    if desktop.exists():
        try:
            children = list(desktop.iterdir())
        except OSError:
            children = []
        for child in children:
            if child.is_dir() and any(hint in child.name.lower() for hint in SPARK_REPO_NAME_HINTS):
                candidates[str(child.resolve()).lower()] = child

    for payload in as_dict(installed).values():
        path = as_dict(payload).get("path")
        if isinstance(path, str) and path.strip():
            resolved = Path(path).expanduser()
            candidates[str(resolved.resolve()).lower() if resolved.exists() else str(resolved).lower()] = resolved
    return sorted(candidates.values(), key=lambda p: str(p).lower())


def git_summary(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists():
        return {"available": False}
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return {"available": False, "head_short": None}
    return {"available": True, "head_short": result.stdout.strip() if result.returncode == 0 else None}


def run_git(path: Path, args: list[str], timeout: int = 3) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return 1, ""
    return result.returncode, result.stdout.strip()


def parse_branch_status(line: str) -> dict[str, Any]:
    branch = ""
    upstream = None
    ahead = 0
    behind = 0
    if line.startswith("## "):
        body = line[3:]
        no_commit_prefix = "No commits yet on "
        if body.startswith(no_commit_prefix):
            branch = body[len(no_commit_prefix) :].split(" ", 1)[0]
        elif "..." in body:
            branch, rest = body.split("...", 1)
            upstream = rest.split(" ", 1)[0] if rest else None
        else:
            branch = body.split(" ", 1)[0]
        ahead_match = re.search(r"ahead\s+(\d+)", body)
        behind_match = re.search(r"behind\s+(\d+)", body)
        ahead = int(ahead_match.group(1)) if ahead_match else 0
        behind = int(behind_match.group(1)) if behind_match else 0
    return {"branch": branch, "upstream": upstream, "ahead": ahead, "behind": behind}


def git_board_status(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists():
        return {
            "available": False,
            "branch": None,
            "upstream": None,
            "ahead": 0,
            "behind": 0,
            "dirty_tracked_count": 0,
            "untracked_count": 0,
            "last_commit": None,
            "head_commit": None,
        }

    code, status = run_git(path, ["status", "--short", "--branch"])
    lines = status.splitlines() if code == 0 and status else []
    branch_status = parse_branch_status(lines[0] if lines else "")
    dirty_tracked_count = 0
    untracked_count = 0
    for line in lines[1:]:
        if line.startswith("??"):
            untracked_count += 1
        elif line.strip():
            dirty_tracked_count += 1

    code, commit = run_git(path, ["log", "-1", "--format=%h %cI"])
    head_code, head_commit = run_git(path, ["rev-parse", "HEAD"])
    return {
        "available": True,
        "branch": branch_status["branch"] or None,
        "upstream": branch_status["upstream"],
        "ahead": branch_status["ahead"],
        "behind": branch_status["behind"],
        "dirty_tracked_count": dirty_tracked_count,
        "untracked_count": untracked_count,
        "last_commit": commit if code == 0 and commit else None,
        "head_commit": head_commit if head_code == 0 and head_commit else None,
    }


def git_remote_branch_head(path: Path, branch: str | None) -> str | None:
    if not branch:
        return None
    code, commit = run_git(path, ["rev-parse", f"refs/remotes/origin/{branch}"])
    if code == 0 and commit:
        return commit.strip()
    return None


def collect_repo_metadata(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"name": path.name, "path": str(path), "exists": path.exists()}
    if not path.exists():
        return record

    toml_data, toml_error = read_toml(path / "spark.toml")
    if toml_data:
        module = as_dict(toml_data.get("module"))
        provides = as_dict(toml_data.get("provides"))
        needs = as_dict(toml_data.get("needs"))
        claims = as_dict(toml_data.get("claims"))
        profiles = as_dict(toml_data.get("profiles"))
        record["spark_toml"] = {
            "module_name": module.get("name"),
            "version": module.get("version"),
            "kind": module.get("kind"),
            "plane": module.get("plane"),
            "description": module.get("description"),
            "homepage": module.get("homepage"),
            "provides_capabilities": as_list(provides.get("capabilities")),
            "needs_modules": as_list(needs.get("modules")),
            "needs_capability_count": len(as_list(needs.get("capabilities"))),
            "needs_secret_count": len(as_list(needs.get("secrets"))),
            "claimed_secret_count": len(as_list(claims.get("secrets"))),
            "claimed_port_count": len(as_list(claims.get("ports"))),
            "claimed_route_count": len(as_list(claims.get("routes"))),
            "profile_names": sorted(profiles.keys()),
        }
    elif toml_error != "missing":
        record["spark_toml_error"] = toml_error

    chip_data, chip_error = read_json(path / "spark-chip.json")
    if isinstance(chip_data, dict):
        record["spark_chip"] = {
            "schema_version": chip_data.get("schema_version"),
            "io_protocol": chip_data.get("io_protocol"),
            "chip_name": chip_data.get("chip_name"),
            "domain": chip_data.get("domain"),
            "description": chip_data.get("description"),
            "capabilities": as_list(chip_data.get("capabilities")),
            "command_count": len(as_dict(chip_data.get("commands"))),
            "task_topics": as_list(chip_data.get("task_topics")),
            "frontier": as_dict(chip_data.get("frontier")),
        }
    elif chip_error != "missing":
        record["spark_chip_error"] = chip_error

    manifest_data, manifest_error = read_json(path / "spark-skill-manifest.json")
    if isinstance(manifest_data, dict):
        record["skill_manifest"] = {
            "schema_version": manifest_data.get("schema_version"),
            "generated_at": manifest_data.get("generated_at"),
            "stats": as_dict(manifest_data.get("stats")),
            "category_count": len(as_dict(manifest_data.get("categories"))),
        }
    elif manifest_error != "missing":
        record["skill_manifest_error"] = manifest_error

    record["contract_files"] = [rel for rel in CONTRACT_FILE_HINTS if (path / rel).exists()]
    record["git"] = git_summary(path)
    return record


def repo_ids(repo: dict[str, Any]) -> set[str]:
    toml = as_dict(repo.get("spark_toml"))
    module_name = toml.get("module_name")
    return {module_name.strip()} if isinstance(module_name, str) and module_name.strip() else set()


def summarize_installed(installed: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(installed, dict):
        return {}
    out = {}
    for module_id, payload in installed.items():
        item = as_dict(payload)
        out[module_id] = {
            "path": item.get("path"),
            "version": item.get("version"),
            "kind": item.get("kind"),
            "plane": item.get("plane"),
            "source": item.get("source"),
            "summary": item.get("summary"),
            "blessed": item.get("blessed"),
            "installed_at": item.get("installed_at"),
            "updated_at": item.get("updated_at"),
            "bundle_provenance": item.get("bundle_provenance"),
            "registry_source": item.get("registry_source"),
            "registry_commit": item.get("registry_commit"),
            "last_install_status": as_dict(item.get("last_install")).get("status"),
            "last_update_status": as_dict(item.get("last_update")).get("status"),
        }
    return out


def summarize_registry(registry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(registry, dict):
        return {"modules": {}, "bundles": {}}
    modules = {}
    for module_id, payload in as_dict(registry.get("modules")).items():
        item = as_dict(payload)
        modules[module_id] = {
            "source": item.get("source"),
            "commit": item.get("commit"),
            "require_signed_commit": item.get("require_signed_commit"),
            "blessed": item.get("blessed"),
            "summary": item.get("summary"),
            "attestation_type": as_dict(item.get("attestation")).get("type"),
        }
    bundles = {}
    for bundle_id, payload in as_dict(registry.get("bundles")).items():
        item = as_dict(payload)
        bundles[bundle_id] = {"modules": as_list(item.get("modules")), "summary": item.get("summary")}
    return {"modules": modules, "bundles": bundles}


def inspect_builder_state_db(builder_home: Path) -> dict[str, Any]:
    db_path = builder_home / "state.db"
    out: dict[str, Any] = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "redaction": "table names and row counts only; no row contents read",
    }
    if not db_path.exists():
        return out

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table' order by name")]
            out["table_count"] = len(tables)
            out["tables_of_interest"] = {}
            for table in BUILDER_TABLES_OF_INTEREST:
                if table not in tables:
                    out["tables_of_interest"][table] = {"exists": False}
                    continue
                count = conn.execute(f'select count(*) from "{table}"').fetchone()[0]
                out["tables_of_interest"][table] = {"exists": True, "row_count": int(count)}
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def summarize_upgrade_ledger(repo_paths: list[Path]) -> dict[str, Any]:
    for repo in repo_paths:
        candidate = repo / "docs" / "SPARK_UPGRADE_LEDGER.yaml"
        if not candidate.exists():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except Exception as exc:
            return {"exists": True, "path": str(candidate), "error": f"{type(exc).__name__}: {exc}"}
        statuses = Counter(re.findall(r"(?m)^\s*status:\s*([a-zA-Z0-9_.-]+)\s*$", text))
        schema_match = re.search(r"(?m)^\s*schema(?:_version)?:\s*([a-zA-Z0-9_.-]+)\s*$", text)
        return {
            "exists": True,
            "path": str(candidate),
            "schema_hint": schema_match.group(1) if schema_match else None,
            "status_counts": dict(sorted(statuses.items())),
            "redaction": "status counts only; ledger item contents omitted",
        }
    return {"exists": False}


def summarize_capability_ledger(builder_home: Path) -> dict[str, Any]:
    path = builder_home / "artifacts" / "capability-ledger" / "capability-ledger.json"
    data, error = read_json(path)
    out: dict[str, Any] = {"path": str(path), "exists": path.exists(), "redaction": "shape only; contents omitted"}
    if error and error != "missing":
        out["error"] = error
        return out
    if isinstance(data, list):
        out["entry_count"] = len(data)
    elif isinstance(data, dict):
        out["top_level_keys"] = sorted(data.keys())
        for key, value in data.items():
            if isinstance(value, list):
                out[f"{key}_count"] = len(value)
    return out


def count_safe_jsonl(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "redaction": "line counts, parse counts, key presence, and allowlisted primitive counters only",
    }
    if not path.exists():
        return out

    line_count = parsed_count = parse_errors = redacted_key_name_count = 0
    key_counts: Counter[str] = Counter()
    value_counts: dict[str, Counter[str]] = {key: Counter() for key in SAFE_JSONL_COUNT_KEYS}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                line_count += 1
                try:
                    payload = json.loads(line)
                except Exception:
                    parse_errors += 1
                    continue
                parsed_count += 1
                if not isinstance(payload, dict):
                    continue
                for key, value in payload.items():
                    key_name = str(key)
                    if any(hint in key_name.lower() for hint in SENSITIVE_KEY_NAME_HINTS):
                        redacted_key_name_count += 1
                        continue
                    key_counts[key_name] += 1
                    if key in value_counts and isinstance(value, (str, int, float, bool)) and value is not None:
                        value_counts[key][str(value)[:80]] += 1
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    out["line_count"] = line_count
    out["parsed_count"] = parsed_count
    out["parse_errors"] = parse_errors
    out["redacted_key_name_count"] = redacted_key_name_count
    out["top_keys"] = dict(key_counts.most_common(30))
    out["safe_value_counts"] = {key: dict(counter.most_common(30)) for key, counter in value_counts.items() if counter}
    return out


def inspect_safe_jsonl_samples(
    path: Path,
    *,
    source: str,
    safe_fields: tuple[str, ...],
    identifier_fields: dict[str, str] | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "source": source,
        "path": str(path),
        "exists": path.exists(),
        "limit": limit,
        "redaction": "bounded samples over allowlisted primitive metadata only; raw messages and text previews omitted",
    }
    if not path.exists():
        return out

    identifier_fields = identifier_fields or {}
    line_count = parsed_count = parse_errors = redacted_key_name_count = 0
    key_counts: Counter[str] = Counter()
    samples: deque[dict[str, Any]] = deque(maxlen=max(0, min(int(limit), 100)))
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                line_count += 1
                try:
                    payload = json.loads(line)
                except Exception:
                    parse_errors += 1
                    continue
                parsed_count += 1
                if not isinstance(payload, dict):
                    continue
                for key in payload:
                    key_name = str(key)
                    if any(hint in key_name.lower() for hint in SENSITIVE_KEY_NAME_HINTS):
                        redacted_key_name_count += 1
                        continue
                    key_counts[key_name] += 1
                sample: dict[str, Any] = {}
                for field in safe_fields:
                    if field in payload:
                        sample[field] = safe_jsonl_sample_value(
                            field,
                            payload.get(field),
                            identifier_fields=identifier_fields,
                        )
                if sample:
                    samples.append(sample)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    out["line_count"] = line_count
    out["parsed_count"] = parsed_count
    out["parse_errors"] = parse_errors
    out["redacted_key_name_count"] = redacted_key_name_count
    out["top_keys"] = dict(key_counts.most_common(30))
    out["samples"] = list(samples)
    out["sample_count"] = len(samples)
    return out


def safe_jsonl_sample_value(field: str, value: Any, *, identifier_fields: dict[str, str]) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        identifier_column = identifier_fields.get(field)
        if identifier_column:
            return safe_builder_event_value(identifier_column, value)
        return safe_short_string(value, limit=160)
    if isinstance(value, list):
        return f"[list:{len(value)}]"
    if isinstance(value, dict):
        return f"[object:{len(value)}]"
    return safe_short_string(str(value), limit=80)


def inspect_telegram_final_answer_gate(path: Path) -> dict[str, Any]:
    out = inspect_safe_jsonl_samples(
        path,
        source="telegram_final_answer_gate",
        safe_fields=SAFE_TELEGRAM_FINAL_ANSWER_FIELDS,
    )
    top_keys = as_dict(out.get("top_keys"))
    request_id_present = "request_id" in top_keys or "requestId" in top_keys
    trace_ref_present = "trace_ref" in top_keys or "traceRef" in top_keys
    out["trace_join"] = {
        "request_id_field_present": request_id_present,
        "trace_ref_field_present": trace_ref_present,
        "status": "join_key_present" if request_id_present or trace_ref_present else "missing_join_key",
        "next_action": "Emit request_id or trace_ref from Telegram final-answer gate checks.",
    }
    return out


def inspect_telegram_outbound_audit(path: Path) -> dict[str, Any]:
    return inspect_safe_jsonl_samples(
        path,
        source="telegram_outbound_audit",
        safe_fields=SAFE_TELEGRAM_OUTBOUND_FIELDS,
    )


def inspect_spawner_prd_auto_trace(path: Path, *, builder_home: Path) -> dict[str, Any]:
    out = inspect_safe_jsonl_samples(
        path,
        source="spawner_prd_auto_trace",
        safe_fields=SAFE_SPAWNER_PRD_TRACE_FIELDS,
        identifier_fields={
            "requestId": "request_id",
            "missionId": "request_id",
            "traceRef": "trace_ref",
            "trace_ref": "trace_ref",
        },
    )
    request_ids: set[str] = set()
    mission_ids: set[str] = set()
    trace_refs: set[str] = set()
    derived_trace_refs: set[str] = set()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    request_id = payload.get("requestId")
                    mission_id = payload.get("missionId")
                    trace_ref = payload.get("traceRef") or payload.get("trace_ref")
                    if isinstance(request_id, str) and request_id.strip():
                        request_ids.add(request_id.strip())
                    if isinstance(mission_id, str) and mission_id.strip():
                        clean_mission_id = mission_id.strip()
                        mission_ids.add(clean_mission_id)
                        derived_trace_refs.add(f"trace:spawner-prd:{clean_mission_id}")
                    if isinstance(trace_ref, str) and trace_ref.strip():
                        trace_refs.add(trace_ref.strip())
        except OSError as exc:
            out["join_error"] = f"{type(exc).__name__}: {exc}"
    effective_trace_refs = set(trace_refs)
    effective_trace_refs.update(derived_trace_refs)
    out["join_keys"] = {
        "request_id_count": len(request_ids),
        "mission_id_count": len(mission_ids),
        "trace_ref_count": len(trace_refs),
        "derived_trace_ref_count": len(derived_trace_refs),
    }
    out["derived_trace_contract"] = {
        "scheme": "trace:spawner-prd:<missionId>",
        "source": "missionId",
        "status": "derived_available" if derived_trace_refs else "missing_mission_id",
    }
    out["builder_request_overlap"] = inspect_builder_request_id_overlap(builder_home, request_ids)
    out["builder_trace_ref_overlap"] = inspect_builder_trace_ref_overlap(builder_home, effective_trace_refs)
    return out


def inspect_builder_request_id_overlap(builder_home: Path, request_ids: set[str]) -> dict[str, Any]:
    db_path = builder_home / "state.db"
    out: dict[str, Any] = {
        "source": "builder_events",
        "exists": db_path.exists(),
        "checked_request_id_count": len(request_ids),
        "redaction": "overlap counts only; request id values omitted",
    }
    if not request_ids or not db_path.exists():
        out["matched_builder_request_id_count"] = 0
        return out
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table'")]
            if "builder_events" not in tables:
                out["table_exists"] = False
                out["matched_builder_request_id_count"] = 0
                return out
            columns = [row[1] for row in conn.execute("pragma table_info(builder_events)")]
            if "request_id" not in columns:
                out["request_id_column_exists"] = False
                out["matched_builder_request_id_count"] = 0
                return out
            candidates = sorted(request_ids)[:500]
            placeholders = ",".join("?" for _ in candidates)
            matched = conn.execute(
                f"""
                select count(distinct request_id)
                from builder_events
                where request_id in ({placeholders})
                """,
                candidates,
            ).fetchone()[0]
            out["matched_builder_request_id_count"] = int(matched or 0)
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def inspect_builder_trace_ref_overlap(builder_home: Path, trace_refs: set[str]) -> dict[str, Any]:
    db_path = builder_home / "state.db"
    out: dict[str, Any] = {
        "source": "builder_events",
        "exists": db_path.exists(),
        "checked_trace_ref_count": len(trace_refs),
        "redaction": "overlap counts only; trace ref values omitted",
    }
    if not trace_refs or not db_path.exists():
        out["matched_builder_trace_ref_count"] = 0
        return out
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table'")]
            if "builder_events" not in tables:
                out["table_exists"] = False
                out["matched_builder_trace_ref_count"] = 0
                return out
            columns = [row[1] for row in conn.execute("pragma table_info(builder_events)")]
            if "trace_ref" not in columns:
                out["trace_ref_column_exists"] = False
                out["matched_builder_trace_ref_count"] = 0
                return out
            candidates = sorted(trace_refs)[:500]
            placeholders = ",".join("?" for _ in candidates)
            matched = conn.execute(
                f"""
                select count(distinct trace_ref)
                from builder_events
                where trace_ref in ({placeholders})
                """,
                candidates,
            ).fetchone()[0]
            out["matched_builder_trace_ref_count"] = int(matched or 0)
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def inspect_spawner_authority_verdicts(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "source": "spawner_prd_auto_trace",
        "path": str(path),
        "exists": path.exists(),
        "schema_version": "spark.authority_verdict_index.v0",
        "redaction": "authority verdict metadata only; prompts, mission bodies, provider output, and raw request identifiers omitted",
        "verdict_count": 0,
        "verdict_counts": {},
        "action_family_counts": {},
        "source_policy_counts": {},
        "items": [],
    }
    if not path.exists():
        return out

    verdict_counts: Counter[str] = Counter()
    action_family_counts: Counter[str] = Counter()
    source_policy_counts: Counter[str] = Counter()
    items: deque[dict[str, Any]] = deque(maxlen=40)
    parsed_count = parse_errors = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    parse_errors += 1
                    continue
                if not isinstance(payload, dict):
                    continue
                parsed_count += 1
                if payload.get("event") != "authority_verdict_evaluated":
                    continue
                verdict = as_dict(payload.get("authorityVerdict"))
                verdict_name = str(verdict.get("verdict") or "unknown")
                action_family = str(verdict.get("actionFamily") or "unknown")
                source_policy = str(verdict.get("sourcePolicy") or "unknown")
                verdict_counts[verdict_name] += 1
                action_family_counts[action_family] += 1
                source_policy_counts[source_policy] += 1
                trace_ref = verdict.get("traceRef") or payload.get("traceRef") or payload.get("trace_ref")
                request_id = payload.get("requestId")
                items.append(
                    {
                        "schema_version": str(verdict.get("schema_version") or "spark.authority_verdict.v1"),
                        "ts": safe_jsonl_sample_value("ts", payload.get("ts"), identifier_fields={}),
                        "request_id": redacted_identifier("request_id", request_id) if isinstance(request_id, str) else None,
                        "trace_ref": redacted_identifier("trace_ref", trace_ref) if isinstance(trace_ref, str) else None,
                        "action_family": action_family,
                        "source_policy": source_policy,
                        "verdict": verdict_name,
                        "confirmation_required": bool(verdict.get("confirmationRequired")),
                        "scope": safe_short_string(str(verdict.get("scope") or "unknown"), limit=120),
                        "source_repo": safe_short_string(str(verdict.get("sourceRepo") or "unknown"), limit=80),
                        "reason_code": safe_short_string(str(verdict.get("reasonCode") or "unknown"), limit=120),
                    }
                )
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    out["parsed_count"] = parsed_count
    out["parse_errors"] = parse_errors
    out["verdict_count"] = sum(verdict_counts.values())
    out["verdict_counts"] = dict(verdict_counts.most_common(20))
    out["action_family_counts"] = dict(action_family_counts.most_common(20))
    out["source_policy_counts"] = dict(source_policy_counts.most_common(20))
    out["items"] = list(items)
    return out


def build_spark_os_review_candidates(path: Path, *, builder_home: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": REVIEW_CANDIDATES_SCHEMA,
        "source": "spawner_prd_auto_trace",
        "path": str(path),
        "exists": path.exists(),
        "owner_repos": {
            "labs_packet": "spark-domain-chip-labs",
            "swarm_proposal": "spark-swarm",
            "source_trace": "spawner-ui",
        },
        "redaction": (
            "metadata-only review candidates; raw prompts, project names, provider output, chat/user ids, "
            "memory bodies, artifact bodies, transcript/audio bodies, secrets, and raw paths omitted"
        ),
        "counts": {"candidate_count": 0, "blocked_count": 0},
        "items": [],
    }
    if not path.exists():
        return out

    groups: dict[str, dict[str, Any]] = {}
    parse_errors = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    parse_errors += 1
                    continue
                if not isinstance(payload, dict):
                    continue

                request_id = payload.get("requestId")
                trace_ref = payload.get("traceRef") or payload.get("trace_ref")
                mission_id = payload.get("missionId")
                raw_key = next(
                    (
                        value.strip()
                        for value in (trace_ref, request_id, mission_id)
                        if isinstance(value, str) and value.strip()
                    ),
                    "",
                )
                if not raw_key:
                    continue

                group = groups.setdefault(
                    raw_key,
                    {
                        "request_id": request_id.strip() if isinstance(request_id, str) else None,
                        "trace_ref": trace_ref.strip() if isinstance(trace_ref, str) else None,
                        "mission_id": mission_id.strip() if isinstance(mission_id, str) else None,
                        "event_counts": Counter(),
                        "file_count": None,
                        "task_count": None,
                        "authority_verdict": {},
                        "latest_ts": None,
                    },
                )
                if isinstance(request_id, str) and request_id.strip():
                    group["request_id"] = request_id.strip()
                if isinstance(trace_ref, str) and trace_ref.strip():
                    group["trace_ref"] = trace_ref.strip()
                if isinstance(mission_id, str) and mission_id.strip():
                    group["mission_id"] = mission_id.strip()

                event = str(payload.get("event") or "unknown")
                group["event_counts"][safe_short_string(event, limit=80)] += 1
                if isinstance(payload.get("fileCount"), int):
                    group["file_count"] = payload.get("fileCount")
                if isinstance(payload.get("taskCount"), int):
                    group["task_count"] = payload.get("taskCount")
                if isinstance(payload.get("ts"), str):
                    group["latest_ts"] = payload.get("ts")
                if event == "authority_verdict_evaluated":
                    verdict = as_dict(payload.get("authorityVerdict"))
                    group["authority_verdict"] = {
                        "schema_version": str(verdict.get("schema_version") or "spark.authority_verdict.v1"),
                        "verdict": str(verdict.get("verdict") or "unknown"),
                        "action_family": safe_short_string(str(verdict.get("actionFamily") or "unknown"), limit=80),
                        "source_policy": safe_short_string(str(verdict.get("sourcePolicy") or "unknown"), limit=120),
                        "source_repo": safe_short_string(str(verdict.get("sourceRepo") or "unknown"), limit=80),
                        "reason_code": safe_short_string(str(verdict.get("reasonCode") or "unknown"), limit=120),
                    }
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    candidates: list[dict[str, Any]] = []
    for raw_key, group in groups.items():
        event_counts = Counter(group.get("event_counts") or {})
        has_artifact_metadata = bool(
            event_counts.get("deterministic_static_artifacts_written")
            or event_counts.get("fallback_analysis_written")
            or event_counts.get("auto_worker_finished")
        )
        if not has_artifact_metadata:
            continue

        raw_request_id = group.get("request_id")
        raw_trace_ref = group.get("trace_ref")
        request_ref = (
            redacted_identifier("request_id", raw_request_id)
            if isinstance(raw_request_id, str) and raw_request_id
            else None
        )
        trace_ref = (
            redacted_identifier("trace_ref", raw_trace_ref)
            if isinstance(raw_trace_ref, str) and raw_trace_ref
            else redacted_identifier("trace_ref", raw_key)
        )
        authority = as_dict(group.get("authority_verdict"))
        if not authority:
            authority = {
                "schema_version": "spark.authority_verdict.v1",
                "verdict": "unknown",
                "action_family": "unknown",
                "source_policy": "unknown",
                "source_repo": "spawner-ui",
                "reason_code": "authority_verdict_missing",
            }

        builder_request_join = (
            inspect_builder_request_id_overlap(builder_home, {raw_request_id})
            if isinstance(raw_request_id, str) and raw_request_id
            else {"matched_builder_request_id_count": 0}
        )
        builder_trace_join = (
            inspect_builder_trace_ref_overlap(builder_home, {raw_trace_ref})
            if isinstance(raw_trace_ref, str) and raw_trace_ref
            else {"matched_builder_trace_ref_count": 0}
        )
        builder_join_present = bool(
            int(as_dict(builder_request_join).get("matched_builder_request_id_count") or 0)
            or int(as_dict(builder_trace_join).get("matched_builder_trace_ref_count") or 0)
        )
        blockers = []
        if authority.get("verdict") != "allowed":
            blockers.append("authority_verdict_not_allowed")
        if not builder_join_present:
            blockers.append("builder_trace_join_missing")
        blockers.extend(
            [
                "human_review_required",
                "benchmark_evidence_missing",
                "rollback_review_missing",
                "publication_approval_missing",
            ]
        )

        event_count_dict = dict(event_counts.most_common(20))
        labs_packet = {
            "schema_version": "adaptive_creator_loop.spark_os_labs_review_packet.v1",
            "packet_id": f"labs-review:{hashlib.sha256(raw_key.encode('utf-8', errors='ignore')).hexdigest()[:12]}",
            "trace_ref": trace_ref,
            "request_id": request_ref,
            "source_repo": "spawner-ui",
            "ownership": {
                "contract_owner_repo": "spark-domain-chip-labs",
                "contract_scope": "metadata_schema_review_only",
                "source_owner_repo": "spawner-ui",
                "labs_may_promote_memory": False,
                "labs_may_wire_product_runtime": False,
                "labs_may_publish_network": False,
            },
            "source_artifact_metadata": {
                "source_surface": "spawner_prd_auto_trace",
                "artifact_body_exported": False,
                "event_counts": event_count_dict,
                "file_count": group.get("file_count"),
                "task_count": group.get("task_count"),
            },
            "authority_verdict_ref": authority,
            "privacy_status": {
                "status": "metadata_only",
                "raw_prompt_exported": False,
                "provider_output_exported": False,
                "chat_or_user_id_exported": False,
                "memory_body_exported": False,
                "artifact_body_exported": False,
            },
            "benchmark": {
                "status": "placeholder",
                "placeholder": "Labs benchmark review required before promotion.",
                "required_before_promotion": True,
            },
            "rollback_route": {
                "status": "review_required",
                "route": "Reject packet candidate; leave source proof local and unchanged.",
                "owner_repo": "spark-domain-chip-labs",
            },
            "human_review_required": True,
            "network_absorbable": False,
            "network_publication_allowed": False,
            "memory_promotion_allowed": False,
            "payload_export_policy": {
                "mode": "metadata_only",
                "allowed_fields_only": True,
                "forbidden_payloads": [
                    "raw_prompt",
                    "provider_output",
                    "chat_id",
                    "user_id",
                    "memory_body",
                    "transcript_body",
                    "audio_body",
                    "secret_value",
                    "artifact_body",
                ],
            },
            "next_action": "Review this trace candidate in Labs before promotion or publication.",
        }
        swarm_proposal = {
            "schemaVersion": "spark_swarm.spark_os_review_only_proposal.v1",
            "proposalKind": "recursive_system",
            "proposalState": "blocked",
            "reviewOnly": True,
            "owner": {
                "contractOwnerRepo": "spark-swarm",
                "sourceOwnerRepo": "spawner-ui",
                "workspaceScoped": True,
                "routeWorkspaceRequired": True,
            },
            "networkPublicationAllowed": False,
            "networkPublishAction": "none",
            "networkAbsorbable": False,
            "memoryPromotionAllowed": False,
            "traceRef": trace_ref,
            "requestId": request_ref,
            "spawnerProof": {
                "status": "completed",
                "sourceSystem": "spawner-ui",
                "artifactBodyExported": False,
                "eventCounts": event_count_dict,
                "fileCount": group.get("file_count"),
                "taskCount": group.get("task_count"),
            },
            "requiredGates": {
                "labsReviewPacket": True,
                "metadataOnlyPrivacy": True,
                "humanReview": False,
                "benchmarkEvidence": False,
                "rollbackReview": False,
                "publicationApproval": False,
                "authorityApproval": authority.get("verdict") == "allowed",
            },
            "publicationBlock": {
                "networkAbsorbable": False,
                "networkPublicationAllowed": False,
                "automaticPublish": False,
                "noAutomaticPublish": True,
            },
            "blockedReasons": blockers,
            "nextAction": "Keep as review-only until human, benchmark, rollback, publication, and authority gates pass.",
        }
        candidates.append(
            {
                "schema_version": "spark.os_review_candidate.v0",
                "candidate_id": f"spark-os-review:{hashlib.sha256(raw_key.encode('utf-8', errors='ignore')).hexdigest()[:12]}",
                "status": "blocked",
                "latest_ts": safe_jsonl_sample_value("ts", group.get("latest_ts"), identifier_fields={}),
                "trace_ref": trace_ref,
                "request_id": request_ref,
                "source_repo": "spawner-ui",
                "owner_repo": "spark-cli",
                "labs_packet_owner_repo": "spark-domain-chip-labs",
                "swarm_proposal_owner_repo": "spark-swarm",
                "builder_trace_join_present": builder_join_present,
                "blockers": blockers,
                "labs_review_packet_candidate": labs_packet,
                "swarm_review_only_proposal_candidate": swarm_proposal,
                "verification_command": "spark os compile --json",
            }
        )

    out["parse_errors"] = parse_errors
    candidates.sort(key=lambda item: str(item.get("latest_ts") or ""), reverse=True)
    items = candidates[:20]
    out["counts"] = {
        "candidate_count": len(candidates),
        "candidate_sample_count": len(items),
        "blocked_count": sum(1 for item in candidates if item.get("status") == "blocked"),
        "builder_trace_join_present_count": sum(
            1 for item in candidates if item.get("builder_trace_join_present")
        ),
    }
    out["items"] = items
    return out


def inspect_json_shape(path: Path) -> dict[str, Any]:
    data, error = read_json(path)
    out: dict[str, Any] = {"path": str(path), "exists": path.exists(), "redaction": "shape only; values omitted"}
    if error and error != "missing":
        out["error"] = error
        return out
    if isinstance(data, dict):
        out["shape"] = "object"
        out["top_level_keys"] = sorted(str(key) for key in data.keys())[:80]
        out["top_level_key_count"] = len(data)
    elif isinstance(data, list):
        out["shape"] = "array"
        out["item_count"] = len(data)
    elif data is not None:
        out["shape"] = type(data).__name__
    return out


def inspect_file_metadata(path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "redaction": "filesystem metadata only; file body not read",
    }
    if not path.exists():
        return out
    try:
        stat = path.stat()
    except OSError as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    out["size_bytes"] = int(stat.st_size)
    out["modified_at"] = (
        datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    return out


def safe_short_string(value: str, limit: int = 240) -> str:
    cleaned = re.sub(r"(?i)(api[_-]?key|token|secret)([=:\s]+)(\S+)", r"\1\2[redacted]", value.strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def sensitive_identifier(value: str) -> bool:
    lowered = str(value or "").lower()
    return bool(
        re.search(r"(human|telegram|user|chat):", lowered)
        or re.search(r"\d{7,}", lowered)
        or re.search(r"(?i)(token|secret|api[_-]?key)", lowered)
    )


def redacted_identifier(column: str, value: str) -> str:
    column = str(column or "")
    value_str = str(value or "")
    digest = hashlib.sha256(value_str.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"{column}:redacted:{digest}"


def safe_builder_event_value(column: str, value: Any) -> Any:
    column = str(column or "")
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    if column in BUILDER_EVENT_IDENTIFIER_COLUMNS and sensitive_identifier(text):
        return redacted_identifier(column, text)
    return safe_short_string(text, limit=160)


def key_has_raw_memory_hint(key: Any) -> bool:
    lowered = str(key or "").lower()
    return any(hint in lowered for hint in RAW_MEMORY_KEY_HINTS)


def safe_memory_status_value(value: Any, *, depth: int = 0) -> Any:
    depth = int(depth or 0)
    if depth > 4:
        return "[depth-limit]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return safe_short_string(value)
    if isinstance(value, list):
        return [safe_memory_status_value(item, depth=depth + 1) for item in value[:50]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:80]:
            if key_has_raw_memory_hint(key):
                continue
            out[str(key)[:120]] = safe_memory_status_value(item, depth=depth + 1)
        return out
    return str(type(value).__name__)


def count_raw_memory_hint_keys(value: Any) -> int:
    if isinstance(value, dict):
        count = sum(1 for key in value.keys() if key_has_raw_memory_hint(key))
        return count + sum(count_raw_memory_hint_keys(item) for item in value.values())
    if isinstance(value, list):
        return sum(count_raw_memory_hint_keys(item) for item in value)
    return 0


def read_memory_movement_status_export(builder_home: Path) -> dict[str, Any]:
    path = builder_home / "artifacts" / "memory-movement-index" / "memory-movement-status.json"
    data, error = read_json(path)
    out: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "redaction": "allowlisted status fields only; rows, raw memory text, and evidence bodies omitted",
    }
    if error and error != "missing":
        out["error"] = error
        return out
    if not isinstance(data, dict):
        return out

    allowed: dict[str, Any] = {}
    for key in sorted(SAFE_MEMORY_STATUS_KEYS):
        if key in data:
            allowed[key] = safe_memory_status_value(data[key])
    out["status"] = allowed
    out["omitted_top_level_keys"] = sorted(
        str(key) for key in data.keys() if key not in SAFE_MEMORY_STATUS_KEYS and not key_has_raw_memory_hint(key)
    )[:80]
    out["raw_hint_key_count"] = count_raw_memory_hint_keys(data)
    return out


def count_files_under(path: Path, *, max_files: int = 5000) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "redaction": "counts only; file names and file bodies omitted",
    }
    if not path.exists():
        return out

    file_count = 0
    dir_count = 0
    extension_counts: Counter[str] = Counter()
    try:
        for child in path.rglob("*"):
            if child.is_dir():
                dir_count += 1
                continue
            if not child.is_file():
                continue
            file_count += 1
            suffix = child.suffix.lower() or "[none]"
            extension_counts[suffix] += 1
            if file_count >= max_files:
                out["max_files_reached"] = True
                break
    except OSError as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    out["file_count"] = file_count
    out["dir_count"] = dir_count
    out["extension_counts"] = dict(sorted(extension_counts.items()))
    return out


def count_schema_files(path: Path, *, max_files: int = 500) -> dict[str, Any]:
    out: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "schema_count": 0,
        "schemas": [],
        "redaction": "schema file names only; schema bodies omitted",
    }
    if not path.exists():
        return out

    names: list[str] = []
    try:
        for child in sorted(path.glob("*.schema.json"), key=lambda item: item.name.lower()):
            if not child.is_file():
                continue
            names.append(child.name)
            if len(names) >= max_files:
                out["max_files_reached"] = True
                break
    except OSError as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    out["schema_count"] = len(names)
    out["schemas"] = names
    return out


def repo_source_ref(repo_path: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_path).as_posix()
    except ValueError:
        return path.name


def proof_verdict(
    *,
    domain: str,
    status: str,
    source_kind: str,
    source_ref: str | None = None,
    schema_version: str | None = None,
    raw_status: str | None = None,
    raw_verdict: str | None = None,
    detail_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": CAPABILITY_PROOF_VERDICTS_SCHEMA,
        "domain": domain,
        "status": status,
        "satisfied": status == "passed",
        "source_kind": source_kind,
        "source_ref": source_ref,
        "source_schema_version": schema_version,
        "source_status": raw_status,
        "source_verdict": raw_verdict,
        "detail_counts": detail_counts or {},
        "redaction": "metadata only; proof bodies, commands, labels, and raw evidence omitted",
    }


def missing_proof_verdict(domain: str) -> dict[str, Any]:
    return proof_verdict(domain=domain, status="missing", source_kind="not_found")


def source_presence_verdict(
    *,
    domain: str,
    repo_path: Path,
    source_path: Path,
    source_kind: str,
) -> dict[str, Any]:
    if source_path.exists():
        return proof_verdict(
            domain=domain,
            status="present_unverified",
            source_kind=source_kind,
            source_ref=repo_source_ref(repo_path, source_path),
        )
    return missing_proof_verdict(domain)


def status_from_json_verdict(data: dict[str, Any], *, passed_keys: tuple[str, ...] = ()) -> str:
    values = [
        str(data.get("verdict") or "").strip().lower(),
        str(data.get("status") or "").strip().lower(),
    ]
    if any(
        value
        and (
            value in {"blocked", "failed", "fail", "rejected", "not_approved", "placeholder", "template_only"}
            or value.startswith("blocked")
            or "blocked" in value
        )
        for value in values
    ):
        return "blocked"
    for key in passed_keys:
        value = data.get(key)
        if value is True:
            return "passed"
        if value is False:
            return "blocked"

    if any(value in {"passed", "pass", "approved", "verified", "active"} for value in values):
        return "passed"
    return "present_unverified"


def json_proof_verdict(
    *,
    repo_path: Path,
    rel_path: str,
    domain: str,
    source_kind: str,
    passed_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    path = repo_path / rel_path
    data, error = read_json(path)
    if error == "missing":
        return missing_proof_verdict(domain)
    if error:
        return proof_verdict(
            domain=domain,
            status="read_error",
            source_kind=source_kind,
            source_ref=repo_source_ref(repo_path, path),
        )
    payload = as_dict(data)
    return proof_verdict(
        domain=domain,
        status=status_from_json_verdict(payload, passed_keys=passed_keys),
        source_kind=source_kind,
        source_ref=repo_source_ref(repo_path, path),
        schema_version=first_string(payload.get("schema_version")),
        raw_status=first_string(payload.get("status")),
        raw_verdict=first_string(payload.get("verdict")),
        detail_counts={
            "required_before_approval_count": len(as_list(payload.get("required_before_approval"))),
            "blocked_reason_count": len(as_list(as_dict(payload.get("stop_ship")).get("blocked_reasons"))),
        },
    )


def first_run_artifact(repo_path: Path, rel_path: str) -> Path | None:
    runs_root = repo_path / "runs"
    if not runs_root.exists():
        return None
    try:
        for run_dir in sorted((child for child in runs_root.iterdir() if child.is_dir()), key=lambda item: item.name.lower()):
            candidate = run_dir / rel_path
            if candidate.exists():
                return candidate
    except Exception:
        return None
    return None


def labs_creator_proof_sources(repo_path: Path) -> dict[str, Any]:
    repo_path = Path(repo_path)
    gate_path = repo_path / LABS_CREATOR_SURFACE_FILES["release_gate"]
    benchmark_path = first_run_artifact(repo_path, LABS_CREATOR_RUN_ARTIFACTS["benchmark_manifest"])
    loop_policy_path = first_run_artifact(repo_path, LABS_CREATOR_RUN_ARTIFACTS["loop_policy"])
    proof_sources = {
        "gate": source_presence_verdict(
            domain="gate",
            repo_path=repo_path,
            source_path=gate_path,
            source_kind="release_gate_source",
        ),
        "benchmark": (
            proof_verdict(
                domain="benchmark",
                status="present_unverified",
                source_kind="benchmark_manifest",
                source_ref=repo_source_ref(repo_path, benchmark_path),
            )
            if benchmark_path
            else missing_proof_verdict("benchmark")
        ),
        "privacy": missing_proof_verdict("privacy"),
        "rollback": missing_proof_verdict("rollback"),
        "authority": missing_proof_verdict("authority"),
        "publication": missing_proof_verdict("publication"),
    }

    if loop_policy_path:
        data, error = read_json(loop_policy_path)
        payload = as_dict(data)
        proof_sources["rollback"] = proof_verdict(
            domain="rollback",
            status="present_unverified" if not error else "read_error",
            source_kind="autoloop_rollback_policy",
            source_ref=repo_source_ref(repo_path, loop_policy_path),
            schema_version=first_string(payload.get("schema_version")),
            detail_counts={"rollback_condition_present": int(bool(payload.get("rollback_condition")))},
        )
        if payload.get("network_publication_allowed") is False:
            proof_sources["publication"] = proof_verdict(
                domain="publication",
                status="blocked",
                source_kind="autoloop_publication_boundary",
                source_ref=repo_source_ref(repo_path, loop_policy_path),
                schema_version=first_string(payload.get("schema_version")),
                raw_status="network_publication_allowed=false",
            )
    return proof_sources


def swarm_specialization_proof_sources(
    repo_path: Path,
    *,
    benchmark_adapter_counts: dict[str, Any],
    rollback_policy_counts: dict[str, Any],
    promotion_packet_count: int,
    evidence_ledger_count: int,
) -> dict[str, Any]:
    repo_path = Path(repo_path)
    benchmark_adapter_counts = benchmark_adapter_counts if isinstance(benchmark_adapter_counts, dict) else {}
    rollback_policy_counts = rollback_policy_counts if isinstance(rollback_policy_counts, dict) else {}
    promotion_packet_count = int(promotion_packet_count or 0)
    evidence_ledger_count = int(evidence_ledger_count or 0)
    proof_sources = {
        "benchmark": (
            proof_verdict(domain="benchmark", status="present_unverified", source_kind="benchmark_adapter_config")
            if benchmark_adapter_counts
            else missing_proof_verdict("benchmark")
        ),
        "publication": json_proof_verdict(
            repo_path=repo_path,
            rel_path=SWARM_CAPABILITY_VERDICT_FILES["publication_approval"],
            domain="publication",
            source_kind="publication_approval",
            passed_keys=("network_publication_allowed",),
        ),
        "privacy": missing_proof_verdict("privacy"),
        "rollback": (
            proof_verdict(domain="rollback", status="present_unverified", source_kind="rollback_policy_config")
            if rollback_policy_counts
            else missing_proof_verdict("rollback")
        ),
        "authority": json_proof_verdict(
            repo_path=repo_path,
            rel_path=SWARM_CAPABILITY_VERDICT_FILES["github_ruleset_review"],
            domain="authority",
            source_kind="github_ruleset_review",
            passed_keys=("ruleset_review_passed",),
        ),
        "trace": (
            proof_verdict(
                domain="trace",
                status="present_unverified",
                source_kind="collective_packet_or_ledger",
                detail_counts={
                    "promotion_packet_count": promotion_packet_count,
                    "evidence_ledger_count": evidence_ledger_count,
                },
            )
            if promotion_packet_count or evidence_ledger_count
            else missing_proof_verdict("trace")
        ),
    }
    return proof_sources


def capability_proof_summary(
    proof_verdicts: dict[str, Any],
    required_labels: dict[str, str],
) -> dict[str, Any]:
    proof_verdicts = proof_verdicts if isinstance(proof_verdicts, dict) else {}
    required_labels = required_labels if isinstance(required_labels, dict) else {}
    counts: Counter[str] = Counter()
    passed: list[str] = []
    blocked: list[str] = []
    unverified: list[str] = []
    missing: list[str] = []

    for domain, label in required_labels.items():
        verdict = as_dict(proof_verdicts.get(domain))
        status = str(verdict.get("status") or "missing")
        counts[status] += 1
        if status == "passed":
            passed.append(label)
        elif status == "blocked":
            blocked.append(label)
        elif status == "present_unverified":
            unverified.append(label)
        else:
            missing.append(label)

    if blocked:
        overall = "blocked"
    elif missing or unverified:
        overall = "missing_required_verdicts"
    else:
        overall = "passed"

    return {
        "overall_status": overall,
        "required_proofs": list(required_labels.values()),
        "passed_proofs": passed,
        "blocked_proofs": blocked,
        "unverified_proofs": unverified,
        "missing_proofs": missing,
        "unsatisfied_proofs": [*blocked, *unverified, *missing],
        "status_counts": dict(sorted(counts.items())),
    }


def inspect_labs_creator_surface(repo_path: Path) -> dict[str, Any] | None:
    repo_path = Path(repo_path)
    schema_dir = repo_path / "docs" / "creator_system" / "schemas"
    if not schema_dir.exists() and repo_path.name != "spark-domain-chip-labs":
        return None

    runs_root = repo_path / "runs"
    run_count = 0
    artifact_counts: Counter[str] = Counter()
    if runs_root.exists():
        try:
            for run_dir in runs_root.iterdir():
                if not run_dir.is_dir():
                    continue
                run_count += 1
                for label, rel_path in LABS_CREATOR_RUN_ARTIFACTS.items():
                    if (run_dir / rel_path).exists():
                        artifact_counts[label] += 1
        except Exception:
            pass

    return {
        "repo": str(repo_path.name or ""),
        "schema_inventory": count_schema_files(schema_dir),
        "review_and_release_sources": {
            label: {"path": str(repo_path / rel_path), "exists": (repo_path / rel_path).exists()}
            for label, rel_path in LABS_CREATOR_SURFACE_FILES.items()
        },
        "creator_run_artifacts": {
            "run_count": run_count,
            "artifact_presence_counts": dict(sorted(artifact_counts.items())),
        },
        "proof_sources": labs_creator_proof_sources(repo_path),
        "claim_boundary": (
            "Creator-system schemas and run artifacts are compatibility and review evidence; "
            "they are not network publication approval or durable memory truth."
        ),
    }


def inspect_swarm_specialization_surface(repo_path: Path) -> dict[str, Any] | None:
    repo_path = Path(repo_path)
    config_path = repo_path / "config" / "specialization-paths.json"
    schemas_dir = repo_path / "schemas"
    has_specialization_schema = False
    if schemas_dir.exists():
        try:
            has_specialization_schema = any(schemas_dir.glob("spark-specialization-path*.schema.json"))
        except Exception:
            has_specialization_schema = False
    if (
        not config_path.exists()
        and not has_specialization_schema
        and repo_path.name != "spark-swarm"
        and "specialization-path" not in repo_path.name
    ):
        return None

    config, error = read_json(config_path)
    config_dict = as_dict(config)
    path_rows = as_list(config_dict.get("paths"))
    categories: Counter[str] = Counter()
    loop_kinds: Counter[str] = Counter()
    benchmark_adapters: Counter[str] = Counter()
    evolution_modes: Counter[str] = Counter()
    rollback_policies: Counter[str] = Counter()
    for row in path_rows:
        item = as_dict(row)
        categories[str(item.get("category") or "[missing]")] += 1
        runtime = as_dict(item.get("runtime"))
        benchmark = as_dict(item.get("benchmark"))
        defaults = as_dict(item.get("specialization_defaults"))
        mutation = as_dict(item.get("mutation"))
        loop_kinds[str(runtime.get("loop_kind") or "[missing]")] += 1
        benchmark_adapters[str(benchmark.get("adapter") or "[missing]")] += 1
        evolution_modes[str(defaults.get("evolution_mode") or "[missing]")] += 1
        rollback_policies[str(mutation.get("rollback_policy") or "[missing]")] += 1

    collective_root = repo_path / "collective"
    promotion_packet_count = 0
    evidence_ledger_count = 0
    if collective_root.exists():
        try:
            promotion_packet_count = sum(1 for path in collective_root.glob("*/promotion-packet.json") if path.is_file())
            evidence_ledger_count = sum(1 for path in collective_root.glob("*/evidence-ledger.jsonl") if path.is_file())
        except Exception:
            promotion_packet_count = 0
            evidence_ledger_count = 0

    return {
        "repo": str(repo_path.name or ""),
        "config": {
            "path": str(config_path),
            "exists": config_path.exists(),
            "error": error,
            "path_count": len(path_rows),
            "category_counts": dict(sorted(categories.items())),
            "loop_kind_counts": dict(sorted(loop_kinds.items())),
            "benchmark_adapter_counts": dict(sorted(benchmark_adapters.items())),
            "evolution_mode_counts": dict(sorted(evolution_modes.items())),
            "rollback_policy_counts": dict(sorted(rollback_policies.items())),
            "redaction": "commands, labels, repo names, descriptions, and path bodies omitted",
        },
        "schema_inventory": count_schema_files(schemas_dir),
        "publication_governance_sources": {
            label: {"path": str(repo_path / rel_path), "exists": (repo_path / rel_path).exists()}
            for label, rel_path in SWARM_PUBLICATION_GOVERNANCE_FILES.items()
        },
        "collective_artifacts": {
            "promotion_packet_count": promotion_packet_count,
            "evidence_ledger_count": evidence_ledger_count,
        },
        "proof_sources": swarm_specialization_proof_sources(
            repo_path,
            benchmark_adapter_counts=dict(benchmark_adapters),
            rollback_policy_counts=dict(rollback_policies),
            promotion_packet_count=promotion_packet_count,
            evidence_ledger_count=evidence_ledger_count,
        ),
        "claim_boundary": (
            "Specialization paths and collective packets are review and benchmark surfaces; "
            "network-visible publication still requires verified proof and approval gates."
        ),
    }


def bool_count(items: dict[str, Any]) -> int:
    return sum(1 for item in items.values() if as_dict(item).get("exists") is True)


def capability_card_status_from_labs(surface: dict[str, Any]) -> str:
    artifacts = as_dict(surface.get("creator_run_artifacts"))
    schema_inventory = as_dict(surface.get("schema_inventory"))
    if int(artifacts.get("run_count") or 0) > 0:
        return "local-artifacts"
    if int(schema_inventory.get("schema_count") or 0) > 0:
        return "schema-shaped"
    return "seen"


def capability_card_status_from_specialization(surface: dict[str, Any]) -> str:
    config = as_dict(surface.get("config"))
    artifacts = as_dict(surface.get("collective_artifacts"))
    schema_inventory = as_dict(surface.get("schema_inventory"))
    if int(artifacts.get("promotion_packet_count") or 0) > 0:
        return "local-artifacts"
    if int(config.get("path_count") or 0) > 0 or int(schema_inventory.get("schema_count") or 0) > 0:
        return "schema-shaped"
    return "seen"


def capability_proof_state(status: str) -> str:
    if status == "schema-shaped":
        return "schema_only"
    if status == "local-artifacts":
        return "artifact_present_unverified"
    return "proof_incomplete"


def capability_trust_fields(
    *,
    status: str,
    compiled_proofs: dict[str, Any],
    trust_basis: list[str],
    proof_verdicts: dict[str, Any],
    required_proofs: dict[str, str],
) -> dict[str, Any]:
    proof_summary = capability_proof_summary(proof_verdicts, required_proofs)
    proof_status = proof_summary["overall_status"]
    trust_status = "trusted" if proof_status == "passed" else "untrusted"
    return {
        "trust_status": trust_status,
        "proof_state": capability_proof_state(status),
        "trust_scope": "local" if trust_status == "trusted" else "none",
        "trust_basis": trust_basis,
        "compiled_proofs": compiled_proofs,
        "proof_verdicts": proof_verdicts,
        "proof_summary": proof_summary,
        "proof_blockers": proof_summary["blocked_proofs"],
        "missing_proofs": proof_summary["unsatisfied_proofs"],
        "trust_rule": "Schema, manifest, conformance, or local artifact presence never makes a capability trusted.",
    }


def build_capability_cards(
    creator_system_surfaces: list[dict[str, Any]],
    specialization_path_surfaces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []

    for surface in creator_system_surfaces:
        repo = str(surface.get("repo") or "unknown")
        schema_inventory = as_dict(surface.get("schema_inventory"))
        artifacts = as_dict(surface.get("creator_run_artifacts"))
        review_sources = as_dict(surface.get("review_and_release_sources"))
        artifact_counts = as_dict(artifacts.get("artifact_presence_counts"))
        status = capability_card_status_from_labs(surface)
        creator_run_count = int(artifacts.get("run_count") or 0)
        schema_count = int(schema_inventory.get("schema_count") or 0)
        benchmark_manifest_count = int(artifact_counts.get("benchmark_manifest") or 0)
        review_source_count = bool_count(review_sources)
        proof_verdicts = as_dict(surface.get("proof_sources"))
        trust = capability_trust_fields(
            status=status,
            compiled_proofs={
                "schema_present": schema_count > 0,
                "local_artifacts_present": creator_run_count > 0,
                "benchmark_manifest_present": benchmark_manifest_count > 0,
                "review_sources_present": review_source_count > 0,
                "trace_refs_present": False,
                "rollback_refs_present": as_dict(proof_verdicts.get("rollback")).get("status") != "missing",
                "privacy_review_verdict_present": as_dict(proof_verdicts.get("privacy")).get("status")
                not in {None, "missing"},
                "publication_approval_present": as_dict(proof_verdicts.get("publication")).get("status")
                == "passed",
            },
            trust_basis=[
                basis
                for basis, present in (
                    ("schema_present", schema_count > 0),
                    ("local_artifacts_present", creator_run_count > 0),
                    ("benchmark_manifest_present", benchmark_manifest_count > 0),
                    ("review_source_present", review_source_count > 0),
                )
                if present
            ],
            proof_verdicts=proof_verdicts,
            required_proofs=CREATOR_REQUIRED_PROOF_LABELS,
        )
        cards.append(
            {
                "schema_version": CAPABILITY_CARD_SCHEMA,
                "id": f"creator-system:{repo}",
                "name": f"{repo} creator system",
                "owner_repo": repo,
                "surface_type": "creator-system",
                "status": status,
                **trust,
                "requested_authority": ["local_files_read", "review_only"],
                "memory_policy": "non_authoritative_evidence_only",
                "evidence_summary": {
                    "schema_count": schema_count,
                    "creator_run_count": creator_run_count,
                    "artifact_presence_counts": artifact_counts,
                },
                "benchmark_summary": {
                    "benchmark_manifest_count": benchmark_manifest_count,
                },
                "review_summary": {
                    "review_source_count": review_source_count,
                    "review_sources": {
                        key: bool(as_dict(value).get("exists")) for key, value in sorted(review_sources.items())
                    },
                },
                "trace_refs": [],
                "rollback_refs": [],
                "privacy_boundary": "Local creator artifacts are evidence references only; raw packet bodies are not exported.",
                "public_boundary": "Network publication is blocked unless explicit approval and proof gates pass.",
                "blockers": [
                    "Capability remains untrusted until every required proof domain passes.",
                    "Present benchmark, gate, or rollback metadata is still unverified unless a pass/fail verdict exists.",
                    "Network publication approval is blocked or missing unless the publication proof verdict passes.",
                ],
                "next_action": "Resolve the first unsatisfied proof in proof_summary.unsatisfied_proofs.",
            }
        )

    for surface in specialization_path_surfaces:
        repo = str(surface.get("repo") or "unknown")
        config = as_dict(surface.get("config"))
        schema_inventory = as_dict(surface.get("schema_inventory"))
        artifacts = as_dict(surface.get("collective_artifacts"))
        governance_sources = as_dict(surface.get("publication_governance_sources"))
        status = capability_card_status_from_specialization(surface)
        configured_path_count = int(config.get("path_count") or 0)
        schema_count = int(schema_inventory.get("schema_count") or 0)
        promotion_packet_count = int(artifacts.get("promotion_packet_count") or 0)
        evidence_ledger_count = int(artifacts.get("evidence_ledger_count") or 0)
        benchmark_adapter_counts = as_dict(config.get("benchmark_adapter_counts"))
        rollback_policy_counts = as_dict(config.get("rollback_policy_counts"))
        governance_source_count = bool_count(governance_sources)
        proof_verdicts = as_dict(surface.get("proof_sources"))
        trust = capability_trust_fields(
            status=status,
            compiled_proofs={
                "schema_present": schema_count > 0,
                "configured_paths_present": configured_path_count > 0,
                "promotion_packets_present": promotion_packet_count > 0,
                "evidence_ledgers_present": evidence_ledger_count > 0,
                "benchmark_adapter_config_present": bool(benchmark_adapter_counts),
                "rollback_policy_config_present": bool(rollback_policy_counts),
                "publication_governance_sources_present": governance_source_count > 0,
                "trace_refs_present": False,
                "rollback_refs_present": as_dict(proof_verdicts.get("rollback")).get("status") != "missing",
                "publication_approval_present": as_dict(proof_verdicts.get("publication")).get("status")
                == "passed",
            },
            trust_basis=[
                basis
                for basis, present in (
                    ("schema_present", schema_count > 0),
                    ("configured_paths_present", configured_path_count > 0),
                    ("promotion_packets_present", promotion_packet_count > 0),
                    ("evidence_ledgers_present", evidence_ledger_count > 0),
                    ("benchmark_adapter_config_present", bool(benchmark_adapter_counts)),
                    ("rollback_policy_config_present", bool(rollback_policy_counts)),
                    ("publication_governance_source_present", governance_source_count > 0),
                )
                if present
            ],
            proof_verdicts=proof_verdicts,
            required_proofs=SPECIALIZATION_REQUIRED_PROOF_LABELS,
        )
        cards.append(
            {
                "schema_version": CAPABILITY_CARD_SCHEMA,
                "id": f"specialization-path:{repo}",
                "name": f"{repo} specialization path",
                "owner_repo": repo,
                "surface_type": "specialization-path",
                "status": status,
                **trust,
                "requested_authority": ["local_files_read", "review_only"],
                "memory_policy": "selective_or_surface_defined",
                "evidence_summary": {
                    "configured_path_count": configured_path_count,
                    "schema_count": schema_count,
                    "promotion_packet_count": promotion_packet_count,
                    "evidence_ledger_count": evidence_ledger_count,
                },
                "benchmark_summary": {
                    "loop_kind_counts": as_dict(config.get("loop_kind_counts")),
                    "benchmark_adapter_counts": benchmark_adapter_counts,
                    "evolution_mode_counts": as_dict(config.get("evolution_mode_counts")),
                    "rollback_policy_counts": rollback_policy_counts,
                },
                "review_summary": {
                    "publication_governance_source_count": governance_source_count,
                    "publication_governance_sources": {
                        key: bool(as_dict(value).get("exists")) for key, value in sorted(governance_sources.items())
                    },
                },
                "trace_refs": [],
                "rollback_refs": [],
                "privacy_boundary": "Specialization metadata is exported without commands, labels, descriptions, or packet bodies.",
                "public_boundary": "Collective publication requires verified proof, approval gates, and rollback review.",
                "blockers": [
                    "Capability remains untrusted until every required proof domain passes.",
                    "Configured benchmark or rollback metadata is still unverified unless a pass/fail verdict exists.",
                    "Collective publication is blocked or missing unless publication and authority verdicts pass.",
                ],
                "next_action": "Resolve the first unsatisfied proof in proof_summary.unsatisfied_proofs.",
            }
        )

    return cards


def summarize_memory_kb_artifacts(builder_home: Path) -> dict[str, Any]:
    root = builder_home / "artifacts" / "spark-memory-kb"
    summary = count_files_under(root)
    if not root.exists():
        return summary

    lanes = {
        "current_state": root / "wiki" / "current-state",
        "events": root / "wiki" / "events",
        "sources": root / "wiki" / "sources",
        "syntheses": root / "wiki" / "syntheses",
    }
    summary["lane_counts"] = {name: count_files_under(path) for name, path in lanes.items()}
    summary["compile_latest_metadata"] = inspect_file_metadata(builder_home / "artifacts" / "spark-memory-kb-compile-latest.json")
    summary["sdk_state_metadata"] = inspect_file_metadata(builder_home / "artifacts" / "domain_chip_memory_sdk_state.json")
    return summary


def summarize_memory_run_artifacts(builder_home: Path) -> dict[str, Any]:
    artifacts = builder_home / "artifacts"
    prefixes = (
        "supervised-memory-qa",
        "telegram-memory-gauntlet",
        "telegram-memory-acceptance",
    )
    out: dict[str, Any] = {
        "path": str(artifacts),
        "exists": artifacts.exists(),
        "redaction": "run directory counts and timestamps only; run names and payloads omitted",
        "prefixes": {},
    }
    if not artifacts.exists():
        return out

    try:
        for prefix in prefixes:
            runs = [child for child in artifacts.iterdir() if child.is_dir() and child.name.startswith(prefix)]
            latest_mtime = max((child.stat().st_mtime for child in runs), default=None)
            out["prefixes"][prefix] = {
                "run_count": len(runs),
                "latest_modified_at": (
                    datetime.fromtimestamp(latest_mtime, timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z")
                    if latest_mtime is not None
                    else None
                ),
            }
    except OSError as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def memory_review_item(
    *,
    item_id: str,
    severity: str,
    category: str,
    owner_repo: str,
    source_surface: str,
    reason_code: str,
    recommended_action: str,
    count: int,
    target_kind: str = "aggregate_bucket",
    target_ref: str | None = None,
    request_id_present: bool | None = None,
    trace_ref_present: bool | None = None,
    source_family: str | None = None,
    authority: str | None = None,
    movement_state: str | None = None,
    memory_role: str | None = None,
    retention_class: str | None = None,
) -> dict[str, Any]:
    operator_paths = memory_review_operator_paths(
        category=category,
        owner_repo=owner_repo,
        source_surface=source_surface,
        movement_state=movement_state,
        retention_class=retention_class,
        authority=authority,
    )
    return {
        "id": item_id,
        "severity": severity,
        "category": category,
        "owner_repo": owner_repo,
        "source_surface": source_surface,
        "target_kind": target_kind,
        "target_ref": target_ref,
        "request_id_present": request_id_present,
        "trace_ref_present": trace_ref_present,
        "source_family": source_family,
        "authority": authority,
        "movement_state": movement_state,
        "memory_role": memory_role,
        "retention_class": retention_class,
        "salience_score_present": None,
        "message_preview_present": False,
        "count": int(count or 0),
        "reason_code": reason_code,
        "recommended_action": recommended_action,
        "verification_command": "spark os memory --json",
        "operator_paths": operator_paths,
    }


def memory_review_operator_paths(
    *,
    category: str,
    owner_repo: str,
    source_surface: str,
    movement_state: str | None,
    retention_class: str | None,
    authority: str | None,
) -> dict[str, Any]:
    provenance_by_category = {
        "trace_join": "Builder black-box trace join and memory movement export",
        "candidate_review": "Builder approval inbox or memory dashboard candidate lane",
        "privacy_redaction": "Spark OS compiler redaction report",
        "authority_boundary": "domain-chip-memory movement contract and source hierarchy",
        "current_state_audit": "domain-chip-memory current-state provenance lane",
        "promotion_audit": "domain-chip-memory promotion and rollback audit lane",
        "kb_snapshot_review": "spark-memory-quality-dashboard current-state KB panel",
        "movement_export": "Builder metadata-only memory movement status export",
    }
    stale_current_by_category = {
        "trace_join": "blocked_until_trace_join_exists",
        "candidate_review": "candidate_until_source_review_promotes_or_rejects",
        "privacy_redaction": "not_a_memory_truth_lane",
        "authority_boundary": "supporting_rows_cannot_override_current_state",
        "current_state_audit": "authoritative_current_requires_freshness_and_scope_check",
        "promotion_audit": "promoted_rows_need_periodic_stale_current_revalidation",
        "kb_snapshot_review": "current_state_snapshot_requires_dashboard_source_check",
        "movement_export": "unavailable_until_source_export_is_supported",
    }
    purge_by_category = {
        "trace_join": "no_purge_from_cockpit_repair_trace_context_first",
        "candidate_review": "source_builder_approval_inbox_reject_or_archive",
        "privacy_redaction": "compiler_omission_only_no_memory_mutation",
        "authority_boundary": "source_domain_chip_memory_decay_or_demote_gate",
        "current_state_audit": "source_domain_chip_memory_supersede_or_stale_preserve_gate",
        "promotion_audit": "source_domain_chip_memory_rollback_or_decay_gate",
        "kb_snapshot_review": "source_memory_dashboard_rebuild_or_review_queue",
        "movement_export": "source_builder_export_repair",
    }
    return {
        "source_owner": owner_repo,
        "source_surface": source_surface,
        "provenance_drilldown": provenance_by_category.get(category, source_surface),
        "stale_current_adjudication": stale_current_by_category.get(
            category,
            "source_owner_must_adjudicate_before_memory_truth_changes",
        ),
        "purge_or_decay_path": purge_by_category.get(category, "source_owner_review_required"),
        "cockpit_action": "read_only_observe_and_route",
        "movement_state": movement_state,
        "retention_class": retention_class,
        "authority": authority,
    }


def build_memory_review_queue(memory_index: dict[str, Any]) -> dict[str, Any]:
    safe_status = as_dict(memory_index.get("safe_status_export"))
    status = as_dict(safe_status.get("status"))
    builder_memory_tables = as_dict(memory_index.get("builder_memory_tables"))
    memory_lane_trace_join = as_dict(builder_memory_tables.get("memory_lane_trace_join"))
    movement_counts = as_dict(status.get("movement_counts"))
    authority_counts = as_dict(status.get("authority_counts"))
    source_family_counts = as_dict(status.get("source_family_counts"))
    record_counts = as_dict(status.get("record_counts"))
    kb_artifacts = as_dict(memory_index.get("memory_kb_artifacts"))
    kb_lanes = as_dict(kb_artifacts.get("lane_counts"))
    current_state_lane = as_dict(kb_lanes.get("current_state"))
    items: list[dict[str, Any]] = []

    export_status = str(status.get("status") or "missing")
    row_count = int(status.get("row_count") or 0)
    if export_status != "supported":
        items.append(
            memory_review_item(
                item_id="memory-export-not-supported",
                severity="critical",
                category="movement_export",
                owner_repo="spark-intelligence-builder",
                source_surface="Builder memory movement export",
                reason_code="memory_movement_export_not_supported",
                recommended_action="Restore Builder's metadata-only memory movement status export before Cockpit review.",
                count=1,
                target_kind="status_export",
                target_ref="memory-movement-status",
            )
        )

    captured_count = int(movement_counts.get("captured") or 0)
    if captured_count:
        items.append(
            memory_review_item(
                item_id="captured-memory-needs-review",
                severity="high",
                category="candidate_review",
                owner_repo="spark-intelligence-builder",
                source_surface="Builder memory movement export",
                reason_code="captured_candidates_present",
                recommended_action="Review captured candidates in the source memory dashboard or Builder approval inbox without exporting proposed text.",
                count=captured_count,
                movement_state="captured",
                retention_class="candidate",
            )
        )

    promoted_count = int(movement_counts.get("promoted") or 0)
    if promoted_count:
        items.append(
            memory_review_item(
                item_id="promoted-memory-audit",
                severity="medium",
                category="promotion_audit",
                owner_repo="domain-chip-memory",
                source_surface="domain-chip-memory movement contract",
                reason_code="promoted_rows_need_periodic_audit",
                recommended_action="Audit promoted-memory buckets against provenance, evaluation, approval, and rollback gates.",
                count=promoted_count,
                movement_state="promoted",
                retention_class="durable",
            )
        )

    supporting_count = int(authority_counts.get("supporting_not_authoritative") or 0)
    if supporting_count:
        items.append(
            memory_review_item(
                item_id="supporting-memory-boundary-review",
                severity="medium",
                category="authority_boundary",
                owner_repo="domain-chip-memory",
                source_surface="domain-chip-memory movement contract",
                reason_code="supporting_rows_must_not_override_authoritative_memory",
                recommended_action="Confirm supporting/advisory rows remain non-authoritative and cannot override current-state memory.",
                count=supporting_count,
                source_family="episodic_summary",
                authority="supporting_not_authoritative",
                retention_class="supporting",
            )
        )

    current_authoritative_count = int(authority_counts.get("authoritative_current") or 0)
    if current_authoritative_count:
        items.append(
            memory_review_item(
                item_id="authoritative-current-memory-audit",
                severity="medium",
                category="current_state_audit",
                owner_repo="domain-chip-memory",
                source_surface="domain-chip-memory movement contract",
                reason_code="authoritative_current_rows_present",
                recommended_action="Spot-check authoritative current-state buckets for source scope, freshness, and rollback availability.",
                count=current_authoritative_count,
                source_family="current_state",
                authority="authoritative_current",
                retention_class="current_state",
            )
        )

    current_state_file_count = int(current_state_lane.get("file_count") or 0)
    if current_state_file_count:
        items.append(
            memory_review_item(
                item_id="memory-kb-current-state-files-review",
                severity="low",
                category="kb_snapshot_review",
                owner_repo="spark-memory-quality-dashboard",
                source_surface="Spark memory KB artifacts",
                reason_code="current_state_kb_files_present",
                recommended_action="Use the memory dashboard source module for current-state provenance drilldown; Cockpit should keep file names and bodies hidden.",
                count=current_state_file_count,
                target_kind="kb_lane",
                target_ref="current_state",
                source_family="current_state",
                retention_class="current_state",
            )
        )

    raw_hint_count = int(safe_status.get("raw_hint_key_count") or 0)
    if raw_hint_count:
        items.append(
            memory_review_item(
                item_id="memory-export-redaction-review",
                severity="high",
                category="privacy_redaction",
                owner_repo="spark-cli",
                source_surface="Spark OS compiler",
                reason_code="raw_memory_hint_keys_omitted",
                recommended_action="Keep omitted raw-hint fields out of OS artifacts and verify no review queue item includes memory body fields.",
                count=raw_hint_count,
                target_kind="compiler_redaction",
                target_ref="safe_status_export",
            )
        )

    trace_join_row_count = int(memory_lane_trace_join.get("row_count") or 0)
    trace_ref_present_count = int(memory_lane_trace_join.get("trace_ref_present_count") or 0)
    missing_trace_ref_count = int(memory_lane_trace_join.get("missing_trace_ref_count") or 0)
    if row_count and not trace_ref_present_count:
        items.append(
            memory_review_item(
                item_id="memory-trace-join-not-compiled",
                severity="high",
                category="trace_join",
                owner_repo="spark-intelligence-builder",
                source_surface="Builder memory movement export",
                reason_code="memory_rows_lack_compiled_trace_join",
                recommended_action="Join memory movement buckets to trace ids after Builder event envelopes carry stable trace refs.",
                count=row_count,
                request_id_present=None,
                trace_ref_present=None,
                target_kind="movement_rows",
            )
        )
    elif trace_join_row_count and missing_trace_ref_count:
        items.append(
            memory_review_item(
                item_id="memory-trace-join-partial",
                severity="medium",
                category="trace_join",
                owner_repo="spark-intelligence-builder",
                source_surface="Builder memory_lane_records",
                reason_code="memory_lane_rows_partially_missing_trace_ref",
                recommended_action=(
                    "Keep routing new memory preflight and promotion events through Builder event envelopes; "
                    "audit legacy rows before any cleanup."
                ),
                count=missing_trace_ref_count,
                request_id_present=bool(memory_lane_trace_join.get("request_id_present_count")),
                trace_ref_present=True,
                target_kind="memory_lane_records",
            )
        )

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    items = sorted(
        items,
        key=lambda item: (
            severity_rank.get(str(item.get("severity")), 9),
            -int(item.get("count") or 0),
            str(item.get("id")),
        ),
    )
    return {
        "schema_version": MEMORY_REVIEW_QUEUE_SCHEMA,
        "generated_at": utc_now(),
        "authority": "observability_non_authoritative",
        "source": "spark.memory_movement_index.compiled.v0",
        "redaction": "aggregate metadata only; proposed text, memory bodies, relation fields, evidence payloads, and message previews omitted",
        "counts": {
            "item_count": len(items),
            "movement_row_count": row_count,
            "movement_counts": movement_counts,
            "authority_counts": authority_counts,
            "source_family_counts": source_family_counts,
            "record_counts": record_counts,
            "memory_lane_trace_join": {
                "status": memory_lane_trace_join.get("status"),
                "row_count": trace_join_row_count,
                "request_id_present_count": memory_lane_trace_join.get("request_id_present_count"),
                "trace_ref_present_count": trace_ref_present_count,
                "missing_trace_ref_count": missing_trace_ref_count,
            },
        },
        "items": items,
        "non_override_rules": as_list(status.get("non_override_rules")),
    }


def inspect_builder_memory_tables(builder_home: Path) -> dict[str, Any]:
    db_path = builder_home / "state.db"
    out: dict[str, Any] = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "redaction": "memory-related table names and row counts only; no row contents read",
    }
    if not db_path.exists():
        return out

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table' order by name")]
            memory_tables = [table for table in tables if "memory" in table.lower()]
            out["table_count"] = len(memory_tables)
            out["tables"] = {}
            for table in memory_tables:
                count = conn.execute(f'select count(*) from "{table}"').fetchone()[0]
                out["tables"][table] = {"row_count": int(count)}
            if "memory_lane_records" in memory_tables:
                out["memory_lane_trace_join"] = inspect_memory_lane_trace_join(conn)
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def inspect_memory_lane_trace_join(conn: sqlite3.Connection) -> dict[str, Any]:
    out: dict[str, Any] = {
        "source": "memory_lane_records",
        "redaction": "aggregate trace coverage only; row ids, trace ids, evidence JSON, memory bodies, and source refs omitted",
    }
    columns = [row[1] for row in conn.execute("pragma table_info(memory_lane_records)")]
    required = {"request_id", "trace_ref", "artifact_lane", "status"}
    missing = sorted(required - set(columns))
    if missing:
        out["status"] = "missing_columns"
        out["missing_columns"] = missing
        return out

    row_count = int(conn.execute("select count(*) from memory_lane_records").fetchone()[0])
    request_id_present_count = int(
        conn.execute(
            "select count(*) from memory_lane_records where request_id is not null and trim(request_id) <> ''"
        ).fetchone()[0]
    )
    trace_ref_present_count = int(
        conn.execute(
            "select count(*) from memory_lane_records where trace_ref is not null and trim(trace_ref) <> ''"
        ).fetchone()[0]
    )
    distinct_trace_ref_count = int(
        conn.execute(
            "select count(distinct trace_ref) from memory_lane_records where trace_ref is not null and trim(trace_ref) <> ''"
        ).fetchone()[0]
    )
    lane_rows = conn.execute(
        """
        select
            coalesce(nullif(trim(artifact_lane), ''), 'unknown') as artifact_lane,
            coalesce(nullif(trim(status), ''), 'unknown') as status,
            count(*) as row_count,
            sum(case when request_id is not null and trim(request_id) <> '' then 1 else 0 end) as request_id_present_count,
            sum(case when trace_ref is not null and trim(trace_ref) <> '' then 1 else 0 end) as trace_ref_present_count
        from memory_lane_records
        group by coalesce(nullif(trim(artifact_lane), ''), 'unknown'), coalesce(nullif(trim(status), ''), 'unknown')
        order by row_count desc
        limit 25
        """
    ).fetchall()

    def get_val(r, key, idx):
        if isinstance(r, sqlite3.Row) or (hasattr(r, "keys") and key in r.keys()):
            return r[key]
        return r[idx]

    out.update(
        {
            "status": "present" if trace_ref_present_count else "missing_trace_refs",
            "row_count": row_count,
            "request_id_present_count": request_id_present_count,
            "trace_ref_present_count": trace_ref_present_count,
            "missing_request_id_count": max(0, row_count - request_id_present_count),
            "missing_trace_ref_count": max(0, row_count - trace_ref_present_count),
            "distinct_trace_ref_count": distinct_trace_ref_count,
            "trace_ref_coverage_ratio": round(trace_ref_present_count / row_count, 4) if row_count else 0.0,
            "request_id_coverage_ratio": round(request_id_present_count / row_count, 4) if row_count else 0.0,
            "lane_status_counts": [
                {
                    "artifact_lane": str(get_val(row, "artifact_lane", 0)),
                    "status": str(get_val(row, "status", 1)),
                    "row_count": int(get_val(row, "row_count", 2) or 0),
                    "request_id_present_count": int(get_val(row, "request_id_present_count", 3) or 0),
                    "trace_ref_present_count": int(get_val(row, "trace_ref_present_count", 4) or 0),
                }
                for row in lane_rows
            ],
        }
    )
    return out


def inspect_builder_event_trace(builder_home: Path) -> dict[str, Any]:
    db_path = builder_home / "state.db"
    out: dict[str, Any] = {
        "source": "builder_events",
        "path": str(db_path),
        "exists": db_path.exists(),
        "redaction": "aggregate counts only; event summaries, facts, and provenance JSON omitted",
    }
    if not db_path.exists():
        return out
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table'")]
            if "builder_events" not in tables:
                out["table_exists"] = False
                return out
            out["table_exists"] = True
            out["row_count"] = int(conn.execute("select count(*) from builder_events").fetchone()[0])
            out["created_at_min"] = conn.execute("select min(created_at) from builder_events").fetchone()[0]
            out["created_at_max"] = conn.execute("select max(created_at) from builder_events").fetchone()[0]
            for column in ("event_type", "truth_kind", "target_surface", "component", "evidence_lane", "severity", "status"):
                rows = conn.execute(
                    f'select "{column}" as value, count(*) as n from builder_events group by "{column}" order by n desc limit 40'
                ).fetchall()
                out[f"{column}_counts"] = {str(row["value"]): int(row["n"]) for row in rows}
            for column in ("trace_ref", "request_id", "correlation_id", "parent_event_id"):
                missing = conn.execute(
                    f'select count(*) from builder_events where "{column}" is null or trim("{column}") = ""'
                ).fetchone()[0]
                out[f"missing_{column}_count"] = int(missing)
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def inspect_builder_event_samples(builder_home: Path, *, limit: int = 40) -> dict[str, Any]:
    db_path = builder_home / "state.db"
    out: dict[str, Any] = {
        "source": "builder_events",
        "path": str(db_path),
        "exists": db_path.exists(),
        "limit": limit,
        "redaction": "allowlisted event metadata only; summaries, facts JSON, provenance JSON, and message text omitted",
    }
    if not db_path.exists():
        return out

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table'")]
            if "builder_events" not in tables:
                out["table_exists"] = False
                return out
            out["table_exists"] = True
            columns = [row[1] for row in conn.execute("pragma table_info(builder_events)")]
            selected = [column for column in SAFE_BUILDER_EVENT_SAMPLE_COLUMNS if column in columns]
            if not selected:
                out["events"] = []
                out["sample_count"] = 0
                return out

            quoted = ", ".join(f'"{column}"' for column in selected)
            order_column = "created_at" if "created_at" in columns else "rowid"
            rows = conn.execute(
                f'select {quoted} from builder_events order by "{order_column}" desc limit ?',
                (max(0, min(int(limit), 100)),),
            ).fetchall()
            events: list[dict[str, Any]] = []
            trace_counts: Counter[str] = Counter()
            for row in rows:
                event: dict[str, Any] = {}
                for column in selected:
                    event[column] = safe_builder_event_value(column, row[column])
                trace_ref = str(event.get("trace_ref") or "").strip()
                trace_counts[trace_ref or "[missing]"] += 1
                events.append(event)
            out["events"] = events
            out["sample_count"] = len(events)
            out["top_trace_refs"] = [
                {"trace_ref": trace_ref, "event_count": count}
                for trace_ref, count in trace_counts.most_common(20)
                if trace_ref != "[missing]"
            ]
            out["missing_trace_ref_count"] = int(trace_counts.get("[missing]", 0))
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def selected_builder_event_columns(columns: list[str]) -> list[str]:
    return [column for column in SAFE_BUILDER_EVENT_SAMPLE_COLUMNS if column in columns]


def sanitize_builder_event_row(row: sqlite3.Row, selected: list[str]) -> dict[str, Any]:
    event: dict[str, Any] = {}
    for column in selected:
        event[column] = safe_builder_event_value(column, row[column])
    return event


def inspect_builder_trace_groups(
    builder_home: Path,
    *,
    group_limit: int = 12,
    events_per_trace: int = 12,
    edge_sample_limit: int = 24,
) -> dict[str, Any]:
    db_path = builder_home / "state.db"
    out: dict[str, Any] = {
        "source": "builder_events",
        "path": str(db_path),
        "exists": db_path.exists(),
        "group_limit": group_limit,
        "events_per_trace": events_per_trace,
        "edge_sample_limit": edge_sample_limit,
        "redaction": (
            "trace grouping over allowlisted event metadata only; summaries, facts JSON, "
            "provenance JSON, and raw event bodies omitted"
        ),
    }
    if not db_path.exists():
        return out

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table'")]
            if "builder_events" not in tables:
                out["table_exists"] = False
                return out
            out["table_exists"] = True
            columns = [row[1] for row in conn.execute("pragma table_info(builder_events)")]
            if "trace_ref" not in columns:
                out["trace_ref_column_exists"] = False
                return out
            selected = selected_builder_event_columns(columns)
            if not selected:
                out["groups"] = []
                out["group_count"] = 0
                return out

            group_rows = conn.execute(
                """
                select trace_ref, count(*) as event_count, min(created_at) as first_seen_at, max(created_at) as last_seen_at
                from builder_events
                where trace_ref is not null and trim(trace_ref) != ''
                group by trace_ref
                order by max(created_at) desc
                limit ?
                """,
                (max(0, min(int(group_limit), 50)),),
            ).fetchall()
            quoted = ", ".join(f'"{column}"' for column in selected)
            groups = []
            for group_row in group_rows:
                trace_ref = str(group_row["trace_ref"] or "")
                event_rows = conn.execute(
                    f"""
                    select {quoted}
                    from builder_events
                    where trace_ref = ?
                    order by created_at asc
                    limit ?
                    """,
                    (trace_ref, max(0, min(int(events_per_trace), 50))),
                ).fetchall()
                groups.append(
                    {
                        "trace_ref": safe_builder_event_value("trace_ref", trace_ref),
                        "event_count": int(group_row["event_count"] or 0),
                        "first_seen_at": group_row["first_seen_at"],
                        "last_seen_at": group_row["last_seen_at"],
                        "topology": builder_trace_topology(
                            conn,
                            columns,
                            trace_ref=trace_ref,
                            event_count=int(group_row["event_count"] or 0),
                            edge_sample_limit=edge_sample_limit,
                        ),
                        "events": [sanitize_builder_event_row(row, selected) for row in event_rows],
                    }
                )
            out["groups"] = groups
            out["group_count"] = len(groups)
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def builder_trace_topology(
    conn: sqlite3.Connection,
    columns: list[str],
    *,
    trace_ref: str,
    event_count: int,
    edge_sample_limit: int,
) -> dict[str, Any]:
    if not {"event_id", "parent_event_id"}.issubset(columns):
        return {"available": False, "reason": "event_id_or_parent_event_id_missing"}

    parent_link_count = conn.execute(
        """
        select count(*)
        from builder_events
        where trace_ref = ?
          and parent_event_id is not null
          and trim(parent_event_id) != ''
        """,
        (trace_ref,),
    ).fetchone()[0]
    root_event_count = conn.execute(
        """
        select count(*)
        from builder_events
        where trace_ref = ?
          and (parent_event_id is null or trim(parent_event_id) = '')
        """,
        (trace_ref,),
    ).fetchone()[0]
    orphan_parent_count = conn.execute(
        """
        select count(*)
        from builder_events child
        where child.trace_ref = ?
          and child.parent_event_id is not null
          and trim(child.parent_event_id) != ''
          and not exists (
            select 1 from builder_events parent where parent.event_id = child.parent_event_id
          )
        """,
        (trace_ref,),
    ).fetchone()[0]
    order_expr = 'child."created_at"' if "created_at" in columns else "child.rowid"
    child_event_type_expr = 'child."event_type"' if "event_type" in columns else "null"
    child_component_expr = 'child."component"' if "component" in columns else "null"
    parent_event_type_expr = 'parent."event_type"' if "event_type" in columns else "null"
    edge_rows = conn.execute(
        f"""
        select
          child.event_id as child_event_id,
          child.parent_event_id as parent_event_id,
          {child_event_type_expr} as child_event_type,
          {child_component_expr} as child_component,
          {parent_event_type_expr} as parent_event_type,
          case when parent.event_id is null then 0 else 1 end as parent_exists,
          case when parent.event_id is not null and parent.trace_ref = child.trace_ref then 1 else 0 end as parent_in_same_trace
        from builder_events child
        left join builder_events parent on parent.event_id = child.parent_event_id
        where child.trace_ref = ?
          and child.parent_event_id is not null
          and trim(child.parent_event_id) != ''
        order by {order_expr} asc
        limit ?
        """,
        (trace_ref, max(0, min(int(edge_sample_limit), 50))),
    ).fetchall()
    return {
        "available": True,
        "event_count": int(event_count or 0),
        "root_event_count": int(root_event_count or 0),
        "parent_link_count": int(parent_link_count or 0),
        "orphan_parent_event_count": int(orphan_parent_count or 0),
        "edge_sample_count": len(edge_rows),
        "edge_sample": [
            {
                "parent_event_id": safe_builder_event_value("parent_event_id", row["parent_event_id"]),
                "child_event_id": safe_builder_event_value("event_id", row["child_event_id"]),
                "parent_event_type": safe_builder_event_value("event_type", row["parent_event_type"]),
                "child_event_type": safe_builder_event_value("event_type", row["child_event_type"]),
                "child_component": safe_builder_event_value("component", row["child_component"]),
                "parent_exists": bool(row["parent_exists"]),
                "parent_in_same_trace": bool(row["parent_in_same_trace"]),
            }
            for row in edge_rows
        ],
        "claim_boundary": "Trace topology is derived from allowlisted event ids and metadata only; it is not event body evidence.",
    }


def inspect_builder_trace_health(builder_home: Path) -> dict[str, Any]:
    db_path = builder_home / "state.db"
    out: dict[str, Any] = {
        "source": "builder_events",
        "path": str(db_path),
        "exists": db_path.exists(),
        "redaction": "aggregate trace health counts only; no event bodies, summaries, facts, or provenance read",
    }
    if not db_path.exists():
        return out

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table'")]
            if "builder_events" not in tables:
                out["table_exists"] = False
                return out
            out["table_exists"] = True
            columns = [row[1] for row in conn.execute("pragma table_info(builder_events)")]
            group_columns = [
                column
                for column in (
                    "component",
                    "event_type",
                    "reason_code",
                    "status",
                    "severity",
                    "target_surface",
                    "evidence_lane",
                )
                if column in columns
            ]
            total = int(conn.execute("select count(*) from builder_events").fetchone()[0])
            out["row_count"] = total
            for column in ("trace_ref", "request_id", "parent_event_id"):
                if column in columns:
                    missing = conn.execute(
                        f'select count(*) from builder_events where "{column}" is null or trim("{column}") = ""'
                    ).fetchone()[0]
                    out[f"missing_{column}_count"] = int(missing)
            if "trace_ref" in columns:
                trace_group_count = conn.execute(
                    "select count(distinct trace_ref) from builder_events where trace_ref is not null and trim(trace_ref) != ''"
                ).fetchone()[0]
                out["trace_group_count"] = int(trace_group_count)
                if "created_at" in columns:
                    out["recent_windows"] = _builder_trace_recent_windows(conn)
                if group_columns:
                    expressions = [
                        f"coalesce(nullif(trim(\"{column}\"), ''), '[missing]') as \"{column}\""
                        for column in group_columns
                    ]
                    group_by = ", ".join(f'"{column}"' for column in group_columns)
                    rows = conn.execute(
                        f"""
                        select {", ".join(expressions)}, count(*) as event_count
                        from builder_events
                        where trace_ref is null or trim(trace_ref) = ''
                        group by {group_by}
                        order by event_count desc
                        limit 30
                        """
                    ).fetchall()
                    row_items = []
                    for row in rows:
                        values = {
                            column: str(row[index] or "[missing]") for index, column in enumerate(group_columns)
                        }
                        row_items.append(
                            {
                                **values,
                                "event_count": int(row[len(group_columns)] or 0),
                                **builder_trace_missing_source_state(
                                    conn,
                                    group_columns=group_columns,
                                    values=values,
                                    columns=columns,
                                ),
                            }
                        )
                    out["missing_trace_ref_sources"] = {
                        "group_by": group_columns,
                        "limit": 30,
                        "redaction": "aggregate counts grouped by allowlisted event metadata only",
                        "rows": row_items,
                    }
            if {"severity", "status"}.issubset(columns):
                high_open = conn.execute(
                    """
                    select count(*) from builder_events
                    where lower(coalesce(severity, '')) in ('high', 'critical')
                      and lower(coalesce(status, '')) in ('open', 'failed', 'error', 'blocked')
                    """
                ).fetchone()[0]
                out["high_severity_open_count"] = int(high_open)
                if group_columns:
                    expressions = [
                        f"coalesce(nullif(trim(\"{column}\"), ''), '[missing]') as \"{column}\""
                        for column in group_columns
                    ]
                    group_by = ", ".join(f'"{column}"' for column in group_columns)
                    rows = conn.execute(
                        f"""
                        select {", ".join(expressions)}, count(*) as event_count
                        from builder_events
                        where lower(coalesce(severity, '')) in ('high', 'critical')
                          and lower(coalesce(status, '')) in ('open', 'failed', 'error', 'blocked')
                        group by {group_by}
                        order by event_count desc
                        limit 30
                        """
                    ).fetchall()
                    row_items = []
                    for row in rows:
                        values = {
                            column: str(row[index] or "[missing]") for index, column in enumerate(group_columns)
                        }
                        row_items.append(
                            {
                                **values,
                                "event_count": int(row[len(group_columns)] or 0),
                                **builder_high_severity_source_state(
                                    conn,
                                    group_columns=group_columns,
                                    values=values,
                                    columns=columns,
                                ),
                            }
                        )
                    out["high_severity_open_sources"] = {
                        "group_by": group_columns,
                        "limit": 30,
                        "redaction": "aggregate high-severity counts grouped by allowlisted event metadata only",
                        "rows": row_items,
                    }
            if {"event_id", "parent_event_id"}.issubset(columns):
                orphaned = conn.execute(
                    """
                    select count(*) from builder_events child
                    where child.parent_event_id is not null
                      and trim(child.parent_event_id) != ''
                      and not exists (
                        select 1 from builder_events parent where parent.event_id = child.parent_event_id
                      )
                    """
                ).fetchone()[0]
                out["orphan_parent_event_id_count"] = int(orphaned)
                orphan_columns = [
                    column
                    for column in ("component", "event_type", "status", "severity", "target_surface", "evidence_lane")
                    if column in columns
                ]
                if orphan_columns:
                    out["orphan_parent_event_sources"] = builder_trace_orphan_parent_sources(
                        conn,
                        orphan_columns,
                    )
            flags = []
            if int(out.get("missing_trace_ref_count") or 0):
                flags.append("missing_trace_refs")
            if int(out.get("orphan_parent_event_id_count") or 0):
                flags.append("orphan_parent_event_ids")
            if int(out.get("high_severity_open_count") or 0):
                flags.append("open_high_severity_events")
            out["health_flags"] = flags
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def builder_trace_orphan_parent_sources(conn: sqlite3.Connection, group_columns: list[str]) -> dict[str, Any]:
    expressions = [
        f"coalesce(nullif(trim(child.\"{column}\"), ''), '[missing]') as \"{column}\""
        for column in group_columns
    ]
    group_by = ", ".join(f'"{column}"' for column in group_columns)
    rows = conn.execute(
        f"""
        select {", ".join(expressions)}, count(*) as event_count
        from builder_events child
        where child.parent_event_id is not null
          and trim(child.parent_event_id) != ''
          and not exists (
            select 1 from builder_events parent where parent.event_id = child.parent_event_id
          )
        group by {group_by}
        order by event_count desc
        limit 30
        """
    ).fetchall()
    return {
        "group_by": group_columns,
        "limit": 30,
        "redaction": "aggregate orphan-parent counts grouped by allowlisted event metadata only",
        "rows": [
            {
                **{column: str(row[index] or "[missing]") for index, column in enumerate(group_columns)},
                "event_count": int(row[len(group_columns)] or 0),
            }
            for row in rows
        ],
    }


def _builder_trace_recent_windows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    windows = (("1h", timedelta(hours=1)), ("24h", timedelta(hours=24)), ("7d", timedelta(days=7)))
    rows: list[dict[str, Any]] = []
    for label, delta in windows:
        threshold = (now - delta).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        total = conn.execute(
            "select count(*) from builder_events where created_at >= ?",
            (threshold,),
        ).fetchone()[0]
        missing = conn.execute(
            """
            select count(*)
            from builder_events
            where created_at >= ?
              and (trace_ref is null or trim(trace_ref) = '')
            """,
            (threshold,),
        ).fetchone()[0]
        total_count = int(total or 0)
        missing_count = int(missing or 0)
        rows.append(
            {
                "window": label,
                "threshold": threshold,
                "row_count": total_count,
                "missing_trace_ref_count": missing_count,
                "missing_trace_ref_ratio": round(missing_count / total_count, 4) if total_count else 0.0,
            }
        )
    return rows


def builder_trace_missing_source_state(
    conn: sqlite3.Connection,
    *,
    group_columns: list[str],
    values: dict[str, str],
    columns: list[str],
) -> dict[str, Any]:
    if "trace_ref" not in columns:
        return {}

    where_sql, params = builder_trace_group_where(group_columns, values)
    order_column = "created_at" if "created_at" in columns else "rowid"
    latest = conn.execute(
        f"""
        select trace_ref, request_id{', created_at' if 'created_at' in columns else ''}
        from builder_events
        where {where_sql}
        order by "{order_column}" desc
        limit 1
        """,
        params,
    ).fetchone()
    out: dict[str, Any] = {
        "latest_event_trace_state": "unknown",
        "latest_event_trace_ref_present": False,
        "latest_event_request_id_present": False,
    }
    if latest is not None:
        latest_trace_ref = str(latest[0] or "").strip()
        latest_request_id = str(latest[1] or "").strip()
        out["latest_event_trace_ref_present"] = bool(latest_trace_ref)
        out["latest_event_request_id_present"] = bool(latest_request_id)
        out["latest_event_trace_state"] = "trace_ref_present" if latest_trace_ref else "missing_trace_ref"
        if "created_at" in columns:
            out["latest_event_created_at"] = str(latest[2] or "")

    if "created_at" in columns:
        now = datetime.now(timezone.utc)
        for label, delta in (("1h", timedelta(hours=1)), ("24h", timedelta(hours=24))):
            threshold = (now - delta).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            count_params = [threshold, *params]
            total = conn.execute(
                f"""
                select count(*)
                from builder_events
                where created_at >= ?
                  and {where_sql}
                """,
                count_params,
            ).fetchone()[0]
            missing = conn.execute(
                f"""
                select count(*)
                from builder_events
                where created_at >= ?
                  and {where_sql}
                  and (trace_ref is null or trim(trace_ref) = '')
                """,
                count_params,
            ).fetchone()[0]
            out[f"recent_{label}_row_count"] = int(total or 0)
            out[f"recent_{label}_missing_trace_ref_count"] = int(missing or 0)

    latest_clean = bool(out.get("latest_event_trace_ref_present"))
    recent_24h_missing = int(out.get("recent_24h_missing_trace_ref_count") or 0)
    if latest_clean and recent_24h_missing:
        out["repair_temporal_state"] = "latest_clean_historical_window_debt"
    elif latest_clean:
        out["repair_temporal_state"] = "latest_clean"
    elif latest is not None and int(out.get("recent_24h_row_count") or 0) == 0:
        out["repair_temporal_state"] = "stale_missing_trace_ref"
    elif latest is not None:
        out["repair_temporal_state"] = "latest_missing_trace_ref"
    else:
        out["repair_temporal_state"] = "unknown"
    return out


def builder_trace_group_where(group_columns: list[str], values: dict[str, str]) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    for column in group_columns:
        value = str(values.get(column) or "[missing]")
        if value == "[missing]":
            clauses.append(f'("{column}" is null or trim("{column}") = "")')
        else:
            clauses.append(f'coalesce(nullif(trim("{column}"), \'\'), \'[missing]\') = ?')
            params.append(value)
    return " and ".join(clauses) if clauses else "1 = 1", params


def builder_high_severity_source_state(
    conn: sqlite3.Connection,
    *,
    group_columns: list[str],
    values: dict[str, str],
    columns: list[str],
) -> dict[str, Any]:
    identity_columns = [
        column
        for column in group_columns
        if column not in {"status", "severity"} and column in columns
    ]
    if not identity_columns:
        identity_columns = [column for column in ("component", "event_type") if column in columns]
    where_sql, params = builder_trace_group_where(identity_columns, values)
    order_column = "created_at" if "created_at" in columns else "rowid"
    latest = conn.execute(
        f"""
        select status, severity, trace_ref, request_id{', created_at' if 'created_at' in columns else ''}
        from builder_events
        where {where_sql}
        order by "{order_column}" desc
        limit 1
        """,
        params,
    ).fetchone()
    out: dict[str, Any] = {
        "latest_lifecycle_state": "unknown",
        "latest_event_status": None,
        "latest_event_severity": None,
        "latest_event_trace_ref_present": False,
        "latest_event_request_id_present": False,
    }
    if latest is not None:
        latest_status = str(latest[0] or "").strip().lower()
        latest_severity = str(latest[1] or "").strip().lower()
        latest_trace_ref = str(latest[2] or "").strip()
        latest_request_id = str(latest[3] or "").strip()
        out["latest_event_status"] = latest_status or None
        out["latest_event_severity"] = latest_severity or None
        out["latest_event_trace_ref_present"] = bool(latest_trace_ref)
        out["latest_event_request_id_present"] = bool(latest_request_id)
        if "created_at" in columns:
            out["latest_event_created_at"] = str(latest[4] or "")
        if latest_status in {"resolved", "closed", "succeeded", "ok", "recorded"} and latest_severity in {
            "",
            "info",
            "low",
            "medium",
        }:
            out["latest_lifecycle_state"] = "latest_resolved"
        elif latest_status in {"open", "failed", "error", "blocked"} and latest_severity in {"high", "critical"}:
            out["latest_lifecycle_state"] = "latest_open_high_severity"
        else:
            out["latest_lifecycle_state"] = "latest_unknown"

    if "created_at" in columns:
        now = datetime.now(timezone.utc)
        for label, delta in (("1h", timedelta(hours=1)), ("24h", timedelta(hours=24))):
            threshold = (now - delta).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            count_params = [threshold, *params]
            total = conn.execute(
                f"""
                select count(*)
                from builder_events
                where created_at >= ?
                  and {where_sql}
                """,
                count_params,
            ).fetchone()[0]
            high_open = conn.execute(
                f"""
                select count(*)
                from builder_events
                where created_at >= ?
                  and {where_sql}
                  and lower(coalesce(severity, '')) in ('high', 'critical')
                  and lower(coalesce(status, '')) in ('open', 'failed', 'error', 'blocked')
                """,
                count_params,
            ).fetchone()[0]
            out[f"recent_{label}_row_count"] = int(total or 0)
            out[f"recent_{label}_high_open_count"] = int(high_open or 0)

    if (
        out.get("latest_lifecycle_state") == "latest_open_high_severity"
        and int(out.get("recent_24h_row_count") or 0) == 0
    ):
        out["lifecycle_temporal_state"] = "stale_open_high_severity"
    elif out.get("latest_lifecycle_state") == "latest_resolved":
        out["lifecycle_temporal_state"] = "latest_resolved"
    elif out.get("latest_lifecycle_state") == "latest_open_high_severity":
        out["lifecycle_temporal_state"] = "latest_open_high_severity"
    else:
        out["lifecycle_temporal_state"] = str(out.get("latest_lifecycle_state") or "unknown")
    return out


def build_modules(
    registry: dict[str, Any],
    installed: dict[str, Any],
    repos: list[dict[str, Any]],
    running: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    repo_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for repo in repos:
        for repo_id in repo_ids(repo):
            repo_by_id[repo_id].append(repo)

    ids = set(registry.get("modules", {}).keys()) | set(installed.keys()) | set(repo_by_id.keys())
    modules = []
    for module_id in sorted(ids):
        reg = as_dict(registry.get("modules", {}).get(module_id))
        inst = as_dict(installed.get(module_id))
        matching_repos = repo_by_id.get(module_id, [])
        primary_repo = matching_repos[0] if matching_repos else {}
        toml = as_dict(primary_repo.get("spark_toml"))
        modules.append(
            {
                "id": module_id,
                "summary": first_string(inst.get("summary"), reg.get("summary"), toml.get("description")),
                "plane": first_string(inst.get("plane"), toml.get("plane")),
                "kind": first_string(inst.get("kind"), toml.get("kind")),
                "version": first_string(inst.get("version"), toml.get("version")),
                "registry": reg or None,
                "installed": inst or None,
                "repos": [
                    {
                        "name": repo.get("name"),
                        "path": repo.get("path"),
                        "contract_files": repo.get("contract_files"),
                        "git": repo.get("git"),
                    }
                    for repo in matching_repos
                ],
                "provides_capabilities": as_list(toml.get("provides_capabilities")),
                "needs_modules": as_list(toml.get("needs_modules")),
                "running_instances": [
                    item
                    for item in running
                    if item.get("module") == module_id or str(item.get("id", "")).startswith(f"{module_id}:")
                ],
            }
        )
    return modules


def build_capability_catalog(repos: list[dict[str, Any]]) -> dict[str, Any]:
    chip_manifests = []
    module_capabilities = []
    skill_graphs = []
    contract_sources = []
    creator_system_surfaces = []
    specialization_path_surfaces = []

    for repo in repos:
        repo_path = Path(str(repo.get("path") or ""))
        chip = as_dict(repo.get("spark_chip"))
        if chip:
            chip_manifests.append(
                {
                    "repo": repo.get("name"),
                    "path": repo.get("path"),
                    "schema_version": chip.get("schema_version"),
                    "io_protocol": chip.get("io_protocol"),
                    "chip_name": chip.get("chip_name"),
                    "domain": chip.get("domain"),
                    "capability_count": len(as_list(chip.get("capabilities"))),
                    "capabilities": as_list(chip.get("capabilities")),
                    "task_topics": as_list(chip.get("task_topics")),
                    "frontier": chip.get("frontier"),
                }
            )

        toml = as_dict(repo.get("spark_toml"))
        caps = as_list(toml.get("provides_capabilities"))
        if caps:
            module_capabilities.append(
                {
                    "repo": repo.get("name"),
                    "module_name": toml.get("module_name"),
                    "plane": toml.get("plane"),
                    "capabilities": caps,
                }
            )

        skill_manifest = as_dict(repo.get("skill_manifest"))
        if skill_manifest:
            skill_graphs.append(
                {
                    "repo": repo.get("name"),
                    "schema_version": skill_manifest.get("schema_version"),
                    "generated_at": skill_manifest.get("generated_at"),
                    "stats": skill_manifest.get("stats"),
                    "category_count": skill_manifest.get("category_count"),
                }
            )

        contract_files = as_list(repo.get("contract_files"))
        if contract_files:
            contract_sources.append({"repo": repo.get("name"), "files": contract_files})

        labs_surface = inspect_labs_creator_surface(repo_path)
        if labs_surface:
            creator_system_surfaces.append(labs_surface)

        swarm_surface = inspect_swarm_specialization_surface(repo_path)
        if swarm_surface:
            specialization_path_surfaces.append(swarm_surface)

    return {
        "schema_version": CAPABILITY_CATALOG_SCHEMA,
        "generated_at": utc_now(),
        "redaction": "capability metadata only; command bodies, logs, and runtime outputs omitted",
        "chip_manifests": chip_manifests,
        "module_capabilities": module_capabilities,
        "skill_graphs": skill_graphs,
        "contract_sources": contract_sources,
        "creator_system_surfaces": creator_system_surfaces,
        "specialization_path_surfaces": specialization_path_surfaces,
        "capability_cards": build_capability_cards(creator_system_surfaces, specialization_path_surfaces),
    }


def read_text_or_none(path: Path) -> str | None:
    if not path:
        return None
    path = Path(path)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except Exception:
        return None


def literal_assignment(text: str | None, name: str) -> Any:
    text_str = str(text or "")
    if not text_str:
        return None
    name_str = str(name or "")
    try:
        tree = ast.parse(text_str)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name_str:
                try:
                    return ast.literal_eval(node.value)
                except Exception:
                    return None
            continue
        if any(isinstance(target, ast.Name) and target.id == name_str for target in node.targets):
            try:
                return ast.literal_eval(node.value)
            except Exception:
                return None
    return None


def regex_int(text: str | None, pattern: str) -> int | None:
    text_str = str(text or "")
    pattern_str = str(pattern or "")
    if not text_str or not pattern_str:
        return None
    match = re.search(pattern_str, text_str)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (ValueError, IndexError):
        return None


def regex_string(text: str | None, pattern: str) -> str | None:
    text_str = str(text or "")
    pattern_str = str(pattern or "")
    if not text_str or not pattern_str:
        return None
    match = re.search(pattern_str, text_str)
    if not match:
        return None
    try:
        value = match.group(1).strip()
        return value or None
    except IndexError:
        return None


def parse_ts_union(text: str | None, type_name: str) -> list[str]:
    text_str = str(text or "")
    type_name_str = str(type_name or "")
    if not text_str or not type_name_str:
        return []
    match = re.search(rf"export\s+type\s+{re.escape(type_name_str)}\s*=\s*([^;]+);", text_str, re.S)
    if not match:
        return []
    return re.findall(r"'([^']+)'|\"([^\"]+)\"", match.group(1))


def clean_ts_union(values: list[tuple[str, str]] | list[str]) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    cleaned: list[str] = []
    for value in values:
        if isinstance(value, (tuple, list, set)):
            item = next((str(part) for part in value if part), "")
        else:
            item = str(value or "")
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def parse_ts_union_values(text: str | None, type_name: str) -> list[str]:
    return clean_ts_union(parse_ts_union(text, type_name))


def ts_function_body(text: str | None, function_name: str) -> str:
    text_str = str(text or "")
    function_name_str = str(function_name or "")
    if not text_str or not function_name_str:
        return ""
    match = re.search(
        rf"export\s+function\s+{re.escape(function_name_str)}\s*\([^)]*\)[^{{]*{{(?P<body>.*?)\n}}",
        text_str,
        re.S,
    )
    return match.group("body") if match else ""


def ts_allowed_profiles(text: str | None, function_name: str, profiles: list[str]) -> list[str]:
    profiles_list = list(profiles) if isinstance(profiles, (list, tuple, set)) else []
    body = ts_function_body(text, function_name)
    if not body:
        return []
    denied = set(re.findall(r"profile\s*!==\s*'([^']+)'", body))
    if denied:
        return [profile for profile in profiles_list if profile not in denied]
    allowed = re.findall(r"profile\s*===\s*'([^']+)'", body)
    return [profile for profile in profiles_list if profile in set(allowed)]


def parse_ts_access_levels(text: str | None) -> dict[str, int]:
    body = ts_function_body(text, "sparkAccessLevel")
    levels: dict[str, int] = {}
    for profile, level in re.findall(r"case\s+'([^']+)':\s*return\s+(\d+)", body):
        levels[profile] = int(level)
    default_match = re.search(r"default:\s*return\s+(\d+)", body)
    if default_match:
        for profile in ("builder",):
            levels.setdefault(profile, int(default_match.group(1)))
    return levels


def inspect_cli_access_source(path: Path) -> dict[str, Any]:
    path = Path(path)
    text = read_text_or_none(path)
    lower_profiles = literal_assignment(text, "LOWER_ACCESS_PROFILES")
    profiles = []
    if isinstance(lower_profiles, dict):
        for level, payload in sorted(lower_profiles.items()):
            profile = as_dict(payload)
            profiles.append(
                {
                    "level": level,
                    "id": profile.get("id"),
                    "label": profile.get("label"),
                    "activation_state": profile.get("activation_state"),
                }
            )

    level5_env = literal_assignment(text, "LEVEL5_ENV")
    return {
        "source": str(path),
        "exists": path.exists(),
        "default_access_level": regex_int(text, r"DEFAULT_ACCESS_LEVEL\s*=\s*(\d+)"),
        "default_sandbox_lane": regex_string(text, r"DEFAULT_SANDBOX_LANE\s*=\s*['\"]([^'\"]+)['\"]"),
        "default_codex_sandbox": regex_string(text, r"DEFAULT_CODEX_SANDBOX\s*=\s*['\"]([^'\"]+)['\"]"),
        "lower_access_profiles": profiles,
        "level5_guardrail_keys": sorted(level5_env.keys()) if isinstance(level5_env, dict) else [],
        "level5_guardrail_contract": (
            "Level 5 requires high-agency workers, external-project opt-in, and danger-full-access sandbox."
            if isinstance(level5_env, dict)
            else "missing"
        ),
    }


def inspect_cli_capability_source(path: Path) -> dict[str, Any]:
    path = Path(path)
    text = read_text_or_none(path)
    toxic_pairs = literal_assignment(text, "TOXIC_CAPABILITY_PAIRS")
    dimensions = []
    for name, body in re.findall(r"(\w+Capability)\s*=\s*Literal\[(.*?)\]", text or "", re.S):
        dimensions.append({"dimension": name.replace("Capability", "").lower(), "values": clean_ts_union(re.findall(r"'([^']+)'|\"([^\"]+)\"", body))})

    safe_pairs = []
    if isinstance(toxic_pairs, tuple):
        for pair in toxic_pairs:
            if isinstance(pair, tuple) and len(pair) >= 3:
                safe_pairs.append({"left": pair[0], "right": pair[1], "reason": pair[2]})

    return {
        "source": str(path),
        "exists": path.exists(),
        "capability_dimensions": dimensions,
        "toxic_capability_pairs": safe_pairs,
        "toxic_pair_count": len(safe_pairs),
    }


def inspect_telegram_access_source(path: Path) -> dict[str, Any]:
    path = Path(path)
    text = read_text_or_none(path)
    profiles = parse_ts_union_values(text, "SparkAccessProfile")
    requirements = parse_ts_union_values(text, "SparkAccessRequirement")
    access_levels = parse_ts_access_levels(text)
    matrix = {
        "spawner_build": ts_allowed_profiles(text, "sparkAccessAllowsSpawnerBuilds", profiles),
        "external_research": ts_allowed_profiles(text, "sparkAccessAllowsExternalResearch", profiles),
        "operating_system": ts_allowed_profiles(text, "sparkAccessAllowsOperatingSystemWork", profiles),
    }
    return {
        "source": str(path),
        "exists": path.exists(),
        "profiles": [{"profile": profile, "level": access_levels.get(profile)} for profile in profiles],
        "requirements": requirements,
        "allow_matrix": {key: value for key, value in matrix.items() if value},
        "runtime_guardrails": {
            "hosted_full_access_env_checked": "SPARK_ALLOW_HOSTED_FULL_ACCESS" in (text or ""),
            "level5_guardrails_checked": "sparkLevel5RuntimeGuardrailsActive" in (text or ""),
            "high_agency_worker_env_checked": "SPARK_ALLOW_HIGH_AGENCY_WORKERS" in (text or ""),
        },
    }


def extract_js_object_block(text: str | None, marker: str) -> str:
    text_str = str(text or "")
    marker_str = str(marker or "")
    if not text_str or not marker_str:
        return ""
    marker_index = text_str.find(marker_str)
    if marker_index < 0:
        return ""
    start = text_str.find("{", marker_index)
    if start < 0:
        return ""
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text_str)):
        char = text_str[index]
        if quote:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text_str[start + 1 : index]
    return ""


def inspect_spawner_access_sources(root: Path) -> dict[str, Any]:
    root = Path(root)
    lanes_path = root / "src" / "lib" / "server" / "access-execution-lanes.ts"
    actions_path = root / "src" / "lib" / "server" / "access-execution-actions.ts"
    high_agency_path = root / "src" / "lib" / "server" / "high-agency-workers.ts"
    mission_access_path = root / "src" / "lib" / "server" / "mission-control-access.ts"
    lanes_text = read_text_or_none(lanes_path)
    actions_text = read_text_or_none(actions_path)
    high_agency_text = read_text_or_none(high_agency_path)
    mission_access_text = read_text_or_none(mission_access_path)

    actions = []
    actions_block = extract_js_object_block(actions_text, "ACCESS_EXECUTION_ACTIONS")
    action_matches = list(re.finditer(r"^\s*(\w+):\s*{", actions_block, re.M))
    for index, match in enumerate(action_matches):
        action_id = match.group(1)
        next_start = action_matches[index + 1].start() if index + 1 < len(action_matches) else len(actions_block)
        body = actions_block[match.end() : next_start]
        actions.append(
            {
                "id": regex_string(body, r"id:\s*'([^']+)'") or action_id,
                "lane_id": regex_string(body, r"laneId:\s*'([^']+)'"),
                "display_command": regex_string(body, r"displayCommand:\s*'([^']+)'"),
                "run_policy": regex_string(body, r"runPolicy:\s*'([^']+)'"),
                "confirmation_required": "confirmation:" in body,
                "rollback_declared": "rollback:" in body,
            }
        )

    return {
        "sources": {
            "lanes": {"path": str(lanes_path), "exists": lanes_path.exists()},
            "actions": {"path": str(actions_path), "exists": actions_path.exists()},
            "high_agency": {"path": str(high_agency_path), "exists": high_agency_path.exists()},
            "mission_control_access": {"path": str(mission_access_path), "exists": mission_access_path.exists()},
        },
        "lane_ids": parse_ts_union_values(lanes_text, "AccessExecutionLaneId"),
        "run_policies": parse_ts_union_values(lanes_text, "AccessRunPolicy"),
        "fixed_actions": actions,
        "confirmation_gated_action_count": sum(1 for action in actions if action.get("confirmation_required")),
        "level5_guardrail_keys": sorted(set(re.findall(r"SPARK_[A-Z0-9_]+", high_agency_text or ""))),
        "mission_control_modes": parse_ts_union_values(mission_access_text, "MissionControlAccessMode"),
        "mobile_privacy_contract": {
            "status_metadata_default": "status-metadata" in (mission_access_text or ""),
            "private_payloads_stay_local": "privatePayloadsStayLocal" in (mission_access_text or ""),
        },
    }


def js_const_object_values(text: str | None, object_name: str) -> dict[str, str]:
    text_str = str(text or "")
    object_name_str = str(object_name or "")
    if not text_str or not object_name_str:
        return {}
    match = re.search(rf"export\s+const\s+{re.escape(object_name_str)}\s*=\s*{{(?P<body>.*?)\n}};", text_str, re.S)
    if not match:
        return {}
    return {key: value for key, value in re.findall(r"(\w+):\s*['\"]([^'\"]+)['\"]", match.group("body"))}


def inspect_browser_authority(root: Path) -> dict[str, Any]:
    root = Path(root)
    constants_path = root / "src" / "protocol" / "constants.js"
    policy_path = root / "src" / "protocol" / "policy.js"
    contract_path = root / "docs" / "BROWSER_HOOK_CONTRACT_V1.md"
    constants_text = read_text_or_none(constants_path)
    risk_values = js_const_object_values(constants_text, "RISK_CLASSES")
    approval_values = js_const_object_values(constants_text, "APPROVAL_MODES")
    risk_counts: Counter[str] = Counter()
    approval_counts: Counter[str] = Counter()
    for risk_key in re.findall(r"risk_class:\s*RISK_CLASSES\.(\w+)", constants_text or ""):
        risk_counts[risk_values.get(risk_key, risk_key.lower())] += 1
    for approval_key in re.findall(r"approval_mode:\s*APPROVAL_MODES\.(\w+)", constants_text or ""):
        approval_counts[approval_values.get(approval_key, approval_key.lower())] += 1
    return {
        "sources": {
            "constants": {"path": str(constants_path), "exists": constants_path.exists()},
            "policy": {"path": str(policy_path), "exists": policy_path.exists()},
            "contract": {"path": str(contract_path), "exists": contract_path.exists()},
        },
        "risk_classes": sorted(risk_values.values()),
        "approval_modes": sorted(approval_values.values()),
        "hook_count": sum(risk_counts.values()),
        "risk_class_counts": dict(sorted(risk_counts.items())),
        "approval_mode_counts": dict(sorted(approval_counts.items())),
        "origin_scoped_hook_count": len(re.findall(r"requires_origin_scope:\s*true", constants_text or "")),
        "sensitive_surface_policy_exists": "classifySensitiveSurface" in (read_text_or_none(policy_path) or ""),
    }


def inspect_public_output_authority(desktop: Path) -> dict[str, Any]:
    desktop = Path(desktop)
    swarm_root = desktop / "spark-swarm"
    labs_root = desktop / "spark-domain-chip-labs"
    sync_validation_path = swarm_root / "apps" / "api" / "src" / "collective" / "sync-validation.ts"
    sync_text = read_text_or_none(sync_validation_path)
    checks_match = re.search(r"REQUIRED_PUBLICATION_CHECKS\s*=\s*\[(?P<body>.*?)\]", sync_text or "", re.S)
    required_checks = clean_ts_union(re.findall(r"['\"]([^'\"]+)['\"]", checks_match.group("body") if checks_match else ""))

    swarm_files = {
        name: {"path": str(swarm_root / rel_path), "exists": (swarm_root / rel_path).exists()}
        for name, rel_path in SWARM_PUBLICATION_GOVERNANCE_FILES.items()
    }
    labs_files = {
        name: {"path": str(labs_root / rel_path), "exists": (labs_root / rel_path).exists()}
        for name, rel_path in LABS_CREATOR_SURFACE_FILES.items()
    }
    proposal_template = swarm_root / "templates" / "creator-system-network-proposal" / "creator-network-proposal-bundle.template.json"
    readiness_template = swarm_root / "templates" / "creator-system-network-proposal" / "creator-system-launch-readiness.template.json"

    return {
        "authority": "publication_not_granted_by_local_artifacts",
        "swarm_governance_files": swarm_files,
        "labs_gate_files": labs_files,
        "required_publication_workflow": regex_string(sync_text, r"REQUIRED_PUBLICATION_WORKFLOW\s*=\s*['\"]([^'\"]+)['\"]"),
        "required_publication_checks": required_checks,
        "creator_network_templates": {
            "proposal_bundle": {"path": str(proposal_template), "exists": proposal_template.exists()},
            "launch_readiness": {"path": str(readiness_template), "exists": readiness_template.exists()},
        },
        "non_override_rule": (
            "Schema artifacts, local run artifacts, attestations, and ready-for-swarm packets do not grant "
            "network publication authority without privacy, rollback, verified PR, publication approval, and signed-manifest gates."
        ),
    }


def build_authority_view(desktop: Path, setup_summary: dict[str, Any], spark_home: Path | None = None) -> dict[str, Any]:
    desktop = Path(desktop)
    setup_summary = setup_summary if isinstance(setup_summary, dict) else {}
    spark_home = Path(spark_home) if spark_home is not None else None
    module_sources = spark_home / "modules" if spark_home is not None else None
    spark_cli_package_root = Path(__file__).resolve().parent
    spark_cli_repo_root = spark_cli_package_root.parent.parent
    installed_suffixes: dict[str, tuple[str, Path]] = {
        "cli_access_policy": ("spark-cli", Path("src/spark_cli/sandbox/access.py")),
        "cli_capabilities": ("spark-cli", Path("src/spark_cli/sandbox/capabilities.py")),
        "telegram_access_policy": ("spark-telegram-bot", Path("src/accessPolicy.ts")),
        "builder_aoc": ("spark-intelligence-builder", Path("src/spark_intelligence/self_awareness/operating_context.py")),
        "spawner_access_lanes": ("spawner-ui", Path("src/lib/server/access-execution-lanes.ts")),
        "spawner_access_actions": ("spawner-ui", Path("src/lib/server/access-execution-actions.ts")),
        "browser_constants": ("spark-browser-extension", Path("src/protocol/constants.js")),
        "browser_policy": ("spark-browser-extension", Path("src/protocol/policy.js")),
        "swarm_sync_validation": ("spark-swarm", Path("apps/api/src/collective/sync-validation.ts")),
    }
    desktop_files = {
        "cli_access_policy": desktop / "spark-cli" / "src" / "spark_cli" / "sandbox" / "access.py",
        "cli_capabilities": desktop / "spark-cli" / "src" / "spark_cli" / "sandbox" / "capabilities.py",
        "telegram_access_policy": desktop / "spark-telegram-bot" / "src" / "accessPolicy.ts",
        "builder_aoc": desktop / "spark-intelligence-builder" / "src" / "spark_intelligence" / "self_awareness" / "operating_context.py",
        "spawner_access_lanes": desktop / "spawner-ui" / "src" / "lib" / "server" / "access-execution-lanes.ts",
        "spawner_access_actions": desktop / "spawner-ui" / "src" / "lib" / "server" / "access-execution-actions.ts",
        "browser_constants": desktop / "spark-browser-extension" / "src" / "protocol" / "constants.js",
        "browser_policy": desktop / "spark-browser-extension" / "src" / "protocol" / "policy.js",
        "swarm_sync_validation": desktop / "spark-swarm" / "apps" / "api" / "src" / "collective" / "sync-validation.ts",
    }

    def resolve_source_file(key: str) -> Path:
        desktop_path = desktop_files[key]
        if desktop_path.exists():
            return desktop_path
        module_name, suffix = installed_suffixes[key]
        if module_sources is not None:
            installed_path = module_sources / module_name / "source" / suffix
            if installed_path.exists():
                return installed_path
        if module_name == "spark-cli":
            local_repo_path = spark_cli_repo_root / suffix
            if local_repo_path.exists():
                return local_repo_path
            package_suffix = Path(*suffix.parts[2:]) if suffix.parts[:2] == ("src", "spark_cli") else suffix
            local_package_path = spark_cli_package_root / package_suffix
            if local_package_path.exists():
                return local_package_path
        return desktop_path

    def resolve_repo_root(repo_name: str) -> Path:
        if module_sources is not None:
            installed_root = module_sources / repo_name / "source"
            if installed_root.exists():
                return installed_root
        return desktop / repo_name

    source_files = {key: resolve_source_file(key) for key in desktop_files}
    observed_sources = {name: {"path": str(path), "exists": path.exists()} for name, path in source_files.items()}

    cli_access = inspect_cli_access_source(source_files["cli_access_policy"])
    cli_capability_policy = inspect_cli_capability_source(source_files["cli_capabilities"])
    telegram_policy = inspect_telegram_access_source(source_files["telegram_access_policy"])
    spawner_execution_policy = inspect_spawner_access_sources(resolve_repo_root("spawner-ui"))
    browser_authority = inspect_browser_authority(resolve_repo_root("spark-browser-extension"))
    public_output_authority = inspect_public_output_authority(desktop)

    access_profile_count = len(as_list(telegram_policy.get("profiles")))

    return {
        "schema_version": AUTHORITY_VIEW_SCHEMA,
        "generated_at": utc_now(),
        "redaction": (
            "policy constants, safe command labels, source existence, and aggregate gate counts only; "
            "env files, profile preference files, token values, chat ids, raw mission text, and browser content are not read"
        ),
        "observed_sources": observed_sources,
        "default_access_level_hint": cli_access.get("default_access_level"),
        "telegram_profile_count": access_profile_count,
        "configured_telegram_profile_count": setup_summary.get("telegram_profile_count"),
        "primary_telegram_profile": setup_summary.get("primary_telegram_profile"),
        "cli_access": cli_access,
        "cli_capability_policy": cli_capability_policy,
        "telegram_access_policy": telegram_policy,
        "spawner_execution_policy": spawner_execution_policy,
        "browser_authority": browser_authority,
        "public_output_authority": public_output_authority,
        "guardrail_summary": {
            "toxic_pair_count": cli_capability_policy.get("toxic_pair_count"),
            "spawner_confirmation_gated_action_count": spawner_execution_policy.get("confirmation_gated_action_count"),
            "browser_approval_required_hook_count": sum(
                count
                for mode, count in as_dict(browser_authority.get("approval_mode_counts")).items()
                if mode not in {"not_required", "blocked"}
            ),
            "publication_checks_required": len(as_list(public_output_authority.get("required_publication_checks"))),
        },
        "next_required_bridges": [
            "Promote this compiled AuthorityViewV1 into Builder AOC as evidence, not policy authority.",
            "Point Telegram access/status replies at this view for compact drilldowns without raw ids.",
            "Join authority checks to trace ids for high-agency actions, browser approvals, and publication gates.",
            "Add runtime verdict exports so the view can distinguish configured policy from the currently active runner.",
        ],
    }


def trace_repair_id(*parts: Any) -> str:
    value = "-".join(str(part or "missing").lower() for part in parts)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:96] or "trace-repair"


def trace_repair_owner(component: str) -> dict[str, str]:
    comp = str(component or "")
    return as_dict(TRACE_REPAIR_COMPONENT_OWNERS.get(comp)) or {
        "owner_repo": "spark-intelligence-builder",
        "source_module": f"{comp} event emission",
    }


def build_trace_current_health(trace_index: dict[str, Any]) -> dict[str, Any]:
    trace_idx = trace_index if isinstance(trace_index, dict) else {}
    trace_health = as_dict(trace_idx.get("builder_trace_health"))
    recent_windows = [as_dict(row) for row in as_list(trace_health.get("recent_windows"))]
    total_missing = int(trace_health.get("missing_trace_ref_count") or 0)
    current_window = next(
        (
            row
            for label in ("1h", "24h")
            for row in recent_windows
            if row.get("window") == label and int(row.get("row_count") or 0)
        ),
        None,
    )
    if current_window is None and recent_windows:
        current_window = recent_windows[0]

    if not current_window:
        status = "unknown"
        row_count = 0
        missing_count = 0
        ratio = 0.0
        window = "unknown"
    else:
        window = str(current_window.get("window") or "unknown")
        row_count = int(current_window.get("row_count") or 0)
        missing_count = int(current_window.get("missing_trace_ref_count") or 0)
        ratio = float(current_window.get("missing_trace_ref_ratio") or 0.0)
        if row_count and missing_count:
            status = "current_missing_trace_refs"
        elif row_count and total_missing:
            status = "current_clean_historical_backlog"
        elif row_count:
            status = "current_clean"
        elif total_missing:
            status = "no_recent_events_historical_backlog"
        else:
            status = "clean"

    return {
        "schema_version": "spark.trace_current_health.v0",
        "status": status,
        "window": window,
        "row_count": row_count,
        "missing_trace_ref_count": missing_count,
        "missing_trace_ref_ratio": ratio,
        "total_missing_trace_ref_count": total_missing,
        "historical_missing_trace_ref_count": max(total_missing - missing_count, 0),
        "repair_scope": (
            "current"
            if status == "current_missing_trace_refs"
            else "historical_backlog"
            if status in {"current_clean_historical_backlog", "no_recent_events_historical_backlog"}
            else status
        ),
        "redaction": "aggregate recency metadata only; no raw event text or identifiers",
    }


def build_trace_repair_queue(trace_index: dict[str, Any]) -> list[dict[str, Any]]:
    trace_idx = trace_index if isinstance(trace_index, dict) else {}
    queue: list[dict[str, Any]] = []
    trace_health = as_dict(trace_idx.get("builder_trace_health"))
    current_health = as_dict(trace_idx.get("trace_current_health")) or build_trace_current_health(trace_idx)
    historical_scope = str(current_health.get("repair_scope") or "") == "historical_backlog"
    telegram_gate = as_dict(trace_idx.get("telegram_final_answer_gate_samples"))
    telegram_join = as_dict(telegram_gate.get("trace_join"))
    spawner = as_dict(trace_idx.get("spawner_prd_auto_trace_samples"))
    spawner_join = as_dict(spawner.get("join_keys"))
    spawner_request_overlap = as_dict(spawner.get("builder_request_overlap"))
    spawner_trace_overlap = as_dict(spawner.get("builder_trace_ref_overlap"))

    if telegram_gate.get("exists") and telegram_join.get("status") != "join_key_present":
        queue.append(
            {
                "id": "telegram-final-answer-missing-join-key",
                "priority": "critical",
                "rank_reason": "blocks Telegram -> Builder trace joins",
                "owner_repo": "spark-telegram-bot",
                "source_module": "final-answer gate audit producer",
                "event_producer_family": "telegram_final_answer_gate",
                "missing_field": "request_id_or_trace_ref",
                "observed_event_count": int(telegram_gate.get("parsed_count") or 0),
                "safe_fix": "Emit request_id or trace_ref metadata with final-answer gate checks.",
                "verification_command": "spark os trace --json",
            }
        )

    spawner_request_count = int(spawner_join.get("request_id_count") or 0)
    spawner_overlap_count = int(spawner_request_overlap.get("matched_builder_request_id_count") or 0)
    spawner_trace_overlap_count = int(spawner_trace_overlap.get("matched_builder_trace_ref_count") or 0)
    if spawner_request_count and not (spawner_overlap_count or spawner_trace_overlap_count):
        queue.append(
            {
                "id": "spawner-builder-missing-shared-trace",
                "priority": "critical",
                "rank_reason": "blocks Builder -> Spawner mission reconstruction",
                "owner_repo": "spawner-ui",
                "source_module": "PRD auto trace / Builder mission bridge",
                "event_producer_family": "spawner_prd_auto_trace",
                "missing_field": "shared_request_id_or_trace_ref",
                "observed_event_count": spawner_request_count,
                "safe_fix": "Write the Builder request id or derived trace ref into Spawner mission events and Builder mission events.",
                "verification_command": "spark os trace --json",
            }
        )

    rows = as_list(as_dict(trace_health.get("missing_trace_ref_sources")).get("rows"))
    for row in rows[:10]:
        row = as_dict(row)
        component = str(row.get("component") or "unknown")
        event_type = str(row.get("event_type") or "unknown")
        owner = trace_repair_owner(component)
        rank_reason = "largest Builder producer bucket missing trace_ref"
        safe_fix = "Thread the active request_id/trace_ref into this event producer before recording black-box events."
        temporal_state = str(row.get("repair_temporal_state") or "")
        latest_clean = temporal_state in {"latest_clean", "latest_clean_historical_window_debt"}
        stale_missing = temporal_state == "stale_missing_trace_ref"
        if latest_clean:
            rank_reason = "latest Builder row for this producer carries trace_ref; older rows remain in the aggregate window"
            safe_fix = "Watch for new missing-trace rows; no source patch is needed unless the producer regresses."
        elif stale_missing:
            rank_reason = "historical Builder producer bucket has no recent rows; latest known row predates the active window"
            safe_fix = "Reproduce the producer before patching; this may be stale backlog rather than current runtime behavior."
        elif historical_scope:
            rank_reason = "historical Builder backlog missing trace_ref; recent trace window is clean"
            safe_fix = (
                "Verify whether this historical bucket still reproduces; new traffic may already carry trace refs."
            )
        queue.append(
            {
                "id": trace_repair_id("builder", component, event_type, "missing-trace-ref"),
                "priority": "medium" if historical_scope or latest_clean or stale_missing else "high",
                "rank_reason": rank_reason,
                "owner_repo": owner.get("owner_repo"),
                "source_module": owner.get("source_module"),
                "event_producer_family": component,
                "event_type": event_type,
                "missing_field": "trace_ref",
                "observed_event_count": int(row.get("event_count") or 0),
                "temporal_scope": temporal_state or ("historical_backlog" if historical_scope else "current_or_unknown"),
                "latest_event_trace_state": row.get("latest_event_trace_state"),
                "latest_event_trace_ref_present": bool(row.get("latest_event_trace_ref_present")),
                "latest_event_request_id_present": bool(row.get("latest_event_request_id_present")),
                "recent_1h_missing_trace_ref_count": int(row.get("recent_1h_missing_trace_ref_count") or 0),
                "recent_24h_missing_trace_ref_count": int(row.get("recent_24h_missing_trace_ref_count") or 0),
                "recent_24h_row_count": int(row.get("recent_24h_row_count") or 0),
                "current_health_status": current_health.get("status"),
                "current_window": current_health.get("window"),
                "current_window_missing_trace_ref_count": int(current_health.get("missing_trace_ref_count") or 0),
                "safe_fix": safe_fix,
                "verification_command": "spark os trace --json",
            }
        )

    high_open_count = int(trace_health.get("high_severity_open_count") or 0)
    if high_open_count:
        queue.append(
            {
                "id": "builder-open-high-severity-events",
                "priority": "medium",
                "rank_reason": "high severity events remain open",
                "owner_repo": "spark-intelligence-builder",
                "source_module": "Builder black-box event lifecycle",
                "event_producer_family": "builder_events",
                "missing_field": "resolution_or_close_event",
                "observed_event_count": high_open_count,
                "safe_fix": "Add close/resolution metadata for high-severity events once the owning guardrail is repaired or confirmed active.",
                "verification_command": "spark os trace --json",
            }
        )

    priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(
        queue,
        key=lambda item: (
            priority_rank.get(str(item.get("priority")), 9),
            -int(item.get("observed_event_count") or 0),
            str(item.get("id")),
        ),
    )


def build_builder_trace_repair_cards(trace_index: dict[str, Any]) -> dict[str, Any]:
    trace_idx = trace_index if isinstance(trace_index, dict) else {}
    trace_health = as_dict(trace_idx.get("builder_trace_health"))
    current_health = as_dict(trace_idx.get("trace_current_health")) or build_trace_current_health(trace_idx)
    repair_queue = [as_dict(item) for item in as_list(trace_idx.get("trace_repair_queue"))]
    cards: list[dict[str, Any]] = []

    for item in repair_queue:
        if item.get("owner_repo") != "spark-intelligence-builder" or item.get("missing_field") != "trace_ref":
            continue
        component = str(item.get("event_producer_family") or "builder_events")
        event_type = str(item.get("event_type") or "unknown")
        temporal_scope = str(item.get("temporal_scope") or "")
        if temporal_scope == "latest_clean_historical_window_debt":
            status = "latest_clean_historical_window_debt"
        elif temporal_scope == "latest_clean":
            status = "latest_clean"
        elif temporal_scope == "stale_missing_trace_ref":
            status = "stale_missing_trace_ref"
        elif current_health.get("repair_scope") == "current":
            status = "current"
        elif current_health.get("repair_scope") == "historical_backlog":
            status = "historical_backlog"
        else:
            status = "unknown"
        cards.append(
            {
                "schema_version": "spark.builder_trace_repair_card.v0",
                "id": item.get("id") or trace_repair_id("builder", component, event_type, "missing-trace-ref"),
                "category": "missing_trace_ref",
                "title": f"Thread trace_ref into {component} / {event_type}",
                "status": status,
                "priority": item.get("priority") or "high",
                "owner_repo": "spark-intelligence-builder",
                "source_module": item.get("source_module") or f"{component} event emission",
                "event_producer_family": component,
                "event_type": event_type,
                "missing_field": "trace_ref",
                "observed_event_count": int(item.get("observed_event_count") or 0),
                "current_window": current_health.get("window"),
                "current_window_row_count": int(current_health.get("row_count") or 0),
                "current_window_missing_trace_ref_count": int(current_health.get("missing_trace_ref_count") or 0),
                "total_missing_trace_ref_count": int(current_health.get("total_missing_trace_ref_count") or 0),
                "latest_event_trace_state": item.get("latest_event_trace_state") or "unknown",
                "latest_event_trace_ref_present": bool(item.get("latest_event_trace_ref_present")),
                "latest_event_request_id_present": bool(item.get("latest_event_request_id_present")),
                "recent_1h_missing_trace_ref_count": int(item.get("recent_1h_missing_trace_ref_count") or 0),
                "recent_24h_missing_trace_ref_count": int(item.get("recent_24h_missing_trace_ref_count") or 0),
                "recent_24h_row_count": int(item.get("recent_24h_row_count") or 0),
                "evidence": item.get("rank_reason") or "Builder event producer bucket is missing trace_ref.",
                "recommended_action": item.get("safe_fix")
                or "Thread active request_id and trace_ref into the event producer before recording Builder events.",
                "verification_command": item.get("verification_command") or "spark os trace --json",
                "data_boundary": "aggregate metadata only; no event bodies, raw prompts, provider output, memory bodies, transcripts, audio, chat ids, or secrets",
            }
        )
        if len(cards) >= 6:
            break

    high_rows = [as_dict(row) for row in as_list(as_dict(trace_health.get("high_severity_open_sources")).get("rows"))]
    for row in high_rows[:4]:
        component = str(row.get("component") or "builder_events")
        event_type = str(row.get("event_type") or "unknown")
        status = str(row.get("status") or "open")
        severity = str(row.get("severity") or "high")
        lifecycle_state = str(row.get("lifecycle_temporal_state") or row.get("latest_lifecycle_state") or "unknown")
        if lifecycle_state == "latest_resolved":
            card_status = "latest_resolved"
            priority = "medium"
            evidence = "latest lifecycle row for this high-severity family is resolved or lower severity"
            recommended_action = "Keep as historical lifecycle debt unless new high-severity rows appear."
        elif lifecycle_state == "stale_open_high_severity":
            card_status = "stale_open_high_severity"
            priority = "medium"
            evidence = "latest high-severity row predates the active window"
            recommended_action = "Reproduce before patching; this may be stale lifecycle backlog."
        else:
            card_status = "open"
            priority = "critical" if severity == "critical" else "high"
            evidence = "high or critical Builder events remain open in aggregate black-box metadata"
            recommended_action = (
                "Confirm whether the guardrail is still active, then add source-owned close/resolution metadata."
            )
        owner = trace_repair_owner(component)
        cards.append(
            {
                "schema_version": "spark.builder_trace_repair_card.v0",
                "id": trace_repair_id(
                    "builder",
                    component,
                    event_type,
                    row.get("reason_code") or "unknown-reason",
                    status,
                    severity,
                    "open-high-severity",
                ),
                "category": "open_high_severity_event",
                "title": f"Resolve high-severity {component} / {event_type}",
                "status": card_status,
                "priority": priority,
                "owner_repo": owner.get("owner_repo") or "spark-intelligence-builder",
                "source_module": owner.get("source_module") or f"{component} event lifecycle",
                "event_producer_family": component,
                "event_type": event_type,
                "reason_code": row.get("reason_code"),
                "event_status": status,
                "event_severity": severity,
                "latest_lifecycle_state": row.get("latest_lifecycle_state") or "unknown",
                "latest_event_status": row.get("latest_event_status"),
                "latest_event_severity": row.get("latest_event_severity"),
                "latest_event_trace_ref_present": bool(row.get("latest_event_trace_ref_present")),
                "latest_event_request_id_present": bool(row.get("latest_event_request_id_present")),
                "recent_1h_high_open_count": int(row.get("recent_1h_high_open_count") or 0),
                "recent_24h_high_open_count": int(row.get("recent_24h_high_open_count") or 0),
                "recent_24h_row_count": int(row.get("recent_24h_row_count") or 0),
                "missing_field": "resolution_or_close_event",
                "observed_event_count": int(row.get("event_count") or 0),
                "current_window": current_health.get("window"),
                "evidence": evidence,
                "recommended_action": recommended_action,
                "verification_command": "spark os trace --json",
                "data_boundary": "aggregate metadata only; no event bodies, raw prompts, provider output, memory bodies, transcripts, audio, chat ids, or secrets",
            }
        )

    category_counts: dict[str, int] = {}
    owner_counts: dict[str, int] = {}
    for card in cards:
        category = str(card.get("category") or "unknown")
        owner_repo = str(card.get("owner_repo") or "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        owner_counts[owner_repo] = owner_counts.get(owner_repo, 0) + 1

    return {
        "schema_version": "spark.builder_trace_repair_cards.v0",
        "card_count": len(cards),
        "category_counts": category_counts,
        "owner_counts": owner_counts,
        "current_health": current_health,
        "redaction": "repair cards are derived from aggregate Builder event metadata only",
        "items": cards,
    }


def build_trace_index(spark_home: Path, builder_home: Path) -> dict[str, Any]:
    spark_home = Path(spark_home)
    builder_home = Path(builder_home)
    spawner_state = spark_home / "state" / "spawner-ui"
    telegram_state = spark_home / "state" / "spark-telegram-bot"
    trace_index = {
        "schema_version": TRACE_INDEX_SCHEMA,
        "generated_at": utc_now(),
        "redaction": "aggregate metadata only; no raw event summaries, mission responses, logs, or message text",
        "builder_events": inspect_builder_event_trace(builder_home),
        "builder_event_samples": inspect_builder_event_samples(builder_home),
        "builder_trace_groups": inspect_builder_trace_groups(builder_home),
        "builder_trace_health": inspect_builder_trace_health(builder_home),
        "telegram_final_answer_gate": count_safe_jsonl(telegram_state / "final-answer-gate-audit.jsonl"),
        "telegram_final_answer_gate_samples": inspect_telegram_final_answer_gate(
            telegram_state / "final-answer-gate-audit.jsonl"
        ),
        "telegram_outbound_audit": count_safe_jsonl(telegram_state / "node-outbound-audit.jsonl"),
        "telegram_outbound_audit_samples": inspect_telegram_outbound_audit(
            telegram_state / "node-outbound-audit.jsonl"
        ),
        "spawner_mission_control_shape": inspect_json_shape(spawner_state / "mission-control.json"),
        "spawner_provider_results_shape": inspect_json_shape(spawner_state / "mission-provider-results.json"),
        "spawner_prd_auto_trace": count_safe_jsonl(spawner_state / "prd-auto-trace.jsonl"),
        "spawner_prd_auto_trace_samples": inspect_spawner_prd_auto_trace(
            spawner_state / "prd-auto-trace.jsonl",
            builder_home=builder_home,
        ),
        "authority_verdicts": inspect_spawner_authority_verdicts(spawner_state / "prd-auto-trace.jsonl"),
        "review_candidates": build_spark_os_review_candidates(
            spawner_state / "prd-auto-trace.jsonl",
            builder_home=builder_home,
        ),
        "next_required_bridges": [
            "Map Spawner mission ids to Builder mission_changed_state events.",
            "Map Telegram final-answer gate checks to final_answer_checked black-box events.",
            "Emit Telegram request_id or trace_ref join keys from final-answer gate checks.",
        ],
    }
    trace_index["trace_current_health"] = build_trace_current_health(trace_index)
    trace_index["trace_repair_queue"] = build_trace_repair_queue(trace_index)
    trace_index["builder_trace_repair_cards"] = build_builder_trace_repair_cards(trace_index)
    return trace_index


def build_memory_movement_index(builder_home: Path) -> dict[str, Any]:
    builder_home = Path(builder_home)
    builder_memory_tables = inspect_builder_memory_tables(builder_home)
    trace_join = as_dict(builder_memory_tables.get("memory_lane_trace_join"))
    trace_bridge_instruction = (
        "Audit legacy memory lane rows missing trace refs before cleanup; new memory preflight events should keep request_id and trace_ref."
        if trace_join.get("status") == "present"
        else "Join memory movement events to trace ids once Builder event envelopes carry stable trace refs."
    )
    memory_index = {
        "schema_version": MEMORY_MOVEMENT_INDEX_SCHEMA,
        "generated_at": utc_now(),
        "authority": "observability_non_authoritative",
        "redaction": (
            "metadata-only memory movement index; no raw memory text, row bodies, profile facts, "
            "conversation turns, evidence payloads, or Telegram update payloads emitted"
        ),
        "builder_memory_tables": builder_memory_tables,
        "safe_status_export": read_memory_movement_status_export(builder_home),
        "memory_kb_artifacts": summarize_memory_kb_artifacts(builder_home),
        "memory_run_artifacts": summarize_memory_run_artifacts(builder_home),
        "next_required_bridges": [
            "Have Builder write artifacts/memory-movement-index/memory-movement-status.json from inspect_memory_movement_status().",
            "Have domain-chip-memory expose movement counts by lane, authority, source family, and record type without record text.",
            trace_bridge_instruction,
            "Promote this index into Builder AOC and cockpit as evidence only, never as instructions or profile truth.",
        ],
    }
    memory_index["memory_review_queue"] = build_memory_review_queue(memory_index)
    return memory_index


def build_gaps(system_map: dict[str, Any]) -> list[dict[str, str]]:
    sys_map = system_map if isinstance(system_map, dict) else {}
    registry_modules = set(as_dict(sys_map.get("registry", {}).get("modules")).keys())
    installed_modules = set(as_dict(sys_map.get("installed_modules")).keys())
    repos = as_list(sys_map.get("discovered_repos"))
    raw_gaps: list[dict[str, str]] = []

    def add_gap(severity: str, area: str, item: str, message: str) -> None:
        raw_gaps.append({"severity": str(severity), "area": str(area), "item": str(item), "message": str(message)})

    for module_id in sorted(registry_modules - installed_modules):
        add_gap("info", "install", module_id, "Registry module is not installed in the current local Spark home.")

    for module_id in sorted(installed_modules - registry_modules):
        add_gap("warning", "registry", module_id, "Installed module is missing from spark-cli registry.json.")

    known_modules = registry_modules | installed_modules
    for repo in repos:
        repo = as_dict(repo)
        ids = repo_ids(repo)
        toml = as_dict(repo.get("spark_toml"))
        chip = as_dict(repo.get("spark_chip"))
        if toml and not (ids & known_modules):
            add_gap(
                "decision",
                "system-map",
                str(toml.get("module_name") or repo.get("name")),
                "Repo declares spark.toml but is not in installed state or starter registry.",
            )
        chip_name = str(chip.get("chip_name") or repo.get("name") or "")
        if chip and chip_name and chip_name not in known_modules:
            add_gap(
                "decision",
                "capability",
                chip_name,
                "Repo declares spark-chip.json but is not in installed state or starter registry.",
            )

    for module in as_list(sys_map.get("modules")):
        installed = as_dict(module.get("installed"))
        if installed and installed.get("path") and not Path(str(installed.get("path"))).exists():
            add_gap("warning", "install", str(module.get("id")), "Installed module path does not exist.")

    if not any(as_dict(repo).get("skill_manifest") for repo in repos):
        add_gap("decision", "skill-graphs", "spark-skill-graphs", "No skill graph manifest discovered; specialist routing cannot be cataloged.")

    deduped: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for gap in raw_gaps:
        key = (gap["severity"], gap["area"], gap["item"], gap["message"])
        if key not in deduped:
            deduped[key] = dict(gap)
            deduped[key]["count"] = "1"
        else:
            deduped[key]["count"] = str(int(deduped[key]["count"]) + 1)
    return list(deduped.values())


def repo_owner_surface(name: str) -> str:
    name_str = str(name or "")
    if name_str in OWNER_SURFACES:
        return OWNER_SURFACES[name_str]
    if name_str.startswith("domain-chip-"):
        return "domain chip candidate"
    if name_str.startswith("specialization-path-"):
        return "specialization path candidate"
    if "telegram" in name_str:
        return "Telegram-adjacent surface"
    if "swarm" in name_str:
        return "Swarm-adjacent surface"
    if "spark" in name_str:
        return "Spark-adjacent repo"
    return "unclassified"


def repo_manifest_presence(repo: dict[str, Any]) -> dict[str, bool]:
    repo_dict = repo if isinstance(repo, dict) else {}
    contract_files = set(as_list(repo_dict.get("contract_files")))
    return {
        "spark_toml": bool(as_dict(repo_dict.get("spark_toml"))),
        "spark_chip": bool(as_dict(repo_dict.get("spark_chip"))),
        "skill_manifest": bool(as_dict(repo_dict.get("skill_manifest"))),
        "agents_md": "AGENTS.md" in contract_files,
        "contract_file_count": bool(contract_files),
    }


def repo_release_status(name: str, git: dict[str, Any], manifest: dict[str, bool], registry_present: bool) -> tuple[str, str | None, str]:
    git_dict = git if isinstance(git, dict) else {}
    manifest_dict = manifest if isinstance(manifest, dict) else {}
    name_str = str(name or "")
    dirty = int(git_dict.get("dirty_tracked_count") or 0)
    untracked = int(git_dict.get("untracked_count") or 0)
    behind = int(git_dict.get("behind") or 0)
    if not git_dict.get("available"):
        return "not_release_candidate", "not a git repo", "inspect or ignore before product work"
    if dirty or untracked:
        return "blocked", "dirty worktree", "curate local changes before merge or release"
    if behind:
        return "blocked", "behind upstream", "pull or merge upstream before release"
    if name_str in CORE_REPOS and not any(manifest_dict.values()):
        return "blocked", "core repo missing Spark manifest", "add or confirm owner manifest before release"
    if name_str == "spark-cli" and any(manifest_dict.values()):
        return "eligible", None, "installer and Spark OS compiler source truth is manifest-declared"
    if registry_present:
        return "eligible", None, "safe to consider for the next verified workstream"
    return "inspect", "not in installer registry", "decide whether this repo should remain local, become a capability, or be ignored"


def repo_risk_class(name: str, release_eligibility: str) -> str:
    name_str = str(name or "")
    eligibility = str(release_eligibility or "")
    if name_str in {"spark-cli", "spark-intelligence-builder", "spark-telegram-bot", "spawner-ui"}:
        return "critical"
    if eligibility == "blocked":
        return "high"
    if name_str in CORE_REPOS:
        return "medium"
    return "low"


def repo_by_name(system_map: dict[str, Any], name: str) -> dict[str, Any]:
    sys_map = system_map if isinstance(system_map, dict) else {}
    name_str = str(name or "")
    for repo in as_list(sys_map.get("discovered_repos")):
        repo = as_dict(repo)
        if repo.get("name") == name_str:
            return repo
    return {}


def duplicate_truth_item(
    *,
    item_id: str,
    fact: str,
    classification: str,
    owner_repo: str,
    canonical_path: str,
    duplicate_path: str,
    evidence: str,
    risk: str,
    next_safe_action: str,
    verification_command: str,
    rollback: str,
    severity: str = "warning",
    evidence_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = {
        "id": str(item_id or ""),
        "fact": str(fact or ""),
        "classification": str(classification or ""),
        "severity": str(severity or "warning"),
        "owner_repo": str(owner_repo or ""),
        "canonical_path": str(canonical_path or ""),
        "duplicate_path": str(duplicate_path or ""),
        "evidence": str(evidence or ""),
        "risk": str(risk or ""),
        "next_safe_action": str(next_safe_action or ""),
        "verification_command": str(verification_command or ""),
        "rollback": str(rollback or ""),
    }
    if evidence_details is not None:
        item["evidence_details"] = evidence_details
    return item


BUILDER_AOC_COMMAND_MARKERS = {
    "panel": '"panel"',
    "black-box": '"black-box"',
    "source-used": '"source-used"',
    "route-selection": '"route-selection"',
    "mission-state": '"mission-state"',
    "turn-trace": '"turn-trace"',
}


def dirty_family_for_path(path_value: str) -> str:
    normalized = str(path_value or "").replace("\\", "/").strip()
    if " -> " in normalized:
        normalized = normalized.split(" -> ", 1)[1].strip()
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return "unknown"
    if parts[0] == "src" and len(parts) >= 2:
        return "src/" + parts[1]
    if parts[0] in {"docs", "tests", "ops", "artifacts", "scripts", ".github"}:
        return parts[0]
    return "root"


def git_dirty_family_counts(path: Path) -> dict[str, int]:
    path = Path(path)
    if not (path / ".git").exists():
        return {}
    code, status = run_git(path, ["status", "--porcelain"])
    if code != 0 or not status:
        return {}
    counts: Counter[str] = Counter()
    for line in status.splitlines():
        if not line.strip():
            continue
        counts[dirty_family_for_path(line[3:])] += 1
    return dict(sorted(counts.items()))


def builder_source_audit(path: Path) -> dict[str, Any]:
    path = Path(path)
    git = git_board_status(path)
    cli_path = path / "src" / "spark_intelligence" / "cli.py"
    command_markers: dict[str, bool] = {name: False for name in BUILDER_AOC_COMMAND_MARKERS}
    trace_ref_argument_present = False
    if cli_path.exists():
        try:
            text = cli_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        command_markers = {name: marker in text for name, marker in BUILDER_AOC_COMMAND_MARKERS.items()}
        trace_ref_argument_present = "--trace-ref" in text

    return {
        "path": str(path),
        "exists": path.exists(),
        "git_available": bool(git.get("available")),
        "branch": git.get("branch"),
        "upstream": git.get("upstream"),
        "ahead": git.get("ahead"),
        "behind": git.get("behind"),
        "dirty_tracked_count": git.get("dirty_tracked_count"),
        "untracked_count": git.get("untracked_count"),
        "dirty_family_counts": git_dirty_family_counts(path),
        "last_commit": git.get("last_commit"),
        "cli_path_exists": cli_path.exists(),
        "aoc_command_markers": command_markers,
        "aoc_command_marker_count": sum(1 for present in command_markers.values() if present),
        "trace_ref_argument_present": trace_ref_argument_present,
    }


def spawner_state_source_audit(path: Path) -> dict[str, Any]:
    path = Path(path)
    reference_needles = (".spawner", "SPAWNER_STATE_DIR", "spawnerStateDir", "spawner-state")
    family_counts: Counter[str] = Counter()
    file_count = 0
    for root_name in ["src", "scripts", "docs", "tests"]:
        root = path / root_name
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            if any(part in {"node_modules", ".git", "dist", "build", ".svelte-kit"} for part in candidate.parts):
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(needle in text for needle in reference_needles):
                file_count += 1
                family_counts[root_name] += 1

    state_helper = path / "src" / "lib" / "server" / "spawner-state.ts"
    helper_text = ""
    if state_helper.exists():
        try:
            helper_text = state_helper.read_text(encoding="utf-8", errors="replace")
        except OSError:
            helper_text = ""

    audit_route = path / "src" / "routes" / "api" / "system" / "state-root" / "+server.ts"
    spark_home_state_fallback_present = (
        "SPARK_HOME" in helper_text
        and "state" in helper_text
        and "spawner-ui" in helper_text
    )
    cwd_spawner_fallback_present = "'.spawner'" in helper_text or '".spawner"' in helper_text
    return {
        "path": str(path),
        "exists": path.exists(),
        "module_local_state_exists": (path / ".spawner").exists(),
        "state_root_audit_route_exists": audit_route.exists(),
        "state_helper_exists": state_helper.exists(),
        "configured_state_env_supported": "SPAWNER_STATE_DIR" in helper_text,
        "spark_home_state_fallback_present": spark_home_state_fallback_present,
        "cwd_spawner_fallback_present": cwd_spawner_fallback_present,
        "cwd_spawner_fallback_gated_by_spark_home": cwd_spawner_fallback_present and spark_home_state_fallback_present,
        "reference_file_count": file_count,
        "reference_family_counts": dict(sorted(family_counts.items())),
        "redaction": "source metadata only; no mission files, provider results, prompts, or state row contents read",
    }


def git_dirty_from_repo(repo: dict[str, Any]) -> tuple[int, int]:
    repo_dict = repo if isinstance(repo, dict) else {}
    git = as_dict(repo_dict.get("git"))
    dirty = int(git.get("dirty_tracked_count") or 0)
    untracked = int(git.get("untracked_count") or 0)
    if dirty or untracked:
        return dirty, untracked
    path = repo_dict.get("path")
    if isinstance(path, str) and path.strip():
        status = git_board_status(Path(path))
        return int(status.get("dirty_tracked_count") or 0), int(status.get("untracked_count") or 0)
    return 0, 0


def installed_runtime_clean_summary(installed_modules: dict[str, Any], module_id: str) -> dict[str, Any]:
    installed = as_dict(installed_modules.get(module_id))
    installed_path_raw = first_string(installed.get("path"), installed.get("source"))
    if not installed_path_raw:
        return {"clean": False, "path": "", "head": "", "reason": "not installed"}
    installed_path = Path(installed_path_raw)
    installed_git = git_board_status(installed_path)
    dirty = int(installed_git.get("dirty_tracked_count") or 0)
    untracked = int(installed_git.get("untracked_count") or 0)
    head = str(installed_git.get("head_commit") or "")[:12]
    return {
        "clean": dirty == 0 and untracked == 0,
        "path": str(installed_path),
        "head": head,
        "branch": installed_git.get("branch"),
        "dirty_tracked_count": dirty,
        "untracked_count": untracked,
        "reason": "" if dirty == 0 and untracked == 0 else "installed runtime dirty",
    }


def build_duplicate_truths(system_map: dict[str, Any]) -> dict[str, Any]:
    sys_map = system_map if isinstance(system_map, dict) else {}
    source_roots = as_dict(sys_map.get("source_roots"))
    spark_home = Path(str(source_roots.get("spark_home") or "")).expanduser()
    desktop = Path(str(source_roots.get("desktop") or "")).expanduser()
    installed_modules = as_dict(sys_map.get("installed_modules"))
    registry_modules = as_dict(as_dict(sys_map.get("registry")).get("modules"))
    items: list[dict[str, Any]] = []

    builder_installed = as_dict(installed_modules.get("spark-intelligence-builder"))
    builder_runtime_artifact = first_string(builder_installed.get("path"), builder_installed.get("source"))
    builder_owner_source = desktop / "spark-intelligence-builder"
    builder_nonrelease = spark_home / "modules" / "spark-intelligence-builder" / "source"
    if builder_runtime_artifact and builder_nonrelease.exists() and str(builder_nonrelease) != builder_runtime_artifact:
        runtime_audit = builder_source_audit(Path(builder_runtime_artifact))
        duplicate_audit = builder_source_audit(builder_nonrelease)
        desktop_audit = builder_source_audit(builder_owner_source)
        command_count = int(runtime_audit.get("aoc_command_marker_count") or 0)
        trace_ref_present = bool(runtime_audit.get("trace_ref_argument_present"))
        release_ready = command_count == len(BUILDER_AOC_COMMAND_MARKERS) and trace_ref_present
        runtime_clean = (
            int(runtime_audit.get("dirty_tracked_count") or 0) == 0
            and int(runtime_audit.get("untracked_count") or 0) == 0
        )
        duplicate_dirty = int(duplicate_audit.get("dirty_tracked_count") or 0) + int(duplicate_audit.get("untracked_count") or 0)
        builder_classification = "installed_legacy_backlog" if release_ready and runtime_clean else "active_legacy"
        builder_severity = "warning" if builder_classification == "installed_legacy_backlog" else "critical"
        builder_risk = (
            "Operators can patch the non-release duplicate and believe they changed active Builder truth, but installed module "
            "metadata and generated Telegram config point at the clean release source."
            if builder_classification == "installed_legacy_backlog"
            else "Operators can patch the dirty Desktop owner checkout or non-release duplicate and believe they changed the active Builder truth."
        )
        builder_next_action = (
            "Keep the release Builder source canonical. Treat the non-release installed-looking path and Desktop checkout as "
            "read-only backlog until a targeted feature slice is re-derived onto the clean release line."
            if builder_classification == "installed_legacy_backlog"
            else (
                "Treat the release Builder source as canonical for the current Spark OS line. Curate or replace the dirty "
                "Desktop owner checkout separately, and do not merge its backlog wholesale into the promoted source."
            )
        )
        items.append(
            duplicate_truth_item(
                item_id="builder-release-vs-nonrelease-installed-source",
                fact="Promoted Builder release source and legacy Builder sources",
                classification=builder_classification,
                severity=builder_severity,
                owner_repo="spark-intelligence-builder-release",
                canonical_path=str(Path(builder_runtime_artifact)),
                duplicate_path=str(builder_nonrelease),
                evidence=(
                    "Installed module metadata points at the promoted Builder release source while another installed-looking "
                    "Builder source and the dirty Desktop Builder owner checkout still exist. "
                    f"Promoted release source exposes {command_count}/{len(BUILDER_AOC_COMMAND_MARKERS)} AOC command markers"
                    f"{' with trace-ref support' if trace_ref_present else ' without detected trace-ref support'}."
                ),
                risk=builder_risk,
                next_safe_action=builder_next_action,
                verification_command="spark verify --onboarding --json",
                rollback="Repoint installed module metadata only after another Builder source passes the same AOC, trace, and live proof gates.",
                evidence_details={
                    "promoted_release_source": runtime_audit,
                    "desktop_backlog_source": desktop_audit,
                    "duplicate_nonrelease": duplicate_audit,
                    "duplicate_dirty_file_count": duplicate_dirty,
                    "onboarding_gate": "builder_runtime_source",
                    "local_source_probe": "Insert repo src on sys.path before importing spark_intelligence.cli build_parser.",
                    "source_truth_policy": "Release Builder source is canonical for the current Spark OS line; Desktop Builder is backlog until curated or replaced.",
                    "release_ready": release_ready,
                    "runtime_clean": runtime_clean,
                },
            )
        )

    spawner_installed = as_dict(installed_modules.get("spawner-ui"))
    spawner_source_raw = first_string(spawner_installed.get("path"), spawner_installed.get("source"))
    spawner_source = Path(spawner_source_raw) if spawner_source_raw else Path()
    spawner_state = spark_home / "state" / "spawner-ui"
    spawner_local_state = spawner_source / ".spawner" if spawner_source_raw else Path()
    spawner_state_audit_route = spawner_source / "src" / "routes" / "api" / "system" / "state-root" / "+server.ts"
    if spawner_source_raw and spawner_local_state.exists():
        spawner_audit = spawner_state_source_audit(spawner_source)
        audit_route_evidence = (
            " State-root audit route exists."
            if spawner_state_audit_route.exists()
            else " State-root audit route is not present yet."
        )
        if spawner_audit.get("cwd_spawner_fallback_gated_by_spark_home"):
            fallback_evidence = " Source still contains a cwd .spawner fallback, gated behind SPARK_HOME state fallback."
            spawner_classification = "active_legacy_gated"
            spawner_severity = "warning"
            spawner_next_action = (
                "Keep module-local state read-only and warning-only. Before archive, run a source-reference scan, "
                "two clean compiles, and one live trace proof showing no runtime read/write dependency."
            )
        elif spawner_audit.get("cwd_spawner_fallback_present"):
            fallback_evidence = " Source still contains a cwd .spawner fallback."
            spawner_classification = "active_legacy"
            spawner_severity = "critical"
            spawner_next_action = (
                "Keep module-local state read-only and warning-only. Before archive, replace or gate the cwd .spawner fallback, "
                "then rerun source-reference scan, two clean compiles, and one live trace proof."
            )
        else:
            fallback_evidence = " No cwd .spawner fallback was detected in the state helper."
            spawner_classification = "active_legacy_gated"
            spawner_severity = "warning"
            spawner_next_action = (
                "Keep module-local state read-only and warning-only. Before archive, run two clean compiles and one live trace proof."
            )
        items.append(
            duplicate_truth_item(
                item_id="spawner-module-local-state-root",
                fact="Spawner mission state root",
                classification=spawner_classification,
                severity=spawner_severity,
                owner_repo="spawner-ui",
                canonical_path=str(spawner_state),
                duplicate_path=str(spawner_local_state),
                evidence=(
                    "Current compiler and proof artifacts use spark-home state while module-local Spawner state also exists."
                    + audit_route_evidence
                    + fallback_evidence
                ),
                risk="Old mission files can be mistaken for current mission truth.",
                next_safe_action=spawner_next_action,
                verification_command="Invoke-WebRequest http://127.0.0.1:3333/api/system/state-root; rg -n \"\\\\.spawner|SPAWNER_STATE|stateDir\" src scripts",
                rollback="Leave module-local state untouched and read-only until current runtime no longer reads or writes it.",
                evidence_details=spawner_audit,
            )
        )

    for repo_name, fact, owner, classification in [
        ("spark-intelligence-builder", "Builder owner repo curation state", "spark-intelligence-builder", "owner_repo_dirty"),
        ("spark-telegram-bot", "Telegram owner repo curation state", "spark-telegram-bot", "owner_repo_dirty"),
        ("spawner-ui", "Spawner owner repo curation state", "spawner-ui", "owner_repo_dirty"),
        ("domain-chip-memory", "Memory substrate owner repo curation state", "domain-chip-memory", "owner_repo_dirty"),
        ("spark-memory-quality-dashboard", "Memory dashboard projection state", "spark-memory-quality-dashboard", "projection_dirty"),
    ]:
        repo = repo_by_name(sys_map, repo_name)
        if not repo:
            continue
        dirty, untracked = git_dirty_from_repo(repo)
        if dirty or untracked:
            runtime_module = {"spark-intelligence-builder": "spark-intelligence-builder", "spawner-ui": "spawner-ui"}.get(repo_name)
            runtime_summary = installed_runtime_clean_summary(installed_modules, runtime_module) if runtime_module else {}
            repo_path = str(repo.get("path") or "")
            installed_path = str(runtime_summary.get("path") or "")
            non_authoritative_backlog = bool(runtime_summary.get("clean")) and installed_path and repo_path and installed_path != repo_path
            item_classification = "read_only_backlog" if non_authoritative_backlog else classification
            severity = "warning" if owner not in {"spark-intelligence-builder", "spark-telegram-bot", "spawner-ui"} else "critical"
            risk = "Dirty source can be mistaken for released or installed truth before curation."
            next_safe_action = "Curate the worktree by feature family before merge, release, or cleanup."
            rollback = "Do not revert unrelated work; leave the worktree intact until source-owner curation."
            evidence = f"Repo board reports {dirty} tracked and {untracked} untracked local changes."
            evidence_details: dict[str, Any] | None = None
            if non_authoritative_backlog:
                severity = "warning"
                evidence += (
                    " Installed runtime truth is clean and points at a different source path, so this checkout is "
                    "classified as non-authoritative backlog."
                )
                risk = "Backlog source can confuse operators, but current installed runtime truth is clean and separate."
                next_safe_action = (
                    "Keep this checkout out of installer/release truth. Re-derive selected backlog slices onto the clean "
                    "canonical runtime line with focused tests before promotion."
                )
                rollback = "Leave the backlog checkout intact; keep installed runtime metadata pointed at the clean canonical source."
                evidence_details = {
                    "installed_runtime": runtime_summary,
                    "source_truth_policy": "Dirty Desktop checkout is backlog while clean installed runtime remains canonical.",
                }
            items.append(
                duplicate_truth_item(
                    item_id=f"{repo_name}-dirty-owner-repo",
                    fact=fact,
                    classification=item_classification,
                    owner_repo=owner,
                    canonical_path=repo_path,
                    duplicate_path="",
                    evidence=evidence,
                    risk=risk,
                    next_safe_action=next_safe_action,
                    verification_command="git status --short --branch",
                    rollback=rollback,
                    severity=severity,
                    evidence_details=evidence_details,
                )
            )

    for module_id, fact in [
        ("spark-telegram-bot", "Telegram installed runtime source"),
        ("spawner-ui", "Spawner installed runtime source"),
    ]:
        installed = as_dict(installed_modules.get(module_id))
        installed_path_raw = first_string(installed.get("path"), installed.get("source"))
        if installed_path_raw:
            installed_path = Path(installed_path_raw)
            installed_repo = collect_repo_metadata(installed_path)
            installed_git = git_board_status(installed_path)
            dirty, untracked = git_dirty_from_repo(installed_repo)
            if dirty or untracked:
                items.append(
                    duplicate_truth_item(
                        item_id=f"{module_id}-dirty-installed-runtime",
                        fact=fact,
                        classification="canonical_runtime_dirty",
                        severity="critical",
                        owner_repo=module_id,
                        canonical_path=str(installed_path),
                        duplicate_path="",
                        evidence=f"Running installed source has {dirty} tracked and {untracked} untracked local changes.",
                        risk="The current runtime can drift from owner repo, registry, and hosted installer truth.",
                        next_safe_action="Commit or port the minimum live-proof changes into the owner repo and release line.",
                        verification_command="git status --short --branch",
                        rollback="Keep runtime running from installed source until curated release proof passes.",
                    )
                )
            else:
                registry_entry = as_dict(registry_modules.get(module_id))
                registry_commit = str(installed.get("registry_commit") or registry_entry.get("commit") or "").strip().lower()
                registry_source = str(installed.get("registry_source") or registry_entry.get("source") or "").strip()
                head_commit = str(installed_git.get("head_commit") or "").strip().lower()
                if registry_commit and head_commit and registry_commit != head_commit:
                    branch = str(installed_git.get("branch") or "").strip()
                    remote_branch_head = str(git_remote_branch_head(installed_path, branch) or "").strip().lower()
                    release_branch_published = bool(
                        branch.startswith("release/stability-") and remote_branch_head and remote_branch_head == head_commit
                    )
                    classification = (
                        "release_branch_pending_registry_batch"
                        if release_branch_published
                        else "runtime_ahead_of_registry_pin"
                    )
                    severity = "decision" if release_branch_published else ("critical" if module_id == "spark-telegram-bot" else "warning")
                    evidence = (
                        "Running installed source is clean and its HEAD is already present on the release branch, "
                        "but the public registry commit still points at the previous installer batch. "
                        "This is an intentional release metadata decision, not dirty local file drift."
                        if release_branch_published
                        else "Running installed source is clean but its git HEAD differs from the registry commit. "
                        "This is release metadata drift, not dirty local file drift."
                    )
                    next_safe_action = (
                        "Include this clean release-branch runtime in the next named installer metadata batch, or hold the "
                        "current public registry pin if the batch is deferred."
                        if release_branch_published
                        else "Port and push the owner repo commit, update registry/release metadata, or explicitly keep this "
                        "installed source classified as a local runtime test artifact."
                    )
                    items.append(
                        duplicate_truth_item(
                            item_id=f"{module_id}-runtime-registry-pin-drift",
                            fact=f"{fact} release pin",
                            classification=classification,
                            severity=severity,
                            owner_repo=module_id,
                            canonical_path=str(installed_path),
                            duplicate_path=registry_source,
                            evidence=evidence,
                            risk="Spark start/restart/update can warn or move operators back to older public installer truth.",
                            next_safe_action=next_safe_action,
                            verification_command="spark status --json; git status --short --branch; git rev-parse HEAD",
                            rollback="Keep the current public registry pin until the newer runtime commit has source-owner release proof.",
                            evidence_details={
                                "installed_head": head_commit[:12],
                                "registry_commit": registry_commit[:12],
                                "branch": branch,
                                "remote_branch_head": remote_branch_head[:12] if remote_branch_head else None,
                                "release_branch_published": release_branch_published,
                                "runtime_dirty_tracked_count": dirty,
                                "runtime_untracked_count": untracked,
                            },
                        )
                    )

    browser_extension = repo_by_name(sys_map, "spark-browser-extension")
    if browser_extension:
        items.append(
            duplicate_truth_item(
                item_id="spark-browser-extension-planning-residue",
                fact="Browser/computer-use capability lane",
                classification="deprecated",
                owner_repo="spark-cli",
                canonical_path="browser-use lane through spark-cli authority policy",
                duplicate_path=str(browser_extension.get("path") or ""),
                evidence="Browser extension repo exists but current Spark plan uses browser-use through CLI authority and trace metadata.",
                risk="Old extension language can reintroduce a parallel capability surface.",
                next_safe_action="Keep browser-extension references historical; route active plans through browser-use.",
                verification_command="rg -n \"spark-browser-extension|browser extension\" docs README.md tasks.md",
                rollback="Keep old repo untouched as history; do not route runtime through it.",
                severity="decision",
            )
        )

    systems_repo = repo_by_name(system_map, "spark-intelligence-systems")
    if systems_repo:
        items.append(
            duplicate_truth_item(
                item_id="spark-intelligence-systems-prototype-compiler",
                fact="Spark OS compiler ownership",
                classification="projection",
                owner_repo="spark-cli",
                canonical_path="spark-cli production compiler",
                duplicate_path=str(systems_repo.get("path") or desktop / "spark-intelligence-systems"),
                evidence="spark-intelligence-systems remains doctrine/runbook/prototype while production compile output is owned by spark-cli.",
                risk="Prototype output can be mistaken for live OS truth.",
                next_safe_action="Keep doctrine here; keep runtime read-model artifacts source-owned by spark-cli.",
                verification_command="spark os compile",
                rollback="If production compiler fails, use this repo only as a reference, not runtime truth.",
                severity="decision",
            )
        )

    counts = Counter(str(item.get("classification")) for item in items)
    severity_counts = Counter(str(item.get("severity")) for item in items)
    return {
        "schema_version": DUPLICATE_TRUTHS_SCHEMA,
        "generated_at": utc_now(),
        "redaction": "metadata only; no diffs, env values, logs, prompts, memory bodies, transcripts, or provider output",
        "summary": {
            "item_count": len(items),
            "classification_counts": dict(sorted(counts.items())),
            "severity_counts": dict(sorted(severity_counts.items())),
        },
        "items": items,
    }


def build_repo_board(system_map: dict[str, Any]) -> dict[str, Any]:
    sys_map = system_map if isinstance(system_map, dict) else {}
    registry_modules = set(as_dict(as_dict(sys_map.get("registry")).get("modules")).keys())
    installed_modules = set(as_dict(sys_map.get("installed_modules")).keys())
    rows: list[dict[str, Any]] = []

    for repo in as_list(sys_map.get("discovered_repos")):
        repo = as_dict(repo)
        name = str(repo.get("name") or "")
        ids = repo_ids(repo)
        registry_present = bool(ids & registry_modules)
        installed_present = bool(ids & installed_modules)
        git = git_board_status(Path(str(repo.get("path") or "")))
        manifest = repo_manifest_presence(repo)
        release_eligibility, do_not_merge_reason, next_safe_action = repo_release_status(name, git, manifest, registry_present)
        rows.append(
            {
                "repo": name,
                "path": repo.get("path"),
                "branch": git.get("branch"),
                "upstream": git.get("upstream"),
                "ahead": git.get("ahead"),
                "behind": git.get("behind"),
                "dirty_tracked_count": git.get("dirty_tracked_count"),
                "untracked_count": git.get("untracked_count"),
                "last_commit": git.get("last_commit"),
                "git_available": git.get("available"),
                "manifest_presence": manifest,
                "registry_present": registry_present,
                "installed_present": installed_present,
                "module_ids": sorted(ids),
                "owner_surface": repo_owner_surface(name),
                "release_eligibility": release_eligibility,
                "risk_class": repo_risk_class(name, release_eligibility),
                "next_safe_action": next_safe_action,
                "do_not_merge_reason": do_not_merge_reason,
            }
        )

    summary = {
        "repo_count": len(rows),
        "git_repo_count": sum(1 for row in rows if row["git_available"]),
        "dirty_repo_count": sum(1 for row in rows if int(row.get("dirty_tracked_count") or 0) or int(row.get("untracked_count") or 0)),
        "blocked_release_count": sum(1 for row in rows if row["release_eligibility"] == "blocked"),
        "critical_repo_count": sum(1 for row in rows if row["risk_class"] == "critical"),
    }
    duplicate_truths = build_duplicate_truths(sys_map)
    summary["duplicate_truth_count"] = as_dict(duplicate_truths.get("summary")).get("item_count", 0)
    summary["critical_duplicate_truth_count"] = as_dict(
        as_dict(duplicate_truths.get("summary")).get("severity_counts")
    ).get("critical", 0)
    ranked = sorted(
        rows,
        key=lambda row: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(row["risk_class"]), 4),
            {"blocked": 0, "inspect": 1, "eligible": 2, "not_release_candidate": 3}.get(str(row["release_eligibility"]), 4),
            str(row["repo"]).lower(),
        ),
    )
    return {
        "schema_version": REPO_BOARD_SCHEMA,
        "generated_at": utc_now(),
        "redaction": "repo status metadata only; filenames, diffs, env files, logs, and untracked file names omitted",
        "summary": summary,
        "next_actions": [
            {
                "repo": row["repo"],
                "risk_class": row["risk_class"],
                "release_eligibility": row["release_eligibility"],
                "next_safe_action": row["next_safe_action"],
                "do_not_merge_reason": row["do_not_merge_reason"],
            }
            for row in ranked[:20]
        ],
        "duplicate_truths": duplicate_truths,
        "repos": rows,
    }


def build_voice_surface_view(system_map: dict[str, Any]) -> dict[str, Any]:
    sys_map = system_map if isinstance(system_map, dict) else {}
    repos = [as_dict(repo) for repo in as_list(sys_map.get("discovered_repos"))]
    repo_names = {str(repo.get("name")) for repo in repos}
    repo_paths = {
        str(repo.get("name")): Path(str(repo.get("path"))).expanduser()
        for repo in repos
        if isinstance(repo.get("path"), str) and str(repo.get("path")).strip()
    }
    installed_modules = set(as_dict(sys_map.get("installed_modules")).keys())
    available = "spark-voice-comms" in repo_names
    installed = "spark-voice-comms" in installed_modules
    source_roots = as_dict(sys_map.get("source_roots"))

    runtime_state_error = "spark_home_missing"
    runtime_state: dict[str, Any] = {}
    spark_home_raw = source_roots.get("spark_home")
    if isinstance(spark_home_raw, str) and spark_home_raw.strip():
        runtime_state_path = Path(spark_home_raw).expanduser() / "state" / "spark-voice-comms" / "voice-runtime-state.json"
        runtime_state_raw, runtime_state_error = read_json(runtime_state_path)
        if isinstance(runtime_state_raw, dict):
            runtime_state = runtime_state_raw

    runtime_state_export_present = as_dict(runtime_state).get("schema_version") == "spark.voice_runtime_state.v1"
    if runtime_state and not runtime_state_export_present:
        runtime_state_error = "invalid_schema"

    runtime_stt = as_dict(as_dict(runtime_state).get("stt")) if runtime_state_export_present else {}
    runtime_tts = as_dict(as_dict(runtime_state).get("tts")) if runtime_state_export_present else {}
    runtime_delivery = as_dict(as_dict(runtime_state).get("telegram_delivery")) if runtime_state_export_present else {}
    runtime_claims = as_dict(as_dict(runtime_state).get("claim_levels")) if runtime_state_export_present else {}
    runtime_sources = [str(item) for item in as_list(as_dict(runtime_state).get("source_ledger"))] if runtime_state_export_present else []
    stt_ready = runtime_stt.get("ready") is True
    tts_ready = runtime_tts.get("ready") is True
    delivery_ready = runtime_delivery.get("ready") is True
    configured = runtime_claims.get("configured") is True or stt_ready or tts_ready

    def source_file_contains(repo_name: str, relative: str, *needles: str) -> bool:
        repo_name = str(repo_name or "")
        relative = str(relative or "")
        root = repo_paths.get(repo_name)
        if root is None:
            return False
        path = root / relative
        if not path.exists() or not path.is_file():
            return False
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return all(str(needle) in text for needle in needles)

    voice_hook_has_transcribe = source_file_contains(
        "spark-voice-comms",
        "src/voice_comms_chip/spark_hook.py",
        "voice.transcribe",
    )
    voice_hook_has_speak = source_file_contains(
        "spark-voice-comms",
        "src/voice_comms_chip/spark_hook.py",
        "voice.speak",
    )
    voice_hook_has_status = source_file_contains(
        "spark-voice-comms",
        "src/voice_comms_chip/spark_hook.py",
        "voice.status",
    )
    builder_has_transcribe_bridge = source_file_contains(
        "spark-intelligence-builder",
        "src/spark_intelligence/adapters/telegram/runtime.py",
        "voice.transcribe",
    )
    builder_has_speak_bridge = source_file_contains(
        "spark-intelligence-builder",
        "src/spark_intelligence/adapters/telegram/runtime.py",
        "voice.speak",
    )
    builder_has_status_bridge = source_file_contains(
        "spark-intelligence-builder",
        "src/spark_intelligence/adapters/telegram/runtime.py",
        "voice.status",
    )
    builder_has_transcript_preview = source_file_contains(
        "spark-intelligence-builder",
        "src/spark_intelligence/adapters/telegram/runtime.py",
        "voice_transcript_preview",
    )
    telegram_has_voice_bridge = source_file_contains(
        "spark-telegram-bot",
        "src/telegramVoiceBridge.ts",
        "voice",
    ) or source_file_contains(
        "spark-telegram-bot",
        "src/index.ts",
        "telegramVoiceBridge",
    )

    ingress_source_present = voice_hook_has_transcribe and builder_has_transcribe_bridge
    egress_source_present = voice_hook_has_speak and builder_has_speak_bridge
    if ingress_source_present and egress_source_present:
        source_mode = "duplex"
    elif ingress_source_present:
        source_mode = "ingress"
    elif egress_source_present:
        source_mode = "egress"
    else:
        source_mode = "disabled"

    runtime_egress_ready = tts_ready and delivery_ready
    if stt_ready and runtime_egress_ready:
        runtime_mode = "duplex"
    elif stt_ready:
        runtime_mode = "ingress"
    elif runtime_egress_ready:
        runtime_mode = "egress"
    else:
        runtime_mode = source_mode

    hard_blocked = not available or not installed or source_mode == "disabled" or builder_has_transcript_preview
    final_answer_supported = delivery_ready and telegram_has_voice_bridge

    blockers = []
    if not available:
        blockers.append("spark-voice-comms repo not discovered")
    if available and not installed:
        blockers.append("spark-voice-comms is not installed in local Spark state")
    if available and source_mode == "disabled":
        blockers.append("voice ingress/egress source hooks are not detected")
    if available and installed and not runtime_state_export_present:
        blockers.append("voice provider/profile runtime status is not exported to Spark OS state")
    if runtime_state_export_present and runtime_claims.get("synthesis_ready") is not True:
        blockers.append("voice synthesis is not ready")
    if runtime_state_export_present and runtime_claims.get("delivery_ready") is not True:
        blockers.append("voice Telegram delivery is not proven")
    if not final_answer_supported:
        blockers.append("voice final-answer join evidence is not compiled")
    if builder_has_transcript_preview:
        blockers.append("Builder retains raw voice transcript preview in private trace fields")

    trace_evidence = "missing_source_hooks"
    if source_mode != "disabled" and runtime_state_export_present:
        trace_evidence = "runtime_state_export_present"
        if not final_answer_supported:
            trace_evidence = "runtime_state_export_present_delivery_unproven"
    elif source_mode != "disabled":
        trace_evidence = "source_present_not_proven"

    provider_kind = first_string(
        runtime_stt.get("provider_kind"),
        runtime_stt.get("mode"),
        runtime_tts.get("mode"),
        "unknown",
    )
    voice_style_ref = first_string(
        runtime_tts.get("voice_name"),
        runtime_tts.get("voice_id_masked"),
        runtime_tts.get("voice_id_fingerprint"),
    )

    return {
        "schema_version": VOICE_SURFACE_SCHEMA,
        "generated_at": utc_now(),
        "owner_system": "spark-voice-comms",
        "mode": "disabled" if hard_blocked else runtime_mode,
        "source_capability": {
            "repo_discovered": available,
            "installed_in_spark_state": installed,
            "source_mode": source_mode,
            "ingress_source_present": ingress_source_present,
            "egress_source_present": egress_source_present,
            "duplex_source_present": source_mode == "duplex",
            "status_hook_present": voice_hook_has_status and builder_has_status_bridge,
            "telegram_bridge_present": telegram_has_voice_bridge,
        },
        "provider": {
            "configured": configured,
            "kind": provider_kind if configured else "unknown",
            "stt_ready": stt_ready,
            "tts_ready": tts_ready,
            "runtime_state_export_present": runtime_state_export_present,
        },
        "profile": {"configured": bool(voice_style_ref), "voice_style_ref": voice_style_ref or None},
        "authority": {
            "can_answer": runtime_egress_ready and final_answer_supported and not hard_blocked,
            "can_trigger_actions": False,
            "requires_confirmation_for_actions": True,
        },
        "memory_policy": {
            "transcripts_are_durable_by_default": False,
            "raw_audio_exported_to_os_artifacts": False,
            "transcript_bodies_exported_to_os_artifacts": False,
        },
        "trace": {
            "voice_events_supported": bool(runtime_sources),
            "final_answer_check_supported": final_answer_supported,
            "source_hooks_present": source_mode != "disabled",
            "telegram_delivery_bridge_present": telegram_has_voice_bridge,
            "runtime_state_export_present": runtime_state_export_present,
            "runtime_state_error": None if runtime_state_export_present else runtime_state_error,
            "stt_ready": stt_ready,
            "tts_ready": tts_ready,
            "delivery_ready": delivery_ready,
            "conversation_ready": runtime_claims.get("conversation_ready") is True,
            "trace_evidence": trace_evidence,
        },
        "privacy_findings": {"builder_transcript_preview_present": builder_has_transcript_preview},
        "blockers": blockers,
        "redaction": "metadata only; raw audio, transcript bodies, provider secrets, and voice profile secrets omitted",
    }


def build_operating_cockpit(compiled: dict[str, Any]) -> dict[str, Any]:
    compiled = compiled if isinstance(compiled, dict) else {}
    system_map = as_dict(compiled.get("system_map"))
    repo_board = as_dict(compiled.get("repo_board"))
    trace_index = as_dict(compiled.get("trace_index"))
    capability_catalog = as_dict(compiled.get("capability_catalog"))
    voice_surface = as_dict(compiled.get("voice_surface_view"))
    duplicate_truths = as_dict(repo_board.get("duplicate_truths"))
    return {
        "schema_version": OPERATING_COCKPIT_SCHEMA,
        "generated_at": utc_now(),
        "product_decision": "Spark Operating Cockpit is the single daily command center. Source repos keep runtime truth; the Cockpit owns the unified operator experience.",
        "privacy": {
            "raw_secret_values_allowed": False,
            "raw_chat_ids_allowed": False,
            "raw_user_wording_allowed": False,
            "raw_memory_bodies_allowed": False,
            "raw_audio_allowed": False,
            "raw_transcript_bodies_allowed": False,
        },
        "input_artifacts": {
            "system_map": {
                "schema_version": system_map.get("schema_version"),
                "module_count": len(as_list(system_map.get("modules"))),
                "repo_count": len(as_list(system_map.get("discovered_repos"))),
            },
            "repo_board": {
                "schema_version": repo_board.get("schema_version"),
                "repo_count": as_dict(repo_board.get("summary")).get("repo_count"),
                "dirty_repo_count": as_dict(repo_board.get("summary")).get("dirty_repo_count"),
                "duplicate_truth_count": as_dict(repo_board.get("summary")).get("duplicate_truth_count"),
            },
            "trace_index": {
                "schema_version": trace_index.get("schema_version"),
                "builder_event_count": as_dict(trace_index.get("builder_events")).get("row_count"),
                "trace_repair_candidate_count": len(as_list(trace_index.get("trace_repair_queue"))),
                "builder_trace_repair_card_count": as_dict(trace_index.get("builder_trace_repair_cards")).get(
                    "card_count"
                ),
                "authority_verdict_count": as_dict(trace_index.get("authority_verdicts")).get("verdict_count"),
                "review_candidate_count": as_dict(as_dict(trace_index.get("review_candidates")).get("counts")).get(
                    "candidate_count"
                ),
            },
            "capability_catalog": {
                "schema_version": capability_catalog.get("schema_version"),
                "capability_card_count": len(as_list(capability_catalog.get("capability_cards"))),
                "chip_manifest_count": len(as_list(capability_catalog.get("chip_manifests"))),
            },
            "voice_surface": {
                "schema_version": voice_surface.get("schema_version"),
                "mode": voice_surface.get("mode"),
                "blocker_count": len(as_list(voice_surface.get("blockers"))),
            },
            "memory_review_queue": {
                "schema_version": as_dict(as_dict(compiled.get("memory_movement_index")).get("memory_review_queue")).get(
                    "schema_version"
                ),
                "item_count": as_dict(
                    as_dict(as_dict(compiled.get("memory_movement_index")).get("memory_review_queue")).get("counts")
                ).get("item_count"),
            },
        },
        "action_boundary": "Read-only until high-agency actions carry AuthorityVerdictV1 trace evidence.",
        "trace_repair_queue": as_list(trace_index.get("trace_repair_queue"))[:5],
        "builder_trace_repair_cards": as_list(as_dict(trace_index.get("builder_trace_repair_cards")).get("items"))[:10],
        "review_candidates": as_list(as_dict(trace_index.get("review_candidates")).get("items"))[:5],
        "duplicate_truths": {
            "schema_version": duplicate_truths.get("schema_version"),
            "summary": duplicate_truths.get("summary"),
            "items": as_list(duplicate_truths.get("items"))[:10],
        },
        "authority_verdicts": as_list(as_dict(trace_index.get("authority_verdicts")).get("items"))[:5],
        "memory_review_queue": as_list(
            as_dict(as_dict(compiled.get("memory_movement_index")).get("memory_review_queue")).get("items")
        )[:5],
        "top_blockers": as_list(system_map.get("gaps"))[:10],
    }


def compile_system_map(desktop: Path, spark_home: Path, registry_path: Path) -> dict[str, Any]:
    desktop = Path(desktop)
    spark_home = Path(spark_home)
    registry_path = Path(registry_path)
    state_dir = spark_home / "state"
    registry, registry_error = read_json(registry_path)
    installed, installed_error = read_json(state_dir / "installed.json")
    setup, setup_error = read_json(state_dir / "setup.json")
    pids, pids_error = read_json(state_dir / "pids.json")

    installed_summary = summarize_installed(installed if isinstance(installed, dict) else None)
    registry_summary = summarize_registry(registry if isinstance(registry, dict) else None)
    setup_summary = summarize_setup(setup if isinstance(setup, dict) else None)
    running = summarize_pids(pids if isinstance(pids, dict) else None)

    repo_paths = discover_repo_paths(desktop, installed if isinstance(installed, dict) else None)
    repos = [collect_repo_metadata(path) for path in repo_paths]
    builder_home = Path(str(setup_summary.get("builder_home") or state_dir / "spark-intelligence")).expanduser()

    system_map: dict[str, Any] = {
        "schema_version": SYSTEM_MAP_SCHEMA,
        "generated_at": utc_now(),
        "generator": "spark_cli.system_map",
        "privacy": {
            "raw_secret_values_read": False,
            "raw_logs_read": False,
            "raw_conversation_content_read": False,
            "raw_memory_evidence_read": False,
            "sqlite_row_contents_read": False,
        },
        "source_roots": {"desktop": str(desktop), "spark_home": str(spark_home), "registry": str(registry_path)},
        "source_errors": {"registry": registry_error, "installed": installed_error, "setup": setup_error, "pids": pids_error},
        "setup": setup_summary,
        "registry": registry_summary,
        "installed_modules": installed_summary,
        "running_processes": running,
        "discovered_repos": repos,
        "builder_state_db": inspect_builder_state_db(builder_home),
        "upgrade_ledger": summarize_upgrade_ledger(repo_paths),
        "capability_ledger": summarize_capability_ledger(builder_home),
    }
    system_map["modules"] = build_modules(registry_summary, installed_summary, repos, running)
    system_map["gaps"] = build_gaps(system_map)

    compiled = {
        "system_map": system_map,
        "authority_view": build_authority_view(desktop, setup_summary, spark_home),
        "capability_catalog": build_capability_catalog(repos),
        "trace_index": build_trace_index(spark_home, builder_home),
        "memory_movement_index": build_memory_movement_index(builder_home),
    }
    compiled["repo_board"] = build_repo_board(system_map)
    compiled["voice_surface_view"] = build_voice_surface_view(system_map)
    compiled["operating_cockpit"] = build_operating_cockpit(compiled)
    return compiled


def write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_gaps_markdown(path: Path, gaps: list[dict[str, str]], system_map: dict[str, Any]) -> None:
    path = Path(path)
    system_map = system_map if isinstance(system_map, dict) else {}
    lines = [
        "# Spark System Map Gaps",
        "",
        f"Generated: {system_map.get('generated_at')}",
        "",
        "This report is generated from metadata only. It should not contain raw secrets, raw conversations, raw memory evidence, or logs.",
        "",
        "## Summary",
        "",
        f"- modules compiled: {len(as_list(system_map.get('modules')))}",
        f"- discovered repos: {len(as_list(system_map.get('discovered_repos')))}",
        f"- gaps: {len(as_list(gaps))}",
        "",
        "## Gaps",
        "",
    ]
    gaps_list = as_list(gaps)
    if not gaps_list:
        lines.append("- No gaps detected by this compiler pass.")
    else:
        for gap in gaps_list:
            gap_dict = as_dict(gap)
            count = int(gap_dict.get("count", "1"))
            suffix = f" Observed {count} times." if count > 1 else ""
            lines.append(f"- [{gap_dict.get('severity')}] {gap_dict.get('area')} / {gap_dict.get('item')}: {gap_dict.get('message')}{suffix}")
    lines.extend(
        [
            "",
            "## Next Bridges",
            "",
            "1. Promote this generated map into Builder's AOC panel as a read-only source.",
            "2. Deepen trace-index compilation from aggregate counts into redacted trace drilldowns.",
            "3. Have Builder publish a safe memory movement status export for the compiler to ingest.",
            "4. Add per-gap owner assignment before any runtime behavior changes.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_compiled_outputs(out_dir: Path, compiled: dict[str, Any]) -> dict[str, str]:
    out_dir = Path(out_dir)
    compiled = compiled if isinstance(compiled, dict) else {}
    system_map = as_dict(compiled.get("system_map"))
    paths = {
        "system_map": out_dir / "system-map.json",
        "authority_view": out_dir / "authority-view.json",
        "capability_catalog": out_dir / "capability-catalog.json",
        "trace_index": out_dir / "trace-index.json",
        "memory_movement_index": out_dir / "memory-movement-index.json",
        "repo_board": out_dir / "repo-board.json",
        "voice_surface_view": out_dir / "voice-surface-view.json",
        "operating_cockpit": out_dir / "operating-cockpit.json",
        "gaps": out_dir / "gaps.md",
    }
    write_json(paths["system_map"], system_map)
    write_json(paths["authority_view"], compiled.get("authority_view"))
    write_json(paths["capability_catalog"], compiled.get("capability_catalog"))
    write_json(paths["trace_index"], compiled.get("trace_index"))
    write_json(paths["memory_movement_index"], compiled.get("memory_movement_index"))
    write_json(paths["repo_board"], compiled.get("repo_board"))
    write_json(paths["voice_surface_view"], compiled.get("voice_surface_view"))
    write_json(paths["operating_cockpit"], compiled.get("operating_cockpit"))
    write_gaps_markdown(paths["gaps"], as_list(system_map.get("gaps")), system_map)
    return {key: str(path) for key, path in paths.items()}


def compile_summary(compiled: dict[str, Any], written: dict[str, str] | None = None) -> dict[str, Any]:
    compiled = compiled if isinstance(compiled, dict) else {}
    written = written if isinstance(written, dict) else {}
    system_map = as_dict(compiled.get("system_map"))
    capability_catalog = as_dict(compiled.get("capability_catalog"))
    trace_index = as_dict(compiled.get("trace_index"))
    memory_index = as_dict(compiled.get("memory_movement_index"))
    repo_board = as_dict(compiled.get("repo_board"))
    voice_surface = as_dict(compiled.get("voice_surface_view"))
    duplicate_truths = as_dict(repo_board.get("duplicate_truths"))
    builder_events = as_dict(trace_index.get("builder_events"))
    builder_event_samples = as_dict(trace_index.get("builder_event_samples"))
    builder_trace_groups = as_dict(trace_index.get("builder_trace_groups"))
    builder_trace_health = as_dict(trace_index.get("builder_trace_health"))
    review_candidates = as_dict(trace_index.get("review_candidates"))
    memory_status = as_dict(as_dict(memory_index.get("safe_status_export")).get("status"))
    builder_memory_tables = as_dict(memory_index.get("builder_memory_tables"))
    return {
        "schema_version": "spark.os_compile.summary.v0",
        "generated_at": system_map.get("generated_at"),
        "modules": len(as_list(system_map.get("modules"))),
        "repos": len(as_list(system_map.get("discovered_repos"))),
        "gaps": len(as_list(system_map.get("gaps"))),
        "chip_manifests": len(as_list(capability_catalog.get("chip_manifests"))),
        "skill_graphs": len(as_list(capability_catalog.get("skill_graphs"))),
        "creator_system_surfaces": len(as_list(capability_catalog.get("creator_system_surfaces"))),
        "specialization_path_surfaces": len(as_list(capability_catalog.get("specialization_path_surfaces"))),
        "capability_cards": len(as_list(capability_catalog.get("capability_cards"))),
        "authority_sources": {
            key: as_dict(value).get("exists")
            for key, value in as_dict(as_dict(compiled.get("authority_view")).get("observed_sources")).items()
        },
        "builder_event_rows": builder_events.get("row_count"),
        "builder_event_samples": builder_event_samples.get("sample_count"),
        "builder_trace_groups": builder_trace_groups.get("group_count"),
        "builder_trace_health_flags": as_list(builder_trace_health.get("health_flags")),
        "review_candidates": as_dict(review_candidates.get("counts")).get("candidate_count"),
        "memory_movement_status": memory_status.get("status"),
        "memory_movement_rows": memory_status.get("row_count"),
        "builder_memory_table_count": builder_memory_tables.get("table_count"),
        "repo_board": as_dict(repo_board.get("summary")),
        "duplicate_truths": as_dict(duplicate_truths.get("summary")),
        "voice_surface_mode": voice_surface.get("mode"),
        "voice_surface_blockers": len(as_list(voice_surface.get("blockers"))),
        "privacy": system_map.get("privacy"),
        "outputs": written or {},
    }
