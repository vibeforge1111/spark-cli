from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib


SPARK_HOME = Path.home() / ".spark"
STATE_DIR = SPARK_HOME / "state"
CONFIG_DIR = SPARK_HOME / "config"
MODULE_CONFIG_DIR = CONFIG_DIR / "modules"
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
    def needs_modules(self) -> list[str]:
        return [str(item) for item in self.manifest.get("needs", {}).get("modules", [])]

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
    def install_commands(self) -> list[str]:
        commands = self.manifest.get("install", {}).get("dev", {}).get("commands", [])
        return [str(command) for command in commands]

    @property
    def telegram_profile(self) -> dict[str, Any]:
        return dict(self.manifest.get("profiles", {}).get("telegram_starter", {}))

    @property
    def needed_secrets(self) -> list[str]:
        return [str(item) for item in self.manifest.get("needs", {}).get("secrets", [])]

    def resolve_secret_definition(self, secret_id: str) -> dict[str, Any]:
        secret_blocks = self.manifest.get("secrets", {})
        candidates = [
            secret_id,
            secret_id.replace(".", "_"),
            secret_id.replace("-", "_"),
        ]
        for candidate in candidates:
            block = secret_blocks.get(candidate)
            if isinstance(block, dict):
                return dict(block)
        suffix = secret_id.split(".")[-1].replace("-", "_")
        for key, block in secret_blocks.items():
            if str(key).endswith(suffix) and isinstance(block, dict):
                return dict(block)
        return {}

    def hook_command(self, hook_name: str) -> str | None:
        hooks = self.manifest.get("hooks", {})
        command = hooks.get(hook_name)
        if not command:
            return None
        return str(command)


def load_registry_definition() -> dict[str, Any]:
    return load_json(LOCAL_REGISTRY_PATH, {"modules": {}, "bundles": {}})


def ensure_state_dirs() -> None:
    for path in (SPARK_HOME, STATE_DIR, CONFIG_DIR, MODULE_CONFIG_DIR, LOG_DIR):
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


def timestamp_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_secret_pairs(raw_pairs: list[str] | None) -> dict[str, str]:
    secrets: dict[str, str] = {}
    for raw in raw_pairs or []:
        if "=" not in raw:
            raise SystemExit(f"Invalid --secret value: {raw}. Expected KEY=VALUE.")
        key, value = raw.split("=", 1)
        secrets[key.strip()] = value
    return secrets


def collect_secret_requirements(modules: list[Module]) -> dict[str, dict[str, Any]]:
    requirements: dict[str, dict[str, Any]] = {}
    for module in modules:
        for secret_id in module.needed_secrets:
            definition = module.resolve_secret_definition(secret_id)
            requirement = requirements.setdefault(
                secret_id,
                {
                    "prompt": definition.get("prompt") or secret_id,
                    "required": bool(definition.get("required", True)),
                    "env_var": definition.get("env_var"),
                    "modules": [],
                },
            )
            requirement["modules"].append(module.name)
            if definition.get("required", False):
                requirement["required"] = True
            if definition.get("env_var") and not requirement.get("env_var"):
                requirement["env_var"] = definition.get("env_var")
    return requirements


def collect_secret_values(args: argparse.Namespace, modules: list[Module]) -> dict[str, str]:
    secret_values = parse_secret_pairs(getattr(args, "secret", None))
    legacy_map = {
        "telegram.bot_token": getattr(args, "bot_token", None),
        "telegram.admin_ids": getattr(args, "admin_telegram_ids", None),
        "telegram.webhook_secret": getattr(args, "telegram_webhook_secret", None),
    }
    for key, value in legacy_map.items():
        if value:
            secret_values.setdefault(key, str(value))

    requirements = collect_secret_requirements(modules)
    missing = [
        secret_id
        for secret_id, requirement in requirements.items()
        if requirement.get("required") and not secret_values.get(secret_id)
    ]
    if missing:
        descriptions = []
        for secret_id in missing:
            requirement = requirements[secret_id]
            descriptions.append(f"{secret_id} ({requirement.get('prompt')})")
        raise SystemExit("Missing required secrets: " + ", ".join(descriptions))
    return secret_values


def generated_module_env_path(module: Module) -> Path:
    return MODULE_CONFIG_DIR / f"{module.name}.env"


def write_generated_env(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_module_envs(args: argparse.Namespace, modules_by_name: dict[str, Module], secret_values: dict[str, str]) -> dict[str, dict[str, str]]:
    gateway = modules_by_name["spark-telegram-bot"]
    spawner = modules_by_name["spawner-ui"]
    builder = modules_by_name["spark-intelligence-builder"]

    gateway_env = {
        "BOT_TOKEN": secret_values.get("telegram.bot_token", ""),
        "ADMIN_TELEGRAM_IDS": secret_values.get("telegram.admin_ids", ""),
        "SPARK_BUILDER_REPO": str(builder.path),
        "SPARK_BUILDER_BRIDGE_MODE": "auto",
        "SPAWNER_UI_URL": args.spawner_ui_url,
        "TELEGRAM_GATEWAY_MODE": args.telegram_gateway_mode,
    }
    if secret_values.get("telegram.webhook_secret"):
        gateway_env["TELEGRAM_WEBHOOK_SECRET"] = secret_values["telegram.webhook_secret"]
    if args.telegram_webhook_url:
        gateway_env["TELEGRAM_WEBHOOK_URL"] = args.telegram_webhook_url

    relay_base = args.spawner_ui_url
    if relay_base.endswith(":5173"):
        relay_base = relay_base[:-4] + "8788"
    spawner_env = {
        "MISSION_CONTROL_WEBHOOK_URLS": f"{relay_base}/spawner-events",
    }
    if secret_values.get("telegram.webhook_secret"):
        spawner_env["TELEGRAM_RELAY_SECRET"] = secret_values["telegram.webhook_secret"]

    return {
        gateway.name: gateway_env,
        spawner.name: spawner_env,
        builder.name: {},
    }


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


def remove_managed_env_block(path: Path) -> None:
    start = "# --- spark-cli managed start ---"
    end = "# --- spark-cli managed end ---"
    if not path.exists():
        return
    lines: list[str] = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
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
    output = "\n".join(lines).strip()
    path.write_text((output + "\n") if output else "", encoding="utf-8")


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


def install_module_record(
    module: Module,
    *,
    operation: str,
    source_kind: str,
    source_target: str,
    skip_install_commands: bool,
    bundle_name: str | None = None,
) -> None:
    installed = load_json(REGISTRY_PATH, {})
    existing = dict(installed.get(module.name, {}))
    registry_metadata = load_registry_definition().get("modules", {}).get(module.name, {})
    now = timestamp_now()
    installed_via = dict(existing.get("installed_via", {}))
    if not installed_via:
        installed_via = {
            "kind": source_kind,
            "target": source_target,
        }
        if bundle_name:
            installed_via["bundle"] = bundle_name

    bundle_provenance = list(existing.get("bundle_provenance", []))
    if bundle_name and bundle_name not in bundle_provenance:
        bundle_provenance.append(bundle_name)

    installed[module.name] = {
        **existing,
        "path": str(module.path),
        "source": str(module.path),
        "version": module.version,
        "kind": module.kind,
        "plane": module.plane,
        "summary": str(registry_metadata.get("summary") or module.manifest.get("module", {}).get("description", "")),
        "blessed": bool(registry_metadata.get("blessed", False)),
        "installed_at": existing.get("installed_at") or now,
        "updated_at": now,
        "installed_via": installed_via,
        "bundle_provenance": bundle_provenance,
    }
    outcome_key = "last_install" if operation == "install" else "last_update"
    installed[module.name][outcome_key] = {
        "status": "ok",
        "at": now,
        "source_kind": source_kind,
        "source_target": source_target,
        "bundle": bundle_name,
        "skip_install_commands": skip_install_commands,
    }
    save_json(REGISTRY_PATH, installed)


def describe_installed_record(module: Module, record: dict[str, Any]) -> dict[str, Any]:
    registry_metadata = load_registry_definition().get("modules", {}).get(module.name, {})
    installed = dict(record)
    installed.setdefault("path", str(module.path))
    installed.setdefault("source", str(module.path))
    installed.setdefault("version", module.version)
    installed.setdefault("kind", module.kind)
    installed.setdefault("plane", module.plane)
    installed.setdefault("summary", str(registry_metadata.get("summary") or module.manifest.get("module", {}).get("description", "")))
    installed.setdefault("blessed", bool(registry_metadata.get("blessed", False)))
    return installed


def remove_module_record(module_name: str) -> None:
    installed = load_json(REGISTRY_PATH, {})
    installed.pop(module_name, None)
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
        print(f"Installed {module.name} from {module.path}")
        if "telegram.ingress" in module.capabilities:
            print("This module declares telegram.ingress and should be the only live Telegram token owner.")


def execute_install_commands(module: Module) -> None:
    for command in module.install_commands:
        print(f"Running install command for {module.name}: {command}")
        result = run_shell(command, module.path)
        if result.returncode != 0:
            raise SystemExit(
                f"{module.name} install command failed: {summarize_command_output(result)}"
            )


def run_module_hook(module: Module, hook_name: str) -> None:
    command = module.hook_command(hook_name)
    if not command:
        return
    result = run_shell(command, module.path)
    if result.returncode != 0:
        raise SystemExit(
            f"{module.name} hook `{hook_name}` failed: {summarize_command_output(result)}"
        )


def sync_generated_env_to_module(module: Module) -> None:
    generated_path = generated_module_env_path(module)
    env_path = module_env_path(module)
    if env_path is None or not generated_path.exists():
        return
    values: dict[str, str] = {}
    for line in generated_path.read_text(encoding="utf-8").splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    if values:
        update_env_file(env_path, values)


def update_setup_state_after_uninstall(module_names: list[str]) -> None:
    setup_state = load_json(CONFIG_PATH, {})
    if not setup_state:
        return
    remaining = [name for name in setup_state.get("modules", []) if name not in module_names]
    if not remaining:
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
        return
    setup_state["modules"] = remaining
    if setup_state.get("telegram_ingress_owner") in module_names:
        setup_state["telegram_ingress_owner"] = None
    save_json(CONFIG_PATH, setup_state)


def resolve_installed_modules() -> dict[str, Module]:
    installed = load_json(REGISTRY_PATH, {})
    return {name: load_module(Path(data["path"])) for name, data in installed.items()}


def detect_uninstall_blockers(removing_modules: list[Module], installed_modules: dict[str, Module]) -> list[str]:
    removing_names = {module.name for module in removing_modules}
    blockers: list[str] = []
    for module in installed_modules.values():
        if module.name in removing_names:
            continue
        for dependency in module.needs_modules:
            if dependency in removing_names:
                blockers.append(f"{module.name} depends on {dependency}")
    return blockers


def evaluate_module_health(module: Module) -> dict[str, Any]:
    command = module.healthcheck_command
    if not command:
        return {
            "name": module.name,
            "version": module.version,
            "kind": module.kind,
            "plane": module.plane,
            "healthy": None,
            "detail": "no healthcheck declared",
            "healthcheck_command": None,
            "failure_hint": None,
        }
    result = run_shell(command, module.path)
    detail = summarize_command_output(result)
    failure_hint = str(module.manifest.get("healthcheck", {}).get("failure_hint", "")).strip() or None
    success_hint = str(module.manifest.get("healthcheck", {}).get("success_hint", "")).strip() or None
    return {
        "name": module.name,
        "version": module.version,
        "kind": module.kind,
        "plane": module.plane,
        "healthy": result.returncode == 0,
        "detail": detail,
        "healthcheck_command": command,
        "failure_hint": failure_hint,
        "success_hint": success_hint,
    }


def determine_install_source_kind(target: str, modules: dict[str, Module]) -> str:
    if target in load_registry_definition().get("modules", {}):
        return "registry"
    if Path(target).exists():
        return "local_path"
    if target in modules:
        return "discovered"
    return "unknown"


def dependency_issues_for_module(module: Module, module_results: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    missing_dependencies: list[str] = []
    unhealthy_dependencies: list[str] = []
    for dependency in module.needs_modules:
        dependency_result = module_results.get(dependency)
        if dependency_result is None:
            missing_dependencies.append(dependency)
            continue
        if dependency_result.get("healthy") is False:
            unhealthy_dependencies.append(dependency)
    return missing_dependencies, unhealthy_dependencies


def build_module_repair_hints(
    module: Module,
    result: dict[str, Any],
    module_results: dict[str, dict[str, Any]],
    setup_state: dict[str, Any],
) -> list[str]:
    hints: list[str] = []
    missing_dependencies, unhealthy_dependencies = dependency_issues_for_module(module, module_results)
    if missing_dependencies:
        hints.append(
            "Install missing dependencies first: " + ", ".join(missing_dependencies) + "."
        )
    if unhealthy_dependencies:
        hints.append(
            "Repair dependency health first: " + ", ".join(unhealthy_dependencies) + "."
        )
    if result.get("healthy") is False and result.get("failure_hint"):
        hints.append(str(result["failure_hint"]))
    if module.manifest.get("config", {}).get("installer_owned"):
        generated_path = generated_module_env_path(module)
        env_path = module_env_path(module)
        if env_path is not None and not generated_path.exists():
            bundle_name = setup_state.get("bundle") or "telegram-starter"
            hints.append(f"Run `spark setup {bundle_name}` to regenerate installer-owned config.")
    deduped: list[str] = []
    for hint in hints:
        if hint not in deduped:
            deduped.append(hint)
    return deduped


def build_status_repair_hints(
    modules: dict[str, Module],
    module_results: list[dict[str, Any]],
    setup_state: dict[str, Any],
) -> list[str]:
    hints: list[str] = []
    bundle_name = setup_state.get("bundle")
    installed_names = set(modules)
    if bundle_name:
        expected_modules: set[str] | None = None
        try:
            expected_modules = set(resolve_bundle_names(str(bundle_name)))
        except SystemExit:
            hints.append(
                f"Configured bundle `{bundle_name}` is not present in the local registry. Run `spark setup telegram-starter`."
            )
        if expected_modules is not None:
            missing_modules = sorted(expected_modules - installed_names)
            if missing_modules:
                hints.append(
                    f"Setup bundle `{bundle_name}` is incomplete. Reinstall missing modules: {', '.join(missing_modules)}."
                )
    ingress_owner = setup_state.get("telegram_ingress_owner")
    if ingress_owner and ingress_owner not in installed_names:
        hints.append(
            f"Configured Telegram ingress owner `{ingress_owner}` is not installed. Run `spark setup {bundle_name or 'telegram-starter'}`."
        )
    module_results_by_name = {item["name"]: item for item in module_results}
    for module in modules.values():
        missing_dependencies, unhealthy_dependencies = dependency_issues_for_module(module, module_results_by_name)
        if missing_dependencies:
            hints.append(
                f"{module.name} is missing dependencies: {', '.join(missing_dependencies)}."
            )
        if unhealthy_dependencies:
            hints.append(
                f"{module.name} is blocked on unhealthy dependencies: {', '.join(unhealthy_dependencies)}."
            )
    deduped: list[str] = []
    for hint in hints:
        if hint not in deduped:
            deduped.append(hint)
    return deduped


def cmd_install(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = discover_modules()
    installed_modules = resolve_installed_modules()
    registry = load_registry_definition()
    if args.target in registry.get("bundles", {}):
        bundle_modules = [modules[name] for name in resolve_bundle_names(args.target)]
        detect_ingress_owner(bundle_modules)
        conflicts = detect_capability_conflicts(bundle_modules, installed_modules)
        if conflicts:
            raise SystemExit("Cannot install bundle because of capability conflicts: " + "; ".join(conflicts))
        if not args.skip_install_commands:
            for module in bundle_modules:
                execute_install_commands(module)
        install_modules(bundle_modules)
        for module in bundle_modules:
            install_module_record(
                module,
                operation="install",
                source_kind="bundle",
                source_target=args.target,
                bundle_name=args.target,
                skip_install_commands=args.skip_install_commands,
            )
        return 0
    module = resolve_install_target(args.target, modules)
    source_kind = determine_install_source_kind(args.target, modules)
    conflicts = detect_capability_conflicts([module], installed_modules)
    if conflicts:
        raise SystemExit("Cannot install module because of capability conflicts: " + "; ".join(conflicts))
    if not args.skip_install_commands:
        execute_install_commands(module)
    install_modules([module])
    install_module_record(
        module,
        operation="install",
        source_kind=source_kind,
        source_target=args.target,
        skip_install_commands=args.skip_install_commands,
    )
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = discover_modules()
    bundle = resolve_bundle(args.bundle, modules)
    ingress_owner = detect_ingress_owner(bundle)
    installed_modules = resolve_installed_modules()
    conflicts = detect_capability_conflicts(bundle, installed_modules)
    if conflicts:
        raise SystemExit("Cannot run setup because of capability conflicts: " + "; ".join(conflicts))
    secret_values = collect_secret_values(args, bundle)

    setup_state = {
        "bundle": args.bundle,
        "modules": [module.name for module in bundle],
        "telegram_ingress_owner": ingress_owner.name,
        "configured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "secret_keys": sorted(secret_values.keys()),
    }
    save_json(CONFIG_PATH, setup_state)
    if not args.skip_install_commands:
        for module in bundle:
            execute_install_commands(module)
    install_modules(bundle)
    for module in bundle:
        install_module_record(
            module,
            operation="install",
            source_kind="bundle",
            source_target=args.bundle,
            bundle_name=args.bundle,
            skip_install_commands=args.skip_install_commands,
        )

    generated_envs = build_module_envs(args, modules, secret_values)
    for module in bundle:
        env_values = generated_envs.get(module.name, {})
        generated_path = generated_module_env_path(module)
        write_generated_env(generated_path, env_values)
        env_path = module_env_path(module)
        if env_path is not None and env_values:
            update_env_file(env_path, env_values)

    print("Spark setup complete.")
    print(f"Bundle: {args.bundle}")
    print(f"Telegram ingress owner: {ingress_owner.name}")
    print("Bot token routed only to spark-telegram-bot.")
    print(f"Generated module config dir: {MODULE_CONFIG_DIR}")
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


def collect_status_payload() -> dict[str, Any]:
    ensure_state_dirs()
    installed = load_json(REGISTRY_PATH, {})
    setup_state = load_json(CONFIG_PATH, {})
    if not installed:
        return {
            "ok": False,
            "summary": "No installed Spark modules recorded.",
            "repair": "Run `spark setup telegram-starter` first.",
            "modules": [],
        }

    modules = {name: load_module(Path(data["path"])) for name, data in installed.items()}
    module_results = [evaluate_module_health(module) for module in modules.values()]
    module_results_by_name = {item["name"]: item for item in module_results}
    for item in module_results:
        item["installed"] = describe_installed_record(modules[item["name"]], dict(installed.get(item["name"], {})))
        item["repair_hints"] = build_module_repair_hints(
            modules[item["name"]],
            item,
            module_results_by_name,
            setup_state,
        )
    repair_hints = build_status_repair_hints(modules, module_results, setup_state)
    ok = all(item["healthy"] is not False for item in module_results) and not repair_hints
    return {
        "ok": ok,
        "summary": "Spark CLI spike status",
        "telegram_ingress_owner": setup_state.get("telegram_ingress_owner"),
        "modules": module_results,
        "tracked_pids": load_pids(),
        "config_dir": str(CONFIG_DIR),
        "repair_hints": repair_hints,
    }


def cmd_status(args: argparse.Namespace) -> int:
    payload = collect_status_payload()
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if payload.get("ok") else 1

    if not payload.get("modules"):
        print(payload["summary"])
        print(payload["repair"])
        return 1

    print(payload["summary"])
    ingress_owner = payload.get("telegram_ingress_owner")
    if ingress_owner:
        print(f"Telegram ingress owner: {ingress_owner}")
    for hint in payload.get("repair_hints", []):
        print(f"Repair: {hint}")
    print("")

    exit_code = 0
    for module in payload["modules"]:
        healthy = module["healthy"]
        if healthy is None:
            marker = "[SKIP]"
        elif healthy:
            marker = "[OK]"
        else:
            marker = "[ERR]"
        detail = str(module["detail"])
        if module.get("repair_hints"):
            detail = f"{detail} -- {' '.join(module['repair_hints'])}"
        print(f"{marker} {module['name']:<26} {detail}")
        if healthy is False:
            exit_code = 1
    if payload.get("repair_hints"):
        exit_code = 1
    return exit_code


def cmd_doctor(args: argparse.Namespace) -> int:
    payload = collect_status_payload()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("Spark CLI spike doctor")
        print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 1


def resolve_installed_target_modules(target: str | None) -> list[Module]:
    modules = resolve_installed_modules()
    if not modules:
        return []
    names = expand_targets(target, modules, include_all=True)
    resolved: list[Module] = []
    for name in names:
        module = modules.get(name)
        if module is None:
            raise SystemExit(f"Unknown installed module: {name}")
        resolved.append(module)
    return resolved


def reverse_dependency_map(modules: dict[str, Module]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {}
    for module in modules.values():
        for dependency in module.needs_modules:
            reverse.setdefault(dependency, set()).add(module.name)
    return reverse


def topologically_sort_modules(modules: dict[str, Module]) -> list[Module]:
    ordered: list[Module] = []
    permanent: set[str] = set()
    temporary: set[str] = set()

    def visit(name: str) -> None:
        if name in permanent:
            return
        if name in temporary:
            raise SystemExit(f"Dependency cycle detected while ordering modules: {name}")
        module = modules.get(name)
        if module is None:
            raise SystemExit(f"Cannot order missing module: {name}")
        temporary.add(name)
        for dependency in module.needs_modules:
            if dependency in modules:
                visit(dependency)
        temporary.remove(name)
        permanent.add(name)
        ordered.append(module)

    for name in sorted(modules):
        visit(name)
    return ordered


def resolve_start_modules(target: str | None, installed_modules: dict[str, Module]) -> list[Module]:
    requested_names = expand_targets(target, installed_modules, include_all=True)
    needed_names: set[str] = set()
    stack = list(requested_names)
    while stack:
        name = stack.pop()
        module = installed_modules.get(name)
        if module is None:
            raise SystemExit(f"Unknown installed module: {name}")
        if name in needed_names:
            continue
        needed_names.add(name)
        missing_dependencies = [dependency for dependency in module.needs_modules if dependency not in installed_modules]
        if missing_dependencies:
            raise SystemExit(
                f"Cannot start {module.name} because required modules are not installed: {', '.join(missing_dependencies)}"
            )
        stack.extend(module.needs_modules)
    selected_modules = {name: installed_modules[name] for name in needed_names}
    return topologically_sort_modules(selected_modules)


def resolve_stop_module_names(target: str | None, installed_modules: dict[str, Module], tracked_pids: dict[str, Any]) -> list[str]:
    if not tracked_pids:
        return []
    requested_names = expand_targets(target, installed_modules, include_all=True)
    reverse_map = reverse_dependency_map(installed_modules)
    stop_names: set[str] = set()
    stack = list(requested_names)
    while stack:
        name = stack.pop()
        if name in stop_names:
            continue
        stop_names.add(name)
        stack.extend(sorted(reverse_map.get(name, set())))

    installed_subset = {name: installed_modules[name] for name in stop_names if name in installed_modules}
    ordered_names = [module.name for module in reversed(topologically_sort_modules(installed_subset))]
    extra_names = [name for name in stop_names if name not in installed_subset]
    return ordered_names + sorted(extra_names)


def load_pids() -> dict[str, Any]:
    return load_json(PID_PATH, {})


def save_pids(payload: dict[str, Any]) -> None:
    save_json(PID_PATH, payload)


def pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def ready_timeout_seconds(module: Module) -> int:
    configured = module.manifest.get("healthcheck", {}).get("timeout_seconds", 10)
    try:
        return max(1, int(configured))
    except (TypeError, ValueError):
        return 10


def wait_for_ready_check(module: Module) -> tuple[bool, str]:
    ready_check = module.ready_check
    if not ready_check:
        return True, "no ready check declared"

    deadline = time.time() + ready_timeout_seconds(module)
    last_error = "ready check did not pass before timeout"
    while time.time() < deadline:
        if ready_check.startswith(("http://", "https://")):
            try:
                with urllib.request.urlopen(ready_check, timeout=2) as response:
                    if 200 <= int(response.status) < 400:
                        return True, ready_check
                    last_error = f"ready check returned HTTP {response.status}"
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = str(error)
        else:
            result = run_shell(ready_check, module.path)
            if result.returncode == 0:
                return True, summarize_command_output(result)
            last_error = summarize_command_output(result)
        time.sleep(1)
    return False, last_error


def start_module(module: Module) -> bool:
    command = module.run_command
    if not command:
        return True

    pids = load_pids()
    existing = pids.get(module.name)
    if existing:
        existing_pid = int(existing.get("pid", 0))
        if pid_is_running(existing_pid):
            print(f"Skipping {module.name}: already running (pid {existing_pid})")
            return True
        pids.pop(module.name, None)
        save_pids(pids)

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
    pids[module.name] = {
        "pid": process.pid,
        "command": command,
        "path": str(module.path),
        "started_at": timestamp_now(),
        "log_path": str(log_path),
        "ready_check": module.ready_check,
    }
    save_pids(pids)
    print(f"Started {module.name} (pid {process.pid})")
    ready, detail = wait_for_ready_check(module)
    if ready:
        print(f"Ready {module.name}: {detail}")
    else:
        print(f"Start warning for {module.name}: {detail}")
    return ready


def cmd_start(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = resolve_installed_modules()
    if not modules:
        print("No installed Spark modules recorded. Run `spark setup telegram-starter` first.")
        return 1
    exit_code = 0
    target_modules = resolve_start_modules(args.target, modules)
    for module in target_modules:
        if not module.run_command:
            print(f"Skipping {module.name}: no run.default command declared")
            continue
        if not start_module(module):
            exit_code = 1
    return exit_code


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

    installed_modules = resolve_installed_modules()
    target_names = resolve_stop_module_names(args.target, installed_modules, pids)
    for name in target_names:
        record = pids.get(name)
        if not record:
            print(f"Skipping {name}: no tracked pid")
            continue
        stop_module(name, int(record["pid"]))
        pids.pop(name, None)
    save_pids(pids)
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = resolve_installed_target_modules(args.target)
    if not modules:
        print("No installed Spark modules recorded.")
        return 0
    print_install_summary(modules)
    for module in modules:
        if not args.skip_install_commands:
            execute_install_commands(module)
        run_module_hook(module, "post_install")
        existing_record = load_json(REGISTRY_PATH, {}).get(module.name, {})
        installed_via = dict(existing_record.get("installed_via", {}))
        install_module_record(
            module,
            operation="update",
            source_kind=str(installed_via.get("kind", "installed")),
            source_target=str(installed_via.get("target", module.path)),
            bundle_name=installed_via.get("bundle"),
            skip_install_commands=args.skip_install_commands,
        )
        sync_generated_env_to_module(module)
        print(f"Updated {module.name} from {module.path}")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    ensure_state_dirs()
    modules = resolve_installed_target_modules(args.target)
    if not modules:
        print("No installed Spark modules recorded.")
        return 0
    installed_modules = resolve_installed_modules()
    blockers = detect_uninstall_blockers(modules, installed_modules)
    if blockers and not args.force:
        raise SystemExit("Cannot uninstall because other installed modules depend on it: " + "; ".join(blockers))

    pids = load_pids()
    removed_names: list[str] = []
    for module in modules:
        run_module_hook(module, "pre_uninstall")
        record = pids.get(module.name)
        if record:
            stop_module(module.name, int(record["pid"]))
            pids.pop(module.name, None)
        generated_path = generated_module_env_path(module)
        if generated_path.exists():
            generated_path.unlink()
        env_path = module_env_path(module)
        if env_path is not None:
            remove_managed_env_block(env_path)
        remove_module_record(module.name)
        run_module_hook(module, "post_uninstall")
        removed_names.append(module.name)
        print(f"Uninstalled {module.name}")
    save_pids(pids)
    update_setup_state_after_uninstall(removed_names)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spark", description="Spark installer and operator CLI spike")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List local Spark modules with manifests")
    list_parser.set_defaults(func=cmd_list)

    install_parser = subparsers.add_parser("install", help="Install a module by registry name or local repo path")
    install_parser.add_argument("target")
    install_parser.add_argument("--skip-install-commands", action="store_true")
    install_parser.set_defaults(func=cmd_install)

    setup_parser = subparsers.add_parser("setup", help="Configure a starter bundle")
    setup_parser.add_argument("bundle", choices=sorted(load_registry_definition().get("bundles", {}).keys()))
    setup_parser.add_argument("--skip-install-commands", action="store_true")
    setup_parser.add_argument("--secret", action="append", help="Provide manifest secret values as key=value")
    setup_parser.add_argument("--bot-token")
    setup_parser.add_argument("--admin-telegram-ids")
    setup_parser.add_argument("--telegram-gateway-mode", choices=["auto", "polling", "webhook"], default="auto")
    setup_parser.add_argument("--telegram-webhook-url")
    setup_parser.add_argument("--telegram-webhook-secret")
    setup_parser.add_argument("--spawner-ui-url", default="http://127.0.0.1:5173")
    setup_parser.set_defaults(func=cmd_setup)

    status_parser = subparsers.add_parser("status", help="Run module healthchecks")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_status)

    doctor_parser = subparsers.add_parser("doctor", help="Run diagnostic status and emit structured output")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=cmd_doctor)

    update_parser = subparsers.add_parser("update", help="Refresh installed modules from their current source paths")
    update_parser.add_argument("target", nargs="?")
    update_parser.add_argument("--skip-install-commands", action="store_true")
    update_parser.set_defaults(func=cmd_update)

    uninstall_parser = subparsers.add_parser("uninstall", help="Remove installed modules from Spark state and generated config")
    uninstall_parser.add_argument("target", nargs="?")
    uninstall_parser.add_argument("--force", action="store_true")
    uninstall_parser.set_defaults(func=cmd_uninstall)

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
