"""Export generated DXF drawings to PDF through QCAD's command-line tool."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from artifact_normalization import normalize_qcad_pdf, publish_staged_files
from tooling import qcad_pdf_command

ROOT = Path(__file__).resolve().parents[1]

DRAWINGS = [
    "floor_plan",
    "equipment_layout",
    "section_aa",
    "system_riser",
    "pipe_support_detail",
    "wall_penetration_detail",
    "duct_hanger_detail",
]


def _render_pdf(executable: str | Path, dxf_path: Path, output_path: Path) -> None:
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
        f"-outfile={output_path}",
        str(dxf_path),
    ]
    print("$", " ".join(cmd), flush=True)
    subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        env={**os.environ, "TZ": "UTC"},
    )
    normalize_qcad_pdf(output_path)


def _export_pdf(executable: str | Path, dxf_path: Path, pdf_path: Path) -> None:
    """Render and validate beside one target before publishing it."""

    with tempfile.TemporaryDirectory(dir=pdf_path.parent, prefix=f".{pdf_path.stem}.") as temp:
        temporary_output = Path(temp) / pdf_path.name
        _render_pdf(executable, dxf_path, temporary_output)
        publish_staged_files(((temporary_output, pdf_path),))


def main() -> int:
    executable = qcad_pdf_command()
    if executable is None:
        raise SystemExit(
            "QCAD dwg2pdf was not found. Set QCAD_DWG2PDF or add dwg2pdf to PATH."
        )

    out_dir = ROOT / "qcad" / "pdf_exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".coordproof-qcad-") as temp:
        stage_dir = Path(temp)
        publications: list[tuple[Path, Path]] = []
        for name in DRAWINGS:
            dxf_path = ROOT / "qcad" / f"{name}.dxf"
            pdf_path = out_dir / f"{name}.pdf"
            staged_path = stage_dir / pdf_path.name
            _render_pdf(executable, dxf_path, staged_path)
            publications.append((staged_path, pdf_path))
        publish_staged_files(publications)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
