from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import generate_all as cadquery_generate_all
import pytest
import reconcile_parameters as reconciliation
import validate_reconciliation as reconciliation_validation
from project_spec import load_project_spec
from reconcile_parameters import (
    DEFAULT_CONTRACT_PATH,
    DEFAULT_CSV_PATH,
    DEFAULT_MARKDOWN_PATH,
    DEFAULT_PROJECT_SPEC_PATH,
    ReconciliationError,
    _python_mapping,
    load_contract,
    reconcile,
    render_reports,
)

from tools.generate_openscad_exports import (
    ASSETS as OPENSCAD_ASSETS,
)
from tools.generate_openscad_exports import (
    PARAMETER_ALIASES,
    build_openscad_command,
)

ROW_FIELDS = {
    "relation_id",
    "subject_kind",
    "subject_id",
    "canonical_path",
    "producer",
    "producer_path",
    "relation",
    "expected",
    "actual",
    "unit",
    "tolerance_mm",
    "status",
    "reason",
}
ROOT = DEFAULT_PROJECT_SPEC_PATH.parents[1]
RECONCILIATION_SCHEMA_PATH = DEFAULT_CONTRACT_PATH.with_name(
    "reconciliation.schema.json"
)
RECONCILIATION_CONTRACT_V1_FINGERPRINT = (
    "df5ca1354eaeb929e63fcff1c7b6170901d7cf4e992ba43f796f4f2f7d9b08f3"
)
RECONCILIATION_SCHEMA_V1_FINGERPRINT = (
    "36ea29e197bd831af859608eea2a8ad348bec94f86a210e7a1dabb3459df3f9d"
)


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def canonical_json_fingerprint(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def copy_producer_sources(target_root: Path) -> None:
    for folder in ("cadquery", "openscad"):
        shutil.copytree(ROOT / folder, target_root / folder)


def project_payload() -> dict[str, object]:
    return json.loads(DEFAULT_PROJECT_SPEC_PATH.read_text(encoding="utf-8"))


def asset_type(payload: dict[str, object], type_id: str) -> dict[str, object]:
    return next(item for item in payload["asset_types"] if item["type_id"] == type_id)


def occurrence(payload: dict[str, object], occurrence_id: str) -> dict[str, object]:
    return next(
        item for item in payload["occurrences"] if item["occurrence_id"] == occurrence_id
    )


def failed_row(
    result: dict[str, object],
    *,
    subject_id: str,
    parameter: str,
) -> dict[str, object]:
    matches = [
        row
        for row in result["rows"]
        if row["status"] == "failed"
        and row["subject_id"] == subject_id
        and row["canonical_path"].rsplit(".", 1)[-1] == parameter
    ]
    assert len(matches) == 1, matches
    return matches[0]


def test_reconciliation_v1_contract_migration_fingerprint() -> None:
    assert (
        canonical_json_fingerprint(DEFAULT_CONTRACT_PATH)
        == RECONCILIATION_CONTRACT_V1_FINGERPRINT
    )


def test_reconciliation_v1_schema_migration_fingerprint() -> None:
    assert (
        canonical_json_fingerprint(RECONCILIATION_SCHEMA_PATH)
        == RECONCILIATION_SCHEMA_V1_FINGERPRINT
    )


@pytest.mark.parametrize("stale_format", ["csv", "markdown"])
def test_validation_rejects_stale_committed_reconciliation_report(
    tmp_path: Path,
    monkeypatch,
    stale_format: str,
) -> None:
    live_result = reconcile()
    expected_csv, expected_markdown = render_reports(live_result)
    csv_path = tmp_path / DEFAULT_CSV_PATH.name
    markdown_path = tmp_path / DEFAULT_MARKDOWN_PATH.name
    csv_path.write_text(expected_csv, encoding="utf-8")
    markdown_path.write_text(expected_markdown, encoding="utf-8")
    stale_path = csv_path if stale_format == "csv" else markdown_path
    stale_path.write_text(
        stale_path.read_text(encoding="utf-8") + "stale evidence\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(reconciliation_validation, "ROOT", tmp_path)
    monkeypatch.setattr(reconciliation_validation, "DEFAULT_CSV_PATH", csv_path)
    monkeypatch.setattr(
        reconciliation_validation,
        "DEFAULT_MARKDOWN_PATH",
        markdown_path,
    )

    result = reconciliation_validation.validate()

    assert result["status"] == "failed"
    assert result["summary"]["failure_count"] == 1
    assert result["failures"] == [
        f"[STALE_REPORT] {stale_path.name} does not match live reconciliation"
    ]


def test_validation_never_launders_a_failed_live_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    failed_result = {
        "name": "Parameter Reconciliation",
        "status": "failed",
        "summary": {"failed_row_count": 1},
        "failures": [],
        "warnings": [],
        "rows": [
            {
                "relation_id": "failed_relation",
                "subject_kind": "occurrence",
                "subject_id": "failed_occurrence",
                "canonical_path": "$.asset_types[failed].parameters.length_mm",
                "producer": "project_spec.relation",
                "producer_path": "$.occurrences[failed].dimensions_mm[0]",
                "relation": "derived",
                "expected": None,
                "actual": None,
                "unit": "mm",
                "tolerance_mm": 0,
                "status": "failed",
                "reason": "",
            }
        ],
    }
    csv_text, markdown_text = render_reports(failed_result)
    csv_path = tmp_path / DEFAULT_CSV_PATH.name
    markdown_path = tmp_path / DEFAULT_MARKDOWN_PATH.name
    csv_path.write_text(csv_text, encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")
    monkeypatch.setattr(reconciliation_validation, "ROOT", tmp_path)
    monkeypatch.setattr(reconciliation_validation, "DEFAULT_CSV_PATH", csv_path)
    monkeypatch.setattr(
        reconciliation_validation,
        "DEFAULT_MARKDOWN_PATH",
        markdown_path,
    )
    monkeypatch.setattr(
        reconciliation_validation,
        "reconcile",
        lambda: copy.deepcopy(failed_result),
    )

    result = reconciliation_validation.validate()

    assert result["status"] == "failed"
    assert result["failures"] == [
        "[LIVE_RECONCILIATION] reconciliation failed without a diagnostic"
    ]


def test_reconciliation_rows_are_complete_deterministic_and_passing() -> None:
    first = reconcile()
    second = reconcile()

    assert first["name"] == "Parameter Reconciliation"
    assert first["status"] == "passed", first["failures"]
    assert first["failures"] == []
    assert first["rows"]
    assert first["rows"] == second["rows"]
    assert json.dumps(first["rows"], sort_keys=True) == json.dumps(
        second["rows"], sort_keys=True
    )
    assert all(set(row) == ROW_FIELDS for row in first["rows"])
    assert all(row["status"] == "passed" for row in first["rows"])
    assert {"equal", "derived", "excluded", "override"} <= {
        row["relation"] for row in first["rows"]
    }
    assert all(
        isinstance(row["reason"], str) and row["reason"].strip()
        for row in first["rows"]
        if row["relation"] == "override"
    )
    assert any(
        row["expected"] != row["actual"]
        for row in first["rows"]
        if row["relation"] == "override"
    )

    identities = [
        (
            row["relation_id"],
            row["subject_kind"],
            row["subject_id"],
            row["canonical_path"],
            row["producer"],
            row["producer_path"],
        )
        for row in first["rows"]
    ]
    assert len(identities) == len(set(identities))


def test_excluded_inputs_are_explicit_auditable_evidence_rows() -> None:
    contract = load_contract(DEFAULT_CONTRACT_PATH)
    expected = {
        (producer["producer_id"], name): reason
        for producer in contract["producers"]
        for name, reason in producer.get("excluded_parameters", {}).items()
    }

    result = reconcile()
    rows = [row for row in result["rows"] if row["relation"] == "excluded"]

    assert len(rows) == len(expected) == 3
    _, markdown = render_reports(result)
    for row in rows:
        key = (row["producer"], row["producer_path"].rsplit("::", 1)[-1])
        assert row["status"] == "passed"
        assert row["canonical_path"].startswith("$.producers[")
        assert row["reason"] == expected[key]
        assert row["producer"] in markdown
        assert row["producer_path"] in markdown
        assert row["reason"] in markdown


def test_every_scoped_producer_and_canonical_parameter_has_a_row() -> None:
    contract = load_contract(DEFAULT_CONTRACT_PATH)
    project = project_payload()
    types = {item["type_id"]: item for item in project["asset_types"]}
    result = reconcile()

    assert result["status"] == "passed", result["failures"]
    rows = result["rows"]
    producer_ids = {producer["producer_id"] for producer in contract["producers"]}
    assert producer_ids <= {row["producer"] for row in rows}

    for producer in contract["producers"]:
        producer_id = producer["producer_id"]
        subject = producer["subject"]
        assert subject["kind"] == "asset_type"
        parameters = types[subject["id"]]["parameters"]
        parameter_map = producer["parameter_map"]
        if parameter_map == {"*": "*"}:
            canonical_names = {
                name
                for name, value in parameters.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
        else:
            canonical_names = set(parameter_map)

        scoped_rows = [
            row
            for row in rows
            if row["producer"] == producer_id
            and row["subject_kind"] == subject["kind"]
            and row["subject_id"] == subject["id"]
        ]
        observed_names = {
            name
            for name in canonical_names
            if any(row["canonical_path"].rsplit(".", 1)[-1] == name for row in scoped_rows)
        }
        assert observed_names == canonical_names, producer_id


def test_removing_a_parameter_binding_fails_closed(
    tmp_path: Path,
) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    producer = next(
        item
        for item in contract["producers"]
        if item["parameter_map"] != {"*": "*"} and len(item["parameter_map"]) > 1
    )
    removed_name = next(iter(producer["parameter_map"]))
    producer["parameter_map"].pop(removed_name)
    path = write_json(tmp_path / "missing-binding.json", contract)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH, contract_path=path)

    assert result["status"] == "failed"
    diagnostic = "\n".join(result["failures"])
    assert producer["producer_id"] in diagnostic
    assert removed_name in diagnostic
    assert "unmapped" in diagnostic.lower() or "coverage" in diagnostic.lower()


def test_override_relation_requires_a_nonempty_reason(tmp_path: Path) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    override = next(
        relation
        for relation in contract["relations"]
        if relation["classification"] == "override"
    )
    override.pop("reason", None)
    path = write_json(tmp_path / "override-without-reason.json", contract)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH, contract_path=path)

    assert result["status"] == "failed"
    diagnostic = "\n".join(result["failures"])
    assert override["relation_id"] in diagnostic
    assert "override" in diagnostic.lower()
    assert "reason" in diagnostic.lower()


def test_relations_must_point_from_type_to_occurrence(tmp_path: Path) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    relation = next(
        item for item in contract["relations"] if item["relation_id"] == "duct_main_width"
    )
    relation["from"] = copy.deepcopy(relation["to"])
    path = write_json(tmp_path / "wrong-direction.json", contract)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH, contract_path=path)

    assert result["status"] == "failed"
    diagnostic = "\n".join(result["failures"])
    assert "duct_main_width" in diagnostic
    assert "asset_type" in diagnostic


def test_relation_occurrence_must_instantiate_source_type(tmp_path: Path) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    relation = next(
        item for item in contract["relations"] if item["relation_id"] == "duct_main_width"
    )
    relation["to"] = {
        "kind": "occurrence",
        "id": "equipment_ahu_001",
        "path": "dimensions_mm[1]",
    }
    path = write_json(tmp_path / "wrong-occurrence-type.json", contract)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH, contract_path=path)

    assert result["status"] == "failed"
    diagnostic = "\n".join(result["failures"])
    assert "does not instantiate the source type" in diagnostic
    assert "equipment_ahu_001" in diagnostic
    assert "duct_main_001" in diagnostic


@pytest.mark.parametrize(
    ("operator", "operand"),
    [
        ("add", 0),
        ("subtract", 0),
        ("multiply", 0),
        ("multiply", 1),
        ("divide", 1),
    ],
)
def test_derived_relations_reject_neutral_or_degenerate_transforms(
    tmp_path: Path,
    operator: str,
    operand: int,
) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    relation = next(
        item for item in contract["relations"] if item["relation_id"] == "duct_main_width"
    )
    relation["classification"] = "derived"
    relation["transform"] = {"operator": operator, "operand": operand}
    path = write_json(tmp_path / f"neutral-{operator}.json", contract)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH, contract_path=path)

    assert result["status"] == "failed"
    assert "neutral or degenerate" in "\n".join(result["failures"])


def test_derived_relation_divide_by_zero_has_a_diagnostic(tmp_path: Path) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    relation = next(
        item
        for item in contract["relations"]
        if item["relation_id"] == "pipe_supply_diameter_to_radius"
    )
    relation["transform"]["operand"] = 0
    path = write_json(tmp_path / "divide-zero.json", contract)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH, contract_path=path)

    assert result["status"] == "failed"
    assert result["failures"]
    assert "divides by zero" in "\n".join(result["failures"])


def test_wildcard_python_mapping_cannot_hide_exclusions(tmp_path: Path) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    producer = next(
        item
        for item in contract["producers"]
        if item["adapter"] == "python_mapping"
    )
    producer["excluded_parameters"] = {
        "length_mm": "This must remain mapped by the wildcard."
    }
    path = write_json(tmp_path / "wildcard-exclusion.json", contract)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH, contract_path=path)

    assert result["status"] == "failed"
    assert "wildcard parameter_map cannot define exclusions" in "\n".join(
        result["failures"]
    )


def test_invalid_nonnumeric_binding_does_not_emit_value_mismatch(tmp_path: Path) -> None:
    project = project_payload()
    asset_type(project, "openscad_pipe_clamp_type_b")["parameters"][
        "material_tag"
    ] = "steel"
    project_path = write_json(tmp_path / "project.json", project)
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    producer = next(
        item
        for item in contract["producers"]
        if item["adapter"] == "openscad_assignments"
    )
    canonical_name, producer_name = next(iter(producer["parameter_map"].items()))
    del producer["parameter_map"][canonical_name]
    producer["parameter_map"]["material_tag"] = producer_name
    path = write_json(tmp_path / "nonnumeric-binding.json", contract)

    result = reconcile(project_spec_path=project_path, contract_path=path)

    diagnostic = "\n".join(result["failures"])
    assert "[NONNUMERIC_CANONICAL_PARAMETER]" in diagnostic
    assert "material_tag" in diagnostic
    assert "[VALUE_MISMATCH]" not in diagnostic


def test_mutated_project_parameter_reports_precise_source_drift(tmp_path: Path) -> None:
    payload = project_payload()
    plate = asset_type(payload, "plate_mounting_type_a")
    plate["parameters"]["length_mm"] = 261
    occurrence(payload, "plate_mounting_type_a")["dimensions_mm"][0] = 261
    project_path = write_json(tmp_path / "mutated.project.json", payload)

    result = reconcile(project_spec_path=project_path)

    assert result["status"] == "failed"
    row = failed_row(
        result,
        subject_id="plate_mounting_type_a",
        parameter="length_mm",
    )
    assert row["expected"] == pytest.approx(261)
    assert row["actual"] == pytest.approx(260)
    assert row["producer"]
    assert row["producer_path"]
    assert row["tolerance_mm"] >= 0
    diagnostic = "\n".join(result["failures"])
    assert "plate_mounting_type_a" in diagnostic
    assert "length_mm" in diagnostic
    assert "261" in diagnostic
    assert "260" in diagnostic


def test_derived_relation_applies_transform_and_reports_endpoint_drift(
    tmp_path: Path,
) -> None:
    payload = project_payload()
    supply_type = asset_type(payload, "pipe_supply_001")
    supply_type["parameters"]["pipe_diameter_mm"] = 82
    project_path = write_json(tmp_path / "stale-radius.project.json", payload)

    result = reconcile(project_spec_path=project_path)

    assert result["status"] == "failed"
    row = next(
        row
        for row in result["rows"]
        if row["relation_id"] == "pipe_supply_diameter_to_radius"
    )
    assert row["relation"] == "derived"
    assert row["expected"] == pytest.approx(41)
    assert row["actual"] == pytest.approx(40)
    assert row["status"] == "failed"
    diagnostic = "\n".join(result["failures"])
    assert "pipe_supply_diameter_to_radius" in diagnostic
    assert "41" in diagnostic
    assert "40" in diagnostic


def test_producer_tolerance_is_inclusive_and_rejects_larger_drift(
    tmp_path: Path,
) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    producer = next(
        item
        for item in contract["producers"]
        if item["subject"] == {"kind": "asset_type", "id": "plate_mounting_type_a"}
    )
    producer["tolerance_mm"] = 0.5
    contract_path = write_json(tmp_path / "tolerant-contract.json", contract)

    payload = project_payload()
    plate = asset_type(payload, "plate_mounting_type_a")
    plate["parameters"]["length_mm"] = 260.5
    plate_occurrence = occurrence(payload, "plate_mounting_type_a")
    plate_occurrence["dimensions_mm"][0] = 260.5
    boundary_path = write_json(tmp_path / "boundary.project.json", payload)

    boundary = reconcile(
        project_spec_path=boundary_path,
        contract_path=contract_path,
    )
    assert boundary["status"] == "passed", boundary["failures"]
    boundary_row = next(
        row
        for row in boundary["rows"]
        if row["producer"] == producer["producer_id"]
        and row["canonical_path"].rsplit(".", 1)[-1] == "length_mm"
    )
    assert boundary_row["tolerance_mm"] == pytest.approx(0.5)
    assert boundary_row["status"] == "passed"

    plate["parameters"]["length_mm"] = 260.500001
    plate_occurrence["dimensions_mm"][0] = 260.500001
    outside_path = write_json(tmp_path / "outside.project.json", payload)
    outside = reconcile(
        project_spec_path=outside_path,
        contract_path=contract_path,
    )

    assert outside["status"] == "failed"
    outside_row = failed_row(
        outside,
        subject_id="plate_mounting_type_a",
        parameter="length_mm",
    )
    assert outside_row["tolerance_mm"] == pytest.approx(0.5)
    assert outside_row["expected"] == pytest.approx(260.500001)
    assert outside_row["actual"] == pytest.approx(260)


def test_contract_relative_project_spec_path_is_enforced(tmp_path: Path) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    contract["project_spec"] = "missing.project.json"
    path = write_json(tmp_path / "missing-project-contract.json", contract)

    result = reconcile(contract_path=path)

    assert result["status"] == "failed"
    diagnostic = "\n".join(result["failures"])
    assert "missing.project.json" in diagnostic
    assert "file not found" in diagnostic.lower()


def test_removing_a_whole_producer_reduces_coverage_and_fails(tmp_path: Path) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    removed = contract["producers"].pop(0)
    path = write_json(tmp_path / "missing-producer-contract.json", contract)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH, contract_path=path)

    assert result["status"] == "failed"
    assert result["summary"]["required_producer_count"] > result["summary"]["producer_count"]
    assert (
        result["summary"]["covered_numeric_parameter_count"]
        < result["summary"]["scoped_numeric_parameter_count"]
    )
    diagnostic = "\n".join(result["failures"])
    assert removed["subject"]["id"] in diagnostic
    assert "missing_producer" in diagnostic.lower()


def test_huge_contract_integer_fails_closed(tmp_path: Path) -> None:
    contract = copy.deepcopy(load_contract(DEFAULT_CONTRACT_PATH))
    contract["default_tolerance_mm"] = 10**400
    path = write_json(tmp_path / "huge-integer-contract.json", contract)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH, contract_path=path)

    assert result["status"] == "failed"
    assert "finite range" in "\n".join(result["failures"]).lower()


def test_override_relation_fails_when_it_is_no_longer_an_override(tmp_path: Path) -> None:
    payload = project_payload()
    occurrence(payload, "pipe_return_001")["dimensions_mm"][1] = 3600
    project_path = write_json(tmp_path / "stale-override.project.json", payload)

    result = reconcile(project_spec_path=project_path)

    assert result["status"] == "failed"
    row = next(
        item
        for item in result["rows"]
        if item["relation_id"] == "pipe_return_length_override"
    )
    assert row["status"] == "failed"
    assert "pipe_return_length_override" in "\n".join(result["failures"])


def test_generator_aliases_are_loaded_from_the_contract() -> None:
    contract = load_contract(DEFAULT_CONTRACT_PATH)
    cadquery_bindings = {
        Path(producer["path"]).stem: producer["subject"]["id"]
        for producer in contract["producers"]
        if producer["adapter"] == "python_mapping"
    }
    contract_aliases = {
        producer["subject"]["id"]: producer["parameter_map"]
        for producer in contract["producers"]
        if producer["adapter"] == "openscad_assignments"
    }

    assert cadquery_bindings == cadquery_generate_all.ASSET_BINDINGS
    assert list(cadquery_bindings) == cadquery_generate_all.ASSET_MODULES
    assert contract_aliases == PARAMETER_ALIASES
    assert set(OPENSCAD_ASSETS) == set(contract_aliases)


def test_cadquery_loader_uses_the_exact_reconciled_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    source_dir = repo_root / "cadquery"
    shadow_dir = tmp_path / "shadow"
    source_dir.mkdir(parents=True)
    shadow_dir.mkdir()
    (source_dir / "sample_asset.py").write_text(
        'ORIGIN = "reconciled"\n',
        encoding="utf-8",
    )
    (shadow_dir / "sample_asset.py").write_text(
        'raise RuntimeError("shadow module executed")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cadquery_generate_all, "ROOT", repo_root)
    monkeypatch.syspath_prepend(str(shadow_dir))

    module = cadquery_generate_all.load_asset_module("sample_asset")

    assert module.ORIGIN == "reconciled"
    assert Path(module.__file__).resolve() == (source_dir / "sample_asset.py").resolve()


def test_cadquery_producer_asset_id_drift_is_rejected(
    tmp_path: Path,
    monkeypatch,
) -> None:
    copy_producer_sources(tmp_path)
    source = tmp_path / "cadquery" / "mounting_plate.py"
    text = source.read_text(encoding="utf-8")
    expected_assignment = 'ASSET_ID = "plate_mounting_type_a"'
    assert expected_assignment in text
    source.write_text(
        text.replace(
            expected_assignment,
            'ASSET_ID = "support_pipe_bracket_type_a"',
            1,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(reconciliation, "ROOT", tmp_path)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH)

    assert result["status"] == "failed"
    diagnostic = "\n".join(result["failures"])
    assert "cadquery.mounting_plate" in diagnostic
    assert "ASSET_ID" in diagnostic
    assert "support_pipe_bracket_type_a" in diagnostic
    assert "plate_mounting_type_a" in diagnostic


def test_extra_openscad_numeric_input_increases_scope_and_fails_coverage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    baseline = reconcile()
    copy_producer_sources(tmp_path)
    source = tmp_path / "openscad" / "pipe_clamp.scad"
    source.write_text(
        source.read_text(encoding="utf-8") + "\nunmapped_test_input_mm = 123;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(reconciliation, "ROOT", tmp_path)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH)

    assert result["status"] == "failed"
    assert (
        result["summary"]["producer_input_count"]
        == baseline["summary"]["producer_input_count"] + 1
    )
    diagnostic = "\n".join(result["failures"])
    assert "UNMAPPED_PRODUCER_PARAMETER" in diagnostic
    assert "unmapped_test_input_mm" in diagnostic


def test_openscad_block_comment_cannot_spoof_a_live_value(
    tmp_path: Path,
    monkeypatch,
) -> None:
    copy_producer_sources(tmp_path)
    source = tmp_path / "openscad" / "bracket_plate.scad"
    text = source.read_text(encoding="utf-8")
    text = text.replace("plate_length_mm = 180;", "plate_length_mm = 999;", 1)
    source.write_text(
        text + "\n/*\nplate_length_mm = 180;\n*/\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(reconciliation, "ROOT", tmp_path)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH)

    assert result["status"] == "failed"
    diagnostic = "\n".join(result["failures"])
    assert "plate_length_mm" in diagnostic
    assert "999" in diagnostic


@pytest.mark.parametrize(
    ("extra_source", "expected_diagnostic"),
    [
        ("hidden_geometry_input_mm = 100 + 20;", "finite numeric literals"),
        ("include <hidden_inputs.scad>", "include/use directives"),
        ("$fn = 48; include <hidden_inputs.scad>", "include/use directives"),
        ("pipe_diameter_mm = 50;", "repeats a top-level input"),
    ],
)
def test_openscad_unscanned_or_duplicate_inputs_fail_closed(
    tmp_path: Path,
    monkeypatch,
    extra_source: str,
    expected_diagnostic: str,
) -> None:
    copy_producer_sources(tmp_path)
    source = tmp_path / "openscad" / "pipe_clamp.scad"
    source.write_text(
        source.read_text(encoding="utf-8") + f"\n{extra_source}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(reconciliation, "ROOT", tmp_path)

    result = reconcile(project_spec_path=DEFAULT_PROJECT_SPEC_PATH)

    assert result["status"] == "failed"
    assert expected_diagnostic in "\n".join(result["failures"])


def test_python_mapping_rejects_duplicate_runtime_assignment(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.py"
    source.write_text(
        'DEFAULT_PARAMETERS = {"length_mm": 260}\n'
        'DEFAULT_PARAMETERS = {"length_mm": 999}\n',
        encoding="utf-8",
    )

    with pytest.raises(ReconciliationError, match="one literal assignment"):
        _python_mapping(source, "DEFAULT_PARAMETERS")


@pytest.mark.parametrize(
    "mutation",
    [
        'alias = DEFAULT_PARAMETERS\nalias["hidden_mm"] = 999',
        'DEFAULT_PARAMETERS |= {"length_mm": 999}',
        '(DEFAULT_PARAMETERS := {"length_mm": 999})',
        'globals()["DEFAULT_PARAMETERS"]["hidden_mm"] = 999',
        "def merged(parameters, defaults):\n"
        '    defaults["hidden_mm"] = 999\n'
        "    return defaults",
    ],
)
def test_python_mapping_rejects_alias_and_name_level_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    source = tmp_path / "mutated.py"
    source.write_text(
        "from asset_io import merged\n"
        'DEFAULT_PARAMETERS = {"length_mm": 260}\n'
        "def build(parameters=None):\n"
        "    p = merged(parameters, DEFAULT_PARAMETERS)\n"
        "    return p\n"
        f"{mutation}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ReconciliationError,
        match="selector|merged|dynamic|build parameters",
    ):
        _python_mapping(source, "DEFAULT_PARAMETERS")


def test_python_mapping_requires_trusted_merged_import(tmp_path: Path) -> None:
    source = tmp_path / "untrusted_merge.py"
    source.write_text(
        "from untrusted_helpers import merged\n"
        'DEFAULT_PARAMETERS = {"length_mm": 260}\n'
        "def build(parameters=None):\n"
        "    return merged(parameters, DEFAULT_PARAMETERS)\n",
        encoding="utf-8",
    )

    with pytest.raises(ReconciliationError, match="trusted merged"):
        _python_mapping(source, "DEFAULT_PARAMETERS")


def test_python_mapping_rejects_indirect_module_rebinding(tmp_path: Path) -> None:
    source = tmp_path / "indirect_rebind.py"
    source.write_text(
        "from asset_io import merged\n"
        "import cadquery as cq\n"
        'DEFAULT_PARAMETERS = {"length_mm": 260}\n'
        "def build(parameters=None):\n"
        "    p = merged(parameters, DEFAULT_PARAMETERS)\n"
        "    return p\n"
        "cq.merged = lambda incoming, defaults: defaults\n",
        encoding="utf-8",
    )

    with pytest.raises(ReconciliationError, match="indirect object mutation"):
        _python_mapping(source, "DEFAULT_PARAMETERS")


@pytest.mark.parametrize(
    "first_argument",
    [
        '{"length_mm": 999}',
        "dict(parameters or {}, length_mm=999)",
        "None",
    ],
)
def test_python_mapping_requires_canonical_build_parameters(
    tmp_path: Path,
    first_argument: str,
) -> None:
    source = tmp_path / "override_parameters.py"
    source.write_text(
        "from asset_io import merged\n"
        'DEFAULT_PARAMETERS = {"length_mm": 260}\n'
        "def build(parameters=None):\n"
        f"    p = merged({first_argument}, DEFAULT_PARAMETERS)\n"
        "    return p\n",
        encoding="utf-8",
    )

    with pytest.raises(ReconciliationError, match="canonical merged"):
        _python_mapping(source, "DEFAULT_PARAMETERS")


def test_python_mapping_rejects_build_parameter_rebinding(tmp_path: Path) -> None:
    source = tmp_path / "rebound_parameters.py"
    source.write_text(
        "from asset_io import merged\n"
        'DEFAULT_PARAMETERS = {"length_mm": 260}\n'
        "def build(parameters=None):\n"
        "    p = merged(parameters, DEFAULT_PARAMETERS)\n"
        '    parameters = {"length_mm": 999}\n'
        "    return p\n",
        encoding="utf-8",
    )

    with pytest.raises(ReconciliationError, match="build parameters"):
        _python_mapping(source, "DEFAULT_PARAMETERS")


@pytest.mark.parametrize(
    ("body", "diagnostic"),
    [
        (
            '    p.update({"length_mm": 999})\n'
            '    return float(p["length_mm"])\n',
            "escapes literal key reads",
        ),
        (
            '    p = {**p, "length_mm": 999}\n'
            '    return float(p["length_mm"])\n',
            "escapes literal key reads",
        ),
        ("    return 999.0\n", "numeric inputs are not consumed"),
        (
            '    return float(p["unknown_mm"])\n',
            "unknown input key",
        ),
    ],
)
def test_python_mapping_rejects_unsafe_or_missing_consumption(
    tmp_path: Path,
    body: str,
    diagnostic: str,
) -> None:
    source = tmp_path / "unsafe_consumption.py"
    source.write_text(
        "from asset_io import merged\n"
        'DEFAULT_PARAMETERS = {"length_mm": 260}\n'
        "def build(parameters=None):\n"
        "    p = merged(parameters, DEFAULT_PARAMETERS)\n"
        f"{body}",
        encoding="utf-8",
    )

    with pytest.raises(ReconciliationError, match=diagnostic):
        _python_mapping(source, "DEFAULT_PARAMETERS")


def test_python_mapping_requires_every_numeric_input_to_be_consumed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "missing_consumption.py"
    source.write_text(
        "from asset_io import merged\n"
        'DEFAULT_PARAMETERS = {"length_mm": 260, "width_mm": 160}\n'
        "def build(parameters=None):\n"
        "    p = merged(parameters, DEFAULT_PARAMETERS)\n"
        '    return float(p["length_mm"])\n',
        encoding="utf-8",
    )

    with pytest.raises(ReconciliationError, match="width_mm"):
        _python_mapping(source, "DEFAULT_PARAMETERS")


def test_cadquery_generation_forwards_project_spec_parameters(monkeypatch) -> None:
    project = load_project_spec()
    asset_id = "plate_mounting_type_a"
    expected = dict(project.asset_types_by_id[asset_id].parameters)
    received: list[dict[str, object]] = []
    shape = object()

    fake_module = SimpleNamespace(
        ASSET_ID=asset_id,
        build=lambda parameters: received.append(parameters) or shape,
    )
    monkeypatch.setattr(
        cadquery_generate_all,
        "ASSET_BINDINGS",
        {"fake_plate": asset_id},
    )
    monkeypatch.setattr(cadquery_generate_all, "ASSET_MODULES", ["fake_plate"])
    monkeypatch.setattr(cadquery_generate_all, "load_project_spec", lambda path: project)
    monkeypatch.setattr(
        cadquery_generate_all,
        "load_asset_module",
        lambda name: fake_module,
    )
    monkeypatch.setattr(
        cadquery_generate_all,
        "export_shape",
        lambda actual_shape, actual_id: (
            Path(f"{actual_id}.step"),
            Path(f"{actual_id}.stl"),
        )
        if actual_shape is shape and actual_id == asset_id
        else pytest.fail("CadQuery generator exported the wrong shape or asset ID"),
    )

    cadquery_generate_all.main()

    assert received == [expected]
    assert received[0] is not project.asset_types_by_id[asset_id].parameters


@pytest.mark.parametrize("asset_id", sorted(OPENSCAD_ASSETS))
def test_openscad_command_forwards_every_mapped_project_spec_parameter(
    asset_id: str,
) -> None:
    project = load_project_spec()
    parameters = project.parameters_for_asset_type(
        asset_id,
        expected_group="openscad",
    )
    command = build_openscad_command(
        "openscad",
        asset_id,
        parameters,
        f"{asset_id}.scad",
        f"{asset_id}.stl",
    )

    assert command[:3] == ["openscad", "-o", f"{asset_id}.stl"]
    assert command[-1] == f"{asset_id}.scad"
    definitions = {
        command[index + 1].split("=", 1)[0]: command[index + 1].split("=", 1)[1]
        for index, item in enumerate(command[:-1])
        if item == "-D"
    }
    assert len(definitions) == len(parameters) == len(PARAMETER_ALIASES[asset_id])
    assert set(definitions) == set(PARAMETER_ALIASES[asset_id].values())
    for canonical_name, openscad_name in PARAMETER_ALIASES[asset_id].items():
        assert float(definitions[openscad_name]) == pytest.approx(parameters[canonical_name])


def test_openscad_command_rejects_unmapped_parameters() -> None:
    project = load_project_spec()
    asset_id = "openscad_pipe_clamp_type_b"
    parameters = project.parameters_for_asset_type(
        asset_id,
        expected_group="openscad",
    )
    parameters["unmapped_mm"] = 1

    with pytest.raises(ValueError, match="unmapped ProjectSpec parameter.*unmapped_mm"):
        build_openscad_command(
            "openscad",
            asset_id,
            parameters,
            "pipe_clamp.scad",
            "pipe_clamp.stl",
        )
