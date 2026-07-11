from __future__ import annotations

from tools import preflight_public_package as preflight


def test_preflight_checks_committed_evidence_before_live_validation(
    monkeypatch,
    capsys,
) -> None:
    events: list[str] = []

    def required_files() -> list[str]:
        events.append("required")
        return ["missing required file: validation/validation_report.md"]

    def live_validation() -> list[str]:
        events.append("validation")
        return []

    monkeypatch.setattr(preflight, "check_required_files", required_files)
    monkeypatch.setattr(preflight, "run_validation", live_validation)
    monkeypatch.setattr(preflight, "check_expected_counts", lambda: [])
    monkeypatch.setattr(preflight, "check_backups", lambda: [])
    monkeypatch.setattr(preflight, "check_git_ignored", lambda: [])
    monkeypatch.setattr(preflight, "check_validation_report", lambda: [])
    monkeypatch.setattr(preflight, "run_project_spec_validation", lambda: [])
    monkeypatch.setattr(preflight, "check_provenance", lambda: [])
    monkeypatch.setattr(preflight, "check_ifc", lambda path, min_products: [])
    monkeypatch.setattr(preflight, "scan_patterns", lambda patterns: [])

    assert preflight.main() == 1
    assert events == ["required", "validation"]
    assert "missing required file" in capsys.readouterr().out
