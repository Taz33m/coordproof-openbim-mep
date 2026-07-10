from __future__ import annotations

from pathlib import Path

from asset_io import normalize_step_header

from tools.generate_drawings import setup_doc


def test_step_header_normalization_removes_time_and_host_path(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "asset.step"
    path.write_text(
        "ISO-10303-21;\nHEADER;\n"
        "FILE_NAME('/private/tmp/asset.step','2099-01-02T03:04:05',(''),(''),'','','');\n"
        "ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)

    normalize_step_header(path)

    text = path.read_text(encoding="utf-8")
    assert "FILE_NAME('asset.step','1970-01-01T00:00:00'" in text
    assert "/private/tmp" not in text


def test_dxf_metadata_is_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first.dxf"
    second = tmp_path / "second.dxf"

    setup_doc().saveas(first)
    setup_doc().saveas(second)

    assert first.read_bytes() == second.read_bytes()
