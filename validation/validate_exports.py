"""Validate generated export files and export index coverage."""

from __future__ import annotations

import csv
import json
import struct
import zipfile
from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parents[1]
EXPORT_INDEX = ROOT / "manifest" / "export_index.csv"

REQUIRED_FILES = [
    "exports/step/support_pipe_bracket_type_a.step",
    "exports/step/support_duct_hanger_type_a.step",
    "exports/step/cable_tray_overhead_001.step",
    "exports/step/equipment_base_type_a.step",
    "exports/step/equipment_pump_skid_001.step",
    "exports/step/sleeve_wall_penetration_type_a.step",
    "exports/step/pipe_clamp_type_a.step",
    "exports/step/duct_main_001.step",
    "exports/step/plate_mounting_type_a.step",
    "exports/step/mechanical_room_assembly.step",
    "exports/stl/support_pipe_bracket_type_a.stl",
    "exports/stl/support_duct_hanger_type_a.stl",
    "exports/stl/cable_tray_overhead_001.stl",
    "exports/stl/equipment_base_type_a.stl",
    "exports/stl/equipment_pump_skid_001.stl",
    "exports/stl/sleeve_wall_penetration_type_a.stl",
    "exports/stl/pipe_clamp_type_a.stl",
    "exports/stl/duct_main_001.stl",
    "exports/stl/plate_mounting_type_a.stl",
    "exports/stl/openscad_pipe_clamp_type_b.stl",
    "exports/stl/openscad_bracket_plate_type_b.stl",
    "exports/stl/openscad_cable_tray_segment_type_b.stl",
    "exports/stl/openscad_duct_connector_type_b.stl",
    "freecad/mechanical_room.FCStd",
    "freecad/mechanical_room_bim.FCStd",
    "qcad/floor_plan.dxf",
    "qcad/equipment_layout.dxf",
    "qcad/section_aa.dxf",
    "qcad/system_riser.dxf",
    "qcad/pipe_support_detail.dxf",
    "qcad/wall_penetration_detail.dxf",
    "qcad/duct_hanger_detail.dxf",
    "qcad/pdf_exports/floor_plan.pdf",
    "qcad/pdf_exports/equipment_layout.pdf",
    "qcad/pdf_exports/section_aa.pdf",
    "qcad/pdf_exports/system_riser.pdf",
    "qcad/pdf_exports/pipe_support_detail.pdf",
    "qcad/pdf_exports/wall_penetration_detail.pdf",
    "qcad/pdf_exports/duct_hanger_detail.pdf",
    "bim/mechanical_room.ifc",
    "bim/openbim_semantic_inventory.csv",
    "reports/coordination_report.md",
    "reports/bill_of_materials.csv",
    "reports/clash_clearance_report.csv",
]


def artifact_structure_error(path: Path) -> str | None:
    """Return a concise error when a supported artifact is structurally invalid."""

    suffix = path.suffix.lower()
    if suffix in {".step", ".stp"}:
        data = path.read_bytes()
        if not data.startswith(b"ISO-10303-21;") or b"END-ISO-10303-21;" not in data[-256:]:
            return "invalid ISO-10303 STEP envelope"
        if data.startswith(b"OPENCAD-MOCK"):
            return "analytic OpenCAD mock is not a STEP file"

    elif suffix == ".stl":
        data = path.read_bytes()
        if len(data) < 15:
            return "STL is too short"
        if data.lstrip().lower().startswith(b"solid") and b"endsolid" in data[-512:].lower():
            if b"facet normal" not in data.lower():
                return "ASCII STL contains no facets"
        else:
            if len(data) < 84:
                return "binary STL header is truncated"
            triangle_count = struct.unpack("<I", data[80:84])[0]
            if triangle_count == 0:
                return "binary STL contains no triangles"
            expected_size = 84 + triangle_count * 50
            if len(data) != expected_size:
                return f"binary STL size/count mismatch ({len(data)} != {expected_size})"

    elif suffix == ".dxf":
        try:
            document = ezdxf.readfile(path)
        except Exception as exc:  # pragma: no cover - parser exception type varies
            return f"DXF parse failed: {exc}"
        if len(document.modelspace()) == 0:
            return "DXF modelspace is empty"
        auditor = document.audit()
        if auditor.errors:
            return f"DXF audit found {len(auditor.errors)} unrecoverable error(s)"

    elif suffix == ".pdf":
        data = path.read_bytes()
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-1024:]:
            return "invalid PDF envelope"
        if path.parent == ROOT / "qcad" / "pdf_exports" and b"ReportLab" in data:
            return "portable ReportLab preview found where a canonical QCAD export is required"

    elif suffix == ".fcstd":
        if not zipfile.is_zipfile(path):
            return "FCStd is not a valid ZIP container"
        with zipfile.ZipFile(path) as archive:
            if "Document.xml" not in archive.namelist():
                return "FCStd is missing Document.xml"
    return None


def validate() -> dict[str, object]:
    failures: list[str] = []
    warnings: list[str] = []
    for folder in ["exports/step", "exports/stl", "qcad", "qcad/pdf_exports", "bim", "reports"]:
        path = ROOT / folder
        if not path.exists():
            failures.append(f"Missing folder: {folder}")

    for rel_path in REQUIRED_FILES:
        path = ROOT / rel_path
        if not path.exists():
            failures.append(f"Missing required export: {rel_path}")
        elif path.stat().st_size == 0:
            failures.append(f"Zero-byte required export: {rel_path}")

    indexed_paths: set[str] = set()
    if not EXPORT_INDEX.exists():
        failures.append("Missing manifest/export_index.csv")
    else:
        with EXPORT_INDEX.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                indexed_paths.add(row["path"])
                path = ROOT / row["path"]
                if not path.exists():
                    failures.append(f"Indexed export missing: {row['path']}")
                elif path.stat().st_size == 0:
                    failures.append(f"Indexed export is zero bytes: {row['path']}")

    for rel_path in sorted(set(REQUIRED_FILES) | indexed_paths):
        path = ROOT / rel_path
        if not path.is_file() or path.stat().st_size == 0:
            continue
        error = artifact_structure_error(path)
        if error:
            failures.append(f"Invalid generated artifact {rel_path}: {error}")

    unindexed_required = sorted(set(REQUIRED_FILES) - indexed_paths)
    if unindexed_required:
        warnings.append(
            "Required generated files not in export index: " + ", ".join(unindexed_required)
        )

    generated_files = [
        path
        for path in [
            *(ROOT / "exports" / "step").glob("*.step"),
            *(ROOT / "exports" / "stl").glob("*.stl"),
            *(ROOT / "qcad").glob("*.dxf"),
            *(ROOT / "qcad" / "pdf_exports").glob("*.pdf"),
            *(ROOT / "reports").glob("*.csv"),
            *(ROOT / "reports").glob("*.md"),
        ]
        if path.is_file()
    ]
    return {
        "name": "Exports",
        "status": "passed" if not failures else "failed",
        "summary": {
            "required_file_count": len(REQUIRED_FILES),
            "generated_export_count": len(generated_files),
            "indexed_export_count": len(indexed_paths),
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
