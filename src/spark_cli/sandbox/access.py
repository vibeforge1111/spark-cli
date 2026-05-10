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
    telegram_env["SPARK_ALLOW_HIGH_AGENCY_WORKERS"] = "1"
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
        "telegram": _remove_env_keys(paths["telegram"], {"SPARK_ALLOW_HIGH_AGENCY_WORKERS"}),
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
            "spark restart"
            if level5_restart_required
            else "spark access setup --level 5"
            if level5_enabled
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
                    "Whole-computer mode is enabled, but Spark should still prefer a sandbox."
                    if level5_enabled
                    else "Whole-computer mode is configured; restart Spark so Telegram and Spawner load the guardrails."
                    if level5_restart_required
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
        "os_family": family,
        "workspace_root": str(workspace_root),
        "workspace_path": str(workspace_path),
        "workspace_preflight": workspace_preflight,
        "level5": {
            "enabled": level5_enabled,
            "configured": level5_configured,
            "process_enabled": level5_process_enabled,
            "external_paths": level5_external_paths,
            "codex_sandbox": env_values.get("SPARK_CODEX_SANDBOX") or "workspace-write",
            "configured_codex_sandbox": generated_env.get("SPARK_CODEX_SANDBOX") or "",
            "restart_required": level5_restart_required,
            "env_files": written_level5_env,
            "audit": sandbox_audit_ref("access", "level5") if written_level5_env else {},
            "disable_command": "spark access disable-level5",
        },
        "setup_ran": setup,
        "recommended": recommended,
        "lanes": lanes,
        "next": next_action,
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
