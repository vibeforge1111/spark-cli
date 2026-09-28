from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from spark_cli.sandbox.docker import collect_docker_smoke_payload


REQUIRED_FLAG_PAIRS = (
    ("--user", "1000:1000"),
    ("--pids-limit", "128"),
    ("--memory", "512m"),
    ("--memory-swap", "512m"),
    ("--cpus", "1.0"),
)
SANDBOX_TMPFS = "/sandbox:rw,noexec,nosuid,uid=1000,gid=1000,size=512m"


def test_docker_smoke_uses_one_bounded_non_root_resource_policy() -> None:
    completed = subprocess.CompletedProcess(["docker"], 0, stdout="28.5.1\n", stderr="")
    with (
        patch("spark_cli.sandbox.docker.shutil.which", return_value="docker"),
        patch(
            "spark_cli.sandbox.docker.subprocess.run",
            side_effect=(completed, completed, completed),
        ) as run,
    ):
        payload = collect_docker_smoke_payload(image="spark-test:local")

    assert payload["ok"] is True
    run_args = run.call_args_list[2].args[0]
    for flag, value in REQUIRED_FLAG_PAIRS:
        index = run_args.index(flag)
        assert run_args[index + 1] == value
    assert SANDBOX_TMPFS in run_args


def test_docker_wrappers_and_ci_share_the_bounded_policy() -> None:
    repo = Path(__file__).resolve().parents[1]
    surfaces = (
        (repo / "scripts" / "docker-sandbox-run.sh").read_text(encoding="utf-8"),
        (repo / "scripts" / "docker-sandbox-run.ps1").read_text(encoding="utf-8"),
        (repo / ".github" / "workflows" / "docker-optional.yml").read_text(encoding="utf-8"),
    )
    dockerfile = (repo / "docker" / "sandbox" / "Dockerfile").read_text(encoding="utf-8")

    assert "USER spark" in dockerfile
    for surface in surfaces:
        for flag, value in REQUIRED_FLAG_PAIRS:
            assert flag in surface
            assert value in surface
        assert SANDBOX_TMPFS in surface
