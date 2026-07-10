"""Validate source-level asset parameters before expensive CAD generation."""

from __future__ import annotations

import ast
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from asset_catalog import ALL_ASSETS, CADQUERY_ASSETS  # noqa: E402
from openbim_core import product_schedule  # noqa: E402
from project_spec import load_project_spec  # noqa: E402

ASSET_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
CADQUERY_MODULES = {
    "support_pipe_bracket_type_a": "pipe_support.py",
    "support_duct_hanger_type_a": "duct_hanger.py",
    "cable_tray_overhead_001": "cable_tray.py",
    "equipment_base_type_a": "equipment_base.py",
    "equipment_pump_skid_001": "pump_skid_frame.py",
    "sleeve_wall_penetration_type_a": "wall_sleeve.py",
    "pipe_clamp_type_a": "pipe_clamp.py",
    "duct_main_001": "rectangular_duct.py",
    "plate_mounting_type_a": "mounting_plate.py",
}
PARAMETER_SCHEMA = ROOT / "manifest" / "parameter_schema.json"


def module_defaults(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == "DEFAULT_PARAMETERS" for target in targets):
            value = ast.literal_eval(node.value)
            if not isinstance(value, dict):
                raise TypeError(f"{path}: DEFAULT_PARAMETERS must be a dictionary")
            return value
    raise ValueError(f"{path}: DEFAULT_PARAMETERS was not found")


def validate() -> dict[str, object]:
    project = load_project_spec()
    failures: list[str] = []
    warnings: list[str] = []
    catalog_ids = [asset.asset_id for asset in ALL_ASSETS]

    for asset in ALL_ASSETS:
        if not ASSET_ID_PATTERN.fullmatch(asset.asset_id):
            failures.append(f"Invalid asset_id syntax: {asset.asset_id}")
        for name, value in asset.parameters.items():
            if name.endswith("_mm"):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    failures.append(f"{asset.asset_id}.{name} must be numeric")
                elif not math.isfinite(float(value)) or float(value) <= 0:
                    failures.append(f"{asset.asset_id}.{name} must be finite and greater than zero")
            elif name.endswith("_count") and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                failures.append(f"{asset.asset_id}.{name} must be an integer of at least one")
        for export_path in asset.exports.values():
            candidate = Path(export_path)
            if candidate.is_absolute() or ".." in candidate.parts:
                failures.append(f"{asset.asset_id} has unsafe export path: {export_path}")

    duplicates = sorted({asset_id for asset_id in catalog_ids if catalog_ids.count(asset_id) > 1})
    if duplicates:
        failures.append("Duplicate source asset IDs: " + ", ".join(duplicates))

    by_id = {asset.asset_id: asset for asset in CADQUERY_ASSETS}
    for asset_id, module_name in CADQUERY_MODULES.items():
        if asset_id not in by_id:
            failures.append(f"CadQuery source mapping is missing catalog asset {asset_id}")
            continue
        defaults = module_defaults(ROOT / "cadquery" / module_name)
        catalog = by_id[asset_id].parameters
        missing = sorted(defaults.keys() - catalog.keys())
        if missing:
            failures.append(f"{asset_id} catalog misses builder parameters: {', '.join(missing)}")
        mismatches = [
            name
            for name in defaults.keys() & catalog.keys()
            if defaults[name] != catalog[name]
        ]
        if mismatches:
            failures.append(f"{asset_id} catalog/builder values differ: {', '.join(sorted(mismatches))}")

    schedule = product_schedule(project)
    schedule_ids = [spec.asset_id for spec in schedule]
    duplicate_schedule_ids = sorted(
        {asset_id for asset_id in schedule_ids if schedule_ids.count(asset_id) > 1}
    )
    if duplicate_schedule_ids:
        failures.append("Duplicate placed-occurrence IDs: " + ", ".join(duplicate_schedule_ids))
    for spec in schedule:
        occurrence = project.occurrences_by_id.get(spec.asset_id)
        if occurrence is None:
            failures.append(f"Placed occurrence is missing from ProjectSpec: {spec.asset_id}")
            continue
        asset_type = project.asset_types_by_id[occurrence.type_id]
        if asset_type.ifc_class != spec.ifc_class:
            failures.append(
                f"{spec.asset_id} IFC class differs: "
                f"type={asset_type.ifc_class}, schedule={spec.ifc_class}"
            )
        if asset_type.category != spec.category:
            failures.append(
                f"{spec.asset_id} category differs: "
                f"type={asset_type.category}, schedule={spec.category}"
            )
        if asset_type.source_tool != spec.source_tool:
            failures.append(
                f"{spec.asset_id} source tool differs: "
                f"type={asset_type.source_tool}, schedule={spec.source_tool}"
            )

    schema_properties: set[str] = set()
    if not PARAMETER_SCHEMA.exists():
        failures.append("Missing manifest/parameter_schema.json")
    else:
        schema = json.loads(PARAMETER_SCHEMA.read_text(encoding="utf-8"))
        schema_properties = set(schema.get("properties", {}))
        parameter_names = {name for asset in ALL_ASSETS for name in asset.parameters}
        missing_schema = sorted(parameter_names - schema_properties)
        if missing_schema:
            failures.append("Parameter schema misses catalog keys: " + ", ".join(missing_schema))

    return {
        "name": "Sources",
        "status": "passed" if not failures else "failed",
        "summary": {
            "project_spec_schema_version": project.schema_version,
            "asset_type_count": len(project.asset_types),
            "artifact_count": len(project.artifacts),
            "source_asset_count": len(ALL_ASSETS),
            "cadquery_asset_count": len(CADQUERY_ASSETS),
            "placed_occurrence_count": len(schedule),
            "schema_parameter_count": len(schema_properties),
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
