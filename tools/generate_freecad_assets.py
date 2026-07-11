"""Generate FreeCAD-native source, BIM model, assembly STEP, and review IFC."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from artifact_normalization import publish_staged_files
from freecad_artifact_normalization import (
    normalize_fcstd,
    normalize_review_ifc,
    normalize_step_header,
)
from tooling import freecad_command

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MODEL = ROOT / "freecad" / "mechanical_room.FCStd"
BIM_MODEL = ROOT / "freecad" / "mechanical_room_bim.FCStd"
ASSEMBLY_STEP = ROOT / "exports" / "step" / "mechanical_room_assembly.step"
REVIEW_IFC = ROOT / "bim" / "mechanical_room_freecad_review.ifc"
VALIDATION_MACRO = ROOT / "freecad" / "validate_staged_outputs.FCMacro"


@dataclass(frozen=True)
class FreeCADOutputs:
    source_model: Path
    bim_model: Path
    assembly_step: Path
    review_ifc: Path

    def paths(self) -> tuple[Path, Path, Path, Path]:
        return self.source_model, self.bim_model, self.assembly_step, self.review_ifc


CANONICAL_OUTPUTS = FreeCADOutputs(
    source_model=SOURCE_MODEL,
    bim_model=BIM_MODEL,
    assembly_step=ASSEMBLY_STEP,
    review_ifc=REVIEW_IFC,
)


def run_macro(executable: Path, macro: Path, *, env: dict[str, str]) -> None:
    invocation = (
        "import runpy; "
        f"runpy.run_path({str(macro)!r}, run_name='__main__')"
    )
    # FreeCADCmd returns zero for exceptions in positional FCMacro files on
    # some releases. Exceptions executed through -c reliably propagate a
    # nonzero status to subprocess.run(check=True).
    cmd = [str(executable), "-c", invocation]
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def require_output(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"FreeCAD did not publish the required output: {path}")


def macro_environment(outputs: FreeCADOutputs) -> dict[str, str]:
    return {
        **os.environ,
        "COORDPROOF_FREECAD_SOURCE_PATH": str(outputs.source_model),
        "COORDPROOF_FREECAD_BIM_PATH": str(outputs.bim_model),
        "COORDPROOF_FREECAD_ASSEMBLY_STEP_PATH": str(outputs.assembly_step),
        "COORDPROOF_FREECAD_REVIEW_IFC_PATH": str(outputs.review_ifc),
    }


def normalize_and_publish(
    staged: FreeCADOutputs,
    canonical: FreeCADOutputs,
    *,
    executable: Path,
) -> None:
    """Validate all staged outputs before atomically replacing any golden file."""

    for output in staged.paths():
        require_output(output)
    normalize_step_header(staged.assembly_step)
    normalize_fcstd(
        staged.source_model,
        artifact_identity="freecad/mechanical_room.FCStd",
        expected_object_count=61,
        expected_shape_members=61,
    )
    normalize_fcstd(
        staged.bim_model,
        artifact_identity="freecad/mechanical_room_bim.FCStd",
        expected_object_count=74,
        expected_shape_members=66,
        expected_empty_shape_members=(
            "Space.Shape.brp",
            "BuildingPart.Shape.brp",
            "BuildingPart001.Shape.brp",
            "Site.Shape.brp",
            "Project.Shape.brp",
        ),
    )
    normalize_review_ifc(
        staged.review_ifc,
        expected_root_count=72,
        expected_product_count=65,
        expected_duplicate_relationship_count=1,
    )
    run_macro(executable, VALIDATION_MACRO, env=macro_environment(staged))

    pairs = tuple(zip(staged.paths(), canonical.paths(), strict=True))
    for staged_path, canonical_path in pairs:
        require_output(staged_path)
        if staged_path.stat().st_dev != canonical_path.parent.stat().st_dev:
            raise RuntimeError(
                f"staged output is not on the canonical filesystem: {staged_path}"
            )
    publish_staged_files(pairs)


def main() -> int:
    executable = freecad_command()
    if executable is None:
        raise SystemExit(
            "FreeCAD command was not found. Set FREECAD_CMD or add freecadcmd/FreeCADCmd to PATH."
        )
    freecad_dir = ROOT / "freecad"
    with (
        tempfile.TemporaryDirectory(
            dir=SOURCE_MODEL.parent,
            prefix=".coordproof-freecad-",
        ) as freecad_stage,
        tempfile.TemporaryDirectory(
            dir=ASSEMBLY_STEP.parent,
            prefix=".coordproof-freecad-",
        ) as step_stage,
        tempfile.TemporaryDirectory(
            dir=REVIEW_IFC.parent,
            prefix=".coordproof-freecad-",
        ) as ifc_stage,
    ):
        staged = FreeCADOutputs(
            source_model=Path(freecad_stage) / SOURCE_MODEL.name,
            bim_model=Path(freecad_stage) / BIM_MODEL.name,
            assembly_step=Path(step_stage) / ASSEMBLY_STEP.name,
            review_ifc=Path(ifc_stage) / REVIEW_IFC.name,
        )
        env = macro_environment(staged)
        run_macro(
            executable,
            freecad_dir / "build_mechanical_room.FCMacro",
            env=env,
        )
        for output in (staged.source_model, staged.bim_model, staged.assembly_step):
            require_output(output)
        run_macro(
            executable,
            freecad_dir / "export_bim_ifc.FCMacro",
            env=env,
        )
        require_output(staged.review_ifc)
        normalize_and_publish(staged, CANONICAL_OUTPUTS, executable=executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
