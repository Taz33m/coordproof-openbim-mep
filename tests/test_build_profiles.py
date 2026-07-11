from __future__ import annotations

from pathlib import Path

import pytest

from tools.build_all import steps_for
from tools.generate_drawings import PORTABLE_PDF_DIR, parse_args

ROOT = Path(__file__).resolve().parents[1]


def test_portable_drawings_default_to_disposable_build_output() -> None:
    args = parse_args([])

    assert args.pdf_output_dir == PORTABLE_PDF_DIR
    assert not args.skip_pdf


def test_full_build_leaves_canonical_pdfs_to_qcad() -> None:
    drawing_step = next(
        step
        for step in steps_for("full")
        if any(item.endswith("generate_drawings.py") for item in step)
    )

    assert "--skip-pdf" in drawing_step


def test_unknown_build_profile_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unknown build profile"):
        steps_for("typo")


def test_portable_ci_byte_gate_excludes_platform_native_serializers() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    regeneration = workflow.split("- name: Regenerate portable semantic evidence", 1)[1].split(
        "- name: Reject semantic evidence drift",
        1,
    )[0]
    drift_gate = workflow.split("- name: Reject semantic evidence drift", 1)[1].split(
        "- name: Validate committed evidence package",
        1,
    )[0]

    assert "python tools/generate_drawings.py --skip-pdf" in regeneration
    assert "python cadquery/generate_all.py" not in regeneration
    assert "python tools/generate_review_images.py" not in regeneration
    assert "\n          qcad\n" in drift_gate
    assert "\n          exports/step\n" not in drift_gate
    assert "\n          exports/stl\n" not in drift_gate
    assert "\n          screenshots\n" not in drift_gate
