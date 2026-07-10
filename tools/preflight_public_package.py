"""Run safety and evidence checks before sharing CoordProof publicly."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import ifcopenshell

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "manifest" / "build_provenance.json"

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
    "constraints-release.txt",
    "spec/mechanical_room.project.json",
    "spec/project.schema.json",
    "spec/reconciliation.contract.json",
    "spec/reconciliation.schema.json",
    "bim/mechanical_room.ifc",
    "bim/mechanical_room_freecad_review.ifc",
    "bim/openbim_semantic_inventory.csv",
    "manifest/asset_manifest.json",
    "manifest/export_index.csv",
    "manifest/build_provenance.json",
    "reports/coordination_report.md",
    "reports/bill_of_materials.csv",
    "reports/clash_clearance_report.csv",
    "reports/parameter_reconciliation.csv",
    "reports/parameter_reconciliation.md",
    "validation/validation_report.md",
    "screenshots/00_coordproof_system_overview.png",
    "screenshots/02_freecad_bim_structure.png",
    "screenshots/04_qcad_floor_plan.png",
    "screenshots/05_ifc_validation_report.png",
    "screenshots/07_qcad_section_and_riser.png",
]

MINIMUM_COUNTS = {
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
    for pattern, expected in MINIMUM_COUNTS.items():
        actual = len(list(ROOT.glob(pattern)))
        if actual < expected:
            failures.append(f"{pattern}: expected at least {expected}, found {actual}")
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
        "Sources Validation\n\nStatus: **PASSED**",
        "Parameter Reconciliation Validation\n\nStatus: **PASSED**",
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_provenance() -> list[str]:
    if not PROVENANCE.exists():
        return ["missing manifest/build_provenance.json"]
    try:
        payload = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid manifest/build_provenance.json: {exc}"]

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        return ["build provenance has no artifacts object"]

    required_coverage = {
        "spec/mechanical_room.project.json",
        "spec/project.schema.json",
        "spec/reconciliation.contract.json",
        "spec/reconciliation.schema.json",
        "manifest/asset_manifest.json",
        "manifest/export_index.csv",
        "manifest/parameter_schema.json",
        "bim/bim_object_map.csv",
        "validation/validation_report.md",
        "reports/parameter_reconciliation.csv",
        "reports/parameter_reconciliation.md",
        *(rel(path) for path in (ROOT / "screenshots").glob("*.png")),
    }
    failures = [
        f"build provenance missing golden evidence: {item}"
        for item in sorted(required_coverage - artifacts.keys())
    ]
    for item, record in artifacts.items():
        candidate = Path(item)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in item:
            failures.append(f"unsafe provenance path: {item}")
            continue
        path = ROOT / candidate
        if not path.is_file():
            failures.append(f"provenance artifact missing: {item}")
            continue
        if not isinstance(record, dict):
            failures.append(f"invalid provenance record: {item}")
            continue
        expected_hash = record.get("sha256")
        expected_bytes = record.get("bytes")
        if expected_hash != file_sha256(path):
            failures.append(f"provenance hash mismatch: {item}")
        if expected_bytes != path.stat().st_size:
            failures.append(f"provenance byte-count mismatch: {item}")
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


def run_project_spec_validation() -> list[str]:
    result = subprocess.run(
        [sys.executable, "tools/project_spec.py", "validate"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode:
        return ["tools/project_spec.py validate failed:\n" + result.stdout]
    return []


def main() -> int:
    failures: list[str] = []
    # Refresh the deterministic validation report before inspecting it or its
    # provenance record. This keeps one preflight invocation authoritative.
    failures.extend(run_project_spec_validation())
    failures.extend(run_validation())
    failures.extend(check_required_files())
    failures.extend(check_expected_counts())
    failures.extend(check_backups())
    failures.extend(check_git_ignored())
    failures.extend(check_validation_report())
    failures.extend(check_provenance())
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
    print("- ProjectSpec schema and semantics passed")
    print("- validation report passed")
    print("- required artifacts present")
    print("- expected export counts present")
    print("- provenance hashes cover and match golden evidence")
    print("- primary and review IFCs are IFC4 with zero proxy fallback")
    print("- no secret-like strings or absolute local paths found in text files")
    print("- no transient backup/log/env files found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
