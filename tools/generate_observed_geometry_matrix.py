"""Measure committed geometry and reconcile it with the authoritative ProjectSpec.

The matrix deliberately observes file geometry rather than trusting embedded
property-set or annotation values. It is a bounding-envelope parity gate, not a
topology, fabrication, or engineering-compliance certification.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import struct
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import ezdxf
import ifcopenshell

ROOT = Path(__file__).resolve().parents[1]
CADQUERY_DIR = ROOT / "cadquery"
if str(CADQUERY_DIR) not in sys.path:
    sys.path.insert(0, str(CADQUERY_DIR))

from generate_all import ASSET_BINDINGS  # noqa: E402
from project_spec import (  # noqa: E402
    DEFAULT_PROJECT_SPEC_PATH,
    OccurrenceSpec,
    ProjectSpec,
    load_project_spec,
)

DEFAULT_IFC_PATH = ROOT / "bim" / "mechanical_room.ifc"
DEFAULT_CSV_PATH = ROOT / "reports" / "observed_geometry_matrix.csv"
DEFAULT_MARKDOWN_PATH = ROOT / "reports" / "observed_geometry_matrix.md"
CANONICAL_PROJECT_ID = "coordproof_mechanical_room"
MAX_STL_BYTES = 64 * 1024 * 1024
MAX_STL_FACETS = 1_000_000
MAX_ASCII_NUMBER_CHARS = 128

FIELDNAMES = [
    "subject_kind",
    "type_id",
    "occurrence_id",
    "format",
    "artifact_path",
    "expected_source",
    "expected_min_x_mm",
    "expected_min_y_mm",
    "expected_min_z_mm",
    "expected_max_x_mm",
    "expected_max_y_mm",
    "expected_max_z_mm",
    "observed_min_x_mm",
    "observed_min_y_mm",
    "observed_min_z_mm",
    "observed_max_x_mm",
    "observed_max_y_mm",
    "observed_max_z_mm",
    "tolerance_mm",
    "max_delta_mm",
    "status",
    "diagnostic",
]

DXF_BOX_OBSERVATIONS = (
    ("slab_concrete_base_001", "A-WALL"),
    ("equipment_ahu_001", "M-EQUIP"),
    ("clearance_ahu_service_zone_001", "CLEARANCE"),
    ("equipment_pump_skid_001", "M-EQUIP"),
    ("duct_main_001", "M-DUCT"),
    ("duct_branch_001", "M-DUCT"),
    ("cable_tray_overhead_001", "E-CABLETRAY"),
)


@dataclass(frozen=True)
class Bounds:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def __post_init__(self) -> None:
        values = self.values
        if not all(math.isfinite(value) for value in values):
            raise ValueError("geometry bounds must be finite")
        if self.min_x > self.max_x or self.min_y > self.max_y or self.min_z > self.max_z:
            raise ValueError("geometry bounds are inverted")

    @property
    def values(self) -> tuple[float, float, float, float, float, float]:
        return (
            self.min_x,
            self.min_y,
            self.min_z,
            self.max_x,
            self.max_y,
            self.max_z,
        )

    @property
    def lengths(self) -> tuple[float, float, float]:
        return (
            self.max_x - self.min_x,
            self.max_y - self.min_y,
            self.max_z - self.min_z,
        )


def _safe_repo_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError(f"artifact path escapes repository root: {relative!r}")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"artifact is not a regular file: {relative}")
    return path


def _unit(vector: Iterable[float]) -> tuple[float, float, float]:
    values = tuple(float(value) for value in vector)
    if len(values) != 3 or not all(math.isfinite(value) for value in values):
        raise ValueError("direction must contain three finite values")
    magnitude = math.sqrt(sum(value * value for value in values))
    if magnitude <= 1.0e-12:
        raise ValueError("direction cannot be zero")
    return tuple(value / magnitude for value in values)


def _add(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> tuple[float, float, float]:
    return tuple(a + b for a, b in zip(left, right, strict=True))


def _scale(vector: tuple[float, float, float], factor: float) -> tuple[float, float, float]:
    return tuple(value * factor for value in vector)


def _cross(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _perpendicular_reference(axis: tuple[float, float, float]) -> tuple[float, float, float]:
    normalized = _unit(axis)
    candidate = (0.0, 1.0, 0.0) if abs(normalized[0]) > 0.9 else (1.0, 0.0, 0.0)
    projection = sum(a * b for a, b in zip(candidate, normalized, strict=True))
    return _unit(tuple(a - projection * b for a, b in zip(candidate, normalized, strict=True)))


def occurrence_bounds(occurrence: OccurrenceSpec) -> Bounds:
    origin = tuple(float(value) for value in occurrence.origin_mm)
    if occurrence.geometry == "box":
        length, width, height = (float(value) for value in occurrence.dimensions_mm)
        return Bounds(
            origin[0],
            origin[1],
            origin[2],
            origin[0] + length,
            origin[1] + width,
            origin[2] + height,
        )

    radius, depth = (float(value) for value in occurrence.dimensions_mm)
    axis = _unit(occurrence.extrusion_axis)
    end = _add(origin, _scale(axis, depth))
    radial = tuple(radius * math.sqrt(max(0.0, 1.0 - component * component)) for component in axis)
    minimum = tuple(min(a, b) - r for a, b, r in zip(origin, end, radial, strict=True))
    maximum = tuple(max(a, b) + r for a, b, r in zip(origin, end, radial, strict=True))
    return Bounds(*minimum, *maximum)


def _ifc_position(entity) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    location = tuple(float(value) for value in entity.Location.Coordinates)
    if len(location) == 2:
        location = (*location, 0.0)
    axis = _unit(entity.Axis.DirectionRatios) if getattr(entity, "Axis", None) else (0.0, 0.0, 1.0)
    reference = (
        _unit(entity.RefDirection.DirectionRatios)
        if getattr(entity, "RefDirection", None)
        else _perpendicular_reference(axis)
    )
    return location, axis, reference


def _ifc_product_origin(product) -> tuple[float, float, float]:
    placement = product.ObjectPlacement
    if placement is None or not placement.is_a("IfcLocalPlacement"):
        raise ValueError("product has no supported IfcLocalPlacement")
    if placement.PlacementRelTo is not None:
        raise ValueError("relative IFC placements are outside the v1 observation adapter")
    location, axis, reference = _ifc_position(placement.RelativePlacement)
    if any(abs(a - b) > 1.0e-9 for a, b in zip(axis, (0.0, 0.0, 1.0), strict=True)):
        raise ValueError("rotated product placements are outside the v1 observation adapter")
    if any(abs(a - b) > 1.0e-9 for a, b in zip(reference, (1.0, 0.0, 0.0), strict=True)):
        raise ValueError("rotated product placements are outside the v1 observation adapter")
    return location


def _single_ifc_solid(product):
    representation = product.Representation
    if representation is None:
        raise ValueError("IFC product has no representation")
    items = [
        item
        for shape in representation.Representations
        if shape.RepresentationIdentifier == "Body"
        for item in shape.Items
    ]
    if len(items) != 1 or not items[0].is_a("IfcExtrudedAreaSolid"):
        raise ValueError("IFC v1 adapter requires one Body IfcExtrudedAreaSolid")
    return items[0]


def ifc_product_bounds(product) -> Bounds:
    product_origin = _ifc_product_origin(product)
    solid = _single_ifc_solid(product)
    solid_origin, axis, reference = _ifc_position(solid.Position)
    center = _add(product_origin, solid_origin)
    depth = float(solid.Depth)
    profile = solid.SweptArea

    if profile.is_a("IfcRectangleProfileDef"):
        x_axis = reference
        y_axis = _unit(_cross(axis, x_axis))
        half_x = float(profile.XDim) / 2
        half_y = float(profile.YDim) / 2
        start = center
        end = _add(center, _scale(axis, depth))
        radius = tuple(
            abs(x_axis[index]) * half_x + abs(y_axis[index]) * half_y
            for index in range(3)
        )
    elif profile.is_a("IfcCircleProfileDef"):
        start = center
        end = _add(center, _scale(axis, depth))
        profile_radius = float(profile.Radius)
        radius = tuple(
            profile_radius * math.sqrt(max(0.0, 1.0 - component * component))
            for component in axis
        )
    else:
        raise ValueError(f"unsupported IFC swept profile: {profile.is_a()}")

    minimum = tuple(min(a, b) - r for a, b, r in zip(start, end, radius, strict=True))
    maximum = tuple(max(a, b) + r for a, b, r in zip(start, end, radius, strict=True))
    return Bounds(*minimum, *maximum)


def _bounds_from_points(points: Iterable[tuple[float, float, float]]) -> Bounds:
    values = list(points)
    if not values:
        raise ValueError("geometry contains no vertices")
    return Bounds(
        min(point[0] for point in values),
        min(point[1] for point in values),
        min(point[2] for point in values),
        max(point[0] for point in values),
        max(point[1] for point in values),
        max(point[2] for point in values),
    )


def stl_bounds(path: Path) -> Bounds:
    with path.open("rb") as handle:
        data = handle.read(MAX_STL_BYTES + 1)
    if len(data) > MAX_STL_BYTES:
        raise ValueError(f"STL exceeds {MAX_STL_BYTES} byte observation limit")
    if len(data) < 15:
        raise ValueError("STL is too short")

    if len(data) >= 84:
        facet_count = struct.unpack_from("<I", data, 80)[0]
        expected_size = 84 + facet_count * 50
        if expected_size == len(data):
            if facet_count == 0 or facet_count > MAX_STL_FACETS:
                raise ValueError("binary STL facet count is outside the supported range")
            minimum = [math.inf, math.inf, math.inf]
            maximum = [-math.inf, -math.inf, -math.inf]
            for offset in range(84, len(data), 50):
                values = struct.unpack_from("<12fH", data, offset)
                coordinates = values[3:12]
                if not all(math.isfinite(value) for value in coordinates):
                    raise ValueError("binary STL contains a non-finite vertex")
                for index in range(0, 9, 3):
                    for axis, value in enumerate(coordinates[index : index + 3]):
                        minimum[axis] = min(minimum[axis], float(value))
                        maximum[axis] = max(maximum[axis], float(value))
            return Bounds(*minimum, *maximum)

    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("STL is neither a valid binary nor ASCII mesh") from exc
    if not text.lstrip().lower().startswith("solid") or "endsolid" not in text[-512:].lower():
        raise ValueError("ASCII STL envelope is invalid")
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    vertex_count = 0
    for line in io.StringIO(text):
        parts = line.strip().split()
        if not parts or parts[0] != "vertex":
            continue
        if len(parts) != 4 or any(len(token) > MAX_ASCII_NUMBER_CHARS for token in parts[1:]):
            raise ValueError("ASCII STL vertex is malformed or oversized")
        try:
            point = tuple(float(token) for token in parts[1:])
        except ValueError as exc:
            raise ValueError("ASCII STL vertex is not numeric") from exc
        if not all(math.isfinite(value) for value in point):
            raise ValueError("ASCII STL contains a non-finite vertex")
        vertex_count += 1
        if vertex_count > MAX_STL_FACETS * 3:
            raise ValueError("ASCII STL facet count is invalid")
        for axis, value in enumerate(point):
            minimum[axis] = min(minimum[axis], value)
            maximum[axis] = max(maximum[axis], value)
    if vertex_count == 0 or vertex_count % 3 != 0:
        raise ValueError("ASCII STL facet count is invalid")
    return Bounds(*minimum, *maximum)


def _cadquery_bounds(shape) -> Bounds:
    box = shape.val().BoundingBox()
    return Bounds(box.xmin, box.ymin, box.zmin, box.xmax, box.ymax, box.zmax)


def step_bounds(path: Path) -> Bounds:
    import cadquery as cq

    return _cadquery_bounds(cq.importers.importStep(str(path)))


def _number(parameters: Mapping[str, object], key: str) -> float:
    value = parameters.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"ProjectSpec parameter {key!r} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"ProjectSpec parameter {key!r} must be finite and positive")
    return number


def _cadquery_pipe_support(parameters: Mapping[str, object]) -> Bounds:
    length = _number(parameters, "length_mm")
    width = _number(parameters, "width_mm")
    height = _number(parameters, "height_mm")
    base_thickness = _number(parameters, "base_thickness_mm")
    # The saddle is 34 mm deep and centered 16 mm above the declared post
    # height, so its upper envelope is height + 33 mm.
    return Bounds(
        -length / 2,
        -width / 2,
        -base_thickness / 2,
        length / 2,
        width / 2,
        height + 33,
    )


def _cadquery_duct_hanger(parameters: Mapping[str, object]) -> Bounds:
    duct_width = _number(parameters, "duct_width_mm")
    duct_height = _number(parameters, "duct_height_mm")
    height = _number(parameters, "height_mm")
    strap_width = _number(parameters, "strap_width_mm")
    strap_thickness = _number(parameters, "strap_thickness_mm")
    overall_width = duct_width + 120
    half_depth = max(strap_width / 2, duct_height / 2 + strap_thickness / 2)
    return Bounds(
        -overall_width / 2,
        -half_depth,
        -strap_thickness / 2,
        overall_width / 2,
        half_depth,
        height + strap_thickness / 2,
    )


def _cadquery_cable_tray(parameters: Mapping[str, object]) -> Bounds:
    length = _number(parameters, "length_mm")
    width = _number(parameters, "width_mm")
    height = _number(parameters, "height_mm")
    thickness = _number(parameters, "thickness_mm")
    return Bounds(-length / 2, -width / 2, -thickness / 2, length / 2, width / 2, height)


def _cadquery_equipment_base(parameters: Mapping[str, object]) -> Bounds:
    length = _number(parameters, "length_mm")
    width = _number(parameters, "width_mm")
    height = _number(parameters, "height_mm")
    return Bounds(-length / 2, -width / 2, -height / 2, length / 2, width / 2, height / 2)


def _cadquery_pump_skid(parameters: Mapping[str, object]) -> Bounds:
    length = _number(parameters, "length_mm")
    width = _number(parameters, "width_mm")
    height = _number(parameters, "height_mm")
    rail_width = _number(parameters, "rail_width_mm")
    # End crossmembers are centered on the declared rail endpoints.
    half_length = length / 2 + rail_width / 2
    return Bounds(-half_length, -width / 2, 0, half_length, width / 2, height)


def _cadquery_wall_sleeve(parameters: Mapping[str, object]) -> Bounds:
    diameter = _number(parameters, "flange_diameter_mm")
    depth = _number(parameters, "wall_thickness_mm")
    return Bounds(-diameter / 2, -diameter / 2, 0, diameter / 2, diameter / 2, depth)


def _cadquery_pipe_clamp(parameters: Mapping[str, object]) -> Bounds:
    outer_radius = _number(parameters, "pipe_diameter_mm") / 2 + _number(
        parameters, "thickness_mm"
    )
    ear_extent = outer_radius + _number(parameters, "ear_length_mm") - 2
    width = _number(parameters, "width_mm")
    return Bounds(-ear_extent, -outer_radius, 0, ear_extent, outer_radius, width)


def _cadquery_rectangular_duct(parameters: Mapping[str, object]) -> Bounds:
    length = _number(parameters, "length_mm")
    width = _number(parameters, "duct_width_mm")
    height = _number(parameters, "duct_height_mm")
    flange_depth = _number(parameters, "flange_depth_mm")
    return Bounds(
        -length / 2 - flange_depth,
        -(width + 36) / 2,
        -(height + 36) / 2,
        length / 2 + flange_depth,
        (width + 36) / 2,
        (height + 36) / 2,
    )


def _cadquery_mounting_plate(parameters: Mapping[str, object]) -> Bounds:
    length = _number(parameters, "length_mm")
    width = _number(parameters, "width_mm")
    thickness = _number(parameters, "thickness_mm")
    return Bounds(
        -length / 2,
        -width / 2,
        -thickness / 2,
        length / 2,
        width / 2,
        thickness / 2,
    )


CADQUERY_ENVELOPES: dict[str, Callable[[Mapping[str, object]], Bounds]] = {
    "support_pipe_bracket_type_a": _cadquery_pipe_support,
    "support_duct_hanger_type_a": _cadquery_duct_hanger,
    "cable_tray_overhead_001": _cadquery_cable_tray,
    "equipment_base_type_a": _cadquery_equipment_base,
    "equipment_pump_skid_001": _cadquery_pump_skid,
    "sleeve_wall_penetration_type_a": _cadquery_wall_sleeve,
    "pipe_clamp_type_a": _cadquery_pipe_clamp,
    "duct_main_001": _cadquery_rectangular_duct,
    "plate_mounting_type_a": _cadquery_mounting_plate,
}


def _openscad_bracket(parameters: Mapping[str, object]) -> Bounds:
    length = _number(parameters, "length_mm")
    width = _number(parameters, "width_mm")
    thickness = _number(parameters, "thickness_mm")
    return Bounds(-length / 2, -width / 2, -thickness / 2, length / 2, width / 2, thickness / 2)


def _openscad_tray(parameters: Mapping[str, object]) -> Bounds:
    length = _number(parameters, "length_mm")
    width = _number(parameters, "width_mm")
    height = _number(parameters, "height_mm")
    thickness = _number(parameters, "wall_thickness_mm")
    return Bounds(-length / 2, -width / 2, -thickness / 2, length / 2, width / 2, height)


def _openscad_connector(parameters: Mapping[str, object]) -> Bounds:
    width = _number(parameters, "duct_width_mm")
    height = _number(parameters, "duct_height_mm")
    depth = _number(parameters, "connector_depth_mm")
    wall = _number(parameters, "thickness_mm")
    flange = _number(parameters, "flange_extra_mm")
    return Bounds(
        -depth / 2 - wall,
        -(width + flange) / 2,
        -(height + flange) / 2,
        depth / 2 + wall,
        (width + flange) / 2,
        (height + flange) / 2,
    )


def _openscad_clamp(parameters: Mapping[str, object]) -> Bounds:
    outer_radius = _number(parameters, "pipe_diameter_mm") / 2 + _number(
        parameters, "thickness_mm"
    )
    ear_extent = outer_radius + _number(parameters, "ear_length_mm") - 2
    width = _number(parameters, "width_mm")
    return Bounds(-ear_extent, -outer_radius, 0, ear_extent, outer_radius, width)


OPENSCAD_ENVELOPES: dict[str, Callable[[Mapping[str, object]], Bounds]] = {
    "openscad_bracket_plate_type_b": _openscad_bracket,
    "openscad_cable_tray_segment_type_b": _openscad_tray,
    "openscad_duct_connector_type_b": _openscad_connector,
    "openscad_pipe_clamp_type_b": _openscad_clamp,
}


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "0"
    return f"{value:.9f}".rstrip("0").rstrip(".")


def _row(
    *,
    subject_kind: str,
    type_id: str,
    occurrence_id: str,
    format_name: str,
    artifact_path: str,
    expected_source: str,
    expected: Bounds | None,
    observed: Bounds | None,
    tolerance: float,
    diagnostic: str = "",
    status: str | None = None,
) -> dict[str, str]:
    max_delta: float | None = None
    if expected is not None and observed is not None:
        max_delta = max(
            abs(left - right)
            for left, right in zip(expected.values, observed.values, strict=True)
        )
    resolved_status = status or ("PASS" if max_delta is not None and max_delta <= tolerance else "FAIL")
    expected_values = expected.values if expected else (None,) * 6
    observed_values = observed.values if observed else (None,) * 6
    values = {
        "subject_kind": subject_kind,
        "type_id": type_id,
        "occurrence_id": occurrence_id,
        "format": format_name,
        "artifact_path": artifact_path,
        "expected_source": expected_source,
        "tolerance_mm": _fmt(tolerance),
        "max_delta_mm": _fmt(max_delta),
        "status": resolved_status,
        "diagnostic": diagnostic,
    }
    for prefix, bounds_values in (("expected", expected_values), ("observed", observed_values)):
        for name, value in zip(
            ("min_x_mm", "min_y_mm", "min_z_mm", "max_x_mm", "max_y_mm", "max_z_mm"),
            bounds_values,
            strict=True,
        ):
            values[f"{prefix}_{name}"] = _fmt(value)
    return values


def _failure_row(
    *,
    subject_kind: str,
    type_id: str,
    occurrence_id: str,
    format_name: str,
    artifact_path: str,
    expected_source: str,
    expected: Bounds | None,
    tolerance: float,
    error: Exception,
) -> dict[str, str]:
    return _row(
        subject_kind=subject_kind,
        type_id=type_id,
        occurrence_id=occurrence_id,
        format_name=format_name,
        artifact_path=artifact_path,
        expected_source=expected_source,
        expected=expected,
        observed=None,
        tolerance=tolerance,
        diagnostic=str(error),
        status="FAIL",
    )


def observe_ifc(project: ProjectSpec, ifc_path: Path) -> list[dict[str, str]]:
    relative = ifc_path.relative_to(ROOT).as_posix()
    model = ifcopenshell.open(ifc_path)
    products = {
        str(product.Tag): product
        for product in model.by_type("IfcProduct")
        if getattr(product, "Tag", None)
    }
    spaces = [
        product
        for product in model.by_type("IfcSpace")
        if product.Name == project.spatial.space_ifc_name
    ]
    if len(spaces) == 1:
        products[project.spatial.space_occurrence_id] = spaces[0]

    rows = []
    for occurrence in project.occurrences:
        expected = occurrence_bounds(occurrence)
        try:
            product = products[occurrence.occurrence_id]
            observed = ifc_product_bounds(product)
            rows.append(
                _row(
                    subject_kind="occurrence",
                    type_id=occurrence.type_id,
                    occurrence_id=occurrence.occurrence_id,
                    format_name="ifc",
                    artifact_path=relative,
                    expected_source="ProjectSpec occurrence placement and dimensions",
                    expected=expected,
                    observed=observed,
                    tolerance=0.001,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            rows.append(
                _failure_row(
                    subject_kind="occurrence",
                    type_id=occurrence.type_id,
                    occurrence_id=occurrence.occurrence_id,
                    format_name="ifc",
                    artifact_path=relative,
                    expected_source="ProjectSpec occurrence placement and dimensions",
                    expected=expected,
                    tolerance=0.001,
                    error=exc,
                )
            )
    return rows


def observe_cadquery(project: ProjectSpec) -> list[dict[str, str]]:
    rows = []
    bound_type_ids = set(ASSET_BINDINGS.values())
    adapter_type_ids = set(CADQUERY_ENVELOPES)
    if bound_type_ids != adapter_type_ids:
        missing = sorted(bound_type_ids - adapter_type_ids)
        stale = sorted(adapter_type_ids - bound_type_ids)
        raise ValueError(
            "CadQuery envelope adapters do not match generator bindings; "
            f"missing={missing}, stale={stale}"
        )
    occurrences_by_type: dict[str, list[str]] = {}
    for occurrence in project.occurrences:
        occurrences_by_type.setdefault(occurrence.type_id, []).append(occurrence.occurrence_id)

    for type_id in sorted(ASSET_BINDINGS.values()):
        asset_type = project.asset_types_by_id[type_id]
        occurrence_ids = ";".join(sorted(occurrences_by_type.get(type_id, [])))
        try:
            expected = CADQUERY_ENVELOPES[type_id](asset_type.parameters)
        except (KeyError, TypeError, ValueError) as exc:
            expected = None
            adapter_error = exc
        else:
            adapter_error = None

        for format_name, reader, tolerance in (
            ("step", step_bounds, 0.001),
            ("stl", stl_bounds, 0.5),
        ):
            relative = str(asset_type.exports.get(format_name, ""))
            source = "ProjectSpec asset-type parameters through independent envelope adapter"
            try:
                if adapter_error is not None:
                    raise ValueError(f"expected envelope could not be derived: {adapter_error}")
                if not relative:
                    raise ValueError(f"asset type has no {format_name} export")
                observed = reader(_safe_repo_path(relative))
                rows.append(
                    _row(
                        subject_kind="asset_type",
                        type_id=type_id,
                        occurrence_id=occurrence_ids,
                        format_name=format_name,
                        artifact_path=relative,
                        expected_source=source,
                        expected=expected,
                        observed=observed,
                        tolerance=tolerance,
                    )
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                rows.append(
                    _failure_row(
                        subject_kind="asset_type",
                        type_id=type_id,
                        occurrence_id=occurrence_ids,
                        format_name=format_name,
                        artifact_path=relative,
                        expected_source=source,
                        expected=expected,
                        tolerance=tolerance,
                        error=exc,
                    )
                )
    return rows


def observe_openscad(project: ProjectSpec) -> list[dict[str, str]]:
    rows = []
    for type_id, envelope in sorted(OPENSCAD_ENVELOPES.items()):
        asset_type = project.asset_types_by_id[type_id]
        relative = str(asset_type.exports.get("stl", ""))
        source = "ProjectSpec asset-type parameters through reviewed OpenSCAD envelope adapter"
        expected: Bounds | None = None
        try:
            expected = envelope(asset_type.parameters)
            observed = stl_bounds(_safe_repo_path(relative))
            rows.append(
                _row(
                    subject_kind="asset_type",
                    type_id=type_id,
                    occurrence_id="",
                    format_name="stl",
                    artifact_path=relative,
                    expected_source=source,
                    expected=expected,
                    observed=observed,
                    tolerance=0.5,
                    diagnostic="Reusable type has no placed occurrence in ProjectSpec v1",
                )
            )
        except (OSError, TypeError, ValueError) as exc:
            rows.append(
                _failure_row(
                    subject_kind="asset_type",
                    type_id=type_id,
                    occurrence_id="",
                    format_name="stl",
                    artifact_path=relative,
                    expected_source=source,
                    expected=expected,
                    tolerance=0.5,
                    error=exc,
                )
            )
    return rows


def _dxf_polyline_bounds(entity) -> Bounds:
    if not entity.closed:
        raise ValueError("DXF observation requires a closed LWPOLYLINE")
    points = [(float(x), float(y), 0.0) for x, y, *_ in entity.get_points()]
    return _bounds_from_points(points)


def observe_dxf(project: ProjectSpec) -> list[dict[str, str]]:
    relative = "qcad/floor_plan.dxf"
    document = ezdxf.readfile(_safe_repo_path(relative))
    polylines_by_layer: dict[str, list[Bounds]] = {}
    for entity in document.modelspace().query("LWPOLYLINE"):
        if not entity.closed:
            continue
        polylines_by_layer.setdefault(entity.dxf.layer, []).append(_dxf_polyline_bounds(entity))

    rows = []
    for occurrence_id, layer in DXF_BOX_OBSERVATIONS:
        occurrence = project.occurrences_by_id[occurrence_id]
        expected_3d = occurrence_bounds(occurrence)
        expected = Bounds(
            expected_3d.min_x,
            expected_3d.min_y,
            0,
            expected_3d.max_x,
            expected_3d.max_y,
            0,
        )
        candidates = polylines_by_layer.get(layer, [])
        matching = [
            candidate
            for candidate in candidates
            if max(
                abs(left - right)
                for left, right in zip(expected.values, candidate.values, strict=True)
            )
            <= 0.001
        ]
        if len(matching) == 1:
            rows.append(
                _row(
                    subject_kind="occurrence",
                    type_id=occurrence.type_id,
                    occurrence_id=occurrence_id,
                    format_name="dxf",
                    artifact_path=relative,
                    expected_source=f"ProjectSpec plan bounds on layer {layer}",
                    expected=expected,
                    observed=matching[0],
                    tolerance=0.001,
                )
            )
        else:
            rows.append(
                _failure_row(
                    subject_kind="occurrence",
                    type_id=occurrence.type_id,
                    occurrence_id=occurrence_id,
                    format_name="dxf",
                    artifact_path=relative,
                    expected_source=f"ProjectSpec plan bounds on layer {layer}",
                    expected=expected,
                    tolerance=0.001,
                    error=ValueError(
                        f"expected exactly one matching closed outline, found {len(matching)}"
                    ),
                )
            )
    return rows


def excluded_legacy_assembly(project: ProjectSpec) -> dict[str, str]:
    asset_type = project.asset_types_by_id[project.spatial.space_type_id]
    relative = str(asset_type.exports.get("step", "exports/step/mechanical_room_assembly.step"))
    return _row(
        subject_kind="project_assembly",
        type_id=asset_type.type_id,
        occurrence_id=project.spatial.space_occurrence_id,
        format_name="step",
        artifact_path=relative,
        expected_source="Legacy FreeCAD decomposition awaiting ProjectSpec adapter",
        expected=None,
        observed=None,
        tolerance=0.001,
        status="EXCLUDED",
        diagnostic=(
            "The assembly combines many legacy FreeCAD primitives; it is explicitly outside "
            "v1 observed-envelope certification until its decomposition adapter is complete."
        ),
    )


def build_rows(
    project: ProjectSpec,
    *,
    ifc_path: Path = DEFAULT_IFC_PATH,
) -> list[dict[str, str]]:
    if project.source_path.resolve() != DEFAULT_PROJECT_SPEC_PATH.resolve():
        raise ValueError(
            "observed geometry adapters currently certify only the canonical source "
            "contract at spec/mechanical_room.project.json"
        )
    if project.project.project_id != CANONICAL_PROJECT_ID:
        raise ValueError(
            "observed geometry adapters currently certify only the canonical "
            f"{CANONICAL_PROJECT_ID} reference package"
        )
    rows = [
        *observe_ifc(project, ifc_path),
        *observe_cadquery(project),
        *observe_openscad(project),
        *observe_dxf(project),
        excluded_legacy_assembly(project),
    ]
    return sorted(
        rows,
        key=lambda row: (
            row["format"],
            row["subject_kind"],
            row["type_id"],
            row["occurrence_id"],
            row["artifact_path"],
        ),
    )


def write_csv(rows: Sequence[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: Sequence[dict[str, str]], path: Path) -> None:
    counts = {status: sum(row["status"] == status for row in rows) for status in ("PASS", "FAIL", "EXCLUDED")}
    formats = sorted({row["format"] for row in rows})
    lines = [
        "# Observed Geometry Matrix",
        "",
        "This deterministic report compares authoritative ProjectSpec geometry with",
        "the bounding envelopes measured directly from committed IFC, STEP, STL, and",
        "selected DXF entities. Embedded property-set values are not treated as observed",
        "geometry. Envelope parity does not certify topology, fabrication readiness,",
        "engineering performance, or code compliance.",
        "",
        "## Result",
        "",
        f"- Status: `{'PASSED' if counts['FAIL'] == 0 else 'FAILED'}`",
        f"- Passing observations: `{counts['PASS']}`",
        f"- Failed observations: `{counts['FAIL']}`",
        f"- Explicit exclusions: `{counts['EXCLUDED']}`",
        f"- Formats: `{', '.join(formats)}`",
        "",
        "## Observations",
        "",
        "| Format | Subject | Occurrence | Expected size (mm) | Observed size (mm) | Max delta (mm) | Status |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in rows:
        expected = " × ".join(
            _fmt(float(row[f"expected_max_{axis}_mm"]) - float(row[f"expected_min_{axis}_mm"]))
            for axis in ("x", "y", "z")
        ) if row["expected_min_x_mm"] else "—"
        observed = " × ".join(
            _fmt(float(row[f"observed_max_{axis}_mm"]) - float(row[f"observed_min_{axis}_mm"]))
            for axis in ("x", "y", "z")
        ) if row["observed_min_x_mm"] else "—"
        lines.append(
            f"| `{row['format']}` | `{row['type_id']}` | `{row['occurrence_id'] or '—'}` | "
            f"{expected} | {observed} | {row['max_delta_mm'] or '—'} | `{row['status']}` |"
        )
    lines.extend(
        [
            "",
            "## Explicit Boundary",
            "",
            "`mechanical_room_assembly.step` remains an explicit exclusion because its",
            "legacy FreeCAD decomposition is not yet projected completely from ProjectSpec.",
            "The exclusion is visible in the CSV and cannot be mistaken for a passing check.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def generate(
    *,
    project_spec_path: Path = DEFAULT_PROJECT_SPEC_PATH,
    ifc_path: Path = DEFAULT_IFC_PATH,
    csv_path: Path = DEFAULT_CSV_PATH,
    markdown_path: Path = DEFAULT_MARKDOWN_PATH,
) -> list[dict[str, str]]:
    project = load_project_spec(project_spec_path)
    rows = build_rows(project, ifc_path=ifc_path)
    write_csv(rows, csv_path)
    write_markdown(rows, markdown_path)
    return rows


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-spec", type=Path, default=DEFAULT_PROJECT_SPEC_PATH)
    parser.add_argument("--ifc", type=Path, default=DEFAULT_IFC_PATH)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows = generate(
            project_spec_path=args.project_spec,
            ifc_path=args.ifc,
            csv_path=args.csv,
            markdown_path=args.markdown,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"Observed geometry matrix failed: {exc}", file=sys.stderr)
        return 2
    failures = [row for row in rows if row["status"] == "FAIL"]
    passing = sum(row["status"] == "PASS" for row in rows)
    excluded = sum(row["status"] == "EXCLUDED" for row in rows)
    print(
        f"Observed geometry: {passing} passing, {len(failures)} failed, "
        f"{excluded} explicitly excluded"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
