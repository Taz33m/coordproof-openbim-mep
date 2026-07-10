"""Cross-platform discovery helpers for optional desktop CAD tools."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_executable(
    env_var: str,
    command_names: tuple[str, ...],
    known_paths: tuple[str, ...] = (),
) -> Path | None:
    """Find an executable from an override, PATH, or known platform paths."""

    override = os.environ.get(env_var)
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() and os.access(path, os.X_OK) else None

    for command in command_names:
        resolved = shutil.which(command)
        if resolved:
            return Path(resolved)

    for candidate in known_paths:
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def freecad_command() -> Path | None:
    return find_executable(
        "FREECAD_CMD",
        ("freecadcmd", "FreeCADCmd"),
        ("/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd",),
    )


def qcad_pdf_command() -> Path | None:
    return find_executable(
        "QCAD_DWG2PDF",
        ("dwg2pdf",),
        ("/Applications/QCAD.app/Contents/Resources/dwg2pdf",),
    )


def openscad_command() -> Path | None:
    return find_executable("OPENSCAD_CMD", ("openscad",))
