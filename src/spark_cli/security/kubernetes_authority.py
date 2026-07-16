from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


KubernetesActionClass = Literal[
    "credential_mutation",
    "external_publish",
    "identity_access_mutation",
    "network_exfiltration",
    "remote_code_execution",
]
KubernetesRisk = Literal["high", "critical"]


@dataclass(frozen=True)
class KubernetesAuthority:
    action_class: KubernetesActionClass
    risk: KubernetesRisk
    reason: str
    target_display: str
    confirmation_phrase: str


@dataclass(frozen=True)
class ClusterCommand:
    executable: Literal["kubectl", "helm"]
    command: str
    arguments: tuple[str, ...]


KUBECTL_COMMANDS = frozenset(
    {
        "annotate", "api-resources", "api-versions", "apply", "attach", "auth", "autoscale",
        "certificate", "cluster-info", "completion", "config", "cordon", "cp", "create", "debug",
        "delete", "describe", "diff", "drain", "edit", "events", "exec", "explain", "expose", "get",
        "kustomize", "label", "logs", "options", "patch", "plugin", "port-forward", "proxy", "replace",
        "rollout", "run", "scale", "set", "taint", "top", "uncordon", "version", "wait",
    }
)
HELM_COMMANDS = frozenset(
    {
        "completion", "create", "dependency", "env", "get", "history", "install", "lint", "list",
        "package", "plugin", "pull", "push", "registry", "repo", "rollback", "search", "show", "status",
        "template", "test", "uninstall", "upgrade", "verify", "version",
    }
)
KUBECTL_GLOBAL_VALUE_OPTIONS = frozenset(
    {
        "--as", "--as-group", "--cache-dir", "--certificate-authority", "--client-certificate", "--client-key",
        "--cluster", "--context", "--kubeconfig", "--namespace", "-n", "--password", "--profile",
        "--profile-output", "--request-timeout", "--server", "-s", "--tls-server-name", "--token", "--user",
        "--username", "--vmodule",
    }
)
HELM_GLOBAL_VALUE_OPTIONS = frozenset(
    {
        "--burst-limit", "--kube-apiserver", "--kube-as-group", "--kube-as-user", "--kube-ca-file",
        "--kube-context", "--kube-token", "--kubeconfig", "--namespace", "-n", "--qps", "--registry-config",
        "--repository-cache", "--repository-config",
    }
)
COMMAND_VALUE_OPTIONS = frozenset(
    {
        "--address", "--as", "--as-group", "--cluster", "--container", "-c", "--context", "--dry-run", "-f",
        "--filename", "--kubeconfig", "--namespace", "-n", "--output", "-o", "--password", "--port",
        "--profile", "--request-timeout", "--retries", "--server", "-s", "--token", "--user", "--username",
    }
)
CONFIG_CONTEXT_ACTIONS = frozenset(
    {"delete-context", "rename-context", "set-cluster", "set-context", "unset", "use-context"}
)
WORKLOAD_ACTIONS = frozenset({"annotate", "label", "patch", "scale"})
ROLLOUT_MUTATIONS = frozenset({"pause", "restart", "resume", "undo"})
SET_MUTATIONS = frozenset({"env", "image", "resources", "selector", "serviceaccount", "subject"})
NODE_MUTATIONS = frozenset({"cordon", "drain", "taint", "uncordon"})
RESOURCE_MUTATIONS = frozenset({"autoscale", "edit", "expose", "replace"})
WINDOWS_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")


def _command_word(value: str) -> str:
    normalized = value.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    match = re.match(r"[a-z][a-z0-9_.-]*", normalized)
    if not match:
        return ""
    return re.sub(r"\.(?:exe|cmd|bat)$", "", match.group(0))


def _split_option(value: str) -> tuple[str, str]:
    if value.startswith("--") and "=" in value:
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
        # Unknown global-option values and plugin words cannot hide a later
        # built-in command from the authority classifier.
        index += 1
    return "", ()


def _cluster_command(parts: list[str]) -> ClusterCommand | None:
    if not parts:
        return None
    executable = _command_word(parts[0])
    if executable == "kubectl":
        command, arguments = _locate_command(parts[1:], KUBECTL_COMMANDS, KUBECTL_GLOBAL_VALUE_OPTIONS)
        return ClusterCommand("kubectl", command, arguments)
    if executable == "helm":
        command, arguments = _locate_command(parts[1:], HELM_COMMANDS, HELM_GLOBAL_VALUE_OPTIONS)
        return ClusterCommand("helm", command, arguments)
    return None


def _lower(arguments: tuple[str, ...]) -> list[str]:
    return [argument.lower() for argument in arguments]


def _has_option(arguments: tuple[str, ...], names: frozenset[str]) -> bool:
    return any(argument.lower().split("=", 1)[0] in names for argument in arguments)


def _option_value(arguments: tuple[str, ...], name: str) -> str:
    lowered = _lower(arguments)
    for index, part in enumerate(lowered):
        if part.startswith(name + "="):
            return part.split("=", 1)[1]
        if part == name and index + 1 < len(arguments) and not arguments[index + 1].startswith("-"):
            return arguments[index + 1].lower()
    return ""


def _positionals(arguments: tuple[str, ...]) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(arguments):
        part = arguments[index]
        lowered = part.lower()
        if lowered == "--":
            result.extend(arguments[index + 1 :])
            break
        name, attached = _split_option(lowered)
        if name in COMMAND_VALUE_OPTIONS:
            index += 1 if attached else 2
            continue
        if lowered.startswith("-"):
            index += 1
            continue
        result.append(part)
        index += 1
    return result


def _remote_copy_spec(value: str) -> bool:
    return ":" in value and not WINDOWS_PATH_PATTERN.match(value)


def _authority(
    action_class: KubernetesActionClass, risk: KubernetesRisk, reason: str, target: str, phrase: str
) -> KubernetesAuthority:
    return KubernetesAuthority(action_class, risk, reason, target, phrase)


def _kubectl_authority(command: ClusterCommand) -> KubernetesAuthority | None:
    action = command.command
    arguments = _lower(command.arguments)
    positionals = [value.lower() for value in _positionals(command.arguments)]
    subcommand = positionals[0] if positionals else ""

    if action == "config":
        if subcommand in {"delete-user", "set-credentials"}:
            return _authority(
                "credential_mutation", "high", "Kubernetes config can change or remove stored user credentials.",
                f"kubectl config {subcommand}", "approve kubernetes credential change",
            )
        if subcommand in CONFIG_CONTEXT_ACTIONS:
            return _authority(
                "identity_access_mutation", "high", "Kubernetes config can change cluster, context, or user routing.",
                f"kubectl config {subcommand}", "approve kubernetes context change",
            )
        if subcommand == "view" and "--raw" in arguments:
            return _authority(
                "credential_mutation", "critical", "Kubernetes config view --raw can reveal kubeconfig credentials.",
                "kubectl config view", "approve kubernetes secret read",
            )
        return None
    if action in {"get", "describe"} and subcommand in {"secret", "secrets"}:
        return _authority(
            "credential_mutation", "critical", "Kubernetes command can reveal cluster secrets.",
            f"kubectl {action} {subcommand}", "approve kubernetes secret read",
        )
    if action == "cp":
        copies = _positionals(command.arguments)
        if len(copies) >= 2 and not _remote_copy_spec(copies[0]) and _remote_copy_spec(copies[1]):
            return _authority(
                "external_publish", "high", "Kubernetes copy can upload local files into a cluster workload.",
                "kubectl cp", "approve kubernetes file upload",
            )
        return None
    if action == "exec":
        return _authority(
            "remote_code_execution", "high", "Kubernetes exec can run commands inside a cluster workload.",
            "kubectl exec", "approve kubernetes exec",
        )
    if action in {"debug", "attach"}:
        return _authority(
            "remote_code_execution", "high", "Kubernetes command can attach to a live process or start a debug container.",
            f"kubectl {action}", "approve kubernetes remote process",
        )
    if action == "run":
        if _option_value(command.arguments, "--dry-run") == "client":
            return None
        return _authority(
            "remote_code_execution", "high", "Kubernetes run can create a live pod and start container code.",
            "kubectl run", "approve kubernetes run",
        )
    if action in {"port-forward", "proxy"}:
        return _authority(
            "network_exfiltration", "high", "Kubernetes command can expose cluster services through a local listener.",
            f"kubectl {action}", "approve kubernetes network exposure",
        )
    if action == "auth" and subcommand == "reconcile":
        return _authority(
            "identity_access_mutation", "high", "Kubernetes auth reconcile can change live RBAC permissions.",
            "kubectl auth reconcile", "approve kubernetes access change",
        )
    if action == "certificate" and subcommand in {"approve", "deny"}:
        return _authority(
            "identity_access_mutation", "high", "Kubernetes certificate command can decide a signing request.",
            f"kubectl certificate {subcommand}", "approve kubernetes access change",
        )
    if action == "create":
        if subcommand in {"secret", "token"}:
            return _authority(
                "credential_mutation", "critical", "Kubernetes create can create or reveal credential material.",
                f"kubectl create {subcommand}", "approve kubernetes create",
            )
        if _option_value(command.arguments, "--dry-run") == "client":
            return None
        return _authority(
            "external_publish", "high", "Kubernetes create can mutate live cluster resources.",
            "kubectl create", "approve kubernetes create",
        )
    if action in WORKLOAD_ACTIONS or (action == "rollout" and subcommand in ROLLOUT_MUTATIONS) or (
        action == "set" and subcommand in SET_MUTATIONS
    ):
        return _authority(
            "external_publish", "high", "Kubernetes command can mutate live workload or rollout state.",
            f"kubectl {action}", "approve kubernetes workload change",
        )
    if action in NODE_MUTATIONS:
        return _authority(
            "external_publish", "high", "Kubernetes command can mutate node scheduling, eviction, or taint state.",
            f"kubectl {action}", "approve kubernetes node change",
        )
    if action in RESOURCE_MUTATIONS:
        if action != "edit" and _option_value(command.arguments, "--dry-run") == "client":
            return None
        return _authority(
            "external_publish", "high", "Kubernetes command can mutate live resources or service exposure.",
            f"kubectl {action}", "approve kubernetes resource change",
        )
    if action in {"apply", "delete"}:
        return _authority(
            "external_publish", "critical" if action == "delete" else "high",
            "Kubernetes command can mutate live infrastructure.", f"kubectl {action}", "approve infrastructure change",
        )
    return None


def _helm_authority(command: ClusterCommand) -> KubernetesAuthority | None:
    action = command.command
    positionals = [value.lower() for value in _positionals(command.arguments)]
    subcommand = positionals[0] if positionals else ""
    if action == "repo" and subcommand in {"add", "remove", "rm", "update"}:
        if subcommand == "add" and _has_option(
            command.arguments, frozenset({"--ca-file", "--cert-file", "--key-file", "--password", "--username"})
        ):
            return _authority(
                "credential_mutation", "high", "Helm repo add can store repository credentials or key material.",
                "helm repo add", "approve helm repo credential change",
            )
        return _authority(
            "identity_access_mutation", "high", "Helm repo command can change chart source routing or indexes.",
            f"helm repo {subcommand}", "approve helm repo change",
        )
    if action == "registry" and subcommand in {"login", "logout"}:
        return _authority(
            "credential_mutation", "high", "Helm registry command can store, change, or remove OCI credentials.",
            f"helm registry {subcommand}", "approve helm registry credential change",
        )
    if action in {"install", "rollback", "uninstall", "upgrade"}:
        return _authority(
            "external_publish", "high", "Helm command can mutate a live cluster release.",
            f"helm {action}", "approve infrastructure change",
        )
    if action == "push":
        return _authority(
            "external_publish", "high", "Helm push can publish a chart artifact.", "helm push", "approve publish",
        )
    return None


def decide_kubernetes_authority(
    parts: list[str], context: Any, decision_factory: Callable[..., Any]
) -> Any:
    command = _cluster_command(parts)
    if command is None or not command.command:
        return None
    authority = _kubectl_authority(command) if command.executable == "kubectl" else _helm_authority(command)
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
