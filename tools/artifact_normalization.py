"""Deterministic normalization for volatile desktop-tool export metadata/order."""

from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import tempfile
import uuid
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

from reproducibility import source_date_epoch, source_timestamp

STL_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
PDF_INFO_DATE_FIELDS = tuple(
    re.compile(rb"(?P<prefix>/" + name + rb" \()D:\d{14}Z(?=\))")
    for name in (b"CreationDate", b"ModDate")
)
PDF_XMP_DATE_FIELDS = tuple(
    re.compile(
        rb"(?P<prefix>" + name + rb"=\")"
        rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}(?=\")"
    )
    for name in (b"xmp:CreateDate", b"xmp:ModifyDate", b"xmp:MetadataDate")
)
PDF_XMP_DOCUMENT_ID = re.compile(
    rb"(?P<prefix>xmpMM:DocumentID=\"uuid:)"
    rb"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    rb"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}(?=\")"
)
PDF_TRAILER_ID = re.compile(
    rb"/ID\s*\[\s*<[0-9A-Fa-f]{72}>\s*<[0-9A-Fa-f]{72}>\s*\]"
)
PDF_STARTXREF = re.compile(rb"startxref\s+(\d+)\s+%%EOF\s*$")
MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_PDF_STREAM_BYTES = 10 * 1024 * 1024
MAX_PDF_DECODED_BYTES = 10 * 1024 * 1024
MAX_PDF_TOTAL_DECODED_BYTES = 20 * 1024 * 1024
MAX_ASCII_STL_BYTES = 10 * 1024 * 1024
MAX_ASCII_STL_FACETS = 200_000
MAX_ASCII_STL_NUMBER_CHARS = 128
MAX_ASCII_STL_ADJUSTED_EXPONENT = 100


@dataclass(frozen=True)
class _Facet:
    normal: tuple[Decimal, Decimal, Decimal]
    vertices: tuple[
        tuple[Decimal, Decimal, Decimal],
        tuple[Decimal, Decimal, Decimal],
        tuple[Decimal, Decimal, Decimal],
    ]


_DecimalPoint = tuple[Decimal, Decimal, Decimal]
_FractionPoint = tuple[Fraction, Fraction, Fraction]


def _fraction_point(point: _DecimalPoint) -> _FractionPoint:
    """Convert a parsed decimal point to exact rational coordinates."""

    return (Fraction(point[0]), Fraction(point[1]), Fraction(point[2]))


def _exact_vertex(
    point: _DecimalPoint,
    cache: dict[_DecimalPoint, _FractionPoint],
) -> _FractionPoint:
    if point not in cache:
        cache[point] = _fraction_point(point)
    return cache[point]


def _decimal_tokens(line: str, prefix: str, count: int) -> tuple[Decimal, ...]:
    parts = line.strip().split()
    prefix_parts = prefix.split()
    if parts[: len(prefix_parts)] != prefix_parts or len(parts) != len(prefix_parts) + count:
        raise ValueError(f"Malformed ASCII STL line: {line!r}")
    number_tokens = parts[len(prefix_parts) :]
    if any(len(token) > MAX_ASCII_STL_NUMBER_CHARS for token in number_tokens):
        raise ValueError(f"ASCII STL number token exceeds length limit: {line!r}")
    try:
        values = tuple(Decimal(token) for token in number_tokens)
    except InvalidOperation as exc:
        raise ValueError(f"Malformed ASCII STL number: {line!r}") from exc
    if not all(value.is_finite() for value in values):
        raise ValueError(f"Non-finite ASCII STL number: {line!r}")
    if any(abs(value.adjusted()) > MAX_ASCII_STL_ADJUSTED_EXPONENT for value in values):
        raise ValueError(f"ASCII STL number exponent exceeds supported range: {line!r}")
    return values


def _validate_facet(
    facet: _Facet,
    exact_vertices: dict[_DecimalPoint, _FractionPoint],
) -> None:
    first, second, third = tuple(
        _exact_vertex(vertex, exact_vertices) for vertex in facet.vertices
    )
    left = tuple(second[index] - first[index] for index in range(3))
    right = tuple(third[index] - first[index] for index in range(3))
    cross = (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )
    magnitude = math.sqrt(sum(float(value) ** 2 for value in cross))
    if not math.isfinite(magnitude) or magnitude == 0:
        raise ValueError("ASCII STL facet is degenerate")
    computed = tuple(float(value) / magnitude for value in cross)
    declared = tuple(float(value) for value in facet.normal)
    declared_magnitude = math.sqrt(sum(value**2 for value in declared))
    if abs(declared_magnitude - 1.0) > 1e-5 or any(
        abs(actual - expected) > 1e-5
        for actual, expected in zip(declared, computed, strict=True)
    ):
        raise ValueError("ASCII STL facet normal does not match its winding")


def _format_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    # Decimal.normalize() applies the active decimal context and can silently
    # round vendor coordinates with more than 28 significant digits.
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _validate_closed_mesh(
    facets: list[_Facet],
    exact_vertices: dict[_DecimalPoint, _FractionPoint],
) -> None:
    """Require consistently oriented, positive-volume closed manifold shells."""

    if len(facets) < 4:
        raise ValueError("ASCII STL mesh has too few facets to enclose a volume")
    edge_facets: dict[
        tuple[tuple[Decimal, Decimal, Decimal], tuple[Decimal, Decimal, Decimal]],
        list[int],
    ] = defaultdict(list)
    directed_edges: Counter[
        tuple[tuple[Decimal, Decimal, Decimal], tuple[Decimal, Decimal, Decimal]]
    ] = Counter()
    for facet_index, facet in enumerate(facets):
        first, second, third = facet.vertices
        for start, end in ((first, second), (second, third), (third, first)):
            edge_facets[tuple(sorted((start, end)))].append(facet_index)
            directed_edges[(start, end)] += 1

    bad_incidence = [edge for edge, owners in edge_facets.items() if len(owners) != 2]
    if bad_incidence:
        raise ValueError(
            "ASCII STL mesh is not a closed 2-manifold "
            f"({len(bad_incidence)} edges do not have incidence 2)"
        )
    bad_orientation = [
        edge
        for edge in edge_facets
        if directed_edges[edge] != 1 or directed_edges[(edge[1], edge[0])] != 1
    ]
    if bad_orientation:
        raise ValueError(
            "ASCII STL mesh has inconsistent facet orientation "
            f"across {len(bad_orientation)} edges"
        )

    neighbors: dict[int, set[int]] = defaultdict(set)
    for first_owner, second_owner in edge_facets.values():
        neighbors[first_owner].add(second_owner)
        neighbors[second_owner].add(first_owner)
    unvisited = set(range(len(facets)))
    while unvisited:
        pending = [unvisited.pop()]
        component: list[int] = []
        while pending:
            facet_index = pending.pop()
            component.append(facet_index)
            discovered = neighbors[facet_index] & unvisited
            unvisited.difference_update(discovered)
            pending.extend(discovered)
        reference = _exact_vertex(facets[component[0]].vertices[0], exact_vertices)
        component_volume = Fraction()
        for facet_index in component:
            translated = tuple(
                tuple(
                    coordinate - reference[axis]
                    for axis, coordinate in enumerate(_exact_vertex(vertex, exact_vertices))
                )
                for vertex in facets[facet_index].vertices
            )
            first, second, third = translated
            cross = (
                second[1] * third[2] - second[2] * third[1],
                second[2] * third[0] - second[0] * third[2],
                second[0] * third[1] - second[1] * third[0],
            )
            component_volume += sum(first[axis] * cross[axis] for axis in range(3))
        if component_volume == 0:
            raise ValueError("ASCII STL mesh shell must have nonzero signed volume")
        # Aggregate signed volume cannot distinguish a genuine enclosed cavity
        # from a disconnected inward-wound solid. Supporting negative shells
        # safely requires intersection checks and a containment/parity tree, so
        # fail closed until that stronger proof is part of the contract.
        if component_volume < 0:
            raise ValueError(
                "ASCII STL mesh shell must have positive signed volume; "
                "inward-wound disconnected shells are not supported"
            )


def normalize_ascii_stl(path: str | Path, *, solid_name: str) -> None:
    """Sort ASCII STL facets while preserving exact geometry and outward winding."""

    if not STL_NAME.fullmatch(solid_name):
        raise ValueError(f"Unsafe STL solid name: {solid_name!r}")
    target = Path(path)
    if target.stat().st_size > MAX_ASCII_STL_BYTES:
        raise ValueError(f"ASCII STL exceeds size limit: {target}")
    try:
        lines = target.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"ASCII STL could not be read: {target}: {exc}") from exc
    if len(lines) < 2 or not lines[0].strip().startswith("solid "):
        raise ValueError(f"ASCII STL has no solid header: {target}")
    if not lines[-1].strip().startswith("endsolid "):
        raise ValueError(f"ASCII STL has no endsolid footer: {target}")

    facets: list[_Facet] = []
    exact_vertices: dict[_DecimalPoint, _FractionPoint] = {}
    index = 1
    while index < len(lines) - 1:
        if not lines[index].strip():
            index += 1
            continue
        if index + 6 >= len(lines):
            raise ValueError(f"ASCII STL facet is incomplete: {target}")
        normal_values = _decimal_tokens(lines[index], "facet normal", 3)
        if lines[index + 1].strip() != "outer loop":
            raise ValueError(f"Malformed ASCII STL outer loop: {target}")
        vertices = tuple(
            _decimal_tokens(lines[index + offset], "vertex", 3)
            for offset in (2, 3, 4)
        )
        if lines[index + 5].strip() != "endloop" or lines[index + 6].strip() != "endfacet":
            raise ValueError(f"Malformed ASCII STL facet footer: {target}")
        rotations = tuple(vertices[offset:] + vertices[:offset] for offset in range(3))
        facet = _Facet(
            normal=(normal_values[0], normal_values[1], normal_values[2]),
            vertices=min(rotations),
        )
        _validate_facet(facet, exact_vertices)
        facets.append(facet)
        if len(facets) > MAX_ASCII_STL_FACETS:
            raise ValueError(f"ASCII STL exceeds facet limit: {target}")
        index += 7
    if not facets:
        raise ValueError(f"ASCII STL has no facets: {target}")
    _validate_closed_mesh(facets, exact_vertices)

    output = [f"solid {solid_name}"]
    for facet in sorted(facets, key=lambda item: (item.vertices, item.normal)):
        output.append("  facet normal " + " ".join(map(_format_decimal, facet.normal)))
        output.append("    outer loop")
        for vertex in facet.vertices:
            output.append("      vertex " + " ".join(map(_format_decimal, vertex)))
        output.extend(("    endloop", "  endfacet"))
    output.append(f"endsolid {solid_name}")
    target.write_bytes(("\n".join(output) + "\n").encode("ascii"))


def publish_staged_files(pairs: Iterable[tuple[Path, Path]]) -> None:
    """Publish a validated batch and restore every prior target on failure."""

    items = tuple((Path(staged), Path(target)) for staged, target in pairs)
    if not items:
        raise ValueError("No staged artifacts were provided for publication")
    staged_paths = [staged for staged, _ in items]
    target_paths = [target for _, target in items]
    if len(staged_paths) != len(set(staged_paths)):
        raise ValueError("Staged artifact paths must be unique")
    if len(target_paths) != len(set(target_paths)):
        raise ValueError("Publication target paths must be unique")

    def symlink_component(path: Path) -> Path | None:
        absolute = path.absolute()
        current = Path(absolute.anchor)
        for part in absolute.parts[1:]:
            current /= part
            if current.is_symlink():
                return current
        return None

    for staged, target in items:
        if staged == target:
            raise ValueError(f"Staged artifact is also its publication target: {target}")
        if staged.is_symlink() or not staged.is_file() or staged.stat().st_size == 0:
            raise ValueError(f"Staged artifact is missing or empty: {staged}")
        if staged.stat().st_nlink != 1:
            raise ValueError(f"Staged artifact must not be a hardlink: {staged}")
        if target.is_symlink():
            raise ValueError(f"Publication target cannot be a symlink: {target}")
        if target.exists() and target.stat().st_nlink != 1:
            raise ValueError(f"Publication target must not be a hardlink: {target}")
        staged_symlink = symlink_component(staged.parent)
        target_symlink = symlink_component(target.parent)
        if staged_symlink is not None:
            raise ValueError(f"Staged artifact parent uses a symlink: {staged_symlink}")
        if target_symlink is not None:
            raise ValueError(f"Publication target parent uses a symlink: {target_symlink}")
        if not target.parent.is_dir():
            raise ValueError(f"Publication target directory is missing: {target.parent}")
        if staged.stat().st_dev != target.parent.stat().st_dev:
            raise ValueError(f"Staged artifact is not on the target filesystem: {staged}")

    resolved_staged = {path.resolve() for path in staged_paths}
    resolved_targets = {path.resolve(strict=False) for path in target_paths}
    if len(resolved_staged) != len(staged_paths):
        raise ValueError("Staged artifact paths must not alias one another")
    if len(resolved_targets) != len(target_paths):
        raise ValueError("Publication target paths must not alias one another")
    if len({str(path).casefold() for path in resolved_staged}) != len(staged_paths):
        raise ValueError("Staged artifact paths have a case-insensitive alias")
    if len({str(path).casefold() for path in resolved_targets}) != len(target_paths):
        raise ValueError("Publication target paths have a case-insensitive alias")
    if resolved_staged & resolved_targets:
        raise ValueError("Staged artifact paths and publication targets must be disjoint")
    staged_inodes = {
        (path.stat().st_dev, path.stat().st_ino) for path in staged_paths
    }
    existing_targets = [path for path in target_paths if path.exists()]
    target_inodes = {
        (path.stat().st_dev, path.stat().st_ino) for path in existing_targets
    }
    if len(staged_inodes) != len(staged_paths):
        raise ValueError("Staged artifacts must not share an inode")
    if len(target_inodes) != len(existing_targets):
        raise ValueError("Publication targets must not share an inode")
    if staged_inodes & target_inodes:
        raise ValueError("Staged artifacts must not alias publication targets")

    backups: dict[Path, Path | None] = {}
    try:
        for target in target_paths:
            if not target.exists():
                backups[target] = None
                continue
            descriptor, name = tempfile.mkstemp(
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".rollback",
            )
            os.close(descriptor)
            backup = Path(name)
            backups[target] = backup
            shutil.copy2(target, backup)

        published: list[Path] = []
        try:
            for staged, target in items:
                os.replace(staged, target)
                published.append(target)
        except BaseException as publication_error:
            rollback_errors: list[OSError] = []
            for target in reversed(published):
                backup = backups[target]
                try:
                    if backup is None:
                        target.unlink(missing_ok=True)
                    else:
                        os.replace(backup, target)
                        backups[target] = None
                except OSError as exc:  # pragma: no cover - catastrophic filesystem fault
                    # Preserve the backup for manual recovery if the filesystem
                    # refuses the rollback itself.
                    backups[target] = None
                    rollback_errors.append(exc)
            if rollback_errors:
                raise RuntimeError(
                    "Artifact publication failed and rollback was incomplete"
                ) from publication_error
            raise
    finally:
        for backup in backups.values():
            if backup is not None:
                backup.unlink(missing_ok=True)


def _replacement_count(
    pattern: re.Pattern[bytes],
    replacement: bytes,
    payload: bytes,
    *,
    expected: int,
    label: str,
) -> bytes:
    normalized, count = pattern.subn(replacement, payload)
    if count != expected:
        raise ValueError(f"QCAD PDF has {count} {label}; expected {expected}")
    return normalized


def _replace_pdf_field(
    pattern: re.Pattern[bytes],
    value: bytes,
    payload: bytes,
    *,
    label: str,
) -> bytes:
    """Replace exactly one named PDF metadata field, preserving its prefix."""

    normalized, count = pattern.subn(
        lambda match: match.group("prefix") + value,
        payload,
    )
    if count != 1:
        raise ValueError(f"QCAD PDF has {count} {label}; expected 1")
    return normalized


def _validate_classic_pdf_xref(payload: bytes) -> None:
    """Reject truncated, corrupt, or offset-invalid QCAD classic PDFs."""

    active_markers = (
        b"JavaScript",
        b"JS",
        b"OpenAction",
        b"AA",
        b"Launch",
        b"EmbeddedFile",
        b"RichMedia",
        b"XFA",
    )
    for marker in active_markers:
        if re.search(rb"/" + marker + rb"\b", payload):
            raise ValueError(f"QCAD PDF contains forbidden active content: /{marker.decode()}")

    matches = list(PDF_STARTXREF.finditer(payload))
    if len(matches) != 1:
        raise ValueError(f"QCAD PDF has {len(matches)} startxref markers; expected 1")
    xref_offset = int(matches[0].group(1))
    if payload[xref_offset : xref_offset + 4] != b"xref":
        raise ValueError("QCAD PDF startxref does not point to a classic xref table")

    xref_end = payload.find(b"trailer", xref_offset)
    if xref_end < 0:
        raise ValueError("QCAD PDF xref table has no trailer")
    lines = payload[xref_offset:xref_end].splitlines()
    if not lines or lines[0] != b"xref":
        raise ValueError("QCAD PDF xref table is malformed")
    offsets: dict[int, int] = {}
    index = 1
    while index < len(lines):
        subsection = re.fullmatch(rb"(\d+) (\d+)", lines[index].strip())
        if subsection is None:
            raise ValueError("QCAD PDF xref subsection is malformed")
        first_object, count = map(int, subsection.groups())
        index += 1
        if index + count > len(lines):
            raise ValueError("QCAD PDF xref subsection is truncated")
        for offset_index in range(count):
            entry = re.fullmatch(
                rb"(\d{10}) (\d{5}) ([fn])\s*",
                lines[index + offset_index],
            )
            if entry is None:
                raise ValueError("QCAD PDF xref entry is malformed")
            offset, generation, state = entry.groups()
            if state == b"n":
                if generation != b"00000":
                    raise ValueError("QCAD PDF uses an unexpected object generation")
                offsets[first_object + offset_index] = int(offset)
        index += count
    if not offsets:
        raise ValueError("QCAD PDF xref table has no in-use objects")
    ordered_offsets = sorted((*offsets.values(), xref_offset))
    objects: dict[int, bytes] = {}
    for object_number, object_offset in offsets.items():
        header = re.match(
            rb"(\d+)\s+0\s+obj\b",
            payload[object_offset : object_offset + 40],
        )
        if header is None or int(header.group(1)) != object_number:
            raise ValueError("QCAD PDF xref entry does not point to an object")
        next_offset = min(offset for offset in ordered_offsets if offset > object_offset)
        body = payload[object_offset:next_offset]
        if b"endobj" not in body:
            raise ValueError(f"QCAD PDF object {object_number} has no endobj marker")
        objects[object_number] = body

    def indirect_integer(object_number: int, generation: int) -> int:
        if generation != 0 or object_number not in objects:
            raise ValueError("QCAD PDF stream has an invalid indirect length reference")
        match = re.fullmatch(
            rb"\d+\s+0\s+obj\s*(\d+)\s*endobj\s*",
            objects[object_number],
        )
        if match is None:
            raise ValueError("QCAD PDF indirect stream length is not an integer")
        return int(match.group(1))

    decoded_streams: dict[int, bytes] = {}
    total_decoded_bytes = 0
    for object_number, body in objects.items():
        marker = re.search(rb"stream\r?\n", body)
        if marker is None:
            continue
        dictionary = body[: marker.start()]
        length = re.search(
            rb"/Length\s+(?:(\d+)\s+(\d+)\s+R|(\d+))\b",
            dictionary,
        )
        if length is None:
            raise ValueError(f"QCAD PDF stream object {object_number} has no length")
        stream_length = (
            int(length.group(3))
            if length.group(3) is not None
            else indirect_integer(int(length.group(1)), int(length.group(2)))
        )
        stream_start = marker.end()
        stream_end = stream_start + stream_length
        if stream_length > MAX_PDF_STREAM_BYTES:
            raise ValueError(f"QCAD PDF stream object {object_number} exceeds size limit")
        if stream_end > len(body) or not re.match(rb"\r?\nendstream\b", body[stream_end:]):
            raise ValueError(
                f"QCAD PDF stream object {object_number} does not match its declared length"
            )
        stream = body[stream_start:stream_end]
        if b"/Filter" in dictionary:
            if re.search(rb"/Filter\s+/FlateDecode\b", dictionary) is None:
                raise ValueError(f"QCAD PDF stream object {object_number} uses an unknown filter")
            try:
                decompressor = zlib.decompressobj()
                decoded = decompressor.decompress(stream, MAX_PDF_DECODED_BYTES + 1)
            except zlib.error as exc:
                raise ValueError(
                    f"QCAD PDF FlateDecode stream {object_number} is corrupt"
                ) from exc
            if (
                len(decoded) > MAX_PDF_DECODED_BYTES
                or not decompressor.eof
                or decompressor.unconsumed_tail
                or decompressor.unused_data
            ):
                raise ValueError(
                    f"QCAD PDF FlateDecode stream {object_number} exceeds or violates limits"
                )
        else:
            decoded = stream
        if not decoded:
            raise ValueError(f"QCAD PDF stream object {object_number} is empty")
        total_decoded_bytes += len(decoded)
        if total_decoded_bytes > MAX_PDF_TOTAL_DECODED_BYTES:
            raise ValueError("QCAD PDF decoded streams exceed aggregate size limit")
        decoded_streams[object_number] = decoded

    pages = [
        (object_number, body)
        for object_number, body in objects.items()
        if re.search(rb"/Type\s+/Page\b", body)
    ]
    if not pages:
        raise ValueError("QCAD PDF has no page objects")
    for page_number, body in pages:
        contents = re.search(rb"/Contents\s+(\d+)\s+0\s+R\b", body)
        if contents is None or int(contents.group(1)) not in decoded_streams:
            raise ValueError(f"QCAD PDF page {page_number} has no valid content stream")


def normalize_qcad_pdf(path: str | Path, *, epoch: int | None = None) -> None:
    """Replace fixed-width volatile Qt PDF metadata without changing xref offsets."""

    target = Path(path)
    if target.stat().st_size > MAX_PDF_BYTES:
        raise ValueError(f"QCAD PDF exceeds size limit: {target}")
    original = target.read_bytes()
    if not original.startswith(b"%PDF-"):
        raise ValueError(f"QCAD output is not a PDF: {target}")
    _validate_classic_pdf_xref(original)
    source_epoch = source_date_epoch(epoch)
    timestamp = source_timestamp(source_epoch)
    info_date = ("D:" + timestamp.translate(str.maketrans("", "", "-:T")) + "Z").encode()
    xmp_date = (timestamp + "+00:00").encode()
    zero_uuid = b"00000000-0000-0000-0000-000000000000"
    zero_hex = zero_uuid.hex().encode()

    payload = original
    for pattern, label in zip(
        PDF_INFO_DATE_FIELDS,
        ("Info CreationDate", "Info ModDate"),
        strict=True,
    ):
        payload = _replace_pdf_field(pattern, info_date, payload, label=label)
    for pattern, label in zip(
        PDF_XMP_DATE_FIELDS,
        ("XMP CreateDate", "XMP ModifyDate", "XMP MetadataDate"),
        strict=True,
    ):
        payload = _replace_pdf_field(pattern, xmp_date, payload, label=label)
    payload = _replace_pdf_field(
        PDF_XMP_DOCUMENT_ID,
        zero_uuid,
        payload,
        label="XMP DocumentID",
    )
    zero_id = b"/ID [ <" + zero_hex + b"> <" + zero_hex + b"> ]"
    payload = _replacement_count(
        PDF_TRAILER_ID,
        zero_id,
        payload,
        expected=1,
        label="trailer IDs",
    )

    content_digest = hashlib.sha256(payload).hexdigest()
    content_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:sha256:{content_digest}")).encode()
    content_hex = content_uuid.hex().encode()
    payload, xmp_count = PDF_XMP_DOCUMENT_ID.subn(
        lambda match: match.group("prefix") + content_uuid,
        payload,
    )
    if xmp_count != 1:
        raise ValueError(f"QCAD PDF has {xmp_count} normalized XMP IDs; expected 1")
    zero_id_pattern = re.compile(
        rb"/ID\s*\[\s*<" + zero_hex + rb">\s*<" + zero_hex + rb">\s*\]"
    )
    payload, trailer_count = zero_id_pattern.subn(
        b"/ID [ <" + content_hex + b"> <" + content_hex + b"> ]",
        payload,
    )
    if trailer_count != 1:
        raise ValueError(f"QCAD PDF has {trailer_count} normalized trailer IDs; expected 1")
    if len(payload) != len(original):
        raise ValueError("QCAD PDF normalization changed byte offsets")
    _validate_classic_pdf_xref(payload)
    target.write_bytes(payload)
