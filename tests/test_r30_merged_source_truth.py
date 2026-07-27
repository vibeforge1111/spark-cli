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


def test_accepts_module_specific_followup_ref(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "docs" / "r30" / "R30_MERGED_SOURCE_TRUTH_2026-07-27.json").read_text(encoding="utf-8")
    )
    registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    spawner = next(row for row in manifest["modules"] if row["name"] == "spawner-ui")
    followup_ref = "refs/tags/spark-r30-followup-test"
    spawner["immutable_ref"] = followup_ref
    registry["modules"]["spawner-ui"]["verify_ref"] = followup_ref
    registry["modules"]["spawner-ui"]["attestation"]["verify_ref"] = followup_ref
    manifest_path = tmp_path / "merged-source-truth.json"
    registry_path = tmp_path / "registry.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    payload = collect_r30_merged_source_truth_status(
        manifest_path=manifest_path,
        registry_path=registry_path,
    )

    assert payload["ok"], payload["issues"]
    spawner_status = next(row for row in payload["rows"] if row["name"] == "spawner-ui")
    assert spawner_status["immutable_ref"] == followup_ref


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
