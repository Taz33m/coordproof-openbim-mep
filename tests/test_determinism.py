from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from asset_io import normalize_step_header

from tools.generate_drawings import setup_doc

ROOT = Path(__file__).resolve().parents[1]


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


def test_dxf_serialization_is_stable_across_hash_seeds(tmp_path: Path) -> None:
    script = (
        "from pathlib import Path; "
        "from tools.generate_drawings import setup_doc; "
        "setup_doc().saveas(Path(__import__('sys').argv[1]))"
    )
    outputs = []
    for seed in ("1", "424242"):
        output = tmp_path / f"seed-{seed}.dxf"
        subprocess.run(
            [sys.executable, "-c", script, str(output)],
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=True,
        )
        outputs.append(output.read_bytes())

    assert outputs[0] == outputs[1]
