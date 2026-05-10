from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomllib

SYSTEM_MAP_SCHEMA = "spark.system_map.compiled.v0"
AUTHORITY_VIEW_SCHEMA = "spark.authority_view.compiled.v0"
CAPABILITY_CATALOG_SCHEMA = "spark.capability_catalog.compiled.v0"
TRACE_INDEX_SCHEMA = "spark.trace_index.compiled.v0"

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

    line_count = parsed_count = parse_errors = 0
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
                    key_counts[str(key)] += 1
                    if key in value_counts and isinstance(value, (str, int, float, bool)) and value is not None:
                        value_counts[key][str(value)[:80]] += 1
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    out["line_count"] = line_count
    out["parsed_count"] = parsed_count
    out["parse_errors"] = parse_errors
    out["top_keys"] = dict(key_counts.most_common(30))
    out["safe_value_counts"] = {key: dict(counter.most_common(30)) for key, counter in value_counts.items() if counter}
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

    for repo in repos:
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

    return {
        "schema_version": CAPABILITY_CATALOG_SCHEMA,
        "generated_at": utc_now(),
        "redaction": "capability metadata only; command bodies, logs, and runtime outputs omitted",
        "chip_manifests": chip_manifests,
        "module_capabilities": module_capabilities,
        "skill_graphs": skill_graphs,
        "contract_sources": contract_sources,
    }


def build_authority_view(desktop: Path, setup_summary: dict[str, Any]) -> dict[str, Any]:
    source_files = {
        "cli_access_policy": desktop / "spark-cli" / "src" / "spark_cli" / "sandbox" / "access.py",
        "cli_capabilities": desktop / "spark-cli" / "src" / "spark_cli" / "sandbox" / "capabilities.py",
        "telegram_access_policy": desktop / "spark-telegram-bot" / "src" / "accessPolicy.ts",
        "builder_aoc": desktop / "spark-intelligence-builder" / "src" / "spark_intelligence" / "self_awareness" / "operating_context.py",
        "browser_policy": desktop / "spark-browser-extension" / "src" / "protocol" / "policy.js",
    }
    observed_sources = {name: {"path": str(path), "exists": path.exists()} for name, path in source_files.items()}

    default_access_level = None
    access_file = source_files["cli_access_policy"]
    if access_file.exists():
        try:
            match = re.search(r"DEFAULT_ACCESS_LEVEL\s*=\s*(\d+)", access_file.read_text(encoding="utf-8"))
            default_access_level = int(match.group(1)) if match else None
        except Exception:
            default_access_level = None

    return {
        "schema_version": AUTHORITY_VIEW_SCHEMA,
        "generated_at": utc_now(),
        "observed_sources": observed_sources,
        "default_access_level_hint": default_access_level,
        "telegram_profile_count": setup_summary.get("telegram_profile_count"),
        "primary_telegram_profile": setup_summary.get("primary_telegram_profile"),
        "redaction": "policy file existence and non-secret constants only; env files and token values not read",
        "next_required_bridges": [
            "Map CLI access level, sandbox lane, and capability toxic-pair checks into AOC authority view.",
            "Map Telegram access policy into AuthorityViewV1 without copying token/profile secrets.",
            "Map browser hook risk class and approval mode into AuthorityViewV1.",
            "Map Swarm/Labs publication gates into public-output authority.",
        ],
    }


def build_trace_index(spark_home: Path, builder_home: Path) -> dict[str, Any]:
    spawner_state = spark_home / "state" / "spawner-ui"
    telegram_state = spark_home / "state" / "spark-telegram-bot"
    return {
        "schema_version": TRACE_INDEX_SCHEMA,
        "generated_at": utc_now(),
        "redaction": "aggregate metadata only; no raw event summaries, mission responses, logs, or message text",
        "builder_events": inspect_builder_event_trace(builder_home),
        "telegram_final_answer_gate": count_safe_jsonl(telegram_state / "final-answer-gate-audit.jsonl"),
        "telegram_outbound_audit": count_safe_jsonl(telegram_state / "node-outbound-audit.jsonl"),
        "spawner_mission_control_shape": inspect_json_shape(spawner_state / "mission-control.json"),
        "spawner_provider_results_shape": inspect_json_shape(spawner_state / "mission-provider-results.json"),
        "spawner_prd_auto_trace": count_safe_jsonl(spawner_state / "prd-auto-trace.jsonl"),
        "next_required_bridges": [
            "Map Builder event ids, request ids, trace refs, and parent ids into one trace river.",
            "Map Spawner mission ids to Builder mission_changed_state events.",
            "Map Telegram final-answer gate checks to final_answer_checked black-box events.",
            "Add redacted per-trace drilldown only after owner boundaries are explicit.",
        ],
    }


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

    return {
        "system_map": system_map,
        "authority_view": build_authority_view(desktop, setup_summary),
        "capability_catalog": build_capability_catalog(repos),
        "trace_index": build_trace_index(spark_home, builder_home),
    }


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
            "3. Add memory movement index compilation from Builder and domain-chip-memory ledgers.",
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
        "gaps": out_dir / "gaps.md",
    }
    write_json(paths["system_map"], system_map)
    write_json(paths["authority_view"], compiled["authority_view"])
    write_json(paths["capability_catalog"], compiled["capability_catalog"])
    write_json(paths["trace_index"], compiled["trace_index"])
    write_gaps_markdown(paths["gaps"], as_list(system_map.get("gaps")), system_map)
    return {key: str(path) for key, path in paths.items()}


def compile_summary(compiled: dict[str, Any], written: dict[str, str] | None = None) -> dict[str, Any]:
    system_map = as_dict(compiled["system_map"])
    capability_catalog = as_dict(compiled["capability_catalog"])
    trace_index = as_dict(compiled["trace_index"])
    builder_events = as_dict(trace_index.get("builder_events"))
    return {
        "schema_version": "spark.os_compile.summary.v0",
        "generated_at": system_map.get("generated_at"),
        "modules": len(as_list(system_map.get("modules"))),
        "repos": len(as_list(system_map.get("discovered_repos"))),
        "gaps": len(as_list(system_map.get("gaps"))),
        "chip_manifests": len(as_list(capability_catalog.get("chip_manifests"))),
        "skill_graphs": len(as_list(capability_catalog.get("skill_graphs"))),
        "authority_sources": {
            key: as_dict(value).get("exists")
            for key, value in as_dict(as_dict(compiled["authority_view"]).get("observed_sources")).items()
        },
        "builder_event_rows": builder_events.get("row_count"),
        "privacy": system_map.get("privacy"),
        "outputs": written or {},
    }
