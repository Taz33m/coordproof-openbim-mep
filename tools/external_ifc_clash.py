"""Run a bounded, deterministic clash set across two external IFC files.

IfcClash delegates its geometric work to the compiled ``ifcopenshell.geom.tree``
API.  This module uses that same API directly so JSON clash evidence works with
the project's existing IfcOpenShell dependency.  BCF 3.0 output is deliberately
optional and is only enabled when the upstream ``bcf-client`` API is importable.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import sys
import tempfile
import uuid
import zipfile
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.guid
from reproducibility import source_date_epoch

REPORT_SCHEMA_VERSION = "1.0"
BCF_NAMESPACE = uuid.UUID("90706dc8-f19f-5ba0-9373-308d83374c5d")

DEFAULT_MAX_FILE_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_ELEMENTS_PER_SIDE = 5_000
DEFAULT_MAX_TRIANGLES_PER_SIDE = 5_000_000
DEFAULT_MAX_CANDIDATE_PAIRS = 10_000_000
DEFAULT_MAX_RESULTS = 10_000

HARD_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
HARD_MAX_ELEMENTS_PER_SIDE = 100_000
HARD_MAX_TRIANGLES_PER_SIDE = 50_000_000
HARD_MAX_CANDIDATE_PAIRS = 100_000_000
HARD_MAX_RESULTS = 100_000
HARD_MAX_WORKERS = 16


class ClashError(RuntimeError):
    """Base class for an expected clash-tool failure."""


class ClashInputError(ClashError):
    """Raised when an IFC input or requested clash set is not usable."""


class ClashLimitError(ClashError):
    """Raised when an input or result crosses an explicit resource bound."""


class ClashCapabilityError(ClashError):
    """Raised when an optional or compiled capability is unavailable."""


class ClashExecutionError(ClashError):
    """Raised when the geometry engine cannot complete the clash set."""


@dataclass(frozen=True)
class ClashLimits:
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_elements_per_side: int = DEFAULT_MAX_ELEMENTS_PER_SIDE
    max_triangles_per_side: int = DEFAULT_MAX_TRIANGLES_PER_SIDE
    max_candidate_pairs: int = DEFAULT_MAX_CANDIDATE_PAIRS
    max_results: int = DEFAULT_MAX_RESULTS
    workers: int = 1

    def validate(self) -> None:
        _bounded_integer("max_file_bytes", self.max_file_bytes, maximum=HARD_MAX_FILE_BYTES)
        _bounded_integer(
            "max_elements_per_side",
            self.max_elements_per_side,
            maximum=HARD_MAX_ELEMENTS_PER_SIDE,
        )
        _bounded_integer(
            "max_triangles_per_side",
            self.max_triangles_per_side,
            maximum=HARD_MAX_TRIANGLES_PER_SIDE,
        )
        _bounded_integer(
            "max_candidate_pairs",
            self.max_candidate_pairs,
            maximum=HARD_MAX_CANDIDATE_PAIRS,
        )
        _bounded_integer("max_results", self.max_results, maximum=HARD_MAX_RESULTS)
        _bounded_integer("workers", self.workers, maximum=HARD_MAX_WORKERS)


@dataclass(frozen=True)
class ClashConfig:
    mode: str = "collision"
    a_label: str = "A"
    b_label: str = "B"
    a_classes: tuple[str, ...] = ("IfcElement",)
    b_classes: tuple[str, ...] = ("IfcElement",)
    tolerance_mm: float = 2.0
    clearance_mm: float = 50.0
    allow_touching: bool = False

    def validate(self) -> None:
        if self.mode not in {"collision", "intersection", "clearance"}:
            raise ClashInputError("mode must be one of: collision, intersection, clearance")
        _validate_label("a_label", self.a_label)
        _validate_label("b_label", self.b_label)
        if self.a_label == self.b_label:
            raise ClashInputError("a_label and b_label must be distinct")
        _validate_classes("a_classes", self.a_classes)
        _validate_classes("b_classes", self.b_classes)
        _finite_non_negative("tolerance_mm", self.tolerance_mm)
        _finite_non_negative("clearance_mm", self.clearance_mm)
        if self.mode == "clearance" and self.clearance_mm <= 0:
            raise ClashInputError("clearance_mm must be greater than zero in clearance mode")


@dataclass
class _LoadedSide:
    label: str
    path: Path
    sha256: str
    size_bytes: int
    model: ifcopenshell.file
    schema: str
    project_global_ids: list[str]
    classes: tuple[str, ...]
    elements: list[Any]
    elements_by_guid: dict[str, Any]
    geometry_guids: set[str]
    triangle_count: int


@dataclass(frozen=True)
class _BcfApi:
    version: str
    BcfXml: Any
    model: Any
    XmlDateTime: Any
    numpy: Any


def _bounded_integer(name: str, value: int, *, maximum: int) -> None:
    if type(value) is not int or value <= 0 or value > maximum:
        raise ClashLimitError(f"{name} must be an integer between 1 and {maximum}")


def _finite_non_negative(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ClashInputError(f"{name} must be a finite non-negative number")
    if not math.isfinite(float(value)) or value < 0:
        raise ClashInputError(f"{name} must be a finite non-negative number")


def _validate_classes(name: str, classes: tuple[str, ...]) -> None:
    if not classes:
        raise ClashInputError(f"{name} must contain at least one IFC class")
    for ifc_class in classes:
        if (
            not isinstance(ifc_class, str)
            or not ifc_class.startswith("Ifc")
            or not ifc_class.isascii()
            or not ifc_class.isalnum()
        ):
            raise ClashInputError(f"{name} contains an invalid IFC class: {ifc_class!r}")


def _validate_label(name: str, label: str) -> None:
    if (
        not isinstance(label, str)
        or not label.strip()
        or len(label) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in label)
    ):
        raise ClashInputError(
            f"{name} must be a non-empty label of at most 128 characters without controls"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _preflight_path(path: Path, label: str, limits: ClashLimits) -> tuple[Path, int, str]:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ClashInputError(f"side {label} IFC does not exist or cannot be resolved") from exc
    if not resolved.is_file():
        raise ClashInputError(f"side {label} IFC must be a regular file")
    if resolved.suffix.lower() != ".ifc":
        raise ClashInputError(f"side {label} input must be an uncompressed .ifc STEP file")
    size = resolved.stat().st_size
    if size <= 0:
        raise ClashInputError(f"side {label} IFC is empty")
    if size > limits.max_file_bytes:
        raise ClashLimitError(
            f"side {label} IFC is {size} bytes; limit is {limits.max_file_bytes} bytes"
        )
    return resolved, size, _sha256(resolved)


def _select_elements(
    model: ifcopenshell.file,
    classes: tuple[str, ...],
    label: str,
    limits: ClashLimits,
) -> tuple[list[Any], dict[str, Any]]:
    by_step_id: dict[int, Any] = {}
    for ifc_class in classes:
        try:
            candidates = model.by_type(ifc_class)
        except RuntimeError as exc:
            raise ClashInputError(
                f"side {label} schema {model.schema} does not define {ifc_class}"
            ) from exc
        for element in candidates:
            if not element.is_a("IfcProduct") or element.is_a("IfcFeatureElement"):
                continue
            by_step_id[element.id()] = element

    if not by_step_id:
        joined = ", ".join(classes)
        raise ClashInputError(f"side {label} has no selected products for classes: {joined}")
    if len(by_step_id) > limits.max_elements_per_side:
        raise ClashLimitError(
            f"side {label} selected {len(by_step_id)} products; limit is "
            f"{limits.max_elements_per_side}"
        )

    by_guid: dict[str, Any] = {}
    for element in by_step_id.values():
        global_id = getattr(element, "GlobalId", None)
        if not isinstance(global_id, str):
            raise ClashInputError(
                f"side {label} selected {element.is_a()} #{element.id()} without a GlobalId"
            )
        try:
            ifcopenshell.guid.expand(global_id)
        except (ValueError, TypeError) as exc:
            raise ClashInputError(
                f"side {label} selected {element.is_a()} #{element.id()} with an invalid GlobalId"
            ) from exc
        if global_id in by_guid:
            raise ClashInputError(f"side {label} contains duplicate selected GlobalId {global_id}")
        by_guid[global_id] = element

    elements = sorted(by_guid.values(), key=lambda item: (item.GlobalId, item.id()))
    return elements, by_guid


def _load_side(
    raw_path: str | Path,
    label: str,
    classes: tuple[str, ...],
    limits: ClashLimits,
) -> _LoadedSide:
    path, size, digest = _preflight_path(Path(raw_path), label, limits)
    try:
        model = ifcopenshell.open(str(path))
    except Exception as exc:
        raise ClashInputError(f"side {label} is not a readable IFC STEP file") from exc
    if not isinstance(model, ifcopenshell.file):
        raise ClashInputError(f"side {label} did not load as an IFC model")
    elements, by_guid = _select_elements(model, classes, label, limits)
    project_ids = sorted(
        project.GlobalId
        for project in model.by_type("IfcProject")
        if isinstance(getattr(project, "GlobalId", None), str)
    )
    return _LoadedSide(
        label=label,
        path=path,
        sha256=digest,
        size_bytes=size,
        model=model,
        schema=model.schema,
        project_global_ids=project_ids,
        classes=classes,
        elements=elements,
        elements_by_guid=by_guid,
        geometry_guids=set(),
        triangle_count=0,
    )


def _require_geometry_api() -> None:
    tree_type = getattr(ifcopenshell.geom, "tree", None)
    iterator_type = getattr(ifcopenshell.geom, "iterator", None)
    required = (
        "add_element",
        "clash_collision_many",
        "clash_intersection_many",
        "clash_clearance_many",
        "get_clash_type",
    )
    if (
        tree_type is None
        or iterator_type is None
        or any(not hasattr(tree_type, name) for name in required)
    ):
        raise ClashCapabilityError(
            "this IfcOpenShell build does not expose the compiled IfcClash geometry-tree API"
        )


def _add_side_to_tree(
    tree: Any,
    side: _LoadedSide,
    settings: Any,
    limits: ClashLimits,
) -> None:
    try:
        iterator = ifcopenshell.geom.iterator(
            settings,
            side.model,
            limits.workers,
            include=set(side.elements),
        )
        initialized = iterator.initialize()
        if initialized:
            while True:
                shape = iterator.get()
                tree.add_element(shape)
                side.triangle_count += len(shape.geometry.faces) // 3
                if side.triangle_count > limits.max_triangles_per_side:
                    raise ClashLimitError(
                        f"side {side.label} tessellated to more than "
                        f"{limits.max_triangles_per_side} triangles"
                    )
                if shape.guid in side.elements_by_guid:
                    side.geometry_guids.add(shape.guid)
                if not iterator.next():
                    break
    except ClashError:
        raise
    except Exception as exc:
        raise ClashExecutionError(f"IfcOpenShell could not tessellate side {side.label}") from exc
    if not side.geometry_guids:
        raise ClashInputError(f"side {side.label} has no selected products with clashable geometry")


def _geometry_elements(side: _LoadedSide) -> list[Any]:
    return [
        side.elements_by_guid[guid]
        for guid in sorted(side.geometry_guids)
        if guid in side.elements_by_guid
    ]


def _millimetres(value_metres: float) -> float:
    value = float(value_metres) * 1000.0
    if not math.isfinite(value):
        raise ClashExecutionError("IfcOpenShell returned a non-finite clash coordinate")
    rounded = round(value, 6)
    return 0.0 if rounded == 0 else rounded


def _point_mm(raw: Any) -> list[float]:
    values = list(raw)
    if len(values) != 3:
        raise ClashExecutionError("IfcOpenShell returned a malformed clash point")
    return [_millimetres(value) for value in values]


def _argument(entity: Any, index: int) -> Any:
    try:
        return entity.get_argument(index)
    except Exception as exc:
        raise ClashExecutionError("IfcOpenShell returned malformed clash metadata") from exc


def _normalise_native_result(
    native: Any,
    tree: Any,
    side_a: _LoadedSide,
    side_b: _LoadedSide,
) -> dict[str, Any]:
    first_guid = _argument(native.a, 0)
    second_guid = _argument(native.b, 0)
    first_point = _point_mm(native.p1)
    second_point = _point_mm(native.p2)
    if first_guid in side_a.elements_by_guid and second_guid in side_b.elements_by_guid:
        a_guid, b_guid = first_guid, second_guid
        point_a, point_b = first_point, second_point
    elif first_guid in side_b.elements_by_guid and second_guid in side_a.elements_by_guid:
        a_guid, b_guid = second_guid, first_guid
        point_a, point_b = second_point, first_point
    else:
        raise ClashExecutionError(
            "IfcOpenShell returned a clash outside the requested A/B element sets"
        )

    a_element = side_a.elements_by_guid[a_guid]
    b_element = side_b.elements_by_guid[b_guid]
    distance_mm = _millimetres(native.distance)
    try:
        clash_type = tree.get_clash_type(native.clash_type)
    except Exception as exc:
        raise ClashExecutionError("IfcOpenShell returned an unknown clash type") from exc
    return {
        "a": {
            "global_id": a_guid,
            "ifc_class": a_element.is_a(),
            "name": getattr(a_element, "Name", None),
        },
        "b": {
            "global_id": b_guid,
            "ifc_class": b_element.is_a(),
            "name": getattr(b_element, "Name", None),
        },
        "clash_type": clash_type,
        "distance_mm": distance_mm,
        "point_a_mm": point_a,
        "point_b_mm": point_b,
    }


def _result_rank(result: dict[str, Any], mode: str) -> tuple[Any, ...]:
    distance = result["distance_mm"]
    metric_rank = -distance if mode == "intersection" else distance
    return (
        result["a"]["global_id"],
        result["b"]["global_id"],
        metric_rank,
        result["clash_type"],
        tuple(result["point_a_mm"]),
        tuple(result["point_b_mm"]),
    )


def _clash_id(
    result: dict[str, Any],
    side_a: _LoadedSide,
    side_b: _LoadedSide,
    config: ClashConfig,
) -> str:
    payload = {
        "a_global_id": result["a"]["global_id"],
        "a_sha256": side_a.sha256,
        "b_global_id": result["b"]["global_id"],
        "b_sha256": side_b.sha256,
        "mode": config.mode,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii")
    return f"clash-{hashlib.sha256(encoded).hexdigest()[:32]}"


def _mode_parameters(config: ClashConfig) -> dict[str, Any]:
    if config.mode == "intersection":
        return {"check_all": True, "tolerance_mm": float(config.tolerance_mm)}
    if config.mode == "clearance":
        return {"check_all": True, "clearance_mm": float(config.clearance_mm)}
    return {"allow_touching": config.allow_touching}


def _run_native_batch(
    tree: Any,
    a_elements: list[Any],
    b_elements: list[Any],
    config: ClashConfig,
) -> tuple[Any, ...]:
    try:
        if config.mode == "intersection":
            return tree.clash_intersection_many(
                a_elements,
                b_elements,
                tolerance=float(config.tolerance_mm) / 1000.0,
                check_all=True,
            )
        if config.mode == "clearance":
            return tree.clash_clearance_many(
                a_elements,
                b_elements,
                clearance=float(config.clearance_mm) / 1000.0,
                check_all=True,
            )
        return tree.clash_collision_many(
            a_elements,
            b_elements,
            allow_touching=config.allow_touching,
        )
    except Exception as exc:
        raise ClashExecutionError("IfcOpenShell clash execution failed") from exc


def _run_native_clash(
    tree: Any,
    a_elements: list[Any],
    b_elements: list[Any],
    config: ClashConfig,
    limits: ClashLimits,
) -> tuple[Any, ...]:
    # The compiled API returns all results for a call and has no result-limit
    # argument. Keep each native allocation bounded by querying A in batches
    # whose worst-case Cartesian product cannot exceed max_results.
    if len(b_elements) <= limits.max_results:
        a_batch_size = max(1, limits.max_results // len(b_elements))
        b_batch_size = len(b_elements)
    else:
        a_batch_size = 1
        b_batch_size = limits.max_results
    collected: list[Any] = []
    for a_offset in range(0, len(a_elements), a_batch_size):
        a_batch = a_elements[a_offset : a_offset + a_batch_size]
        for b_offset in range(0, len(b_elements), b_batch_size):
            b_batch = b_elements[b_offset : b_offset + b_batch_size]
            batch_results = _run_native_batch(tree, a_batch, b_batch, config)
            observed = len(collected) + len(batch_results)
            if observed > limits.max_results:
                raise ClashLimitError(
                    f"IfcOpenShell returned at least {observed} native clashes; limit is "
                    f"{limits.max_results}; no truncated report was written"
                )
            collected.extend(batch_results)
    return tuple(collected)


def _side_report(side: _LoadedSide) -> dict[str, Any]:
    return {
        "label": side.label,
        "sha256": side.sha256,
        "size_bytes": side.size_bytes,
        "ifc_schema": side.schema,
        "project_global_ids": side.project_global_ids,
        "selected_classes": list(side.classes),
        "selected_element_count": len(side.elements),
        "geometry_element_count": len(side.geometry_guids),
        "triangle_count": side.triangle_count,
        "skipped_without_geometry_count": len(side.elements) - len(side.geometry_guids),
    }


def _verify_side_unchanged(side: _LoadedSide) -> None:
    try:
        current_size = side.path.stat().st_size
        current_digest = _sha256(side.path)
    except OSError as exc:
        raise ClashInputError(
            f"side {side.label} IFC became unreadable during clash execution"
        ) from exc
    if current_size != side.size_bytes or current_digest != side.sha256:
        raise ClashInputError(
            f"side {side.label} IFC changed during clash execution; results were discarded"
        )


def run_external_clash(
    a_ifc: str | Path,
    b_ifc: str | Path,
    *,
    config: ClashConfig | None = None,
    limits: ClashLimits | None = None,
) -> dict[str, Any]:
    """Execute one bounded A-vs-B clash set and return canonical report data."""

    config = config or ClashConfig()
    limits = limits or ClashLimits()
    config.validate()
    limits.validate()
    _require_geometry_api()

    side_a = _load_side(a_ifc, config.a_label, config.a_classes, limits)
    side_b = _load_side(b_ifc, config.b_label, config.b_classes, limits)
    if side_a.path == side_b.path or side_a.sha256 == side_b.sha256:
        raise ClashInputError(
            "A and B must be distinct IFC models; intra-model clash is not supported"
        )

    shared_guids = sorted(set(side_a.elements_by_guid) & set(side_b.elements_by_guid))
    if shared_guids:
        raise ClashInputError(
            "A and B selected sets share GlobalIds, so deterministic side attribution is "
            f"ambiguous (first: {shared_guids[0]})"
        )

    selected_pairs = len(side_a.elements) * len(side_b.elements)
    if selected_pairs > limits.max_candidate_pairs:
        raise ClashLimitError(
            f"selected A/B sets imply {selected_pairs} candidate pairs; limit is "
            f"{limits.max_candidate_pairs}"
        )

    settings = ifcopenshell.geom.settings()
    tree = ifcopenshell.geom.tree()
    _add_side_to_tree(tree, side_a, settings, limits)
    _add_side_to_tree(tree, side_b, settings, limits)
    a_geometry = _geometry_elements(side_a)
    b_geometry = _geometry_elements(side_b)
    geometry_pairs = len(a_geometry) * len(b_geometry)

    native_results = _run_native_clash(tree, a_geometry, b_geometry, config, limits)
    native_count = len(native_results)
    if native_count > limits.max_results:
        raise ClashLimitError(
            f"IfcOpenShell returned {native_count} native clashes; limit is "
            f"{limits.max_results}; no truncated report was written"
        )

    normalised = [
        _normalise_native_result(result, tree, side_a, side_b) for result in native_results
    ]
    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
    for result in sorted(normalised, key=lambda item: _result_rank(item, config.mode)):
        pair = (result["a"]["global_id"], result["b"]["global_id"])
        deduplicated.setdefault(pair, result)

    clashes = list(deduplicated.values())
    for result in clashes:
        result["clash_id"] = _clash_id(result, side_a, side_b, config)
    clashes.sort(key=lambda item: item["clash_id"])
    _verify_side_unchanged(side_a)
    _verify_side_unchanged(side_b)

    try:
        ifcopenshell_version = importlib.metadata.version("ifcopenshell")
    except importlib.metadata.PackageNotFoundError:
        ifcopenshell_version = "unknown"
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generator": {
            "name": "coordproof.external_ifc_clash",
            "backend": "ifcopenshell.geom.tree",
            "ifcopenshell_version": ifcopenshell_version,
        },
        "configuration": {
            "mode": config.mode,
            "parameters": _mode_parameters(config),
        },
        "inputs": [_side_report(side_a), _side_report(side_b)],
        "limits": {
            "max_file_bytes": limits.max_file_bytes,
            "max_elements_per_side": limits.max_elements_per_side,
            "max_triangles_per_side": limits.max_triangles_per_side,
            "max_candidate_pairs": limits.max_candidate_pairs,
            "max_results": limits.max_results,
            "workers": limits.workers,
        },
        "summary": {
            "status": "clashes_found" if clashes else "clear",
            "clash_count": len(clashes),
            "native_result_count": native_count,
            "selected_candidate_pair_count": selected_pairs,
            "geometry_candidate_pair_count": geometry_pairs,
        },
        "clashes": clashes,
    }


def canonical_json_bytes(report: dict[str, Any]) -> bytes:
    """Serialize clash evidence without timestamps, paths, NaN, or key-order drift."""

    return (
        json.dumps(
            report,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json_report(report: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    if output.suffix.lower() != ".json":
        raise ClashInputError("machine-readable clash output must use a .json suffix")
    _atomic_write(output, canonical_json_bytes(report))


def preflight_output_paths(
    json_path: str | Path,
    bcf_path: str | Path | None = None,
) -> tuple[Path, Path | None]:
    """Validate requested report destinations before expensive tessellation."""

    json_output = Path(json_path)
    if json_output.suffix.lower() != ".json":
        raise ClashInputError("machine-readable clash output must use a .json suffix")
    bcf_output = Path(bcf_path) if bcf_path is not None else None
    if bcf_output is not None and bcf_output.suffix.lower() not in {".bcf", ".bcfzip"}:
        raise ClashInputError("BCF output must use a .bcf or .bcfzip suffix")

    for output in (json_output, bcf_output):
        if output is None:
            continue
        if output.is_symlink():
            raise ClashInputError(f"refusing to replace a symlinked report: {output}")
        if output.exists() and not output.is_file():
            raise ClashInputError(f"report destination is not a regular file: {output}")
    return json_output, bcf_output


def _load_bcf_api() -> _BcfApi:
    try:
        version = importlib.metadata.version("bcf-client")
        import numpy
        from bcf.v3 import model
        from bcf.v3.bcfxml import BcfXml
        from xsdata.models.datatype import XmlDateTime
    except Exception as exc:
        raise ClashCapabilityError(
            "BCF output requires a working optional upstream package bcf-client>=0.8,<0.9"
        ) from exc
    if not version.startswith("0.8."):
        raise ClashCapabilityError(f"BCF output supports bcf-client 0.8.x; found {version}")
    return _BcfApi(
        version=version,
        BcfXml=BcfXml,
        model=model,
        XmlDateTime=XmlDateTime,
        numpy=numpy,
    )


def bcf_available() -> bool:
    """Return whether the tested optional BCF 3.0 writer API is importable."""

    try:
        _load_bcf_api()
    except ClashCapabilityError:
        return False
    return True


def _stable_uuid(value: str) -> str:
    return str(uuid.uuid5(BCF_NAMESPACE, value))


def _normalise_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as source:
        if len(source.namelist()) != len(set(source.namelist())):
            raise ClashExecutionError("BCF writer produced duplicate archive members")
        members = [(name, source.read(name)) for name in sorted(source.namelist())]

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".zip", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as destination:
            for name, payload in members:
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 0
                info.external_attr = 0
                destination.writestr(info, payload, compresslevel=9)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_bcf(path: Path, expected_topics: int, api: _BcfApi) -> None:
    loaded = None
    try:
        loaded = api.BcfXml.load(path)
        if loaded is None or loaded.version.version_id != "3.0":
            raise ClashExecutionError("BCF round-trip did not produce a BCF 3.0 package")
        if len(loaded.topics) != expected_topics:
            raise ClashExecutionError("BCF round-trip topic count does not match clashes")
        for topic in loaded.topics.values():
            if len(topic.viewpoints) != 1:
                raise ClashExecutionError("BCF topic does not contain exactly one viewpoint")
            viewpoint = next(iter(topic.viewpoints.values()))
            selected = viewpoint.get_selected_guids()
            if selected is None or len(selected) != 2:
                raise ClashExecutionError("BCF viewpoint does not select both clash elements")
    except ClashExecutionError:
        raise
    except Exception as exc:
        raise ClashExecutionError("the generated BCF package failed an API round-trip") from exc
    finally:
        if loaded is not None:
            loaded.close()


def write_bcf_report(report: dict[str, Any], path: str | Path) -> None:
    """Write deterministic BCF 3.0 topics using the optional upstream BCF API."""

    output = Path(path)
    if output.suffix.lower() not in {".bcf", ".bcfzip"}:
        raise ClashInputError("BCF output must use a .bcf or .bcfzip suffix")
    api = _load_bcf_api()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        epoch = source_date_epoch()
    except ValueError as exc:
        raise ClashInputError(str(exc)) from exc
    timestamp = datetime.fromtimestamp(epoch, tz=UTC)
    creation_date = api.XmlDateTime.from_datetime(timestamp)
    extensions = api.model.Extensions(
        topic_types=api.model.ExtensionsTopicTypes(topic_type=["Clash"]),
        topic_statuses=api.model.ExtensionsTopicStatuses(topic_status=["Open"]),
        users=api.model.ExtensionsUsers(user=["coordproof@openbim.invalid"]),
    )
    bcf_xml = api.BcfXml.create_new(
        "CoordProof External IFC Clash",
        extensions=extensions,
    )
    report_digest = hashlib.sha256(canonical_json_bytes(report)).hexdigest()
    if bcf_xml.project is None:
        raise ClashExecutionError("BCF API did not create project metadata")
    bcf_xml.project.project_id = _stable_uuid(f"project:{report_digest}")

    for clash in report["clashes"]:
        a_item = clash["a"]
        b_item = clash["b"]
        a_name = a_item["name"] or "Unnamed"
        b_name = b_item["name"] or "Unnamed"
        title = f"{a_item['ifc_class']}/{a_name} vs {b_item['ifc_class']}/{b_name}"
        description = (
            f"CoordProof clash {clash['clash_id']}; A={a_item['global_id']}; "
            f"B={b_item['global_id']}; type={clash['clash_type']}; "
            f"distance_mm={clash['distance_mm']}"
        )
        topic = bcf_xml.add_topic(
            title,
            description,
            "coordproof@openbim.invalid",
            topic_type="Clash",
            topic_status="Open",
        )
        old_topic_guid = topic.guid
        topic_guid = _stable_uuid(f"topic:{clash['clash_id']}")
        topic.topic.guid = topic_guid
        topic.topic.creation_date = creation_date
        topic._topic_dir = Path(topic_guid)
        bcf_xml.topics[topic_guid] = bcf_xml.topics.pop(old_topic_guid)

        point_a = clash["point_a_mm"]
        point_b = clash["point_b_mm"]
        midpoint_metres = api.numpy.array(
            [(float(point_a[index]) + float(point_b[index])) / 2000.0 for index in range(3)],
            dtype=float,
        )
        viewpoint = topic.add_viewpoint_from_point_and_guids(
            midpoint_metres,
            a_item["global_id"],
            b_item["global_id"],
        )
        old_viewpoint_guid = viewpoint.guid
        old_viewpoint_name = f"{old_viewpoint_guid}.bcfv"
        viewpoint_guid = _stable_uuid(f"viewpoint:{clash['clash_id']}")
        viewpoint.visualization_info.guid = viewpoint_guid
        new_viewpoint_name = f"{viewpoint_guid}.bcfv"
        topic.viewpoints[new_viewpoint_name] = topic.viewpoints.pop(old_viewpoint_name)
        markup_viewpoint = topic.topic.viewpoints.view_point[-1]
        markup_viewpoint.guid = viewpoint_guid
        markup_viewpoint.viewpoint = new_viewpoint_name

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=output.suffix, dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink(missing_ok=True)
    try:
        bcf_xml.save(temporary)
        bcf_xml.close()
        _normalise_zip(temporary)
        _validate_bcf(temporary, len(report["clashes"]), api)
        os.replace(temporary, output)
    except ClashError:
        raise
    except Exception as exc:
        raise ClashExecutionError("BCF 3.0 export failed") from exc
    finally:
        bcf_xml.close()
        temporary.unlink(missing_ok=True)


def write_reports(
    report: dict[str, Any],
    json_path: str | Path,
    bcf_path: str | Path | None = None,
) -> None:
    """Stage all requested representations before publishing either one."""

    json_output, bcf_output = preflight_output_paths(json_path, bcf_path)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    if bcf_output is not None:
        bcf_output.parent.mkdir(parents=True, exist_ok=True)

    with ExitStack() as stack:
        json_stage = Path(
            stack.enter_context(
                tempfile.TemporaryDirectory(
                    prefix=f".{json_output.name}.stage-",
                    dir=json_output.parent,
                )
            )
        ) / json_output.name
        write_json_report(report, json_stage)

        bcf_stage: Path | None = None
        if bcf_output is not None:
            bcf_stage = Path(
                stack.enter_context(
                    tempfile.TemporaryDirectory(
                        prefix=f".{bcf_output.name}.stage-",
                        dir=bcf_output.parent,
                    )
                )
            ) / bcf_output.name
            write_bcf_report(report, bcf_stage)

        # Recheck destinations after potentially long BCF generation. Both
        # requested representations are now complete before either is visible.
        preflight_output_paths(json_output, bcf_output)
        os.replace(json_stage, json_output)
        if bcf_output is not None and bcf_stage is not None:
            os.replace(bcf_stage, bcf_output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a bounded A-vs-B clash set using IfcOpenShell geometry.",
    )
    parser.add_argument("a_ifc", help="side A uncompressed IFC STEP file")
    parser.add_argument("b_ifc", help="side B uncompressed IFC STEP file")
    parser.add_argument("--output", required=True, help="deterministic JSON report path")
    parser.add_argument("--bcf", help="optional BCF 3.0 .bcf/.bcfzip issue package")
    parser.add_argument("--a-label", default="A", help="stable logical label for side A")
    parser.add_argument("--b-label", default="B", help="stable logical label for side B")
    parser.add_argument(
        "--mode",
        choices=("collision", "intersection", "clearance"),
        default="collision",
    )
    parser.add_argument(
        "--a-class",
        action="append",
        dest="a_classes",
        help="IFC product class for side A; repeat to form a union (default: IfcElement)",
    )
    parser.add_argument(
        "--b-class",
        action="append",
        dest="b_classes",
        help="IFC product class for side B; repeat to form a union (default: IfcElement)",
    )
    parser.add_argument("--tolerance-mm", type=float, default=2.0)
    parser.add_argument("--clearance-mm", type=float, default=50.0)
    parser.add_argument("--allow-touching", action="store_true")
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--max-elements-per-side", type=int, default=DEFAULT_MAX_ELEMENTS_PER_SIDE)
    parser.add_argument(
        "--max-triangles-per-side", type=int, default=DEFAULT_MAX_TRIANGLES_PER_SIDE
    )
    parser.add_argument("--max-candidate-pairs", type=int, default=DEFAULT_MAX_CANDIDATE_PAIRS)
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--fail-on-clash",
        action="store_true",
        help="return exit status 1 when the report contains one or more clashes",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        preflight_output_paths(args.output, args.bcf)
        if args.bcf:
            _load_bcf_api()
        config = ClashConfig(
            mode=args.mode,
            a_label=args.a_label,
            b_label=args.b_label,
            a_classes=tuple(args.a_classes or ("IfcElement",)),
            b_classes=tuple(args.b_classes or ("IfcElement",)),
            tolerance_mm=args.tolerance_mm,
            clearance_mm=args.clearance_mm,
            allow_touching=args.allow_touching,
        )
        limits = ClashLimits(
            max_file_bytes=args.max_file_bytes,
            max_elements_per_side=args.max_elements_per_side,
            max_triangles_per_side=args.max_triangles_per_side,
            max_candidate_pairs=args.max_candidate_pairs,
            max_results=args.max_results,
            workers=args.workers,
        )
        report = run_external_clash(
            args.a_ifc,
            args.b_ifc,
            config=config,
            limits=limits,
        )
        write_reports(report, args.output, args.bcf)
    except ClashError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    count = report["summary"]["clash_count"]
    print(f"External IFC clash complete: {count} clash(es); wrote {args.output}")
    if args.fail_on_clash and count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
