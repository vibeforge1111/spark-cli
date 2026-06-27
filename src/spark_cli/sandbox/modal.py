from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

from .audit import sandbox_audit_ref, write_audit_event
from .capabilities import CapabilityManifest
from .output import bound_sandbox_output


MODAL_SMOKE_TIMEOUT_SECONDS = 90
MODAL_SANDBOX_TIMEOUT_SECONDS = 60
MODAL_SANDBOX_IDLE_TIMEOUT_SECONDS = 30
MODAL_APP_NAME = "spark-sandbox-smoke"
MODAL_SMOKE_ENV_ALLOWLIST = {
    "APPDATA",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "MODAL_CONFIG_PATH",
    "MODAL_ENVIRONMENT",
    "MODAL_PROFILE",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
}


def modal_doctor_capabilities() -> CapabilityManifest:
    return CapabilityManifest(
        backend="modal",
        filesystem="none",
        network="off",
        secrets="none",
        persistence="ephemeral",
        privilege="rootless-container",
        inbound="none",
        cost="bounded-cloud",
    )


def modal_smoke_capabilities() -> CapabilityManifest:
    return CapabilityManifest(
        backend="modal",
        filesystem="temp",
        network="off",
        secrets="none",
        persistence="ephemeral",
        privilege="rootless-container",
        inbound="none",
        cost="bounded-cloud",
    )


def _check(name: str, ok: bool, detail: str, *, repair: str = "", level: str | None = None) -> dict[str, object]:
    return {
        "name": name,
        "ok": ok,
        "detail": detail,
        "repair": repair,
        "level": level or ("info" if ok else "error"),
    }


def modal_sdk_available() -> bool:
    return importlib.util.find_spec("modal") is not None


def modal_cli_path() -> str:
    return shutil.which("modal") or ""


def modal_auth_markers(*, home: Path | None = None) -> dict[str, object]:
    root = home or Path.home()
    config_candidates = [
        Path(os.environ.get("MODAL_CONFIG_PATH", "")).expanduser() if os.environ.get("MODAL_CONFIG_PATH") else None,
        root / ".modal.toml",
        root / ".modal" / "config.toml",
    ]
    config_paths = [path for path in config_candidates if path is not None and path.exists()]
    env_auth = bool(os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET"))
    return {
        "env_auth": env_auth,
        "config_present": bool(config_paths),
        "config_count": len(config_paths),
        "profile": os.environ.get("MODAL_PROFILE") or "",
        "environment": os.environ.get("MODAL_ENVIRONMENT") or "",
    }


def collect_modal_doctor_payload(*, home: Path | None = None) -> dict[str, object]:
    capabilities = modal_doctor_capabilities()
    sdk_ok = modal_sdk_available()
    cli = modal_cli_path()
    auth = modal_auth_markers(home=home)
    auth_ok = bool(auth["env_auth"] or auth["config_present"])
    checks = [
        _check(
            "modal_sdk",
            sdk_ok,
            "Modal Python SDK is importable." if sdk_ok else "Modal Python SDK is not importable.",
            repair="Install Modal with `python -m pip install modal`, then rerun doctor.",
        ),
        _check(
            "modal_cli",
            bool(cli),
            "Modal CLI is available on PATH." if cli else "Modal CLI is optional and was not found on PATH.",
            repair="Optional: install the Modal CLI or use the Python SDK path.",
            level="info" if cli else "warning",
        ),
        _check(
            "modal_auth_marker",
            auth_ok,
            "Modal auth marker found without reading token material." if auth_ok else "No Modal auth marker found.",
            repair="Run `python -m modal setup` or set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET.",
        ),
        _check(
            "default_limits",
            True,
            f"Smoke uses timeout={MODAL_SANDBOX_TIMEOUT_SECONDS}s, idle_timeout={MODAL_SANDBOX_IDLE_TIMEOUT_SECONDS}s, block_network=True.",
        ),
        _check(
            "secret_policy",
            True,
            "Smoke sends no Spark secrets, no Modal Secrets, and no project files by default.",
        ),
    ]
    ok = all(bool(check["ok"]) for check in checks if check["level"] != "warning")
    return {
        "ok": ok,
        "backend": "modal",
        "command": "doctor",
        "mode": "read_only",
        "capabilities": capabilities.to_dict(),
        "checks": checks,
        "auth": {
            "env_auth": auth["env_auth"],
            "config_present": auth["config_present"],
            "profile": auth["profile"],
            "environment": auth["environment"],
        },
        "next": "Run `spark sandbox modal smoke --json` to create a tiny no-secret sandbox." if ok else "Fix Modal SDK/auth checks, then rerun doctor.",
    }


def modal_smoke_script() -> str:
    return textwrap.dedent(
        f"""
        import sys

        import modal


        def _text(value):
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return str(value or "")


        sandbox = None
        try:
            app = modal.App.lookup({MODAL_APP_NAME!r}, create_if_missing=True)
            sandbox = modal.Sandbox.create(
                "sh",
                "-lc",
                "sleep 20",
                app=app,
                timeout={MODAL_SANDBOX_TIMEOUT_SECONDS},
                idle_timeout={MODAL_SANDBOX_IDLE_TIMEOUT_SECONDS},
                block_network=True,
            )
            process = sandbox.exec(
                "sh",
                "-lc",
                "printf 'SPARK_MODAL_SMOKE_OK\\\\n'; printf 'network=blocked\\\\n'; id -u",
                timeout=15,
            )
            stdout = process.stdout.read()
            stderr = process.stderr.read()
            result = process.wait()
            if result is None:
                result = getattr(process, "returncode", 0) or 0
            sys.stdout.write(_text(stdout))
            sys.stderr.write(_text(stderr))
            sys.exit(int(result))
        finally:
            if sandbox is not None:
                try:
                    sandbox.terminate()
                except Exception as _e:
                    import logging as _log; _log.getLogger(__name__).warning("Suppressed: %s", _e, exc_info=True)
                try:
                    sandbox.detach()
                except Exception:
                    pass
        """
    ).strip()


def modal_smoke_subprocess_env(env: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    return {
        key: value
        for key, value in source.items()
        if key.upper() in MODAL_SMOKE_ENV_ALLOWLIST
    }


def run_modal_smoke_probe(*, timeout: int = MODAL_SMOKE_TIMEOUT_SECONDS) -> dict[str, object]:
    if not modal_sdk_available():
        return {
            "ok": False,
            "returncode": 127,
            "output": bound_sandbox_output("").to_dict(),
            "cleanup_requested": False,
            "detail": "Modal Python SDK is not importable.",
        }
    try:
        result = subprocess.run(
            [sys.executable, "-c", modal_smoke_script()],
            capture_output=True,
            env=modal_smoke_subprocess_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        return {
            "ok": False,
            "returncode": 124,
            "output": bound_sandbox_output((stdout or "") + ("\n" if stdout and stderr else "") + (stderr or "")).to_dict(),
            "cleanup_requested": True,
            "detail": f"Modal smoke timed out after {timeout}s.",
        }
    except OSError as error:
        return {
            "ok": False,
            "returncode": 127,
            "output": bound_sandbox_output("").to_dict(),
            "cleanup_requested": False,
            "detail": f"Could not start Modal smoke: {error.__class__.__name__}.",
        }
    output = bound_sandbox_output((result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or ""))
    ok = result.returncode == 0 and "SPARK_MODAL_SMOKE_OK" in output.text
    return {
        "ok": ok,
        "returncode": result.returncode,
        "output": output.to_dict(),
        "cleanup_requested": True,
        "detail": "Modal no-secret sandbox smoke completed." if ok else "Modal no-secret sandbox smoke failed.",
    }


def collect_modal_smoke_payload(*, home: Path | None = None) -> dict[str, object]:
    capabilities = modal_smoke_capabilities()
    doctor = collect_modal_doctor_payload(home=home)
    checks: list[dict[str, object]] = [
        _check(
            "modal_doctor",
            bool(doctor.get("ok")),
            "Modal doctor prerequisites passed." if doctor.get("ok") else "Modal doctor prerequisites failed.",
            repair="Run `spark sandbox modal doctor --json` and fix failing checks.",
        )
    ]
    smoke: dict[str, object] | None = None
    if doctor.get("ok"):
        smoke = run_modal_smoke_probe()
        checks.append(_check(
            "no_secret_sandbox_smoke",
            bool(smoke.get("ok")),
            str(smoke.get("detail") or "Modal smoke failed."),
            repair="Check Modal auth, workspace billing/access, SDK version, and sandbox availability.",
        ))
    ok = all(bool(check["ok"]) for check in checks if check["level"] != "warning")
    write_audit_event(
        "modal",
        "smoke",
        {
            "action_id": "modal_smoke",
            "ok": ok,
            "returncode": smoke.get("returncode") if smoke else None,
            "cleanup_requested": smoke.get("cleanup_requested") if smoke else False,
        },
        home=home,
    )
    payload: dict[str, Any] = {
        "ok": ok,
        "backend": "modal",
        "command": "smoke",
        "mode": "no_secret_ephemeral_sandbox",
        "capabilities": capabilities.to_dict(),
        "checks": checks,
        "audit": sandbox_audit_ref("modal", "smoke"),
        "next": "Modal smoke passed; controlled run/artifact flows remain intentionally unimplemented." if ok else "Fix failed Modal checks, then rerun smoke.",
    }
    if smoke is not None:
        payload["probe"] = smoke
    return payload
