"""Regenerate all CadQuery STEP and STL exports."""

from __future__ import annotations

import importlib

from asset_io import export_shape

ASSET_MODULES = [
    "pipe_support",
    "duct_hanger",
    "cable_tray",
    "equipment_base",
    "pump_skid_frame",
    "wall_sleeve",
    "pipe_clamp",
    "rectangular_duct",
    "mounting_plate",
]


def main() -> None:
    for module_name in ASSET_MODULES:
        module = importlib.import_module(module_name)
        shape = module.build()
        step_path, stl_path = export_shape(shape, module.ASSET_ID)
        print(f"{module.ASSET_ID}: {step_path.name}, {stl_path.name}")


if __name__ == "__main__":
    main()
