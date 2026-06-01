"""Validate the IFC-first OpenBIM model with IfcOpenShell."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import ifcopenshell

ROOT = Path(__file__).resolve().parents[1]
IFC_PATH = ROOT / "bim" / "mechanical_room.ifc"
MANIFEST = ROOT / "manifest" / "asset_manifest.json"

sys.path.insert(0, str(ROOT / "tools"))
from asset_catalog import ALL_ASSETS  # noqa: E402


REQUIRED_ENTITY_COUNTS = {
    "IfcProject": 1,
    "IfcSite": 1,
    "IfcBuilding": 1,
    "IfcBuildingStorey": 1,
    "IfcSpace": 1,
    "IfcSlab": 1,
    "IfcWall": 4,
    "IfcDoor": 1,
    "IfcFooting": 1,
    "IfcElementAssembly": 1,
    "IfcUnitaryEquipment": 1,
    "IfcFilter": 1,
    "IfcCoil": 1,
    "IfcFan": 1,
    "IfcPump": 2,
    "IfcPipeSegment": 4,
    "IfcPipeFitting": 2,
    "IfcValve": 4,
    "IfcSensor": 1,
    "IfcDuctSegment": 3,
    "IfcDamper": 1,
    "IfcAirTerminal": 2,
    "IfcCableCarrierSegment": 2,
    "IfcMechanicalFastener": 4,
    "IfcVirtualElement": 1,
    "IfcDistributionSystem": 5,
    "IfcDistributionPort": 20,
    "IfcRelAssignsToGroup": 5,
    "IfcRelConnectsPortToElement": 20,
    "IfcRelConnectsPorts": 15,
    "IfcRelDefinesByProperties": 60,
    "IfcRelAssociatesMaterial": 30,
}

REQUIRED_NAMES = {
    "Project_CoordProof_MechanicalRoom",
    "Site_OpenBIM_Testbed",
    "Building_MechanicalLab",
    "Storey_MechanicalLevel_01",
    "Space_MechanicalRoom_001",
    "Slab_Concrete_Base",
    "Wall_North_01",
    "Wall_South_01",
    "Wall_East_01",
    "Wall_West_01",
    "Door_Access_01",
    "EquipmentPad_AHU_01",
    "Equipment_AHU_01",
    "AHU_Filter_01",
    "AHU_Coil_01",
    "AHU_Fan_01",
    "Equipment_PumpSkid_01",
    "Pump_CHWS_Duty_01",
    "Pump_CHWS_Standby_01",
    "Pipe_Supply_01",
    "Pipe_Return_01",
    "Pipe_Supply_Drop_01",
    "Pipe_Return_Drop_01",
    "Valve_CHWS_Isolation_01",
    "Valve_CHWS_Balancing_01",
    "Valve_CHWR_Isolation_01",
    "Valve_CHWR_Balancing_01",
    "PipeFitting_CHWS_Elbow_01",
    "PipeFitting_CHWR_Elbow_01",
    "Sensor_CHWS_Pressure_01",
    "Duct_Main_01",
    "Duct_Branch_01",
    "Duct_Return_01",
    "Damper_Fire_01",
    "AirTerminal_SupplyDiffuser_01",
    "AirTerminal_ReturnGrille_01",
    "CableTray_Overhead_01",
    "CableTray_Drop_01",
    "Support_PipeBracket_01",
    "Support_DuctHanger_01",
    "PipeClamp_TypeA_01",
    "Plate_Mounting_01",
    "Sleeve_WallPenetration_01",
    "Clearance_ServiceZone_AHU_01",
}

REQUIRED_SYSTEMS = {
    "System_CHWS",
    "System_CHWR",
    "System_SupplyAir",
    "System_ReturnAir",
    "System_ElectricalRouting",
}

REQUIRED_SYSTEM_MEMBERS = {
    "System_CHWS": {"Pump_CHWS_Duty_01", "Pipe_Supply_01", "AHU_Coil_01"},
    "System_CHWR": {"Pipe_Return_01", "Valve_CHWR_Isolation_01", "AHU_Coil_01"},
    "System_SupplyAir": {"Equipment_AHU_01", "AHU_Fan_01", "Duct_Main_01"},
    "System_ReturnAir": {"Equipment_AHU_01", "Duct_Return_01", "AirTerminal_ReturnGrille_01"},
    "System_ElectricalRouting": {"CableTray_Overhead_01", "CableTray_Drop_01"},
}


def nominal_value(prop) -> object:
    value = getattr(prop, "NominalValue", None)
    return getattr(value, "wrappedValue", value)


def product_psets(model: ifcopenshell.file) -> dict[int, dict[str, dict[str, object]]]:
    lookup: dict[int, dict[str, dict[str, object]]] = defaultdict(dict)
    for rel in model.by_type("IfcRelDefinesByProperties"):
        pset = rel.RelatingPropertyDefinition
        if not pset or not pset.is_a("IfcPropertySet"):
            continue
        props = {prop.Name: nominal_value(prop) for prop in pset.HasProperties}
        for product in rel.RelatedObjects:
            lookup[product.id()][pset.Name] = props
    return lookup


def system_members(model: ifcopenshell.file) -> dict[str, set[str]]:
    members: dict[str, set[str]] = defaultdict(set)
    for rel in model.by_type("IfcRelAssignsToGroup"):
        group = rel.RelatingGroup
        if not group or not group.is_a("IfcDistributionSystem"):
            continue
        for obj in rel.RelatedObjects:
            if getattr(obj, "Name", None):
                members[group.Name].add(obj.Name)
    return members


def contained_product_ids(model: ifcopenshell.file) -> set[int]:
    ids: set[int] = set()
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        for product in rel.RelatedElements:
            ids.add(product.id())
    return ids


def is_any(entity, classes: tuple[str, ...]) -> bool:
    return any(entity.is_a(ifc_class) for ifc_class in classes)


def manifest_asset_ids() -> set[str]:
    if MANIFEST.exists():
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        return {
            asset["asset_id"]
            for asset in data.get("assets", [])
            if asset.get("source_tool") not in {"OpenSCAD", "QCAD-compatible DXF", "Python"}
        }
    return {
        asset.asset_id
        for asset in ALL_ASSETS
        if asset.source_tool not in {"OpenSCAD", "QCAD-compatible DXF", "Python"}
    }


def validate() -> dict[str, object]:
    failures: list[str] = []
    warnings: list[str] = []
    if not IFC_PATH.exists():
        return {
            "name": "IFC",
            "status": "failed",
            "summary": {},
            "failures": [f"Missing {IFC_PATH.relative_to(ROOT)}"],
            "warnings": [],
        }

    try:
        model = ifcopenshell.open(str(IFC_PATH))
    except Exception as exc:  # pragma: no cover - exact parser exceptions vary
        return {
            "name": "IFC",
            "status": "failed",
            "summary": {},
            "failures": [f"IfcOpenShell could not open IFC: {exc}"],
            "warnings": [],
        }

    counts = Counter(entity.is_a() for entity in model)
    for entity, expected_min in REQUIRED_ENTITY_COUNTS.items():
        if counts[entity] < expected_min:
            failures.append(f"Expected at least {expected_min} `{entity}`, found {counts[entity]}")

    products = model.by_type("IfcProduct")
    named_objects = [
        entity
        for entity in model
        if hasattr(entity, "Name") and getattr(entity, "Name", None)
    ]
    names = {entity.Name for entity in named_objects if entity.Name}
    missing_names = sorted(REQUIRED_NAMES - names)
    if missing_names:
        failures.append("Missing required IFC object names: " + ", ".join(missing_names))

    blank_products = [
        f"#{product.id()} {product.is_a()}" for product in products if not product.Name
    ]
    if blank_products:
        failures.append("Blank product names: " + ", ".join(blank_products))

    unit_assignments = model.by_type("IfcUnitAssignment")
    if not unit_assignments:
        failures.append("No IfcUnitAssignment found")
    else:
        length_units = [
            unit
            for unit in unit_assignments[0].Units
            if getattr(unit, "UnitType", None) == "LENGTHUNIT"
        ]
        if not any(getattr(unit, "Name", None) == "METRE" for unit in length_units):
            failures.append("No metre-based length unit detected")

    systems = {system.Name for system in model.by_type("IfcDistributionSystem")}
    missing_systems = sorted(REQUIRED_SYSTEMS - systems)
    if missing_systems:
        failures.append("Missing distribution systems: " + ", ".join(missing_systems))

    members = system_members(model)
    for system_name, required_members in REQUIRED_SYSTEM_MEMBERS.items():
        missing = sorted(required_members - members.get(system_name, set()))
        if missing:
            failures.append(f"{system_name} missing members: " + ", ".join(missing))

    psets = product_psets(model)
    non_port_products = [
        product for product in products if not product.is_a("IfcDistributionPort")
    ]
    physical_products = [
        product
        for product in non_port_products
        if not is_any(product, ("IfcSite", "IfcBuilding", "IfcBuildingStorey"))
    ]
    missing_openbim_pset = [
        product.Name
        for product in physical_products
        if "Pset_OpenBIMAsset" not in psets.get(product.id(), {})
    ]
    if missing_openbim_pset:
        failures.append("Products missing Pset_OpenBIMAsset: " + ", ".join(missing_openbim_pset))

    missing_geometry = [
        product.Name
        for product in physical_products
        if not product.is_a("IfcSpace") and product.Representation is None
    ]
    if missing_geometry:
        failures.append("Products missing geometric representation: " + ", ".join(missing_geometry))

    contained_ids = contained_product_ids(model)
    not_contained = [
        product.Name
        for product in physical_products
        if not product.is_a("IfcSpace") and product.id() not in contained_ids
    ]
    if not_contained:
        failures.append("Products not spatially contained: " + ", ".join(not_contained))

    tag_values = {
        getattr(product, "Tag", None)
        for product in non_port_products
        if getattr(product, "Tag", None)
    }
    tag_values.add("room_shell_001")
    if model.by_type("IfcProject"):
        tag_values.add("mechanical_room_ifc_001")
    covered_assets = manifest_asset_ids()
    missing_manifest_assets = sorted(covered_assets - tag_values)
    if missing_manifest_assets:
        failures.append("Manifest assets missing from IFC tags/names: " + ", ".join(missing_manifest_assets))

    proxies = counts["IfcBuildingElementProxy"]
    if proxies:
        failures.append(
            f"{proxies} `IfcBuildingElementProxy` objects found; semantic OpenBIM model should use specific IFC classes."
        )

    connected_port_pairs = model.by_type("IfcRelConnectsPorts")
    if connected_port_pairs and counts["IfcDistributionPort"] < len(connected_port_pairs):
        failures.append("Connected port relationship count exceeds available ports")

    return {
        "name": "IFC",
        "status": "passed" if not failures else "failed",
        "summary": {
            "schema": model.schema,
            "entity_count": sum(counts.values()),
            "product_count": len(non_port_products),
            "distribution_system_count": len(systems),
            "connected_port_pair_count": len(connected_port_pairs),
            "manifest_ifc_asset_count": len(covered_assets),
            "proxy_count": proxies,
            "top_entities": dict(sorted(counts.items())),
        },
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
