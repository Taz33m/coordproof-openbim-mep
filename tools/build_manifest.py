"""Generate asset manifest, parameter schema, export index, and BIM map."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from asset_catalog import ALL_ASSETS

ROOT = Path(__file__).resolve().parents[1]

FREECAD_OBJECT_NAMES = {
    "room_shell_001": "Space_MechanicalRoom_001",
    "slab_concrete_base_001": "Slab_Concrete_Base",
    "wall_north_001": "Wall_North_01",
    "wall_south_001": "Wall_South_01",
    "wall_east_001": "Wall_East_01",
    "wall_west_001": "Wall_West_01",
    "door_access_001": "Door_Access_01",
    "equipment_ahu_001": "Equipment_AHU_01",
    "equipment_base_type_a": "EquipmentPad_AHU_01",
    "equipment_pump_skid_001": "Equipment_PumpSkid_01",
    "pipe_supply_001": "Pipe_Supply_01",
    "pipe_return_001": "Pipe_Return_01",
    "duct_main_001": "Duct_Main_01",
    "cable_tray_overhead_001": "CableTray_Overhead_01",
    "support_pipe_bracket_type_a": "Support_PipeBracket_01",
    "support_duct_hanger_type_a": "Support_DuctHanger_01",
    "sleeve_wall_penetration_type_a": "Sleeve_WallPenetration_01",
    "pipe_clamp_type_a": "PipeClamp_TypeA_01",
    "plate_mounting_type_a": "Plate_Mounting_01",
    "clearance_ahu_service_zone_001": "Clearance_ServiceZone_AHU_01",
    "mechanical_room_ifc_001": "Project_CoordProof_MechanicalRoom",
}


def manifest_entries() -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for asset in ALL_ASSETS:
        entries.append(
            {
                "asset_id": asset.asset_id,
                "display_name": asset.display_name,
                "category": asset.category,
                "source_tool": asset.source_tool,
                "units": "millimeters",
                "ifc_class": asset.ifc_class,
                "parameters": asset.parameters,
                "exports": asset.exports,
                "validation_status": "pending",
                "notes": asset.notes,
            }
        )
    return entries


def write_manifest(entries: list[dict[str, object]]) -> None:
    path = ROOT / "manifest" / "asset_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"assets": entries}, indent=2) + "\n", encoding="utf-8")


def write_parameter_schema() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Mechanical Room Asset Parameters",
        "type": "object",
        "additionalProperties": {
            "type": ["number", "integer", "string", "boolean", "array", "object"]
        },
        "properties": {
            "asset_id": {"type": "string"},
            "length_mm": {"type": "number", "minimum": 0},
            "width_mm": {"type": "number", "minimum": 0},
            "height_mm": {"type": "number", "minimum": 0},
            "thickness_mm": {"type": "number", "minimum": 0},
            "wall_thickness_mm": {"type": "number", "minimum": 0},
            "pipe_diameter_mm": {"type": "number", "minimum": 0},
            "duct_width_mm": {"type": "number", "minimum": 0},
            "duct_height_mm": {"type": "number", "minimum": 0},
            "bolt_diameter_mm": {"type": "number", "minimum": 0},
            "bolt_spacing_mm": {"type": "number", "minimum": 0},
            "mounting_hole_count": {"type": "integer", "minimum": 0},
            "clearance_mm": {"type": "number", "minimum": 0},
            "material_tag": {"type": "string"},
            "export_formats": {"type": "array", "items": {"type": "string"}},
        },
    }
    path = ROOT / "manifest" / "parameter_schema.json"
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def write_export_index(entries: list[dict[str, object]]) -> None:
    path = ROOT / "manifest" / "export_index.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["asset_id", "format", "path"], lineterminator="\n"
        )
        writer.writeheader()
        for entry in entries:
            for fmt, export_path in entry["exports"].items():
                writer.writerow(
                    {
                        "asset_id": entry["asset_id"],
                        "format": fmt,
                        "path": export_path,
                    }
                )


def write_bim_map(entries: list[dict[str, object]]) -> None:
    path = ROOT / "bim" / "bim_object_map.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "asset_id",
                "freecad_object_name",
                "ifc_class",
                "category",
                "notes",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for entry in entries:
            if entry["source_tool"] in {"OpenSCAD", "QCAD-compatible DXF"}:
                continue
            object_name = FREECAD_OBJECT_NAMES.get(
                entry["asset_id"], entry["display_name"].replace(" ", "_")
            )
            writer.writerow(
                {
                    "asset_id": entry["asset_id"],
                    "freecad_object_name": object_name,
                    "ifc_class": entry["ifc_class"],
                    "category": entry["category"],
                    "notes": entry["notes"],
                }
            )


def main() -> None:
    entries = manifest_entries()
    write_manifest(entries)
    write_parameter_schema()
    write_export_index(entries)
    write_bim_map(entries)
    print(f"Wrote {len(entries)} manifest entries")


if __name__ == "__main__":
    main()
