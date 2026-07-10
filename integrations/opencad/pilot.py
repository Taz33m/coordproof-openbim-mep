"""Build and verify the optional OpenCAD mounting-plate pilot.

The canonical ProjectSpec asset type remains authoritative. This module creates
sidecar OpenCAD outputs and rejects them unless their real OCCT geometry and
forced feature-tree rebuild match the canonical asset within tight tolerances.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CADQUERY_DIR = ROOT / "cadquery"
TOOLS_DIR = ROOT / "tools"
for search_path in (str(TOOLS_DIR), str(CADQUERY_DIR)):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)

from mounting_plate import build as build_reference_plate  # noqa: E402
from project_spec import load_project_spec  # noqa: E402

ASSET_ID = "plate_mounting_type_a"
OPENCAD_REVISION = "be5bbfe915f98bc61e5ea62f3c88bc6d28b96d54"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "opencad" / ASSET_ID
DEFAULT_BBOX_TOLERANCE_MM = 1e-5
DEFAULT_VOLUME_RELATIVE_TOLERANCE = 1e-8
PROJECT_SPEC = load_project_spec()


@dataclass(frozen=True)
class GeometryMetrics:
    length_mm: float
    width_mm: float
    height_mm: float
    volume_mm3: float
    area_mm2: float = 0.0
    min_x_mm: float = 0.0
    min_y_mm: float = 0.0
    min_z_mm: float = 0.0
    max_x_mm: float = 0.0
    max_y_mm: float = 0.0
    max_z_mm: float = 0.0
    center_x_mm: float = 0.0
    center_y_mm: float = 0.0
    center_z_mm: float = 0.0
    solid_count: int = 0
    face_count: int = 0
    edge_count: int = 0


def catalog_parameters() -> dict[str, object]:
    try:
        asset_type = PROJECT_SPEC.asset_types_by_id[ASSET_ID]
    except KeyError as exc:
        raise RuntimeError(f"Canonical ProjectSpec does not contain {ASSET_ID}") from exc
    if asset_type.group != "cadquery":
        raise RuntimeError(f"Canonical ProjectSpec asset {ASSET_ID} is not a CadQuery type")
    return dict(asset_type.parameters)


def validate_parameters(parameters: dict[str, object]) -> dict[str, float | str]:
    required_numeric = (
        "length_mm",
        "width_mm",
        "thickness_mm",
        "bolt_diameter_mm",
        "bolt_spacing_mm",
        "slot_length_mm",
    )
    missing = [name for name in (*required_numeric, "material_tag") if name not in parameters]
    if missing:
        raise ValueError(f"Missing pilot parameter(s): {', '.join(missing)}")

    values: dict[str, float | str] = {"material_tag": str(parameters["material_tag"])}
    for name in required_numeric:
        raw = parameters[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError(f"{name} must be numeric")
        value = float(raw)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a finite positive number")
        values[name] = value

    diameter = float(values["bolt_diameter_mm"])
    slot_length = float(values["slot_length_mm"])
    spacing = float(values["bolt_spacing_mm"])
    length = float(values["length_mm"])
    width = float(values["width_mm"])
    if slot_length < diameter:
        raise ValueError("slot_length_mm must be at least bolt_diameter_mm")
    if spacing + slot_length >= length:
        raise ValueError("bolt spacing and slot length must fit inside the plate length")
    if diameter >= width:
        raise ValueError("bolt_diameter_mm must be smaller than plate width_mm")
    return values


def real_occt_context():
    """Create an OpenCAD 0.1.1 context backed by real OCCT geometry.

    At the pinned revision, RuntimeContext defaults to the analytic backend and
    otherwise writes an ``OPENCAD-MOCK`` file. This compatibility bridge is
    deliberately isolated here and protected by STEP/parity tests.
    """

    try:
        from opencad import RuntimeContext, set_default_context
        from opencad_kernel.core.occt_backend import OcctBackend
        from opencad_kernel.operations.handlers import OpenCadKernel
        from opencad_kernel.operations.registry import OperationRegistry
    except ImportError as exc:
        raise RuntimeError(
            "OpenCAD pilot dependencies are missing. Run `make install-opencad`."
        ) from exc

    context = RuntimeContext(id_strategy="readable")
    context.kernel = OpenCadKernel(
        backend=OcctBackend(id_strategy="readable"),
        id_strategy="readable",
    )
    context.registry = OperationRegistry(context.kernel)
    set_default_context(context)
    return context


def extruded_rectangle(
    context,
    *,
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    z: float,
    depth: float,
    name: str,
):
    from opencad import Part, Sketch

    sketch = Sketch(context=context, origin=(0.0, 0.0, z), name=f"{name} sketch").rect(
        width,
        height,
        origin=(center_x - width / 2.0, center_y - height / 2.0),
    )
    return Part(context=context, name=name).extrude(sketch, depth=depth, name=name)


def extruded_circle(
    context,
    *,
    center_x: float,
    center_y: float,
    radius: float,
    z: float,
    depth: float,
    name: str,
):
    from opencad import Part, Sketch

    sketch = Sketch(context=context, origin=(0.0, 0.0, z), name=f"{name} sketch").circle(
        radius,
        center=(center_x, center_y),
    )
    return Part(context=context, name=name).extrude(sketch, depth=depth, name=name)


def vertical_edge_ids(context, shape_id: str, thickness: float) -> list[str]:
    """Select four unique vertical edges despite OpenCAD's duplicate enumeration."""

    topology = context.kernel.get_topology(shape_id)
    selected: list[str] = []
    seen_centroids: set[tuple[float, float, float]] = set()
    for edge in topology.edges:
        if edge.length is None or not math.isclose(edge.length, thickness, abs_tol=1e-6):
            continue
        centroid = tuple(round(value, 6) for value in (edge.centroid or ()))
        if len(centroid) != 3 or centroid in seen_centroids:
            continue
        seen_centroids.add(centroid)
        selected.append(edge.id)
    if len(selected) != 4:
        raise RuntimeError(f"Expected four unique vertical plate edges, got {len(selected)}")
    return selected


def build_plate(context, parameters: dict[str, object]):
    values = validate_parameters(parameters)
    length = float(values["length_mm"])
    width = float(values["width_mm"])
    thickness = float(values["thickness_mm"])
    diameter = float(values["bolt_diameter_mm"])
    spacing = float(values["bolt_spacing_mm"])
    slot_length = float(values["slot_length_mm"])

    plate = extruded_rectangle(
        context,
        center_x=0.0,
        center_y=0.0,
        width=length,
        height=width,
        z=-thickness / 2.0,
        depth=thickness,
        name="Plate blank",
    )
    plate.chamfer(
        edges=vertical_edge_ids(context, plate.shape_id, thickness),
        distance=5.0,
        name="Chamfer plate corners",
    )

    # OpenCAD's current sketch subtract flag is not applied by the OCCT
    # backend, so each rounded slot is an explicit boolean cutter.
    radius = diameter / 2.0
    middle_length = slot_length - diameter
    cut_z = -thickness / 2.0 - 1.0
    cut_depth = thickness + 2.0
    for slot_number, slot_x in enumerate((-spacing / 2.0, spacing / 2.0), start=1):
        middle = extruded_rectangle(
            context,
            center_x=slot_x,
            center_y=0.0,
            width=middle_length,
            height=diameter,
            z=cut_z,
            depth=cut_depth,
            name=f"Slot {slot_number} middle",
        )
        for end_name, end_x in (
            ("left", slot_x - middle_length / 2.0),
            ("right", slot_x + middle_length / 2.0),
        ):
            end = extruded_circle(
                context,
                center_x=end_x,
                center_y=0.0,
                radius=radius,
                z=cut_z,
                depth=cut_depth,
                name=f"Slot {slot_number} {end_name} end",
            )
            middle.union(end, name=f"Fuse slot {slot_number} {end_name} end")
        plate.cut(middle, name=f"Cut slot {slot_number}")
    return plate


def shape_metrics(shape) -> GeometryMetrics:
    bbox = shape.BoundingBox()
    center = shape.Center()
    return GeometryMetrics(
        length_mm=bbox.xlen,
        width_mm=bbox.ylen,
        height_mm=bbox.zlen,
        volume_mm3=shape.Volume(),
        area_mm2=shape.Area(),
        min_x_mm=bbox.xmin,
        min_y_mm=bbox.ymin,
        min_z_mm=bbox.zmin,
        max_x_mm=bbox.xmax,
        max_y_mm=bbox.ymax,
        max_z_mm=bbox.zmax,
        center_x_mm=center.x,
        center_y_mm=center.y,
        center_z_mm=center.z,
        solid_count=len(shape.Solids()),
        face_count=len(shape.Faces()),
        edge_count=len(shape.Edges()),
    )


def cadquery_metrics() -> GeometryMetrics:
    return shape_metrics(build_reference_plate().val())


def opencad_shape(context, shape_id: str):
    import cadquery as cq

    native = context.kernel.get_native_shape(shape_id)
    if native is None:
        raise RuntimeError(f"OpenCAD shape {shape_id!r} was not found")
    return cq.Shape(native)


def opencad_metrics(context, shape_id: str) -> GeometryMetrics:
    return shape_metrics(opencad_shape(context, shape_id))


def load_step_shape(path: Path):
    from cadquery import importers

    try:
        return importers.importStep(str(path)).val()
    except Exception as exc:
        raise RuntimeError(f"OpenCAD STEP could not be re-imported: {path}") from exc


def step_metrics(path: Path) -> GeometryMetrics:
    return shape_metrics(load_step_shape(path))


def symmetric_difference_volume(left, right) -> float:
    """Measure actual BRep disagreement without requiring identical topology."""

    return abs(left.cut(right).Volume()) + abs(right.cut(left).Volume())


def compare_metrics(
    reference: GeometryMetrics,
    candidate: GeometryMetrics,
    *,
    bbox_tolerance_mm: float = DEFAULT_BBOX_TOLERANCE_MM,
    volume_relative_tolerance: float = DEFAULT_VOLUME_RELATIVE_TOLERANCE,
    symmetric_difference_mm3: float | None = None,
) -> dict[str, Any]:
    bbox_delta = {
        name: abs(getattr(reference, name) - getattr(candidate, name))
        for name in ("length_mm", "width_mm", "height_mm")
    }
    position_delta = {
        name: abs(getattr(reference, name) - getattr(candidate, name))
        for name in (
            "min_x_mm",
            "min_y_mm",
            "min_z_mm",
            "max_x_mm",
            "max_y_mm",
            "max_z_mm",
            "center_x_mm",
            "center_y_mm",
            "center_z_mm",
        )
    }
    volume_delta = abs(reference.volume_mm3 - candidate.volume_mm3)
    volume_relative_delta = volume_delta / reference.volume_mm3
    area_delta = abs(reference.area_mm2 - candidate.area_mm2)
    area_relative_delta = (
        area_delta / reference.area_mm2
        if reference.area_mm2
        else (0.0 if candidate.area_mm2 == 0 else math.inf)
    )
    topology_match = all(
        getattr(reference, name) == getattr(candidate, name)
        for name in ("solid_count", "face_count", "edge_count")
    )
    symmetric_difference_relative = (
        symmetric_difference_mm3 / reference.volume_mm3
        if symmetric_difference_mm3 is not None
        else None
    )
    geometry_match = (
        symmetric_difference_relative is None
        or symmetric_difference_relative <= volume_relative_tolerance
    )
    passed = (
        max((*bbox_delta.values(), *position_delta.values())) <= bbox_tolerance_mm
        and volume_relative_delta <= volume_relative_tolerance
        and area_relative_delta <= volume_relative_tolerance
        and geometry_match
    )
    return {
        "passed": passed,
        "bbox_delta_mm": bbox_delta,
        "position_delta_mm": position_delta,
        "volume_delta_mm3": volume_delta,
        "volume_relative_delta": volume_relative_delta,
        "area_delta_mm2": area_delta,
        "area_relative_delta": area_relative_delta,
        "topology_match": topology_match,
        "symmetric_difference_mm3": symmetric_difference_mm3,
        "symmetric_difference_relative": symmetric_difference_relative,
        "tolerances": {
            "bbox_mm": bbox_tolerance_mm,
            "volume_relative": volume_relative_tolerance,
        },
    }


def verify_real_step(path: Path) -> None:
    data = path.read_bytes()
    if not data.startswith(b"ISO-10303-21;") or b"END-ISO-10303-21;" not in data[-256:]:
        raise RuntimeError(f"OpenCAD did not produce a real STEP file: {path}")


def rebuild_shape(tree_path: Path, final_feature_id: str):
    context = real_occt_context()
    context.load_tree_json(str(tree_path))
    for node_id, node in context.tree.nodes.items():
        if node_id == context.tree.root_id:
            continue
        node.shape_id = None
        node.status = "stale"
    context.rebuild_tree()
    final_node = context.tree.nodes[final_feature_id]
    if not final_node.shape_id:
        raise RuntimeError("Forced OpenCAD tree rebuild produced no final shape")
    return opencad_shape(context, final_node.shape_id)


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def run_pilot(
    output_dir: Path,
    *,
    bbox_tolerance_mm: float = DEFAULT_BBOX_TOLERANCE_MM,
    volume_relative_tolerance: float = DEFAULT_VOLUME_RELATIVE_TOLERANCE,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    parameters = catalog_parameters()
    context = real_occt_context()
    plate = build_plate(context, parameters)

    step_path = output_dir / f"{ASSET_ID}.step"
    tree_path = output_dir / f"{ASSET_ID}.tree.json"
    design_path = output_dir / f"{ASSET_ID}.design.json"
    report_path = output_dir / "comparison.json"

    plate.export(str(step_path))
    context.save_tree_json(str(tree_path))
    plate.export_design_artifact(
        str(design_path),
        artifact_id=ASSET_ID,
        parameters={
            name: {
                "value": value,
                "unit": "mm" if name.endswith("_mm") else None,
                "role": "geometry" if name.endswith("_mm") else "metadata",
            }
            for name, value in parameters.items()
        },
        simulation_tags=[
            {
                "name": "ifc_asset_id",
                "kind": "body",
                "target": ASSET_ID,
                "metadata": {"ifc_class": "IfcMechanicalFastener"},
            }
        ],
    )
    verify_real_step(step_path)

    reference_shape = build_reference_plate().val()
    reference = shape_metrics(reference_shape)
    candidate_shape = opencad_shape(context, plate.shape_id)
    candidate = shape_metrics(candidate_shape)
    direct = compare_metrics(
        reference,
        candidate,
        bbox_tolerance_mm=bbox_tolerance_mm,
        volume_relative_tolerance=volume_relative_tolerance,
        symmetric_difference_mm3=symmetric_difference_volume(
            reference_shape, candidate_shape
        ),
    )
    rebuilt_shape = rebuild_shape(tree_path, plate.feature_id)
    rebuilt = shape_metrics(rebuilt_shape)
    rebuild = compare_metrics(
        reference,
        rebuilt,
        bbox_tolerance_mm=bbox_tolerance_mm,
        volume_relative_tolerance=volume_relative_tolerance,
        symmetric_difference_mm3=symmetric_difference_volume(
            reference_shape, rebuilt_shape
        ),
    )
    imported_shape = load_step_shape(step_path)
    imported = shape_metrics(imported_shape)
    step_import = compare_metrics(
        reference,
        imported,
        bbox_tolerance_mm=bbox_tolerance_mm,
        volume_relative_tolerance=volume_relative_tolerance,
        symmetric_difference_mm3=symmetric_difference_volume(
            reference_shape, imported_shape
        ),
    )
    passed = bool(direct["passed"] and rebuild["passed"] and step_import["passed"])
    report = {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "asset_id": ASSET_ID,
        "authority": "CoordProof ProjectSpec asset type with CadQuery reference geometry",
        "opencad": {
            "version": package_version("opencad"),
            "revision": OPENCAD_REVISION,
            "feature_node_count": len(context.tree.nodes),
            "compatibility_bridge": "RuntimeContext wired to OcctBackend",
        },
        "reference_metrics": asdict(reference),
        "opencad_metrics": asdict(candidate),
        "rebuilt_metrics": asdict(rebuilt),
        "step_reimport_metrics": asdict(imported),
        "direct_comparison": direct,
        "rebuild_comparison": rebuild,
        "step_reimport_comparison": step_import,
        "outputs": {
            "step": step_path.name,
            "feature_tree": tree_path.name,
            "design_artifact": design_path.name,
        },
        "limitations": [
            "The OpenCAD dependency is experimental and pinned to one revision.",
            "CoordProof remains authoritative for asset identity, parameters, IFC semantics, and validation.",
            "Persistent OpenCAD face/edge identity is not used across builds.",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--bbox-tolerance-mm", type=float, default=DEFAULT_BBOX_TOLERANCE_MM)
    parser.add_argument(
        "--volume-relative-tolerance",
        type=float,
        default=DEFAULT_VOLUME_RELATIVE_TOLERANCE,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_pilot(
        args.output_dir,
        bbox_tolerance_mm=args.bbox_tolerance_mm,
        volume_relative_tolerance=args.volume_relative_tolerance,
    )
    print(f"OpenCAD pilot: {report['status'].upper()}")
    print(f"Outputs: {args.output_dir}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
