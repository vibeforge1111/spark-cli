from __future__ import annotations

import json
from pathlib import Path

from spark_cli import release_gate


def test_release_gate_uses_recorded_installed_source_paths(tmp_path: Path) -> None:
    custom = tmp_path / "managed" / "spark-telegram-bot" / "r30-source"
    custom.mkdir(parents=True)
    (custom / "package.json").write_text(
        json.dumps({"scripts": {"r30:loop-readiness:strict": "ts-node audit.ts"}}),
        encoding="utf-8",
    )

    def fake_run(args: list[str], **kwargs: object) -> tuple[int, str, str]:
        assert kwargs["cwd"] == custom
        return 0, "ready 17/17", ""

    row = release_gate.collect_readiness_audit(
        modules_root=tmp_path / "modules",
        installed={"spark-telegram-bot": {"path": str(custom)}},
        runner=fake_run,
    )

    assert row["ok"]
