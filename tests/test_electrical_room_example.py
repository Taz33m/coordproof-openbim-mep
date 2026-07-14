from __future__ import annotations

from collections import Counter
from pathlib import Path

from project_spec import load_project_spec

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SPEC = ROOT / "examples" / "electrical_room" / "electrical_room.project.json"


def test_electrical_room_loads_through_the_generic_projectspec_contract() -> None:
    electrical = load_project_spec(EXAMPLE_SPEC)
    mechanical = load_project_spec()

    assert electrical.source_path == EXAMPLE_SPEC
    assert electrical.summary() == {
        "schema_version": 1,
        "project_id": "coordproof_electrical_room",
        "units": "millimeters",
        "asset_type_count": 12,
        "occurrence_count": 16,
        "artifact_count": 3,
        "catalog_record_count": 15,
        "system_count": 4,
        "connection_count": 12,
        "declared_port_count": 24,
    }
    assert [record.catalog_order for record in electrical.catalog_records()] == list(range(15))
    assert electrical.system_names == (
        "System_Normal480V",
        "System_Normal208V",
        "System_Grounding",
        "System_Monitoring",
    )
    assert set(electrical.system_names).isdisjoint(mechanical.system_names)
    assert set(electrical.asset_types_by_id).isdisjoint(mechanical.asset_types_by_id)


def test_electrical_room_has_complete_independent_system_topology() -> None:
    project = load_project_spec(EXAMPLE_SPEC)
    occurrences = project.occurrences_by_id

    transformer = occurrences["transformer_t1_001"]
    assert transformer.systems == (
        "System_Normal480V",
        "System_Normal208V",
        "System_Grounding",
    )
    assert transformer.port_systems == {
        "primary": "System_Normal480V",
        "secondary": "System_Normal208V",
        "ground": "System_Grounding",
    }

    feeder_ids = {
        "feeder_service_001",
        "feeder_transformer_primary_001",
        "feeder_panel_secondary_001",
        "feeder_branch_001",
    }
    feeders = [occurrences[occurrence_id] for occurrence_id in sorted(feeder_ids)]
    assert {feeder.type_id for feeder in feeders} == {"feeder_route_type"}
    assert {feeder.systems for feeder in feeders} == {
        ("System_Normal480V",),
        ("System_Normal208V",),
    }
    assert all(feeder.ports == ("source_end", "load_end") for feeder in feeders)

    assert Counter(connection.system for connection in project.connections) == Counter(
        {
            "System_Normal480V": 4,
            "System_Normal208V": 4,
            "System_Grounding": 3,
            "System_Monitoring": 1,
        }
    )

    declared_endpoints = {
        (occurrence.occurrence_id, port)
        for occurrence in project.occurrences
        for port in occurrence.ports
    }
    connected_endpoints = [
        (connection.source.occurrence_id, connection.source.port)
        for connection in project.connections
    ] + [
        (connection.target.occurrence_id, connection.target.port)
        for connection in project.connections
    ]
    assert len(connected_endpoints) == len(set(connected_endpoints))
    assert set(connected_endpoints) == declared_endpoints


def test_electrical_types_use_native_ifc_distribution_classes() -> None:
    types = load_project_spec(EXAMPLE_SPEC).asset_types_by_id
    expected = {
        "utility_service_type": "IfcElectricDistributionBoard",
        "main_switchboard_type": "IfcElectricDistributionBoard",
        "dry_type_transformer_type": "IfcTransformer",
        "panelboard_type": "IfcElectricDistributionBoard",
        "load_bank_type": "IfcElectricAppliance",
        "feeder_route_type": "IfcCableCarrierSegment",
        "main_ground_bar_type": "IfcJunctionBox",
    }
    actual = {type_id: asset.ifc_class for type_id, asset in types.items()}
    assert expected.items() <= actual.items()
    assert types["revenue_meter_type"].ifc_class == "IfcSensor"
    assert all("intended_ifc_class" not in asset.parameters for asset in types.values())
