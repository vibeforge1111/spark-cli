from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


NetworkRisk = Literal["medium", "high"]
TransferDirection = Literal["upload", "download", "remote", "local", "read"]


@dataclass(frozen=True)
class NetworkAuthority:
    risk: NetworkRisk
    reason: str
    target_display: str
    confirmation_phrase: str


@dataclass(frozen=True)
class OutboundTransferAction:
    transport: str
    direction: TransferDirection
    target: str


SHELL_CONTROL_MARKERS = frozenset({"&&", "||", "|", ";", "&"})
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
SSH_FORWARD_VALUE_OPTIONS = frozenset({"-D", "-L", "-R", "-W"})
SSH_OTHER_VALUE_OPTIONS = frozenset(
    {"-b", "-B", "-c", "-E", "-e", "-F", "-I", "-i", "-J", "-l", "-m", "-O", "-o", "-P", "-p", "-Q", "-S", "-w"}
)
SSH_FORWARD_CONFIG_KEYS = frozenset({"dynamicforward", "localforward", "remoteforward"})
CURL_UPLOAD_LONG_OPTIONS = frozenset(
    {
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
)
WGET_UPLOAD_LONG_OPTIONS = frozenset(
    {"--body-data", "--body-file", "--post-data", "--post-file", "--upload-file"}
)
FTP_UPLOAD_VERBS = frozenset({"append", "mput", "put", "reput", "send"})
SOCAT_FILE_PREFIXES = ("file:", "open:")
SOCAT_NETWORK_PREFIXES = ("tcp:", "tcp4:", "tcp6:", "ssl:", "tls:", "udp:", "udp4:", "udp6:")


def _command_word(value: str) -> str:
    normalized = value.strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    normalized = normalized.lstrip("&|;(")
    match = re.match(r"[a-z][a-z0-9_.-]*", normalized)
    if not match:
        return ""
    return re.sub(r"\.(?:exe|cmd|bat)$", "", match.group(0))


def _segments(parts: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for part in parts:
        for chunk in re.split(r"(&&|\|\||[|;&])", part):
            if not chunk:
                continue
            if chunk in SHELL_CONTROL_MARKERS:
                if current:
                    segments.append(current)
                    current = []
            else:
                current.append(chunk)
    if current:
        segments.append(current)
    return segments


def _option_name_and_value(part: str) -> tuple[str, str]:
    lowered = part.lower()
    if not lowered.startswith("-"):
        return "", ""
    for separator in ("=", ":"):
        if separator in lowered:
            name, value = lowered.split(separator, 1)
            return name, value
    return lowered, ""


def _option_values(parts: list[str], option_names: frozenset[str]) -> list[str]:
    values: list[str] = []
    lowered = [part.lower() for part in parts]
    for index, part in enumerate(lowered):
        name, attached = _option_name_and_value(part)
        if name in option_names and attached:
            values.append(attached)
        elif part in option_names and index + 1 < len(parts):
            values.append(parts[index + 1].lower())
    return values


def _positionals_after(parts: list[str], start: int, *, value_options: frozenset[str]) -> list[str]:
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
    lowered = [part.lower() for part in parts]
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


def _has_network_upload_option(command: str, parts: list[str]) -> bool:
    long_options = CURL_UPLOAD_LONG_OPTIONS if command == "curl" else WGET_UPLOAD_LONG_OPTIONS
    for part in parts[1:]:
        lowered = part.lower()
        if lowered in long_options or any(lowered.startswith(f"{option}=") for option in long_options):
            return True
        if command == "curl" and part.startswith("-") and not part.startswith("--"):
            if any(flag in part[1:] for flag in {"F", "T", "d"}):
                return True
    return False


def network_upload_option(command: str, parts: list[str]) -> bool:
    """Return whether curl/wget arguments carry an upload payload."""
    return command in {"curl", "wget"} and _has_network_upload_option(command, parts)


def _httpie_upload(parts: list[str]) -> bool:
    if not parts or _command_word(parts[0]) not in {"http", "https"}:
        return False
    return any(re.match(r"^[^=@:]+@[^@]+$", part) for part in parts[1:])


def _contains_ftp_upload_verb(parts: list[str]) -> bool:
    for part in parts:
        if part.startswith("-"):
            continue
        tokens = {token for token in re.split(r"[^A-Za-z0-9_-]+", part.lower()) if token}
        if tokens & FTP_UPLOAD_VERBS:
            return True
    return False


def _ftp_upload(parts: list[str]) -> bool:
    if not parts:
        return False
    executable = _command_word(parts[0])
    lowered = [part.lower() for part in parts]
    if executable == "ftp":
        return any(part in {"-u", "--upload-file"} for part in lowered[1:]) or _contains_ftp_upload_verb(parts[1:])
    if executable == "lftp":
        reverse_mirror = any("mirror" in part.lower() for part in parts[1:]) and any(
            part in {"-r", "--reverse"} or part == "-R" for part in parts[1:]
        )
        return reverse_mirror or _contains_ftp_upload_verb(parts[1:])
    if executable == "sftp":
        return any(part.lower() in {"-b", "-bb", "-batchfile"} for part in parts[1:]) or _contains_ftp_upload_verb(parts[1:])
    return False


def _has_input_redirection(parts: list[str]) -> bool:
    return "<" in parts or any(part.startswith("<") and len(part) > 1 for part in parts)


def _raw_socket_file_upload(parts: list[str]) -> bool:
    if not parts:
        return False
    executable = _command_word(parts[0])
    lowered = [part.lower() for part in parts]
    if executable in {"nc", "ncat", "netcat"}:
        if any(
            part in {"-c", "-e", "--exec", "--sh-exec"}
            or part.startswith(("--exec=", "--sh-exec="))
            for part in lowered[1:]
        ):
            return False
        return _has_input_redirection(parts[1:])
    if executable == "socat":
        if any("exec:" in part or "system:" in part for part in lowered[1:]):
            return False
        has_file_source = any(part.startswith(SOCAT_FILE_PREFIXES) for part in lowered[1:])
        has_network_target = any(part.startswith(SOCAT_NETWORK_PREFIXES) for part in lowered[1:])
        return has_file_source and has_network_target
    return False


def _openssl_file_upload(parts: list[str]) -> bool:
    return (
        len(parts) > 1
        and _command_word(parts[0]) == "openssl"
        and parts[1].lower() == "s_client"
        and _has_input_redirection(parts[2:])
    )


def _strip_bind_port(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.startswith("[") and "]" in normalized:
        return normalized[1 : normalized.index("]")]
    if normalized.count(":") == 1:
        host, port = normalized.rsplit(":", 1)
        if port.isdigit():
            return host
    return normalized


def _is_loopback_bind(value: str) -> bool:
    host = _strip_bind_port(value)
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _public_file_server(parts: list[str]) -> bool:
    if not parts:
        return False
    executable = _command_word(parts[0])
    lowered = [part.lower() for part in parts]
    if any(part in {"-h", "--help", "-v", "--version"} for part in lowered[1:]):
        return False

    python_executable = executable in {"py", "python", "python2", "python3"} or bool(
        re.fullmatch(r"python\d+(?:\.\d+)?", executable)
    )
    if python_executable and "-m" in lowered:
        module_index = lowered.index("-m")
        if module_index + 1 < len(lowered) and lowered[module_index + 1] == "http.server":
            binds = _option_values(parts, frozenset({"--bind", "-b"}))
            return not binds or any(not _is_loopback_bind(value) for value in binds)

    if executable == "php" and "-s" in lowered:
        server_index = lowered.index("-s")
        return server_index + 1 >= len(parts) or not _is_loopback_bind(parts[server_index + 1])

    httpd_offset = 1 if executable == "httpd" else 2 if executable == "busybox" and lowered[1:2] == ["httpd"] else 0
    if httpd_offset:
        binds = _option_values(parts[httpd_offset - 1 :], frozenset({"-p", "--port"}))
        return not binds or any(not _is_loopback_bind(value) for value in binds)
    return False


def _has_help_or_version(parts: list[str]) -> bool:
    return any(part.lower() in {"-h", "--help", "-v", "--version", "help", "version"} for part in parts[1:])


def _public_tunnel(parts: list[str]) -> bool:
    if not parts or _has_help_or_version(parts):
        return False
    executable = _command_word(parts[0])
    lowered = [part.lower() for part in parts]
    second = lowered[1] if len(lowered) > 1 else ""
    if executable == "ngrok":
        return second in {"http", "tcp", "start"}
    if executable == "cloudflared" and second == "tunnel":
        return "--url" in lowered or any(part.startswith("--url=") for part in lowered) or "run" in lowered[2:]
    if executable in {"lt", "localtunnel"}:
        return len(parts) > 1
    return False


def _ssh_config_key(value: str) -> str:
    normalized = value.strip().lower()
    return re.split(r"[=\s]", normalized, maxsplit=1)[0].replace("-", "")


def _ssh_has_tunnel(parts: list[str]) -> bool:
    if not parts or _command_word(parts[0]) != "ssh":
        return False

    index = 1
    config_only = False
    tunnel = False
    while index < len(parts):
        part = parts[index]
        if part == "--":
            return tunnel and not config_only
        if not part.startswith("-") or part == "-":
            return tunnel and not config_only
        if not part.startswith("--") and "G" in part[1:]:
            config_only = True
        option = part[:2]
        if part in SSH_FORWARD_VALUE_OPTIONS:
            if index + 1 >= len(parts) or not parts[index + 1]:
                return False
            tunnel = True
            index += 2
            continue
        if option in SSH_FORWARD_VALUE_OPTIONS and len(part) > 2:
            tunnel = True
            index += 1
            continue
        if part == "-o":
            if index + 1 >= len(parts):
                return False
            if _ssh_config_key(parts[index + 1]) in SSH_FORWARD_CONFIG_KEYS:
                tunnel = True
            index += 2
            continue
        if option == "-o" and len(part) > 2:
            if _ssh_config_key(part[2:]) in SSH_FORWARD_CONFIG_KEYS:
                tunnel = True
            index += 1
            continue
        if part in SSH_OTHER_VALUE_OPTIONS:
            if index + 1 >= len(parts):
                return False
            index += 2
            continue
        if option in SSH_OTHER_VALUE_OPTIONS and len(part) > 2:
            index += 1
            continue
        index += 1
    return False


def parse_ssh_tunnel_authority(parts: list[str]) -> NetworkAuthority | None:
    if not _ssh_has_tunnel(parts):
        return None
    return NetworkAuthority(
        risk="high",
        reason="SSH forwarding can expose or relay network services through another host.",
        target_display="ssh tunnel",
        confirmation_phrase="approve ssh tunnel",
    )


def _parse_upload(parts: list[str]) -> OutboundTransferAction | None:
    if not parts:
        return None
    executable = _command_word(parts[0])
    action = (
        _parse_powershell_web_transfer(parts)
        or _parse_remote_copy_transfer(parts)
        or _parse_cloud_storage_transfer(parts)
    )
    if action is not None:
        return action
    if executable in {"curl", "wget"} and _has_network_upload_option(executable, parts):
        return OutboundTransferAction(executable, "upload", executable)
    if _httpie_upload(parts):
        return OutboundTransferAction(executable, "upload", executable)
    if _ftp_upload(parts):
        return OutboundTransferAction(executable, "upload", executable)
    if _raw_socket_file_upload(parts):
        return OutboundTransferAction(executable, "upload", executable)
    if _openssl_file_upload(parts):
        return OutboundTransferAction("openssl s_client", "upload", "openssl s_client")
    return None


def parse_network_authority(parts: list[str]) -> NetworkAuthority | None:
    for segment in _segments(parts):
        if _public_file_server(segment):
            return NetworkAuthority(
                risk="high",
                reason="Command can serve local files on a non-loopback network interface.",
                target_display="public file server",
                confirmation_phrase="approve public file server",
            )
        if _public_tunnel(segment):
            return NetworkAuthority(
                risk="high",
                reason="Command can expose a local service through a public tunnel.",
                target_display="public tunnel",
                confirmation_phrase="approve public tunnel",
            )
        action = _parse_upload(segment)
        if action is not None and action.direction == "upload":
            return NetworkAuthority(
                risk="medium",
                reason="Command can transfer local data to a remote system or network endpoint.",
                target_display=action.transport,
                confirmation_phrase="approve network upload",
            )
    return None


def _decide(parts: list[str], context: Any, decision_factory: Callable[..., Any], authority: NetworkAuthority | None) -> Any:
    if authority is None:
        return None
    return decision_factory(
        parts,
        context,
        "network_exfiltration",
        authority.risk,
        authority.reason,
        target_display=authority.target_display,
        confirmation_phrase=authority.confirmation_phrase,
    )


def decide_ssh_tunnel_authority(parts: list[str], context: Any, decision_factory: Callable[..., Any]) -> Any:
    return _decide(parts, context, decision_factory, parse_ssh_tunnel_authority(parts))


def decide_network_authority(parts: list[str], context: Any, decision_factory: Callable[..., Any]) -> Any:
    return _decide(parts, context, decision_factory, parse_network_authority(parts))
