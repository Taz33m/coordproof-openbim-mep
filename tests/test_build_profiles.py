from __future__ import annotations

import pytest

from tools.build_all import steps_for
from tools.generate_drawings import PORTABLE_PDF_DIR, parse_args


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
