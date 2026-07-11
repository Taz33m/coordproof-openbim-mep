"""Pure-Python canonicality checks for committed desktop CAD artifacts."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from artifact_normalization import normalize_ascii_stl, normalize_qcad_pdf
from freecad_artifact_normalization import (
    normalize_fcstd,
    normalize_review_ifc,
    normalize_step_header,
)

OPENSCAD_ASSETS = (
    "openscad_bracket_plate_type_b",
    "openscad_cable_tray_segment_type_b",
    "openscad_duct_connector_type_b",
    "openscad_pipe_clamp_type_b",
)
MAX_DESKTOP_ARTIFACT_BYTES = 50 * 1024 * 1024


def _epoch(source_date: str) -> int:
    parsed = datetime.strptime(source_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return int(parsed.timestamp())


def canonical_desktop_artifact_failures(root: Path, source_date: str) -> list[str]:
    """Return failures when a desktop artifact changes under canonical normalization."""

    try:
        epoch = _epoch(source_date)
    except ValueError as exc:
        return [f"desktop artifact source_date is invalid: {exc}"]
    failures: list[str] = []
    previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(epoch)
    try:
        with tempfile.TemporaryDirectory(prefix="coordproof-canonical-") as temporary:
            stage = Path(temporary)

            def check(relative: str, normalize) -> None:
                source = root / relative
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source.is_symlink() or not source.is_file():
                    failures.append(f"desktop artifact is missing: {relative}")
                    return
                if not source.resolve().is_relative_to(root.resolve()):
                    failures.append(f"desktop artifact escapes repository root: {relative}")
                    return
                if source.stat().st_nlink != 1:
                    failures.append(f"desktop artifact must not be a hardlink: {relative}")
                    return
                if source.stat().st_size > MAX_DESKTOP_ARTIFACT_BYTES:
                    failures.append(f"desktop artifact exceeds size limit: {relative}")
                    return
                try:
                    shutil.copy2(source, destination)
                    normalize(destination)
                except Exception as exc:  # noqa: BLE001 - normalize failures are diagnostics
                    failures.append(f"desktop artifact validation failed for {relative}: {exc}")
                    return
                if destination.read_bytes() != source.read_bytes():
                    failures.append(f"desktop artifact is not canonical: {relative}")

            pdfs = sorted((root / "qcad" / "pdf_exports").glob("*.pdf"))
            if len(pdfs) != 7:
                failures.append(f"expected 7 canonical QCAD PDFs, found {len(pdfs)}")
            for path in pdfs:
                relative = path.relative_to(root).as_posix()
                check(relative, lambda target: normalize_qcad_pdf(target, epoch=epoch))

            for asset_id in OPENSCAD_ASSETS:
                relative = f"exports/stl/{asset_id}.stl"
                check(
                    relative,
                    lambda target, name=asset_id: normalize_ascii_stl(
                        target,
                        solid_name=name,
                    ),
                )

            check("exports/step/mechanical_room_assembly.step", normalize_step_header)
            check(
                "freecad/mechanical_room.FCStd",
                lambda target: normalize_fcstd(
                    target,
                    artifact_identity="freecad/mechanical_room.FCStd",
                    expected_object_count=61,
                    expected_shape_members=61,
                ),
            )
            check(
                "freecad/mechanical_room_bim.FCStd",
                lambda target: normalize_fcstd(
                    target,
                    artifact_identity="freecad/mechanical_room_bim.FCStd",
                    expected_object_count=74,
                    expected_shape_members=66,
                    expected_empty_shape_members=(
                        "Space.Shape.brp",
                        "BuildingPart.Shape.brp",
                        "BuildingPart001.Shape.brp",
                        "Site.Shape.brp",
                        "Project.Shape.brp",
                    ),
                ),
            )
            check(
                "bim/mechanical_room_freecad_review.ifc",
                lambda target: normalize_review_ifc(
                    target,
                    expected_root_count=72,
                    expected_product_count=65,
                    expected_duplicate_relationship_count=1,
                ),
            )
    finally:
        if previous_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous_epoch
    return failures
