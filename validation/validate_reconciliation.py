"""Validate the versioned cross-format parameter reconciliation contract."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from reconcile_parameters import (  # noqa: E402
    DEFAULT_CSV_PATH,
    DEFAULT_MARKDOWN_PATH,
    reconcile,
    render_reports,
)


def validate() -> dict[str, object]:
    result = reconcile()
    live_status = result["status"]
    expected_csv, expected_markdown = render_reports(result)
    failures = list(result["failures"])
    if live_status != "passed" and not failures:
        failures.append(
            "[LIVE_RECONCILIATION] reconciliation failed without a diagnostic"
        )
    for path, expected in (
        (DEFAULT_CSV_PATH, expected_csv),
        (DEFAULT_MARKDOWN_PATH, expected_markdown),
    ):
        if not path.is_file():
            failures.append(f"[STALE_REPORT] missing {path.relative_to(ROOT)}")
        elif path.read_text(encoding="utf-8") != expected:
            failures.append(
                f"[STALE_REPORT] {path.relative_to(ROOT)} does not match live reconciliation"
            )
    result["failures"] = failures
    result["status"] = (
        "passed" if live_status == "passed" and not failures else "failed"
    )
    result["summary"] = {
        **result["summary"],
        "committed_report_count": 2,
        "failure_count": len(failures),
    }
    return result


def main() -> int:
    result = validate()
    for failure in result["failures"]:
        print(failure)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
