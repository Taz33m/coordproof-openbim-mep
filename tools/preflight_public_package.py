"""Run safety and evidence checks before sharing CoordProof publicly."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import ifcopenshell

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = [
    re.compile(r"OPENAI_API_KEY\s*="),
    re.compile(r"sk-proj-[A-Za-z0-9_-]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
]

ABSOLUTE_PATH_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
]

TEXT_SUFFIXES = {
    ".csv",
    ".css",
    ".FCMacro",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".scad",
    ".sh",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}

REQUIRED_FILES = [
    "README.md",
    "Makefile",
    "bim/mechanical_room.ifc",
    "bim/mechanical_room_freecad_review.ifc",
    "bim/openbim_semantic_inventory.csv",
    "manifest/asset_manifest.json",
    "manifest/export_index.csv",
    "reports/coordination_report.md",
    "reports/bill_of_materials.csv",
    "reports/clash_clearance_report.csv",
    "validation/validation_report.md",
    "screenshots/00_coordproof_system_overview.png",
    "screenshots/02_freecad_bim_structure.png",
    "screenshots/04_qcad_floor_plan.png",
    "screenshots/05_ifc_validation_report.png",
    "screenshots/07_qcad_section_and_riser.png",
]

EXPECTED_COUNTS = {
    "qcad/*.dxf": 7,
    "qcad/pdf_exports/*.pdf": 7,
    "exports/step/*.step": 10,
    "exports/stl/*.stl": 13,
}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def iter_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.name in {"Makefile", ".gitignore"} or path.suffix in TEXT_SUFFIXES:
            files.append(path)
    return files


def scan_patterns(patterns: list[re.Pattern[str]]) -> list[str]:
    hits: list[str] = []
    for path in iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in patterns):
                hits.append(f"{rel(path)}:{line_no}")
    return hits


def check_required_files() -> list[str]:
    failures: list[str] = []
    for item in REQUIRED_FILES:
        path = ROOT / item
        if not path.exists():
            failures.append(f"missing required file: {item}")
        elif path.is_file() and path.stat().st_size == 0:
            failures.append(f"zero-byte required file: {item}")
    return failures


def check_expected_counts() -> list[str]:
    failures: list[str] = []
    for pattern, expected in EXPECTED_COUNTS.items():
        actual = len(list(ROOT.glob(pattern)))
        if actual != expected:
            failures.append(f"{pattern}: expected {expected}, found {actual}")
    return failures


def check_backups() -> list[str]:
    patterns = ["*.FCBak", "*.FCStd1", "*.bak", "*.tmp", "*.log"]
    hits = sorted({rel(path) for pattern in patterns for path in ROOT.rglob(pattern)})
    return [f"transient file present: {path}" for path in hits]


def check_validation_report() -> list[str]:
    report = ROOT / "validation" / "validation_report.md"
    if not report.exists():
        return ["missing validation/validation_report.md"]
    text = report.read_text(encoding="utf-8")
    required = [
        "Overall Status: **PASSED**",
        "IFC Validation\n\nStatus: **PASSED**",
        "Manifest Validation\n\nStatus: **PASSED**",
        "Exports Validation\n\nStatus: **PASSED**",
        "| `proxy_count` | 0 |",
    ]
    return [f"validation report missing marker: {marker}" for marker in required if marker not in text]


def check_ifc(path: Path, min_products: int) -> list[str]:
    failures: list[str] = []
    if not path.exists():
        return [f"missing IFC: {rel(path)}"]
    model = ifcopenshell.open(str(path))
    products = [
        product for product in model.by_type("IfcProduct") if not product.is_a("IfcDistributionPort")
    ]
    proxies = len(model.by_type("IfcBuildingElementProxy"))
    systems = len(model.by_type("IfcDistributionSystem"))
    ports = len(model.by_type("IfcDistributionPort"))
    if model.schema != "IFC4":
        failures.append(f"{rel(path)} schema is {model.schema}, expected IFC4")
    if len(products) < min_products:
        failures.append(f"{rel(path)} has {len(products)} products, expected at least {min_products}")
    if proxies:
        failures.append(f"{rel(path)} has {proxies} IfcBuildingElementProxy objects")
    if path.name == "mechanical_room.ifc":
        if systems < 5:
            failures.append(f"{rel(path)} has {systems} systems, expected at least 5")
        if ports < 50:
            failures.append(f"{rel(path)} has {ports} ports, expected at least 50")
    return failures


def check_git_ignored() -> list[str]:
    candidates = [ROOT / ".env", ROOT / ".env.local"]
    failures = [f"environment file present: {rel(path)}" for path in candidates if path.exists()]
    return failures


def run_validation() -> list[str]:
    result = subprocess.run(
        [sys.executable, "validation/run_all.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode:
        return ["validation/run_all.py failed:\n" + result.stdout]
    return []


def main() -> int:
    failures: list[str] = []
    failures.extend(check_required_files())
    failures.extend(check_expected_counts())
    failures.extend(check_backups())
    failures.extend(check_git_ignored())
    failures.extend(check_validation_report())
    failures.extend(run_validation())
    failures.extend(check_ifc(ROOT / "bim" / "mechanical_room.ifc", min_products=43))
    failures.extend(check_ifc(ROOT / "bim" / "mechanical_room_freecad_review.ifc", min_products=40))
    failures.extend(f"secret-like pattern found: {hit}" for hit in scan_patterns(SECRET_PATTERNS))
    failures.extend(f"absolute local path found: {hit}" for hit in scan_patterns(ABSOLUTE_PATH_PATTERNS))

    if failures:
        print("Preflight FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Preflight PASSED")
    print("- validation report passed")
    print("- required artifacts present")
    print("- expected export counts present")
    print("- primary and review IFCs are IFC4 with zero proxy fallback")
    print("- no secret-like strings or absolute local paths found in text files")
    print("- no transient backup/log/env files found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
