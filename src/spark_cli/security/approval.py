from __future__ import annotations

import hashlib
import re
import shlex
from dataclasses import asdict, dataclass
from typing import Literal

from .aws_authority import decide_aws_authority
from .container_authority import decide_container_authority
from .credential_authority import decide_credential_authority
from .git_authority import decide_git_authority
from .host_authority import decide_host_authority
from .infrastructure_authority import decide_infrastructure_authority
from .kubernetes_authority import decide_kubernetes_authority
from .network_authority import decide_network_authority, decide_ssh_tunnel_authority, network_upload_option
from .wrapper_policy import (
    DYNAMIC_LOADER_ENV_NAMES,
    PROCESS_SCHEDULER_WRAPPERS,
    PROCESS_TRACE_WRAPPERS,
    TRANSPARENT_COMMAND_WRAPPERS,
    transparent_wrapper_command,
)


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


PublishKind = Literal["source", "package", "image", "chart", "hosted", "database", "infrastructure"]


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


SshActionKind = Literal["inspection", "remote_access", "invalid"]


@dataclass(frozen=True)
class SshAction:
    kind: SshActionKind
    destination: str = ""
    has_remote_command: bool = False


SECRET_LIKE_PATTERN = re.compile(
    r"(?i)("
    r"sk-[A-Za-z0-9_-]{8,}"                          # OpenAI / Anthropic keys
    r"|gh[pors]_[A-Za-z0-9]{36,}"                     # GitHub PATs
    r"|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}"             # AWS access keys
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"                  # Slack tokens
    r"|[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"  # JWTs
    r"|\d{5,}:[A-Za-z0-9_-]{20,}"                    # Telegram bot tokens
    r")"
)
INVALID_COMMAND_TOKEN = "<spark-invalid-command>"
INVALID_COMMAND_REASON = "Command input could not be validated as an ordered sequence of text tokens."
SENSITIVE_ENV_NAME_PATTERN = re.compile(
    r"(?i)(?:^|[_-])(?:token|secret|api[_-]?key|password|passwd|credential|auth)(?:$|[_-])"
)
SPARK_SETUP_CREDENTIAL_OPTIONS = frozenset(
    {
        "--secret",
        "--telegram-relay-secret",
        "--zai-api-key",
        "--openai-api-key",
        "--anthropic-api-key",
        "--openrouter-api-key",
        "--kimi-api-key",
        "--huggingface-api-key",
        "--minimax-api-key",
        "--elevenlabs-api-key",
    }
)
SPARK_IDENTITY_ACCESS_OPTIONS = frozenset(
    {
        "--access",
        "--admin-telegram-ids",
        "--bot-token",
    }
)


def _digest_command(argv: list[str]) -> str:
    redacted = [SECRET_LIKE_PATTERN.sub("[REDACTED]", part) for part in argv]
    return hashlib.sha256("\0".join(redacted).encode("utf-8")).hexdigest()


def _redact_display(text: str) -> str:
    """Redact secret-like values from user-facing display strings."""
    return SECRET_LIKE_PATTERN.sub("[REDACTED]", text)


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


def _has_option(parts: list[str], option_names: frozenset[str]) -> bool:
    return any(part.lower().split("=", 1)[0] in option_names for part in parts)


def _is_env_assignment(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*", value))


def _looks_like_sensitive_env_name(value: str) -> bool:
    return bool(SENSITIVE_ENV_NAME_PATTERN.search(value))


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


SSH_VALUE_OPTIONS = frozenset(
    {"-b", "-B", "-c", "-D", "-E", "-e", "-F", "-I", "-i", "-J", "-L", "-l", "-m", "-O", "-o", "-P", "-p", "-Q", "-R", "-S", "-W", "-w"}
)
SSH_FLAG_OPTION_CHARS = frozenset("46AaCfGgKkMNnqsTtVvXxYy")


def _parse_ssh_action(parts: list[str]) -> SshAction | None:
    if not parts or _command_word(parts[0]) != "ssh":
        return None
    if parts[1:] == ["-V"]:
        return SshAction(kind="inspection")
    if len(parts) == 3 and parts[1] == "-Q" and parts[2] and not parts[2].startswith("-"):
        return SshAction(kind="inspection")

    index = 1
    config_only = False
    options_done = False
    while index < len(parts):
        part = parts[index]
        if not options_done and part == "--":
            options_done = True
            index += 1
            continue
        if options_done or not part.startswith("-"):
            break
        if part == "-" or part.startswith("--"):
            return SshAction(kind="invalid")
        if part in SSH_VALUE_OPTIONS:
            if index + 1 >= len(parts) or not parts[index + 1]:
                return SshAction(kind="invalid")
            index += 2
            continue
        option = part[:2]
        if option in SSH_VALUE_OPTIONS and len(part) > 2:
            index += 1
            continue
        flags = part[1:]
        if not flags or any(flag not in SSH_FLAG_OPTION_CHARS for flag in flags):
            return SshAction(kind="invalid")
        config_only = config_only or "G" in flags
        index += 1

    if index >= len(parts) or not parts[index] or parts[index] == "-":
        return SshAction(kind="invalid")
    destination = parts[index]
    has_remote_command = index + 1 < len(parts)
    if config_only:
        if has_remote_command:
            return SshAction(kind="invalid", destination=destination, has_remote_command=True)
        return SshAction(kind="inspection", destination=destination)
    return SshAction(
        kind="remote_access",
        destination=destination,
        has_remote_command=has_remote_command,
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
    ExternalPublishRule(frozenset({"npx"}), ("prisma", "migrate", "deploy"), "database"),
    ExternalPublishRule(frozenset({"firebase", "netlify"}), ("deploy",), "hosted"),
    ExternalPublishRule(frozenset({"wrangler"}), ("deploy",), "hosted"),
    ExternalPublishRule(frozenset({"wrangler"}), ("publish",), "hosted"),
    ExternalPublishRule(frozenset({"gh"}), ("release", "create"), "source"),
)
HOSTED_DEPLOY_EXECUTABLES = frozenset({"flyctl", "railway", "serverless", "sls", "vercel"})
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

    if executable == "az" and (
        _prefix_matches(arguments, ("functionapp", "deployment", "source"))
        or (len(arguments) > 2 and arguments[0] == "deployment" and "create" in arguments[2:])
    ):
        return ExternalPublishAction(kind="hosted", executable=executable, action="deployment")

    if executable == "kubectl" and (
        _prefix_matches(arguments, ("rollout", "restart"))
        or bool(arguments and arguments[0] in {"annotate", "cordon", "drain", "label", "patch", "scale"})
    ):
        return ExternalPublishAction(kind="infrastructure", executable=executable, action=arguments[0])

    if executable == "pulumi" and arguments and arguments[0] == "import":
        return ExternalPublishAction(kind="infrastructure", executable=executable, action="import")

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


def _opens_privileged_shell(parts: list[str]) -> bool:
    if not parts:
        return False
    wrapper = _command_word(parts[0])
    if wrapper not in {"sudo", "doas", "pkexec", "run0", "gosu", "su"}:
        return False
    if wrapper in {"sudo", "doas"} and any(part in {"-i", "--login", "-s", "--shell"} for part in parts[1:]):
        return True
    nested_parts = _extract_privileged_command(parts)
    if not nested_parts:
        return False
    return _command_word(nested_parts[0]) in {"bash", "csh", "dash", "fish", "ksh", "sh", "tcsh", "zsh"}


def _nested_privilege_decision(parts: list[str], context: CommandContext) -> ApprovalDecision:
    if _opens_privileged_shell(parts):
        return _decision(
            parts,
            context,
            "identity_access_mutation",
            "critical",
            "Command opens a shell through a privilege-elevation wrapper.",
            target_display=_command_word(parts[0]) if parts else "privilege wrapper",
            confirmation_phrase="approve privileged shell",
        )
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
        target_display=_redact_display(target_display),
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
        return [INVALID_COMMAND_TOKEN]


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

    raw_parts = list(argv)
    parts = [part for part in raw_parts if part != "--"]
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
    first = _command_word(parts[0])
    second = lowered[1] if len(lowered) > 1 else ""
    joined = " ".join(lowered)
    bin_name = first
    if bin_name in PROCESS_TRACE_WRAPPERS:
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "critical",
            "Process tracing can inspect another process's arguments, memory, files, and secret-bearing system calls.",
            target_display=bin_name,
            confirmation_phrase="approve process tracing",
        )
    if bin_name in PROCESS_SCHEDULER_WRAPPERS:
        return _decision(
            parts,
            ctx,
            "identity_access_mutation",
            "high",
            "Process scheduler commands can inspect or change execution authority for an existing process.",
            target_display=bin_name,
            confirmation_phrase="approve process scheduling",
        )
    if bin_name in TRANSPARENT_COMMAND_WRAPPERS:
        inner_parts, env_names, read_only = transparent_wrapper_command(parts)
        if read_only:
            return _decision(parts, ctx, "none", "none", f"`{bin_name}` help/version output is read-only.")
        injection_names = env_names & DYNAMIC_LOADER_ENV_NAMES
        if injection_names:
            return _decision(
                parts,
                ctx,
                "remote_code_execution",
                "high",
                "Environment assignments can inject code or alter executable/module loading before the wrapped command starts.",
                target_display=", ".join(sorted(injection_names)),
                confirmation_phrase="approve environment code injection",
            )
        if not inner_parts:
            action_class: ApprovalClass = "credential_mutation" if bin_name == "env" else "identity_access_mutation"
            phrase = "approve environment reveal" if bin_name == "env" else "approve unresolved command wrapper"
            return _decision(
                parts,
                ctx,
                action_class,
                "high",
                "Command wrapper did not expose a complete inner command that Spark could classify safely.",
                target_display=bin_name,
                confirmation_phrase=phrase,
            )
        nested = approval_required_for_command(inner_parts, ctx)
        if nested.requires_approval:
            return _decision(
                parts,
                ctx,
                nested.action_class,
                nested.risk,
                f"Command runs through `{bin_name}`. {nested.reason}",
                target_display=nested.target_display,
                confirmation_phrase=nested.confirmation_phrase,
            )
        return _decision(parts, ctx, "none", "none", f"`{bin_name}` wraps a classified read-only command.")

    shell_interpreters = {"bash", "sh", "zsh", "dash", "ksh", "fish", "pwsh", "powershell"}
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
                if bin_name in {"pwsh", "powershell"}:
                    break
                return _decision(
                    parts,
                    ctx,
                    "remote_code_execution",
                    "high",
                    "Shell interpreter invoked with inline source code.",
                    target_display=bin_name,
                    confirmation_phrase="approve remote code execution",
                )

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

    if first == "spark" and second in {"status", "guide"}:
        return _decision(parts, ctx, "none", "none", f"`spark {second}` is read-only.")
    if first == "spark" and lowered[1:3] in (["access", "status"], ["access", "guide"]):
        return _decision(parts, ctx, "none", "none", f"`spark access {lowered[2]}` is read-only.")
    if first == "spark" and second == "verify" and "--deep" not in lowered:
        return _decision(parts, ctx, "none", "none", "`spark verify` without --deep is report-only.")
    if first == "spark" and lowered[1:3] == ["providers", "status"]:
        return _decision(parts, ctx, "none", "none", "`spark providers status` is read-only.")

    if first == "spark" and second == "setup" and _has_option(parts, SPARK_IDENTITY_ACCESS_OPTIONS):
        return _decision(
            parts,
            ctx,
            "identity_access_mutation",
            "high",
            "Setup arguments can change Telegram identity or operator access configuration.",
            target_display="spark setup",
            confirmation_phrase="approve access change",
        )
    if first == "spark" and second == "setup" and _has_option(parts, SPARK_SETUP_CREDENTIAL_OPTIONS):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "high",
            "Setup arguments can store, rotate, or overwrite Spark credentials.",
            target_display="spark setup",
            confirmation_phrase="approve secret change",
        )

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
    if first == "spark" and second == "uninstall" and "--all" in lowered:
        return _decision(
            parts,
            ctx,
            "destructive_filesystem",
            "high",
            "Command removes all installed Spark modules and their generated config. This cannot be undone without reinstalling.",
            target_display="all modules",
            confirmation_phrase="uninstall all modules",
        )

    if container_decision := decide_container_authority(raw_parts, ctx, _decision):
        return container_decision
    if kubernetes_decision := decide_kubernetes_authority(raw_parts, ctx, _decision):
        return kubernetes_decision
    if infrastructure_decision := decide_infrastructure_authority(raw_parts, ctx, _decision):
        return infrastructure_decision
    if aws_decision := decide_aws_authority(raw_parts, ctx, _decision):
        return aws_decision
    if host_decision := decide_host_authority(raw_parts, ctx, _decision):
        return host_decision

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

    # curl/wget that writes downloaded content to disk. wget writes to the local
    # filesystem by default (no flag required); curl only writes with -o/-O/--output.
    # Skip when a higher-severity rule below already covers it (pipe-to-shell RCE
    # at the curl|sh check, or an upload via --data/--upload-file), so we never
    # downgrade those classes.
    _curl_writes_file = first == "curl" and (
        _contains_any(lowered, {"-o", "--output"}) or _contains_any(parts, {"-O"})
    )
    _fetch_writes_file = first == "wget" or _curl_writes_file
    _fetch_is_rce = first in {"curl", "wget"} and re.search(
        r"\b(?:bash|sh|powershell|pwsh|iex|invoke-expression|python|node)\b", joined
    )
    _fetch_is_upload = network_upload_option(first, parts)
    if _fetch_writes_file and not _fetch_is_rce and not _fetch_is_upload:
        target = _target_after(parts, {"curl", "wget"})
        return _decision(
            parts,
            ctx,
            "destructive_filesystem",
            "high",
            "Command can write downloaded content to the local filesystem.",
            target_display=target or parts[0],
            confirmation_phrase=f"approve file write {target}".strip().lower()[:80] if target else "approve file write",
        )

    if git_decision := decide_git_authority(raw_parts, ctx, _decision):
        return git_decision
    if credential_decision := decide_credential_authority(raw_parts, ctx, _decision):
        return credential_decision

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

    if network_decision := decide_ssh_tunnel_authority(raw_parts, ctx, _decision):
        return network_decision

    ssh_action = _parse_ssh_action(parts)
    if ssh_action is not None:
        if ssh_action.kind == "inspection":
            return _decision(parts, ctx, "none", "none", "SSH command is a local metadata inspection.")
        if ssh_action.kind == "invalid":
            reason = "SSH command grammar could not be validated safely."
        elif ssh_action.has_remote_command:
            reason = "SSH command can execute instructions on a remote host."
        else:
            reason = "SSH command can open an interactive command session on a remote host."
        return _decision(
            parts,
            ctx,
            "remote_code_execution",
            "high",
            reason,
            target_display=ssh_action.destination,
            confirmation_phrase="approve ssh remote access",
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

    if first == "nsenter":
        return _decision(
            parts,
            ctx,
            "container_privilege_escalation",
            "critical",
            "nsenter enters one or more Linux namespaces of a target process and can escape container isolation on the host.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve namespace entry",
        )

    if first == "chroot":
        return _decision(
            parts,
            ctx,
            "container_privilege_escalation",
            "high",
            "chroot changes the root directory for a process, which can escape filesystem containment or grant access to an alternative OS tree.",
            target_display=" ".join(parts[:3]),
            confirmation_phrase="approve chroot",
        )

    if first in {
        "adduser", "useradd", "usermod", "userdel", "deluser",
        "groupadd", "groupmod", "groupdel",
        "passwd", "chpasswd",
    }:
        return _decision(
            parts,
            ctx,
            "identity_access_mutation",
            "high",
            "Command modifies local user accounts, groups, or credentials.",
            target_display=" ".join(parts[:3]),
            confirmation_phrase="approve user account change",
        )

    if first in {"railway", "vercel", "flyctl", "serverless"} and _contains_any(lowered, {"up", "deploy", "redeploy"}):
        return _decision(
            parts,
            ctx,
            "external_publish",
            "high",
            "Command can publish or redeploy hosted infrastructure.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve hosted deploy",
        )
    if (first == "netlify" and second == "deploy") or (
        first == "wrangler" and second in {"deploy", "publish"}
    ):
        return _decision(
            parts,
            ctx,
            "external_publish",
            "high",
            "Command can publish or redeploy hosted edge/static infrastructure.",
            target_display=" ".join(parts[:5]),
            confirmation_phrase="approve hosted deploy",
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
    if first in {"terraform", "pulumi"} and _contains_any(lowered, {"apply", "delete", "destroy", "upgrade", "install", "up"}):
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
        confirmation_phrases = {
            "database": "approve database migration",
            "hosted": "approve hosted deploy",
            "infrastructure": "approve infrastructure change",
        }
        return _decision(
            parts,
            ctx,
            "external_publish",
            "high",
            "Command can publish artifacts or mutate a remote deployment outside this machine.",
            target_display=f"{external_publish.executable} {external_publish.action}".strip(),
            confirmation_phrase=confirmation_phrases.get(external_publish.kind, "approve publish"),
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
    if network_decision := decide_network_authority(raw_parts, ctx, _decision):
        return network_decision

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
        or _has_option(parts, SPARK_IDENTITY_ACCESS_OPTIONS)
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
