from __future__ import annotations

import hashlib
import re
import shlex
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


SECRET_LIKE_PATTERN = re.compile(
    r"(?i)(sk-[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|\d{5,}:[A-Za-z0-9_-]{20,})"
)


def _digest_command(argv: list[str]) -> str:
    argv_list = argv if isinstance(argv, list) else list(argv) if isinstance(argv, (tuple, set)) else []
    redacted = [SECRET_LIKE_PATTERN.sub("[REDACTED]", str(part or "")) for part in argv_list]
    return hashlib.sha256("\0".join(redacted).encode("utf-8")).hexdigest()


def _lower_parts(argv: list[str]) -> list[str]:
    if not isinstance(argv, str): argv = str(argv or '')
    try:
        argv_list = argv if isinstance(argv, list) else list(argv) if isinstance(argv, (tuple, set)) else []
        return [str(part or "").lower() for part in argv_list]



    except Exception:
        return []
def _contains_any(parts: list[str], values: set[str]) -> bool:
    if not isinstance(parts, str): parts = str(parts or '')
    if not isinstance(values, str): values = str(values or '')
    try:
        parts_list = parts if isinstance(parts, list) else list(parts) if isinstance(parts, (tuple, set)) else []
        values_set = values if isinstance(values, set) else set(values) if isinstance(values, (list, tuple)) else set()
        lowered_parts = {str(p or "").lower() for p in parts_list}
        lowered_values = {str(v or "").lower() for v in values_set}
        return bool(lowered_parts & lowered_values)



    except Exception:
        return False
def _target_after(parts: list[str], command_names: set[str]) -> str:
    if not isinstance(parts, str): parts = str(parts or '')
    if not isinstance(command_names, str): command_names = str(command_names or '')
    try:
        parts_list = parts if isinstance(parts, list) else list(parts) if isinstance(parts, (tuple, set)) else []
        cmd_names = {str(cmd or "").lower() for cmd in (command_names if isinstance(command_names, set) else set(command_names or []))}
        for index, part in enumerate(parts_list):
            part_str = str(part or "").lower()
            if part_str in cmd_names and index + 1 < len(parts_list):
                for candidate in parts_list[index + 1 :]:
                    candidate_str = str(candidate or "")
                    if not candidate_str.startswith("-"):
                        return candidate_str
        return ""



    except Exception:
        return ""
def _has_option_value(parts: list[str], option_names: set[str], suspicious_values: set[str]) -> bool:
    if not isinstance(parts, str): parts = str(parts or '')
    if not isinstance(option_names, str): option_names = str(option_names or '')
    if not isinstance(suspicious_values, str): suspicious_values = str(suspicious_values or '')
    try:
        parts_list = parts if isinstance(parts, list) else list(parts) if isinstance(parts, (tuple, set)) else []
        lowered = _lower_parts(parts_list)
        opt_names = {str(opt or "").lower() for opt in (option_names if isinstance(option_names, set) else set(option_names or []))}
        susp_vals = {str(susp or "").lower() for susp in (suspicious_values if isinstance(suspicious_values, set) else set(suspicious_values or []))}
        for index, part in enumerate(lowered):
            value = ""
            if "=" in part:
                name, value = part.split("=", 1)
                if name not in opt_names:
                    continue
            elif part in opt_names and index + 1 < len(lowered):
                value = lowered[index + 1]
            else:
                continue
            normalized = value.replace("\\", "/").rstrip("/")
            if (
                normalized in susp_vals
                or any(normalized.startswith(item.rstrip("/") + "/") for item in susp_vals)
                or any(f"source={item}" in normalized or f"src={item}" in normalized or f"{item}:" in normalized for item in susp_vals)
            ):
                return True
        return False



    except Exception:
        return False
def _is_env_assignment(value: str) -> bool:
    if not isinstance(value, str): value = str(value or '')
    try:
        return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*", str(value or "")))



    except Exception:
        return False
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
    argv_list = argv if isinstance(argv, list) else list(argv) if isinstance(argv, (tuple, set)) else []
    requires = action_class != "none"
    phrase = confirmation_phrase
    ctx_non_interactive = getattr(context, "non_interactive", False)
    ctx_surface = getattr(context, "surface", "cli")
    if requires and not phrase:
        noun = target_display or action_class.replace("_", " ")
        phrase = f"approve {noun}".strip().lower()[:80]
    return ApprovalDecision(
        action_class=action_class,
        risk=risk,
        requires_approval=requires,
        approval_mode="blocked" if requires and ctx_non_interactive else "interactive" if requires else "none",
        reason=reason,
        target_display=target_display,
        command_digest=_digest_command(argv_list),
        confirmation_phrase=phrase,
        surface=ctx_surface,
    )


def parse_command_text(command: str) -> list[str]:
    cmd_str = str(command or "")
    try:
        return shlex.split(cmd_str, posix=True)
    except ValueError:
        return cmd_str.split()


def approval_required_for_command(argv: list[str], context: CommandContext | None = None) -> ApprovalDecision:
    ctx = context if isinstance(context, CommandContext) else CommandContext()
    argv_list = argv if isinstance(argv, list) else list(argv) if isinstance(argv, (tuple, set)) else []
    parts = [str(part or "") for part in argv_list if str(part or "") != "--"]
    lowered = _lower_parts(parts)
    if not lowered:
        return _decision(parts, ctx, "none", "none", "Empty command.")

    joined = " ".join(lowered)
    first = lowered[0]
    second = lowered[1] if len(lowered) > 1 else ""

    if first in {"sudo", "doas"}:
        nested = approval_required_for_command(parts[1:], ctx) if len(parts) > 1 else None
        if nested and nested.requires_approval:
            return nested
        return _decision(
            parts,
            ctx,
            "identity_access_mutation",
            "high",
            "Command runs through a privilege-elevation wrapper.",
            target_display=" ".join(parts[:3]),
            confirmation_phrase="approve privilege escalation",
        )

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
        len(lowered) == 1
        or any(re.search(r"(?i)(token|secret|password|api[_-]?key|credential)", part) for part in lowered[1:])
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

    if first == "aws" and (
        lowered[1:3] in [["secretsmanager", "get-secret-value"], ["ssm", "get-parameter"]]
        or ("configure" in lowered and "get" in lowered and any("secret" in part or "key" in part for part in lowered))
    ):
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "critical",
            "AWS command can reveal cloud secrets or decrypted parameters.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve cloud secret reveal",
        )

    if first == "kubectl" and len(lowered) > 2 and lowered[1] in {"get", "describe"} and lowered[2] in {"secret", "secrets"}:
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "critical",
            "Kubernetes command can reveal cluster secrets.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve kubernetes secret reveal",
        )

    if first == "docker" and second == "login":
        return _decision(
            parts,
            ctx,
            "credential_mutation",
            "high",
            "Docker command can store or change registry credentials.",
            target_display="docker login",
            confirmation_phrase="approve docker credential change",
        )

    if first in {"curl", "wget", "iwr", "invoke-webrequest"} and re.search(
        r"\b(?:bash|sh|powershell|pwsh|iex|invoke-expression|python|node)\b",
        joined,
    ):
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
    if (
        (first == "git" and second == "push")
        or (first in {"npm", "pnpm", "yarn"} and second == "publish")
        or (first == "twine" and second == "upload")
        or (first == "cargo" and second == "publish")
        or (first == "gem" and second == "push")
        or (first == "nuget" and second == "push")
        or (first == "helm" and second == "push")
        or (first == "docker" and second == "push")
        or (first == "prisma" and lowered[1:3] == ["migrate", "deploy"])
        or (first == "alembic" and second in {"upgrade", "downgrade"})
        or (first in {"az", "gcloud", "supabase"} and _contains_any(lowered, {"deploy", "push", "up"}))
        or joined.startswith("gh release create")
    ):
        return _decision(
            parts,
            ctx,
            "external_publish",
            "high",
            "Command can publish code, packages, releases, or tags outside this machine.",
            target_display=" ".join(parts[:4]),
            confirmation_phrase="approve publish",
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
    if first in {"schtasks", "setx", "reg", "systemctl", "launchctl"}:
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
    if first in {"curl", "wget"} and (
        _contains_any(
            lowered,
            {"--upload-file", "--form", "--data", "--data-binary", "--data-raw", "--data-urlencode"},
        )
        or _contains_any(parts, {"-F", "-T"})
    ):
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
