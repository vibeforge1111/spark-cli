from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


InfrastructureActionClass = Literal[
    "credential_mutation",
    "external_publish",
    "identity_access_mutation",
    "remote_code_execution",
]
InfrastructureRisk = Literal["high", "critical"]


@dataclass(frozen=True)
class InfrastructureAuthority:
    action_class: InfrastructureActionClass
    risk: InfrastructureRisk
    reason: str
    target_display: str
    confirmation_phrase: str


@dataclass(frozen=True)
class InfrastructureCommand:
    executable: str
    command: str
    arguments: tuple[str, ...]


TERRAFORM_COMMANDS = frozenset(
    {
        "apply", "console", "destroy", "env", "fmt", "force-unlock", "get", "graph", "import", "init",
        "login", "logout", "metadata", "output", "plan", "providers", "refresh", "show", "state", "taint",
        "test", "untaint", "validate", "version", "workspace",
    }
)
PULUMI_COMMANDS = frozenset(
    {
        "about", "ai", "cancel", "config", "console", "convert", "destroy", "env", "gen-completion", "import",
        "install", "login", "logout", "new", "org", "package", "plugin", "policy", "preview", "refresh",
        "schema", "stack", "state", "up", "version", "watch", "whoami",
    }
)
TERRAFORM_GLOBAL_VALUE_OPTIONS = frozenset({"-chdir"})
PULUMI_GLOBAL_VALUE_OPTIONS = frozenset(
    {
        "--color", "--cwd", "-C", "--emoji", "--logflow", "--logtostderr", "--profiling", "--stack",
        "--tracing", "--verbose", "-v",
    }
)
TERRAFORM_STATE_MUTATIONS = frozenset({"mv", "push", "replace-provider", "rm"})
PULUMI_CONFIG_MUTATIONS = frozenset({"cp", "refresh", "rm", "rm-all", "set", "set-all"})
PULUMI_STACK_ROUTING = frozenset({"init", "remove", "rename", "rm", "select"})
ANSIBLE_PLAYBOOK_INSPECTION = frozenset({"--help", "-h", "--list-hosts", "--list-tags", "--list-tasks", "--syntax-check", "--version"})
ANSIBLE_VAULT_SECRET_ACTIONS = frozenset(
    {"create", "decrypt", "edit", "encrypt", "encrypt_string", "rekey", "view"}
)


def _command_word(value: str) -> str:
    normalized = value.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    match = re.match(r"[a-z][a-z0-9_.-]*", normalized)
    if not match:
        return ""
    return re.sub(r"\.(?:exe|cmd|bat)$", "", match.group(0))


def _split_option(value: str) -> tuple[str, str]:
    if "=" in value:
        return value.split("=", 1)
    return value, ""


def _locate_command(
    arguments: list[str], commands: frozenset[str], value_options: frozenset[str]
) -> tuple[str, tuple[str, ...]]:
    index = 0
    while index < len(arguments):
        lowered = arguments[index].lower()
        if lowered == "--":
            index += 1
            continue
        name, attached = _split_option(lowered)
        if name in value_options:
            index += 1 if attached else 2
            continue
        if lowered.startswith("-"):
            index += 1
            continue
        if lowered in commands:
            return lowered, tuple(arguments[index + 1 :])
        index += 1
    return "", ()


def _infrastructure_command(parts: list[str]) -> InfrastructureCommand | None:
    if not parts:
        return None
    executable = _command_word(parts[0])
    if executable == "terraform":
        command, arguments = _locate_command(parts[1:], TERRAFORM_COMMANDS, TERRAFORM_GLOBAL_VALUE_OPTIONS)
        return InfrastructureCommand(executable, command, arguments)
    if executable == "pulumi":
        command, arguments = _locate_command(parts[1:], PULUMI_COMMANDS, PULUMI_GLOBAL_VALUE_OPTIONS)
        return InfrastructureCommand(executable, command, arguments)
    if executable in {"ansible", "ansible-inventory", "ansible-playbook", "ansible-vault"}:
        return InfrastructureCommand(executable, "", tuple(parts[1:]))
    return None


def _lower(arguments: tuple[str, ...]) -> list[str]:
    return [argument.lower() for argument in arguments]


def _authority(
    action_class: InfrastructureActionClass,
    risk: InfrastructureRisk,
    reason: str,
    target: str,
    phrase: str,
) -> InfrastructureAuthority:
    return InfrastructureAuthority(action_class, risk, reason, target, phrase)


def _terraform_authority(command: InfrastructureCommand) -> InfrastructureAuthority | None:
    action = command.command
    arguments = _lower(command.arguments)
    subcommand = arguments[0] if arguments else ""
    if action in {"login", "logout"}:
        return _authority(
            "credential_mutation", "high", "Terraform can store, change, or remove Terraform Cloud credentials.",
            f"terraform {action}", "approve terraform credential change",
        )
    if action == "workspace" and subcommand in {"delete", "new", "select"}:
        return _authority(
            "identity_access_mutation", "high",
            "Terraform workspace routing can create, change, or remove the state targeted by future operations.",
            f"terraform workspace {subcommand}", "approve terraform workspace change",
        )
    if action in {"import", "taint", "untaint", "force-unlock"} or (
        action == "state" and subcommand in TERRAFORM_STATE_MUTATIONS
    ):
        return _authority(
            "external_publish", "high",
            "Terraform can mutate resource bindings, lifecycle state, locks, or remote backend state.",
            f"terraform {action} {subcommand}".strip(), "approve terraform state change",
        )
    if action == "state" and subcommand in {"pull", "show"}:
        return _authority(
            "credential_mutation", "critical", "Terraform state can contain plaintext credentials and secret values.",
            f"terraform state {subcommand}", "approve terraform secret read",
        )
    if action == "show":
        return _authority(
            "credential_mutation", "critical", "Terraform show can render secret-bearing plan or state values in plaintext.",
            "terraform show", "approve terraform secret read",
        )
    if action == "output" and any(argument.split("=", 1)[0] in {"-json", "-raw"} for argument in arguments):
        return _authority(
            "credential_mutation", "critical", "Terraform raw or JSON output can reveal sensitive output values.",
            "terraform output", "approve terraform secret read",
        )
    return None


def _pulumi_authority(command: InfrastructureCommand) -> InfrastructureAuthority | None:
    action = command.command
    arguments = _lower(command.arguments)
    subcommand = arguments[0] if arguments else ""
    if action in {"login", "logout"}:
        return _authority(
            "credential_mutation", "high", "Pulumi can store, change, or remove backend credentials.",
            f"pulumi {action}", "approve pulumi credential change",
        )
    if action == "stack" and subcommand in PULUMI_STACK_ROUTING:
        return _authority(
            "identity_access_mutation", "high",
            "Pulumi stack routing can create, change, rename, or remove the stack targeted by future operations.",
            f"pulumi stack {subcommand}", "approve pulumi stack change",
        )
    if action == "stack" and subcommand == "change-secrets-provider":
        return _authority(
            "credential_mutation", "high", "Pulumi can rotate the provider protecting stack secrets.",
            "pulumi stack change-secrets-provider", "approve pulumi config change",
        )
    if action == "config" and subcommand in PULUMI_CONFIG_MUTATIONS:
        return _authority(
            "credential_mutation", "high", "Pulumi can store, copy, refresh, change, or remove stack configuration.",
            f"pulumi config {subcommand}", "approve pulumi config change",
        )
    if (action == "config" and subcommand == "get") or (
        action in {"config", "stack"} and "--show-secrets" in arguments
    ):
        return _authority(
            "credential_mutation", "critical", "Pulumi can decrypt or reveal stack secret values.",
            f"pulumi {action} {subcommand}".strip(), "approve pulumi secret reveal",
        )
    return None


def _ansible_authority(command: InfrastructureCommand) -> InfrastructureAuthority | None:
    executable = command.executable
    arguments = _lower(command.arguments)
    if executable == "ansible-vault":
        action = next((argument for argument in arguments if not argument.startswith("-")), "")
        if action in ANSIBLE_VAULT_SECRET_ACTIONS:
            return _authority(
                "credential_mutation", "critical", "Ansible Vault can reveal, decrypt, create, or mutate encrypted secrets.",
                f"ansible-vault {action}", "approve ansible vault secret access",
            )
        return None
    if executable == "ansible-inventory" and any(option in arguments for option in {"--host", "--list"}):
        return _authority(
            "credential_mutation", "critical", "Ansible inventory output can reveal secret-bearing host and group variables.",
            "ansible-inventory", "approve ansible inventory secret read",
        )
    if executable == "ansible-playbook":
        if any(option in arguments for option in ANSIBLE_PLAYBOOK_INSPECTION):
            return None
        return _authority(
            "remote_code_execution", "high", "Ansible playbooks can execute tasks against inventory hosts.",
            "ansible-playbook", "approve ansible execution",
        )
    if executable == "ansible":
        if not arguments or any(option in arguments for option in {"--help", "-h", "--version"}):
            return None
        return _authority(
            "remote_code_execution", "high", "Ansible ad-hoc commands execute modules against inventory hosts.",
            "ansible", "approve ansible execution",
        )
    return None


def decide_infrastructure_authority(
    parts: list[str], context: Any, decision_factory: Callable[..., Any]
) -> Any:
    command = _infrastructure_command(parts)
    if command is None:
        return None
    if command.executable == "terraform":
        authority = _terraform_authority(command)
    elif command.executable == "pulumi":
        authority = _pulumi_authority(command)
    else:
        authority = _ansible_authority(command)
    if authority is None:
        return None
    return decision_factory(
        parts,
        context,
        authority.action_class,
        authority.risk,
        authority.reason,
        target_display=authority.target_display,
        confirmation_phrase=authority.confirmation_phrase,
    )
