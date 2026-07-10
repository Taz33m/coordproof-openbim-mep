"""Run the full code-generated pipeline."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CORE_STEPS = [
    ["tools/project_spec.py", "validate"],
    ["tools/build_manifest.py"],
    ["tools/generate_drawings.py"],
    ["cadquery/generate_all.py"],
    ["tools/generate_ifc.py"],
    ["tools/generate_coordination_reports.py"],
    ["validation/run_all.py"],
    ["tools/generate_review_images.py"],
    ["tools/build_provenance.py"],
]

FULL_ONLY_STEPS = [
    ["tools/export_qcad_pdfs.py"],
    ["tools/generate_openscad_exports.py"],
    ["tools/generate_freecad_assets.py"],
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("core", "full"),
        default="full",
        help="core uses portable Python generators; full also runs desktop CAD exporters",
    )
    return parser.parse_args()


def steps_for(profile: str) -> list[list[str]]:
    if profile == "core":
        return CORE_STEPS

    # Desktop exporters run after their source generators and before provenance
    # and validation. Keep the order explicit so failures cannot be mistaken for
    # a successfully refreshed evidence package.
    return [
        ["tools/project_spec.py", "validate"],
        ["tools/build_manifest.py"],
        ["tools/generate_drawings.py", "--skip-pdf"],
        ["tools/export_qcad_pdfs.py"],
        ["tools/generate_openscad_exports.py"],
        ["cadquery/generate_all.py"],
        ["tools/generate_freecad_assets.py"],
        ["tools/generate_ifc.py"],
        ["tools/generate_coordination_reports.py"],
        ["validation/run_all.py"],
        ["tools/generate_review_images.py"],
        ["tools/build_provenance.py"],
    ]


def main() -> int:
    args = parse_args()
    for step in steps_for(args.profile):
        cmd = [sys.executable, *step]
        print("$", " ".join(cmd), flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
