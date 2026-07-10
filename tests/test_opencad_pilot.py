from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from integrations.opencad.pilot import (
    GeometryMetrics,
    catalog_parameters,
    compare_metrics,
    run_pilot,
    validate_parameters,
    verify_real_step,
)


def test_pilot_parameter_contract_uses_catalog() -> None:
    values = validate_parameters(catalog_parameters())
    assert values["length_mm"] == 260.0
    assert values["slot_length_mm"] == 34.0


def test_metric_comparison_detects_geometry_drift() -> None:
    reference = GeometryMetrics(260.0, 160.0, 12.0, 488185.0)
    drifted = GeometryMetrics(261.0, 160.0, 12.0, 488185.0)
    assert not compare_metrics(reference, drifted)["passed"]


def test_metric_comparison_detects_translation_and_topology_drift() -> None:
    reference = GeometryMetrics(260.0, 160.0, 12.0, 488185.0, face_count=20)
    translated = GeometryMetrics(
        260.0,
        160.0,
        12.0,
        488185.0,
        min_x_mm=10.0,
        max_x_mm=270.0,
        center_x_mm=140.0,
        face_count=20,
    )
    changed_topology = GeometryMetrics(260.0, 160.0, 12.0, 488185.0, face_count=21)

    assert not compare_metrics(reference, translated)["passed"]
    comparison = compare_metrics(
        reference,
        changed_topology,
        symmetric_difference_mm3=1.0,
    )
    assert not comparison["passed"]
    assert not comparison["topology_match"]


def test_real_step_envelope_rejects_truncated_payload(tmp_path: Path) -> None:
    path = tmp_path / "truncated.step"
    path.write_bytes(b"ISO-10303-21;\nHEADER;\n")

    with pytest.raises(RuntimeError, match="real STEP"):
        verify_real_step(path)


@pytest.mark.opencad
@pytest.mark.skipif(importlib.util.find_spec("opencad") is None, reason="OpenCAD is optional")
def test_real_opencad_pilot(tmp_path: Path) -> None:
    report = run_pilot(tmp_path)
    assert report["status"] == "passed"
    assert report["opencad"]["feature_node_count"] == 22
    assert (tmp_path / "plate_mounting_type_a.step").read_bytes().startswith(b"ISO-10303-21;")
