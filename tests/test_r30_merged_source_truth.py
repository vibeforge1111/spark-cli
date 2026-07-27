from __future__ import annotations

import json
from pathlib import Path

from spark_cli.r30_merged_source_truth import collect_r30_merged_source_truth_status


def test_binds_every_registry_module() -> None:
    payload = collect_r30_merged_source_truth_status()

    assert payload["ok"], payload["issues"]
    assert payload["module_count"] == 10
    assert payload["public_points_baseline"] == 24409
    assert payload["proposed_points"] == 0
    assert payload["source_overlap_count"] == 0
    assert payload["immutable_ref"] == "refs/tags/spark-r30-2026-07-27"
    assert all(row["ok"] for row in payload["rows"])


def test_rejects_point_and_spawner_supersession_drift(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "docs" / "r30" / "R30_MERGED_SOURCE_TRUTH_2026-07-27.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["proposed_points"] = 10
    spawner = next(row for row in manifest["modules"] if row["name"] == "spawner-ui")
    spawner.pop("supersession_reason")
    manifest_path = tmp_path / "merged-source-truth.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    payload = collect_r30_merged_source_truth_status(manifest_path=manifest_path)

    assert not payload["ok"]
    assert "proposed_points_mismatch" in payload["issues"]
    assert "spawner-ui:spawner_supersession_reason_missing" in payload["issues"]
