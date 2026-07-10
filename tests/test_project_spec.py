from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from asset_catalog import ALL_ASSETS
from openbim_core import product_schedule
from project_spec import ProjectSpecError, clear_project_spec_cache, load_project_spec

ROOT = Path(__file__).resolve().parents[1]
PROJECT_SPEC_PATH = ROOT / "spec" / "mechanical_room.project.json"


@pytest.fixture
def project_payload() -> dict[str, object]:
    return json.loads(PROJECT_SPEC_PATH.read_text(encoding="utf-8"))


def load_mutated_spec(tmp_path: Path, payload: dict[str, object]):
    path = tmp_path / "mutated.project.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    clear_project_spec_cache()
    return load_project_spec(path)


def test_project_spec_loads_with_expected_inventory() -> None:
    project = load_project_spec()

    assert project.source_path == PROJECT_SPEC_PATH
    assert project.schema_version == 1
    assert project.units == "millimeters"
    assert project.summary() == {
        "schema_version": 1,
        "project_id": "coordproof_mechanical_room",
        "units": "millimeters",
        "asset_type_count": 44,
        "occurrence_count": 40,
        "artifact_count": 11,
        "catalog_record_count": 55,
        "system_count": 5,
        "connection_count": 22,
        "declared_port_count": 51,
    }
    assert [record.catalog_order for record in project.catalog_records()] == list(range(55))
    assert len(project.asset_types_by_id) == len(project.asset_types)
    assert len(project.occurrences_by_id) == len(project.occurrences)
    assert len(project.artifacts_by_id) == len(project.artifacts)


def test_catalog_projection_preserves_the_legacy_asset_contract() -> None:
    records = load_project_spec().catalog_records()

    projected = [
        {
            "asset_id": record.asset_id,
            "display_name": record.display_name,
            "category": record.category,
            "source_tool": record.source_tool,
            "ifc_class": record.ifc_class,
            "parameters": record.parameters,
            "exports": record.exports,
            "notes": record.notes,
        }
        for record in records
    ]
    assert projected == [asdict(asset) for asset in ALL_ASSETS]


def test_occurrence_projection_preserves_the_openbim_product_contract() -> None:
    project = load_project_spec()
    type_by_id = project.asset_types_by_id
    scheduled_occurrences = [
        occurrence
        for occurrence in project.occurrences
        if occurrence.occurrence_id != project.spatial.space_occurrence_id
    ]
    products = product_schedule()

    assert [item.occurrence_id for item in scheduled_occurrences] == [
        product.asset_id for product in products
    ]
    for occurrence, product in zip(scheduled_occurrences, products, strict=True):
        asset_type = type_by_id[occurrence.type_id]
        assert product.asset_id == occurrence.occurrence_id
        assert product.type_id == occurrence.type_id
        assert product.name == occurrence.ifc_name
        assert product.ifc_class == asset_type.ifc_class
        assert product.category == asset_type.category
        assert product.source_tool == asset_type.source_tool
        assert product.material == occurrence.material
        assert product.system == occurrence.systems
        assert product.object_type == occurrence.object_type
        assert product.geometry == occurrence.geometry
        assert product.origin_mm == occurrence.origin_mm
        assert product.dimensions_mm == occurrence.dimensions_mm
        assert product.extrusion_axis == occurrence.extrusion_axis
        assert product.ports == occurrence.ports
        assert product.port_systems == occurrence.port_systems
        assert product.properties == occurrence.properties


def test_product_schedule_supports_reused_types_with_distinct_occurrences() -> None:
    project = load_project_spec()
    source = project.occurrences_by_id["slab_concrete_base_001"]
    second = replace(
        source,
        occurrence_id="slab_concrete_base_002",
        ifc_name="Slab_Concrete_Base_02",
        origin_mm=(0.0, 0.0, 400.0),
    )
    project_with_reuse = replace(
        project,
        occurrences=(*project.occurrences, second),
    )

    products = product_schedule(project_with_reuse)
    first_product = next(
        product for product in products if product.asset_id == source.occurrence_id
    )
    second_product = next(
        product for product in products if product.asset_id == second.occurrence_id
    )

    assert first_product.asset_id != second_product.asset_id
    assert first_product.type_id == second_product.type_id == source.type_id


def test_every_port_and_connection_has_an_explicit_consistent_system() -> None:
    project = load_project_spec()
    occurrences = project.occurrences_by_id

    ahu = occurrences["equipment_ahu_001"]
    assert ahu.systems == (
        "System_SupplyAir",
        "System_ReturnAir",
        "System_CHWS",
        "System_CHWR",
    )
    assert ahu.port_systems == {
        "return_air_in": "System_ReturnAir",
        "supply_air_out": "System_SupplyAir",
        "chws_in": "System_CHWS",
        "chwr_out": "System_CHWR",
    }
    for pump_id in ("pump_chws_duty_001", "pump_chws_standby_001"):
        pump = occurrences[pump_id]
        assert pump.systems == ("System_CHWS", "System_CHWR")
        assert pump.port_systems == {
            "suction": "System_CHWR",
            "discharge": "System_CHWS",
        }

    for occurrence in project.occurrences:
        assert set(occurrence.port_systems) == set(occurrence.ports)
        assert set(occurrence.port_systems.values()) <= set(occurrence.systems)

    for connection in project.connections:
        source = occurrences[connection.source.occurrence_id]
        target = occurrences[connection.target.occurrence_id]
        assert source.port_systems[connection.source.port] == connection.system
        assert target.port_systems[connection.target.port] == connection.system


def test_schema_rejects_unknown_fields(
    tmp_path: Path, project_payload: dict[str, object]
) -> None:
    project_payload["unexpected"] = True

    with pytest.raises(ProjectSpecError, match="schema validation failed") as exc_info:
        load_mutated_spec(tmp_path, project_payload)

    assert "Additional properties are not allowed" in str(exc_info.value)


def test_semantics_reject_unknown_references(
    tmp_path: Path, project_payload: dict[str, object]
) -> None:
    occurrence = project_payload["occurrences"][1]
    occurrence["type_id"] = "missing_asset_type"
    project_payload["requirements"]["asset_ids"].append("missing_required_asset")

    with pytest.raises(ProjectSpecError, match="semantic validation failed") as exc_info:
        load_mutated_spec(tmp_path, project_payload)

    message = str(exc_info.value)
    assert "[UNKNOWN_REFERENCE]" in message
    assert "missing_asset_type" in message
    assert "missing_required_asset" in message


def test_semantics_reject_unsafe_export_paths(
    tmp_path: Path, project_payload: dict[str, object]
) -> None:
    project_payload["asset_types"][0]["exports"]["step"] = "../outside.step"

    with pytest.raises(ProjectSpecError, match="semantic validation failed") as exc_info:
        load_mutated_spec(tmp_path, project_payload)

    assert "[UNSAFE_EXPORT_PATH]" in str(exc_info.value)


def test_semantics_reject_missing_port_bindings(
    tmp_path: Path, project_payload: dict[str, object]
) -> None:
    occurrence = next(
        item
        for item in project_payload["occurrences"]
        if item["occurrence_id"] == "equipment_ahu_001"
    )
    occurrence["port_systems"].pop("chws_in")

    with pytest.raises(ProjectSpecError, match="semantic validation failed") as exc_info:
        load_mutated_spec(tmp_path, project_payload)

    assert "[PORT_SYSTEM_BINDING]" in str(exc_info.value)
    assert "chws_in" in str(exc_info.value)


def test_semantics_reject_connection_system_mismatch(
    tmp_path: Path, project_payload: dict[str, object]
) -> None:
    connection = project_payload["connections"][0]
    connection["system"] = "System_ReturnAir"

    with pytest.raises(ProjectSpecError, match="semantic validation failed") as exc_info:
        load_mutated_spec(tmp_path, project_payload)

    message = str(exc_info.value)
    assert "[SYSTEM_MEMBERSHIP]" in message
    assert f"{connection['connection_id']}.from" in message
    assert f"{connection['connection_id']}.to" in message


def test_semantics_reject_unknown_connection_references(
    tmp_path: Path, project_payload: dict[str, object]
) -> None:
    connection = project_payload["connections"][0]
    connection["to"]["occurrence_id"] = "missing_occurrence"
    connection["realizing_occurrence_id"] = "missing_realizer"

    with pytest.raises(ProjectSpecError, match="semantic validation failed") as exc_info:
        load_mutated_spec(tmp_path, project_payload)

    message = str(exc_info.value)
    assert "[UNKNOWN_REFERENCE]" in message
    assert "missing_occurrence" in message
    assert "missing_realizer" in message


def test_project_spec_summary_cli() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "project_spec.py"),
            "summary",
            "--project-spec",
            str(PROJECT_SPEC_PATH),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["project_id"] == "coordproof_mechanical_room"
    assert summary["catalog_record_count"] == 55
    assert summary["connection_count"] == 22
