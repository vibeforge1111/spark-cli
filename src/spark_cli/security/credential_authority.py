from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


CredentialActionClass = Literal["credential_mutation", "identity_access_mutation"]
CredentialRisk = Literal["high", "critical"]


@dataclass(frozen=True)
class CredentialAuthority:
    action_class: CredentialActionClass
    risk: CredentialRisk
    reason: str
    target_display: str
    confirmation_phrase: str


PACKAGE_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(?:authtoken|(?:^|[:._-])(?:auth(?:token)?|_auth|password|credential|secret|api[_-]?key)(?:[:._-]|$))"
)
PIP_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(?:index[-_.]?url|extra[-_.]?index[-_.]?url|trusted[-_.]?host|client[-_.]?cert|cert|proxy|password|token|auth|username)"
)
PYTHON_EXECUTABLE_PATTERN = re.compile(r"python(?:\d+(?:\.\d+)*)?$")
PIP_EXECUTABLE_PATTERN = re.compile(r"pip(?:\d+(?:\.\d+)*)?$")

PROVIDER_AUTH_MUTATIONS = frozenset(
    {
        ("huggingface-cli", "login"),
        ("huggingface-cli", "logout"),
        ("hf", "auth", "login"),
        ("hf", "auth", "logout"),
        ("modal", "token", "clear"),
        ("modal", "token", "delete"),
        ("modal", "token", "remove"),
        ("modal", "token", "set"),
        ("wandb", "login"),
        ("wandb", "logout"),
    }
)
CLOUD_TOKEN_REVEALS = frozenset(
    {
        ("az", "account", "get-access-token"),
        ("gcloud", "auth", "application-default", "print-access-token"),
        ("gcloud", "auth", "print-access-token"),
    }
)
CLOUD_AUTH_MUTATIONS = frozenset(
    {
        ("az", "login"),
        ("az", "logout"),
        ("gcloud", "auth", "activate-service-account"),
        ("gcloud", "auth", "application-default", "login"),
        ("gcloud", "auth", "application-default", "revoke"),
        ("gcloud", "auth", "login"),
        ("gcloud", "auth", "revoke"),
    }
)
GITHUB_AUTH_MUTATIONS = frozenset(
    {
        ("gh", "auth", "login"),
        ("gh", "auth", "logout"),
        ("gh", "auth", "refresh"),
        ("gh", "auth", "setup-git"),
        ("gh", "auth", "switch"),
    }
)
PACKAGE_AUTH_MUTATIONS = frozenset(
    {
        ("npm", "adduser"),
        ("npm", "login"),
        ("npm", "logout"),
        ("npm", "token", "create"),
        ("npm", "token", "delete"),
        ("npm", "token", "revoke"),
        ("pnpm", "adduser"),
        ("pnpm", "login"),
        ("pnpm", "logout"),
        ("pnpm", "token", "create"),
        ("pnpm", "token", "delete"),
        ("pnpm", "token", "revoke"),
        ("yarn", "npm", "login"),
        ("yarn", "npm", "logout"),
    }
)


def _command_word(value: str) -> str:
    word = value.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"\.(?:exe|cmd|bat)$", "", word)


def _authority(
    action_class: CredentialActionClass,
    risk: CredentialRisk,
    reason: str,
    target: str,
    phrase: str,
) -> CredentialAuthority:
    return CredentialAuthority(action_class, risk, reason, target, phrase)


def _matches_prefix(words: list[str], prefixes: frozenset[tuple[str, ...]]) -> bool:
    return any(tuple(words[: len(prefix)]) == prefix for prefix in prefixes)


def _before_separator(arguments: list[str]) -> list[str]:
    try:
        return arguments[: arguments.index("--")]
    except ValueError:
        return arguments


def _short_flag(arguments: list[str], flag: str) -> bool:
    return any(
        argument.startswith("-")
        and not argument.startswith("--")
        and argument != "-"
        and flag in argument[1:]
        for argument in _before_separator(arguments)
    )


def _pip_config_arguments(parts: list[str]) -> list[str] | None:
    if not parts:
        return None
    executable = _command_word(parts[0])
    lowered = [part.lower() for part in parts]
    if PIP_EXECUTABLE_PATTERN.fullmatch(executable) and lowered[1:2] == ["config"]:
        return parts[2:]
    if executable == "py" or PYTHON_EXECUTABLE_PATTERN.fullmatch(executable):
        for index, argument in enumerate(lowered[1:], start=1):
            if argument != "-m":
                continue
            if lowered[index + 1 : index + 3] == ["pip", "config"]:
                return parts[index + 3 :]
            return None
    return None


def _pip_config_sensitive(arguments: list[str]) -> bool:
    if not arguments:
        return False
    lowered = [argument.lower() for argument in arguments]
    action_index = next((index for index, argument in enumerate(lowered) if not argument.startswith("-")), None)
    if action_index is None:
        return False
    action = lowered[action_index]
    if action in {"debug", "list"}:
        return True
    if action not in {"get", "set", "unset"} or action_index + 1 >= len(arguments):
        return False
    key = arguments[action_index + 1].split("=", 1)[0]
    return bool(PIP_SENSITIVE_KEY_PATTERN.search(key))


def _package_config_key(parts: list[str]) -> str:
    if len(parts) < 4 or _command_word(parts[0]) not in {"npm", "pnpm", "yarn"}:
        return ""
    lowered = [part.lower() for part in parts]
    if lowered[1] != "config" or lowered[2] not in {"delete", "get", "remove", "rm", "set", "unset"}:
        return ""
    return parts[3].split("=", 1)[0]


def _password_manager_read(parts: list[str]) -> bool:
    if not parts:
        return False
    lowered = [part.lower() for part in parts]
    first = _command_word(parts[0])
    second = lowered[1] if len(lowered) > 1 else ""
    third = lowered[2] if len(lowered) > 2 else ""
    if first == "pass" and second in {"otp", "show"}:
        return True
    if first == "op" and (second == "read" or lowered[1:3] in (["item", "get"], ["document", "get"])):
        return True
    if first == "bw" and second == "get" and third in {"item", "notes", "password", "totp"}:
        return True
    if first == "security" and second in {"find-generic-password", "find-internet-password"} and "-w" in lowered:
        return True
    return first == "secret-tool" and second == "lookup"


def _sensitive_file_target(arguments: list[str]) -> bool:
    exact_leaves = {
        ".netrc",
        ".npmrc",
        ".pypirc",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
    }
    env_examples = {".env.example", ".env.sample", ".env.template"}
    suffixes = (
        "/.aws/credentials",
        "/.config/gcloud/application_default_credentials.json",
        "/.docker/config.json",
    )
    for argument in arguments:
        if not argument or argument.startswith("-"):
            continue
        normalized = argument.lower().replace("\\", "/").rstrip("/")
        leaf = normalized.rsplit("/", 1)[-1]
        if leaf in env_examples:
            continue
        if leaf in exact_leaves or leaf == ".env" or leaf.startswith(".env.") or normalized.endswith(suffixes):
            return True
    return False


def parse_credential_authority(parts: list[str]) -> CredentialAuthority | None:
    if not parts:
        return None
    executable = _command_word(parts[0])
    arguments = parts[1:]
    lowered = [part.lower() for part in parts]
    command_words = [executable, *[part.lower() for part in parts[1:]]]
    bounded_arguments = _before_separator(arguments)

    if _matches_prefix(command_words, CLOUD_TOKEN_REVEALS):
        return _authority(
            "credential_mutation",
            "critical",
            "Cloud CLI command can reveal an active access token.",
            "cloud access token",
            "approve cloud token reveal",
        )

    if command_words[:3] == ["gh", "auth", "token"]:
        return _authority(
            "credential_mutation",
            "critical",
            "GitHub command can reveal the active authentication token.",
            "gh auth token",
            "approve github token reveal",
        )

    if _matches_prefix(command_words, PROVIDER_AUTH_MUTATIONS):
        return _authority(
            "credential_mutation",
            "high",
            "Provider auth command can store, replace, or remove local service credentials.",
            "provider auth credentials",
            "approve provider auth change",
        )

    if _matches_prefix(command_words, CLOUD_AUTH_MUTATIONS):
        return _authority(
            "credential_mutation",
            "high",
            "Cloud CLI auth command can store, replace, or remove local cloud credentials.",
            "cloud auth credentials",
            "approve cloud auth change",
        )

    if _matches_prefix(command_words, GITHUB_AUTH_MUTATIONS):
        return _authority(
            "credential_mutation",
            "high",
            "GitHub CLI auth command can store, remove, switch, or expand local GitHub credentials.",
            "github cli auth",
            "approve github auth change",
        )

    if _matches_prefix(command_words, PACKAGE_AUTH_MUTATIONS):
        return _authority(
            "credential_mutation",
            "high",
            "Package manager auth command can store, remove, create, or revoke registry credentials.",
            "package manager auth",
            "approve package auth change",
        )

    pip_config = _pip_config_arguments(parts)
    if pip_config is not None and _pip_config_sensitive(pip_config):
        return _authority(
            "credential_mutation",
            "high",
            "pip config can reveal or mutate package-index credentials and credential-bearing routing.",
            "pip credential config",
            "approve pip config access",
        )

    if executable in {"gpg", "gpg2"} and any(
        argument in {
            "--delete-secret-and-public-keys",
            "--delete-secret-keys",
            "--export-secret-keys",
            "--export-secret-subkeys",
        }
        for argument in bounded_arguments
    ):
        return _authority(
            "credential_mutation",
            "critical",
            "GPG can export or delete private key material.",
            "gpg secret key",
            "approve gpg secret key access",
        )

    if executable == "ssh-keygen" and (_short_flag(arguments, "p") or _short_flag(arguments, "y")):
        return _authority(
            "identity_access_mutation",
            "high",
            "ssh-keygen can read a private key or mutate its passphrase.",
            "ssh-keygen private key",
            "approve ssh key access",
        )

    if _password_manager_read(parts):
        return _authority(
            "credential_mutation",
            "critical",
            "Password-manager commands can reveal stored secrets, documents, or one-time passwords.",
            "password manager secret",
            "approve password manager access",
        )

    package_key = _package_config_key(parts)
    if package_key and PACKAGE_CREDENTIAL_PATTERN.search(package_key):
        return _authority(
            "credential_mutation",
            "critical",
            "Package-manager config can reveal, store, or remove registry credentials.",
            "package manager credentials",
            "approve package credential access",
        )

    if executable in {"cat", "grep", "head", "less", "more", "rg", "tail"} and _sensitive_file_target(arguments):
        return _authority(
            "credential_mutation",
            "high",
            "File inspection can reveal credential files or private key material.",
            "credential file",
            "approve credential file read",
        )

    if executable in {"age", "gpg", "gpg2", "sops"} and (
        "--decrypt" in bounded_arguments or _short_flag(arguments, "d")
    ):
        return _authority(
            "credential_mutation",
            "high",
            "The command can decrypt protected secret material.",
            "encrypted secret",
            "approve secret decrypt",
        )

    return None


def decide_credential_authority(parts: list[str], context: Any, decision_factory: Callable[..., Any]) -> Any:
    authority = parse_credential_authority(parts)
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
