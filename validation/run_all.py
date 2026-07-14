"""Run all validators and write a Markdown validation report."""

from __future__ import annotations

import os
from pathlib import Path

from validate_exports import validate as validate_exports
from validate_ifc import validate as validate_ifc
from validate_manifest import validate as validate_manifest
from validate_observed_geometry import validate as validate_observed_geometry
from validate_reconciliation import validate as validate_reconciliation
from validate_sources import validate as validate_sources

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "validation" / "validation_report.md"
DEFAULT_VALIDATION_LABEL = "deterministic report; set VALIDATION_DATE to stamp a release"


def status_line(status: str) -> str:
    return "PASSED" if status == "passed" else "FAILED"


def render_section(result: dict[str, object]) -> list[str]:
    lines = [f"## {result['name']} Validation", "", f"Status: **{status_line(result['status'])}**", ""]
    summary = result.get("summary", {})
    if summary:
        lines.extend(["### Summary", "", "| Metric | Value |", "| --- | --- |"])
        for key, value in summary.items():
            if isinstance(value, dict):
                value = ", ".join(f"{k}: {v}" for k, v in value.items())
            lines.append(f"| `{key}` | {value} |")
        lines.append("")

    failures = result.get("failures", [])
    lines.extend(["### Failures", ""])
    if failures:
        lines.extend([f"- {failure}" for failure in failures])
    else:
        lines.append("- None")
    lines.append("")

    warnings = result.get("warnings", [])
    lines.extend(["### Warnings", ""])
    if warnings:
        lines.extend([f"- {warning}" for warning in warnings])
    else:
        lines.append("- None")
    lines.append("")
    return lines


def main() -> int:
    results = [
        validate_sources(),
        validate_reconciliation(),
        validate_ifc(),
        validate_observed_geometry(),
        validate_manifest(),
        validate_exports(),
    ]
    overall = "passed" if all(result["status"] == "passed" for result in results) else "failed"
    lines = [
        "# Validation Report",
        "",
        f"Validation Date: {os.environ.get('VALIDATION_DATE', DEFAULT_VALIDATION_LABEL)}",
        "",
        f"Overall Status: **{status_line(overall)}**",
        "",
        "This report checks IFC readability, semantic MEP class coverage, distribution systems, port connectivity, property sets, observed IFC/STEP/STL/DXF bounding-envelope parity, manifest completeness, export presence, file sizes, and required asset coverage. It does not perform engineering or code-compliance validation.",
        "",
    ]
    for result in results:
        lines.extend(render_section(result))

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT}")
    print(f"Overall Status: {status_line(overall)}")
    validation_token = os.environ.get("COORDPROOF_VALIDATION_TOKEN")
    if validation_token:
        print(f"Validation Run Token: {validation_token}")
    return 0 if overall == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
