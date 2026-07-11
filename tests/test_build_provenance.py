from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import build_provenance as provenance


def test_desktop_versions_are_sanitized_to_stable_tokens(
    monkeypatch,
) -> None:
    monkeypatch.setattr(provenance, "freecad_command", lambda: Path("/private/bin/freecadcmd"))
    monkeypatch.setattr(provenance, "openscad_command", lambda: Path("/private/bin/openscad"))
    monkeypatch.setattr(provenance, "qcad_pdf_command", lambda: Path("/private/bin/dwg2pdf"))
    monkeypatch.setattr(
        provenance,
        "_qcad_version_executable",
        lambda _exporter: Path("/private/bin/QCAD"),
    )

    outputs = {
        "freecadcmd": "FreeCAD 1.1.1 Revision: 20260414 (Git shallow)\n",
        "openscad": "OpenSCAD version 2021.01\n",
        "QCAD": (
            "QCAD version  3.32.9\n21:43:46: Debug: loading plugins...\n"
            "Version: 3.32.9\n"
        ),
    }

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=outputs[Path(command[0]).name], stderr="")

    monkeypatch.setattr(provenance.subprocess, "run", fake_run)

    versions = provenance.desktop_tool_versions()

    assert versions == {"freecad": "1.1.1", "openscad": "2021.01", "qcad": "3.32.9"}
    assert "/private" not in repr(versions)
    assert "21:43:46" not in repr(versions)


def test_missing_desktop_tools_are_nonfatal(monkeypatch) -> None:
    monkeypatch.setattr(provenance, "freecad_command", lambda: None)
    monkeypatch.setattr(provenance, "openscad_command", lambda: None)
    monkeypatch.setattr(provenance, "qcad_pdf_command", lambda: None)

    assert provenance.desktop_tool_versions() == {
        "freecad": provenance.NOT_INSTALLED,
        "openscad": provenance.NOT_INSTALLED,
        "qcad": provenance.NOT_INSTALLED,
    }


def test_embedded_freecad_producer_versions_are_extracted(tmp_path: Path) -> None:
    step = tmp_path / "assembly.step"
    step.write_text(
        "FILE_NAME('assembly.step','1970-01-01T00:00:00',(''),(''),"
        "'Open CASCADE STEP processor 7.8','FreeCAD','Unknown');\n",
        encoding="utf-8",
    )
    review_ifc = tmp_path / "review.ifc"
    review_ifc.write_text(
        "FILE_NAME('review.ifc','1970-01-01T00:00:00',(''),(''),"
        "'IfcOpenShell 0.8.4','IfcOpenShell 0.8.4','');\n",
        encoding="utf-8",
    )

    assert provenance.embedded_producer_versions(
        step_path=step,
        review_ifc_path=review_ifc,
    ) == {
        "freecad_step_occt": "7.8",
        "freecad_review_ifcopenshell": "0.8.4",
    }


def test_core_payload_never_executes_optional_desktop_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    monkeypatch.setattr(provenance, "artifact_paths", lambda: [])
    monkeypatch.setattr(provenance, "package_versions", lambda: {"defusedxml": "0.7.1"})
    monkeypatch.setattr(
        provenance,
        "desktop_tool_versions",
        lambda: (_ for _ in ()).throw(AssertionError("desktop probe executed")),
    )
    monkeypatch.setattr(
        provenance,
        "embedded_producer_versions",
        lambda: {
            "freecad_step_occt": "7.8",
            "freecad_review_ifcopenshell": "0.8.4",
        },
    )

    payload = provenance.build_payload(profile="core")

    assert payload["source_date"] == "1970-01-01T00:00:00Z"
    assert payload["environment"]["desktop_tools"] == {
        "freecad": provenance.NOT_PROBED,
        "openscad": provenance.NOT_PROBED,
        "qcad": provenance.NOT_PROBED,
    }


def test_source_date_epoch_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "-1")

    with pytest.raises(ValueError, match="non-negative integer"):
        provenance.reproducible_timestamp()


def test_provenance_records_hardened_xml_dependency() -> None:
    assert provenance.package_versions()["defusedxml"] == "0.7.1"


def test_provenance_publish_failure_preserves_last_known_good(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "build_provenance.json"
    output.write_bytes(b"last-known-good\n")
    monkeypatch.setattr(provenance, "OUTPUT", output)
    monkeypatch.setattr(
        provenance,
        "parse_args",
        lambda: SimpleNamespace(profile="core"),
    )
    monkeypatch.setattr(provenance, "build_payload", lambda **_kwargs: {"new": True})
    monkeypatch.setattr(provenance, "provenance_metadata_failures", lambda _payload: [])
    monkeypatch.setattr(
        provenance,
        "publish_staged_files",
        lambda _pairs: (_ for _ in ()).throw(OSError("injected publication failure")),
    )

    with pytest.raises(OSError, match="injected publication failure"):
        provenance.main()

    assert output.read_bytes() == b"last-known-good\n"


def test_invalid_full_provenance_is_not_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "build_provenance.json"
    output.write_bytes(b"last-known-good\n")
    monkeypatch.setattr(provenance, "OUTPUT", output)
    monkeypatch.setattr(provenance, "parse_args", lambda: SimpleNamespace(profile="full"))
    monkeypatch.setattr(
        provenance,
        "build_payload",
        lambda **_kwargs: {
            "schema_version": 2,
            "build_profile": "full",
            "source_date": "1970-01-01T00:00:00Z",
            "environment": {
                "python": "3.11",
                "implementation": "CPython",
                "platform": "test",
                "machine": "test",
                "packages": {name: "1.0" for name in provenance.PACKAGE_NAMES},
                "desktop_tools": {
                    "freecad": provenance.VERSION_UNAVAILABLE,
                    "openscad": "2021.01",
                    "qcad": "3.32.9",
                },
            },
            "artifact_producers": {
                "freecad_step_occt": "7.8",
                "freecad_review_ifcopenshell": "0.8.4",
            },
            "artifacts": {},
        },
    )

    with pytest.raises(ValueError, match="Refusing to publish invalid"):
        provenance.main()

    assert output.read_bytes() == b"last-known-good\n"
