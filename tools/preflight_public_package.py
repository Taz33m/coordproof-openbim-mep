"""Run safety and evidence checks before sharing CoordProof publicly."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
import subprocess
import sys
import zipfile
from contextlib import suppress
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
from build_provenance import embedded_producer_versions
from desktop_artifact_contract import canonical_desktop_artifact_failures
from provenance_contract import (
    provenance_metadata_failures,
    required_artifact_paths,
    strict_json_loads,
    validated_repository_file,
)

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "manifest" / "build_provenance.json"

SECRET_PATTERNS = [
    re.compile(r"OPENAI_API_KEY\s*="),
    re.compile(r"sk-proj-[A-Za-z0-9_-]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-(?:svcacct|admin)-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
]

_SLASH = "/"
_BACKSLASH = chr(92)
_PATH_SEPARATOR_CLASS = "[" + re.escape(_BACKSLASH + _SLASH) + "]+"
ABSOLUTE_PATH_PATTERNS = [
    re.compile(_SLASH + "Users" + r"/[^/\r\n]+/"),
    re.compile(_SLASH + "home" + r"/[^/\r\n]+/"),
    re.compile(_SLASH + "root" + _SLASH),
    re.compile(_SLASH + "private" + r"/(?:tmp|var)/"),
    re.compile(_SLASH + r"(?:tmp|var/folders)/"),
    re.compile(
        r"(?i)\b[A-Z]:"
        + _PATH_SEPARATOR_CLASS
        + r"[A-Za-z0-9_$.-][A-Za-z0-9 _.$-]*"
        + _PATH_SEPARATOR_CLASS
    ),
    re.compile(
        re.escape(_BACKSLASH * 2)
        + r"[A-Za-z0-9_$-][A-Za-z0-9._$ -]*"
        + _PATH_SEPARATOR_CLASS
        + r"[A-Za-z0-9_$-][A-Za-z0-9._$ -]*"
        + _PATH_SEPARATOR_CLASS
    ),
]

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".coverage",
    "build",
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
    "screenshots/01_freecad_mechanical_room_overview.png",
    "screenshots/02_freecad_bim_structure.png",
    "screenshots/03_cadquery_asset_grid.png",
    "screenshots/04_qcad_floor_plan.png",
    "screenshots/05_ifc_validation_report.png",
    "screenshots/06_export_formats_overview.png",
    "screenshots/07_qcad_section_and_riser.png",
]

MINIMUM_COUNTS = {
    "qcad/*.dxf": 7,
    "qcad/pdf_exports/*.pdf": 7,
    "exports/step/*.step": 10,
    "exports/stl/*.stl": 13,
}
MAX_SCANNED_FILE_BYTES = 50 * 1024 * 1024
MAX_FCSTD_MEMBER_BYTES = 10 * 1024 * 1024
MAX_FCSTD_TOTAL_BYTES = 20 * 1024 * 1024
MAX_FCSTD_MEMBERS = 1000


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def iter_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        files.append(path)
    return files


def scan_patterns(
    patterns: list[re.Pattern[str]],
    *,
    scan_binary: bool = False,
) -> list[str]:
    hits: set[str] = set()

    def decoded_views(payload: bytes) -> list[str]:
        if scan_binary:
            views = [payload.decode("utf-8", errors="surrogateescape")]
        else:
            views = []
            with suppress(UnicodeError):
                views.append(payload.decode("utf-8", errors="strict"))
        if b"\x00" in payload or payload.startswith((b"\xff\xfe", b"\xfe\xff")):
            for encoding in ("utf-16", "utf-16-le", "utf-16-be"):
                try:
                    view = payload.decode(encoding, errors="strict")
                except UnicodeError:
                    continue
                if view not in views:
                    views.append(view)
        return views

    for path in iter_text_files():
        if path.stat().st_size > MAX_SCANNED_FILE_BYTES:
            continue
        raw = path.read_bytes()
        payloads = [(rel(path), raw)]
        if path.suffix.casefold() == ".pdf" and not scan_binary:
            payloads = []
            xmp = re.search(rb"<x:xmpmeta\b.*?</x:xmpmeta>", raw, flags=re.DOTALL)
            first_stream = raw.find(b"stream")
            if first_stream > 0:
                payloads.append((f"{rel(path)}!Info", raw[:first_stream]))
            if xmp is not None:
                payloads.append((f"{rel(path)}!XMP", xmp.group(0)))
        if path.suffix.casefold() == ".fcstd" and zipfile.is_zipfile(path):
            if not scan_binary:
                payloads = []
            try:
                with zipfile.ZipFile(path) as archive:
                    infos = archive.infolist()
                    if (
                        len(infos) > MAX_FCSTD_MEMBERS
                        or any(info.flag_bits & 1 for info in infos)
                        or any(stat.S_ISLNK(info.external_attr >> 16) for info in infos)
                        or any(info.file_size > MAX_FCSTD_MEMBER_BYTES for info in infos)
                        or sum(info.file_size for info in infos) > MAX_FCSTD_TOTAL_BYTES
                        or any(
                            info.file_size / max(info.compress_size, 1) > 1000
                            for info in infos
                        )
                        or any(
                            not info.filename
                            or "\\" in info.filename
                            or any(ord(character) < 32 for character in info.filename)
                            or any(
                                part in {"", ".", ".."}
                                or re.fullmatch(r"[A-Za-z0-9._-]+", part) is None
                                for part in info.filename.split("/")
                            )
                            for info in infos
                        )
                    ):
                        continue
                    payloads.extend(
                        (f"{rel(path)}!{info.filename}", archive.read(info))
                        for info in infos
                    )
            except (OSError, RuntimeError, zipfile.BadZipFile):
                continue
        for label, payload in payloads:
            for text in decoded_views(payload):
                for line_no, line in enumerate(text.splitlines(), start=1):
                    if any(pattern.search(line) for pattern in patterns):
                        hits.add(f"{label}:{line_no}")
    return sorted(hits)


def check_scan_safety() -> list[str]:
    failures: list[str] = []
    for path in iter_text_files():
        if path.stat().st_size > MAX_SCANNED_FILE_BYTES:
            failures.append(f"public file is too large to scan safely: {rel(path)}")
            continue
        if path.suffix.casefold() != ".fcstd":
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                unsafe = (
                    len(infos) > MAX_FCSTD_MEMBERS
                    or len(names) != len(set(names))
                    or any(info.flag_bits & 1 for info in infos)
                    or any(stat.S_ISLNK(info.external_attr >> 16) for info in infos)
                    or any(info.file_size > MAX_FCSTD_MEMBER_BYTES for info in infos)
                    or sum(info.file_size for info in infos) > MAX_FCSTD_TOTAL_BYTES
                    or any(
                        info.file_size / max(info.compress_size, 1) > 1000
                        for info in infos
                    )
                    or any(
                        not info.filename
                        or "\\" in info.filename
                        or any(ord(character) < 32 for character in info.filename)
                        or any(
                            part in {"", ".", ".."}
                            or re.fullmatch(r"[A-Za-z0-9._-]+", part) is None
                            for part in info.filename.split("/")
                        )
                        for info in infos
                    )
                )
                bad_member = None if unsafe else archive.testzip()
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            failures.append(f"FCStd cannot be scanned safely: {rel(path)}: {exc}")
            continue
        if bad_member is not None:
            failures.append(f"FCStd CRC failure while scanning: {rel(path)}!{bad_member}")
        if len(infos) > MAX_FCSTD_MEMBERS:
            failures.append(f"FCStd has too many members while scanning: {rel(path)}")
        if len(names) != len(set(names)):
            failures.append(f"FCStd has duplicate members while scanning: {rel(path)}")
        for info in infos:
            if (
                not info.filename
                or "\\" in info.filename
                or any(ord(character) < 32 for character in info.filename)
                or any(
                    part in {"", ".", ".."}
                    or re.fullmatch(r"[A-Za-z0-9._-]+", part) is None
                    for part in info.filename.split("/")
                )
            ):
                failures.append(
                    f"FCStd has unsafe member while scanning: {rel(path)}!{info.filename}"
                )
            if info.flag_bits & 1:
                failures.append(
                    f"FCStd has encrypted member while scanning: {rel(path)}!{info.filename}"
                )
            if stat.S_ISLNK(info.external_attr >> 16):
                failures.append(
                    f"FCStd has symlink member while scanning: {rel(path)}!{info.filename}"
                )
        if any(info.file_size > MAX_FCSTD_MEMBER_BYTES for info in infos):
            failures.append(f"FCStd member exceeds scan limit: {rel(path)}")
        if sum(info.file_size for info in infos) > MAX_FCSTD_TOTAL_BYTES:
            failures.append(f"FCStd archive exceeds scan limit: {rel(path)}")
        if any(info.file_size / max(info.compress_size, 1) > 1000 for info in infos):
            failures.append(f"FCStd archive has suspicious compression: {rel(path)}")
    return failures


def check_required_files() -> list[str]:
    failures: list[str] = []
    inodes: dict[tuple[int, int], str] = {}
    for item in REQUIRED_FILES:
        path = ROOT / item
        if not path.exists():
            failures.append(f"missing required file: {item}")
        elif path.is_symlink() or not path.is_file():
            failures.append(f"required path is not a regular file: {item}")
        elif not path.resolve().is_relative_to(ROOT.resolve()):
            failures.append(f"required file escapes repository root: {item}")
        elif path.stat().st_size == 0:
            failures.append(f"zero-byte required file: {item}")
        else:
            if path.stat().st_nlink != 1:
                failures.append(f"required file must not be a hardlink: {item}")
            cursor = ROOT
            for part in Path(item).parts:
                cursor /= part
                if cursor.is_symlink():
                    failures.append(f"required file uses a symlink: {item}")
                    break
            inode = (path.stat().st_dev, path.stat().st_ino)
            if inode in inodes:
                failures.append(
                    f"required files share an inode: {inodes[inode]} and {item}"
                )
            else:
                inodes[inode] = item
    return failures


def check_expected_counts() -> list[str]:
    failures: list[str] = []
    for pattern, expected in MINIMUM_COUNTS.items():
        actual = len(list(ROOT.glob(pattern)))
        if actual < expected:
            failures.append(f"{pattern}: expected at least {expected}, found {actual}")
    return failures


def check_backups() -> list[str]:
    patterns = ["*.FCBak", "*.FCStd1", "*.bak", "*.tmp", "*.log", "*.rollback"]
    hits = sorted({rel(path) for pattern in patterns for path in ROOT.rglob(pattern)})
    hits.extend(rel(path) for path in ROOT.rglob(".coordproof-*") if rel(path) not in hits)
    return [f"transient file present: {path}" for path in hits]


def check_repository_symlinks() -> list[str]:
    return [
        f"repository symlink present: {rel(path)}"
        for path in ROOT.rglob("*")
        if not any(part in EXCLUDED_DIRS for part in path.parts) and path.is_symlink()
    ]


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
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger, express_rules=True)
    formal_errors = [item for item in logger.statements if item.get("level") == "error"]
    if formal_errors:
        first = str(formal_errors[0].get("message", "validation error")).splitlines()[0]
        failures.append(
            f"{rel(path)} has {len(formal_errors)} formal IFC validation error(s): {first}"
        )
    return failures


def check_git_ignored() -> list[str]:
    return [
        f"environment file present: {rel(path)}"
        for path in ROOT.rglob(".env*")
        if not any(part in EXCLUDED_DIRS for part in path.parts)
    ]


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
        payload = strict_json_loads(PROVENANCE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return [f"invalid manifest/build_provenance.json: {exc}"]

    failures = provenance_metadata_failures(payload)
    if not isinstance(payload, dict):
        return failures
    if payload.get("build_profile") != "full":
        failures.append("public package requires full build provenance")
    source_date = payload.get("source_date")
    if isinstance(source_date, str):
        failures.extend(canonical_desktop_artifact_failures(ROOT, source_date))
    claimed_producers = payload.get("artifact_producers")
    actual_producers = embedded_producer_versions(
        step_path=ROOT / "exports" / "step" / "mechanical_room_assembly.step",
        review_ifc_path=ROOT / "bim" / "mechanical_room_freecad_review.ifc",
    )
    if isinstance(claimed_producers, dict) and claimed_producers != actual_producers:
        failures.append("build provenance artifact producers do not match embedded versions")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        return [*failures, "build provenance has no artifacts object"]

    try:
        required_coverage = set(required_artifact_paths(ROOT))
    except ValueError as exc:
        return [*failures, str(exc)]
    failures.extend(
        f"build provenance missing golden evidence: {item}"
        for item in sorted(required_coverage - artifacts.keys())
    )
    for item, record in artifacts.items():
        try:
            validated_repository_file(ROOT, item)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        path = ROOT / item
        if not isinstance(record, dict):
            failures.append(f"invalid provenance record: {item}")
            continue
        if set(record) != {"sha256", "bytes"}:
            failures.append(f"invalid provenance record fields: {item}")
            continue
        expected_hash = record.get("sha256")
        expected_bytes = record.get("bytes")
        if not isinstance(expected_hash, str) or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
            failures.append(f"invalid provenance SHA-256: {item}")
            continue
        if (
            not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or expected_bytes < 0
        ):
            failures.append(f"invalid provenance byte count: {item}")
            continue
        if expected_hash != file_sha256(path):
            failures.append(f"provenance hash mismatch: {item}")
        if expected_bytes != path.stat().st_size:
            failures.append(f"provenance byte-count mismatch: {item}")
    return failures


def run_validation() -> list[str]:
    token = secrets.token_hex(16)
    result = subprocess.run(
        [sys.executable, "validation/run_all.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env={**os.environ, "COORDPROOF_VALIDATION_TOKEN": token},
    )
    if result.returncode:
        return ["validation/run_all.py failed:\n" + result.stdout]
    if f"Validation Run Token: {token}" not in result.stdout:
        return ["validation/run_all.py did not prove a fresh validation run"]
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
    # Golden evidence must already exist before live validation runs; preflight
    # must not launder a missing committed report by regenerating it first.
    failures.extend(check_required_files())
    failures.extend(check_expected_counts())
    failures.extend(check_backups())
    failures.extend(check_git_ignored())
    failures.extend(check_repository_symlinks())
    failures.extend(check_scan_safety())
    failures.extend(check_validation_report())
    failures.extend(run_project_spec_validation())
    # Verify the checked-in bytes before validation regenerates its report,
    # then verify again so both the committed and freshly generated states are
    # covered by the same provenance manifest.
    failures.extend(check_provenance())
    failures.extend(run_validation())
    failures.extend(check_provenance())
    failures.extend(check_ifc(ROOT / "bim" / "mechanical_room.ifc", min_products=43))
    failures.extend(check_ifc(ROOT / "bim" / "mechanical_room_freecad_review.ifc", min_products=40))
    failures.extend(
        f"secret-like pattern found: {hit}"
        for hit in scan_patterns(SECRET_PATTERNS, scan_binary=True)
    )
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
