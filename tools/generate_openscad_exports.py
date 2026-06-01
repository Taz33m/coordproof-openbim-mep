"""Generate OpenSCAD STL exports."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ASSETS = {
    "openscad_pipe_clamp_type_b": "pipe_clamp.scad",
    "openscad_bracket_plate_type_b": "bracket_plate.scad",
    "openscad_cable_tray_segment_type_b": "cable_tray_segment.scad",
    "openscad_duct_connector_type_b": "duct_connector.scad",
}


def main() -> int:
    executable = shutil.which("openscad")
    if executable is None:
        raise SystemExit("OpenSCAD command was not found.")
    out_dir = ROOT / "exports" / "stl"
    out_dir.mkdir(parents=True, exist_ok=True)
    for asset_id, source in ASSETS.items():
        output = out_dir / f"{asset_id}.stl"
        source_path = ROOT / "openscad" / source
        cmd = [executable, "-o", str(output), str(source_path)]
        print("$", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
