"""Record hashes and tool versions for the generated evidence package."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import platform
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "manifest" / "build_provenance.json"
EXPORT_INDEX = ROOT / "manifest" / "export_index.csv"

PACKAGE_NAMES = (
    "cadquery",
    "cadquery-ocp",
    "ifcopenshell",
    "ezdxf",
    "reportlab",
    "Pillow",
    "jsonschema",
)
ADDITIONAL_ARTIFACTS = (
    "spec/mechanical_room.project.json",
    "spec/project.schema.json",
    "bim/mechanical_room.ifc",
    "bim/mechanical_room_freecad_review.ifc",
    "bim/bim_object_map.csv",
    "manifest/asset_manifest.json",
    "manifest/export_index.csv",
    "manifest/parameter_schema.json",
    "reports/coordination_report.md",
    "reports/bill_of_materials.csv",
    "reports/clash_clearance_report.csv",
    "validation/validation_report.md",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_paths() -> list[str]:
    paths = set(ADDITIONAL_ARTIFACTS)
    paths.update(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "screenshots").glob("*.png")
        if path.is_file()
    )
    if EXPORT_INDEX.exists():
        with EXPORT_INDEX.open(newline="", encoding="utf-8") as handle:
            paths.update(row["path"] for row in csv.DictReader(handle))
    return sorted(path for path in paths if (ROOT / path).is_file())


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def reproducible_timestamp() -> str | None:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        return None
    return datetime.fromtimestamp(int(raw), tz=UTC).isoformat().replace("+00:00", "Z")


def build_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_date": reproducible_timestamp(),
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "packages": package_versions(),
        },
        "artifacts": {
            path: {"sha256": sha256(ROOT / path), "bytes": (ROOT / path).stat().st_size}
            for path in artifact_paths()
        },
    }


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
