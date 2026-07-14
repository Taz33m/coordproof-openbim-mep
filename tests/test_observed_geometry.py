from __future__ import annotations

import json
import struct
from pathlib import Path

import ezdxf
import pytest

import tools.generate_observed_geometry_matrix as geometry_matrix
from tools.generate_observed_geometry_matrix import (
    CADQUERY_ENVELOPES,
    Bounds,
    _cadquery_duct_hanger,
    _dxf_polyline_bounds,
    _openscad_connector,
    _row,
    _safe_repo_path,
    ifc_product_bounds,
    main,
    occurrence_bounds,
    stl_bounds,
)
from tools.openbim_core import PROJECT_SPEC, build_openbim_model


def test_ifc_observer_reads_geometry_not_property_schedule() -> None:
    model = build_openbim_model()
    product = next(
        item
        for item in model.by_type("IfcUnitaryEquipment")
        if item.Tag == "equipment_ahu_001"
    )
    occurrence = PROJECT_SPEC.occurrences_by_id["equipment_ahu_001"]

    assert ifc_product_bounds(product) == occurrence_bounds(occurrence)

    solid = product.Representation.Representations[0].Items[0]
    solid.SweptArea.XDim = 1499.0
    assert ifc_product_bounds(product) != occurrence_bounds(occurrence)


def test_binary_stl_bounds_are_measured_from_vertices(tmp_path: Path) -> None:
    path = tmp_path / "triangle.stl"
    record = struct.pack(
        "<12fH",
        0,
        0,
        1,
        -2,
        3,
        4,
        5,
        -6,
        7,
        1,
        2,
        -8,
        0,
    )
    path.write_bytes(b"binary".ljust(80, b"\0") + struct.pack("<I", 1) + record)

    assert stl_bounds(path) == Bounds(-2, -6, -8, 5, 3, 7)


def test_ascii_stl_rejects_nonfinite_vertices(tmp_path: Path) -> None:
    path = tmp_path / "bad.stl"
    path.write_text(
        "solid bad\n"
        "facet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex nan 1 0\n"
        "endloop\nendfacet\nendsolid bad\n",
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="non-finite"):
        stl_bounds(path)


def test_stl_size_is_bounded_before_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "oversized.stl"
    path.write_bytes(b"012345678")
    monkeypatch.setattr(geometry_matrix, "MAX_STL_BYTES", 8)

    with pytest.raises(ValueError, match="exceeds 8 byte"):
        stl_bounds(path)


def test_dxf_observer_rejects_an_open_outline() -> None:
    document = ezdxf.new()
    polyline = document.modelspace().add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        close=False,
    )

    with pytest.raises(ValueError, match="closed LWPOLYLINE"):
        _dxf_polyline_bounds(polyline)


def test_dxf_observer_rejects_bulge_arcs() -> None:
    document = ezdxf.new()
    polyline = document.modelspace().add_lwpolyline(
        [(0, 0, 1), (10, 0, 0), (10, 10, 0)],
        format="xyb",
        close=True,
    )

    with pytest.raises(ValueError, match="bulge arcs"):
        _dxf_polyline_bounds(polyline)


@pytest.mark.parametrize("symlinked_parent", [False, True])
def test_safe_repo_path_rejects_symlink_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symlinked_parent: bool,
) -> None:
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    artifact = outside / "artifact.ifc"
    artifact.write_text("outside", encoding="utf-8")

    if symlinked_parent:
        (root / "linked").symlink_to(outside, target_is_directory=True)
        supplied = Path("linked/artifact.ifc")
    else:
        (root / "artifact.ifc").symlink_to(artifact)
        supplied = Path("artifact.ifc")

    monkeypatch.setattr(geometry_matrix, "ROOT", root)
    with pytest.raises(ValueError, match="symlink component"):
        _safe_repo_path(supplied)


def test_openscad_connector_envelope_is_derived_from_project_parameters() -> None:
    parameters = PROJECT_SPEC.asset_types_by_id[
        "openscad_duct_connector_type_b"
    ].parameters

    assert _openscad_connector(parameters) == Bounds(-30, -195, -105, 30, 195, 105)


def test_cadquery_envelopes_are_independent_and_cover_every_bound_asset() -> None:
    parameters = PROJECT_SPEC.asset_types_by_id["support_duct_hanger_type_a"].parameters

    assert _cadquery_duct_hanger(parameters) == Bounds(-270, -114, -4, 270, 114, 524)
    assert set(CADQUERY_ENVELOPES) == {
        "cable_tray_overhead_001",
        "duct_main_001",
        "equipment_base_type_a",
        "equipment_pump_skid_001",
        "pipe_clamp_type_a",
        "plate_mounting_type_a",
        "sleeve_wall_penetration_type_a",
        "support_duct_hanger_type_a",
        "support_pipe_bracket_type_a",
    }


def test_matrix_row_fails_when_placement_differs_despite_equal_size() -> None:
    expected = Bounds(0, 0, 0, 10, 20, 30)
    shifted = Bounds(1, 0, 0, 11, 20, 30)

    row = _row(
        subject_kind="occurrence",
        type_id="example_type",
        occurrence_id="example_occurrence",
        format_name="ifc",
        artifact_path="model.ifc",
        expected_source="test",
        expected=expected,
        observed=shifted,
        tolerance=0.001,
    )

    assert row["status"] == "FAIL"
    assert row["max_delta_mm"] == "1"


def test_observed_matrix_cli_rejects_noncanonical_projects_cleanly(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    electrical = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "electrical_room"
        / "electrical_room.project.json"
    )

    assert main(
        [
            "--project-spec",
            str(electrical),
            "--csv",
            str(tmp_path / "matrix.csv"),
            "--markdown",
            str(tmp_path / "matrix.md"),
        ]
    ) == 2
    assert "currently certify only the canonical" in capsys.readouterr().err


def test_observed_matrix_cli_accepts_a_repo_relative_ifc_path(
    tmp_path: Path,
) -> None:
    assert main(
        [
            "--ifc",
            "bim/mechanical_room.ifc",
            "--csv",
            str(tmp_path / "matrix.csv"),
            "--markdown",
            str(tmp_path / "matrix.md"),
        ]
    ) == 0


def test_observed_matrix_rejects_a_noncanonical_contract_spoofing_the_project_id(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "electrical_room"
        / "electrical_room.project.json"
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["project"]["project_id"] = "coordproof_mechanical_room"
    spoof = tmp_path / "spoof.project.json"
    spoof.write_text(json.dumps(payload), encoding="utf-8")

    assert main(
        [
            "--project-spec",
            str(spoof),
            "--csv",
            str(tmp_path / "matrix.csv"),
            "--markdown",
            str(tmp_path / "matrix.md"),
        ]
    ) == 2
    error = capsys.readouterr().err
    assert "only the canonical source contract" in error
    assert "Traceback" not in error
