from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from .capabilities import CapabilityManifest
from .output import bound_sandbox_output
from .paths import os_family as docker_os_family


DEFAULT_SANDBOX_IMAGE = "spark-cli-sandbox:local"


def docker_capabilities() -> CapabilityManifest:
    return CapabilityManifest(
        backend="docker",
        filesystem="workspace",
        network="off",
        secrets="none",
        persistence="ephemeral",
        privilege="rootless-container",
        inbound="none",
        cost="free-local",
    )


def docker_repair_hint(family: str) -> str:
    if family == "macos":
        return "Install Docker Desktop for Mac, then rerun `spark sandbox docker doctor`."
    if family == "windows":
        return "Install Docker Desktop for Windows with WSL support, then rerun `spark sandbox docker doctor`."
    if family == "linux":
        return "Install Docker Engine or Docker Desktop for your Linux distro, then rerun `spark sandbox docker doctor`."
    return "Install Docker for this operating system, then rerun `spark sandbox docker doctor`."


def _check(name: str, ok: bool, detail: str, *, repair: str = "", level: str | None = None) -> dict[str, object]:
    return {
        "name": name,
        "ok": ok,
        "detail": detail,
        "repair": "" if ok else repair,
        "level": level or ("info" if ok else "error"),
    }


def collect_docker_doctor_payload(*, timeout: int = 8) -> dict[str, Any]:
    family = docker_os_family()
    docker_path = shutil.which("docker")
    checks = [
        _check(
            "docker_cli",
            bool(docker_path),
            f"Docker CLI found at {docker_path}." if docker_path else "Docker CLI was not found on PATH.",
            repair=docker_repair_hint(family),
        )
    ]
    daemon_ok = False
    version_detail = "Docker daemon was not checked because the CLI is missing."
    if docker_path:
        try:
            result = subprocess.run(
                [docker_path, "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            daemon_ok = result.returncode == 0 and bool((result.stdout or "").strip())
            version_detail = (
                f"Docker daemon responded with server version {(result.stdout or '').strip()}."
                if daemon_ok
                else "Docker CLI is installed, but the daemon is not responding."
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            version_detail = f"Docker daemon check failed: {error.__class__.__name__}."
    checks.append(
        _check(
            "docker_daemon",
            daemon_ok,
            version_detail,
            repair="Start Docker Desktop or the Docker service, then rerun `spark sandbox docker doctor`.",
        )
    )
    checks.append(
        _check(
            "spark_policy",
            True,
            "Spark Docker lane is optional and should only mount approved Spark workspaces.",
        )
    )
    ok = all(bool(check["ok"]) for check in checks if check.get("level") != "warning")
    return {
        "ok": ok,
        "backend": "docker",
        "command": "doctor",
        "os_family": family,
        "capabilities": docker_capabilities().to_dict(),
        "checks": checks,
        "next": "Run `spark access setup --with docker` for Docker-backed Level 4 tasks." if ok else docker_repair_hint(family),
    }


def collect_docker_smoke_payload(
    *,
    timeout: int = 180,
    build: bool = True,
    image: str | None = None,
    network: bool = False,
) -> dict[str, Any]:
    image_name = image or os.environ.get("SPARK_DOCKER_SANDBOX_IMAGE") or DEFAULT_SANDBOX_IMAGE
    doctor = collect_docker_doctor_payload(timeout=min(timeout, 8))
    checks = [
        _check(
            "docker_doctor",
            bool(doctor.get("ok")),
            "Docker doctor passed." if doctor.get("ok") else "Docker doctor did not pass.",
            repair="Run `spark sandbox docker doctor --json` and fix failing checks.",
        )
    ]
    output_text = ""
    build_detail = "Build skipped by request."
    build_ok = not build
    docker_path = shutil.which("docker")
    repo_root = Path(__file__).resolve().parents[3]
    dockerfile = repo_root / "docker" / "sandbox" / "Dockerfile"
    if doctor.get("ok") and build:
        if not dockerfile.exists():
            build_detail = "Docker sandbox Dockerfile was not found in this Spark CLI checkout."
        elif docker_path:
            try:
                result = subprocess.run(
                    [docker_path, "build", "-f", str(dockerfile), "-t", image_name, str(repo_root)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                )
                build_ok = result.returncode == 0
                build_detail = (
                    f"Built Docker sandbox image {image_name}."
                    if build_ok
                    else "Docker sandbox image build failed."
                )
                output_text += (result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")
            except (OSError, subprocess.TimeoutExpired) as error:
                build_detail = f"Docker sandbox image build failed: {error.__class__.__name__}."
    checks.append(
        _check(
            "docker_sandbox_image",
            build_ok,
            build_detail,
            repair="Run from the Spark CLI source checkout or build docker/sandbox/Dockerfile manually.",
        )
    )

    run_ok = False
    run_detail = "Docker sandbox run skipped because earlier checks failed."
    if doctor.get("ok") and build_ok and docker_path:
        network_mode = "bridge" if network else "none"
        run_args = [
            docker_path,
            "run",
            "--rm",
            "--network",
            network_mode,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m",
            "--tmpfs",
            "/sandbox:rw,nosuid,uid=1000,gid=1000,size=512m",
            image_name,
            "status",
            "--help",
        ]
        try:
            result = subprocess.run(
                run_args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            output_text += (result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")
            run_ok = result.returncode == 0
            run_detail = (
                f"Docker sandbox ran with network={network_mode}, read-only root, no-new-privileges, and no Spark secrets."
                if run_ok
                else "Docker sandbox run failed."
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            run_detail = f"Docker sandbox run failed: {error.__class__.__name__}."
    checks.append(
        _check(
            "no_secret_sandbox_smoke",
            run_ok,
            run_detail,
            repair="Check Docker Desktop, the sandbox image, and the read-only/tmpfs mount settings.",
        )
    )

    ok = all(bool(check["ok"]) for check in checks if check.get("level") != "warning")
    return {
        "ok": ok,
        "backend": "docker",
        "command": "smoke",
        "image": image_name,
        "network": "bridge" if network else "none",
        "capabilities": docker_capabilities().to_dict(),
        "checks": checks,
        "output": bound_sandbox_output(output_text).to_dict(),
        "next": "Docker no-secret sandbox smoke passed." if ok else "Fix failed Docker smoke checks, then rerun `spark sandbox docker smoke --json`.",
    }
