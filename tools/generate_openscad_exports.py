"""Generate OpenSCAD STL exports."""

from __future__ import annotations

import math
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

from artifact_normalization import normalize_ascii_stl, publish_staged_files
from project_spec import load_project_spec
from reconcile_parameters import contract_project_spec_path, load_contract
from tooling import openscad_command

ROOT = Path(__file__).resolve().parents[1]

def contract_openscad_bindings() -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Load OpenSCAD source paths and aliases from the versioned contract."""

    assets: dict[str, str] = {}
    aliases: dict[str, dict[str, str]] = {}
    for producer in load_contract()["producers"]:
        if producer["adapter"] != "openscad_assignments":
            continue
        asset_id = producer["subject"]["id"]
        assets[asset_id] = producer["path"]
        aliases[asset_id] = dict(producer["parameter_map"])
    if not assets:
        raise ValueError("Reconciliation contract declares no OpenSCAD producers")
    return assets, aliases


ASSETS, PARAMETER_ALIASES = contract_openscad_bindings()


def _openscad_number(name: str, value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"OpenSCAD parameter {name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"OpenSCAD parameter {name} must be finite and positive")
    if isinstance(value, int):
        return str(value)
    return format(number, ".17g")


def build_openscad_command(
    executable: str | Path,
    asset_id: str,
    parameters: Mapping[str, object],
    source_path: str | Path,
    output_path: str | Path,
) -> list[str]:
    """Construct a deterministic OpenSCAD command without filesystem side effects."""

    try:
        aliases = PARAMETER_ALIASES[asset_id]
    except KeyError as exc:
        raise ValueError(f"No OpenSCAD parameter map for asset type: {asset_id}") from exc

    missing = sorted(set(aliases) - set(parameters))
    if missing:
        raise ValueError(
            f"{asset_id} is missing mapped ProjectSpec parameter(s): {', '.join(missing)}"
        )
    unmapped = sorted(set(parameters) - set(aliases))
    if unmapped:
        raise ValueError(
            f"{asset_id} has unmapped ProjectSpec parameter(s): {', '.join(unmapped)}"
        )
    if len(set(aliases.values())) != len(aliases):
        raise ValueError(f"{asset_id} maps multiple parameters to one OpenSCAD variable")

    command = [str(executable), "-o", str(output_path)]
    for parameter_name in sorted(aliases):
        value = _openscad_number(parameter_name, parameters[parameter_name])
        command.extend(["-D", f"{aliases[parameter_name]}={value}"])
    command.append(str(source_path))
    return command


def _render_stl(
    executable: str | Path,
    asset_id: str,
    parameters: Mapping[str, object],
    source_path: Path,
    output_path: Path,
) -> None:
    cmd = build_openscad_command(
        executable,
        asset_id,
        parameters,
        source_path,
        output_path,
    )
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)
    normalize_ascii_stl(output_path, solid_name=asset_id)


def _export_stl(
    executable: str | Path,
    asset_id: str,
    parameters: Mapping[str, object],
    source_path: Path,
    output_path: Path,
) -> None:
    """Render and validate beside one target before publishing it."""

    with tempfile.TemporaryDirectory(dir=output_path.parent, prefix=f".{output_path.stem}.") as temp:
        temporary_output = Path(temp) / output_path.name
        _render_stl(executable, asset_id, parameters, source_path, temporary_output)
        publish_staged_files(((temporary_output, output_path),))


def main() -> int:
    executable = openscad_command()
    if executable is None:
        raise SystemExit("OpenSCAD was not found. Set OPENSCAD_CMD or add openscad to PATH.")
    out_dir = ROOT / "exports" / "stl"
    out_dir.mkdir(parents=True, exist_ok=True)
    project = load_project_spec(contract_project_spec_path())
    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".coordproof-openscad-") as temp:
        stage_dir = Path(temp)
        publications: list[tuple[Path, Path]] = []
        for asset_id, source in ASSETS.items():
            output = out_dir / f"{asset_id}.stl"
            staged_output = stage_dir / output.name
            source_path = ROOT / source
            parameters = project.parameters_for_asset_type(
                asset_id,
                expected_group="openscad",
            )
            _render_stl(
                executable,
                asset_id,
                parameters,
                source_path,
                staged_output,
            )
            publications.append((staged_output, output))
        publish_staged_files(publications)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
