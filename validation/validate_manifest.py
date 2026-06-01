"""Validate manifest structure and asset coverage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from asset_catalog import REQUIRED_ASSET_IDS, REQUIRED_CATEGORIES  # noqa: E402

MANIFEST = ROOT / "manifest" / "asset_manifest.json"


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

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assets = data.get("assets", [])
    ids = [asset.get("asset_id") for asset in assets]
    duplicate_ids = sorted({asset_id for asset_id in ids if ids.count(asset_id) > 1})
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
            path = ROOT / export_path
            if not path.exists():
                failures.append(f"{asset.get('asset_id')} export missing: {fmt} -> {export_path}")
            elif path.stat().st_size == 0:
                failures.append(f"{asset.get('asset_id')} export is zero bytes: {export_path}")

    categories = {asset.get("category") for asset in assets}
    missing_categories = sorted(REQUIRED_CATEGORIES - categories)
    if missing_categories:
        failures.append(f"Missing required categories: {', '.join(missing_categories)}")

    missing_assets = sorted(REQUIRED_ASSET_IDS - set(ids))
    if missing_assets:
        failures.append(f"Missing required assets: {', '.join(missing_assets)}")

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
            "export_reference_count": sum(len(asset.get("exports", {})) for asset in assets),
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
