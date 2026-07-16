from __future__ import annotations

import hashlib
import re
import shlex
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal


ApprovalClass = Literal[
    "none",
    "destructive_filesystem",
    "git_history_mutation",
    "credential_mutation",
    "external_publish",
    "process_autostart_mutation",
    "network_exfiltration",
    "remote_code_execution",
    "container_privilege_escalation",
    "identity_access_mutation",
    "high_cost_execution",
]
ApprovalRisk = Literal["none", "low", "medium", "high", "critical"]


@dataclass(frozen=True)
class CommandContext:
    surface: str = "cli"
    hosted: bool = False
    non_interactive: bool = False


@dataclass(frozen=True)
class ApprovalDecision:
    action_class: ApprovalClass
    risk: ApprovalRisk
    requires_approval: bool
    approval_mode: str
    reason: str
    target_display: str
    command_digest: str
    confirmation_phrase: str
    surface: str = "cli"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class OsStartupAction:
    executable: str
    action: str
    read_only: bool


TransferDirection = Literal["upload", "download", "remote", "local", "read"]


@dataclass(frozen=True)
class OutboundTransferAction:
    transport: str
    direction: TransferDirection
    target: str


PublishKind = Literal["source", "package", "image", "chart", "hosted", "database"]


@dataclass(frozen=True)
class ExternalPublishAction:
    kind: PublishKind
    executable: str
    action: str


@dataclass(frozen=True)
class ExternalPublishRule:
    executables: frozenset[str]
    prefix: tuple[str, ...]
    kind: PublishKind


SECRET_LIKE_PATTERN = re.compile(
    r"(?i)(sk-[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|\d{5,}:[A-Za-z0-9_-]{20,})"
)
INVALID_COMMAND_TOKEN = "<spark-invalid-command>"
INVALID_COMMAND_REASON = "Command input could not be validated as an ordered sequence of text tokens."
SENSITIVE_ENV_NAME_PATTERN = re.compile(
    r"(?i)(?:^|[_-])(?:token|secret|api[_-]?key|password|passwd|credential|auth)(?:$|[_-])"
)


def _digest_command(argv: list[str]) -> str:
    redacted = [SECRET_LIKE_PATTERN.sub("[REDACTED]", part) for part in argv]
    return hashlib.sha256("\0".join(redacted).encode("utf-8")).hexdigest()


def _lower_parts(argv: list[str]) -> list[str]:
    return [part.lower() for part in argv]


def _contains_any(parts: list[str], values: set[str]) -> bool:
    return any(part in values for part in parts)


def _target_after(parts: list[str], command_names: set[str]) -> str:
    for index, part in enumerate(parts):
        if part.lower() in command_names and index + 1 < len(parts):
            for candidate in parts[index + 1 :]:
                if not candidate.startswith("-"):
                    return candidate
    return ""


def _has_option_value(parts: list[str], option_names: set[str], suspicious_values: set[str]) -> bool:
    lowered = _lower_parts(parts)
    for index, part in enumerate(lowered):
        value = ""
        if "=" in part:
            name, value = part.split("=", 1)
            if name not in option_names:
                continue
        elif part in option_names and index + 1 < len(lowered):
            value = lowered[index + 1]
        else:
            continue
        normalized = value.replace("\\", "/").rstrip("/")
        if (
            normalized in suspicious_values
            or any(normalized.startswith(item.rstrip("/") + "/") for item in suspicious_values)
            or any(f"source={item}" in normalized or f"src={item}" in normalized or f"{item}:" in normalized for item in suspicious_values)
        ):
            return True
    return False


def _is_env_assignment(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*", value))


def _looks_like_sensitive_env_name(value: str) -> bool:
    return bool(SENSITIVE_ENV_NAME_PATTERN.search(value))


def _looks_like_npm_auth_key(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in {"_authtoken", "auth-token", "auth_token"})


def _command_word(value: str) -> str:
    normalized = value.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    normalized = normalized.lstrip("&|;(")
    match = re.match(r"[a-z][a-z0-9_-]*", normalized)
    if not match:
        return ""
    word = match.group(0)
    return word.removesuffix(".exe")


OS_STARTUP_EXECUTABLES = frozenset({"launchctl", "reg", "schtasks", "setx", "systemctl"})
SYSTEMCTL_READ_ONLY_ACTIONS = frozenset(
    {"is-active", "is-enabled", "list-unit-files", "list-units", "show", "status"}
)
SYSTEMCTL_READ_ONLY_PREFIX_OPTIONS = frozenset(
    {
        "--all",
        "--full",
        "--global",
        "--no-ask-password",
        "--no-block",
        "--no-legend",
        "--no-pager",
        "--plain",
        "--quiet",
        "--runtime",
        "--system",
        "--user",
        "-a",
        "-l",
        "-q",
    }
)
SCHTASKS_ACTION_SWITCHES = frozenset({"/change", "/create", "/delete", "/end", "/query", "/run"})
SHELL_CONTROL_MARKERS = ("&&", "||", "|", ";", "&")


def _has_shell_control_syntax(parts: list[str]) -> bool:
    return any(any(marker in part for marker in SHELL_CONTROL_MARKERS) for part in parts)


def _parse_os_startup_action(parts: list[str]) -> OsStartupAction | None:
    if not parts:
        return None
    executable = _command_word(parts[0])
    if executable not in OS_STARTUP_EXECUTABLES:
        return None
    lowered = _lower_parts(parts)
    if _has_shell_control_syntax(parts):
        return OsStartupAction(executable=executable, action="composed", read_only=False)

    if executable == "reg":
        action = lowered[1] if len(lowered) > 1 else ""
        return OsStartupAction(executable=executable, action=action, read_only=action == "query")

    if executable == "schtasks":
        actions = sorted(SCHTASKS_ACTION_SWITCHES.intersection(lowered[1:]))
        action = "+".join(actions) if actions else ""
        return OsStartupAction(executable=executable, action=action, read_only=actions == ["/query"])

    if executable == "systemctl":
        index = 1
        while index < len(lowered) and lowered[index] in SYSTEMCTL_READ_ONLY_PREFIX_OPTIONS:
            index += 1
        action = lowered[index] if index < len(lowered) else ""
        return OsStartupAction(
            executable=executable,
            action=action,
            read_only=action in SYSTEMCTL_READ_ONLY_ACTIONS,
        )

    if executable == "launchctl":
        action = lowered[1] if len(lowered) > 1 else ""
        return OsStartupAction(executable=executable, action=action, read_only=action in {"list", "print"})

    return OsStartupAction(executable=executable, action="", read_only=False)


def _has_remote_download_execution(parts: list[str]) -> bool:
    words = [_command_word(part) for part in parts]
    if not words:
        return False
    downloaders = {"curl", "wget", "iwr", "irm", "invoke-webrequest", "invoke-restmethod"}
    pipeline_executors = {
        "bash",
        "sh",
        "zsh",
        "dash",
        "ksh",
        "iex",
        "invoke-expression",
        "powershell",
        "pwsh",
        "python",
        "python2",
        "python3",
        "node",
        "ruby",
        "perl",
    }
    expression_executors = {"iex", "invoke-expression"}
    if words[0] in expression_executors and any(word in downloaders for word in words[1:]):
        return True
    if words[0] not in downloaders:
        return False
    for index, part in enumerate(parts[1:], start=1):
        if part not in {"|", "|&"}:
            continue
        if any(word in pipeline_executors for word in words[index + 1 :]):
            return True
    return False


def _has_network_upload_option(command: str, parts: list[str]) -> bool:
    curl_long_options = {
        "--data",
        "--data-ascii",
        "--data-binary",
        "--data-raw",
        "--data-urlencode",
        "--form",
        "--form-string",
        "--json",
        "--post-data",
        "--post-file",
        "--upload-file",
    }
    wget_long_options = {
        "--body-data",
        "--body-file",
        "--post-data",
        "--post-file",
        "--upload-file",
    }
    long_options = curl_long_options if command == "curl" else wget_long_options
    for part in parts[1:]:
        lowered = part.lower()
        if lowered in long_options or any(lowered.startswith(f"{option}=") for option in long_options):
            return True
        if command == "curl" and part.startswith("-") and not part.startswith("--"):
            if any(flag in part[1:] for flag in {"F", "T", "d"}):
                return True
    return False


POWERSHELL_WEB_COMMANDS = frozenset({"irm", "invoke-restmethod", "invoke-webrequest", "iwr"})
POWERSHELL_UPLOAD_INPUT_OPTIONS = frozenset({"-body", "-form", "-formdata", "-infile"})
REMOTE_COPY_VALUE_OPTIONS = {
    "scp": frozenset({"-c", "-F", "-i", "-J", "-l", "-o", "-P", "-S", "-X"}),
    "rsync": frozenset(
        {
            "--address",
            "--backup-dir",
            "--bwlimit",
            "--chmod",
            "--contimeout",
            "--exclude",
            "--exclude-from",
            "--files-from",
            "--filter",
            "--include",
            "--include-from",
            "--max-size",
            "--min-size",
            "--password-file",
            "--port",
            "--rsync-path",
            "--rsh",
            "--temp-dir",
            "--timeout",
            "-e",
        }
    ),
}
AWS_S3_VALUE_OPTIONS = frozenset(
    {
        "--acl",
        "--cache-control",
        "--content-disposition",
        "--content-encoding",
        "--content-language",
        "--content-type",
        "--copy-props",
        "--exclude",
        "--expires",
        "--grant-full-control",
        "--grant-read",
        "--grant-read-acp",
        "--grant-write-acp",
        "--include",
        "--metadata",
        "--metadata-directive",
        "--page-size",
        "--profile",
        "--region",
        "--sse",
        "--sse-c",
        "--sse-c-copy-source",
        "--sse-c-copy-source-key",
        "--sse-c-key",
        "--sse-kms-key-id",
        "--storage-class",
        "--website-redirect",
    }
)
GSUTIL_VALUE_OPTIONS = frozenset({"-a", "-h", "-i", "-j", "-o", "-p", "-u"})


def _option_name_and_value(part: str) -> tuple[str, str]:
    lowered = part.lower()
    if not lowered.startswith("-"):
        return "", ""
    for separator in ("=", ":"):
        if separator in lowered:
            name, value = lowered.split(separator, 1)
            return name, value
    return lowered, ""


def _positionals_after(
    parts: list[str],
    start: int,
    *,
    value_options: frozenset[str],
) -> list[str]:
    positionals: list[str] = []
    skip_next = False
    options_done = False
    for part in parts[start:]:
        lowered = part.lower()
        if skip_next:
            skip_next = False
            continue
        if not options_done and lowered == "--":
            options_done = True
            continue
        if not options_done and lowered.startswith("-"):
            option_text = part if part.startswith("-") and not part.startswith("--") else lowered
            if "=" in option_text:
                option, attached = option_text.split("=", 1)
            else:
                option, attached = option_text, ""
            if option in value_options and not attached:
                skip_next = True
            elif len(option) > 2 and option[:2] in value_options and not option.startswith("--"):
                continue
            continue
        positionals.append(part)
    return positionals


def _is_remote_copy_spec(value: str) -> bool:
    normalized = value.strip()
    lowered = normalized.lower()
    if lowered.startswith(("rsync://", "scp://")):
        return True
    if "://" in normalized or re.match(r"^[A-Za-z]:[\\/]", normalized):
        return False
    if ":" not in normalized:
        return False
    host, remote_path = normalized.split(":", 1)
    return bool(host and remote_path and "/" not in host and "\\" not in host and not host.startswith((".", "~")))


def _transfer_direction(
    sources: list[str],
    target: str,
    *,
    is_remote: Callable[[str], bool],
) -> TransferDirection:
    remote_target = is_remote(target)
    remote_sources = [is_remote(source) for source in sources]
    if remote_target:
        return "upload" if any(not remote for remote in remote_sources) else "remote"
    if any(remote_sources):
        return "download"
    return "local"


def _is_cloud_storage_uri(value: str) -> bool:
    return value.strip().lower().startswith(("s3://", "gs://", "az://", "abfs://", "abfss://"))


def _parse_powershell_web_transfer(parts: list[str]) -> OutboundTransferAction | None:
    executable = _command_word(parts[0]) if parts else ""
    if executable not in POWERSHELL_WEB_COMMANDS:
        return None
    method = ""
    upload_input = False
    for index, part in enumerate(parts[1:], start=1):
        option, attached = _option_name_and_value(part)
        if option in POWERSHELL_UPLOAD_INPUT_OPTIONS:
            upload_input = True
        if option == "-method":
            method = attached or (parts[index + 1].lower() if index + 1 < len(parts) else "")
    direction: TransferDirection = "upload" if upload_input or method in {"patch", "post", "put"} else "read"
    return OutboundTransferAction(transport=executable, direction=direction, target=executable)


def _parse_remote_copy_transfer(parts: list[str]) -> OutboundTransferAction | None:
    executable = _command_word(parts[0]) if parts else ""
    if executable not in REMOTE_COPY_VALUE_OPTIONS:
        return None
    positionals = _positionals_after(parts, 1, value_options=REMOTE_COPY_VALUE_OPTIONS[executable])
    if len(positionals) < 2:
        return None
    sources, target = positionals[:-1], positionals[-1]
    return OutboundTransferAction(
        transport=executable,
        direction=_transfer_direction(sources, target, is_remote=_is_remote_copy_spec),
        target=target,
    )


def _find_cloud_action(parts: list[str], executable: str) -> tuple[int, str] | None:
    lowered = _lower_parts(parts)
    if executable == "aws":
        for index in range(1, len(lowered) - 1):
            if lowered[index] == "s3" and lowered[index + 1] in {"cp", "sync"}:
                return index + 2, lowered[index + 1]
    if executable == "gsutil":
        for index in range(1, len(lowered)):
            if lowered[index] in {"cp", "rsync"}:
                return index + 1, lowered[index]
    return None


def _parse_cloud_storage_transfer(parts: list[str]) -> OutboundTransferAction | None:
    executable = _command_word(parts[0]) if parts else ""
    if executable not in {"aws", "gsutil"}:
        return None
    action = _find_cloud_action(parts, executable)
    if action is None:
        return None
    start, _ = action
    value_options = AWS_S3_VALUE_OPTIONS if executable == "aws" else GSUTIL_VALUE_OPTIONS
    positionals = _positionals_after(parts, start, value_options=value_options)
    if len(positionals) < 2:
        return None
    sources, target = positionals[:-1], positionals[-1]
    return OutboundTransferAction(
        transport=f"{executable} cloud storage",
        direction=_transfer_direction(sources, target, is_remote=_is_cloud_storage_uri),
        target=target,
    )


def _shell_command_segments(parts: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for part in parts:
        chunks = re.split(r"(&&|\|\||[|;&])", part)
        for chunk in chunks:
            if not chunk:
                continue
            if chunk in SHELL_CONTROL_MARKERS:
                if current:
                    segments.append(current)
                    current = []
                continue
            current.append(chunk)
    if current:
        segments.append(current)
    return segments


def _parse_outbound_transfer(parts: list[str]) -> OutboundTransferAction | None:
    observed: OutboundTransferAction | None = None
    for segment in _shell_command_segments(parts):
        action = (
            _parse_powershell_web_transfer(segment)
            or _parse_remote_copy_transfer(segment)
            or _parse_cloud_storage_transfer(segment)
        )
        if action is not None and action.direction == "upload":
            return action
        observed = observed or action
    return observed


EXTERNAL_PUBLISH_PREFIX_RULES = (
    ExternalPublishRule(frozenset({"git"}), ("push",), "source"),
    ExternalPublishRule(frozenset({"npm", "pnpm", "yarn"}), ("publish",), "package"),
    ExternalPublishRule(frozenset({"twine"}), ("upload",), "package"),
    ExternalPublishRule(frozenset({"cargo"}), ("publish",), "package"),
    ExternalPublishRule(frozenset({"gem"}), ("push",), "package"),
    ExternalPublishRule(frozenset({"nuget"}), ("push",), "package"),
    ExternalPublishRule(frozenset({"dotnet"}), ("nuget", "push"), "package"),
    ExternalPublishRule(frozenset({"docker", "podman"}), ("push",), "image"),
    ExternalPublishRule(frozenset({"helm"}), ("push",), "chart"),
    ExternalPublishRule(frozenset({"helm"}), ("chart", "push"), "chart"),
    ExternalPublishRule(frozenset({"prisma"}), ("migrate", "deploy"), "database"),
    ExternalPublishRule(frozenset({"firebase", "netlify"}), ("deploy",), "hosted"),
    ExternalPublishRule(frozenset({"wrangler"}), ("deploy",), "hosted"),
    ExternalPublishRule(frozenset({"wrangler"}), ("publish",), "hosted"),
    ExternalPublishRule(frozenset({"gh"}), ("release", "create"), "source"),
)
HOSTED_DEPLOY_EXECUTABLES = frozenset({"flyctl", "railway", "serverless", "vercel"})
CLOUD_MUTATION_EXECUTABLES = frozenset({"az", "gcloud", "supabase"})


def _prefix_matches(arguments: list[str], prefix: tuple[str, ...]) -> bool:
    return tuple(arguments[: len(prefix)]) == prefix


def _gradle_publish_task(arguments: list[str]) -> str:
    for argument in arguments:
        if argument.startswith("-"):
            continue
        task = argument.rsplit(":", 1)[-1]
        if task in {"publish", "publishplugins"}:
            return task
        if task.startswith("publish") and task.endswith("repository") and "localrepository" not in task:
            return task
    return ""


def _parse_external_publish_segment(parts: list[str]) -> ExternalPublishAction | None:
    if not parts:
        return None
    executable = _command_word(parts[0])
    arguments = _lower_parts(parts[1:])

    for rule in EXTERNAL_PUBLISH_PREFIX_RULES:
        if executable in rule.executables and _prefix_matches(arguments, rule.prefix):
            return ExternalPublishAction(
                kind=rule.kind,
                executable=executable,
                action=" ".join(rule.prefix),
            )

    if executable in {"py", "python", "python2", "python3"} and _prefix_matches(
        arguments, ("-m", "twine", "upload")
    ):
        return ExternalPublishAction(kind="package", executable=executable, action="twine upload")

    if executable in {"mvn", "mvnw"}:
        goal = next((argument for argument in arguments if argument == "deploy" or argument.startswith("deploy:")), "")
        if goal:
            return ExternalPublishAction(kind="package", executable=executable, action=goal)

    if executable in {"gradle", "gradlew"}:
        task = _gradle_publish_task(arguments)
        if task:
            return ExternalPublishAction(kind="package", executable=executable, action=task)

    if executable == "alembic" and arguments and arguments[0] in {"downgrade", "upgrade"}:
        return ExternalPublishAction(kind="database", executable=executable, action=arguments[0])

    if executable in HOSTED_DEPLOY_EXECUTABLES:
        action = next((argument for argument in arguments if argument in {"deploy", "redeploy", "up"}), "")
        if action:
            return ExternalPublishAction(kind="hosted", executable=executable, action=action)

    if executable == "gcloud" and (
        any(_prefix_matches(arguments, prefix) for prefix in (("app", "deploy"), ("functions", "deploy"), ("run", "deploy")))
        or bool(arguments and arguments[0] == "deploy")
    ):
        return ExternalPublishAction(kind="hosted", executable=executable, action="deploy")

    if executable in CLOUD_MUTATION_EXECUTABLES:
        action = next((argument for argument in arguments if argument in {"deploy", "push", "up"}), "")
        if action:
            return ExternalPublishAction(kind="hosted", executable=executable, action=action)

    return None


def _parse_external_publish_action(parts: list[str]) -> ExternalPublishAction | None:
    for segment in _shell_command_segments(parts):
        action = _parse_external_publish_segment(segment)
        if action is not None:
            return action
    return None


def _extract_privileged_command(parts: list[str]) -> list[str] | None:
    if not parts:
        return None
    wrapper = _command_word(parts[0])
    if wrapper == "gosu":
        return parts[2:] if len(parts) > 2 and not parts[1].startswith("-") else None
    if wrapper == "su":
        for index, part in enumerate(parts[1:], start=1):
            if part in {"-c", "--command"}:
                return parse_command_text(parts[index + 1]) if index + 1 < len(parts) else None
            if part.startswith("--command="):
                return parse_command_text(part.split("=", 1)[1])
        return None

    option_values = {
        "sudo": {"-C", "-D", "-g", "-h", "-p", "-R", "-r", "-t", "-T", "-u", "--chdir", "--group", "--host", "--prompt", "--role", "--type", "--user"},
        "doas": {"-a", "-C", "-u"},
        "pkexec": {"--user"},
        "run0": {"--chdir", "--description", "--gid", "--nice", "--property", "--setenv", "--slice", "--unit", "--user"},
    }
    no_value_options = {
        "sudo": {"-A", "-b", "-E", "-H", "-K", "-k", "-n", "-P", "-S", "-V", "-v", "--askpass", "--background", "--help", "--non-interactive", "--preserve-env", "--remove-timestamp", "--reset-timestamp", "--set-home", "--stdin", "--validate", "--version"},
        "doas": {"-L", "-n", "-s"},
        "pkexec": {"--disable-internal-agent", "--help", "--keep-cwd", "--version"},
        "run0": {"--background", "--help", "--pipe", "--pty", "--quiet", "--version"},
    }
    if wrapper not in option_values:
        return None
    index = 1
    while index < len(parts):
        part = parts[index]
        if not part.startswith("-") or part == "-":
            return parts[index:]
        if part in no_value_options[wrapper]:
            index += 1
            continue
        if part in option_values[wrapper]:
            if index + 1 >= len(parts):
                return None
            index += 2
            continue
        if part.startswith("--") and any(part.startswith(f"{option}=") for option in option_values[wrapper] if option.startswith("--")):
            index += 1
            continue
        if len(part) > 2 and part[:2] in option_values[wrapper] and not part.startswith("--"):
            index += 1
            continue
        return None
    return None


def _nested_privilege_decision(parts: list[str], context: CommandContext) -> ApprovalDecision:
    nested_parts = _extract_privileged_command(parts)
    if nested_parts:
        nested = approval_required_for_command(nested_parts, context)
        if nested.requires_approval:
            risk_order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
            risk: ApprovalRisk = nested.risk if risk_order[nested.risk] >= risk_order["high"] else "high"
            return _decision(
                parts,
                context,
                nested.action_class,
                risk,
                f"Command runs through a privilege-elevation wrapper. {nested.reason}",
                target_display=nested.target_display,
                confirmation_phrase=nested.confirmation_phrase,
            )
    return _decision(
        parts,
        context,
        "identity_access_mutation",
        "high",
        "Command runs through a privilege-elevation wrapper whose inner authority is not independently safe.",
        target_display=_command_word(parts[0]) if parts else "privilege wrapper",
        confirmation_phrase="approve privilege escalation",
    )


def _decision(
    argv: list[str],
    context: CommandContext,
    action_class: ApprovalClass,
    risk: ApprovalRisk,
    reason: str,
    *,
    target_display: str = "",
    confirmation_phrase: str = "",
) -> ApprovalDecision:
    requires = action_class != "none"
    phrase = confirmation_phrase
    if requires and not phrase:
        noun = target_display or action_class.replace("_", " ")
        phrase = f"approve {noun}".strip().lower()[:80]
    return ApprovalDecision(
        action_class=action_class,
        risk=risk,
        requires_approval=requires,
        approval_mode="blocked" if requires and context.non_interactive else "interactive" if requires else "none",
        reason=reason,
        target_display=target_display,
        command_digest=_digest_command(argv),
        confirmation_phrase=phrase,
        surface=context.surface,
    )


def parse_command_text(command: object) -> list[str]:
    if not isinstance(command, str):
        return [INVALID_COMMAND_TOKEN]
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def approval_required_for_command(argv: object, context: CommandContext | None = None) -> ApprovalDecision:
    if context is None:
        ctx = CommandContext()
    elif isinstance(context, CommandContext):
        ctx = context
    else:
        return _decision(
            [INVALID_COMMAND_TOKEN],
            CommandContext(surface="invalid-context", hosted=True, non_interactive=True),
            "remote_code_execution",
            "high",
            INVALID_COMMAND_REASON,
            confirmation_phrase="approve unvalidated command",
        )

    if not isinstance(argv, (list, tuple)) or not all(isinstance(part, str) for part in argv):
        return _decision(
            [INVALID_COMMAND_TOKEN],
            ctx,
            "remote_code_execution",
            "high",
            INVALID_COMMAND_REASON,
            confirmation_phrase="approve unvalidated command",
        )

    parts = [part for part in argv if part != "--"]
    if INVALID_COMMAND_TOKEN in parts:
        return _decision(
            [INVALID_COMMAND_TOKEN],
            ctx,
            "remote_code_execution",
            "high",
            INVALID_COMMAND_REASON,
            confirmation_phrase="approve unvalidated command",
        )
    lowered = _lower_parts(parts)
    if not lowered:
        return _decision(parts, ctx, "none", "none", "Empty command.")

    first = lowered[0]
    second = lowered[1] if len(lowered) > 1 else ""

    bin_name = re.sub(r"\.(?:exe|cmd|bat)$", "", first.replace("\\", "/").rsplit("/", 1)[-1])
    shell_interpreters = {"bash", "sh", "zsh", "dash", "ksh", "pwsh", "powershell"}
    language_interpreters = {"python", "python2", "python3", "node", "ruby", "perl"}

    if bin_name in shell_interpreters:
        shell_code_flags = {"-c", "-lc", "-command"}
        payload = ""
        for index, part in enumerate(lowered[1:], start=1):
            flag = part.split("=", 1)[0] if "=" in part else part
            if flag in shell_code_flags:
                if "=" in part:
                    payload = parts[index].split("=", 1)[1]
                elif index + 1 < len(parts):
                    payload = parts[index + 1]
                if not payload.strip():
                    return _decision(
                        parts,
                        ctx,
                        "remote_code_execution",
                        "high",
                        "Shell interpreter invoked with an inline-command flag but no payload could be isolated.",
                        target_display=bin_name,
                        confirmation_phrase="approve remote code execution",
                    )
                nested = approval_required_for_command(parse_command_text(payload), ctx)
                if nested.requires_approval:
                    return nested
                break

    if bin_name in language_interpreters:
        lang_code_flags = {"-c", "-e", "--eval", "-p", "--print"}
        for index, part in enumerate(lowered[1:], start=1):
            flag = part.split("=", 1)[0] if "=" in part else part
            if flag in lang_code_flags:
                if "=" in part:
                    payload = parts[index].split("=", 1)[1]
                elif index + 1 < len(parts):
                    payload = parts[index + 1]
                else:
                    payload = ""
                if payload.strip():
                    return _decision(
                        parts,
                        ctx,
                        "remote_code_execution",
                        "high",
                        "Language interpreter invoked with inline source code.",
                        target_display=bin_name,
                        confirmation_phrase="approve remote code execution",
                    )

    if bin_name in {"sudo", "doas", "pkexec", "run0", "gosu", "su"}:
        return _nested_privilege_decision(parts, ctx)

    if first == "env":
        index = 1
        while index < len(parts) and _is_env_assignment(parts[index]):
            index += 1
        if index < len(parts):
            nested = approval_required_for_command(parts[index:], ctx)
            if nested.requires_approval:
                return nested
        else:
            return _decision(
                parts,
                ctx,
                "credential_mutation",
                "high",
                "Command can print environment variables that may include secrets.",
                target_display="env",
                confirmation_phrase="approve environment reveal",
            )

    if first == "spark" and second in {"status", "guide"}:
        return _decision(parts, ctx, "none", "none", f"`spark {second}` is read-only.")
    if first == "spark" and lowered[1:3] in (["access", "status"], ["access", "guide"]):
        return _decision(parts, ctx, "none", "none", f"`spark access {lowered[2]}` is read-only.")
    if first == "spark" and second == "verify" and "--deep" not in lowered:
        return _decision(parts, ctx, "none", "none", "`spark verify` without --deep is report-only.")
    if first == "spark" and lowered[1:3] == ["providers", "status"]:
        return _decision(parts, ctx, "none", "none", "`spark providers status` is read-only.")

    if first == "spark" and second == "uninstall" and "--purge-home" in lowered:
        return _decision(
            parts,
            ctx,
            "destructive_filesystem",
            "critical",
            "Command can delete the local Spark home, including state, logs, generated config, and installed module checkouts.",
            target_display="SPARK_HOME",
            confirmation_phrase="delete spark home",
        )

    destructive_bins = {"rm", "rmdir", "del", "remove-item", "erase"}
    if first in destructive_bins or _contains_any(lowered, destructive_bins):
        recursive_or_force = _contains_any(lowered, {"-rf", "-fr", "-r", "--recursive", "-recurse", "-force", "/s"})
        target = _target_after(parts, destructive_bins)
        return _decision(
            parts,
            ctx,
            "destructive_filesystem",
            "critical" if recursive_or_force else "high",
            "Command can delete local files or directories.",
            target_display=target,
            confirmation_phrase=f"delete {target}".strip().lower()[:80] if target else "approve delete",
        )

    if first == "git" and (
        "filter-repo" in lowered
        or "filter-branch" in lowered
        or "--force" in lowered
        or "--force-with-lease" in lowered
        or "-f" in lowered and second in {"push", "tag"}
        or second in {"rebase", "reset"}
    ):
        return _decision(
            parts,
            ctx,
            "git_history_mutation",
            "critical",
            "Command can rewrite published history or discard local work.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve git history mutation",
        )

    if first == "spark" and second == "secrets" and _contains_any(lowered, {"delete", "get", "export", "--reveal"}):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "high",
            "Command can reveal, export, delete, or mutate stored credentials.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve secret access",
        )
    if first == "spark" and second == "secrets" and _contains_any(lowered, {"set"}):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "high",
            "Command can store, rotate, or overwrite Spark credentials.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve secret change",
        )
    if first == "spark" and lowered[1:3] == ["security", "revoke-all"]:
        if "--dry-run" in lowered:
            return _decision(parts, ctx, "none", "none", "`spark security revoke-all --dry-run` is report-only.")
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "critical",
            "Command stops Spark, rotates local control keys, removes local secrets, and writes incident state.",
            target_display="spark security revoke-all",
            confirmation_phrase="revoke spark access",
        )

    if first in {"printenv", "set"} and (
        len(lowered) == 1 or any(_looks_like_sensitive_env_name(part) for part in parts[1:])
    ):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "high",
            "Command can reveal environment variables or credential-like values.",
            target_display=parts[0],
            confirmation_phrase="approve environment reveal",
        )

    if first == "gh" and lowered[1:3] == ["auth", "token"]:
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "critical",
            "GitHub command can reveal the active authentication token.",
            target_display="gh auth token",
            confirmation_phrase="approve github token reveal",
        )

    if first == "npm" and (
        second == "token"
        or (
            second == "config"
            and len(lowered) > 3
            and lowered[2] in {"get", "set", "delete", "rm", "remove"}
            and _looks_like_npm_auth_key(parts[3])
        )
    ):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "high",
            "npm command can reveal, create, revoke, or change registry authentication tokens.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve npm token access",
        )

    if (
        (first == "gcloud" and lowered[1:3] == ["auth", "print-access-token"])
        or (first == "az" and lowered[1:3] == ["account", "get-access-token"])
    ):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "critical",
            "Cloud CLI command can reveal a live access token.",
            target_display=" ".join(parts[:3]),
            confirmation_phrase="approve cloud token reveal",
        )

    if first == "aws" and (
        lowered[1:3] in [["secretsmanager", "get-secret-value"], ["ssm", "get-parameter"]]
        or lowered[1:3] in [["ecr", "get-login-password"], ["sts", "get-session-token"]]
        or (
            lowered[1:3] == ["configure", "get"]
            and len(lowered) > 3
            and any(marker in lowered[3] for marker in {"secret_access_key", "session_token", "security_token"})
        )
    ):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "critical",
            "AWS command can reveal cloud secrets, registry passwords, or session credentials.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve aws credential reveal",
        )

    if first == "kubectl" and (
        (lowered[1:3] == ["config", "view"] and "--raw" in lowered)
        or (len(lowered) > 2 and lowered[1] in {"get", "describe"} and lowered[2] in {"secret", "secrets"})
    ):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "critical",
            "Kubernetes command can reveal cluster secrets or raw kubeconfig credentials.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve kubernetes secret read",
        )

    if (
        (first == "op" and (second == "read" or lowered[1:3] == ["item", "get"]))
        or (first == "pass" and second in {"show", "otp"})
        or (
            first == "security"
            and second in {"find-generic-password", "find-internet-password"}
            and "-w" in lowered
        )
    ):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "critical",
            "Password-manager command can reveal stored secret values.",
            target_display=" ".join(parts[:3]),
            confirmation_phrase="approve password reveal",
        )

    if first == "docker" and second in {"login", "logout"}:
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "high",
            "Docker command can store, change, or remove registry credentials.",
            target_display=f"docker {second}",
            confirmation_phrase="approve docker credential change",
        )

    if _has_remote_download_execution(parts):
        return _decision(
            parts,
            ctx,
            "remote_code_execution",
            "critical",
            "Command appears to download remote code and execute it.",
            target_display=parts[0],
            confirmation_phrase="approve remote code execution",
        )

    if first == "find" and any(part in {"-exec", "-execdir"} for part in lowered):
        return _decision(
            parts,
            ctx,
            "remote_code_execution",
            "high",
            "Command runs another command through find over matched filesystem paths.",
            target_display="find -exec",
            confirmation_phrase="approve find execution",
        )

    if first == "git" and lowered[1:3] in [["submodule", "add"], ["submodule", "update"]]:
        return _decision(
            parts,
            ctx,
            "remote_code_execution",
            "high",
            "Git submodule commands can add or fetch executable code from another repository.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve submodule code fetch",
        )

    if first == "docker" and (
        "--privileged" in lowered
        or "--network=host" in lowered
        or ("--network" in lowered and "host" in lowered)
        or _has_option_value(lowered, {"-v", "--volume", "--mount"}, {"/", "/root", "/home", "/users", "/var/run/docker.sock"})
    ):
        return _decision(
            parts,
            ctx,
            "container_privilege_escalation",
            "critical",
            "Docker command can expose the host, Docker socket, host network, or privileged container capabilities.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve container privilege",
        )

    if first in {"railway", "vercel", "flyctl"} and _contains_any(lowered, {"variables", "env", "secret", "secrets"}):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "high",
            "Command can change hosted environment variables or secrets.",
            target_display=" ".join(parts[:5]),
            confirmation_phrase="approve hosted secret change",
        )
    if first == "gh" and (
        lowered[1:3] in [["secret", "set"], ["variable", "set"]]
        or lowered[1:3] in [["pr", "merge"], ["release", "create"], ["release", "upload"]]
    ):
        action = "credential_mutation" if "secret" in lowered or "variable" in lowered else "external_publish"
        return _decision(
            parts,
            ctx,
            action,
            "high",
            "GitHub command can mutate repository secrets/variables, merge PRs, or publish releases.",
            target_display=" ".join(parts[:5]),
            confirmation_phrase="approve github mutation",
        )
    if first in {"kubectl", "helm", "terraform", "pulumi"} and _contains_any(lowered, {"apply", "delete", "destroy", "upgrade", "install", "up"}):
        return _decision(
            parts,
            ctx,
            "external_publish",
            "critical" if "destroy" in lowered or "delete" in lowered else "high",
            "Command can mutate live infrastructure.",
            target_display=" ".join(parts[:5]),
            confirmation_phrase="approve infrastructure change",
        )
    external_publish = _parse_external_publish_action(parts)
    if external_publish is not None:
        hosted = external_publish.kind == "hosted"
        return _decision(
            parts,
            ctx,
            "external_publish",
            "high",
            "Command can publish artifacts or mutate a remote deployment outside this machine.",
            target_display=f"{external_publish.executable} {external_publish.action}".strip(),
            confirmation_phrase="approve hosted deploy" if hosted else "approve publish",
        )

    if first == "spark" and lowered[1:3] == ["autostart", "status"]:
        return _decision(parts, ctx, "none", "none", "`spark autostart status` is read-only.")
    if first == "spark" and second == "setup" and "--no-autostart" not in lowered:
        return _decision(
            parts,
            ctx,
            "process_autostart_mutation",
            "medium",
            "`spark setup` installs OS login autostart by default.",
            target_display="spark setup",
            confirmation_phrase="approve autostart change",
        )
    if first == "spark" and second == "autostart":
        return _decision(
            parts,
            ctx,
            "process_autostart_mutation",
            "medium",
            "Command changes login/startup behavior for this computer or host.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve autostart change",
        )
    os_startup_action = _parse_os_startup_action(parts)
    if os_startup_action is not None and os_startup_action.read_only:
        return _decision(
            parts,
            ctx,
            "none",
            "none",
            "Command performs one parsed read-only OS startup or service inspection.",
            target_display=f"{os_startup_action.executable} {os_startup_action.action}".strip(),
        )
    if os_startup_action is not None:
        return _decision(
            parts,
            ctx,
            "process_autostart_mutation",
            "high",
            "Command can change OS services, registry, shell profile, or startup behavior.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve system startup change",
        )

    if first == "spark" and second == "doctor" and "--include-logs" in lowered:
        return _decision(
            parts,
            ctx,
            "network_exfiltration",
            "medium",
            "Doctor logs may be sent to a configured LLM provider after redaction.",
            target_display="spark doctor llm --include-logs",
            confirmation_phrase="approve redacted log sharing",
        )
    outbound_transfer = _parse_outbound_transfer(parts)
    if outbound_transfer is not None and outbound_transfer.direction == "upload":
        return _decision(
            parts,
            ctx,
            "network_exfiltration",
            "medium",
            "Command can transfer local data to a remote system or cloud storage.",
            target_display=outbound_transfer.transport,
            confirmation_phrase="approve network upload",
        )
    if bin_name in {"curl", "wget"} and _has_network_upload_option(bin_name, parts):
        return _decision(
            parts,
            ctx,
            "network_exfiltration",
            "medium",
            "Command may upload local data to a network endpoint.",
            target_display=parts[0],
            confirmation_phrase="approve network upload",
        )

    if first == "spark" and second == "access":
        level5_requested = "--enable-high-agency" in lowered or "disable-level5" in lowered
        return _decision(
            parts,
            ctx,
            "identity_access_mutation",
            "critical" if level5_requested else "high",
            "Command changes Spark access or high-agency runner configuration.",
            target_display=" ".join(parts[:5]),
            confirmation_phrase="approve level 5 access" if level5_requested else "approve access change",
        )

    if first == "spark" and (
        second == "telegram"
        or ("--admin-telegram-ids" in lowered)
        or ("--bot-token" in lowered)
        or ("--access" in lowered)
    ):
        return _decision(
            parts,
            ctx,
            "identity_access_mutation",
            "high",
            "Command changes Telegram, identity, or operator access configuration.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve access change",
        )

    if first == "spark" and second == "verify" and "--deep" in lowered:
        return _decision(
            parts,
            ctx,
            "high_cost_execution",
            "medium",
            "Deep verification can start live provider or mission smoke tests.",
            target_display="spark verify --deep",
            confirmation_phrase="approve deep verification",
        )

    return _decision(parts, ctx, "none", "none", "No sensitive action class matched.")
