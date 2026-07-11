from __future__ import annotations

import pytest
from generate_all import ASSET_BINDINGS, load_asset_module
from mounting_plate import build
from project_spec import load_project_spec
from reconcile_parameters import contract_project_spec_path


def _geometry_signature(workplane) -> tuple[object, ...]:
    shape = workplane.val()
    vertices, triangles = shape.tessellate(0.5)
    coordinates = tuple(
        sorted(
            (round(vertex.x, 5), round(vertex.y, 5), round(vertex.z, 5))
            for vertex in vertices
        )
    )
    bounds = shape.BoundingBox()
    envelope = tuple(
        round(value, 5)
        for value in (
            bounds.xmin,
            bounds.ymin,
            bounds.zmin,
            bounds.xmax,
            bounds.ymax,
            bounds.zmax,
        )
    )
    return (
        coordinates,
        len(triangles),
        round(shape.Volume(), 5),
        round(shape.Area(), 5),
        envelope,
    )


def test_mounting_plate_matches_catalog_envelope() -> None:
    solid = build().val()
    bbox = solid.BoundingBox()
    assert bbox.xlen == pytest.approx(260.0)
    assert bbox.ylen == pytest.approx(160.0)
    assert bbox.zlen == pytest.approx(12.0)
    assert solid.Volume() == pytest.approx(488185.4870393785, rel=1e-10)


def test_mounting_plate_rejects_impossible_slot() -> None:
    with pytest.raises(ValueError, match="slot_length_mm"):
        build({"slot_length_mm": 5, "bolt_diameter_mm": 14})


def test_every_numeric_cadquery_input_changes_geometry() -> None:
    project = load_project_spec(contract_project_spec_path())
    for module_name, asset_id in sorted(ASSET_BINDINGS.items()):
        module = load_asset_module(module_name)
        parameters = dict(project.asset_types_by_id[asset_id].parameters)
        baseline = _geometry_signature(module.build(parameters))
        assert _geometry_signature(module.build(parameters)) == baseline, (
            f"{module_name} geometry signature is not deterministic"
        )

        for name, value in parameters.items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            delta = 1 if isinstance(value, int) else max(abs(value) * 0.01, 0.5)
            varied = dict(parameters)
            varied[name] = value + delta
            assert _geometry_signature(module.build(varied)) != baseline, (
                f"{module_name}.{name} does not influence the generated geometry"
            )
