"""Public package metadata for CoordProof."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _distribution_version() -> str:
    try:
        return version("coordproof-openbim-mep")
    except PackageNotFoundError:
        version_file = Path(__file__).resolve().parents[2] / "VERSION"
        if version_file.is_file():
            return version_file.read_text(encoding="utf-8").strip()
        return "0+unknown"


__version__ = _distribution_version()

__all__ = ["__version__"]
