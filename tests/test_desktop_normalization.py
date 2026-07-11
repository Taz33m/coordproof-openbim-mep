from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import export_qcad_pdfs, generate_openscad_exports
from tools.artifact_normalization import (
    normalize_ascii_stl,
    normalize_qcad_pdf,
    publish_staged_files,
)

ROOT = Path(__file__).resolve().parents[1]


def _facet(normal: str, vertices: tuple[str, str, str]) -> str:
    return (
        f"  facet normal {normal}\n"
        "    outer loop\n"
        + "".join(f"      vertex {vertex}\n" for vertex in vertices)
        + "    endloop\n"
        "  endfacet\n"
    )


def _tetra_facets(
    *,
    x0: str = "0",
    x1: str = "1",
    cycle: bool = False,
    reverse: bool = False,
) -> list[str]:
    a, b, c, d = f"{x0} 0 0", f"{x1} 0 0", f"{x0} 1 0", f"{x0} 0 1"
    definitions = [
        ("0 0 -1", (a, c, b)),
        ("0 -1 0", (a, b, d)),
        ("-1 0 0", (a, d, c)),
        ("0.5773502691896258 0.5773502691896258 0.5773502691896258", (b, c, d)),
    ]
    if reverse:
        definitions = [
            (" ".join(str(-float(value)) for value in normal.split()), (vertices[0], vertices[2], vertices[1]))
            for normal, vertices in definitions
        ]
    if cycle:
        definitions = [
            (normal, (vertices[1], vertices[2], vertices[0]))
            for normal, vertices in reversed(definitions)
        ]
    return [_facet(normal, vertices) for normal, vertices in definitions]


def _scaled_tetra_facets(
    origin: tuple[float, float, float],
    size: float,
    *,
    reverse: bool = False,
) -> list[str]:
    ox, oy, oz = origin

    def vertex(dx: float, dy: float, dz: float) -> str:
        coordinates = (ox + dx, oy + dy, oz + dz)
        return " ".join(
            str(value) if isinstance(value, int) else f"{value:g}" for value in coordinates
        )

    a = vertex(0, 0, 0)
    b = vertex(size, 0, 0)
    c = vertex(0, size, 0)
    d = vertex(0, 0, size)
    definitions = [
        ("0 0 -1", (a, c, b)),
        ("0 -1 0", (a, b, d)),
        ("-1 0 0", (a, d, c)),
        ("0.5773502691896258 0.5773502691896258 0.5773502691896258", (b, c, d)),
    ]
    if reverse:
        definitions = [
            (
                " ".join(str(-float(value)) for value in normal.split()),
                (vertices[0], vertices[2], vertices[1]),
            )
            for normal, vertices in definitions
        ]
    return [_facet(normal, vertices) for normal, vertices in definitions]


def test_ascii_stl_normalization_is_order_and_cycle_independent(tmp_path: Path) -> None:
    first = tmp_path / "first.stl"
    second = tmp_path / "second.stl"
    first.write_text(
        "solid volatile\n" + "".join(_tetra_facets()) + "endsolid volatile\n",
        encoding="ascii",
    )
    second.write_text(
        "solid other\n"
        + "".join(_tetra_facets(cycle=True))
        + "endsolid other\n",
        encoding="ascii",
    )

    normalize_ascii_stl(first, solid_name="asset_type_a")
    normalize_ascii_stl(second, solid_name="asset_type_a")
    once = first.read_bytes()
    normalize_ascii_stl(first, solid_name="asset_type_a")

    assert first.read_bytes() == second.read_bytes() == once
    assert first.read_text(encoding="ascii").startswith("solid asset_type_a\n")


def test_ascii_stl_normalization_canonicalizes_crlf(tmp_path: Path) -> None:
    path = tmp_path / "windows.stl"
    path.write_bytes(
        (
            "solid volatile\n"
            + "".join(_tetra_facets())
            + "endsolid volatile\n"
        ).replace("\n", "\r\n").encode("ascii")
    )

    normalize_ascii_stl(path, solid_name="asset")

    assert b"\r" not in path.read_bytes()


def test_ascii_stl_normalization_preserves_long_decimal_exactly(tmp_path: Path) -> None:
    coordinate = "1.12345678901234567890123456789"
    path = tmp_path / "precise.stl"
    path.write_text(
        "solid volatile\n"
        + "".join(
            _tetra_facets(
                x0=coordinate,
                x1="2.12345678901234567890123456789",
            )
        )
        + "endsolid volatile\n",
        encoding="ascii",
    )

    normalize_ascii_stl(path, solid_name="precise")

    assert coordinate.encode() in path.read_bytes()


def test_ascii_stl_normalization_rejects_degenerate_facets(tmp_path: Path) -> None:
    path = tmp_path / "degenerate.stl"
    path.write_text(
        "solid bad\n"
        + _facet("0 0 1", ("0 0 0", "1 0 0", "2 0 0"))
        + "endsolid bad\n",
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="degenerate"):
        normalize_ascii_stl(path, solid_name="bad")


def test_ascii_stl_normalization_rejects_inward_winding(tmp_path: Path) -> None:
    outward = tmp_path / "outward.stl"
    reversed_path = tmp_path / "reversed.stl"
    outward.write_text(
        "solid a\n"
        + "".join(_tetra_facets())
        + "endsolid a\n",
        encoding="ascii",
    )
    reversed_path.write_text(
        "solid b\n"
        + "".join(_tetra_facets(reverse=True))
        + "endsolid b\n",
        encoding="ascii",
    )

    normalize_ascii_stl(outward, solid_name="asset")

    with pytest.raises(ValueError, match="positive signed volume"):
        normalize_ascii_stl(reversed_path, solid_name="asset")


def test_ascii_stl_signed_volume_is_exact_for_large_translated_coordinates(
    tmp_path: Path,
) -> None:
    path = tmp_path / "translated-reversed.stl"
    origin = (266952647900000, -917523037300000, 916381185200000)
    path.write_text(
        "solid translated-reversed\n"
        + "".join(_scaled_tetra_facets(origin, 1, reverse=True))
        + "endsolid translated-reversed\n",
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="positive signed volume"):
        normalize_ascii_stl(path, solid_name="translated-reversed")


@pytest.mark.parametrize("token", ["1e-9999999", "1e9999999", "0e-9999999"])
def test_ascii_stl_rejects_extreme_exponents_before_exact_conversion(
    tmp_path: Path,
    token: str,
) -> None:
    path = tmp_path / "extreme-exponent.stl"
    facets = "".join(_tetra_facets()).replace("vertex 0 0 0", f"vertex {token} 0 0")
    path.write_text(
        "solid extreme-exponent\n" + facets + "endsolid extreme-exponent\n",
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="exponent exceeds supported range"):
        normalize_ascii_stl(path, solid_name="extreme-exponent")


def test_ascii_stl_rejects_oversized_number_tokens(tmp_path: Path) -> None:
    path = tmp_path / "oversized-number.stl"
    token = "1." + ("0" * 128)
    facets = "".join(_tetra_facets()).replace("vertex 0 0 0", f"vertex {token} 0 0")
    path.write_text(
        "solid oversized-number\n" + facets + "endsolid oversized-number\n",
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="number token exceeds length limit"):
        normalize_ascii_stl(path, solid_name="oversized-number")


def test_ascii_stl_normalization_rejects_open_surface(tmp_path: Path) -> None:
    path = tmp_path / "open.stl"
    path.write_text(
        "solid open\n"
        + _facet("0 0 1", ("0 0 0", "1 0 0", "0 1 0"))
        + "endsolid open\n",
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="too few facets|not a closed"):
        normalize_ascii_stl(path, solid_name="open")


@pytest.mark.parametrize(
    "origin",
    [
        pytest.param((0.5, 0.5, 0.5), id="enclosed-cavity"),
        pytest.param((10, 0, 0), id="remote-solid"),
        pytest.param((3, 3, 3), id="inside-bounds-outside-tetrahedron"),
    ],
)
def test_ascii_stl_normalization_rejects_disconnected_negative_volume_shell(
    tmp_path: Path,
    origin: tuple[float, float, float],
) -> None:
    path = tmp_path / "negative-shell.stl"
    path.write_text(
        "solid negative-shell\n"
        + "".join(_scaled_tetra_facets((0, 0, 0), 4))
        + "".join(_scaled_tetra_facets(origin, 0.25, reverse=True))
        + "endsolid negative-shell\n",
        encoding="ascii",
    )

    with pytest.raises(ValueError, match="inward-wound disconnected shells"):
        normalize_ascii_stl(path, solid_name="negative-shell")


def test_ascii_stl_normalization_accepts_disconnected_positive_shells(tmp_path: Path) -> None:
    path = tmp_path / "positive-shells.stl"
    path.write_text(
        "solid positive-shells\n"
        + "".join(_scaled_tetra_facets((0, 0, 0), 1))
        + "".join(_scaled_tetra_facets((10, 0, 0), 1))
        + "endsolid positive-shells\n",
        encoding="ascii",
    )

    normalize_ascii_stl(path, solid_name="positive-shells")

    assert path.read_text(encoding="ascii").startswith("solid positive-shells\n")


def test_qcad_pdf_normalization_removes_only_volatile_metadata(tmp_path: Path) -> None:
    source = ROOT / "qcad" / "pdf_exports" / "floor_plan.pdf"
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    shutil.copyfile(source, first)
    variant = source.read_bytes()
    variant = re.sub(
        rb"D:\d{14}Z",
        b"D:20991231235959Z",
        variant,
    )
    variant = re.sub(
        rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}",
        b"2099-12-31T23:59:59-05:00",
        variant,
    )
    replacement_uuid = b"ffffffff-ffff-4fff-8fff-ffffffffffff"
    variant = re.sub(
        rb"uuid:[0-9A-Fa-f-]{36}",
        b"uuid:" + replacement_uuid,
        variant,
    )
    replacement_hex = replacement_uuid.hex().encode()
    variant = re.sub(
        rb"/ID\s*\[\s*<[0-9A-Fa-f]{72}>\s*<[0-9A-Fa-f]{72}>\s*\]",
        b"/ID [ <" + replacement_hex + b"> <" + replacement_hex + b"> ]",
        variant,
    )
    second.write_bytes(variant)

    normalize_qcad_pdf(first, epoch=0)
    normalize_qcad_pdf(second, epoch=0)
    once = first.read_bytes()
    normalize_qcad_pdf(first, epoch=0)

    assert first.read_bytes() == second.read_bytes() == once
    assert b"D:19700101000000Z" in once
    assert b"1970-01-01T00:00:00+00:00" in once


def test_qcad_pdf_normalization_fails_closed_on_unknown_shape(tmp_path: Path) -> None:
    path = tmp_path / "minimal.pdf"
    path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    with pytest.raises(ValueError, match="startxref"):
        normalize_qcad_pdf(path, epoch=0)


def test_qcad_pdf_normalization_only_accepts_named_metadata_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ambiguous.pdf"
    payload = (ROOT / "qcad" / "pdf_exports" / "floor_plan.pdf").read_bytes()
    payload = payload.replace(b"/ModDate", b"/BadDate", 1)
    payload = payload.replace(
        b"startxref",
        b"% drawing text D:20991231235959Z\nstartxref",
        1,
    )
    path.write_bytes(payload)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="Info ModDate"):
        normalize_qcad_pdf(path, epoch=0)

    assert path.read_bytes() == before


def test_qcad_pdf_normalization_rejects_corrupt_drawing_stream(
    tmp_path: Path,
) -> None:
    path = tmp_path / "corrupt-stream.pdf"
    payload = bytearray((ROOT / "qcad" / "pdf_exports" / "floor_plan.pdf").read_bytes())
    object_start = payload.index(b"12 0 obj")
    stream_start = payload.index(b"stream\n", object_start) + len(b"stream\n")
    payload[stream_start + 40] ^= 1
    path.write_bytes(payload)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="FlateDecode stream 12 is corrupt"):
        normalize_qcad_pdf(path, epoch=0)

    assert path.read_bytes() == before


def test_qcad_pdf_normalization_rejects_negative_epoch(tmp_path: Path) -> None:
    path = tmp_path / "floor.pdf"
    shutil.copyfile(ROOT / "qcad" / "pdf_exports" / "floor_plan.pdf", path)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="non-negative integer"):
        normalize_qcad_pdf(path, epoch=-1)

    assert path.read_bytes() == before


def test_qcad_export_is_utc_and_preserves_target_on_normalization_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dxf_path = tmp_path / "drawing.dxf"
    dxf_path.write_text("0\nEOF\n", encoding="ascii")
    pdf_path = tmp_path / "drawing.pdf"
    pdf_path.write_bytes(b"known-good")
    observed_env: dict[str, str] = {}

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        observed_env.update(kwargs["env"])  # type: ignore[arg-type]
        temporary_output = Path(
            next(argument for argument in command if argument.startswith("-outfile=")).split(
                "=", 1
            )[1]
        )
        temporary_output.write_bytes(b"%PDF-broken")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(export_qcad_pdfs.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="startxref"):
        export_qcad_pdfs._export_pdf("dwg2pdf", dxf_path, pdf_path)

    assert observed_env["TZ"] == "UTC"
    assert pdf_path.read_bytes() == b"known-good"
    assert not list(tmp_path.glob(".drawing.*"))


def test_openscad_export_preserves_target_on_normalization_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "asset.scad"
    source_path.write_text("cube(1);\n", encoding="ascii")
    output_path = tmp_path / "asset.stl"
    output_path.write_bytes(b"known-good")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        Path(command[command.index("-o") + 1]).write_bytes(b"raw-vendor-output")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(generate_openscad_exports.subprocess, "run", fake_run)
    monkeypatch.setattr(
        generate_openscad_exports,
        "normalize_ascii_stl",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("invalid STL")),
    )

    with pytest.raises(ValueError, match="invalid STL"):
        generate_openscad_exports._export_stl(
            "openscad",
            "openscad_pipe_clamp_type_b",
            {
                "pipe_diameter_mm": 50,
                "thickness_mm": 5,
                "width_mm": 20,
                "ear_length_mm": 20,
                "bolt_diameter_mm": 10,
            },
            source_path,
            output_path,
        )

    assert output_path.read_bytes() == b"known-good"
    assert not list(tmp_path.glob(".asset.*"))


def test_batch_publication_rolls_back_every_target_on_late_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged = [tmp_path / f"staged-{index}" for index in range(2)]
    targets = [tmp_path / f"target-{index}" for index in range(2)]
    for index, path in enumerate(staged):
        path.write_bytes(f"new-{index}".encode())
    for index, path in enumerate(targets):
        path.write_bytes(f"old-{index}".encode())
    actual_replace = export_qcad_pdfs.os.replace

    def fail_second_replace(source: str | Path, target: str | Path) -> None:
        if Path(source) == staged[1] and Path(target) == targets[1]:
            raise OSError("injected late publication failure")
        actual_replace(source, target)

    monkeypatch.setattr("tools.artifact_normalization.os.replace", fail_second_replace)

    with pytest.raises(OSError, match="injected late"):
        publish_staged_files(zip(staged, targets, strict=True))

    assert [path.read_bytes() for path in targets] == [b"old-0", b"old-1"]
    assert not list(tmp_path.glob("*.rollback"))


def test_batch_publication_rejects_cross_pair_aliases(tmp_path: Path) -> None:
    first = tmp_path / "first"
    middle = tmp_path / "middle"
    last = tmp_path / "last"
    first.write_bytes(b"first")
    middle.write_bytes(b"middle")
    last.write_bytes(b"last")

    with pytest.raises(ValueError, match="must be disjoint"):
        publish_staged_files(((first, middle), (middle, last)))

    assert first.read_bytes() == b"first"
    assert middle.read_bytes() == b"middle"
    assert last.read_bytes() == b"last"


def test_batch_publication_rejects_same_target_aliases(tmp_path: Path) -> None:
    staged = [tmp_path / f"staged-{index}" for index in range(2)]
    for index, path in enumerate(staged):
        path.write_bytes(f"new-{index}".encode())
    target = tmp_path / "target"
    target.write_bytes(b"old")
    subdirectory = tmp_path / "subdirectory"
    subdirectory.mkdir()
    lexical_alias = subdirectory / ".." / target.name

    with pytest.raises(ValueError, match="target paths must not alias"):
        publish_staged_files(((staged[0], target), (staged[1], lexical_alias)))

    assert target.read_bytes() == b"old"
    assert [path.read_bytes() for path in staged] == [b"new-0", b"new-1"]


def test_batch_publication_rejects_same_staged_inode(tmp_path: Path) -> None:
    first = tmp_path / "first"
    alias = tmp_path / "alias"
    first.write_bytes(b"new")
    alias.hardlink_to(first)
    targets = [tmp_path / f"target-{index}" for index in range(2)]

    with pytest.raises(ValueError, match="hardlink|share an inode"):
        publish_staged_files(((first, targets[0]), (alias, targets[1])))


def test_batch_publication_cleans_backup_when_copy_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged = tmp_path / "staged"
    target = tmp_path / "target"
    staged.write_bytes(b"new")
    target.write_bytes(b"old")
    monkeypatch.setattr(
        "tools.artifact_normalization.shutil.copy2",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("copy failed")),
    )

    with pytest.raises(OSError, match="copy failed"):
        publish_staged_files(((staged, target),))

    assert staged.read_bytes() == b"new"
    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob("*.rollback"))
