"""Validate manifest structure and asset coverage."""

from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from asset_catalog import ALL_ASSETS, REQUIRED_ASSET_IDS, REQUIRED_CATEGORIES  # noqa: E402

MANIFEST = ROOT / "manifest" / "asset_manifest.json"


def _is_safe_export_path(value: str) -> bool:
    """Return whether *value* is a canonical, portable repository-relative path."""

    portable = PurePosixPath(value)
    return (
        bool(value)
        and all(ord(character) >= 32 and ord(character) != 127 for character in value)
        and ":" not in value
        and "\\" not in value
        and not portable.is_absolute()
        and portable != PurePosixPath(".")
        and value == portable.as_posix()
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def validate() -> dict[str, object]:
    failures: list[str] = []
    warnings: list[str] = []
    if not MANIFEST.exists():
        return {
            "name": "Manifest",
            "status": "failed",
            "summary": {},
            "failures": [f"Missing {MANIFEST.relative_to(ROOT)}"],
            "warnings": [],
        }

    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "name": "Manifest",
            "status": "failed",
            "summary": {},
            "failures": [f"Manifest is not readable JSON: {exc}"],
            "warnings": [],
        }
    if not isinstance(data, dict):
        return {
            "name": "Manifest",
            "status": "failed",
            "summary": {},
            "failures": ["Manifest root must be a JSON object"],
            "warnings": [],
        }
    assets = data.get("assets", [])
    if not isinstance(assets, list) or any(not isinstance(asset, dict) for asset in assets):
        return {
            "name": "Manifest",
            "status": "failed",
            "summary": {},
            "failures": ["Manifest assets must be an array of objects"],
            "warnings": [],
        }
    ids = [asset.get("asset_id") for asset in assets]
    duplicate_ids = sorted(
        {asset_id for asset_id in ids if isinstance(asset_id, str) and ids.count(asset_id) > 1}
    )
    if duplicate_ids:
        failures.append(f"Duplicate asset IDs: {', '.join(duplicate_ids)}")

    required_fields = [
        "asset_id",
        "display_name",
        "category",
        "source_tool",
        "units",
        "ifc_class",
        "parameters",
        "exports",
        "validation_status",
        "notes",
    ]
    for index, asset in enumerate(assets):
        missing = [
            field
            for field in required_fields
            if field not in asset or asset[field] is None or asset[field] == ""
        ]
        if missing:
            failures.append(f"Asset #{index + 1} missing required fields: {', '.join(missing)}")
        if asset.get("units") != "millimeters":
            failures.append(f"{asset.get('asset_id')} does not use millimeters")
        exports = asset.get("exports", {})
        if not isinstance(exports, dict) or not exports:
            failures.append(f"{asset.get('asset_id')} has no exports listed")
            continue
        for fmt, export_path in exports.items():
            if not isinstance(fmt, str) or not isinstance(export_path, str):
                failures.append(
                    f"{asset.get('asset_id')} export names and paths must be strings"
                )
                continue
            if not _is_safe_export_path(export_path):
                failures.append(
                    f"{asset.get('asset_id')} has unsafe export path: {export_path!r}"
                )
                continue
            path = ROOT / export_path
            if not path.exists():
                failures.append(f"{asset.get('asset_id')} export missing: {fmt} -> {export_path}")
            elif path.stat().st_size == 0:
                failures.append(f"{asset.get('asset_id')} export is zero bytes: {export_path}")

    categories = {
        asset.get("category")
        for asset in assets
        if isinstance(asset.get("category"), str)
    }
    missing_categories = sorted(REQUIRED_CATEGORIES - categories)
    if missing_categories:
        failures.append(f"Missing required categories: {', '.join(missing_categories)}")

    string_ids = {asset_id for asset_id in ids if isinstance(asset_id, str)}
    missing_assets = sorted(REQUIRED_ASSET_IDS - string_ids)
    if missing_assets:
        failures.append(f"Missing required assets: {', '.join(missing_assets)}")

    expected_by_id = {asset.asset_id: asset for asset in ALL_ASSETS}
    actual_by_id = {
        asset["asset_id"]: asset
        for asset in assets
        if isinstance(asset.get("asset_id"), str)
    }
    missing_declared = sorted(set(expected_by_id) - set(actual_by_id))
    unexpected = sorted(set(actual_by_id) - set(expected_by_id))
    if missing_declared:
        failures.append(
            "Manifest misses ProjectSpec catalog records: " + ", ".join(missing_declared)
        )
    if unexpected:
        failures.append(
            "Manifest contains records not declared by ProjectSpec: " + ", ".join(unexpected)
        )
    expected_order = [asset.asset_id for asset in ALL_ASSETS]
    if ids != expected_order:
        failures.append("Manifest record order does not match ProjectSpec catalog_order")
    for asset_id in sorted(set(expected_by_id) & set(actual_by_id)):
        expected = expected_by_id[asset_id]
        expected_fields = {
            "display_name": expected.display_name,
            "category": expected.category,
            "source_tool": expected.source_tool,
            "units": "millimeters",
            "ifc_class": expected.ifc_class,
            # Catalog projections preserve nested tuples for runtime immutability;
            # the manifest is the equivalent JSON representation with arrays.
            "parameters": json.loads(json.dumps(expected.parameters)),
            "exports": expected.exports,
            "validation_status": "not_evaluated",
            "notes": expected.notes,
        }
        mismatches = [
            field
            for field, expected_value in expected_fields.items()
            if actual_by_id[asset_id].get(field) != expected_value
        ]
        if mismatches:
            failures.append(
                f"{asset_id} differs from ProjectSpec fields: {', '.join(mismatches)}"
            )

    fcstd_files = [ROOT / "freecad" / "mechanical_room.FCStd", ROOT / "freecad" / "mechanical_room_bim.FCStd"]
    for path in fcstd_files:
        if not path.exists():
            warnings.append(
                f"{path.relative_to(ROOT)} not present yet; create with FreeCAD GUI/macro during final modeling pass"
            )

    return {
        "name": "Manifest",
        "status": "passed" if not failures else "failed",
        "summary": {
            "asset_count": len(assets),
            "category_count": len(categories),
            "export_reference_count": sum(
                len(exports)
                for asset in assets
                if isinstance((exports := asset.get("exports")), dict)
            ),
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
