"""Regenerate all CadQuery STEP and STL exports."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path, PurePosixPath
from types import ModuleType

from asset_io import export_shape

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from project_spec import load_project_spec  # noqa: E402
from reconcile_parameters import contract_project_spec_path, load_contract  # noqa: E402


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


def load_asset_module(module_name: str) -> ModuleType:
    """Load the exact reconciled CadQuery source instead of a shadowable name."""

    source_path = (ROOT / "cadquery" / f"{module_name}.py").resolve()
    cadquery_root = (ROOT / "cadquery").resolve()
    try:
        source_path.relative_to(cadquery_root)
    except ValueError as exc:
        raise ValueError(f"CadQuery module path escaped the source root: {module_name}") from exc
    spec = importlib.util.spec_from_file_location(
        f"coordproof_cadquery_{module_name}",
        source_path,
    )
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load CadQuery module: {source_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    project = load_project_spec(contract_project_spec_path())
    for module_name in ASSET_MODULES:
        module = load_asset_module(module_name)
        expected_asset_id = ASSET_BINDINGS[module_name]
        if expected_asset_id != module.ASSET_ID:
            raise ValueError(
                f"CadQuery module {module_name} declares ASSET_ID {module.ASSET_ID!r}; "
                f"the reconciliation contract expects {expected_asset_id!r}"
            )
        parameters = project.parameters_for_asset_type(
            expected_asset_id,
            expected_group="cadquery",
        )
        shape = module.build(parameters)
        step_path, stl_path = export_shape(shape, expected_asset_id)
        print(f"{expected_asset_id}: {step_path.name}, {stl_path.name}")


if __name__ == "__main__":
    main()
