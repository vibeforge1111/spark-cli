from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


ContainerActionClass = Literal[
    "container_privilege_escalation",
    "credential_mutation",
    "destructive_filesystem",
    "external_publish",
    "identity_access_mutation",
    "remote_code_execution",
]
ContainerRisk = Literal["high", "critical"]


@dataclass(frozen=True)
class ContainerAuthority:
    action_class: ContainerActionClass
    risk: ContainerRisk
    reason: str
    target_display: str
    confirmation_phrase: str


@dataclass(frozen=True)
class RuntimeCommand:
    executable: str
    lane: Literal["docker", "podman", "compose"]
    arguments: tuple[str, ...]


DOCKER_GLOBAL_VALUE_OPTIONS = frozenset(
    {"--config", "--context", "-c", "--host", "-H", "--log-level", "-l", "--tlscacert", "--tlscert", "--tlskey"}
)
PODMAN_GLOBAL_VALUE_OPTIONS = frozenset(
    {
        "--connection",
        "-c",
        "--events-backend",
        "--hooks-dir",
        "--identity",
        "--log-level",
        "--module",
        "--namespace",
        "--network-cmd-path",
        "--network-config-dir",
        "--registries-conf",
        "--root",
        "--runroot",
        "--runtime",
        "--storage-driver",
        "--tmpdir",
        "--url",
    }
)
COMPOSE_GLOBAL_VALUE_OPTIONS = frozenset(
    {"--ansi", "--env-file", "-f", "--file", "--parallel", "-p", "--profile", "--project-directory", "--project-name"}
)
PRUNE_OBJECTS = frozenset({"builder", "buildx", "container", "image", "network", "system", "volume"})
CONTEXT_MUTATIONS = frozenset({"create", "import", "remove", "rm", "update", "use"})
COMPOSE_START_ACTIONS = frozenset({"restart", "start", "up"})
COMPOSE_DESTRUCTIVE_ACTIONS = frozenset({"down", "kill", "rm", "stop"})
CONTAINER_SPEC_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*:")
WINDOWS_PATH_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
SENSITIVE_HOST_SOURCES = (
    "/",
    "/home",
    "/root",
    "/run/docker.sock",
    "/run/podman/podman.sock",
    "/users",
    "/var/run/docker.sock",
    "/var/run/podman/podman.sock",
)


def _command_word(value: str) -> str:
    normalized = value.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    match = re.match(r"[a-z][a-z0-9_.-]*", normalized)
    if not match:
        return ""
    return re.sub(r"\.(?:exe|cmd|bat)$", "", match.group(0))


def _split_option(part: str) -> tuple[str, str]:
    if part.startswith("--") and "=" in part:
        return part.split("=", 1)
    return part, ""


def _strip_leading_options(arguments: list[str], value_options: frozenset[str]) -> list[str]:
    index = 0
    while index < len(arguments):
        part = arguments[index]
        if part == "--":
            return arguments[index + 1 :]
        if not part.startswith("-") or part == "-":
            return arguments[index:]
        name, attached = _split_option(part)
        if name in value_options:
            if attached:
                index += 1
            elif index + 1 < len(arguments):
                index += 2
            else:
                return []
            continue
        if len(part) > 2 and part[:2] in value_options and not part.startswith("--"):
            index += 1
            continue
        index += 1
    return []


def _runtime_command(parts: list[str]) -> RuntimeCommand | None:
    if not parts:
        return None
    executable = _command_word(parts[0])
    if executable == "docker":
        arguments = _strip_leading_options(parts[1:], DOCKER_GLOBAL_VALUE_OPTIONS)
        if not arguments:
            return RuntimeCommand(executable, "docker", ())
        if arguments[0].lower() == "compose":
            compose = _strip_leading_options(arguments[1:], COMPOSE_GLOBAL_VALUE_OPTIONS)
            return RuntimeCommand(executable, "compose", tuple(compose))
        return RuntimeCommand(executable, "docker", tuple(arguments))
    if executable == "podman":
        arguments = _strip_leading_options(parts[1:], PODMAN_GLOBAL_VALUE_OPTIONS)
        return RuntimeCommand(executable, "podman", tuple(arguments))
    if executable == "docker-compose":
        arguments = _strip_leading_options(parts[1:], COMPOSE_GLOBAL_VALUE_OPTIONS)
        return RuntimeCommand(executable, "compose", tuple(arguments))
    return None


def _lower(arguments: tuple[str, ...]) -> list[str]:
    return [argument.lower() for argument in arguments]


def _has_option(arguments: tuple[str, ...], names: frozenset[str]) -> bool:
    for argument in arguments:
        lowered = argument.lower()
        name = lowered.split("=", 1)[0]
        if name in names:
            return True
    return False


def _option_values(arguments: tuple[str, ...], names: frozenset[str]) -> list[str]:
    values: list[str] = []
    lowered = _lower(arguments)
    for index, part in enumerate(lowered):
        if "=" in part:
            name, value = part.split("=", 1)
            if name in names:
                values.append(value)
        elif part in names and index + 1 < len(arguments):
            values.append(arguments[index + 1])
        elif len(part) > 2 and part[:2] in names and not part.startswith("--"):
            values.append(arguments[index][2:])
    return values


def _authority(
    action_class: ContainerActionClass,
    risk: ContainerRisk,
    reason: str,
    target: str,
    phrase: str,
) -> ContainerAuthority:
    return ContainerAuthority(action_class, risk, reason, target, phrase)


def _prune_authority(command: RuntimeCommand) -> ContainerAuthority | None:
    arguments = _lower(command.arguments)
    if command.lane not in {"docker", "podman"} or len(arguments) < 2:
        return None
    object_name = arguments[0]
    if object_name not in PRUNE_OBJECTS or arguments[1] != "prune":
        return None
    critical = object_name in {"system", "volume"} or "--volumes" in arguments
    runtime = command.lane
    return _authority(
        "destructive_filesystem",
        "critical" if critical else "high",
        f"{runtime.title()} prune can remove local containers, images, volumes, networks, or build cache data.",
        f"{runtime} {object_name} prune",
        f"approve {runtime} prune",
    )


def _image_removal_authority(command: RuntimeCommand) -> ContainerAuthority | None:
    arguments = _lower(command.arguments)
    if command.lane in {"docker", "podman"}:
        if not arguments:
            return None
        removes = arguments[0] == "rmi" or arguments[:2] in (["image", "rm"], ["image", "remove"])
        if not removes:
            return None
        runtime = command.lane
        return _authority(
            "destructive_filesystem",
            "high",
            f"{runtime.title()} image removal can delete local container images.",
            f"{runtime} images",
            f"approve {runtime} image removal",
        )
    if command.lane == "compose" and arguments[:1] == ["down"] and _has_option(command.arguments, frozenset({"--rmi"})):
        return _authority(
            "destructive_filesystem",
            "high",
            "Compose down can remove local container images when --rmi is present.",
            "compose images",
            "approve docker image removal",
        )
    return None


def _registry_authority(command: RuntimeCommand) -> ContainerAuthority | None:
    arguments = _lower(command.arguments)
    if command.lane not in {"docker", "podman"} or not arguments:
        return None
    if arguments[0] in {"login", "logout"}:
        return _authority(
            "credential_mutation",
            "high",
            "Container registry authentication can store, change, or remove credentials.",
            f"{command.lane} {arguments[0]}",
            "approve docker credential change",
        )
    if arguments[0] == "push":
        return _authority(
            "external_publish",
            "high",
            "Container image push can publish an artifact to an external registry.",
            f"{command.lane} push",
            "approve publish",
        )
    return None


def _host_source(value: str) -> str:
    normalized = value.strip().lower().replace("\\", "/")
    if "source=" in normalized or "src=" in normalized:
        for field in normalized.split(","):
            if field.startswith(("source=", "src=")):
                return field.split("=", 1)[1].rstrip("/") or "/"
    if WINDOWS_PATH_PATTERN.match(value):
        match = re.match(r"^[A-Za-z]:[\\/][^:]*", value)
        return (match.group(0) if match else value).replace("\\", "/").lower().rstrip("/")
    return normalized.split(":", 1)[0].rstrip("/") or "/"


def _sensitive_host_source(value: str) -> bool:
    source = _host_source(value)
    return any(source == item or source.startswith(item.rstrip("/") + "/") for item in SENSITIVE_HOST_SOURCES)


def _privilege_authority(command: RuntimeCommand) -> ContainerAuthority | None:
    if command.lane not in {"docker", "podman"}:
        return None
    arguments = command.arguments
    lowered = _lower(arguments)
    direct = _has_option(arguments, frozenset({"--privileged", "--device", "--cap-add"}))
    host_namespaces = any(
        value.lower() == "host"
        for value in _option_values(arguments, frozenset({"--network", "--pid", "--ipc", "--uts", "--userns"}))
    )
    unconfined = any("unconfined" in value.lower() for value in _option_values(arguments, frozenset({"--security-opt"})))
    host_mount = any(
        _sensitive_host_source(value)
        for value in _option_values(arguments, frozenset({"-v", "--volume", "--mount"}))
    )
    if not (direct or host_namespaces or unconfined or host_mount or "--network=host" in lowered):
        return None
    return _authority(
        "container_privilege_escalation",
        "critical",
        "Container command can expose host namespaces, devices, sockets, sensitive paths, or privileged capabilities.",
        " ".join((command.executable, *command.arguments[:3])),
        "approve container privilege",
    )


def _context_authority(command: RuntimeCommand) -> ContainerAuthority | None:
    arguments = _lower(command.arguments)
    if command.lane != "docker" or len(arguments) < 2 or arguments[0] != "context":
        return None
    if arguments[1] not in CONTEXT_MUTATIONS:
        return None
    return _authority(
        "identity_access_mutation",
        "high",
        "Docker context mutation can change the daemon endpoint used by future container operations.",
        " ".join(("docker", *command.arguments[:3])),
        "approve docker context change",
    )


def _looks_container_spec(value: str) -> bool:
    return not bool(WINDOWS_PATH_PATTERN.match(value)) and bool(CONTAINER_SPEC_PATTERN.match(value)) and "://" not in value


def _copy_operands(arguments: tuple[str, ...], start: int, value_options: frozenset[str]) -> list[str]:
    operands: list[str] = []
    index = start
    while index < len(arguments):
        part = arguments[index]
        lowered = part.lower()
        if part == "--":
            operands.extend(arguments[index + 1 :])
            break
        name = lowered.split("=", 1)[0]
        if name in value_options:
            index += 1 if "=" in lowered else 2
            continue
        if part.startswith("-"):
            index += 1
            continue
        operands.append(part)
        index += 1
    return operands


def _copy_authority(command: RuntimeCommand) -> ContainerAuthority | None:
    arguments = _lower(command.arguments)
    start = -1
    value_options: frozenset[str] = frozenset()
    if command.lane in {"docker", "podman"}:
        if arguments[:1] == ["cp"]:
            start = 1
        elif arguments[:2] == ["container", "cp"]:
            start = 2
    elif command.lane == "compose" and arguments[:1] == ["cp"]:
        start = 1
        value_options = frozenset({"--index"})
    if start < 0:
        return None
    operands = _copy_operands(command.arguments, start, value_options)
    if len(operands) < 2 or _looks_container_spec(operands[-2]) or not _looks_container_spec(operands[-1]):
        return None
    return _authority(
        "remote_code_execution",
        "high",
        "Container copy can place local files into a running container or Compose service filesystem.",
        "container filesystem",
        "approve container file upload",
    )


def _build_action(command: RuntimeCommand) -> bool:
    arguments = _lower(command.arguments)
    return command.lane in {"docker", "podman"} and (
        arguments[:1] == ["build"] or arguments[:2] in (["buildx", "build"], ["builder", "build"])
    )


def _build_authority(command: RuntimeCommand) -> ContainerAuthority | None:
    if not _build_action(command):
        return None
    if _has_option(command.arguments, frozenset({"--secret", "--ssh"})):
        return _authority(
            "credential_mutation",
            "high",
            "Container build can forward local secrets or SSH agent credentials into the build environment.",
            "container build credentials",
            "approve docker build credential forwarding",
        )
    push = any(argument.lower() == "--push" for argument in command.arguments)
    push_values = [
        argument.split("=", 1)[1]
        for argument in command.arguments
        if argument.lower().startswith("--push=")
    ]
    push = push or any(value.lower() in {"1", "on", "true", "yes"} for value in push_values)
    outputs = _option_values(command.arguments, frozenset({"--output", "-o"}))
    publishes_output = any("type=registry" in value.lower() or "push=true" in value.lower() for value in outputs)
    if push or publishes_output:
        return _authority(
            "external_publish",
            "high",
            "Container build can publish a built image to an external registry.",
            "docker build publish",
            "approve docker build publish",
        )
    return None


def _execution_authority(command: RuntimeCommand) -> ContainerAuthority | None:
    arguments = _lower(command.arguments)
    if command.lane in {"docker", "podman"} and (
        arguments[:1] == ["exec"] or arguments[:2] == ["container", "exec"]
    ):
        return _authority(
            "container_privilege_escalation",
            "high",
            "Container exec runs a command inside an existing container with its mounts and capabilities.",
            "container exec",
            "approve container exec",
        )
    if command.lane != "compose" or not arguments:
        return None
    action = arguments[0]
    if action in {"exec", "run"}:
        return _authority(
            "remote_code_execution",
            "high",
            "Compose command can execute instructions inside a service container.",
            f"compose {action}",
            "approve compose command execution",
        )
    if action in COMPOSE_START_ACTIONS:
        return _authority(
            "remote_code_execution",
            "high",
            "Compose command can start or restart service containers from project configuration.",
            f"compose {action}",
            "approve compose service start",
        )
    if action in COMPOSE_DESTRUCTIVE_ACTIONS:
        return _authority(
            "destructive_filesystem",
            "high",
            "Compose command can stop, kill, or remove project containers and networks.",
            f"compose {action}",
            "approve compose service change",
        )
    return None


def parse_container_authority(parts: list[str]) -> ContainerAuthority | None:
    command = _runtime_command(parts)
    if command is None or not command.arguments:
        return None
    for parser in (
        _registry_authority,
        _prune_authority,
        _image_removal_authority,
        _context_authority,
        _copy_authority,
        _build_authority,
        _privilege_authority,
        _execution_authority,
    ):
        authority = parser(command)
        if authority is not None:
            return authority
    return None


def decide_container_authority(parts: list[str], context: Any, decision_factory: Callable[..., Any]) -> Any:
    authority = parse_container_authority(parts)
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
