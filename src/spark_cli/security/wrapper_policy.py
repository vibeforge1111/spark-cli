from __future__ import annotations

import re


TRANSPARENT_COMMAND_WRAPPERS = frozenset({"env", "nice", "nohup", "setsid", "stdbuf", "timeout"})
PROCESS_TRACE_WRAPPERS = frozenset({"ltrace", "strace"})
PROCESS_SCHEDULER_WRAPPERS = frozenset({"chrt", "ionice"})
DYNAMIC_LOADER_ENV_NAMES = frozenset(
    {
        "BASH_ENV",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "ENV",
        "GIT_SSH_COMMAND",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "NODE_OPTIONS",
        "PERL5OPT",
        "PYTHONPATH",
        "RUBYOPT",
    }
)


def _command_word(value: str) -> str:
    normalized = value.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    match = re.match(r"[a-z][a-z0-9_-]*", normalized.lstrip("&|;("))
    return match.group(0).removesuffix(".exe") if match else ""


def _is_env_assignment(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*", value))


def transparent_wrapper_command(parts: list[str]) -> tuple[list[str] | None, frozenset[str], bool]:
    wrapper = _command_word(parts[0]) if parts else ""
    index = 1
    env_names: set[str] = set()
    if wrapper == "env":
        value_options = {"-C", "-S", "-u", "--chdir", "--split-string", "--unset"}
        flag_options = {"-0", "-i", "-v", "--debug", "--ignore-environment", "--null"}
        while index < len(parts):
            part = parts[index]
            if part in value_options:
                if index + 1 >= len(parts):
                    return None, frozenset(env_names), False
                index += 2
                continue
            if any(part.startswith(f"{option}=") for option in value_options if option.startswith("--")):
                index += 1
                continue
            if part in flag_options:
                index += 1
                continue
            if _is_env_assignment(part):
                env_names.add(part.split("=", 1)[0].upper())
                index += 1
                continue
            if part.startswith("-"):
                return None, frozenset(env_names), False
            break
    elif wrapper == "nohup":
        if len(parts) == 2 and parts[1] in {"--help", "--version"}:
            return [], frozenset(), True
        if index < len(parts) and parts[index].startswith("-"):
            return None, frozenset(), False
    elif wrapper == "timeout":
        value_options = {"-k", "-s", "--kill-after", "--signal"}
        flag_options = {"--foreground", "--preserve-status", "--verbose"}
        while index < len(parts):
            part = parts[index]
            if part in value_options:
                if index + 1 >= len(parts):
                    return None, frozenset(), False
                index += 2
                continue
            if any(part.startswith(f"{option}=") for option in value_options if option.startswith("--")):
                index += 1
                continue
            if part in flag_options:
                index += 1
                continue
            break
        if index >= len(parts) or not re.fullmatch(r"(?i)(?:\d+(?:\.\d+)?[smhd]?|inf)", parts[index]):
            return None, frozenset(), False
        index += 1
    elif wrapper == "nice":
        if index < len(parts) and parts[index] in {"-n", "--adjustment"}:
            if index + 1 >= len(parts):
                return None, frozenset(), False
            index += 2
        elif index < len(parts) and (
            parts[index].startswith("--adjustment=") or re.fullmatch(r"-\d+", parts[index])
        ):
            index += 1
        elif index < len(parts) and parts[index].startswith("-"):
            return None, frozenset(), False
    elif wrapper == "setsid":
        allowed = {"-c", "-f", "-w", "--ctty", "--fork", "--wait"}
        while index < len(parts) and parts[index] in allowed:
            index += 1
        if index < len(parts) and parts[index].startswith("-"):
            return None, frozenset(), False
    elif wrapper == "stdbuf":
        while index < len(parts):
            part = parts[index]
            if re.fullmatch(r"-[ioe].+", part) or any(
                part.startswith(prefix) for prefix in ("--input=", "--output=", "--error=")
            ):
                index += 1
                continue
            if part in {"-i", "-o", "-e", "--input", "--output", "--error"}:
                if index + 1 >= len(parts):
                    return None, frozenset(), False
                index += 2
                continue
            if part.startswith("-"):
                return None, frozenset(), False
            break
    else:
        return None, frozenset(), False
    return (parts[index:] or None), frozenset(env_names), False
