from __future__ import annotations

import argparse

import pytest

from tools import build_all
from tools.reproducibility import source_date_epoch, source_timestamp


def test_source_date_epoch_defaults_to_epoch_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)

    assert source_date_epoch() == 0
    assert source_timestamp() == "1970-01-01T00:00:00"


@pytest.mark.parametrize(
    "value",
    ("-1", "not-an-integer", " 1", "+1", "1_0", "١", True, 1.2),
)
def test_source_date_epoch_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        source_date_epoch(value)  # type: ignore[arg-type]


def test_build_rejects_invalid_epoch_before_running_any_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "-1")
    monkeypatch.setattr(
        build_all,
        "parse_args",
        lambda: argparse.Namespace(profile="core"),
    )
    monkeypatch.setattr(
        build_all.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(command),
    )

    with pytest.raises(ValueError, match="non-negative integer"):
        build_all.main()

    assert calls == []
