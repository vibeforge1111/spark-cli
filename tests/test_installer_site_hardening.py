from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
UNIX_INSTALLER = ROOT / "scripts" / "install.sh"
WINDOWS_INSTALLER = ROOT / "scripts" / "install.ps1"


def _run_unix_dry_run(*, env_updates: dict[str, str]) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is not available")
    env = {**os.environ, **env_updates}
    return subprocess.run(
        [bash, str(UNIX_INSTALLER), "--dry-run", "--upgrade-existing"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_unix_installer_retains_site_download_and_recovery_hardening() -> None:
    script = UNIX_INSTALLER.read_text(encoding="utf-8")

    assert script.count("--connect-timeout 15 --max-time 300") == 3
    assert '[ -x "$node_dir/bin/node" ] && [ -x "$node_dir/bin/npm" ]' in script
    assert 'log "Removing partial Node $SPARK_NODE_VERSION tree at $node_dir"' in script
    assert 'git -C "$target" rev-parse --verify --quiet HEAD' in script
    assert 'log "Removing partial spark-cli checkout at $target (no HEAD)"' in script
    main_body = script[script.index("main() {") :]
    assert main_body.index("  acquire_install_lock\n") < main_body.index("  ensure_python_runtime\n")


@pytest.mark.parametrize(
    ("env_updates", "expected"),
    [
        ({"SPARK_PREFIX": "/tmp/spark$unsafe"}, "cannot be represented safely"),
        ({"SPARK_UV_VERSION": "0.11.7;unsafe"}, "Unsafe uv version value"),
        ({"SPARK_LLM_PROVIDER": "not-a-provider"}, "Unknown --llm-provider value"),
    ],
)
def test_unix_installer_rejects_unsafe_generated_settings(
    env_updates: dict[str, str],
    expected: str,
) -> None:
    result = _run_unix_dry_run(env_updates=env_updates)

    assert result.returncode != 0
    assert expected in result.stderr


def test_unix_installer_accepts_quoted_path_punctuation() -> None:
    result = _run_unix_dry_run(
        env_updates={"SPARK_PREFIX": "/tmp/Spark safe;and&(path)"},
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Spark safe;and&(path)" in result.stdout


def test_windows_installer_selects_native_node_architecture() -> None:
    script = WINDOWS_INSTALLER.read_text(encoding="utf-8")

    assert "function Get-NodePlatform" in script
    assert 'if ($arch -eq "ARM64")' in script
    assert 'return "win-arm64"' in script
    assert '$nodePlatform = Get-NodePlatform' in script
    assert '"node-v$NodeVersion-$nodePlatform.zip"' in script
    assert '"node-v$NodeVersion-win-x64.zip"' not in script
    assert "try {" in script[script.index("function Test-PythonCompatible") : script.index("function Find-SystemPython")]
