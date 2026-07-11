from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import generate_freecad_assets as freecad_generator
import ifcopenshell
import ifcopenshell.guid
import pytest
from freecad_artifact_normalization import (
    FCSTD_ARCHIVE_COMMENT,
    FCSTD_UUID_NAMESPACE,
    ArtifactNormalizationError,
    _duplicate_relationship_ids,
    _validate_review_hierarchy,
    normalize_fcstd,
    normalize_review_ifc,
    normalize_step_header,
)

ROOT = Path(__file__).resolve().parents[1]


def write_step(path: Path, *, filename: str, timestamp: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "ISO-10303-21;\n"
        "HEADER;\n"
        "FILE_DESCRIPTION(('FreeCAD Model'),'2;1');\n"
        f"FILE_NAME('{filename}','{timestamp}',('Author'),(''),'OCCT','FreeCAD','');\n"
        "FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
        "ENDSEC;\n"
        "DATA;\n"
        "#1=CARTESIAN_POINT('',(0.,0.,0.));\n"
        "ENDSEC;\n"
        "END-ISO-10303-21;\n",
        encoding="utf-8",
    )


def write_fcstd(
    path: Path,
    *,
    timestamp: str,
    document_uid: str,
    first_object_id: int,
    zip_timestamp: tuple[int, int, int, int, int, int],
    reverse_members: bool = False,
    crlf_document: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = f"""<?xml version='1.0' encoding='utf-8'?>
<Document SchemaVersion="4">
    <Properties Count="3">
        <Property name="CreationDate" type="App::PropertyString">
            <String value="{timestamp}"/>
        </Property>
        <Property name="LastModifiedDate" type="App::PropertyString">
            <String value="{timestamp}"/>
        </Property>
        <Property name="Uid" type="App::PropertyUUID">
            <Uuid value="{document_uid}"/>
        </Property>
    </Properties>
    <Objects Count="2">
        <Object type="Part::Feature" name="Shape" id="{first_object_id}" />
        <Object type="App::DocumentObjectGroup" name="Group" id="{first_object_id + 1}" />
    </Objects>
    <ObjectData Count="2">
        <Object name="Shape" />
        <Object name="Group" />
    </ObjectData>
</Document>
"""
    if crlf_document:
        document = document.replace("\n", "\r\n")
    members = [
        ("Document.xml", document.encode("utf-8")),
        ("Shape.Shape.brp", b"deterministic-brep-payload"),
    ]
    if reverse_members:
        members.reverse()
    with zipfile.ZipFile(path, "w") as archive:
        archive.comment = FCSTD_ARCHIVE_COMMENT
        for name, payload in members:
            info = zipfile.ZipInfo(name, date_time=zip_timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED)


def test_step_header_normalization_is_exact_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    paths = [tmp_path / folder / "mechanical_room_assembly.step" for folder in ("a", "b")]
    write_step(paths[0], filename="Open CASCADE Shape Model", timestamp="2026-07-10T12:00:01")
    write_step(
        paths[1],
        filename="/private" + "/" + "tmp/assembly.step",
        timestamp="2031-09-08T07:06:05",
    )

    for path in paths:
        normalize_step_header(path)

    assert paths[0].read_bytes() == paths[1].read_bytes()
    assert "FILE_NAME('mechanical_room_assembly.step','1970-01-01T00:00:00'" in paths[
        0
    ].read_text(encoding="utf-8")
    before = paths[0].read_bytes()
    normalize_step_header(paths[0])
    assert paths[0].read_bytes() == before


def test_step_normalization_rejects_an_invalid_envelope_without_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad.step"
    path.write_text("FILE_NAME('bad','now');\n", encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(ArtifactNormalizationError, match="invalid ISO-10303"):
        normalize_step_header(path)

    assert path.read_bytes() == before


def test_fcstd_normalization_is_exact_structural_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    paths = [tmp_path / folder / "model.FCStd" for folder in ("a", "b")]
    write_fcstd(
        paths[0],
        timestamp="2026-07-10T12:00:01-04:00",
        document_uid="11111111-1111-4111-8111-111111111111",
        first_object_id=4041,
        zip_timestamp=(2026, 7, 10, 12, 0, 2),
    )
    write_fcstd(
        paths[1],
        timestamp="2031-09-08T07:06:05+02:00",
        document_uid="22222222-2222-4222-8222-222222222222",
        first_object_id=3792,
        zip_timestamp=(2031, 9, 8, 7, 6, 6),
        crlf_document=True,
    )

    for path in paths:
        normalize_fcstd(
            path,
            artifact_identity="freecad/model.FCStd",
            expected_object_count=2,
            expected_shape_members=1,
        )

    assert paths[0].read_bytes() == paths[1].read_bytes()
    with zipfile.ZipFile(paths[0]) as archive:
        assert archive.comment == FCSTD_ARCHIVE_COMMENT
        assert archive.namelist() == ["Document.xml", "Shape.Shape.brp"]
        assert {info.date_time for info in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        document = archive.read("Document.xml")
        assert archive.read("Shape.Shape.brp") == b"deterministic-brep-payload"
    root = ET.fromstring(document)
    assert root.find(".//Property[@name='CreationDate']/String").attrib["value"] == (
        "1970-01-01T00:00:00Z"
    )
    assert root.find(".//Property[@name='LastModifiedDate']/String").attrib["value"] == (
        "1970-01-01T00:00:00Z"
    )
    assert root.find(".//Property[@name='Uid']/Uuid").attrib["value"] == str(
        uuid.uuid5(FCSTD_UUID_NAMESPACE, "freecad/model.FCStd")
    )
    assert [item.attrib["id"] for item in root.findall("./Objects/Object")] == ["1", "2"]

    before = paths[0].read_bytes()
    normalize_fcstd(
        paths[0],
        artifact_identity="freecad/model.FCStd",
        expected_object_count=2,
        expected_shape_members=1,
    )
    assert paths[0].read_bytes() == before


def test_fcstd_normalization_preserves_required_producer_member_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reordered.FCStd"
    write_fcstd(
        path,
        timestamp="2026-07-10T12:00:01-04:00",
        document_uid="11111111-1111-4111-8111-111111111111",
        first_object_id=4041,
        zip_timestamp=(2026, 7, 10, 12, 0, 2),
        reverse_members=True,
    )
    before = path.read_bytes()

    with pytest.raises(ArtifactNormalizationError, match="must be the first archive member"):
        normalize_fcstd(
            path,
            artifact_identity="freecad/model.FCStd",
            expected_object_count=2,
            expected_shape_members=1,
        )

    assert path.read_bytes() == before


def test_fcstd_normalization_fails_closed_on_unexpected_counts(tmp_path: Path) -> None:
    path = tmp_path / "model.FCStd"
    write_fcstd(
        path,
        timestamp="2026-07-10T12:00:01-04:00",
        document_uid="11111111-1111-4111-8111-111111111111",
        first_object_id=4041,
        zip_timestamp=(2026, 7, 10, 12, 0, 2),
    )
    before = path.read_bytes()

    with pytest.raises(ArtifactNormalizationError, match="unexpected FCStd object count"):
        normalize_fcstd(
            path,
            artifact_identity="freecad/model.FCStd",
            expected_object_count=3,
            expected_shape_members=1,
        )

    assert path.read_bytes() == before


def test_fcstd_normalization_rejects_xml_entities_without_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "hostile.FCStd"
    write_fcstd(
        path,
        timestamp="2026-07-10T12:00:01-04:00",
        document_uid="11111111-1111-4111-8111-111111111111",
        first_object_id=4041,
        zip_timestamp=(2026, 7, 10, 12, 0, 2),
    )
    with zipfile.ZipFile(path) as archive:
        comment = archive.comment
        members = [(info, archive.read(info.filename)) for info in archive.infolist()]
    with zipfile.ZipFile(path, "w") as archive:
        archive.comment = comment
        for info, payload in members:
            if info.filename == "Document.xml":
                payload = payload.replace(
                    b"<Document SchemaVersion=\"4\">",
                    (
                        b'<!DOCTYPE Document [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
                        b'<Document SchemaVersion="4">'
                    ),
                    1,
                ).replace(b"2026-07-10T12:00:01-04:00", b"&xxe;", 1)
            archive.writestr(info, payload)
    before = path.read_bytes()

    with pytest.raises(ArtifactNormalizationError, match="valid UTF-8 XML"):
        normalize_fcstd(
            path,
            artifact_identity="freecad/hostile.FCStd",
            expected_object_count=2,
            expected_shape_members=1,
        )

    assert path.read_bytes() == before


def make_review_ifc_variant(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    model = ifcopenshell.open(str(source))
    text = source.read_text(encoding="utf-8")
    text, header_count = re.subn(
        r"^(FILE_NAME\('[^']*',)'[^']*'",
        r"\g<1>'2031-09-08T07:06:05'",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    assert header_count == 1
    text, owner_count = re.subn(
        r"^(#[0-9]+=IFCOWNERHISTORY\([^,]+,[^,]+,[^,]+,[^,]+,)"
        r"([^,]+)(,[^,]+,[^,]+,)([^)]+)(\);)$",
        r"\g<1>123\g<3>456\g<5>",
        text,
        flags=re.MULTILINE,
    )
    assert owner_count == len(model.by_type("IfcOwnerHistory"))
    for index, root in enumerate(model.by_type("IfcRoot"), start=1):
        alternate_guid = ifcopenshell.guid.compress(
            uuid.uuid5(uuid.NAMESPACE_OID, f"alternate-root:{index}").hex
        )
        pattern = re.compile(
            rf"^(#{root.id()}={root.is_a().upper()}\()'[^']{{22}}'",
            flags=re.MULTILINE,
        )
        text, count = pattern.subn(rf"\g<1>'{alternate_guid}'", text)
        assert count == 1
    destination.write_text(text, encoding="utf-8")


def test_review_ifc_normalization_is_exact_valid_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    source = ROOT / "bim" / "mechanical_room_freecad_review.ifc"
    paths = [tmp_path / folder / source.name for folder in ("a", "b")]
    paths[0].parent.mkdir(parents=True)
    paths[0].write_bytes(source.read_bytes())
    make_review_ifc_variant(source, paths[1])
    original = ifcopenshell.open(str(source))
    expected_products = sorted(
        (product.is_a(), product.Name) for product in original.by_type("IfcProduct")
    )

    for path in paths:
        normalize_review_ifc(
            path,
            expected_root_count=72,
            expected_product_count=65,
            expected_duplicate_relationship_count=1,
        )

    assert paths[0].read_bytes() == paths[1].read_bytes()
    normalized = ifcopenshell.open(str(paths[0]))
    assert normalized.schema == "IFC4"
    assert sorted(
        (product.is_a(), product.Name) for product in normalized.by_type("IfcProduct")
    ) == expected_products
    roots = normalized.by_type("IfcRoot")
    assert len(roots) == len({root.GlobalId for root in roots}) == 71
    assert all(
        owner.CreationDate == 0 and owner.LastModifiedDate == 0
        for owner in normalized.by_type("IfcOwnerHistory")
    )
    assert "'1970-01-01T00:00:00'" in paths[0].read_text(encoding="utf-8").splitlines()[3]

    before = paths[0].read_bytes()
    normalize_review_ifc(
        paths[0],
        expected_root_count=72,
        expected_product_count=65,
        expected_duplicate_relationship_count=1,
    )
    assert paths[0].read_bytes() == before


def test_review_ifc_normalization_requires_exact_spatial_hierarchy() -> None:
    model = ifcopenshell.open(str(ROOT / "bim" / "mechanical_room_freecad_review.ifc"))
    roots = list(model.by_type("IfcRoot"))
    site_link = next(
        relationship
        for relationship in model.by_type("IfcRelAggregates")
        if relationship.Name == "SiteLink"
    )
    site_link.Name = "BuildingDirectLink"
    site_link.RelatingObject = model.by_type("IfcProject")[0]

    with pytest.raises(ArtifactNormalizationError, match="missing required spatial hierarchy"):
        _validate_review_hierarchy(
            roots,
            _duplicate_relationship_ids(roots),
            expected_duplicate_relationship_count=1,
        )


def test_failed_staged_normalization_preserves_every_canonical_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def outputs(folder: str) -> freecad_generator.FreeCADOutputs:
        root = tmp_path / folder
        root.mkdir()
        return freecad_generator.FreeCADOutputs(
            source_model=root / "mechanical_room.FCStd",
            bim_model=root / "mechanical_room_bim.FCStd",
            assembly_step=root / "mechanical_room_assembly.step",
            review_ifc=root / "mechanical_room_freecad_review.ifc",
        )

    staged = outputs("staged")
    canonical = outputs("canonical")
    for index, path in enumerate(staged.paths()):
        path.write_bytes(f"staged-{index}".encode())
    for index, path in enumerate(canonical.paths()):
        path.write_bytes(f"last-known-good-{index}".encode())
    before = {path: path.read_bytes() for path in canonical.paths()}

    monkeypatch.setattr(freecad_generator, "normalize_step_header", lambda path: None)

    def fail_normalization(*args, **kwargs) -> None:
        raise ArtifactNormalizationError("injected staged validation failure")

    monkeypatch.setattr(freecad_generator, "normalize_fcstd", fail_normalization)

    with pytest.raises(ArtifactNormalizationError, match="injected staged"):
        freecad_generator.normalize_and_publish(
            staged,
            canonical,
            executable=Path("/fake/freecadcmd"),
        )

    assert {path: path.read_bytes() for path in canonical.paths()} == before


def test_freecad_macros_stage_outputs_and_fail_closed_on_step_export() -> None:
    build_macro = (ROOT / "freecad" / "build_mechanical_room.FCMacro").read_text(
        encoding="utf-8"
    )
    ifc_macro = (ROOT / "freecad" / "export_bim_ifc.FCMacro").read_text(
        encoding="utf-8"
    )
    validation_macro = (
        ROOT / "freecad" / "validate_staged_outputs.FCMacro"
    ).read_text(encoding="utf-8")

    assert "COORDPROOF_FREECAD_SOURCE_PATH" in build_macro
    assert "COORDPROOF_FREECAD_BIM_PATH" in build_macro
    assert "COORDPROOF_FREECAD_ASSEMBLY_STEP_PATH" in build_macro
    assert "COORDPROOF_FREECAD_REVIEW_IFC_PATH" in ifc_macro
    assert "Assembly STEP export skipped" not in build_macro
    assert "os.replace(temporary_step_path, ASSEMBLY_STEP_PATH)" in build_macro
    assert 'raise RuntimeError(f"Assembly STEP export failed:' in build_macro
    assert ") from exc" in build_macro
    assert "Shape.isValid()" in validation_macro
    assert "Part.read(ASSEMBLY_STEP_PATH)" in validation_macro
    assert "len(step_shape.Solids) != 122" in validation_macro


def test_freecad_macros_use_reliable_command_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro = tmp_path / "macro.FCMacro"
    macro.write_text("raise RuntimeError('failure')\n", encoding="utf-8")
    observed: list[str] = []

    def fake_run(command, **_kwargs) -> None:
        observed.extend(command)

    monkeypatch.setattr(freecad_generator.subprocess, "run", fake_run)

    freecad_generator.run_macro(Path("/fake/freecadcmd"), macro, env={})

    assert observed[:2] == ["/fake/freecadcmd", "-c"]
    assert "runpy.run_path" in observed[2]
    assert str(macro) in observed[2]


def test_native_reopen_failure_preserves_every_canonical_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def outputs(folder: str) -> freecad_generator.FreeCADOutputs:
        root = tmp_path / folder
        root.mkdir()
        return freecad_generator.FreeCADOutputs(
            source_model=root / "mechanical_room.FCStd",
            bim_model=root / "mechanical_room_bim.FCStd",
            assembly_step=root / "mechanical_room_assembly.step",
            review_ifc=root / "mechanical_room_freecad_review.ifc",
        )

    staged = outputs("native-staged")
    canonical = outputs("native-canonical")
    for path in staged.paths():
        path.write_bytes(b"staged")
    for path in canonical.paths():
        path.write_bytes(b"last-known-good")
    before = {path: path.read_bytes() for path in canonical.paths()}

    monkeypatch.setattr(freecad_generator, "normalize_step_header", lambda _path: None)
    monkeypatch.setattr(freecad_generator, "normalize_fcstd", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        freecad_generator,
        "normalize_review_ifc",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        freecad_generator,
        "run_macro",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("native reopen failed")),
    )

    with pytest.raises(RuntimeError, match="native reopen failed"):
        freecad_generator.normalize_and_publish(
            staged,
            canonical,
            executable=Path("/fake/freecadcmd"),
        )

    assert {path: path.read_bytes() for path in canonical.paths()} == before
