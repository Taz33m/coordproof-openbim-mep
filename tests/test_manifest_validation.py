from __future__ import annotations

import csv
import json
from pathlib import Path

import validate_exports
import validate_manifest


def test_manifest_rejects_a_stale_projectspec_projection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload = json.loads(validate_manifest.MANIFEST.read_text(encoding="utf-8"))
    payload["assets"] = payload["assets"][:-1]
    stale = tmp_path / "asset_manifest.json"
    stale.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(validate_manifest, "MANIFEST", stale)

    result = validate_manifest.validate()

    assert result["status"] == "failed"
    assert any(
        "report_observed_geometry_001" in failure for failure in result["failures"]
    )


def test_export_index_rejects_a_missing_projectspec_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with validate_exports.EXPORT_INDEX.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    stale = tmp_path / "export_index.csv"
    with stale.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["asset_id", "format", "path"])
        writer.writeheader()
        writer.writerows(rows[:-1])
    monkeypatch.setattr(validate_exports, "EXPORT_INDEX", stale)

    result = validate_exports.validate()

    assert result["status"] == "failed"
    assert any(
        "Export index misses ProjectSpec references" in failure
        for failure in result["failures"]
    )


def test_manifest_malformed_root_fails_without_a_traceback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    malformed = tmp_path / "asset_manifest.json"
    malformed.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(validate_manifest, "MANIFEST", malformed)

    result = validate_manifest.validate()

    assert result["status"] == "failed"
    assert result["failures"] == ["Manifest root must be a JSON object"]


def test_manifest_malformed_exports_fail_without_a_traceback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    malformed = tmp_path / "asset_manifest.json"
    malformed.write_text(
        json.dumps({"assets": [{"asset_id": "example", "exports": None}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(validate_manifest, "MANIFEST", malformed)

    result = validate_manifest.validate()

    assert result["status"] == "failed"
    assert result["summary"]["export_reference_count"] == 0
    assert any("has no exports listed" in item for item in result["failures"])


def test_export_index_malformed_row_fails_without_a_traceback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    malformed = tmp_path / "export_index.csv"
    malformed.write_text("asset_id,format\nexample,ifc\n", encoding="utf-8")
    monkeypatch.setattr(validate_exports, "EXPORT_INDEX", malformed)

    result = validate_exports.validate()

    assert result["status"] == "failed"
    assert any("Unsafe or incomplete export index row 2" in item for item in result["failures"])
