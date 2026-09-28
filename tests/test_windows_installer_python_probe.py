from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _function_body(script: str, name: str, next_name: str) -> str:
    match = re.search(
        rf"function {re.escape(name)} \{{(?P<body>.*?)\n\}}\n\nfunction {re.escape(next_name)} \{{",
        script,
        flags=re.DOTALL,
    )
    assert match is not None, f"missing {name} before {next_name}"
    return match.group("body")


def test_windows_python_probe_treats_broken_alias_as_incompatible() -> None:
    script = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
    probe = _function_body(script, "Test-PythonCompatible", "Find-SystemPython")
    finder = _function_body(script, "Find-SystemPython", "Find-Uv")

    assert "try {" in probe
    assert "& $PythonExe -c" in probe
    assert "return $LASTEXITCODE -eq 0" in probe
    assert "catch {" in probe
    assert "return $false" in probe
    assert 'foreach ($name in @("python", "python3"))' in finder
    assert "Test-PythonCompatible $cmd.Source" in finder
    assert "return $false" in finder
