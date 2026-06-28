from __future__ import annotations

import json
import hashlib
import ipaddress
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .audit import sandbox_audit_ref, write_audit_event
from .capabilities import CapabilityManifest
from .output import bound_sandbox_output
from .paths import ssh_known_hosts_path, ssh_targets_path, validate_target_name


SSH_TARGETS_SCHEMA_VERSION = 1
SSH_HOST_PATTERN = re.compile(r"^[A-Za-z0-9.:-]+$")
SSH_USER_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}\$?$")
SSH_REMOTE_WORKSPACE_PATTERN = re.compile(r"^(?:~(?:/|$)|/)[A-Za-z0-9._~@%+=:,/-]*$")
SSH_SUBPROCESS_ENV_ALLOWLIST = {
    "APPDATA",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
}
SSH_SMOKE_PROBE = """#!/bin/sh
set -eu
printf 'SPARK_SSH_SMOKE_OK\\n'
printf 'probe_sha256=%s\\n' "${1:-missing}"
printf 'remote_uid=%s\\n' "$(id -u)"
"""


@dataclass(frozen=True)
class SshTarget:
    name: str
    host: str
    user: str
    port: int
    identity_file: str
    remote_workspace: str
    host_key_status: str
    host_key_fingerprint: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_public_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("identity_file", None)
        payload["identity_file_configured"] = bool(self.identity_file)
        return payload


@dataclass(frozen=True)
class SshDoctorCheck:
    name: str
    ok: bool
    detail: str
    repair: str = ""
    level: str = "error"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SshHostKeyScan:
    known_hosts_line: str
    fingerprint: str
    key_type: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def ssh_management_capabilities() -> CapabilityManifest:
    try:
        return CapabilityManifest(
            backend="ssh",
            filesystem="none",
            network="off",
            secrets="none",
            persistence="named-target",
            privilege="non-root",
            inbound="none",
            cost="free-local",
        )



    except Exception:
        return None
def ssh_smoke_capabilities() -> CapabilityManifest:
    try:
        return CapabilityManifest(
            backend="ssh",
            filesystem="temp",
            network="allowlist",
            secrets="none",
            persistence="session",
            privilege="non-root",
            inbound="none",
            cost="free-local",
        )



    except Exception:
        return None
def _timestamp() -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())



    except Exception:
        return ""
def ssh_subprocess_env(env: dict[str, str] | None = None) -> dict[str, str]:
    if not isinstance(env, str): env = str(env or '')
    try:
        source = os.environ if env is None else env
        return {
            key: value
            for key, value in source.items()
            if key.upper() in SSH_SUBPROCESS_ENV_ALLOWLIST
        }



    except Exception:
        return {}
def _parse_ipv4_number(value: str) -> int | None:
    try:
        if value.lower().startswith("0x"):
            return int(value[2:], 16)
        if len(value) > 1 and value.startswith("0"):
            return int(value[1:] or "0", 8)
        return int(value, 10)
    except ValueError:
        return None


def _legacy_ipv4_address(host: str) -> ipaddress.IPv4Address | None:
    if not host or not all(char in "0123456789abcdefABCDEFxX." for char in host):
        return None
    parts = host.split(".")
    if len(parts) > 4 or any(part == "" for part in parts):
        return None
    numbers = [_parse_ipv4_number(part) for part in parts]
    if any(number is None for number in numbers):
        return None
    octets: list[int]
    if len(numbers) == 1:
        value = int(numbers[0])
        if value > 0xFFFFFFFF:
            return None
        octets = [
            (value >> 24) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ]
    elif len(numbers) == 2:
        first, rest = (int(number) for number in numbers)
        if first > 0xFF or rest > 0xFFFFFF:
            return None
        octets = [first, (rest >> 16) & 0xFF, (rest >> 8) & 0xFF, rest & 0xFF]
    elif len(numbers) == 3:
        first, second, rest = (int(number) for number in numbers)
        if first > 0xFF or second > 0xFF or rest > 0xFFFF:
            return None
        octets = [first, second, (rest >> 8) & 0xFF, rest & 0xFF]
    else:
        if any(int(number) > 0xFF for number in numbers):
            return None
        octets = [int(number) for number in numbers]
    return ipaddress.IPv4Address(bytes(octets))


def _ssh_host_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return _legacy_ipv4_address(host)


def _is_metadata_host(value: str) -> bool:
    if value == "metadata.google.internal":
        return True
    ip = _ssh_host_ip(value)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip == ipaddress.ip_address("169.254.169.254") or ip == ipaddress.ip_address("fd00:ec2::254")


def validate_ssh_host(host: str) -> str:
    value = str(host or "").strip().lower().rstrip(".")
    if not value:
        raise ValueError("SSH host is required.")
    if "://" in value or "/" in value or "\\" in value or "@" in value:
        raise ValueError("SSH host must be a hostname or IP address, not a URL or user@host string.")
    if not SSH_HOST_PATTERN.fullmatch(value) or value.startswith("-"):
        raise ValueError("SSH host contains unsupported characters.")
    if _is_metadata_host(value):
        raise ValueError("SSH host must not point at a cloud metadata service.")
    return value


def validate_ssh_user(user: str) -> str:
    value = str(user or "").strip()
    if value == "root":
        raise ValueError("SSH sandbox targets must use a non-root user.")
    if not SSH_USER_PATTERN.fullmatch(value):
        raise ValueError("SSH user must be a simple non-root account name.")
    return value


def validate_remote_workspace(path: str) -> str:
    value = str(path or "").strip()
    if not value:
        raise ValueError("SSH remote workspace is required.")
    if not SSH_REMOTE_WORKSPACE_PATTERN.fullmatch(value):
        raise ValueError("SSH remote workspace must be an absolute or home-relative path without spaces or shell metacharacters.")
    if "/../" in value or value.endswith("/..") or value == "..":
        raise ValueError("SSH remote workspace must not traverse parent directories.")
    return value


def validate_ssh_port(port: int) -> int:
    try:
        value = int(port)
    except (TypeError, ValueError) as error:
        raise ValueError("SSH port must be an integer.") from error
    if value < 1 or value > 65535:
        raise ValueError("SSH port must be between 1 and 65535.")
    return value


def resolve_identity_file(path: str | Path) -> tuple[Path, list[str]]:
    value = str(path or "").strip()
    if not value:
        raise ValueError("SSH identity file is required.")
    candidate = Path(value).expanduser()
    if not candidate.exists():
        raise ValueError(f"SSH identity file does not exist: {candidate}")
    if not candidate.is_file():
        raise ValueError(f"SSH identity path is not a file: {candidate}")
    resolved = candidate.resolve()
    warnings: list[str] = []
    if os.name != "nt":
        mode = stat.S_IMODE(resolved.stat().st_mode)
        if mode & 0o077:
            warnings.append("SSH identity file is readable by group/other users; run chmod 600 on the key.")
    return resolved, warnings


def _target_from_dict(name: str, data: dict[str, Any]) -> SshTarget:
    return SshTarget(
        name=validate_target_name(str(data.get("name") or name)),
        host=validate_ssh_host(str(data.get("host") or "")),
        user=validate_ssh_user(str(data.get("user") or "")),
        port=validate_ssh_port(int(data.get("port") or 22)),
        identity_file=str(data.get("identity_file") or ""),
        remote_workspace=validate_remote_workspace(str(data.get("remote_workspace") or "~/spark-live")),
        host_key_status=str(data.get("host_key_status") or "unverified"),
        host_key_fingerprint=str(data.get("host_key_fingerprint") or ""),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
    )


def load_ssh_targets(*, home: Path | None = None) -> dict[str, SshTarget]:
    path = ssh_targets_path(home)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("SSH target store is not valid JSON.") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != SSH_TARGETS_SCHEMA_VERSION:
        raise ValueError("Unsupported SSH target store schema.")
    targets = payload.get("targets")
    if not isinstance(targets, dict):
        raise ValueError("SSH target store is missing a targets object.")
    return {validate_target_name(name): _target_from_dict(name, data) for name, data in targets.items() if isinstance(data, dict)}


def save_ssh_targets(targets: dict[str, SshTarget], *, home: Path | None = None) -> Path:
    path = ssh_targets_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SSH_TARGETS_SCHEMA_VERSION,
        "targets": {name: target.to_dict() for name, target in sorted(targets.items())},
    }
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def add_ssh_target(
    *,
    name: str,
    host: str,
    user: str,
    identity_file: str | Path,
    port: int = 22,
    remote_workspace: str = "~/spark-live",
    home: Path | None = None,
) -> tuple[SshTarget, list[str]]:
    safe_name = validate_target_name(name)
    safe_host = validate_ssh_host(host)
    safe_user = validate_ssh_user(user)
    safe_port = validate_ssh_port(port)
    safe_remote_workspace = validate_remote_workspace(remote_workspace)
    key_path, warnings = resolve_identity_file(identity_file)
    targets = load_ssh_targets(home=home)
    now = _timestamp()
    existing = targets.get(safe_name)
    target = SshTarget(
        name=safe_name,
        host=safe_host,
        user=safe_user,
        port=safe_port,
        identity_file=str(key_path),
        remote_workspace=safe_remote_workspace,
        host_key_status="unverified",
        host_key_fingerprint="",
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    targets[safe_name] = target
    save_ssh_targets(targets, home=home)
    write_audit_event(
        "ssh",
        safe_name,
        {
            "action_id": "ssh_target_update" if existing else "ssh_target_add",
            "ok": True,
            "host": target.host,
            "port": target.port,
            "user": target.user,
            "identity_file_configured": True,
        },
        home=home,
    )
    return target, warnings


def remove_ssh_target(name: str, *, home: Path | None = None) -> bool:
    safe_name = validate_target_name(name)
    targets = load_ssh_targets(home=home)
    existed = safe_name in targets
    if existed:
        del targets[safe_name]
        save_ssh_targets(targets, home=home)
        write_audit_event(
            "ssh",
            safe_name,
            {
                "action_id": "ssh_target_remove",
                "ok": True,
            },
            home=home,
        )
    return existed


def list_ssh_targets(*, home: Path | None = None) -> list[SshTarget]:
    return list(load_ssh_targets(home=home).values())


def ssh_host_alias(target: SshTarget) -> str:
    return f"[{target.host}]:{target.port}" if target.port != 22 else target.host


def ssh_keyscan_argv(target: SshTarget) -> list[str]:
    return ["ssh-keyscan", "-T", "10", "-p", str(target.port), target.host]


def parse_ssh_keyscan_output(output: str, target: SshTarget) -> str:
    alias = ssh_host_alias(target)
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        hosts = parts[0].split(",")
        key_type = parts[1]
        if alias in hosts or target.host in hosts:
            return f"{alias} {key_type} {parts[2]}"
    raise ValueError(f"ssh-keyscan returned no usable host key for {alias}.")


def fingerprint_known_host_line(line: str) -> SshHostKeyScan:
    parts = line.split()
    if len(parts) < 3:
        raise ValueError("Known-host line is incomplete.")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "known_hosts"
        path.write_text(line + "\n", encoding="utf-8")
        result = subprocess.run(
            ["ssh-keygen", "-lf", str(path)],
            capture_output=True,
            env=ssh_subprocess_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "ssh-keygen failed"
        raise ValueError(f"Could not compute SSH host-key fingerprint: {detail}")
    fields = result.stdout.strip().split()
    if len(fields) < 2:
        raise ValueError("ssh-keygen returned an unexpected fingerprint format.")
    return SshHostKeyScan(known_hosts_line=line, fingerprint=fields[1], key_type=parts[1])


def scan_ssh_host_key(target: SshTarget) -> SshHostKeyScan:
    if not shutil.which("ssh-keyscan"):
        raise ValueError("ssh-keyscan is not installed or not on PATH.")
    if not shutil.which("ssh-keygen"):
        raise ValueError("ssh-keygen is not installed or not on PATH.")
    result = subprocess.run(
        ssh_keyscan_argv(target),
        capture_output=True,
        env=ssh_subprocess_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if result.returncode != 0 and not result.stdout.strip():
        detail = (result.stderr or result.stdout).strip() or "ssh-keyscan failed"
        raise ValueError(f"Could not scan SSH host key: {detail}")
    return fingerprint_known_host_line(parse_ssh_keyscan_output(result.stdout, target))


def trust_ssh_target_host_key(
    name: str,
    *,
    expected_fingerprint: str = "",
    home: Path | None = None,
    scanned: SshHostKeyScan | None = None,
) -> tuple[SshTarget, SshHostKeyScan]:
    safe_name = validate_target_name(name)
    targets = load_ssh_targets(home=home)
    target = targets.get(safe_name)
    if target is None:
        raise ValueError(f"SSH target `{safe_name}` is not configured.")
    scan = scanned or scan_ssh_host_key(target)
    if expected_fingerprint and scan.fingerprint != expected_fingerprint:
        raise ValueError(f"SSH host-key fingerprint mismatch: expected {expected_fingerprint}, got {scan.fingerprint}.")
    known_hosts = ssh_known_hosts_path(home)
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if known_hosts.exists():
        alias = ssh_host_alias(target)
        for raw_line in known_hosts.read_text(encoding="utf-8").splitlines():
            if raw_line.strip() and not raw_line.startswith(f"{alias} "):
                lines.append(raw_line)
    lines.append(scan.known_hosts_line)
    known_hosts.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        known_hosts.chmod(0o600)
    except OSError:
        pass
    trusted = SshTarget(
        **{
            **target.to_dict(),
            "host_key_status": "trusted",
            "host_key_fingerprint": scan.fingerprint,
            "updated_at": _timestamp(),
        }
    )
    targets[safe_name] = trusted
    save_ssh_targets(targets, home=home)
    write_audit_event(
        "ssh",
        safe_name,
        {
            "action_id": "ssh_trust_host_key",
            "ok": True,
            "host": trusted.host,
            "port": trusted.port,
            "fingerprint": scan.fingerprint,
            "key_type": scan.key_type,
        },
        home=home,
    )
    return trusted, scan


def build_ssh_base_argv(target: SshTarget, *, home: Path | None = None) -> list[str]:
    known_hosts = ssh_known_hosts_path(home)
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ForwardAgent=no",
        "-o",
        "RequestTTY=no",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "ServerAliveInterval=10",
        "-o",
        "ServerAliveCountMax=3",
        "-p",
        str(target.port),
        "-i",
        target.identity_file,
        f"{target.user}@{target.host}",
    ]
    return argv


def public_ssh_argv_preview(argv: list[str]) -> list[str]:
    preview: list[str] = []
    mask_next = False
    for item in argv:
        if mask_next:
            preview.append("<identity-file>")
            mask_next = False
            continue
        if item == "-i":
            preview.append(item)
            mask_next = True
            continue
        if item.startswith("UserKnownHostsFile="):
            preview.append("UserKnownHostsFile=<spark-known-hosts>")
            continue
        preview.append(item)
    return preview


def ssh_fixed_probe_argv(target: SshTarget, probe_id: str, *, home: Path | None = None) -> list[str]:
    probes = {
        "connection": "printf 'SPARK_SSH_OK\\n'; id -u",
    }
    if probe_id not in probes:
        raise ValueError(f"Unsupported SSH probe: {probe_id}")
    return [*build_ssh_base_argv(target, home=home), probes[probe_id]]


def run_ssh_fixed_probe(
    target: SshTarget,
    probe_id: str,
    *,
    home: Path | None = None,
    timeout: int = 15,
) -> dict[str, object]:
    argv = ssh_fixed_probe_argv(target, probe_id, home=home)
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            env=ssh_subprocess_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        output = bound_sandbox_output((stdout or "") + ("\n" if stdout and stderr else "") + (stderr or ""))
        return {
            "ok": False,
            "probe_id": probe_id,
            "returncode": 124,
            "output": output.to_dict(),
            "detail": f"SSH probe timed out after {timeout}s.",
        }
    except OSError as error:
        return {
            "ok": False,
            "probe_id": probe_id,
            "returncode": 127,
            "output": bound_sandbox_output("").to_dict(),
            "detail": f"Could not start SSH probe: {error.__class__.__name__}.",
        }
    output = bound_sandbox_output((result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or ""))
    return {
        "ok": result.returncode == 0 and "SPARK_SSH_OK" in output.text,
        "probe_id": probe_id,
        "returncode": result.returncode,
        "output": output.to_dict(),
        "detail": "SSH connection probe completed." if result.returncode == 0 else "SSH connection probe failed.",
    }


def ssh_smoke_probe_hash(probe_content: str = SSH_SMOKE_PROBE) -> str:
    return hashlib.sha256(probe_content.encode("utf-8")).hexdigest()


def ssh_smoke_remote_path(target: SshTarget, probe_hash: str) -> str:
    safe_name = validate_target_name(target.name)
    if not re.fullmatch(r"[0-9a-f]{64}", probe_hash):
        raise ValueError("SSH smoke probe hash must be a SHA-256 hex digest.")
    return f"/tmp/spark-sandbox-smoke-{safe_name}-{probe_hash[:12]}.sh"


def ssh_smoke_upload_argv(target: SshTarget, remote_path: str, *, home: Path | None = None) -> list[str]:
    return [*build_ssh_base_argv(target, home=home), f"umask 077; cat > {shlex.quote(remote_path)}"]


def ssh_smoke_execute_argv(
    target: SshTarget,
    remote_path: str,
    probe_hash: str,
    *,
    keep_debug_files: bool = False,
    home: Path | None = None,
) -> list[str]:
    quoted_path = shlex.quote(remote_path)
    quoted_hash = shlex.quote(probe_hash)
    cleanup = (
        "printf 'SPARK_SSH_DEBUG_FILE=%s\\n' \"$file\""
        if keep_debug_files
        else "cleanup(){ rm -f \"$file\"; }; trap cleanup EXIT"
    )
    command = (
        f"file={quoted_path}; expected={quoted_hash}; {cleanup}; "
        "actual=$(sha256sum \"$file\" | awk '{print $1}'); "
        "if [ \"$actual\" != \"$expected\" ]; then "
        "printf 'SPARK_SSH_HASH_MISMATCH expected=%s actual=%s\\n' \"$expected\" \"$actual\"; "
        "exit 42; "
        "fi; "
        "chmod 700 \"$file\"; "
        "sh \"$file\" \"$expected\""
    )
    return [*build_ssh_base_argv(target, home=home), command]


def _subprocess_payload(
    argv: list[str],
    *,
    timeout: int,
    input_text: str | None = None,
) -> dict[str, object]:
    try:
        result = subprocess.run(
            argv,
            input=input_text,
            capture_output=True,
            env=ssh_subprocess_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        return {
            "returncode": 124,
            "output": bound_sandbox_output((stdout or "") + ("\n" if stdout and stderr else "") + (stderr or "")).to_dict(),
            "detail": f"SSH command timed out after {timeout}s.",
        }
    except OSError as error:
        return {
            "returncode": 127,
            "output": bound_sandbox_output("").to_dict(),
            "detail": f"Could not start SSH command: {error.__class__.__name__}.",
        }
    return {
        "returncode": result.returncode,
        "output": bound_sandbox_output((result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")).to_dict(),
        "detail": "SSH command completed." if result.returncode == 0 else "SSH command failed.",
    }


def run_ssh_smoke_probe(
    target: SshTarget,
    *,
    home: Path | None = None,
    keep_debug_files: bool = False,
    timeout: int = 30,
    probe_content: str = SSH_SMOKE_PROBE,
    expected_hash: str | None = None,
) -> dict[str, object]:
    probe_hash = ssh_smoke_probe_hash(probe_content)
    if expected_hash is not None and expected_hash != probe_hash:
        return {
            "ok": False,
            "blocked": True,
            "stage": "local_hash_check",
            "probe_hash": probe_hash,
            "expected_hash": expected_hash,
            "returncode": 42,
            "output": bound_sandbox_output("").to_dict(),
            "cleanup_requested": False,
            "debug_files_kept": False,
            "detail": "Local SSH smoke probe hash mismatch; refusing to upload.",
        }

    remote_path = ssh_smoke_remote_path(target, probe_hash)
    upload = _subprocess_payload(
        ssh_smoke_upload_argv(target, remote_path, home=home),
        input_text=probe_content,
        timeout=timeout,
    )
    if upload["returncode"] != 0:
        return {
            "ok": False,
            "stage": "upload",
            "probe_hash": probe_hash,
            "remote_path": remote_path,
            "returncode": upload["returncode"],
            "output": upload["output"],
            "cleanup_requested": not keep_debug_files,
            "debug_files_kept": keep_debug_files,
            "detail": upload["detail"],
        }

    execute = _subprocess_payload(
        ssh_smoke_execute_argv(target, remote_path, probe_hash, keep_debug_files=keep_debug_files, home=home),
        timeout=timeout,
    )
    output = execute["output"]
    output_text = str(output.get("text") if isinstance(output, dict) else "")
    ok = execute["returncode"] == 0 and "SPARK_SSH_SMOKE_OK" in output_text and f"probe_sha256={probe_hash}" in output_text
    return {
        "ok": ok,
        "stage": "execute",
        "probe_hash": probe_hash,
        "remote_path": remote_path if keep_debug_files else "",
        "returncode": execute["returncode"],
        "output": output,
        "cleanup_requested": not keep_debug_files,
        "debug_files_kept": keep_debug_files,
        "detail": "SSH smoke probe completed." if ok else "SSH smoke probe failed.",
    }


def _check(name: str, ok: bool, detail: str, *, repair: str = "", level: str | None = None) -> SshDoctorCheck:
    return SshDoctorCheck(name=name, ok=ok, detail=detail, repair=repair, level=level or ("info" if ok else "error"))


def collect_ssh_doctor_payload(
    name: str,
    *,
    home: Path | None = None,
    remote_probe: bool = False,
) -> dict[str, object]:
    capabilities = ssh_management_capabilities()
    safe_name = validate_target_name(name)
    checks: list[SshDoctorCheck] = []

    ssh_path = shutil.which("ssh")
    checks.append(_check(
        "local_ssh_client",
        bool(ssh_path),
        f"SSH client found at {ssh_path}." if ssh_path else "SSH client not found on PATH.",
        repair="Install OpenSSH client, reopen the terminal, then rerun this command.",
    ))

    try:
        targets = load_ssh_targets(home=home)
        target = targets.get(safe_name)
    except ValueError as error:
        return {
            "ok": False,
            "backend": "ssh",
            "command": "doctor",
            "target": safe_name,
            "mode": "read_only",
            "capabilities": capabilities.to_dict(),
            "checks": [_check("target_store", False, str(error), repair="Review <spark-home>/config/ssh_targets.json.").to_dict()],
            "next": "Fix the SSH target store, then rerun doctor.",
        }

    if target is None:
        checks.append(_check(
            "target_record",
            False,
            f"SSH target `{safe_name}` is not configured.",
            repair=f"Run spark sandbox ssh add {safe_name} --host <host> --user <user> --identity-file <path>.",
        ))
        return {
            "ok": False,
            "backend": "ssh",
            "command": "doctor",
            "target": safe_name,
            "mode": "read_only",
            "capabilities": capabilities.to_dict(),
            "checks": [check.to_dict() for check in checks],
            "next": "Add the target before running SSH doctor.",
        }

    checks.append(_check("target_record", True, f"Target `{target.name}` is configured."))
    checks.append(_check("remote_user_non_root", target.user != "root", f"Remote user is `{target.user}`.", repair="Use a dedicated non-root user such as `spark`."))

    identity = Path(target.identity_file).expanduser()
    identity_ok = identity.exists() and identity.is_file()
    checks.append(_check(
        "identity_file",
        identity_ok,
        "Identity file is configured and exists." if identity_ok else "Configured identity file is missing or not a file.",
        repair="Update the target with a valid identity file path.",
    ))

    known_hosts = ssh_known_hosts_path(home)
    known_hosts_exists = known_hosts.exists()
    trusted = target.host_key_status == "trusted" and bool(target.host_key_fingerprint)
    if trusted:
        host_detail = f"Host key fingerprint is pinned for {ssh_host_alias(target)}."
    elif known_hosts_exists:
        host_detail = f"Spark known-hosts exists, but target `{target.name}` is not trusted yet."
    else:
        host_detail = "Spark known-hosts file does not exist yet; no host key is trusted."
    checks.append(_check(
        "host_key_trust",
        trusted,
        host_detail,
        repair=f"Run spark sandbox ssh trust {target.name}; do not use StrictHostKeyChecking=no.",
        level="info" if trusted else "warning",
    ))

    argv = build_ssh_base_argv(target, home=home)
    insecure = {"StrictHostKeyChecking=no", "ForwardAgent=yes"}
    secure_options_ok = not any(item in insecure for item in argv)
    checks.append(_check(
        "secure_ssh_options",
        secure_options_ok,
        "SSH argv uses BatchMode, IdentitiesOnly, ForwardAgent=no, RequestTTY=no, and StrictHostKeyChecking=yes.",
        repair="Keep SSH options strict before remote execution is enabled.",
    ))

    probe_payload: dict[str, object] | None = None
    if remote_probe:
        if not trusted:
            checks.append(_check(
                "remote_connection_probe",
                False,
                "Skipped remote probe because the host key is not trusted yet.",
                repair=f"Run spark sandbox ssh trust {target.name} first.",
            ))
        elif not identity_ok:
            checks.append(_check(
                "remote_connection_probe",
                False,
                "Skipped remote probe because the identity file is missing.",
                repair="Update the target with a valid identity file path.",
            ))
        else:
            probe_payload = run_ssh_fixed_probe(target, "connection", home=home)
            checks.append(_check(
                "remote_connection_probe",
                bool(probe_payload.get("ok")),
                str(probe_payload.get("detail") or "SSH probe completed."),
                repair="Check SSH network reachability, key authorization, and the trusted host key.",
            ))

    ok = all(check.ok for check in checks if check.level != "warning")
    payload = {
        "ok": ok,
        "backend": "ssh",
        "command": "doctor",
        "target": target.to_public_dict(),
        "mode": "read_only",
        "capabilities": capabilities.to_dict(),
        "checks": [check.to_dict() for check in checks],
        "ssh_argv_preview": public_ssh_argv_preview(argv),
        "next": "Run `spark sandbox ssh doctor <name> --remote-probe` after trust to verify login reachability." if not remote_probe else "SSH doctor remote probe completed; run `spark sandbox ssh smoke <name>` for the hashed remote smoke.",
    }
    if probe_payload is not None:
        payload["remote_probe"] = probe_payload
    if remote_probe:
        write_audit_event(
            "ssh",
            safe_name,
            {
                "action_id": "ssh_remote_probe",
                "ok": ok,
                "probe_ran": probe_payload is not None,
                "probe_id": probe_payload.get("probe_id") if probe_payload else "connection",
                "returncode": probe_payload.get("returncode") if probe_payload else None,
            },
            home=home,
        )
        payload["audit"] = sandbox_audit_ref("ssh", safe_name)
    return payload


def collect_ssh_smoke_payload(
    name: str,
    *,
    home: Path | None = None,
    keep_debug_files: bool = False,
) -> dict[str, object]:
    capabilities = ssh_smoke_capabilities()
    safe_name = validate_target_name(name)
    checks: list[SshDoctorCheck] = []
    smoke_payload: dict[str, object] | None = None

    try:
        targets = load_ssh_targets(home=home)
        target = targets.get(safe_name)
    except ValueError as error:
        payload = {
            "ok": False,
            "backend": "ssh",
            "command": "smoke",
            "target": safe_name,
            "mode": "remote_temp_probe",
            "capabilities": capabilities.to_dict(),
            "checks": [_check("target_store", False, str(error), repair="Review <spark-home>/config/ssh_targets.json.").to_dict()],
            "next": "Fix the SSH target store, then rerun smoke.",
        }
        write_audit_event("ssh", safe_name, {"action_id": "ssh_smoke", "ok": False, "detail": str(error)}, home=home)
        payload["audit"] = sandbox_audit_ref("ssh", safe_name)
        return payload

    if target is None:
        checks.append(_check(
            "target_record",
            False,
            f"SSH target `{safe_name}` is not configured.",
            repair=f"Run spark sandbox ssh add {safe_name} --host <host> --user <user> --identity-file <path>.",
        ))
    else:
        checks.append(_check("target_record", True, f"Target `{target.name}` is configured."))
        trusted = target.host_key_status == "trusted" and bool(target.host_key_fingerprint)
        checks.append(_check(
            "host_key_trust",
            trusted,
            f"Host key fingerprint is pinned for {ssh_host_alias(target)}." if trusted else "Host key is not trusted yet.",
            repair=f"Run spark sandbox ssh trust {target.name} first.",
        ))
        identity = Path(target.identity_file).expanduser()
        identity_ok = identity.exists() and identity.is_file()
        checks.append(_check(
            "identity_file",
            identity_ok,
            "Identity file is configured and exists." if identity_ok else "Configured identity file is missing or not a file.",
            repair="Update the target with a valid identity file path.",
        ))
        if trusted and identity_ok:
            smoke_payload = run_ssh_smoke_probe(target, home=home, keep_debug_files=keep_debug_files)
            checks.append(_check(
                "hashed_smoke_probe",
                bool(smoke_payload.get("ok")),
                str(smoke_payload.get("detail") or "SSH smoke probe failed."),
                repair="Check SSH reachability, remote /tmp write access, sha256sum, and non-root shell availability.",
            ))

    ok = all(check.ok for check in checks if check.level != "warning")
    audit_event = {
        "action_id": "ssh_smoke",
        "ok": ok,
        "keep_debug_files": keep_debug_files,
        "probe_hash": smoke_payload.get("probe_hash") if smoke_payload else "",
        "returncode": smoke_payload.get("returncode") if smoke_payload else None,
        "cleanup_requested": smoke_payload.get("cleanup_requested") if smoke_payload else False,
    }
    write_audit_event("ssh", safe_name, audit_event, home=home)
    payload = {
        "ok": ok,
        "backend": "ssh",
        "command": "smoke",
        "target": target.to_public_dict() if target is not None else safe_name,
        "mode": "remote_temp_probe",
        "capabilities": capabilities.to_dict(),
        "checks": [check.to_dict() for check in checks],
        "audit": sandbox_audit_ref("ssh", safe_name),
        "next": "SSH smoke passed; prepare/deploy remain intentionally unimplemented." if ok else "Fix failed smoke checks, then rerun `spark sandbox ssh smoke <name>`.",
    }
    if smoke_payload is not None:
        payload["probe"] = smoke_payload
    return payload
