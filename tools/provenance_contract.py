"""Shared, fail-closed contract for CoordProof build provenance."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

PORTABLE_COMPONENT = re.compile(r"[A-Za-z0-9._-]+")
ASSET_ID = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
EXPORT_FORMAT = re.compile(r"[a-z][a-z0-9_]*")
VERSION = re.compile(
    r"\d+(?:\.\d+)+(?:a\d+|b\d+|rc\d+)?"
    r"(?:\.post\d+)?(?:\.dev\d+)?"
    r"(?:\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?",
    re.IGNORECASE,
)
SENTINELS = {"not-installed", "not-probed", "version-unavailable"}
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

REQUIRED_PACKAGES = frozenset(
    {
        "Pillow",
        "cadquery",
        "cadquery-ocp",
        "defusedxml",
        "ezdxf",
        "ifcopenshell",
        "jsonschema",
        "reportlab",
    }
)
DESKTOP_TOOLS = frozenset({"freecad", "openscad", "qcad"})
ARTIFACT_PRODUCERS = frozenset(
    {"freecad_review_ifcopenshell", "freecad_step_occt"}
)
ADDITIONAL_ARTIFACTS = (
    "spec/mechanical_room.project.json",
    "spec/project.schema.json",
    "spec/reconciliation.contract.json",
    "spec/reconciliation.schema.json",
    "bim/mechanical_room.ifc",
    "bim/mechanical_room_freecad_review.ifc",
    "bim/bim_object_map.csv",
    "bim/ifc_export_notes.md",
    "manifest/asset_manifest.json",
    "manifest/export_index.csv",
    "manifest/parameter_schema.json",
    "reports/coordination_report.md",
    "reports/bill_of_materials.csv",
    "reports/clash_clearance_report.csv",
    "reports/parameter_reconciliation.csv",
    "reports/parameter_reconciliation.md",
    "reports/observed_geometry_matrix.csv",
    "reports/observed_geometry_matrix.md",
    "validation/validation_report.md",
)
REQUIRED_SCREENSHOTS = tuple(
    f"screenshots/{name}.png"
    for name in (
        "00_coordproof_system_overview",
        "01_freecad_mechanical_room_overview",
        "02_freecad_bim_structure",
        "03_cadquery_asset_grid",
        "04_qcad_floor_plan",
        "05_ifc_validation_report",
        "06_export_formats_overview",
        "07_qcad_section_and_riser",
    )
)
GENERATOR_INPUT_GLOBS = (
    "tools/*.py",
    "validation/*.py",
    "cadquery/*.py",
    "freecad/*.FCMacro",
    "openscad/*.scad",
)
GENERATOR_INPUT_FILES = (
    "Makefile",
    "requirements.txt",
    "constraints-release.txt",
)
PUBLIC_ARTIFACT_GLOBS = (
    "exports/step/*.step",
    "exports/stl/*.stl",
    "qcad/*.dxf",
    "qcad/pdf_exports/*.pdf",
    "freecad/*.FCStd",
    "bim/*.ifc",
    "bim/*.csv",
    "bim/*.md",
    "reports/*.csv",
    "reports/*.md",
    "screenshots/*.png",
)


def strict_json_loads(text: str) -> object:
    """Reject duplicate keys and non-standard numeric constants."""

    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> object:
        raise ValueError(f"invalid JSON constant: {value}")

    return json.loads(
        text,
        object_pairs_hook=object_pairs,
        parse_constant=invalid_constant,
    )


def validated_repository_file(root: Path, item: str) -> str:
    """Return a canonical repository path or reject it with a useful error."""

    if not item or "\\" in item or any(ord(character) < 32 for character in item):
        raise ValueError(f"Unsafe provenance path: {item!r}")
    parts = item.split("/")
    if any(
        part in {"", ".", ".."}
        or PORTABLE_COMPONENT.fullmatch(part) is None
        or part.endswith((".", " "))
        or len(part.encode("utf-8")) > 255
        or part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES
        for part in parts
    ) or len(item.encode("utf-8")) > 240:
        raise ValueError(f"Unsafe provenance path: {item!r}")
    candidate = Path(item)
    if candidate.is_absolute() or candidate.as_posix() != item:
        raise ValueError(f"Unsafe provenance path: {item!r}")
    absolute = root / candidate
    cursor = root
    for part in parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"Provenance artifact uses a symlink: {item}")
    if absolute.is_symlink() or not absolute.is_file():
        raise ValueError(f"Provenance artifact is not a regular file: {item}")
    if not absolute.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Provenance artifact escapes repository root: {item}")
    if absolute.stat().st_nlink != 1:
        raise ValueError(f"Provenance artifact must not be a hardlink: {item}")
    return item


def required_artifact_paths(
    root: Path,
    *,
    export_index: Path | None = None,
) -> list[str]:
    """Load every required provenance path, rejecting malformed index entries."""

    index = export_index or root / "manifest" / "export_index.csv"
    if index.is_symlink() or not index.is_file():
        raise ValueError("Provenance export index is not a regular file")
    if not index.resolve().is_relative_to(root.resolve()):
        raise ValueError("Provenance export index escapes repository root")

    try:
        with index.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != ["asset_id", "format", "path"]:
                raise ValueError(
                    "Provenance export index must have asset_id,format,path columns"
                )
            indexed = []
            index_triples: list[tuple[str, str, str]] = []
            mappings: set[tuple[str, str]] = set()
            for row_number, row in enumerate(reader, start=2):
                if None in row or any(
                    not isinstance(row.get(field), str) for field in reader.fieldnames
                ):
                    raise ValueError(f"Malformed provenance export-index row {row_number}")
                if any(
                    not row[field]
                    or row[field] != row[field].strip()
                    for field in reader.fieldnames
                ):
                    raise ValueError(f"Malformed provenance export-index row {row_number}")
                if ASSET_ID.fullmatch(row["asset_id"]) is None:
                    raise ValueError(
                        f"Malformed provenance export-index asset_id on row {row_number}"
                    )
                if EXPORT_FORMAT.fullmatch(row["format"]) is None:
                    raise ValueError(
                        f"Malformed provenance export-index format on row {row_number}"
                    )
                mapping = (row["asset_id"], row["format"])
                if mapping in mappings:
                    raise ValueError(
                        "Duplicate provenance export-index asset/format mapping "
                        f"on row {row_number}"
                    )
                mappings.add(mapping)
                path = row["path"]
                try:
                    indexed.append(validated_repository_file(root, path))
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid provenance export-index row {row_number}: {exc}"
                    ) from exc
                index_triples.append((row["asset_id"], row["format"], path))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError(f"Could not read provenance export index: {exc}") from exc

    manifest_path = root / "manifest" / "asset_manifest.json"
    validated_repository_file(root, "manifest/asset_manifest.json")
    try:
        manifest = strict_json_loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Could not read provenance asset manifest: {exc}") from exc
    if not isinstance(manifest, dict) or set(manifest) != {"assets"}:
        raise ValueError("Provenance asset manifest root is invalid")
    assets = manifest["assets"]
    if not isinstance(assets, list) or not assets:
        raise ValueError("Provenance asset manifest has no assets")
    expected_triples: set[tuple[str, str, str]] = set()
    manifest_asset_ids: set[str] = set()
    for asset_number, asset in enumerate(assets, start=1):
        if not isinstance(asset, dict):
            raise ValueError(f"Malformed provenance asset manifest entry {asset_number}")
        asset_id = asset.get("asset_id")
        exports = asset.get("exports")
        if not isinstance(asset_id, str) or ASSET_ID.fullmatch(asset_id) is None:
            raise ValueError(f"Malformed provenance manifest asset_id at entry {asset_number}")
        if asset_id in manifest_asset_ids:
            raise ValueError(f"Duplicate provenance manifest asset_id: {asset_id}")
        manifest_asset_ids.add(asset_id)
        if not isinstance(exports, dict):
            raise ValueError(f"Malformed provenance manifest exports for {asset_id}")
        for export_format, path in exports.items():
            if (
                not isinstance(export_format, str)
                or EXPORT_FORMAT.fullmatch(export_format) is None
                or not isinstance(path, str)
            ):
                raise ValueError(f"Malformed provenance manifest export for {asset_id}")
            expected_triples.add((asset_id, export_format, path))
    if len(index_triples) != len(expected_triples) or set(index_triples) != expected_triples:
        raise ValueError(
            "Provenance export index does not exactly match asset-manifest exports"
        )

    generator_inputs = set(GENERATOR_INPUT_FILES)
    for pattern in GENERATOR_INPUT_GLOBS:
        matches = {
            path.relative_to(root).as_posix()
            for path in root.glob(pattern)
            if path.is_file()
        }
        if not matches:
            raise ValueError(f"Provenance generator-input pattern is empty: {pattern}")
        generator_inputs.update(matches)
    required = {
        *ADDITIONAL_ARTIFACTS,
        *REQUIRED_SCREENSHOTS,
        *generator_inputs,
        *indexed,
    }
    public_artifacts = {
        path.relative_to(root).as_posix()
        for pattern in PUBLIC_ARTIFACT_GLOBS
        for path in root.glob(pattern)
        if path.is_file() or path.is_symlink()
    }
    unexpected = sorted(public_artifacts - required)
    if unexpected:
        raise ValueError(
            "Unindexed public artifacts are present: " + ", ".join(unexpected)
        )
    validated = sorted(validated_repository_file(root, item) for item in required)
    if len({item.casefold() for item in validated}) != len(validated):
        raise ValueError("Provenance artifact paths contain a case-insensitive collision")
    return validated


def provenance_metadata_failures(payload: object) -> list[str]:
    """Validate provenance-v2 metadata independently of artifact hashes."""

    if not isinstance(payload, dict):
        return ["build provenance root must be an object"]
    failures: list[str] = []
    required_root = {
        "schema_version",
        "build_profile",
        "source_date",
        "environment",
        "artifact_producers",
        "artifacts",
    }
    if set(payload) != required_root:
        failures.append("build provenance root fields are incomplete or unexpected")
    if payload.get("schema_version") != 2:
        failures.append("build provenance schema_version must be 2")
    profile = payload.get("build_profile")
    if profile not in {"core", "full"}:
        failures.append("build provenance build_profile must be core or full")
    source_date = payload.get("source_date")
    try:
        if not isinstance(source_date, str):
            raise ValueError
        parsed_source_date = datetime.strptime(source_date, "%Y-%m-%dT%H:%M:%SZ")
        if (
            parsed_source_date.strftime("%Y-%m-%dT%H:%M:%SZ") != source_date
            or parsed_source_date < datetime(1970, 1, 1)
        ):
            raise ValueError
    except ValueError:
        failures.append("build provenance source_date must be a UTC timestamp")

    environment = payload.get("environment")
    if not isinstance(environment, dict):
        failures.append("build provenance has no environment object")
        return failures
    required_environment = {
        "python",
        "implementation",
        "platform",
        "machine",
        "packages",
        "desktop_tools",
    }
    if set(environment) != required_environment:
        failures.append("build provenance environment fields are incomplete or unexpected")
    for field in ("python", "implementation", "platform", "machine"):
        value = environment.get(field)
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            or value in SENTINELS
            or any(ord(character) < 32 for character in value)
        ):
            failures.append(f"build provenance environment has invalid {field}")
    python_version = environment.get("python")
    if isinstance(python_version, str) and VERSION.fullmatch(python_version) is None:
        failures.append("build provenance environment has invalid python version")
    packages = environment.get("packages")
    if not isinstance(packages, dict):
        failures.append("build provenance environment has no packages object")
    else:
        for name in sorted(REQUIRED_PACKAGES - packages.keys()):
            failures.append(f"build provenance packages missing {name}")
        for name in sorted(packages.keys() - REQUIRED_PACKAGES):
            failures.append(f"build provenance packages has unexpected {name}")
        for name in sorted(REQUIRED_PACKAGES & packages.keys()):
            value = packages[name]
            if not isinstance(value, str) or VERSION.fullmatch(value) is None:
                failures.append(f"build provenance packages has invalid {name} version")

    version_pattern = re.compile(r"\d+(?:\.\d+)+")
    desktop_tools = environment.get("desktop_tools")
    if not isinstance(desktop_tools, dict) or set(desktop_tools) != DESKTOP_TOOLS:
        failures.append("build provenance desktop_tools is incomplete")
    else:
        for name, value in desktop_tools.items():
            if not isinstance(value, str) or (
                value not in SENTINELS and version_pattern.fullmatch(value) is None
            ):
                failures.append(f"build provenance desktop_tools has invalid {name} version")
        if profile == "core" and set(desktop_tools.values()) != {"not-probed"}:
            failures.append("core provenance must not probe desktop tools")
        if profile == "full" and any(
            not isinstance(value, str) or version_pattern.fullmatch(value) is None
            for value in desktop_tools.values()
        ):
            failures.append("full provenance must record every desktop-tool version")

    producers = payload.get("artifact_producers")
    if not isinstance(producers, dict) or set(producers) != ARTIFACT_PRODUCERS:
        failures.append("build provenance artifact_producers is incomplete")
    else:
        for name, value in producers.items():
            if not isinstance(value, str) or version_pattern.fullmatch(value) is None:
                failures.append(f"build provenance has invalid {name} version")
    return failures
