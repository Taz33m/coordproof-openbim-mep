from __future__ import annotations

import pytest
from mounting_plate import build


def test_mounting_plate_matches_catalog_envelope() -> None:
    solid = build().val()
    bbox = solid.BoundingBox()
    assert bbox.xlen == pytest.approx(260.0)
    assert bbox.ylen == pytest.approx(160.0)
    assert bbox.zlen == pytest.approx(12.0)
    assert solid.Volume() == pytest.approx(488185.4870393785, rel=1e-10)


def test_mounting_plate_rejects_impossible_slot() -> None:
    with pytest.raises(ValueError, match="slot_length_mm"):
        build({"slot_length_mm": 5, "bolt_diameter_mm": 14})
