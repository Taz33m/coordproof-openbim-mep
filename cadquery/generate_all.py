"""Regenerate all CadQuery STEP and STL exports."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path, PurePosixPath

from asset_io import export_shape

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from project_spec import ProjectSpec, load_project_spec  # noqa: E402
from reconcile_parameters import load_contract  # noqa: E402


def contract_asset_bindings() -> dict[str, str]:
    """Return CadQuery module-to-ProjectSpec bindings from the contract."""

    bindings = {
        Path(producer["path"]).stem: producer["subject"]["id"]
        for producer in load_contract()["producers"]
        if producer["adapter"] == "python_mapping"
        and PurePosixPath(producer["path"]).parent == PurePosixPath("cadquery")
    }
    if not bindings:
        raise ValueError("Reconciliation contract declares no CadQuery producers")
    return bindings


ASSET_BINDINGS = contract_asset_bindings()
ASSET_MODULES = list(ASSET_BINDINGS)


def parameters_for_asset(project: ProjectSpec, asset_id: str) -> dict[str, object]:
    """Return an isolated ProjectSpec parameter mapping for a CadQuery type."""

    try:
        asset_type = project.asset_types_by_id[asset_id]
    except KeyError as exc:
        raise ValueError(f"Unknown ProjectSpec asset type: {asset_id}") from exc
    if asset_type.group != "cadquery":
        raise ValueError(f"ProjectSpec asset type {asset_id} is not a CadQuery asset")
    return dict(asset_type.parameters)


def main() -> None:
    project = load_project_spec()
    for module_name in ASSET_MODULES:
        module = importlib.import_module(module_name)
        expected_asset_id = ASSET_BINDINGS[module_name]
        if expected_asset_id != module.ASSET_ID:
            raise ValueError(
                f"CadQuery module {module_name} declares ASSET_ID {module.ASSET_ID!r}; "
                f"the reconciliation contract expects {expected_asset_id!r}"
            )
        parameters = parameters_for_asset(project, expected_asset_id)
        shape = module.build(parameters)
        step_path, stl_path = export_shape(shape, expected_asset_id)
        print(f"{expected_asset_id}: {step_path.name}, {stl_path.name}")


if __name__ == "__main__":
    main()
