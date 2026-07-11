from __future__ import annotations

import copy
import json
from pathlib import Path

import provenance_contract as contract

from tools import preflight_public_package as preflight
from tools.provenance_contract import ADDITIONAL_ARTIFACTS, REQUIRED_SCREENSHOTS


def test_preflight_requires_every_public_review_image() -> None:
    expected = {
        f"screenshots/{index:02d}_{name}.png"
        for index, name in enumerate(
            (
                "coordproof_system_overview",
                "freecad_mechanical_room_overview",
                "freecad_bim_structure",
                "cadquery_asset_grid",
                "qcad_floor_plan",
                "ifc_validation_report",
                "export_formats_overview",
                "qcad_section_and_riser",
            )
        )
    }

    assert expected <= set(preflight.REQUIRED_FILES)


def test_preflight_checks_committed_evidence_before_live_validation(
    monkeypatch,
    capsys,
) -> None:
    events: list[str] = []

    def required_files() -> list[str]:
        events.append("required")
        return ["missing required file: validation/validation_report.md"]

    def live_validation() -> list[str]:
        events.append("validation")
        return []

    def provenance() -> list[str]:
        events.append("provenance")
        return []

    monkeypatch.setattr(preflight, "check_required_files", required_files)
    monkeypatch.setattr(preflight, "run_validation", live_validation)
    monkeypatch.setattr(preflight, "check_expected_counts", lambda: [])
    monkeypatch.setattr(preflight, "check_backups", lambda: [])
    monkeypatch.setattr(preflight, "check_git_ignored", lambda: [])
    monkeypatch.setattr(preflight, "check_validation_report", lambda: [])
    monkeypatch.setattr(preflight, "run_project_spec_validation", lambda: [])
    monkeypatch.setattr(preflight, "check_provenance", provenance)
    monkeypatch.setattr(preflight, "check_ifc", lambda path, min_products: [])
    monkeypatch.setattr(preflight, "scan_patterns", lambda patterns, **_kwargs: [])

    assert preflight.main() == 1
    assert events == ["required", "provenance", "validation", "provenance"]
    assert "missing required file" in capsys.readouterr().out


def test_provenance_v2_metadata_is_enforced() -> None:
    valid = {
        "schema_version": 2,
        "build_profile": "full",
        "source_date": "1970-01-01T00:00:00Z",
        "environment": {
            "python": "3.11.13",
            "implementation": "CPython",
            "platform": "test-platform",
            "machine": "test-machine",
            "packages": {
                name: "1.0"
                for name in (
                    "Pillow",
                    "cadquery",
                    "cadquery-ocp",
                    "defusedxml",
                    "ezdxf",
                    "ifcopenshell",
                    "jsonschema",
                    "reportlab",
                )
            },
            "desktop_tools": {
                "freecad": "1.1.1",
                "openscad": "2021.01",
                "qcad": "3.32.9",
            },
        },
        "artifact_producers": {
            "freecad_review_ifcopenshell": "0.8.4",
            "freecad_step_occt": "7.8",
        },
        "artifacts": {},
    }
    assert preflight.provenance_metadata_failures(valid) == []

    stale = copy.deepcopy(valid)
    stale["schema_version"] = 1
    stale["source_date"] = "not-a-date"
    del stale["artifact_producers"]
    del stale["environment"]["desktop_tools"]

    diagnostic = "\n".join(preflight.provenance_metadata_failures(stale))
    assert "schema_version" in diagnostic
    assert "source_date" in diagnostic
    assert "artifact_producers" in diagnostic
    assert "desktop_tools" in diagnostic

    impossible = copy.deepcopy(valid)
    impossible["source_date"] = "9999-99-99T99:99:99Z"
    impossible["environment"]["python"] = ""
    impossible["environment"]["packages"]["defusedxml"] = None
    impossible["environment"]["desktop_tools"]["qcad"] = "not-probed"
    impossible["artifact_producers"]["freecad_step_occt"] = "not-installed"

    diagnostic = "\n".join(preflight.provenance_metadata_failures(impossible))
    assert "source_date" in diagnostic
    assert "invalid python" in diagnostic
    assert "invalid defusedxml" in diagnostic
    assert "every desktop-tool version" in diagnostic
    assert "invalid freecad_step_occt" in diagnostic


def test_required_files_reject_directories_and_symlinks(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setattr(preflight, "REQUIRED_FILES", ["required.txt"])
    (tmp_path / "required.txt").mkdir()
    assert "not a regular file" in "\n".join(preflight.check_required_files())

    (tmp_path / "required.txt").rmdir()
    outside = tmp_path / "actual-required.txt"
    outside.write_text("outside", encoding="utf-8")
    (tmp_path / "required.txt").symlink_to(outside)
    assert "not a regular file" in "\n".join(preflight.check_required_files())


def test_required_files_reject_hardlinks(tmp_path, monkeypatch) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("evidence", encoding="utf-8")
    second.hardlink_to(first)
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setattr(preflight, "REQUIRED_FILES", ["first.txt", "second.txt"])

    diagnostic = "\n".join(preflight.check_required_files())

    assert "share an inode" in diagnostic


def test_preflight_detects_abandoned_staging_directories(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    (tmp_path / "exports" / ".coordproof-openscad-abandoned").mkdir(parents=True)

    assert ".coordproof-openscad-abandoned" in "\n".join(preflight.check_backups())

    abandoned_file = tmp_path / ".coordproof-provenance-orphan"
    abandoned_file.write_text("orphan", encoding="utf-8")
    assert abandoned_file.name in "\n".join(preflight.check_backups())


def test_text_scan_covers_cad_files_and_windows_home_paths(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    separator = chr(92)
    windows_home = f"C:{separator}Users{separator}Alice{separator}CoordProof{separator}model.ifc"
    unc_home = (
        f"{separator * 2}server{separator}Users{separator}Bob{separator}"
        f"CoordProof{separator}model.step"
    )
    for name, content in (
        ("model.ifc", windows_home),
        ("model.step", unc_home),
        ("drawing.dxf", windows_home),
        ("mesh.stl", windows_home),
    ):
        (tmp_path / name).write_text(content, encoding="utf-8")

    hits = preflight.scan_patterns(preflight.ABSOLUTE_PATH_PATTERNS)

    assert {item.split(":", 1)[0] for item in hits} == {
        "model.ifc",
        "model.step",
        "drawing.dxf",
        "mesh.stl",
    }


def test_secret_scan_survives_invalid_utf8(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    token = "github" + "_pat_" + "A" * 30
    (tmp_path / ".npmrc").write_bytes(b"\xffregistry-token=" + token.encode())

    assert ".npmrc:1" in preflight.scan_patterns(
        preflight.SECRET_PATTERNS,
        scan_binary=True,
    )


def _valid_provenance_payload(root: Path, paths: set[str]) -> dict[str, object]:
    artifacts = {
        item: {
            "sha256": preflight.file_sha256(root / item),
            "bytes": (root / item).stat().st_size,
        }
        for item in paths
    }
    return {
        "schema_version": 2,
        "build_profile": "full",
        "source_date": "1970-01-01T00:00:00Z",
        "environment": {
            "python": "3.11.13",
            "implementation": "CPython",
            "platform": "test-platform",
            "machine": "test-machine",
            "packages": {
                name: "1.0"
                for name in (
                    "Pillow",
                    "cadquery",
                    "cadquery-ocp",
                    "defusedxml",
                    "ezdxf",
                    "ifcopenshell",
                    "jsonschema",
                    "reportlab",
                )
            },
            "desktop_tools": {
                "freecad": "1.1.1",
                "openscad": "2021.01",
                "qcad": "3.32.9",
            },
        },
        "artifact_producers": {
            "freecad_review_ifcopenshell": "0.8.4",
            "freecad_step_occt": "7.8",
        },
        "artifacts": artifacts,
    }


def test_provenance_requires_every_export_index_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(contract, "GENERATOR_INPUT_GLOBS", ())
    monkeypatch.setattr(contract, "GENERATOR_INPUT_FILES", ())
    monkeypatch.setattr(contract, "PUBLIC_ARTIFACT_GLOBS", ())
    monkeypatch.setattr(
        preflight,
        "canonical_desktop_artifact_failures",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        preflight,
        "embedded_producer_versions",
        lambda **_kwargs: {
            "freecad_review_ifcopenshell": "0.8.4",
            "freecad_step_occt": "7.8",
        },
    )
    indexed = "exports/stl/indexed.stl"
    required = {*ADDITIONAL_ARTIFACTS, *REQUIRED_SCREENSHOTS, indexed}
    for item in required:
        path = tmp_path / item
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item.encode())
    (tmp_path / "manifest" / "export_index.csv").write_text(
        f"asset_id,format,path\nasset,stl,{indexed}\n",
        encoding="utf-8",
    )
    (tmp_path / "manifest" / "asset_manifest.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "asset_id": "asset",
                        "exports": {"stl": indexed},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    payload = _valid_provenance_payload(tmp_path, required)
    del payload["artifacts"][indexed]  # type: ignore[index]
    output = tmp_path / "manifest" / "build_provenance.json"
    output.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setattr(preflight, "PROVENANCE", output)

    assert f"missing golden evidence: {indexed}" in "\n".join(preflight.check_provenance())


def test_provenance_rejects_non_object_root(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "build_provenance.json"
    output.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(preflight, "PROVENANCE", output)

    assert preflight.check_provenance() == ["build provenance root must be an object"]


def test_provenance_rejects_unsafe_export_index_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    index = tmp_path / "manifest" / "export_index.csv"
    index.parent.mkdir(parents=True)
    index.write_text(
        "asset_id,format,path\nasset,stl,../outside.stl\n",
        encoding="utf-8",
    )
    output = tmp_path / "manifest" / "build_provenance.json"
    output.write_text(json.dumps({"artifacts": {}}), encoding="utf-8")
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setattr(preflight, "PROVENANCE", output)

    assert "Invalid provenance export-index row" in "\n".join(preflight.check_provenance())


def test_provenance_rejects_header_only_export_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    manifest_dir = tmp_path / "manifest"
    manifest_dir.mkdir()
    (manifest_dir / "export_index.csv").write_text(
        "asset_id,format,path\n",
        encoding="utf-8",
    )
    (manifest_dir / "asset_manifest.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "asset_id": "asset",
                        "exports": {"stl": "exports/stl/asset.stl"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = manifest_dir / "build_provenance.json"
    output.write_text(json.dumps({"artifacts": {}}), encoding="utf-8")
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setattr(preflight, "PROVENANCE", output)

    assert "does not exactly match" in "\n".join(preflight.check_provenance())


def test_provenance_rejects_duplicate_json_keys(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "build_provenance.json"
    output.write_text('{"schema_version":1,"schema_version":2}', encoding="utf-8")
    monkeypatch.setattr(preflight, "PROVENANCE", output)

    assert "duplicate JSON key" in "\n".join(preflight.check_provenance())


def test_validation_requires_fresh_run_handshake(monkeypatch) -> None:
    monkeypatch.setattr(
        preflight.subprocess,
        "run",
        lambda *_args, **_kwargs: type(
            "Result",
            (),
            {"returncode": 0, "stdout": "validator returned without running"},
        )(),
    )

    assert "did not prove a fresh" in "\n".join(preflight.run_validation())
