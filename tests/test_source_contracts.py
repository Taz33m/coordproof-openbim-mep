from __future__ import annotations

import pytest
from asset_catalog import CADQUERY_ASSETS
from cable_tray import _frange
from validate_sources import validate


def test_source_contracts_are_consistent() -> None:
    result = validate()
    assert result["status"] == "passed", result["failures"]


def test_all_cadquery_dimensions_are_positive() -> None:
    for asset in CADQUERY_ASSETS:
        dimensions = {
            name: value for name, value in asset.parameters.items() if name.endswith("_mm")
        }
        assert dimensions
        assert all(isinstance(value, (int, float)) and value > 0 for value in dimensions.values())


@pytest.mark.parametrize("step", [0.0, -1.0, float("nan"), float("inf")])
def test_frange_rejects_non_positive_or_non_finite_step(step: float) -> None:
    with pytest.raises(ValueError, match="finite positive"):
        _frange(0.0, 10.0, step)


def test_frange_returns_expected_values() -> None:
    assert _frange(0.0, 1.0, 0.25) == [0.0, 0.25, 0.5, 0.75, 1.0]
