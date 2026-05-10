from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from .audit import sandbox_audit_ref, write_audit_event
from .docker import collect_docker_doctor_payload
from .modal import modal_auth_markers, modal_sdk_available
from .ssh import load_ssh_targets


LEVEL5_ENV = {
    "SPARK_ALLOW_HIGH_AGENCY_WORKERS": "1",
    "SPARK_ALLOW_EXTERNAL_PROJECT_PATHS": "1",
    "SPARK_CODEX_SANDBOX": "danger-full-access",
}


DEFAULT_ACCESS_LEVEL = 4
DEFAULT_SANDBOX_LANE = "spark_workspace"
DEFAULT_CODEX_SANDBOX = "workspace-write"


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
        values[key.strip().lstrip("\ufeff")] = value
    return values


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")


def level5_env_paths(*, home: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Path]:
    root = module_env_dir(home=home, env=env)
    return {
        "spawner": root / "spawner-ui.env",
        "telegram": root / "spark-telegram-bot.env",
    }


def persist_level5_guardrails(*, home: Path | None = None, env: dict[str, str] | None = None) -> dict[str, str]:
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


def disable_level5_guardrails(*, home: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
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
    level5_configured = level >= 5 and level5_activation_state in {"active", "restart_required", "session_only"}
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
                    else "Spark must ask before enabling Level 5. It writes guardrail env files, records an audit event, and then requires Spark restart."
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
) -> dict[str, Any]:
    env_values = env or os.environ
    written_level5_env: dict[str, str] = {}
    if setup and level >= 5 and enable_high_agency:
        written_level5_env = persist_level5_guardrails(home=home, env=env_values)
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
    level5_enabled = level5_process_enabled and level5_external_paths and level5_full_sandbox
    level5_restart_required = level5_configured and not level5_enabled
    if level5_enabled and level5_configured:
        level5_activation_state = "active"
    elif level5_enabled:
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
            if level5_activation_state == "active"
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
    elif level >= 5 and level5_activation_state == "active":
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


def level5_disable_payload(*, home: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    result = disable_level5_guardrails(home=home, env=env)
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
