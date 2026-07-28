from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_prints_path_independent_copyable_commands() -> None:
    script = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")

    assert 'Direct wrapper path for this terminal:' in script
    assert 'Do not reinstall just to refresh PATH.' in script
    assert 'Operational checks (copyable even before PATH refresh):' in script

    for args in (
        '--help',
        'guide',
        'providers list',
        'live start',
        'live status',
        'providers status',
        'providers test --role chat',
        'verify --onboarding',
        'autostart status',
        'fix autostart',
        'autostart on telegram-starter --now',
        'autostart off',
        'fix telegram',
        'logs spark-telegram-bot',
        'fix spawner',
        'logs spawner-ui --lines 80',
    ):
        assert f'Write-Host "  & `"$sparkCmd`" {args}"' in script


def test_windows_installer_skip_setup_guidance_uses_same_copyable_wrapper() -> None:
    script = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")

    assert 'Write-Host "  & `"$sparkCmd`" setup $Bundle"' in script
    assert 'Write-Host "  & `"$sparkCmd`" verify --onboarding"' in script
