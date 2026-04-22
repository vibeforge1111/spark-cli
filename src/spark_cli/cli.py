from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib


SPARK_HOME = Path.home() / ".spark"
STATE_DIR = SPARK_HOME / "state"
LOG_DIR = SPARK_HOME / "logs"
REGISTRY_PATH = STATE_DIR / "installed.json"
CONFIG_PATH = STATE_DIR / "setup.json"
PID_PATH = STATE_DIR / "pids.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_REGISTRY_PATH = REPO_ROOT / "registry.json"


@dataclass
class Module:
    name: str
    path: Path
    manifest: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self.manifest.get("module", {}).get("version", "unknown"))

    @property
    def kind(self) -> str:
        return str(self.manifest.get("module", {}).get("kind", "unknown"))

    @property
    def plane(self) -> str:
        return str(self.manifest.get("module", {}).get("plane", "unknown"))

    @property
    def capabilities(self) -> list[str]:
        return [str(item) for item in self.manifest.get("provides", {}).get("capabilities", [])]

    @property
    def claims(self) -> dict[str, list[Any]]:
        return {
            "secrets": list(self.manifest.get("claims", {}).get("secrets", [])),
            "ports": list(self.manifest.get("claims", {}).get("ports", [])),
            "routes": list(self.manifest.get("claims", {}).get("routes", [])),
        }

    @property
    def run_command(self) -> str | None:
        run = self.manifest.get("run", {}).get("default", {})
        command = run.get("command")
        if not command:
            return None
        return str(command)

    @property
    def healthcheck_command(self) -> str | None:
        health = self.manifest.get("healthcheck", {})
        command = health.get("command")
        if not command:
            return None
        return str(command)

    @property
    def ready_check(self) -> str | None:
        run = self.manifest.get("run", {}).get("default", {})
        ready = run.get("ready_check")
        if not ready:
            return None
        return str(ready)

    @property
    def telegram_profile(self) -> dict[str, Any]:
        return dict(self.manifest.get("profiles", {}).get("telegram_starter", {}))


def load_registry_definition() -> dict[str, Any]:
    return load_json(LOCAL_REGISTRY_PATH, {"modules": {}, "bundles": {}})


def ensure_state_dirs() -> None:
    for path in (SPARK_HOME, STATE_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_module(path: Path) -> Module:
    manifest_path = path / "spark.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    name = str(manifest.get("module", {}).get("name") or path.name)
    return Module(name=name, path=path, manifest=manifest)


def discover_modules() -> dict[str, Module]:
    modules: dict[str, Module] = {}
    registry = load_registry_definition()
    for name, metadata in registry.get("modules", {}).items():
        path = Path(str(metadata.get("source", "")))
        manifest_path = path / "spark.toml"
        if manifest_path.exists():
            module = load_module(path)
            modules[module.name] = module
    return modules


def resolve_bundle(bundle_name: str, modules: dict[str, Module]) -> list[Module]:
    registry = load_registry_definition()
    bundle = registry.get("bundles", {}).get(bundle_name, {})
    names = bundle.get("modules")
    if not names:
        raise SystemExit(f"Unknown bundle: {bundle_name}")
    missing = [name for name in names if name not in modules]
    if missing:
        raise SystemExit(f"Bundle {bundle_name} is missing local module manifests: {', '.join(missing)}")
    return [modules[name] for name in names]


def resolve_bundle_names(bundle_name: str) -> list[str]:
    registry = load_registry_definition()
    bundle = registry.get("bundles", {}).get(bundle_name, {})
    names = bundle.get("modules")
    if not names:
        raise SystemExit(f"Unknown bundle: {bundle_name}")
    return [str(name) for name in names]


def expand_targets(target: str | None, modules: dict[str, Module], include_all: bool = False) -> list[str]:
    if target is None:
        return list(modules.keys()) if include_all else []
    registry = load_registry_definition()
    bundles = registry.get("bundles", {})
    if target in bundles:
        return list(bundles[target].get("modules", []))
    return [target]


def detect_ingress_owner(bundle: list[Module]) -> Module:
    owners = [module for module in bundle if "telegram.ingress" in module.capabilities]
    if len(owners) != 1:
        raise SystemExit(
            "Expected exactly one telegram ingress owner in bundle, found "
            f"{len(owners)}: {', '.join(module.name for module in owners) or 'none'}"
        )
    return owners[0]


def detect_capability_conflicts(candidate_modules: list[Module], installed_modules: dict[str, Module]) -> list[str]:
    combined: dict[str, Module] = dict(installed_modules)
    for module in candidate_modules:
        combined[module.name] = module

    capability_owners: dict[str, set[str]] = {}
    for module in combined.values():
        for capability in module.capabilities:
            capability_owners.setdefault(capability, set()).add(module.name)

    conflicts: list[str] = []
    ingress_owners = sorted(capability_owners.get("telegram.ingress", set()))
    if len(ingress_owners) > 1:
        conflicts.append("multiple telegram ingress owners declared: " + ", ".join(ingress_owners))
    return conflicts


def module_env_path(module: Module) -> Path | None:
    config = module.manifest.get("config", {})
    output = config.get("output")
    if not output:
        return None
    return module.path / str(output)


def update_env_file(path: Path, values: dict[str, str]) -> None:
    start = "# --- spark-cli managed start ---"
    end = "# --- spark-cli managed end ---"
    lines: list[str] = []
    if path.exists():
        existing = path.read_text(encoding="utf-8").splitlines()
        inside = False
        for line in existing:
            if line.strip() == start:
                inside = True
                continue
            if line.strip() == end:
                inside = False
                continue
            if not inside:
                lines.append(line)
        while lines and not lines[-1].strip():
            lines.pop()
    if lines:
        lines.append("")
    lines.append(start)
    for key, value in values.items():
        lines.append(f"{key}={value}")
    lines.append(end)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_list(_: argparse.Namespace) -> int:
    registry = load_registry_definition()
    installed = load_json(REGISTRY_PATH, {})
    modules = discover_modules()
    for module in modules.values():
        metadata = registry.get("modules", {}).get(module.name, {})
        blessed = "yes" if metadata.get("blessed") else "no"
        installed_marker = "installed" if module.name in installed else "available"
        print(
            f"{module.name}\t{module.version}\t{module.kind}\t{module.plane}\t{blessed}\t{installed_marker}\t{module.path}"
        )
    return 0


def resolve_install_target(target: str, modules: dict[str, Module]) -> Module:
    if target in modules:
        return modules[target]
    candidate = Path(target)
    if candidate.exists():
        manifest_path = candidate / "spark.toml"
        if not manifest_path.exists():
            raise SystemExit(f"{candidate} does not contain spark.toml")
        return load_module(candidate)
    raise SystemExit(f"Unknown module target: {target}")


def install_module_record(module: Module) -> None:
    installed = load_json(REGISTRY_PATH, {})
    installed[module.name] = {
        "path": str(module.path),
        "version": module.version,
        "kind": module.kind,
        "plane": module.plane,
    }
    save_json(REGISTRY_PATH, installed)


def print_install_summary(modules: list[Module]) -> None:
    print("Install plan:")
    for module in modules:
        print(f"- {module.name} ({module.kind}, {module.plane})")
    ingress_owners = [module.name for module in modules if "telegram.ingress" in module.capabilities]
    if ingress_owners:
        print(f"Telegram ingress owner: {', '.join(ingress_owners)}")


def install_modules(modules: list[Module]) -> None:
    print_install_summary(modules)
    for module in modules:
        install_module_record(module)
        print(f"Installed {module.name} from {module.path}")
        if "telegram.ingress" in module.capabilities:
            print("This module declares telegram.ingress and should be the only live Telegram token owner.")


def cmd_install(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = discover_modules()
    installed = load_json(REGISTRY_PATH, {})
    installed_modules = {name: load_module(Path(data["path"])) for name, data in installed.items()}
    registry = load_registry_definition()
    if args.target in registry.get("bundles", {}):
        bundle_modules = [modules[name] for name in resolve_bundle_names(args.target)]
        detect_ingress_owner(bundle_modules)
        conflicts = detect_capability_conflicts(bundle_modules, installed_modules)
        if conflicts:
            raise SystemExit("Cannot install bundle because of capability conflicts: " + "; ".join(conflicts))
        install_modules(bundle_modules)
        return 0
    module = resolve_install_target(args.target, modules)
    conflicts = detect_capability_conflicts([module], installed_modules)
    if conflicts:
        raise SystemExit("Cannot install module because of capability conflicts: " + "; ".join(conflicts))
    install_modules([module])
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = discover_modules()
    bundle = resolve_bundle(args.bundle, modules)
    ingress_owner = detect_ingress_owner(bundle)
    installed = load_json(REGISTRY_PATH, {})
    installed_modules = {name: load_module(Path(data["path"])) for name, data in installed.items()}
    conflicts = detect_capability_conflicts(bundle, installed_modules)
    if conflicts:
        raise SystemExit("Cannot run setup because of capability conflicts: " + "; ".join(conflicts))

    if not args.bot_token:
        raise SystemExit("--bot-token is required for the telegram-starter spike")
    if not args.admin_telegram_ids:
        raise SystemExit("--admin-telegram-ids is required for the telegram-starter spike")

    setup_state = {
        "bundle": args.bundle,
        "modules": [module.name for module in bundle],
        "telegram_ingress_owner": ingress_owner.name,
        "configured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_json(CONFIG_PATH, setup_state)
    install_modules(bundle)

    gateway = modules["spark-telegram-bot"]
    gateway_env = {
        "BOT_TOKEN": args.bot_token,
        "ADMIN_TELEGRAM_IDS": args.admin_telegram_ids,
        "SPARK_BUILDER_REPO": str(modules["spark-intelligence-builder"].path),
        "SPARK_BUILDER_BRIDGE_MODE": "auto",
        "SPAWNER_UI_URL": args.spawner_ui_url,
    }
    if args.telegram_gateway_mode:
        gateway_env["TELEGRAM_GATEWAY_MODE"] = args.telegram_gateway_mode
    if args.telegram_webhook_secret:
        gateway_env["TELEGRAM_WEBHOOK_SECRET"] = args.telegram_webhook_secret
    if args.telegram_webhook_url:
        gateway_env["TELEGRAM_WEBHOOK_URL"] = args.telegram_webhook_url

    gateway_env_path = module_env_path(gateway)
    if gateway_env_path is not None:
        update_env_file(gateway_env_path, gateway_env)

    spawner = modules["spawner-ui"]
    spawner_env = {
        "MISSION_CONTROL_WEBHOOK_URLS": f"{args.spawner_ui_url.replace('5173', '8788')}/spawner-events",
    }
    if args.telegram_webhook_secret:
        spawner_env["TELEGRAM_RELAY_SECRET"] = args.telegram_webhook_secret
    spawner_env_path = module_env_path(spawner)
    if spawner_env_path is not None:
        update_env_file(spawner_env_path, spawner_env)

    print("Spark setup complete.")
    print(f"Bundle: {args.bundle}")
    print(f"Telegram ingress owner: {ingress_owner.name}")
    print("Bot token routed only to spark-telegram-bot.")
    return 0


def run_shell(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
    )


def summarize_command_output(result: subprocess.CompletedProcess[str]) -> str:
    lines = []
    for raw_line in (result.stdout + "\n" + result.stderr).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("> "):
            continue
        lines.append(line)
    if not lines:
        return "no output"
    return lines[-1]


def cmd_status(_: argparse.Namespace) -> int:
    ensure_state_dirs()
    installed = load_json(REGISTRY_PATH, {})
    setup_state = load_json(CONFIG_PATH, {})
    if not installed:
        print("No installed Spark modules recorded. Run `spark setup telegram-starter` first.")
        return 1

    modules = {name: load_module(Path(data["path"])) for name, data in installed.items()}
    print("Spark CLI spike status")
    ingress_owner = setup_state.get("telegram_ingress_owner")
    if ingress_owner:
        print(f"Telegram ingress owner: {ingress_owner}")
    print("")

    exit_code = 0
    for module in modules.values():
        command = module.healthcheck_command
        if not command:
            print(f"[SKIP] {module.name:<26} no healthcheck declared")
            continue
        result = run_shell(command, module.path)
        ok = result.returncode == 0
        marker = "[OK]" if ok else "[ERR]"
        detail = summarize_command_output(result)
        if not ok:
            failure_hint = str(module.manifest.get("healthcheck", {}).get("failure_hint", "")).strip()
            if failure_hint:
                detail = f"{detail} -- {failure_hint}"
        print(f"{marker} {module.name:<26} {detail}")
        if not ok:
            exit_code = 1
    return exit_code


def load_pids() -> dict[str, Any]:
    return load_json(PID_PATH, {})


def save_pids(payload: dict[str, Any]) -> None:
    save_json(PID_PATH, payload)


def start_module(module: Module) -> None:
    command = module.run_command
    if not command:
        return

    module_log_dir = LOG_DIR / module.name
    module_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = module_log_dir / "process.log"
    log_handle = log_path.open("a", encoding="utf-8")

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    process = subprocess.Popen(
        command,
        cwd=str(module.path),
        shell=True,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    pids = load_pids()
    pids[module.name] = {
        "pid": process.pid,
        "command": command,
        "path": str(module.path),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "log_path": str(log_path),
    }
    save_pids(pids)
    print(f"Started {module.name} (pid {process.pid})")


def cmd_start(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    installed = load_json(REGISTRY_PATH, {})
    if not installed:
        print("No installed Spark modules recorded. Run `spark setup telegram-starter` first.")
        return 1

    modules = {name: load_module(Path(data["path"])) for name, data in installed.items()}
    target_names = expand_targets(args.target, modules, include_all=True)
    for name in target_names:
        module = modules.get(name)
        if module is None:
            raise SystemExit(f"Unknown installed module: {name}")
        if not module.run_command:
            print(f"Skipping {module.name}: no run.default command declared")
            continue
        start_module(module)
    return 0


def stop_module(name: str, pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    else:
        subprocess.run(["kill", str(pid)], check=False, capture_output=True)
    print(f"Stopped {name} (pid {pid})")


def cmd_stop(args: argparse.Namespace) -> int:
    pids = load_pids()
    if not pids:
        print("No tracked Spark processes.")
        return 0

    target_names = expand_targets(args.target, {name: None for name in pids}, include_all=True)
    for name in target_names:
        record = pids.get(name)
        if not record:
            print(f"Skipping {name}: no tracked pid")
            continue
        stop_module(name, int(record["pid"]))
        pids.pop(name, None)
    save_pids(pids)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spark", description="Spark installer and operator CLI spike")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List local Spark modules with manifests")
    list_parser.set_defaults(func=cmd_list)

    install_parser = subparsers.add_parser("install", help="Install a module by registry name or local repo path")
    install_parser.add_argument("target")
    install_parser.set_defaults(func=cmd_install)

    setup_parser = subparsers.add_parser("setup", help="Configure a starter bundle")
    setup_parser.add_argument("bundle", choices=sorted(load_registry_definition().get("bundles", {}).keys()))
    setup_parser.add_argument("--bot-token")
    setup_parser.add_argument("--admin-telegram-ids")
    setup_parser.add_argument("--telegram-gateway-mode", choices=["auto", "polling", "webhook"], default="auto")
    setup_parser.add_argument("--telegram-webhook-url")
    setup_parser.add_argument("--telegram-webhook-secret")
    setup_parser.add_argument("--spawner-ui-url", default="http://127.0.0.1:5173")
    setup_parser.set_defaults(func=cmd_setup)

    status_parser = subparsers.add_parser("status", help="Run module healthchecks")
    status_parser.set_defaults(func=cmd_status)

    start_parser = subparsers.add_parser("start", help="Start startable modules")
    start_parser.add_argument("target", nargs="?")
    start_parser.set_defaults(func=cmd_start)

    stop_parser = subparsers.add_parser("stop", help="Stop tracked Spark processes")
    stop_parser.add_argument("target", nargs="?")
    stop_parser.set_defaults(func=cmd_stop)

    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_state_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
