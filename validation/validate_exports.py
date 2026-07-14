"""Validate generated export files and export index coverage."""

from __future__ import annotations

import csv
import json
import stat
import struct
import sys
import zipfile
from pathlib import Path, PurePosixPath

import ezdxf

ROOT = Path(__file__).resolve().parents[1]
EXPORT_INDEX = ROOT / "manifest" / "export_index.csv"
sys.path.insert(0, str(ROOT / "tools"))

from project_spec import load_project_spec  # noqa: E402

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
    "reports/parameter_reconciliation.csv",
    "reports/parameter_reconciliation.md",
    "reports/observed_geometry_matrix.csv",
    "reports/observed_geometry_matrix.md",
]


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


def artifact_structure_error(path: Path) -> str | None:
    """Return a concise error when a supported artifact is structurally invalid."""

    suffix = path.suffix.lower()
    if suffix in {".step", ".stp"}:
        data = path.read_bytes()
        if not data.startswith(b"ISO-10303-21;") or b"END-ISO-10303-21;" not in data[-256:]:
            return "invalid ISO-10303 STEP envelope"
        if data.startswith(b"OPENCAD-MOCK"):
            return "analytic OpenCAD mock is not a STEP file"
        if not any(line.lstrip().startswith(b"#") and b"=" in line for line in data.splitlines()):
            return "STEP DATA section contains no entities"

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
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(names) != len(set(names)):
                    return "FCStd contains duplicate archive members"
                for info in infos:
                    member = PurePosixPath(info.filename)
                    if (
                        member.is_absolute()
                        or not info.filename
                        or "\\" in info.filename
                        or any(ord(character) < 32 for character in info.filename)
                        or any(
                            part in {"", ".", ".."}
                            or not all(
                                character.isascii()
                                and (character.isalnum() or character in "._-")
                                for character in part
                            )
                            for part in info.filename.split("/")
                        )
                    ):
                        return f"FCStd contains unsafe archive member: {info.filename}"
                    if info.flag_bits & 1:
                        return f"FCStd contains encrypted archive member: {info.filename}"
                    if stat.S_ISLNK(info.external_attr >> 16):
                        return f"FCStd contains symlink archive member: {info.filename}"
                    if info.file_size > 10 * 1024 * 1024:
                        return f"FCStd archive member is too large: {info.filename}"
                    ratio = info.file_size / max(info.compress_size, 1)
                    if ratio > 1000:
                        return f"FCStd archive member has suspicious compression: {info.filename}"
                if sum(info.file_size for info in infos) > 20 * 1024 * 1024:
                    return "FCStd uncompressed archive is too large"
                if names.count("Document.xml") != 1:
                    return "FCStd must contain exactly one Document.xml"
                bad_member = archive.testzip()
                if bad_member is not None:
                    return f"FCStd CRC failure in {bad_member}"
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            return f"FCStd ZIP validation failed: {exc}"
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
    indexed_rows: list[tuple[str, str, str]] = []
    if not EXPORT_INDEX.exists():
        failures.append("Missing manifest/export_index.csv")
    else:
        with EXPORT_INDEX.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != ["asset_id", "format", "path"]:
                failures.append("Export index header must be exactly: asset_id, format, path")
            for row_number, row in enumerate(reader, start=2):
                raw_values = (row.get("asset_id"), row.get("format"), row.get("path"))
                if not all(isinstance(value, str) for value in raw_values):
                    failures.append(f"Unsafe or incomplete export index row {row_number}")
                    indexed_rows.append(
                        tuple("" if value is None else str(value) for value in raw_values)
                    )
                    continue
                asset_id, format_name, export_path = raw_values
                indexed_rows.append((asset_id, format_name, export_path))
                if (
                    not asset_id
                    or not format_name
                    or not _is_safe_export_path(export_path)
                ):
                    failures.append(f"Unsafe or incomplete export index row {row_number}")
                    continue
                indexed_paths.add(export_path)
                path = ROOT / export_path
                if not path.exists():
                    failures.append(f"Indexed export missing: {export_path}")
                elif path.stat().st_size == 0:
                    failures.append(f"Indexed export is zero bytes: {export_path}")

    expected_rows = {
        (record.asset_id, format_name, str(export_path))
        for record in load_project_spec().catalog_records()
        for format_name, export_path in record.exports.items()
    }
    actual_rows = set(indexed_rows)
    duplicate_rows = sorted(
        {row for row in indexed_rows if indexed_rows.count(row) > 1}
    )
    if duplicate_rows:
        failures.append(
            "Duplicate export index rows: "
            + ", ".join("/".join(row) for row in duplicate_rows)
        )
    missing_rows = sorted(expected_rows - actual_rows)
    unexpected_rows = sorted(actual_rows - expected_rows)
    if missing_rows:
        failures.append(
            "Export index misses ProjectSpec references: "
            + ", ".join("/".join(row) for row in missing_rows)
        )
    if unexpected_rows:
        failures.append(
            "Export index contains undeclared references: "
            + ", ".join("/".join(row) for row in unexpected_rows)
        )

    for rel_path in sorted(set(REQUIRED_FILES) | indexed_paths):
        path = ROOT / rel_path
        if not path.is_file() or path.stat().st_size == 0:
            continue
        error = artifact_structure_error(path)
        if error:
            failures.append(f"Invalid generated artifact {rel_path}: {error}")

    unindexed_required = sorted(set(REQUIRED_FILES) - indexed_paths)
    if unindexed_required:
        failures.append(
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
            "indexed_export_reference_count": len(indexed_rows),
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
