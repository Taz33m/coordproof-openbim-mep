"""Run the full code-generated pipeline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    ["tools/build_manifest.py"],
    ["tools/generate_drawings.py"],
    ["tools/export_qcad_pdfs.py"],
    ["tools/generate_openscad_exports.py"],
    ["cadquery/generate_all.py"],
    ["tools/generate_freecad_assets.py"],
    ["tools/generate_ifc.py"],
    ["tools/generate_coordination_reports.py"],
    ["validation/run_all.py"],
    ["tools/generate_review_images.py"],
]


def main() -> int:
    for step in STEPS:
        cmd = [sys.executable, *step]
        print("$", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
