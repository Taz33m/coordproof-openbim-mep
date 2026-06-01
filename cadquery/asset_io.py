"""Shared CadQuery export helpers."""

from __future__ import annotations

from pathlib import Path

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]


def export_shape(shape: cq.Workplane, asset_id: str) -> tuple[Path, Path]:
    step_path = ROOT / "exports" / "step" / f"{asset_id}.step"
    stl_path = ROOT / "exports" / "stl" / f"{asset_id}.stl"
    step_path.parent.mkdir(parents=True, exist_ok=True)
    stl_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(shape, str(step_path))
    cq.exporters.export(shape, str(stl_path), tolerance=0.25, angularTolerance=0.2)
    return step_path, stl_path


def merged(parameters: dict[str, object] | None, defaults: dict[str, object]) -> dict[str, object]:
    values = dict(defaults)
    if parameters:
        values.update(parameters)
    return values
