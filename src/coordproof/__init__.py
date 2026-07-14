"""Public package metadata for CoordProof."""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PACKAGE_NAME = "coordproof-openbim-mep"


def _source_tree_version(package_file: Path | None = None) -> str | None:
    """Find a marked CoordProof source root without assuming a fixed layout."""

    start = (package_file or Path(__file__)).resolve()
    for directory in start.parents:
        pyproject = directory / "pyproject.toml"
        version_file = directory / "VERSION"
        if not pyproject.is_file() or not version_file.is_file():
            continue
        try:
            metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            value = version_file.read_text(encoding="utf-8").strip()
        except (OSError, tomllib.TOMLDecodeError):
            continue
        project = metadata.get("project")
        if not isinstance(project, dict) or project.get("name") != PACKAGE_NAME:
            continue
        return value or None
    return None


def _distribution_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return _source_tree_version() or "0+unknown"


__version__ = _distribution_version()

__all__ = ["__version__"]
