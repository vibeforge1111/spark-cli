from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from ..env_files import normalize_env_file_value
from .audit import sandbox_audit_ref, write_audit_event
from .docker import collect_docker_doctor_payload
from .modal import modal_auth_markers, modal_sdk_available
from .ssh import load_ssh_targets


LEVEL5_ENV = {
    "SPARK_ALLOW_HIGH_AGENCY_WORKERS": "1",
    "SPARK_ALLOW_EXTERNAL_PROJECT_PATHS": "1",
    "SPARK_CODEX_SANDBOX": "danger-full-access",
}

LEVEL5_ENABLE_TOOL_NAME = "spark-cli.access.level5.enable"
LEVEL5_DISABLE_TOOL_NAME = "spark-cli.access.level5.disable"
LEVEL5_OWNER_SYSTEM = "spark-cli"
LEVEL5_MUTATION_CLASS = "writes_files"
LEVEL5_ACTION_TYPE = "edit_file"
LEVEL5_ENABLE_CAPABILITY_ID = f"capability:{LEVEL5_OWNER_SYSTEM}:{LEVEL5_ENABLE_TOOL_NAME}"
LEVEL5_DISABLE_CAPABILITY_ID = f"capability:{LEVEL5_OWNER_SYSTEM}:{LEVEL5_DISABLE_TOOL_NAME}"


DEFAULT_ACCESS_LEVEL = 4
DEFAULT_SANDBOX_LANE = "spark_workspace"
DEFAULT_CODEX_SANDBOX = "workspace-write"
LOWER_ACCESS_PROFILES: dict[int, dict[str, str]] = {
    1: {
        "id": "chat_memory",
        "label": "Chat, Memory, and Diagnostics",
        "activation_state": "chat",
        "user_message": "Level 1 is ready for chat, memory, recall, and diagnostics. It does not grant mission or local file access.",
        "next": "Use `/access 2`, `/access 3`, or `/access 4` in Telegram when you want missions, research, or local workspace work.",
    },
    2: {
        "id": "requested_missions",
        "label": "Requested Missions",
        "activation_state": "missions",
        "user_message": "Level 2 is ready for explicitly requested missions and builds. It still does not grant public research or local file access.",
        "next": "Use `/access 3` for public research or `/access 4` for safe local workspace work.",
    },
    3: {
        "id": "public_research",
        "label": "Public Research",
        "activation_state": "research",
        "user_message": "Level 3 is ready for public web and GitHub research plus requested missions. It still does not grant local file access.",
        "next": "Use `/access 4` when Spark should prepare a safe local workspace.",
    },
}


def access_os_family(platform: str | None = None) -> str:
    value = platform or sys.platform
    if value == "darwin":
        return "macos"
    if value.startswith("win"):
        return "windows"
    if value.startswith("linux"):
        return "linux"
    return "unknown"


def spark_workspace_root(*, home: Path | None = None, env: dict[str, str] | None = None) -> Path:
    env_values = env or os.environ
    configured = env_values.get("SPARK_WORKSPACE_ROOT") or env_values.get("SPAWNER_WORKSPACE_ROOT")
    if configured:
        return Path(configured).expanduser()
    spark_home = home or Path(env_values.get("SPARK_HOME", Path.home() / ".spark")).expanduser()
    return spark_home / "workspaces"


def ensure_level4_workspace(*, home: Path | None = None, env: dict[str, str] | None = None) -> Path:
    root = spark_workspace_root(home=home, env=env)
    default_workspace = root / "default"
    default_workspace.mkdir(parents=True, exist_ok=True)
    return default_workspace


def module_env_dir(*, home: Path | None = None, env: dict[str, str] | None = None) -> Path:
    env_values = env or os.environ
    spark_home = home or Path(env_values.get("SPARK_HOME", Path.home() / ".spark")).expanduser()
    return spark_home / "config" / "modules"


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip().lstrip("\ufeff")] = normalize_env_file_value(value)
    return values


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")


def _harness_core_source_candidates() -> list[Path]:
    candidates: list[Path] = []
    candidates.append(Path(__file__).resolve().parents[4] / "spark-harness-core" / "src")
    spark_home = os.environ.get("SPARK_HOME")
    if spark_home:
        candidates.append(Path(spark_home).expanduser() / "modules" / "spark-harness-core" / "source" / "src")
    candidates.append(Path.home() / ".spark" / "modules" / "spark-harness-core" / "source" / "src")
    return candidates


def _load_verify_governor_tool_authority() -> Callable[..., dict[str, Any]]:
    try:
        from spark_harness_core.legacy_turn_intent import verify_governor_tool_authority

        return verify_governor_tool_authority
    except ModuleNotFoundError:
        pass

    for candidate in _harness_core_source_candidates():
        if not (candidate / "spark_harness_core" / "__init__.py").exists():
            continue
        candidate_text = str(candidate)
        if candidate_text not in sys.path:
            sys.path.insert(0, candidate_text)
        try:
            from spark_harness_core.legacy_turn_intent import verify_governor_tool_authority

            return verify_governor_tool_authority
        except ModuleNotFoundError:
            continue
    raise RuntimeError("spark_harness_core_unavailable")


def require_level5_access_authority(
    governor_decision: dict[str, Any] | None,
    *,
    tool_name: str,
) -> dict[str, Any]:
    verifier = _load_verify_governor_tool_authority()
    verification = verifier(
        governor_decision,
        tool_name=tool_name,
        owner_system=LEVEL5_OWNER_SYSTEM,
        mutation_class=LEVEL5_MUTATION_CLASS,
        require_pre_execution_ledger=True,
    )
    if not verification.get("allowed"):
        reasons = [str(item) for item in verification.get("reason_codes", []) if str(item).strip()]
        reason_text = ", ".join(reasons) if reasons else "governor_authority_denied"
        raise RuntimeError(f"Level 5 access mutation requires GovernorDecisionV1 authority: {reason_text}")
    return verification


def level5_env_paths(*, home: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Path]:
    root = module_env_dir(home=home, env=env)
    return {
        "spawner": root / "spawner-ui.env",
        "telegram": root / "spark-telegram-bot.env",
    }


def persist_level5_guardrails(
    *,
    home: Path | None = None,
    env: dict[str, str] | None = None,
    governor_decision: dict[str, Any] | None = None,
) -> dict[str, str]:
    require_level5_access_authority(governor_decision, tool_name=LEVEL5_ENABLE_TOOL_NAME)
    paths = level5_env_paths(home=home, env=env)
    spawner_env = read_env_file(paths["spawner"])
    telegram_env = read_env_file(paths["telegram"])
    spawner_env.update(LEVEL5_ENV)
    telegram_env.update(LEVEL5_ENV)
    write_env_file(paths["spawner"], spawner_env)
    write_env_file(paths["telegram"], telegram_env)
    write_audit_event(
        "access",
        "level5",
        {
            "action_id": "level5_guardrails_configure",
            "changed_keys": sorted(LEVEL5_ENV),
            "env_files": {key: str(path) for key, path in paths.items()},
            "rollback_command": "spark access disable-level5",
        },
        home=home,
    )
    return {key: str(path) for key, path in paths.items()}


def _remove_env_keys(path: Path, keys: set[str]) -> bool:
    if not path.exists():
        return False
    values = read_env_file(path)
    changed = False
    for key in keys:
        if key in values:
            values.pop(key, None)
            changed = True
    if changed:
        write_env_file(path, values)
    return changed


def disable_level5_guardrails(
    *,
    home: Path | None = None,
    env: dict[str, str] | None = None,
    governor_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    require_level5_access_authority(governor_decision, tool_name=LEVEL5_DISABLE_TOOL_NAME)
    paths = level5_env_paths(home=home, env=env)
    changed = {
        "spawner": _remove_env_keys(paths["spawner"], set(LEVEL5_ENV)),
        "telegram": _remove_env_keys(paths["telegram"], set(LEVEL5_ENV)),
    }
    write_audit_event(
        "access",
        "level5",
        {
            "action_id": "level5_guardrails_disable",
            "changed": changed,
            "env_files": {key: str(path) for key, path in paths.items()},
            "rollback_command": "spark access setup --level 5 --enable-high-agency",
        },
        home=home,
    )
    return {
        "changed": changed,
        "env_files": {key: str(path) for key, path in paths.items()},
        "audit": sandbox_audit_ref("access", "level5"),
    }


def generated_level5_env(*, home: Path | None = None, env: dict[str, str] | None = None) -> dict[str, str]:
    paths = level5_env_paths(home=home, env=env)
    merged: dict[str, str] = {}
    for path in paths.values():
        merged.update(read_env_file(path))
    return merged


def home_or_default(*, home: Path | None = None, env: dict[str, str] | None = None) -> Path:
    env_values = env or os.environ
    return home or Path(env_values.get("SPARK_HOME", Path.home() / ".spark")).expanduser()


def _parse_utc_timestamp(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _latest_level5_configure_timestamp(*, home: Path | None = None) -> float | None:
    path = home_or_default(home=home) / "logs" / "remote" / "access" / "level5.jsonl"
    if not path.exists():
        return None
    configured_at: float | None = None
    disabled_at: float | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        timestamp = _parse_utc_timestamp(event.get("timestamp"))
        if timestamp is None:
            continue
        action_id = event.get("action_id")
        if action_id == "level5_guardrails_configure":
            configured_at = timestamp
        elif action_id == "level5_guardrails_disable":
            disabled_at = timestamp
    if configured_at is None:
        return None
    if disabled_at is not None and disabled_at >= configured_at:
        return None
    return configured_at


def level5_guardrails_configured_by_audit(*, home: Path | None = None) -> bool:
    """Return true when Level 5 was explicitly enabled and not later disabled."""
    return _latest_level5_configure_timestamp(home=home) is not None


def level5_service_guardrail_state(
    *,
    home: Path | None = None,
    env: dict[str, str] | None = None,
    configured: bool,
) -> dict[str, Any]:
    spark_home = home_or_default(home=home, env=env)
    configured_at = _latest_level5_configure_timestamp(home=spark_home) if configured else None
    state: dict[str, Any] = {
        "enabled": False,
        "activation_state": "blocked" if not configured else "restart_required",
        "configured_at": None,
        "modules": {},
    }
    if configured_at is None:
        return state
    state["configured_at"] = datetime.fromtimestamp(configured_at, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    pids_path = spark_home / "state" / "pids.json"
    try:
        pids = json.loads(pids_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pids = {}
    expected = {
        "spawner-ui": False,
        "spark-telegram-bot": False,
    }
    modules: dict[str, Any] = {}
    if isinstance(pids, dict):
        for key, record in pids.items():
            if not isinstance(record, dict):
                continue
            module = str(record.get("module") or key.split(":", 1)[0])
            if module not in expected:
                continue
            started_at = _parse_utc_timestamp(record.get("started_at"))
            active = bool(started_at is not None and started_at >= configured_at)
            previous = modules.get(module)
            if previous is None or active:
                modules[module] = {
                    "active": active,
                    "pid": record.get("pid"),
                    "started_at": record.get("started_at"),
                }
            if active:
                expected[module] = True
    state["modules"] = modules
    state["enabled"] = all(expected.values())
    if state["enabled"]:
        state["activation_state"] = "active"
    elif modules:
        state["activation_state"] = "partial"
    return state


def enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def probe_workspace_writable(path: Path) -> dict[str, Any]:
    marker = path / f".spark-access-preflight-{os.getpid()}-{int(time.time() * 1000)}.tmp"
    try:
        path.mkdir(parents=True, exist_ok=True)
        marker.write_text("spark access preflight\n", encoding="utf-8")
        marker.unlink(missing_ok=True)
        return {
            "exists": True,
            "writable": True,
            "detail": "Workspace write/delete preflight passed.",
        }
    except OSError as error:
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "exists": path.exists(),
            "writable": False,
            "detail": f"Workspace write/delete preflight failed: {error.__class__.__name__}.",
        }


def docker_available() -> bool:
    return bool(shutil.which("docker"))


def docker_doctor_readiness() -> dict[str, Any]:
    try:
        payload = collect_docker_doctor_payload(timeout=3)
    except Exception as error:  # pragma: no cover - defensive boundary around optional host tooling.
        return {
            "ok": False,
            "configured": docker_available(),
            "detail": f"Docker doctor failed: {error.__class__.__name__}.",
        }
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    cli_configured = any(
        isinstance(check, dict) and check.get("name") == "docker_cli" and bool(check.get("ok"))
        for check in checks
    )
    return {
        "ok": bool(payload.get("ok")),
        "configured": cli_configured,
        "detail": str(payload.get("next") or ""),
    }


def docker_os_hint(family: str) -> str:
    if family == "macos":
        return "Spark can guide Docker Desktop for macOS when a task needs stronger isolation."
    if family == "windows":
        return "Spark can guide Docker Desktop with WSL on Windows when a task needs stronger isolation."
    if family == "linux":
        return "Spark can guide Docker Engine or Docker Desktop on Linux with distro-aware checks."
    return "Spark can guide Docker setup when this OS supports it."


def workspace_os_hint(family: str) -> str:
    if family == "macos":
        return "macOS default: Spark uses a workspace sandbox first, then adds Docker only when useful."
    if family == "windows":
        return "Windows default: Spark uses a workspace sandbox first, then guides Docker/WSL only when useful."
    if family == "linux":
        return "Linux default: Spark uses a workspace sandbox first, then guides Docker only when useful."
    return "Default: Spark uses a workspace sandbox first, then guides heavier sandboxes only when useful."


def goal_needs(goal: str, lane: str) -> bool:
    text = goal.lower()
    if lane == "docker":
        return any(word in text for word in ("docker", "container", "containerized", "isolated", "reproducible"))
    if lane == "ssh":
        return any(word in text for word in ("ssh", "remote machine", "remote server", "remote box", "vps"))
    if lane == "modal":
        return any(word in text for word in ("modal", "gpu", "cloud sandbox", "remote compute", "large job"))
    return False


def safe_workspace_setup_state(*, home: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    workspace_root = spark_workspace_root(home=home, env=env)
    workspace_path = ensure_level4_workspace(home=home, env=env)
    preflight = probe_workspace_writable(workspace_path)
    return {
        "default_level": DEFAULT_ACCESS_LEVEL,
        "default_lane": DEFAULT_SANDBOX_LANE,
        "codex_sandbox": DEFAULT_CODEX_SANDBOX,
        "boundary_kind": "workspace_write",
        "workspace_root": str(workspace_root),
        "workspace_path": str(workspace_path),
        "workspace_preflight": preflight,
        "whole_computer_access": False,
        "user_message": "Spark is set up to work inside one safe working folder by default.",
        "security_note": "This is a practical file boundary, not a hardened container security boundary. Use Docker or Modal when a task needs stronger isolation.",
    }


def access_guide_payload(payload: dict[str, Any]) -> dict[str, Any]:
    level = int(payload.get("access_level") or DEFAULT_ACCESS_LEVEL)
    workspace_preflight = payload.get("workspace_preflight") if isinstance(payload.get("workspace_preflight"), dict) else {}
    workspace_ready = bool(workspace_preflight.get("writable"))
    family = str(payload.get("os_family") or "unknown")
    if level < 4:
        profile = LOWER_ACCESS_PROFILES.get(level, LOWER_ACCESS_PROFILES[1])
        return {
            "summary": profile["user_message"],
            "plain_default": "Levels 1-3 do not need sandbox setup because they do not grant local file access.",
            "security_note": "Spark should not touch local files until Level 4 workspace access or Level 5 operator mode is explicitly selected.",
            "os_note": "This access level works the same on macOS, Windows, Linux, and WSL.",
            "default": {
                "access_level": level,
                "lane": profile["id"],
                "codex_sandbox": "none",
                "whole_computer_access": False,
            },
            "stronger_sandbox_order": ["spark_workspace", "docker", "modal", "ssh"],
            "steps": [
                {
                    "id": profile["id"],
                    "title": profile["label"],
                    "status": "ready",
                    "automatic": True,
                    "user_message": profile["user_message"],
                    "spark_cli_action": f"spark access status --level {level}",
                },
                {
                    "id": "local_workspace",
                    "title": "Safe local workspace",
                    "status": "available_at_level_4",
                    "automatic": True,
                    "user_message": "When the user chooses Level 4, Spark can create the safe workspace automatically.",
                    "spark_cli_action": "spark access setup",
                },
            ],
        }
    level5 = payload.get("level5") if isinstance(payload.get("level5"), dict) else {}
    level5_state = str(level5.get("activation_state") or "")
    if not level5_state:
        if level5.get("enabled"):
            level5_state = "active"
        elif level5.get("restart_required"):
            level5_state = "restart_required"
        else:
            level5_state = "blocked"
    steps = [
        {
            "id": "safe_workspace",
            "title": "Safe workspace",
            "status": "ready" if workspace_ready else "needs_setup",
            "automatic": True,
            "user_message": (
                f"Spark can already work inside the safe workspace at {payload.get('workspace_path')}."
                if workspace_ready
                else "Spark will create one safe working folder before agents touch local files."
            ),
            "spark_cli_action": "spark access setup",
        },
        {
            "id": "mission_control",
            "title": "Mission Control builds",
            "status": "ready" if workspace_ready else "waiting_for_workspace",
            "automatic": True,
            "user_message": "Builds run with workspace-write access by default, not whole-computer access.",
            "spark_cli_action": "spark verify --onboarding",
        },
        {
            "id": "stronger_sandbox",
            "title": "Stronger sandbox, only when needed",
            "status": "optional",
            "automatic": False,
            "default_choice": "docker",
            "user_message": "If a task needs more isolation, Spark should try Docker first, then Modal for cloud/GPU jobs, then SSH for trusted user-owned machines.",
            "spark_cli_action": "spark sandbox docker doctor",
        },
    ]
    if level >= 5:
        if level5_state == "active":
            whole_computer_message = "Level 5 is active. Spark should still prefer the safe workspace unless a task really needs the whole computer."
            whole_computer_action = "spark access status --level 5"
        elif level5_state == "active_for_services":
            whole_computer_message = "Level 5 is ready in Spark. Use Telegram or Mission Control for whole-computer tasks."
            whole_computer_action = "spark access status --level 5"
        elif level5_state == "session_only":
            whole_computer_message = "Level 5 is active only in this process. Run setup to persist it before relying on it after restart."
            whole_computer_action = "spark access setup --level 5 --enable-high-agency"
        elif level5_state == "restart_required":
            whole_computer_message = "Level 5 is configured, but Spark must restart before Telegram and Spawner can see it."
            whole_computer_action = "spark restart"
        else:
            whole_computer_message = "Level 5 can operate on the whole computer. Spark will not enable it silently."
            whole_computer_action = "spark access setup --level 5 --enable-high-agency"
        steps.append(
            {
                "id": "whole_computer",
                "title": "Whole-computer mode",
                "status": level5_state if level5_state != "blocked" else "explicit_opt_in_required",
                "automatic": False,
                "user_message": whole_computer_message,
                "spark_cli_action": whole_computer_action,
            }
        )
    return {
        "summary": (
            "Safe workspace is ready."
            if workspace_ready
            else "Safe workspace is not ready yet. Spark can create it automatically."
        ),
        "plain_default": "Use the Spark Workspace Sandbox first. It is the safe default on macOS, Windows, Linux, and WSL.",
        "security_note": "Workspace mode keeps normal Spark work inside one working folder. It is not a hardened container; use Docker or Modal for stronger isolation.",
        "os_note": workspace_os_hint(family),
        "default": {
            "access_level": DEFAULT_ACCESS_LEVEL,
            "lane": DEFAULT_SANDBOX_LANE,
            "codex_sandbox": DEFAULT_CODEX_SANDBOX,
            "whole_computer_access": False,
        },
        "stronger_sandbox_order": ["docker", "modal", "ssh"],
        "steps": steps,
    }


def access_automation_payload(
    *,
    level: int,
    next_action: str,
    recommended_id: str,
    level5_activation_state: str,
    docker_ready: bool,
) -> dict[str, Any]:
    level5_configured = level >= 5 and level5_activation_state in {"active", "active_for_services", "restart_required", "session_only"}
    return {
        "no_terminal_required": True,
        "ui_contract": "Spark UI/Telegram/installer surfaces may run these fixed Spark CLI actions for nontechnical users after showing the policy-authored confirmation text.",
        "recommended_action": next_action,
        "recommended_lane": recommended_id,
        "actions": [
            {
                "id": "workspace_setup",
                "command": "spark access setup",
                "run_policy": "auto_safe",
                "confirmation": "none",
                "user_message": "Spark can create or repair the safe workspace automatically.",
                "rollback": "No rollback needed; this only creates Spark-owned workspace folders.",
            },
            {
                "id": "docker_doctor",
                "command": "spark sandbox docker doctor --json",
                "run_policy": "auto_read_only",
                "confirmation": "none",
                "user_message": "Spark can check Docker readiness without changing the computer.",
                "available": docker_ready,
            },
            {
                "id": "docker_smoke",
                "command": "spark sandbox docker smoke --json",
                "run_policy": "confirm_once",
                "confirmation": "Run Docker sandbox test",
                "user_message": "Spark can run a no-secret Docker smoke after confirmation. It may build/pull a local image, but it must not mount the Docker socket, home folder, or Spark secrets.",
                "rollback": "Docker smoke uses an ephemeral container; remove the local image only with explicit cleanup approval.",
            },
            {
                "id": "level5_enable",
                "command": "spark access setup --level 5 --enable-high-agency",
                "run_policy": "explicit_opt_in",
                "confirmation": "Enable whole-computer operator mode",
                "user_message": (
                    "Level 5 is already configured or active."
                    if level5_configured
                    else "Spark must ask before enabling Level 5. It writes local safety settings, records an audit event, and then refreshes Spark."
                ),
                "rollback": "spark access disable-level5",
            },
            {
                "id": "level5_disable",
                "command": "spark access disable-level5",
                "run_policy": "confirm_once",
                "confirmation": "Return to workspace sandbox",
                "user_message": "Spark can disable Level 5 guardrails and return to sandbox-first mode after restart.",
                "rollback": "spark access setup --level 5 --enable-high-agency",
            },
        ],
        "level5_runtime_policy": {
            "routine_actions_after_activation": "allowed_without_repeated_confirmation",
            "destructive_actions_after_activation": "still_approval_required",
            "secret_reveal_or_export": "still_approval_required",
            "public_publish_or_deploy": "still_approval_required",
            "why": "Level 5 removes the normal workspace boundary, but it must not remove deletion, secret, or publish safety layers.",
        },
        "deletion_safety": {
            "default": "do_not_delete",
            "safe_workspace_cleanup": "prefer_quarantine_or_trash_then_explicit_empty",
            "outside_workspace": "exact-target approval required",
            "broad_recursive_delete": "blocked unless a policy classifier and explicit confirmation approve it",
            "backup_first": "required for user data, secrets, and stateful Spark homes",
        },
    }


def access_lane_payload(
    *,
    level: int = 4,
    goal: str = "",
    setup: bool = False,
    enable_high_agency: bool = False,
    home: Path | None = None,
    env: dict[str, str] | None = None,
    governor_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    env_values = env or os.environ
    written_level5_env: dict[str, str] = {}
    if level < 4:
        family = access_os_family()
        profile = LOWER_ACCESS_PROFILES.get(level, LOWER_ACCESS_PROFILES[1])
        workspace_root = spark_workspace_root(home=home, env=env_values)
        workspace_path = workspace_root / "default"
        workspace_preflight = {
            "exists": workspace_path.exists(),
            "writable": False,
            "detail": f"Level {level} does not require local workspace setup.",
        }
        recommended = {
            "id": profile["id"],
            "label": profile["label"],
            "available": True,
            "setup_mode": "automatic",
            "spark_cli_action": f"spark access status --level {level}",
            "user_message": profile["user_message"],
            "os_hint": "Levels 1-3 have the same access meaning on macOS, Windows, Linux, and WSL.",
            "recommended": True,
        }
        next_action = profile["next"]
        return {
            "ok": True,
            "access_level": level,
            "effective_access_level": level,
            "os_family": family,
            "workspace_root": str(workspace_root),
            "workspace_path": str(workspace_path),
            "workspace_preflight": workspace_preflight,
            "level5": {
                "enabled": False,
                "configured": False,
                "activation_state": "blocked",
                "process_enabled": False,
                "external_paths": False,
                "codex_sandbox": "none",
                "configured_codex_sandbox": "",
                "restart_required": False,
                "env_files": {},
                "audit": {},
                "disable_command": "spark access disable-level5",
            },
            "state_machine": {
                "requested_access_level": level,
                "effective_access_level": level,
                "activation_state": profile["activation_state"],
                "requires_restart": False,
                "can_operate_whole_computer": False,
                "persistent": True,
            },
            "setup_ran": False,
            "recommended": recommended,
            "lanes": [recommended],
            "next": next_action,
            "automation": access_automation_payload(
                level=level,
                next_action=next_action,
                recommended_id=profile["id"],
                level5_activation_state="blocked",
                docker_ready=False,
            ),
            "guide": access_guide_payload({
                "access_level": level,
                "os_family": family,
                "workspace_path": str(workspace_path),
                "workspace_preflight": workspace_preflight,
                "level5": {"enabled": False, "restart_required": False, "activation_state": "blocked"},
            }),
        }
    if setup and level >= 5 and enable_high_agency:
        written_level5_env = persist_level5_guardrails(home=home, env=env_values, governor_decision=governor_decision)
    family = access_os_family()
    workspace_root = spark_workspace_root(home=home, env=env_values)
    workspace_path = ensure_level4_workspace(home=home, env=env_values) if setup else workspace_root / "default"
    workspace_preflight = probe_workspace_writable(workspace_path) if setup or workspace_path.exists() else {
        "exists": False,
        "writable": False,
        "detail": "Workspace is not created yet. Run `spark access setup`.",
    }
    ssh_targets = load_ssh_targets(home=home)
    modal_auth = modal_auth_markers(home=home)
    modal_configured = modal_sdk_available() and bool(modal_auth.get("env_auth") or modal_auth.get("config_present"))
    modal_ready = modal_configured
    docker_readiness = docker_doctor_readiness()
    docker_configured = bool(docker_readiness.get("configured"))
    docker_ready = bool(docker_readiness.get("ok"))
    trusted_ssh_targets = [
        target for target in ssh_targets
        if target.host_key_status == "trusted" and bool(target.host_key_fingerprint) and bool(target.identity_file)
    ]
    ssh_ready = bool(trusted_ssh_targets)
    generated_env = generated_level5_env(home=home, env=env_values)
    level5_process_enabled = enabled(env_values.get("SPARK_ALLOW_HIGH_AGENCY_WORKERS"))
    level5_external_paths = enabled(env_values.get("SPARK_ALLOW_EXTERNAL_PROJECT_PATHS"))
    level5_full_sandbox = env_values.get("SPARK_CODEX_SANDBOX") == "danger-full-access"
    level5_configured = (
        enabled(generated_env.get("SPARK_ALLOW_HIGH_AGENCY_WORKERS"))
        and enabled(generated_env.get("SPARK_ALLOW_EXTERNAL_PROJECT_PATHS"))
        and generated_env.get("SPARK_CODEX_SANDBOX") == "danger-full-access"
    )
    level5_process_active = level5_process_enabled and level5_external_paths and level5_full_sandbox
    level5_service_state = level5_service_guardrail_state(home=home, env=env_values, configured=level5_configured)
    level5_service_active = bool(level5_service_state.get("enabled"))
    level5_enabled = level5_process_active or level5_service_active
    level5_restart_required = level5_configured and not level5_enabled
    if level5_process_active and level5_configured:
        level5_activation_state = "active"
    elif level5_service_active:
        level5_activation_state = "active_for_services"
    elif level5_process_active:
        level5_activation_state = "session_only"
    elif level5_restart_required:
        level5_activation_state = "restart_required"
    elif any((
        level5_process_enabled,
        level5_external_paths,
        level5_full_sandbox,
        enabled(generated_env.get("SPARK_ALLOW_HIGH_AGENCY_WORKERS")),
        enabled(generated_env.get("SPARK_ALLOW_EXTERNAL_PROJECT_PATHS")),
        generated_env.get("SPARK_CODEX_SANDBOX") == "danger-full-access",
    )):
        level5_activation_state = "partial"
    else:
        level5_activation_state = "blocked"
    effective_access_level = 5 if level >= 5 and level5_enabled else min(level, DEFAULT_ACCESS_LEVEL)

    lanes = [
        {
            "id": "spark_workspace",
            "label": "Spark Workspace Sandbox",
            "available": True,
            "setup_mode": "automatic",
            "spark_cli_action": "spark access setup",
            "user_message": f"Spark can work safely inside {workspace_path}.",
            "os_hint": workspace_os_hint(family),
        },
        {
            "id": "docker",
            "label": "Docker Sandbox",
            "available": docker_ready,
            "configured": docker_configured,
            "doctor_ok": docker_ready,
            "setup_mode": "automatic" if docker_ready else "guided",
            "spark_cli_action": "spark access setup --with docker" if docker_ready else "spark sandbox docker doctor",
            "user_message": (
                "Docker daemon is ready for stronger isolation."
                if docker_ready
                else "Docker is detected but not ready yet; run the doctor to finish it."
                if docker_configured
                else "Docker is optional; Spark can guide setup when a task needs it."
            ),
            "os_hint": docker_os_hint(family),
        },
        {
            "id": "ssh",
            "label": "SSH Remote Sandbox",
            "available": ssh_ready,
            "configured": bool(ssh_targets),
            "trusted_targets": len(trusted_ssh_targets),
            "setup_mode": "automatic" if ssh_ready else "guided",
            "spark_cli_action": "spark sandbox ssh list" if ssh_targets else "spark sandbox ssh add <name> --host <host> --user <user> --identity-file <path>",
            "user_message": (
                "An SSH target has a trusted host key; run doctor before remote writes."
                if ssh_ready
                else "SSH targets exist, but host-key trust or identity setup is not complete."
                if ssh_targets
                else "SSH is optional; connect a trusted remote machine only when needed."
            ),
        },
        {
            "id": "modal",
            "label": "Modal Cloud Sandbox",
            "available": modal_ready,
            "configured": modal_configured,
            "smoke_required": modal_ready,
            "setup_mode": "automatic" if modal_ready else "guided",
            "spark_cli_action": "spark sandbox modal doctor" if modal_ready else "spark sandbox modal doctor",
            "user_message": "Modal credentials are configured; run smoke before heavy cloud work." if modal_ready else "Modal is optional; connect it only for cloud compute jobs.",
        },
    ]

    recommended_id = "spark_workspace"
    if level >= 5 and level5_enabled:
        recommended_id = "level5_operator"
    elif goal_needs(goal, "modal") and modal_ready:
        recommended_id = "modal"
    elif goal_needs(goal, "ssh") and ssh_targets:
        recommended_id = "ssh"
    elif goal_needs(goal, "docker") and docker_ready:
        recommended_id = "docker"

    if level >= 5:
        operator_action = (
            "spark access status --level 5"
            if level5_activation_state in {"active", "active_for_services"}
            else "spark access setup --level 5 --enable-high-agency"
            if level5_activation_state == "session_only"
            else "spark restart"
            if level5_activation_state == "restart_required"
            else "spark access setup --level 5 --enable-high-agency"
        )
        lanes.insert(
            0,
            {
                "id": "level5_operator",
                "label": "Whole-Computer Operator Mode",
                "available": level5_enabled,
                "setup_mode": "automatic" if level5_enabled else "guided" if level5_restart_required else "blocked",
                "spark_cli_action": operator_action,
                "user_message": (
                    "Whole-computer mode is enabled and persisted, but Spark should still prefer a sandbox."
                    if level5_activation_state == "active"
                    else "Level 5 is ready in Spark. Use Telegram or Mission Control for whole-computer tasks."
                    if level5_activation_state == "active_for_services"
                    else "Whole-computer mode is active only for this process. Run setup to persist the guardrails."
                    if level5_activation_state == "session_only"
                    else "Whole-computer mode is configured; restart Spark so Telegram and Spawner load the guardrails."
                    if level5_activation_state == "restart_required"
                    else "Whole-computer mode is partially configured. Rerun setup to repair the guardrails."
                    if level5_activation_state == "partial"
                    else "Whole-computer mode is blocked until high-agency guardrails are explicitly enabled."
                ),
            },
        )

    for lane in lanes:
        lane["recommended"] = lane["id"] == recommended_id
    recommended = next((lane for lane in lanes if lane["recommended"]), lanes[0])
    if recommended.get("available") is False:
        recommended = next(lane for lane in lanes if lane["id"] == "spark_workspace")
        recommended["recommended"] = True
    if level >= 5 and level5_restart_required:
        next_action = "spark restart"
    elif level >= 5 and level5_activation_state == "session_only":
        next_action = "spark access setup --level 5 --enable-high-agency"
    elif level >= 5 and level5_activation_state in {"active", "active_for_services"}:
        next_action = "spark access status --level 5"
    elif level >= 5 and not level5_enabled and not level5_restart_required:
        next_action = "spark access setup --level 5 --enable-high-agency"
    else:
        next_action = recommended["spark_cli_action"]
    ok = True
    if setup:
        ok = bool(workspace_preflight.get("writable"))
        if level >= 5:
            ok = ok and bool(level5_enabled or level5_restart_required)

    return {
        "ok": ok,
        "access_level": level,
        "effective_access_level": effective_access_level,
        "os_family": family,
        "workspace_root": str(workspace_root),
        "workspace_path": str(workspace_path),
        "workspace_preflight": workspace_preflight,
        "level5": {
            "enabled": level5_enabled,
            "configured": level5_configured,
            "activation_state": level5_activation_state,
            "process_enabled": level5_process_enabled,
            "current_process_enabled": level5_process_active,
            "service_enabled": level5_service_active,
            "service_guardrails": level5_service_state,
            "external_paths": level5_external_paths,
            "codex_sandbox": env_values.get("SPARK_CODEX_SANDBOX") or "workspace-write",
            "configured_codex_sandbox": generated_env.get("SPARK_CODEX_SANDBOX") or "",
            "restart_required": level5_restart_required,
            "env_files": written_level5_env,
            "audit": sandbox_audit_ref("access", "level5") if written_level5_env else {},
            "disable_command": "spark access disable-level5",
        },
        "state_machine": {
            "requested_access_level": level,
            "effective_access_level": effective_access_level,
            "activation_state": level5_activation_state if level >= 5 else "workspace",
            "requires_restart": bool(level >= 5 and level5_restart_required),
            "can_operate_whole_computer": bool(level >= 5 and level5_enabled),
            "current_process_can_operate_whole_computer": bool(level >= 5 and level5_process_active),
            "service_can_operate_whole_computer": bool(level >= 5 and level5_service_active),
            "persistent": bool(level >= 5 and level5_enabled and level5_configured),
        },
        "setup_ran": setup,
        "recommended": recommended,
        "lanes": lanes,
        "next": next_action,
        "automation": access_automation_payload(
            level=level,
            next_action=next_action,
            recommended_id=str(recommended.get("id") or ""),
            level5_activation_state=level5_activation_state,
            docker_ready=docker_ready,
        ),
        "guide": access_guide_payload({
            "access_level": level,
            "os_family": family,
            "workspace_path": str(workspace_path),
            "workspace_preflight": workspace_preflight,
            "level5": {
                "enabled": level5_enabled,
                "restart_required": level5_restart_required,
                "activation_state": level5_activation_state,
            },
        }),
    }


def level5_disable_payload(
    *,
    home: Path | None = None,
    env: dict[str, str] | None = None,
    governor_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = disable_level5_guardrails(home=home, env=env, governor_decision=governor_decision)
    return {
        "ok": True,
        "access_level": 4,
        "command": "disable-level5",
        "level5": {
            "enabled": False,
            "configured": False,
            "restart_required": True,
            "env_files": result["env_files"],
            "audit": result["audit"],
        },
        "changed": result["changed"],
        "next": "spark restart",
    }
