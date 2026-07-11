from __future__ import annotations

import zipfile
from pathlib import Path

from validate_exports import ROOT, artifact_structure_error, validate


def test_committed_generated_artifacts_are_structurally_valid() -> None:
    result = validate()
    assert result["status"] == "passed", result["failures"]


def test_known_artifact_formats_parse() -> None:
    examples = (
        ROOT / "exports/step/plate_mounting_type_a.step",
        ROOT / "exports/stl/plate_mounting_type_a.stl",
        ROOT / "qcad/floor_plan.dxf",
        ROOT / "qcad/pdf_exports/floor_plan.pdf",
        ROOT / "freecad/mechanical_room.FCStd",
    )
    for path in examples:
        assert artifact_structure_error(path) is None, path


def test_garbage_step_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.step"
    path.write_text("not a STEP file", encoding="utf-8")
    assert artifact_structure_error(path) == "invalid ISO-10303 STEP envelope"


def test_geometry_empty_step_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.step"
    path.write_text(
        "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",
        encoding="utf-8",
    )

    assert artifact_structure_error(path) == "STEP DATA section contains no entities"


def test_truncated_binary_stl_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.stl"
    path.write_bytes(b"x" * 83)
    assert artifact_structure_error(path) == "binary STL header is truncated"


def test_fcstd_rejects_unsafe_archive_members(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.FCStd"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Document.xml", "<Document/>")
        archive.writestr("../../escape.txt", "escape")

    assert "unsafe archive member" in (artifact_structure_error(path) or "")
