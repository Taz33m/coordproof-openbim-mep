from __future__ import annotations

import json
import logging
import shutil
import uuid
import zipfile
from pathlib import Path

import external_ifc_clash
import ifcopenshell
import ifcopenshell.guid
import pytest
from external_ifc_clash import (
    ClashConfig,
    ClashExecutionError,
    ClashInputError,
    ClashLimitError,
    ClashLimits,
    bcf_available,
    canonical_json_bytes,
    main,
    run_external_clash,
    write_bcf_report,
    write_reports,
)

FIXTURE_NAMESPACE = uuid.UUID("6398c0c4-90b8-5a13-87eb-7fe8d561a67b")


def _guid(key: str) -> str:
    return ifcopenshell.guid.compress(uuid.uuid5(FIXTURE_NAMESPACE, key).hex)


def _write_box_ifc(
    path: Path,
    model_key: str,
    boxes: list[tuple[str, tuple[float, float, float]]],
) -> dict[str, str]:
    model = ifcopenshell.file(schema="IFC4")
    model.header.file_name.time_stamp = "1970-01-01T00:00:00"

    def entity(ifc_class: str, *args, **kwargs):
        return model.create_entity(ifc_class, *args, **kwargs)

    def point(xyz: tuple[float, float, float]):
        return entity("IfcCartesianPoint", Coordinates=[float(value) for value in xyz])

    def direction(xyz: tuple[float, float, float]):
        return entity("IfcDirection", DirectionRatios=[float(value) for value in xyz])

    def axis(xyz: tuple[float, float, float]):
        return entity(
            "IfcAxis2Placement3D",
            Location=point(xyz),
            Axis=direction((0.0, 0.0, 1.0)),
            RefDirection=direction((1.0, 0.0, 0.0)),
        )

    origin_axis = axis((0.0, 0.0, 0.0))
    context = entity(
        "IfcGeometricRepresentationContext",
        ContextIdentifier="Model",
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1.0e-5,
        WorldCoordinateSystem=origin_axis,
    )
    units = entity(
        "IfcUnitAssignment",
        Units=[entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")],
    )
    entity(
        "IfcProject",
        GlobalId=_guid(f"project:{model_key}"),
        OwnerHistory=None,
        Name=f"Fixture {model_key}",
        Description=None,
        ObjectType=None,
        LongName=None,
        Phase=None,
        RepresentationContexts=[context],
        UnitsInContext=units,
    )

    global_ids: dict[str, str] = {}
    for name, xyz in boxes:
        placement = entity(
            "IfcLocalPlacement",
            PlacementRelTo=None,
            RelativePlacement=axis(xyz),
        )
        profile = entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            ProfileName=f"{name} Profile",
            Position=None,
            XDim=1.0,
            YDim=1.0,
        )
        solid = entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=origin_axis,
            ExtrudedDirection=direction((0.0, 0.0, 1.0)),
            Depth=1.0,
        )
        shape = entity(
            "IfcShapeRepresentation",
            ContextOfItems=context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )
        representation = entity(
            "IfcProductDefinitionShape",
            Name=None,
            Description=None,
            Representations=[shape],
        )
        global_id = _guid(f"wall:{model_key}:{name}")
        entity(
            "IfcWall",
            GlobalId=global_id,
            OwnerHistory=None,
            Name=name,
            Description=None,
            ObjectType=None,
            ObjectPlacement=placement,
            Representation=representation,
            Tag=name,
            PredefinedType=None,
        )
        global_ids[name] = global_id

    model.write(path)
    return global_ids


@pytest.fixture
def clashing_ifcs(tmp_path: Path) -> tuple[Path, Path, dict[str, str], dict[str, str]]:
    a_path = tmp_path / "discipline-a.ifc"
    b_path = tmp_path / "discipline-b.ifc"
    a_ids = _write_box_ifc(a_path, "A", [("A-Wall", (0.0, 0.0, 0.0))])
    b_ids = _write_box_ifc(b_path, "B", [("B-Wall", (0.25, 0.25, 0.25))])
    return a_path, b_path, a_ids, b_ids


def test_real_geometry_clash_is_deterministic_and_path_independent(
    clashing_ifcs: tuple[Path, Path, dict[str, str], dict[str, str]],
    tmp_path: Path,
) -> None:
    a_path, b_path, a_ids, b_ids = clashing_ifcs
    first = run_external_clash(a_path, b_path)

    copied_dir = tmp_path / "copied"
    copied_dir.mkdir()
    copied_a = copied_dir / "renamed-a.ifc"
    copied_b = copied_dir / "renamed-b.ifc"
    shutil.copyfile(a_path, copied_a)
    shutil.copyfile(b_path, copied_b)
    second = run_external_clash(copied_a, copied_b)

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["generator"]["backend"] == "ifcopenshell.geom.tree"
    assert first["summary"] == {
        "status": "clashes_found",
        "clash_count": 1,
        "native_result_count": 1,
        "selected_candidate_pair_count": 1,
        "geometry_candidate_pair_count": 1,
    }
    clash = first["clashes"][0]
    assert clash["a"]["global_id"] == a_ids["A-Wall"]
    assert clash["b"]["global_id"] == b_ids["B-Wall"]
    assert clash["clash_type"] == "collision"
    assert clash["distance_mm"] == 0.0
    assert str(tmp_path) not in canonical_json_bytes(first).decode("utf-8")


def test_intersection_and_clearance_modes_use_native_distance(tmp_path: Path) -> None:
    a_path = tmp_path / "a.ifc"
    overlap_path = tmp_path / "overlap.ifc"
    near_path = tmp_path / "near.ifc"
    _write_box_ifc(a_path, "A", [("A", (0.0, 0.0, 0.0))])
    _write_box_ifc(overlap_path, "Overlap", [("B", (0.25, 0.25, 0.25))])
    _write_box_ifc(near_path, "Near", [("C", (2.0, 0.0, 0.0))])

    intersection = run_external_clash(
        a_path,
        overlap_path,
        config=ClashConfig(mode="intersection"),
    )
    clearance = run_external_clash(
        a_path,
        near_path,
        config=ClashConfig(mode="clearance", clearance_mm=1100.0),
    )

    assert intersection["clashes"][0]["clash_type"] in {"pierce", "protrusion"}
    assert intersection["clashes"][0]["distance_mm"] > 0
    assert clearance["clashes"][0]["clash_type"] == "clearance"
    assert clearance["clashes"][0]["distance_mm"] == pytest.approx(1000.0)


def test_clear_models_produce_an_explicit_zero_result(tmp_path: Path) -> None:
    a_path = tmp_path / "a.ifc"
    b_path = tmp_path / "b.ifc"
    _write_box_ifc(a_path, "A", [("A", (0.0, 0.0, 0.0))])
    _write_box_ifc(b_path, "B", [("B", (3.0, 0.0, 0.0))])

    report = run_external_clash(a_path, b_path)

    assert report["summary"]["status"] == "clear"
    assert report["summary"]["clash_count"] == 0
    assert report["clashes"] == []


def test_explicit_model_labels_are_path_independent_metadata(
    clashing_ifcs: tuple[Path, Path, dict[str, str], dict[str, str]],
) -> None:
    a_path, b_path, _, _ = clashing_ifcs

    report = run_external_clash(
        a_path,
        b_path,
        config=ClashConfig(a_label="MEP", b_label="Structure"),
    )

    assert [item["label"] for item in report["inputs"]] == ["MEP", "Structure"]


def test_candidate_pair_limit_fails_instead_of_truncating(tmp_path: Path) -> None:
    a_path = tmp_path / "a.ifc"
    b_path = tmp_path / "b.ifc"
    _write_box_ifc(
        a_path,
        "A",
        [("A1", (0.0, 0.0, 0.0)), ("A2", (2.0, 0.0, 0.0))],
    )
    _write_box_ifc(b_path, "B", [("B", (0.25, 0.25, 0.25))])

    with pytest.raises(ClashLimitError, match="2 candidate pairs; limit is 1"):
        run_external_clash(
            a_path,
            b_path,
            limits=ClashLimits(max_candidate_pairs=1),
        )


def test_triangle_limit_stops_oversized_tessellation(tmp_path: Path) -> None:
    a_path = tmp_path / "a.ifc"
    b_path = tmp_path / "b.ifc"
    _write_box_ifc(a_path, "A", [("A", (0.0, 0.0, 0.0))])
    _write_box_ifc(b_path, "B", [("B", (0.25, 0.25, 0.25))])

    with pytest.raises(ClashLimitError, match="more than 1 triangles"):
        run_external_clash(
            a_path,
            b_path,
            limits=ClashLimits(max_triangles_per_side=1),
        )


def test_native_result_limit_fails_instead_of_truncating(tmp_path: Path) -> None:
    a_path = tmp_path / "a.ifc"
    b_path = tmp_path / "b.ifc"
    _write_box_ifc(
        a_path,
        "A",
        [("A1", (0.0, 0.0, 0.0)), ("A2", (0.1, 0.1, 0.1))],
    )
    _write_box_ifc(b_path, "B", [("B", (0.25, 0.25, 0.25))])

    with pytest.raises(ClashLimitError, match="returned at least 2 native clashes; limit is 1"):
        run_external_clash(
            a_path,
            b_path,
            limits=ClashLimits(max_results=1),
        )


def test_identical_inputs_are_rejected_as_unsupported_intra_model_clash(
    tmp_path: Path,
) -> None:
    a_path = tmp_path / "a.ifc"
    copied_path = tmp_path / "copy.ifc"
    _write_box_ifc(a_path, "A", [("A", (0.0, 0.0, 0.0))])
    shutil.copyfile(a_path, copied_path)

    with pytest.raises(ClashInputError, match="intra-model clash is not supported"):
        run_external_clash(a_path, copied_path)


def test_cli_writes_json_and_can_gate_on_clashes(
    clashing_ifcs: tuple[Path, Path, dict[str, str], dict[str, str]],
    tmp_path: Path,
) -> None:
    a_path, b_path, _, _ = clashing_ifcs
    output = tmp_path / "clashes.json"

    status = main(
        [
            str(a_path),
            str(b_path),
            "--output",
            str(output),
            "--fail-on-clash",
        ]
    )

    assert status == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["clash_count"] == 1


def test_cli_rejects_invalid_output_suffix_before_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unexpected_geometry(*args, **kwargs):
        raise AssertionError("geometry should not run after output preflight fails")

    monkeypatch.setattr(external_ifc_clash, "run_external_clash", unexpected_geometry)

    status = main(
        [
            str(tmp_path / "a.ifc"),
            str(tmp_path / "b.ifc"),
            "--output",
            str(tmp_path / "clashes.txt"),
        ]
    )

    assert status == 2
    assert ".json suffix" in capsys.readouterr().err


def test_grouped_report_staging_does_not_publish_json_when_bcf_fails(
    clashing_ifcs: tuple[Path, Path, dict[str, str], dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a_path, b_path, _, _ = clashing_ifcs
    report = run_external_clash(a_path, b_path)
    output = tmp_path / "clashes.json"
    bcf = tmp_path / "clashes.bcfzip"

    def fail_bcf(*args, **kwargs):
        raise ClashExecutionError("injected BCF failure")

    monkeypatch.setattr(external_ifc_clash, "write_bcf_report", fail_bcf)

    with pytest.raises(ClashExecutionError, match="injected BCF failure"):
        write_reports(report, output, bcf)

    assert not output.exists()
    assert not bcf.exists()


def test_published_ifcclash_wrapper_agrees_when_installed(
    clashing_ifcs: tuple[Path, Path, dict[str, str], dict[str, str]],
) -> None:
    ifcclash = pytest.importorskip(
        "ifcclash.ifcclash",
        reason="the standalone IfcClash wrapper is optional",
    )
    a_path, b_path, a_ids, b_ids = clashing_ifcs
    settings = ifcclash.ClashSettings()
    settings.logger = logging.getLogger("coordproof.ifcclash-test")
    clasher = ifcclash.Clasher(settings)
    clash_set = {
        "name": "fixture",
        "a": [{"file": str(a_path)}],
        "b": [{"file": str(b_path)}],
        "mode": "collision",
        "allow_touching": False,
    }
    clasher.clash_sets = [clash_set]

    clasher.clash()

    assert set(clash_set["clashes"]) == {f"{a_ids['A-Wall']}-{b_ids['B-Wall']}"}
    assert run_external_clash(a_path, b_path)["summary"]["clash_count"] == 1


def test_cli_fails_closed_when_optional_bcf_api_is_absent(
    clashing_ifcs: tuple[Path, Path, dict[str, str], dict[str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if bcf_available():
        pytest.skip("bcf-client is installed; the real writer is covered below")
    a_path, b_path, _, _ = clashing_ifcs
    output = tmp_path / "clashes.json"

    status = main(
        [
            str(a_path),
            str(b_path),
            "--output",
            str(output),
            "--bcf",
            str(tmp_path / "clashes.bcfzip"),
        ]
    )

    assert status == 2
    assert "bcf-client" in capsys.readouterr().err
    assert not output.exists()


def test_cli_reports_invalid_source_date_epoch_as_controlled_bcf_input_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "clashes.json"
    bcf = tmp_path / "clashes.bcfzip"
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "not-an-epoch")
    monkeypatch.setattr(external_ifc_clash, "_load_bcf_api", lambda: object())
    monkeypatch.setattr(external_ifc_clash, "run_external_clash", lambda *args, **kwargs: {})

    status = main(
        [
            str(tmp_path / "a.ifc"),
            str(tmp_path / "b.ifc"),
            "--output",
            str(output),
            "--bcf",
            str(bcf),
        ]
    )

    assert status == 2
    assert "SOURCE_DATE_EPOCH must be a supported non-negative integer" in capsys.readouterr().err
    assert not output.exists()
    assert not bcf.exists()


def test_bcf_is_real_deterministic_bcf3_or_fails_as_optional_capability(
    clashing_ifcs: tuple[Path, Path, dict[str, str], dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a_path, b_path, _, _ = clashing_ifcs
    report = run_external_clash(a_path, b_path)
    first = tmp_path / "first.bcfzip"
    second = tmp_path / "second.bcfzip"

    if not bcf_available():
        from external_ifc_clash import ClashCapabilityError

        with pytest.raises(ClashCapabilityError, match="bcf-client"):
            write_bcf_report(report, first)
        return

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    write_bcf_report(report, first)
    write_bcf_report(report, second)

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert "bcf.version" in archive.namelist()
        assert "project.bcfp" in archive.namelist()
        assert all(member.date_time == (1980, 1, 1, 0, 0, 0) for member in archive.infolist())

    from bcf.v3.bcfxml import BcfXml

    bcf = BcfXml.load(first)
    assert bcf is not None
    try:
        assert bcf.version.version_id == "3.0"
        assert len(bcf.topics) == 1
        topic = next(iter(bcf.topics.values()))
        viewpoint = next(iter(topic.viewpoints.values()))
        assert set(viewpoint.get_selected_guids() or []) == {
            report["clashes"][0]["a"]["global_id"],
            report["clashes"][0]["b"]["global_id"],
        }
    finally:
        bcf.close()
