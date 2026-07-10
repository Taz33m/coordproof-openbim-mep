"""Report whether the current machine can run CoordProof build profiles."""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import platform
import sys
from dataclasses import dataclass

from tooling import freecad_command, openscad_command, qcad_pdf_command


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


PYTHON_PACKAGES = {
    "cadquery": "cadquery",
    "ifcopenshell": "ifcopenshell",
    "ezdxf": "ezdxf",
    "reportlab": "reportlab",
    "PIL": "Pillow",
    "jsonschema": "jsonschema",
}


def package_check(import_name: str, distribution_name: str) -> Check:
    available = importlib.util.find_spec(import_name) is not None
    if not available:
        return Check(distribution_name, False, "not installed")
    try:
        version = importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        version = "installed; version unknown"
    return Check(distribution_name, True, version)


def executable_check(name: str, path, *, required: bool) -> Check:
    return Check(name, path is not None, str(path) if path else "not found", required=required)


def collect_checks(profile: str) -> list[Check]:
    checks = [
        Check(
            "Python",
            sys.version_info >= (3, 11),
            f"{platform.python_version()} ({platform.machine()})",
        )
    ]
    checks.extend(package_check(*item) for item in PYTHON_PACKAGES.items())

    desktop_required = profile == "full"
    checks.extend(
        [
            executable_check("FreeCAD", freecad_command(), required=desktop_required),
            executable_check("OpenSCAD", openscad_command(), required=desktop_required),
            executable_check("QCAD dwg2pdf", qcad_pdf_command(), required=desktop_required),
            Check(
                "OpenCAD pilot",
                importlib.util.find_spec("opencad") is not None,
                "installed" if importlib.util.find_spec("opencad") else "optional; run make install-opencad",
                required=False,
            ),
        ]
    )
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("core", "full"), default="core")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = collect_checks(args.profile)
    print(f"CoordProof doctor ({args.profile} profile)")
    for check in checks:
        status = "PASS" if check.ok else ("FAIL" if check.required else "INFO")
        print(f"[{status}] {check.name}: {check.detail}")

    failures = [check for check in checks if check.required and not check.ok]
    if failures:
        print(f"\n{len(failures)} required check(s) failed.")
        return 1
    print("\nEnvironment is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
