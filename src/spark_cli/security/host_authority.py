from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


HostActionClass = Literal["destructive_filesystem", "identity_access_mutation", "process_autostart_mutation", "remote_code_execution"]
HostRisk = Literal["high", "critical"]
PIP_EXECUTABLE_PATTERN = re.compile(r"pip(?:\d+(?:\.\d+)*)?$")
PYTHON_EXECUTABLE_PATTERN = re.compile(r"python(?:\d+(?:\.\d+)*)?$")


@dataclass(frozen=True)
class HostAuthority:
    action_class: HostActionClass
    risk: HostRisk
    reason: str
    target_display: str
    confirmation_phrase: str


def _command_word(value: str) -> str:
    word = value.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"\.(?:exe|cmd|bat)$", "", word)


def _segments(parts: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for part in parts:
        for chunk in re.split(r"(&&|\|\||[|;&])", part):
            if not chunk:
                continue
            if chunk in {"&&", "||", "|", ";", "&"}:
                if current:
                    segments.append(current)
                    current = []
            else:
                current.append(chunk)
    if current:
        segments.append(current)
    return segments


def _authority(
    action_class: HostActionClass,
    risk: HostRisk,
    reason: str,
    target: str,
    phrase: str,
) -> HostAuthority:
    return HostAuthority(action_class, risk, reason, target, phrase)


def _truncate_target(parts: list[str]) -> str:
    value_options = {"-r", "--reference", "-s", "--size"}
    index = 1
    targets: list[str] = []
    while index < len(parts):
        part = parts[index]
        if part in value_options:
            index += 2
            continue
        if any(part.startswith(f"{option}=") for option in value_options if option.startswith("--")):
            index += 1
            continue
        if part.startswith("-"):
            index += 1
            continue
        targets.append(part)
        index += 1
    return targets[0] if targets else ""


def _ip_action(parts: list[str]) -> tuple[str, str]:
    objects = {"addr", "address", "link", "maddress", "mroute", "neigh", "neighbour", "netns", "route", "rule", "tunnel", "tuntap", "xfrm"}
    for index, part in enumerate(parts[1:], start=1):
        lowered = part.lower()
        if lowered in objects:
            action = parts[index + 1].lower() if index + 1 < len(parts) else "show"
            return lowered, action
    return "", ""


def _package_install(words: list[str]) -> bool:
    executable = words[0]
    if PIP_EXECUTABLE_PATTERN.fullmatch(executable) and words[1:2] == ["install"]:
        return True
    if (executable == "py" or PYTHON_EXECUTABLE_PATTERN.fullmatch(executable)) and words[1:4] == ["-m", "pip", "install"]:
        return True
    if executable == "uv" and words[1:3] in (["pip", "install"], ["tool", "install"]):
        return True
    if executable in {"npm", "pnpm", "bun"} and len(words) > 1 and words[1] in {"add", "ci", "i", "install"}:
        return True
    return executable in {"yarn", "poetry", "pipenv"} and len(words) > 1 and words[1] in {"add", "install"}


def _package_runner(words: list[str]) -> bool:
    executable = words[0]
    return (
        executable == "uvx"
        or executable == "pipx"
        and words[1:2] == ["run"]
        or executable == "uv"
        and words[1:3] == ["tool", "run"]
    )


def _targets_device_path(parts: list[str]) -> bool:
    return any(
        re.search(r"(?i)(?:^|=)(?:/dev/(?:disk|sd|xvd|nvme|mapper/)|\\\\\.\\physicaldrive)", part)
        for part in parts
    )


def _disk_destruction(executable: str, lowered: list[str]) -> bool:
    arguments = lowered[1:]
    if executable.startswith("mkfs"):
        return True
    if executable in {"fdisk", "gdisk", "sfdisk"}:
        return _targets_device_path(arguments) and not any(part in {"-l", "--list"} for part in arguments)
    if executable == "parted":
        return _targets_device_path(arguments) and any(
            part in {"mklabel", "mkpart", "resizepart", "rm"} for part in arguments
        )
    if executable == "diskutil":
        return lowered[1:2] and lowered[1] in {"erasedisk", "erasevolume", "partitiondisk"}
    return executable == "dd" and any(
        part.startswith("of=") and _targets_device_path([part.split("=", 1)[1]]) for part in arguments
    )


def _tar_runs_command(lowered: list[str]) -> bool:
    return any(
        part == "--to-command"
        or part.startswith("--to-command=")
        or part.startswith("--checkpoint-action=exec=")
        for part in lowered[1:]
    )


def _deno_runs_with_authority(lowered: list[str]) -> bool:
    if lowered[1:2] != ["run"]:
        return False
    return any(
        re.match(r"(?i)^(?:https?://|jsr:|npm:)", part)
        or part == "-a"
        or part.startswith("--allow-")
        for part in lowered[2:]
    )


def _parse_segment(parts: list[str]) -> HostAuthority | None:
    if not parts:
        return None
    executable = _command_word(parts[0])
    lowered = [part.lower() for part in parts]
    words = [executable, *lowered[1:]]

    if _package_install(words):
        return _authority(
            "remote_code_execution",
            "high",
            "Package installation can fetch packages and run lifecycle or setup code.",
            "package install",
            "approve package install",
        )

    if _package_runner(words):
        return _authority(
            "remote_code_execution",
            "high",
            "An ephemeral package runner can download package code and execute it.",
            "package runner",
            "approve package runner execution",
        )

    if executable in {"chmod", "chgrp", "chown"}:
        target = next((part for part in reversed(parts[1:]) if not part.startswith("-")), executable)
        return _authority(
            "destructive_filesystem",
            "high",
            "Permission or ownership changes can expose data or change who controls execution.",
            target,
            "approve permission change",
        )

    if _disk_destruction(executable, lowered):
        return _authority(
            "destructive_filesystem",
            "critical",
            "The command can erase, format, repartition, or overwrite disk or device data.",
            " ".join(parts[:4]),
            "approve disk destruction",
        )

    if executable in {"shred", "srm", "wipe"} and not any(
        part in {"-h", "--help", "--version"} for part in lowered[1:]
    ):
        return _authority(
            "destructive_filesystem",
            "critical",
            "The command can securely overwrite or remove local files.",
            " ".join(parts[:3]),
            "approve file wipe",
        )

    if executable == "tar" and _tar_runs_command(lowered):
        return _authority(
            "remote_code_execution",
            "high",
            "Tar can execute another command while processing archive entries.",
            "tar command execution",
            "approve tar execution",
        )

    if executable == "pm2" and len(lowered) > 1 and lowered[1] in {"resurrect", "save", "startup", "unstartup"}:
        return _authority(
            "process_autostart_mutation",
            "high",
            "PM2 can install startup hooks or persist process resurrection state.",
            " ".join(parts[:2]),
            "approve pm2 startup change",
        )

    if executable == "deno" and _deno_runs_with_authority(lowered):
        return _authority(
            "remote_code_execution",
            "high",
            "Deno can fetch remote code or run code with explicit runtime permissions.",
            " ".join(parts[:4]),
            "approve deno execution",
        )

    if executable == "dd":
        target = next((part.split("=", 1)[1] for part in parts[1:] if part.lower().startswith("of=") and part.split("=", 1)[1]), "")
        if target:
            return _authority("destructive_filesystem", "critical", "dd can overwrite an arbitrary local path.", target, "approve raw file overwrite")

    if executable == "tee":
        targets = [part for part in parts[1:] if not part.startswith("-") and part.lower() not in {"warn", "warn-nopipe", "exit", "exit-nopipe"}]
        if targets:
            return _authority("destructive_filesystem", "high", "tee can write or append command input to a local path.", targets[0], "approve tee file write")

    if executable == "truncate":
        target = _truncate_target(parts)
        if target:
            return _authority("destructive_filesystem", "high", "truncate can resize or erase a local file.", target, "approve file truncation")

    if executable in {"nc", "ncat", "netcat"}:
        exec_flag = any(
            part in {"-c", "-e", "--exec", "--sh-exec"}
            or part.startswith(("--exec=", "--sh-exec="))
            or (part.startswith("-") and not part.startswith("--") and bool(set(part[1:]) & {"c", "e"}))
            for part in lowered[1:]
        )
        if exec_flag:
            return _authority("remote_code_execution", "critical", "Netcat can execute a command through a network connection.", executable, "approve remote shell")

    if executable == "socat" and any("exec:" in part or "system:" in part for part in lowered[1:]):
        return _authority("remote_code_execution", "critical", "socat can relay an EXEC or SYSTEM command over a network endpoint.", "socat EXEC/SYSTEM", "approve socat execution")

    if executable == "crontab":
        read_only = any(part in {"-l", "--list", "-t", "--test"} for part in lowered[1:])
        mutating = any(part in {"-e", "--edit", "-r", "--remove"} for part in lowered[1:])
        if not read_only or mutating:
            return _authority("process_autostart_mutation", "high", "crontab can install, edit, or remove persistent scheduled commands.", "crontab", "approve crontab change")

    if executable in {"at", "atrm"}:
        if executable == "atrm" or not any(part in {"-c", "--cat", "-l", "--list"} for part in lowered[1:]):
            return _authority("process_autostart_mutation", "high", "at can schedule or remove deferred command execution.", executable, "approve scheduled execution")

    if executable in {"iptables-restore", "ip6tables-restore"}:
        return _authority("identity_access_mutation", "critical", "Restoring firewall rules changes host network isolation.", executable, "approve firewall policy change")

    if executable in {"iptables", "ip6tables"}:
        read_only = any(part in {"-c", "--check", "-l", "--list", "-s", "--list-rules"} for part in lowered[1:])
        help_only = not parts[1:] or any(part in {"-h", "--help", "--version"} for part in lowered[1:]) or "-V" in parts[1:]
        if not read_only and not help_only:
            return _authority("identity_access_mutation", "critical", "Firewall rule changes can alter or disable host network isolation.", executable, "approve firewall policy change")

    if executable == "nft" and len(parts) > 1 and lowered[1] not in {"describe", "help", "list", "monitor", "--help", "--version"}:
        return _authority("identity_access_mutation", "critical", "nft can change or flush host firewall policy.", "nft", "approve firewall policy change")

    if executable == "ufw" and len(parts) > 1 and lowered[1] not in {"help", "show", "status", "version", "--help", "--version"}:
        return _authority("identity_access_mutation", "critical", "ufw can change or disable host firewall policy.", "ufw", "approve firewall policy change")

    if executable == "sysctl":
        mutating = any(part in {"-p", "--load", "--system", "-w", "--write"} or ("=" in part and not part.startswith("--")) for part in lowered[1:])
        if mutating:
            return _authority("identity_access_mutation", "high", "sysctl can change live kernel and security policy.", "sysctl", "approve kernel policy change")

    if executable == "ip":
        ip_object, action = _ip_action(parts)
        if ip_object and action in {"add", "append", "change", "del", "delete", "flush", "replace", "set"}:
            return _authority("identity_access_mutation", "high", "ip can change host interfaces, addresses, routes, or network namespaces.", f"ip {ip_object} {action}", "approve host network change")

    return None


def parse_host_authority(parts: list[str]) -> HostAuthority | None:
    for segment in _segments(parts):
        authority = _parse_segment(segment)
        if authority is not None:
            return authority
    return None


def decide_host_authority(parts: list[str], context: Any, decision_factory: Callable[..., Any]) -> Any:
    authority = parse_host_authority(parts)
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
