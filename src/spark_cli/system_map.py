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
TRACE_INDEX_SCHEMA = "spark.trace_index.compiled.v0"
MEMORY_MOVEMENT_INDEX_SCHEMA = "spark.memory_movement_index.compiled.v0"
MEMORY_REVIEW_QUEUE_SCHEMA = "spark.memory_review_queue.v1"
REPO_BOARD_SCHEMA = "spark.repo_board.compiled.v0"
VOICE_SURFACE_SCHEMA = "spark.voice_surface_view.compiled.v0"
OPERATING_COCKPIT_SCHEMA = "spark.operating_cockpit.compiled.v0"

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

SWARM_PUBLICATION_GOVERNANCE_FILES = {
    "contract_types": "packages/contracts/src/index.ts",
    "service_reads": "apps/api/src/collective/service-reads.ts",
    "sync_validation": "apps/api/src/collective/sync-validation.ts",
    "publication_signatures": "apps/api/src/collective/publication-proof-signatures.ts",
    "github_delivery_support": "apps/api/src/collective/delivery-github-support.ts",
    "pull_request_delivery": "apps/api/src/collective/pull-request-delivery.ts",
    "github_insight_review_template": "templates/github-insight-review/README.md",
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
    except Exception as exc:
        return None, f"read_json_failed: {type(exc).__name__}: {exc}"


def read_toml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:
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
        for child in desktop.iterdir():
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
    except Exception:
        return {"available": True, "head_short": None}
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
    except Exception:
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
    return {
        "available": True,
        "branch": branch_status["branch"] or None,
        "upstream": branch_status["upstream"],
        "ahead": branch_status["ahead"],
        "behind": branch_status["behind"],
        "dirty_tracked_count": dirty_tracked_count,
        "untracked_count": untracked_count,
        "last_commit": commit if code == 0 and commit else None,
    }


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
    except Exception as exc:
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
                    except Exception:
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
        except Exception as exc:
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
    except Exception as exc:
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
    except Exception as exc:
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
    except Exception as exc:
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
    lowered = value.lower()
    return bool(
        re.search(r"(human|telegram|user|chat):", lowered)
        or re.search(r"\d{7,}", lowered)
        or re.search(r"(?i)(token|secret|api[_-]?key)", lowered)
    )


def redacted_identifier(column: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"{column}:redacted:{digest}"


def safe_builder_event_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    if column in BUILDER_EVENT_IDENTIFIER_COLUMNS and sensitive_identifier(text):
        return redacted_identifier(column, text)
    return safe_short_string(text, limit=160)


def key_has_raw_memory_hint(key: Any) -> bool:
    lowered = str(key).lower()
    return any(hint in lowered for hint in RAW_MEMORY_KEY_HINTS)


def safe_memory_status_value(value: Any, *, depth: int = 0) -> Any:
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
    except Exception as exc:
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
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    out["schema_count"] = len(names)
    out["schemas"] = names
    return out


def inspect_labs_creator_surface(repo_path: Path) -> dict[str, Any] | None:
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
        "repo": repo_path.name,
        "schema_inventory": count_schema_files(schema_dir),
        "review_and_release_sources": {
            label: {"path": str(repo_path / rel_path), "exists": (repo_path / rel_path).exists()}
            for label, rel_path in LABS_CREATOR_SURFACE_FILES.items()
        },
        "creator_run_artifacts": {
            "run_count": run_count,
            "artifact_presence_counts": dict(sorted(artifact_counts.items())),
        },
        "claim_boundary": (
            "Creator-system schemas and run artifacts are compatibility and review evidence; "
            "they are not network publication approval or durable memory truth."
        ),
    }


def inspect_swarm_specialization_surface(repo_path: Path) -> dict[str, Any] | None:
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
    path_rows = as_list(as_dict(config).get("paths")) if isinstance(config, dict) else []
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
        "repo": repo_path.name,
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
    missing_proofs: list[str],
) -> dict[str, Any]:
    return {
        "trust_status": "untrusted",
        "proof_state": capability_proof_state(status),
        "trust_scope": "none",
        "trust_basis": trust_basis,
        "compiled_proofs": compiled_proofs,
        "missing_proofs": missing_proofs,
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
        trust = capability_trust_fields(
            status=status,
            compiled_proofs={
                "schema_present": schema_count > 0,
                "local_artifacts_present": creator_run_count > 0,
                "benchmark_manifest_present": benchmark_manifest_count > 0,
                "review_sources_present": review_source_count > 0,
                "trace_refs_present": False,
                "rollback_refs_present": False,
                "privacy_review_verdict_present": False,
                "publication_approval_present": False,
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
            missing_proofs=[
                "normalized_gate_verdict",
                "benchmark_pass_fail_verdict",
                "privacy_review_verdict",
                "rollback_ref",
                "authority_scope_verdict",
                "publication_approval",
            ],
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
                    "Gate verdicts are not normalized into the card yet.",
                    "Privacy and rollback reviews are not compiled into the card yet.",
                    "Network publication approval is not compiled into the card yet.",
                ],
                "next_action": "Normalize release-gate, operator-review, product-runtime-review, privacy, and rollback verdicts.",
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
                "rollback_refs_present": False,
                "publication_approval_present": False,
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
            missing_proofs=[
                "benchmark_pass_fail_verdict",
                "publication_approval_verdict",
                "privacy_review_verdict",
                "rollback_ref",
                "authority_scope_verdict",
                "trace_or_proof_ref",
            ],
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
                    "Benchmark pass/fail verdicts are not compiled into the card yet.",
                    "Publication approval verdict is not compiled into the card yet.",
                    "Privacy and rollback reviews are not compiled into the card yet.",
                ],
                "next_action": "Normalize benchmark, publication-proof, privacy, and rollback verdicts into capability status.",
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
    except Exception as exc:
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
    }


def build_memory_review_queue(memory_index: dict[str, Any]) -> dict[str, Any]:
    safe_status = as_dict(memory_index.get("safe_status_export"))
    status = as_dict(safe_status.get("status"))
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

    if row_count:
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
        try:
            tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table' order by name")]
            memory_tables = [table for table in tables if "memory" in table.lower()]
            out["table_count"] = len(memory_tables)
            out["tables"] = {}
            for table in memory_tables:
                count = conn.execute(f'select count(*) from "{table}"').fetchone()[0]
                out["tables"][table] = {"row_count": int(count)}
        finally:
            conn.close()
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
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
    except Exception as exc:
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
    except Exception as exc:
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
    except Exception as exc:
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
                group_columns = [
                    column
                    for column in ("component", "event_type", "status", "severity", "target_surface", "evidence_lane")
                    if column in columns
                ]
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
                    out["missing_trace_ref_sources"] = {
                        "group_by": group_columns,
                        "limit": 30,
                        "redaction": "aggregate counts grouped by allowlisted event metadata only",
                        "rows": [
                            {
                                **{column: str(row[index] or "[missing]") for index, column in enumerate(group_columns)},
                                "event_count": int(row[len(group_columns)] or 0),
                            }
                            for row in rows
                        ],
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
    except Exception as exc:
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
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except Exception:
        return None


def literal_assignment(text: str | None, name: str) -> Any:
    if not text:
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
                try:
                    return ast.literal_eval(node.value)
                except Exception:
                    return None
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            try:
                return ast.literal_eval(node.value)
            except Exception:
                return None
    return None


def regex_int(text: str | None, pattern: str) -> int | None:
    if not text:
        return None
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def regex_string(text: str | None, pattern: str) -> str | None:
    if not text:
        return None
    match = re.search(pattern, text)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def parse_ts_union(text: str | None, type_name: str) -> list[str]:
    if not text:
        return []
    match = re.search(rf"export\s+type\s+{re.escape(type_name)}\s*=\s*([^;]+);", text, re.S)
    if not match:
        return []
    return re.findall(r"'([^']+)'|\"([^\"]+)\"", match.group(1))


def clean_ts_union(values: list[tuple[str, str]] | list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        if isinstance(value, tuple):
            item = next((part for part in value if part), "")
        else:
            item = value
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def parse_ts_union_values(text: str | None, type_name: str) -> list[str]:
    return clean_ts_union(parse_ts_union(text, type_name))


def ts_function_body(text: str | None, function_name: str) -> str:
    if not text:
        return ""
    match = re.search(
        rf"export\s+function\s+{re.escape(function_name)}\s*\([^)]*\)[^{{]*{{(?P<body>.*?)\n}}",
        text,
        re.S,
    )
    return match.group("body") if match else ""


def ts_allowed_profiles(text: str | None, function_name: str, profiles: list[str]) -> list[str]:
    body = ts_function_body(text, function_name)
    if not body:
        return []
    denied = set(re.findall(r"profile\s*!==\s*'([^']+)'", body))
    if denied:
        return [profile for profile in profiles if profile not in denied]
    allowed = re.findall(r"profile\s*===\s*'([^']+)'", body)
    return [profile for profile in profiles if profile in set(allowed)]


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
    if not text:
        return ""
    marker_index = text.find(marker)
    if marker_index < 0:
        return ""
    start = text.find("{", marker_index)
    if start < 0:
        return ""
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
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
                return text[start + 1 : index]
    return ""


def inspect_spawner_access_sources(root: Path) -> dict[str, Any]:
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
    if not text:
        return {}
    match = re.search(rf"export\s+const\s+{re.escape(object_name)}\s*=\s*{{(?P<body>.*?)\n}};", text, re.S)
    if not match:
        return {}
    return {key: value for key, value in re.findall(r"(\w+):\s*['\"]([^'\"]+)['\"]", match.group("body"))}


def inspect_browser_authority(root: Path) -> dict[str, Any]:
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


def build_authority_view(desktop: Path, setup_summary: dict[str, Any]) -> dict[str, Any]:
    source_files = {
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
    observed_sources = {name: {"path": str(path), "exists": path.exists()} for name, path in source_files.items()}

    cli_access = inspect_cli_access_source(source_files["cli_access_policy"])
    cli_capability_policy = inspect_cli_capability_source(source_files["cli_capabilities"])
    telegram_policy = inspect_telegram_access_source(source_files["telegram_access_policy"])
    spawner_execution_policy = inspect_spawner_access_sources(desktop / "spawner-ui")
    browser_authority = inspect_browser_authority(desktop / "spark-browser-extension")
    public_output_authority = inspect_public_output_authority(desktop)

    access_profile_count = len(as_list(telegram_policy.get("profiles")))

    return {
        "schema_version": AUTHORITY_VIEW_SCHEMA,
        "generated_at": utc_now(),
        "authority": "observability_non_authoritative",
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
        "redaction": (
            "policy constants, safe command labels, source existence, and aggregate gate counts only; "
            "env files, profile preference files, token values, chat ids, raw mission text, and browser content are not read"
        ),
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
    return as_dict(TRACE_REPAIR_COMPONENT_OWNERS.get(component)) or {
        "owner_repo": "spark-intelligence-builder",
        "source_module": f"{component} event emission",
    }


def build_trace_current_health(trace_index: dict[str, Any]) -> dict[str, Any]:
    trace_health = as_dict(trace_index.get("builder_trace_health"))
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
    queue: list[dict[str, Any]] = []
    trace_health = as_dict(trace_index.get("builder_trace_health"))
    current_health = as_dict(trace_index.get("trace_current_health")) or build_trace_current_health(trace_index)
    historical_scope = str(current_health.get("repair_scope") or "") == "historical_backlog"
    telegram_gate = as_dict(trace_index.get("telegram_final_answer_gate_samples"))
    telegram_join = as_dict(telegram_gate.get("trace_join"))
    spawner = as_dict(trace_index.get("spawner_prd_auto_trace_samples"))
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
        if historical_scope:
            rank_reason = "historical Builder backlog missing trace_ref; recent trace window is clean"
            safe_fix = (
                "Verify whether this historical bucket still reproduces; new traffic may already carry trace refs."
            )
        queue.append(
            {
                "id": trace_repair_id("builder", component, event_type, "missing-trace-ref"),
                "priority": "medium" if historical_scope else "high",
                "rank_reason": rank_reason,
                "owner_repo": owner.get("owner_repo"),
                "source_module": owner.get("source_module"),
                "event_producer_family": component,
                "event_type": event_type,
                "missing_field": "trace_ref",
                "observed_event_count": int(row.get("event_count") or 0),
                "temporal_scope": "historical_backlog" if historical_scope else "current_or_unknown",
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


def build_trace_index(spark_home: Path, builder_home: Path) -> dict[str, Any]:
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
        "next_required_bridges": [
            "Map Spawner mission ids to Builder mission_changed_state events.",
            "Map Telegram final-answer gate checks to final_answer_checked black-box events.",
            "Emit Telegram request_id or trace_ref join keys from final-answer gate checks.",
        ],
    }
    trace_index["trace_current_health"] = build_trace_current_health(trace_index)
    trace_index["trace_repair_queue"] = build_trace_repair_queue(trace_index)
    return trace_index


def build_memory_movement_index(builder_home: Path) -> dict[str, Any]:
    memory_index = {
        "schema_version": MEMORY_MOVEMENT_INDEX_SCHEMA,
        "generated_at": utc_now(),
        "authority": "observability_non_authoritative",
        "redaction": (
            "metadata-only memory movement index; no raw memory text, row bodies, profile facts, "
            "conversation turns, evidence payloads, or Telegram update payloads emitted"
        ),
        "builder_memory_tables": inspect_builder_memory_tables(builder_home),
        "safe_status_export": read_memory_movement_status_export(builder_home),
        "memory_kb_artifacts": summarize_memory_kb_artifacts(builder_home),
        "memory_run_artifacts": summarize_memory_run_artifacts(builder_home),
        "next_required_bridges": [
            "Have Builder write artifacts/memory-movement-index/memory-movement-status.json from inspect_memory_movement_status().",
            "Have domain-chip-memory expose movement counts by lane, authority, source family, and record type without record text.",
            "Join memory movement events to trace ids once Builder event envelopes carry stable trace refs.",
            "Promote this index into Builder AOC and cockpit as evidence only, never as instructions or profile truth.",
        ],
    }
    memory_index["memory_review_queue"] = build_memory_review_queue(memory_index)
    return memory_index


def build_gaps(system_map: dict[str, Any]) -> list[dict[str, str]]:
    registry_modules = set(as_dict(system_map.get("registry", {}).get("modules")).keys())
    installed_modules = set(as_dict(system_map.get("installed_modules")).keys())
    repos = as_list(system_map.get("discovered_repos"))
    raw_gaps: list[dict[str, str]] = []

    def add_gap(severity: str, area: str, item: str, message: str) -> None:
        raw_gaps.append({"severity": severity, "area": area, "item": item, "message": message})

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

    for module in as_list(system_map.get("modules")):
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
    if name in OWNER_SURFACES:
        return OWNER_SURFACES[name]
    if name.startswith("domain-chip-"):
        return "domain chip candidate"
    if name.startswith("specialization-path-"):
        return "specialization path candidate"
    if "telegram" in name:
        return "Telegram-adjacent surface"
    if "swarm" in name:
        return "Swarm-adjacent surface"
    if "spark" in name:
        return "Spark-adjacent repo"
    return "unclassified"


def repo_manifest_presence(repo: dict[str, Any]) -> dict[str, bool]:
    contract_files = set(as_list(repo.get("contract_files")))
    return {
        "spark_toml": bool(as_dict(repo.get("spark_toml"))),
        "spark_chip": bool(as_dict(repo.get("spark_chip"))),
        "skill_manifest": bool(as_dict(repo.get("skill_manifest"))),
        "agents_md": "AGENTS.md" in contract_files,
        "contract_file_count": bool(contract_files),
    }


def repo_release_status(name: str, git: dict[str, Any], manifest: dict[str, bool], registry_present: bool) -> tuple[str, str | None, str]:
    dirty = int(git.get("dirty_tracked_count") or 0)
    untracked = int(git.get("untracked_count") or 0)
    behind = int(git.get("behind") or 0)
    if not git.get("available"):
        return "not_release_candidate", "not a git repo", "inspect or ignore before product work"
    if dirty or untracked:
        return "blocked", "dirty worktree", "curate local changes before merge or release"
    if behind:
        return "blocked", "behind upstream", "pull or merge upstream before release"
    if name in CORE_REPOS and not any(manifest.values()):
        return "blocked", "core repo missing Spark manifest", "add or confirm owner manifest before release"
    if registry_present:
        return "eligible", None, "safe to consider for the next verified workstream"
    return "inspect", "not in installer registry", "decide whether this repo should remain local, become a capability, or be ignored"


def repo_risk_class(name: str, release_eligibility: str) -> str:
    if name in {"spark-cli", "spark-intelligence-builder", "spark-telegram-bot", "spawner-ui"}:
        return "critical"
    if release_eligibility == "blocked":
        return "high"
    if name in CORE_REPOS:
        return "medium"
    return "low"


def build_repo_board(system_map: dict[str, Any]) -> dict[str, Any]:
    registry_modules = set(as_dict(system_map.get("registry", {}).get("modules")).keys())
    installed_modules = set(as_dict(system_map.get("installed_modules")).keys())
    rows: list[dict[str, Any]] = []

    for repo in as_list(system_map.get("discovered_repos")):
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
        "repos": rows,
    }


def build_voice_surface_view(system_map: dict[str, Any]) -> dict[str, Any]:
    repos = [as_dict(repo) for repo in as_list(system_map.get("discovered_repos"))]
    repo_names = {str(repo.get("name")) for repo in repos}
    repo_paths = {
        str(repo.get("name")): Path(str(repo.get("path"))).expanduser()
        for repo in repos
        if isinstance(repo.get("path"), str) and str(repo.get("path")).strip()
    }
    installed_modules = set(as_dict(system_map.get("installed_modules")).keys())
    available = "spark-voice-comms" in repo_names
    installed = "spark-voice-comms" in installed_modules

    def source_file_contains(repo_name: str, relative: str, *needles: str) -> bool:
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
        return all(needle in text for needle in needles)

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

    blockers = []
    if not available:
        blockers.append("spark-voice-comms repo not discovered")
    if available and not installed:
        blockers.append("spark-voice-comms is not installed in local Spark state")
    if available and source_mode == "disabled":
        blockers.append("voice ingress/egress source hooks are not detected")
    blockers.append("voice provider/profile runtime status is not exported to Spark OS state")
    blockers.append("voice final-answer join evidence is not compiled")
    if builder_has_transcript_preview:
        blockers.append("Builder retains raw voice transcript preview in private trace fields")

    return {
        "schema_version": VOICE_SURFACE_SCHEMA,
        "generated_at": utc_now(),
        "owner_system": "spark-voice-comms",
        "mode": "disabled" if blockers else source_mode,
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
        "provider": {"configured": False, "kind": "unknown"},
        "profile": {"configured": False, "voice_style_ref": None},
        "authority": {"can_answer": not blockers, "can_trigger_actions": False, "requires_confirmation_for_actions": True},
        "memory_policy": {
            "transcripts_are_durable_by_default": False,
            "raw_audio_exported_to_os_artifacts": False,
            "transcript_bodies_exported_to_os_artifacts": False,
        },
        "trace": {
            "voice_events_supported": False,
            "final_answer_check_supported": False,
            "source_hooks_present": source_mode != "disabled",
            "telegram_delivery_bridge_present": telegram_has_voice_bridge,
            "trace_evidence": "source_present_not_proven" if source_mode != "disabled" else "missing_source_hooks",
        },
        "privacy_findings": {"builder_transcript_preview_present": builder_has_transcript_preview},
        "blockers": blockers,
        "redaction": "metadata only; raw audio, transcript bodies, provider secrets, and voice profile secrets omitted",
    }


def build_operating_cockpit(compiled: dict[str, Any]) -> dict[str, Any]:
    system_map = as_dict(compiled.get("system_map"))
    repo_board = as_dict(compiled.get("repo_board"))
    trace_index = as_dict(compiled.get("trace_index"))
    capability_catalog = as_dict(compiled.get("capability_catalog"))
    voice_surface = as_dict(compiled.get("voice_surface_view"))
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
            },
            "trace_index": {
                "schema_version": trace_index.get("schema_version"),
                "builder_event_count": as_dict(trace_index.get("builder_events")).get("row_count"),
                "trace_repair_candidate_count": len(as_list(trace_index.get("trace_repair_queue"))),
                "authority_verdict_count": as_dict(trace_index.get("authority_verdicts")).get("verdict_count"),
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
        "authority_verdicts": as_list(as_dict(trace_index.get("authority_verdicts")).get("items"))[:5],
        "memory_review_queue": as_list(
            as_dict(as_dict(compiled.get("memory_movement_index")).get("memory_review_queue")).get("items")
        )[:5],
        "top_blockers": as_list(system_map.get("gaps"))[:10],
    }


def compile_system_map(desktop: Path, spark_home: Path, registry_path: Path) -> dict[str, Any]:
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
        "authority_view": build_authority_view(desktop, setup_summary),
        "capability_catalog": build_capability_catalog(repos),
        "trace_index": build_trace_index(spark_home, builder_home),
        "memory_movement_index": build_memory_movement_index(builder_home),
    }
    compiled["repo_board"] = build_repo_board(system_map)
    compiled["voice_surface_view"] = build_voice_surface_view(system_map)
    compiled["operating_cockpit"] = build_operating_cockpit(compiled)
    return compiled


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_gaps_markdown(path: Path, gaps: list[dict[str, str]], system_map: dict[str, Any]) -> None:
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
        f"- gaps: {len(gaps)}",
        "",
        "## Gaps",
        "",
    ]
    if not gaps:
        lines.append("- No gaps detected by this compiler pass.")
    else:
        for gap in gaps:
            count = int(gap.get("count", "1"))
            suffix = f" Observed {count} times." if count > 1 else ""
            lines.append(f"- [{gap['severity']}] {gap['area']} / {gap['item']}: {gap['message']}{suffix}")
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
    system_map = as_dict(compiled["system_map"])
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
    write_json(paths["authority_view"], compiled["authority_view"])
    write_json(paths["capability_catalog"], compiled["capability_catalog"])
    write_json(paths["trace_index"], compiled["trace_index"])
    write_json(paths["memory_movement_index"], compiled["memory_movement_index"])
    write_json(paths["repo_board"], compiled["repo_board"])
    write_json(paths["voice_surface_view"], compiled["voice_surface_view"])
    write_json(paths["operating_cockpit"], compiled["operating_cockpit"])
    write_gaps_markdown(paths["gaps"], as_list(system_map.get("gaps")), system_map)
    return {key: str(path) for key, path in paths.items()}


def compile_summary(compiled: dict[str, Any], written: dict[str, str] | None = None) -> dict[str, Any]:
    system_map = as_dict(compiled["system_map"])
    capability_catalog = as_dict(compiled["capability_catalog"])
    trace_index = as_dict(compiled["trace_index"])
    memory_index = as_dict(compiled["memory_movement_index"])
    repo_board = as_dict(compiled.get("repo_board"))
    voice_surface = as_dict(compiled.get("voice_surface_view"))
    builder_events = as_dict(trace_index.get("builder_events"))
    builder_event_samples = as_dict(trace_index.get("builder_event_samples"))
    builder_trace_groups = as_dict(trace_index.get("builder_trace_groups"))
    builder_trace_health = as_dict(trace_index.get("builder_trace_health"))
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
            for key, value in as_dict(as_dict(compiled["authority_view"]).get("observed_sources")).items()
        },
        "builder_event_rows": builder_events.get("row_count"),
        "builder_event_samples": builder_event_samples.get("sample_count"),
        "builder_trace_groups": builder_trace_groups.get("group_count"),
        "builder_trace_health_flags": as_list(builder_trace_health.get("health_flags")),
        "memory_movement_status": memory_status.get("status"),
        "memory_movement_rows": memory_status.get("row_count"),
        "builder_memory_table_count": builder_memory_tables.get("table_count"),
        "repo_board": as_dict(repo_board.get("summary")),
        "voice_surface_mode": voice_surface.get("mode"),
        "voice_surface_blockers": len(as_list(voice_surface.get("blockers"))),
        "privacy": system_map.get("privacy"),
        "outputs": written or {},
    }
