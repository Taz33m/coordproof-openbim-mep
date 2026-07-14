from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from project_spec import ProjectSpecError, clear_project_spec_cache, load_project_spec

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spec" / "mechanical_room.project.json"
PROJECT_SPEC_V1_FINGERPRINT = "7e132739096d7a8a28181973d00d296fa05a799dfb112f61af1fe3472995c149"


def test_project_spec_v1_migration_fingerprint() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()

    assert hashlib.sha256(canonical).hexdigest() == PROJECT_SPEC_V1_FINGERPRINT


def test_loaded_project_spec_is_deeply_immutable() -> None:
    project = load_project_spec()
    asset_type = project.asset_types_by_id["openscad_pipe_clamp_type_b"]

    with pytest.raises(TypeError):
        asset_type.parameters["radius_mm"] = 999  # type: ignore[index]
    assert isinstance(project.occurrences[0].dimensions_mm, tuple)


def test_asset_type_parameters_are_isolated_and_group_checked() -> None:
    project = load_project_spec()
    asset_id = "openscad_pipe_clamp_type_b"

    parameters = project.parameters_for_asset_type(
        asset_id,
        expected_group="openscad",
    )

    parameters["pipe_diameter_mm"] = 999
    assert project.asset_types_by_id[asset_id].parameters["pipe_diameter_mm"] != 999
    with pytest.raises(ValueError, match="expected cadquery"):
        project.parameters_for_asset_type(asset_id, expected_group="cadquery")
    with pytest.raises(ValueError, match="Unknown ProjectSpec asset type"):
        project.parameters_for_asset_type("missing", expected_group="openscad")


def test_project_spec_cache_refreshes_when_source_file_changes(tmp_path: Path) -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    path = tmp_path / "project.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    clear_project_spec_cache()
    first = load_project_spec(path)

    payload["project"]["name"] = "CoordProof Mechanical Room Updated"
    path.write_text(json.dumps(payload), encoding="utf-8")
    second = load_project_spec(path)

    assert first.project.name == "CoordProof Mechanical Room"
    assert second.project.name == "CoordProof Mechanical Room Updated"
    assert second is not first


def test_schema_rejects_unknown_ifc_class(tmp_path: Path) -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload["asset_types"][0]["ifc_class"] = "IfcDefinitelyNotAClass"
    path = tmp_path / "project.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    clear_project_spec_cache()

    with pytest.raises(ProjectSpecError, match="schema validation failed"):
        load_project_spec(path)
