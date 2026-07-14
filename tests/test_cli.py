from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.validate
import pytest
from ifcopenshell.util.element import get_psets
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from coordproof import cli
from coordproof.cli import EVIDENCE_FILENAMES, MANIFEST_FILENAME, main

SOURCE = ROOT / "spec" / "mechanical_room.project.json"


def _independent_project(tmp_path: Path) -> Path:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload["project"].update(
        {
            "project_id": "cli_test_room",
            "name": "CLI Test Room",
            "description": "Independent ProjectSpec used to verify the public CLI boundary.",
        }
    )
    payload["spatial"].update(
        {
            "project_ifc_name": "CLI Test Project",
            "site_ifc_name": "CLI Test Site",
            "building_ifc_name": "CLI Test Building",
            "storey_ifc_name": "CLI Test Storey",
            "space_ifc_name": "CLI Test Coordination Space",
            "space_long_name": "CLI Test Room",
        }
    )
    space_occurrence_id = payload["spatial"]["space_occurrence_id"]
    for occurrence in payload["occurrences"]:
        if occurrence["occurrence_id"] == space_occurrence_id:
            occurrence["ifc_name"] = payload["spatial"]["space_ifc_name"]
            break
    path = tmp_path / "independent.project.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_validate_and_summary_use_the_selected_project(tmp_path: Path) -> None:
    project_path = _independent_project(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()

    assert main(["validate", str(project_path)], stdout=stdout, stderr=stderr) == 0
    assert str(project_path) in stdout.getvalue()
    assert stderr.getvalue() == ""

    stdout = io.StringIO()
    assert main(["summary", str(project_path)], stdout=stdout, stderr=stderr) == 0
    summary = json.loads(stdout.getvalue())
    assert summary["project_id"] == "cli_test_room"
    assert summary["occurrence_count"] == 40


def test_invalid_project_returns_validation_exit_code(tmp_path: Path) -> None:
    project_path = _independent_project(tmp_path)
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    payload["units"] = "inches"
    project_path.write_text(json.dumps(payload), encoding="utf-8")
    stderr = io.StringIO()

    assert main(["validate", str(project_path)], stderr=stderr) == 2
    assert "ProjectSpec schema validation failed" in stderr.getvalue()


def test_evidence_build_is_deterministic_and_self_verifying(tmp_path: Path) -> None:
    project_path = _independent_project(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"

    assert main(["build", str(project_path), "--output", str(first)]) == 0
    assert main(["build", str(project_path), "--output", str(second)]) == 0

    expected = {*EVIDENCE_FILENAMES, MANIFEST_FILENAME}
    assert {path.name for path in first.iterdir()} == expected
    assert {name: _digest(first / name) for name in expected} == {
        name: _digest(second / name) for name in expected
    }

    manifest = json.loads((first / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["project_id"] == "cli_test_room"
    assert manifest["profile"] == "evidence"
    assert {item["path"] for item in manifest["artifacts"]} == set(EVIDENCE_FILENAMES)
    for artifact in manifest["artifacts"]:
        artifact_path = first / artifact["path"]
        assert artifact["sha256"] == _digest(artifact_path)
        assert artifact["size_bytes"] == artifact_path.stat().st_size

    schema = json.loads((ROOT / "spec" / "project.schema.json").read_text(encoding="utf-8"))
    normalized = json.loads((first / "project.normalized.json").read_text(encoding="utf-8"))
    assert normalized["$schema"] == schema["$id"]
    assert not list(Draft202012Validator(schema).iter_errors(normalized))

    model = ifcopenshell.open(first / "project.ifc")
    assert model.schema == "IFC4"
    assert len(model.by_type("IfcDistributionSystem")) == 5
    assert "project.normalized.json" in (first / "ifc-entity-summary.md").read_text(
        encoding="utf-8"
    )


def test_electrical_example_builds_a_formally_valid_ifc(tmp_path: Path) -> None:
    project_path = ROOT / "examples" / "electrical_room" / "electrical_room.project.json"
    output = tmp_path / "electrical-evidence"

    assert main(["build", str(project_path), "--output", str(output)]) == 0

    model = ifcopenshell.open(output / "project.ifc")
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger, express_rules=True)
    errors = [item for item in logger.statements if item.get("level") == "error"]
    assert errors == []
    assert len(model.by_type("IfcElectricDistributionBoard")) == 3
    assert len(model.by_type("IfcTransformer")) == 1
    assert len(model.by_type("IfcElectricAppliance")) == 1
    assert len(model.by_type("IfcJunctionBox")) == 1
    products_by_tag = {
        product.Tag: product
        for product in model.by_type("IfcProduct")
        if getattr(product, "Tag", None)
    }
    switchboard_parameters = get_psets(products_by_tag["switchboard_msb_001"])[
        "Pset_ProjectSpecTypeParameters"
    ]
    transformer_parameters = get_psets(products_by_tag["transformer_t1_001"])[
        "Pset_ProjectSpecTypeParameters"
    ]
    assert switchboard_parameters["rated_voltage_v"] == 480
    assert switchboard_parameters["main_rating_a"] == 1600
    assert switchboard_parameters["short_circuit_rating_ka"] == 65
    assert transformer_parameters["rating_kva"] == 225
    assert transformer_parameters["impedance_percent"] == 5.75


def test_checkout_profiles_fail_closed_for_an_arbitrary_project(tmp_path: Path) -> None:
    project_path = _independent_project(tmp_path)
    stderr = io.StringIO()

    assert main(["build", str(project_path), "--profile", "core"], stderr=stderr) == 1
    assert "tied to the canonical CoordProof checkout" in stderr.getvalue()
    assert not (tmp_path / "build").exists()


def test_checkout_profiles_never_execute_a_script_adjacent_to_user_input(
    tmp_path: Path,
) -> None:
    lookalike = tmp_path / "lookalike"
    project_path = lookalike / "spec" / "mechanical_room.project.json"
    build_script = lookalike / "tools" / "build_all.py"
    marker = lookalike / "untrusted-script-executed"
    project_path.parent.mkdir(parents=True)
    build_script.parent.mkdir(parents=True)
    project_path.write_text("{}\n", encoding="utf-8")
    build_script.write_text(
        "from pathlib import Path\n"
        "Path(__file__).resolve().parents[1].joinpath('untrusted-script-executed').touch()\n",
        encoding="utf-8",
    )
    stderr = io.StringIO()

    assert main(["build", str(project_path), "--profile", "core"], stderr=stderr) == 1
    assert "tied to the canonical CoordProof checkout" in stderr.getvalue()
    assert not marker.exists()


def test_checkout_profiles_recognize_only_the_actual_source_checkout() -> None:
    assert cli._canonical_checkout(SOURCE.resolve()) == ROOT


def test_project_snapshot_cannot_mix_a_concurrent_source_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = _independent_project(tmp_path)
    original_load = cli._load_project

    def load_then_mutate(snapshot: Path):
        project = original_load(snapshot)
        project_path.write_text('{"changed": true}', encoding="utf-8")
        return project

    monkeypatch.setattr(cli, "_load_project", load_then_mutate)
    project, payload = cli._project_snapshot(project_path)

    assert project.project.project_id == "cli_test_room"
    assert payload["project"]["project_id"] == "cli_test_room"
    assert json.loads(project_path.read_text(encoding="utf-8")) == {"changed": True}


def test_failed_publication_invalidates_the_previous_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = tmp_path / "stage"
    output = tmp_path / "output"
    stage.mkdir()
    output.mkdir()
    for filename in (*EVIDENCE_FILENAMES, MANIFEST_FILENAME):
        (stage / filename).write_text(f"new {filename}", encoding="utf-8")
        (output / filename).write_text(f"old {filename}", encoding="utf-8")

    original_replace = cli.os.replace
    calls = 0

    def fail_second_artifact(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publication failure")
        original_replace(source, destination)

    monkeypatch.setattr(cli.os, "replace", fail_second_artifact)
    with pytest.raises(OSError, match="injected publication failure"):
        cli._publish(stage, output)

    assert not (output / MANIFEST_FILENAME).exists()


def test_evidence_build_rejects_an_output_directory_symlink(tmp_path: Path) -> None:
    project_path = _independent_project(tmp_path)
    target = tmp_path / "real-output"
    target.mkdir()
    link = tmp_path / "linked-output"
    link.symlink_to(target, target_is_directory=True)
    stderr = io.StringIO()

    assert main(["build", str(project_path), "--output", str(link)], stderr=stderr) == 1
    assert "refusing to publish through a symlink" in stderr.getvalue()
    assert list(target.iterdir()) == []


def test_evidence_build_rejects_stale_unmanifested_output(tmp_path: Path) -> None:
    project_path = _independent_project(tmp_path)
    output = tmp_path / "evidence"
    output.mkdir()
    stale = output / "old-review-note.txt"
    stale.write_text("not part of the six-file evidence contract\n", encoding="utf-8")
    stderr = io.StringIO()

    assert main(["build", str(project_path), "--output", str(output)], stderr=stderr) == 1
    assert "must be a dedicated directory" in stderr.getvalue()
    assert stale.read_text(encoding="utf-8").startswith("not part")
    assert {path.name for path in output.iterdir()} == {stale.name}


def test_clash_command_dispatches_the_public_engine_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeClashError(RuntimeError):
        pass

    class FakeCapabilityError(FakeClashError):
        pass

    def record_config(**kwargs: object) -> SimpleNamespace:
        calls["config"] = kwargs
        return SimpleNamespace(**kwargs)

    def record_limits(**kwargs: object) -> SimpleNamespace:
        calls["limits"] = kwargs
        return SimpleNamespace(**kwargs)

    def run_external_clash(
        a_ifc: Path,
        b_ifc: Path,
        *,
        config: SimpleNamespace,
        limits: SimpleNamespace,
    ) -> dict[str, object]:
        calls["run"] = (a_ifc, b_ifc, config, limits)
        return {"summary": {"clash_count": 2}}

    fake_module = SimpleNamespace(
        ClashError=FakeClashError,
        ClashCapabilityError=FakeCapabilityError,
        ClashConfig=record_config,
        ClashLimits=record_limits,
        bcf_available=lambda: True,
        run_external_clash=run_external_clash,
        preflight_output_paths=lambda output, bcf: calls.update(preflight=(output, bcf)),
        write_reports=lambda report, output, bcf: calls.update(
            reports=(report, output, bcf)
        ),
    )
    monkeypatch.setattr(cli, "_legacy_module", lambda name: fake_module)
    a_ifc = tmp_path / "architecture.ifc"
    b_ifc = tmp_path / "mep.ifc"
    output = tmp_path / "clashes.json"
    bcf = tmp_path / "clashes.bcfzip"
    stdout = io.StringIO()

    exit_code = main(
        [
            "clash",
            str(a_ifc),
            str(b_ifc),
            "--output",
            str(output),
            "--bcf",
            str(bcf),
            "--a-label",
            "Architecture",
            "--b-label",
            "MEP",
            "--mode",
            "intersection",
            "--a-class",
            "IfcWall",
            "--b-class",
            "IfcFlowSegment",
            "--tolerance-mm",
            "3.5",
            "--max-results",
            "25",
            "--workers",
            "2",
            "--fail-on-clash",
        ],
        stdout=stdout,
    )

    assert exit_code == 1
    assert calls["config"] == {
        "mode": "intersection",
        "a_label": "Architecture",
        "b_label": "MEP",
        "a_classes": ("IfcWall",),
        "b_classes": ("IfcFlowSegment",),
        "tolerance_mm": 3.5,
        "clearance_mm": 50.0,
        "allow_touching": False,
    }
    assert calls["limits"] == {
        "max_file_bytes": 256 * 1024 * 1024,
        "max_elements_per_side": 5_000,
        "max_triangles_per_side": 5_000_000,
        "max_candidate_pairs": 10_000_000,
        "max_results": 25,
        "workers": 2,
    }
    assert calls["preflight"] == (output, bcf)
    assert calls["reports"][1:] == (output, bcf)
    assert "2 clash(es)" in stdout.getvalue()
