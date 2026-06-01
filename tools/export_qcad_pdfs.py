"""Export generated DXF drawings to PDF through QCAD's command-line tool."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QCAD_DWG2PDF = Path("/Applications/QCAD.app/Contents/Resources/dwg2pdf")

DRAWINGS = [
    "floor_plan",
    "equipment_layout",
    "section_aa",
    "system_riser",
    "pipe_support_detail",
    "wall_penetration_detail",
    "duct_hanger_detail",
]


def main() -> int:
    if not QCAD_DWG2PDF.exists():
        fallback = shutil.which("dwg2pdf")
        if fallback:
            executable = Path(fallback)
        else:
            raise SystemExit("QCAD dwg2pdf command was not found.")
    else:
        executable = QCAD_DWG2PDF

    out_dir = ROOT / "qcad" / "pdf_exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in DRAWINGS:
        dxf_path = ROOT / "qcad" / f"{name}.dxf"
        pdf_path = out_dir / f"{name}.pdf"
        cmd = [
            str(executable),
            "-f",
            "-a",
            "-l",
            "-paper=A3",
            "-unit=mm",
            "-monochrome",
            "-min-lineweight=0.18",
            "-max-lineweight=0.50",
            "-margin=10",
            f"-outfile={pdf_path}",
            str(dxf_path),
        ]
        print("$", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
