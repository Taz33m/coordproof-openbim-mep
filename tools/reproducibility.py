"""Shared validation for deterministic build timestamps."""

from __future__ import annotations

import os
from datetime import UTC, datetime


def source_date_epoch(value: int | str | None = None) -> int:
    """Return a supported non-negative epoch, defaulting reproducible builds to zero."""

    raw = os.environ.get("SOURCE_DATE_EPOCH", "0") if value is None else value
    if isinstance(raw, str):
        if not raw or not raw.isascii() or not raw.isdigit():
            raise ValueError("SOURCE_DATE_EPOCH must be a supported non-negative integer")
        epoch = int(raw)
    elif type(raw) is int:
        epoch = raw
    else:
        raise ValueError("SOURCE_DATE_EPOCH must be a supported non-negative integer")
    try:
        if epoch < 0:
            raise ValueError
        datetime.fromtimestamp(epoch, tz=UTC)
    except (OverflowError, OSError, TypeError, ValueError) as exc:
        raise ValueError("SOURCE_DATE_EPOCH must be a supported non-negative integer") from exc
    return epoch


def source_timestamp(value: int | str | None = None) -> str:
    return datetime.fromtimestamp(source_date_epoch(value), tz=UTC).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
