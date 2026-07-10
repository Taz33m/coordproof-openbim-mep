"""Generate asset manifest, parameter schema, export index, and BIM map."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from asset_catalog import ALL_ASSETS
from project_spec import load_project_spec

ROOT = Path(__file__).resolve().parents[1]

PROJECT_SPEC = load_project_spec()

FREECAD_OBJECT_NAMES = {
    occurrence.occurrence_id: occurrence.ifc_name
    for occurrence in PROJECT_SPEC.occurrences
}
FREECAD_OBJECT_NAMES["mechanical_room_ifc_001"] = PROJECT_SPEC.spatial.project_ifc_name


def manifest_entries() -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for asset in ALL_ASSETS:
        entries.append(
            {
                "asset_id": asset.asset_id,
                "display_name": asset.display_name,
                "category": asset.category,
                "source_tool": asset.source_tool,
                "units": PROJECT_SPEC.units,
                "ifc_class": asset.ifc_class,
                "parameters": asset.parameters,
                "exports": asset.exports,
                "validation_status": "not_evaluated",
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
            "bolt_offset_mm": {"type": "number", "exclusiveMinimum": 0},
            "base_thickness_mm": {"type": "number", "exclusiveMinimum": 0},
            "web_thickness_mm": {"type": "number", "exclusiveMinimum": 0},
            "strap_width_mm": {"type": "number", "exclusiveMinimum": 0},
            "strap_thickness_mm": {"type": "number", "exclusiveMinimum": 0},
            "rod_diameter_mm": {"type": "number", "exclusiveMinimum": 0},
            "hole_diameter_mm": {"type": "number", "exclusiveMinimum": 0},
            "hole_pitch_mm": {"type": "number", "exclusiveMinimum": 0},
            "slot_length_mm": {"type": "number", "exclusiveMinimum": 0},
            "ear_length_mm": {"type": "number", "exclusiveMinimum": 0},
            "sleeve_wall_mm": {"type": "number", "exclusiveMinimum": 0},
            "flange_diameter_mm": {"type": "number", "exclusiveMinimum": 0},
            "flange_thickness_mm": {"type": "number", "exclusiveMinimum": 0},
            "flange_depth_mm": {"type": "number", "exclusiveMinimum": 0},
            "rail_width_mm": {"type": "number", "exclusiveMinimum": 0},
            "pipe_radius_mm": {"type": "number", "exclusiveMinimum": 0},
            "radius_mm": {"type": "number", "exclusiveMinimum": 0},
            "scale": {"type": "string"},
            "source_of_truth": {"type": "string"},
            "mounting_hole_count": {"type": "integer", "minimum": 0},
            "crossmember_count": {"type": "integer", "minimum": 1},
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
