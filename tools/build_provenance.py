"""Record hashes and tool versions for the generated evidence package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import tempfile
from pathlib import Path

from artifact_normalization import publish_staged_files
from desktop_artifact_contract import canonical_desktop_artifact_failures
from provenance_contract import (
    ADDITIONAL_ARTIFACTS as ADDITIONAL_ARTIFACTS,
)
from provenance_contract import (
    provenance_metadata_failures,
    required_artifact_paths,
)
from reproducibility import source_timestamp
from tooling import freecad_command, openscad_command, qcad_pdf_command

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "manifest" / "build_provenance.json"

PACKAGE_NAMES = (
    "cadquery",
    "cadquery-ocp",
    "defusedxml",
    "ifcopenshell",
    "ezdxf",
    "reportlab",
    "Pillow",
    "jsonschema",
)
VERSION_UNAVAILABLE = "version-unavailable"
NOT_INSTALLED = "not-installed"
NOT_PROBED = "not-probed"


def sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Provenance artifact is not a regular file: {path}")
    if not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError(f"Provenance artifact escapes repository root: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_paths() -> list[str]:
    return required_artifact_paths(ROOT)


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _probe_version(
    executable: Path | None,
    arguments: tuple[str, ...],
    pattern: re.Pattern[str],
) -> str:
    """Return only a stable version token from optional desktop-tool output."""

    if executable is None:
        return NOT_INSTALLED
    try:
        result = subprocess.run(
            [str(executable), *arguments],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
        )
    except (OSError, subprocess.SubprocessError):
        return VERSION_UNAVAILABLE
    output = f"{result.stdout}\n{result.stderr}"
    match = pattern.search(output)
    if result.returncode != 0 or match is None:
        return VERSION_UNAVAILABLE
    return match.group("version")


def _qcad_version_executable(exporter: Path | None) -> Path | None:
    """Locate QCAD itself without invoking the delayed dwg2pdf trial script."""

    if exporter is None:
        return None
    candidates = (
        exporter.parent.parent / "MacOS" / "QCAD",
        exporter.with_name("qcad"),
        exporter.with_name("qcad.exe"),
    )
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        None,
    )


def desktop_tool_versions() -> dict[str, str]:
    """Record installed desktop producers without leaking machine-local paths."""

    return {
        "freecad": _probe_version(
            freecad_command(),
            ("--version",),
            re.compile(r"\bFreeCAD\s+(?P<version>\d+(?:\.\d+)+)\b"),
        ),
        "openscad": _probe_version(
            openscad_command(),
            ("--version",),
            re.compile(r"\bOpenSCAD(?:\s+version)?\s+(?P<version>\d+(?:\.\d+)+)\b"),
        ),
        "qcad": _probe_version(
            _qcad_version_executable(qcad_pdf_command()),
            ("-version",),
            re.compile(r"(?:QCAD version\s+|Version:\s*)(?P<version>\d+(?:\.\d+)+)\b"),
        ),
    }


def _embedded_version(path: Path, pattern: re.Pattern[str]) -> str:
    if not path.is_file():
        return NOT_INSTALLED
    try:
        match = pattern.search(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError):
        return VERSION_UNAVAILABLE
    return match.group("version") if match is not None else VERSION_UNAVAILABLE


def embedded_producer_versions(
    *,
    step_path: Path | None = None,
    review_ifc_path: Path | None = None,
) -> dict[str, str]:
    """Read the library versions embedded by the actual FreeCAD exports."""

    step = step_path or ROOT / "exports" / "step" / "mechanical_room_assembly.step"
    review_ifc = review_ifc_path or ROOT / "bim" / "mechanical_room_freecad_review.ifc"
    return {
        "freecad_step_occt": _embedded_version(
            step,
            re.compile(r"Open CASCADE STEP processor (?P<version>\d+(?:\.\d+)+)"),
        ),
        "freecad_review_ifcopenshell": _embedded_version(
            review_ifc,
            re.compile(r"'IfcOpenShell (?P<version>\d+(?:\.\d+)+)'"),
        ),
    }


def reproducible_timestamp() -> str:
    return source_timestamp() + "Z"


def build_payload(*, profile: str = "core") -> dict[str, object]:
    if profile not in {"core", "full"}:
        raise ValueError(f"Unknown provenance profile: {profile}")
    desktop_versions = (
        desktop_tool_versions()
        if profile == "full"
        else {name: NOT_PROBED for name in ("freecad", "openscad", "qcad")}
    )
    return {
        "schema_version": 2,
        "build_profile": profile,
        "source_date": reproducible_timestamp(),
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "packages": package_versions(),
            "desktop_tools": desktop_versions,
        },
        "artifact_producers": embedded_producer_versions(),
        "artifacts": {
            path: {"sha256": sha256(ROOT / path), "bytes": (ROOT / path).stat().st_size}
            for path in artifact_paths()
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("core", "full"),
        default="core",
        help="full probes desktop producer versions; core never executes optional tools",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    provenance = build_payload(profile=args.profile)
    failures = provenance_metadata_failures(provenance)
    if failures:
        raise ValueError(
            "Refusing to publish invalid build provenance: " + "; ".join(failures)
        )
    if args.profile == "full":
        canonical_failures = canonical_desktop_artifact_failures(
            ROOT,
            provenance["source_date"],
        )
        if canonical_failures:
            raise ValueError(
                "Refusing to publish noncanonical desktop artifacts: "
                + "; ".join(canonical_failures)
            )
    payload = (json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.TemporaryDirectory(dir=OUTPUT.parent, prefix=".coordproof-provenance-") as temp:
        staged = Path(temp) / OUTPUT.name
        with staged.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        publish_staged_files(((staged, OUTPUT),))
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
