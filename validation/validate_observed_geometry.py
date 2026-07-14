"""Validate live format geometry against the committed observation matrix."""

from __future__ import annotations

import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from generate_observed_geometry_matrix import (  # noqa: E402
    DEFAULT_CSV_PATH,
    DEFAULT_IFC_PATH,
    DEFAULT_MARKDOWN_PATH,
    build_rows,
    write_csv,
    write_markdown,
)
from project_spec import load_project_spec  # noqa: E402


def validate() -> dict[str, object]:
    failures: list[str] = []
    warnings: list[str] = []
    try:
        rows = build_rows(load_project_spec(), ifc_path=DEFAULT_IFC_PATH)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "name": "Observed Geometry",
            "status": "failed",
            "summary": {"observation_count": 0, "failure_count": 1},
            "failures": [f"[OBSERVATION_ERROR] {exc}"],
            "warnings": [],
        }

    for row in rows:
        if row["status"] == "FAIL":
            failures.append(
                f"[{row['format'].upper()}_GEOMETRY] "
                f"{row['occurrence_id'] or row['type_id']}: "
                f"{row['diagnostic'] or 'observed bounds exceed tolerance'}"
            )
        elif row["status"] == "EXCLUDED":
            warnings.append(
                f"[EXPLICIT_EXCLUSION] {row['artifact_path']}: {row['diagnostic']}"
            )

    with tempfile.TemporaryDirectory(prefix="coordproof-observed-geometry-") as folder:
        temporary = Path(folder)
        generated_csv = temporary / DEFAULT_CSV_PATH.name
        generated_markdown = temporary / DEFAULT_MARKDOWN_PATH.name
        write_csv(rows, generated_csv)
        write_markdown(rows, generated_markdown)
        for committed, generated in (
            (DEFAULT_CSV_PATH, generated_csv),
            (DEFAULT_MARKDOWN_PATH, generated_markdown),
        ):
            if not committed.is_file():
                failures.append(f"[STALE_REPORT] missing {committed.relative_to(ROOT)}")
            elif committed.read_bytes() != generated.read_bytes():
                failures.append(
                    f"[STALE_REPORT] {committed.relative_to(ROOT)} does not match live geometry"
                )

    counts = Counter(row["status"] for row in rows)
    format_counts = Counter(row["format"] for row in rows)
    return {
        "name": "Observed Geometry",
        "status": "passed" if not failures else "failed",
        "summary": {
            "observation_count": len(rows),
            "passing_observation_count": counts["PASS"],
            "failed_observation_count": counts["FAIL"],
            "explicit_exclusion_count": counts["EXCLUDED"],
            "format_observation_counts": dict(sorted(format_counts.items())),
            "committed_report_count": 2,
            "failure_count": len(failures),
        },
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    result = validate()
    for failure in result["failures"]:
        print(failure)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
