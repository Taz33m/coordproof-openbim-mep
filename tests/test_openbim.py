from __future__ import annotations

from pathlib import Path

from openbim_core import PROJECT_SPEC, OpenBIMBuilder, build_openbim_model, guid
from validate_ifc import product_psets, validate


def global_ids(model) -> list[str]:
    return [entity.GlobalId for entity in model if getattr(entity, "GlobalId", None)]


def test_semantic_guids_are_stable_and_unique() -> None:
    first = global_ids(build_openbim_model())
    second = global_ids(build_openbim_model())
    assert first == second
    assert len(first) == len(set(first))
    assert guid("root:IfcProject:example") == guid("root:IfcProject:example")


def test_source_date_epoch_controls_ifc_header(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    builder = OpenBIMBuilder()
    assert builder.model.header.file_name.time_stamp == "1970-01-01T00:00:00"


def write_model(model, path: Path) -> Path:
    model.write(path)
    return path


def box_contract(product) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    placement = tuple(product.ObjectPlacement.RelativePlacement.Location.Coordinates)
    solid = product.Representation.Representations[0].Items[0]
    profile_offset = tuple(solid.Position.Location.Coordinates)
    dimensions = (solid.SweptArea.XDim, solid.SweptArea.YDim, solid.Depth)
    return placement, profile_offset, dimensions


def test_generated_ifc_formally_valid_and_round_trips_project_spec(
    tmp_path: Path,
) -> None:
    model = build_openbim_model()
    result = validate(write_model(model, tmp_path / "generated.ifc"))

    assert result["status"] == "passed", "\n".join(result["failures"])
    assert result["summary"]["formal_validation_error_count"] == 0
    assert result["summary"]["project_spec_occurrence_count"] == len(
        PROJECT_SPEC.occurrences
    )
    assert result["summary"]["ifc_port_count"] == sum(
        len(occurrence.ports) for occurrence in PROJECT_SPEC.occurrences
    )
    assert result["summary"]["project_spec_connection_count"] == len(
        PROJECT_SPEC.connections
    )


def test_ifc_evidence_keeps_type_port_and_material_identity() -> None:
    model = build_openbim_model()
    psets, duplicates = product_psets(model)
    assert not duplicates

    products_by_tag = {
        product.Tag: product
        for product in model.by_type("IfcProduct")
        if getattr(product, "Tag", None)
    }
    slab = products_by_tag["slab_concrete_base_001"]
    slab_pset = psets[slab.id()]["Pset_OpenBIMAsset"]
    assert slab_pset["TypeID"] == "slab_concrete_base_001"
    assert slab_pset["SystemName"] == ""
    assert slab_pset["MaterialName"] == "cast_in_place_concrete"
    assert slab.GlobalId == guid("root:occurrence:slab_concrete_base_001")

    port_count = 0
    for occurrence in PROJECT_SPEC.occurrences:
        for port_name, system_name in occurrence.port_systems.items():
            expected = {
                "OccurrenceID": occurrence.occurrence_id,
                "PortName": port_name,
                "SystemName": system_name,
            }
            port = next(
                item
                for item in model.by_type("IfcDistributionPort")
                if psets[item.id()]["Pset_OpenBIMPort"] == expected
            )
            assert port.Name == f"{occurrence.ifc_name}_{port_name}"
            port_count += 1
    assert port_count == len(model.by_type("IfcDistributionPort"))

    clearance = products_by_tag["clearance_ahu_service_zone_001"]
    assert psets[clearance.id()]["Pset_OpenBIMAsset"]["MaterialName"] == "clearance_volume"
    material_targets = {
        product.id()
        for rel in model.by_type("IfcRelAssociatesMaterial")
        for product in rel.RelatedObjects
    }
    assert clearance.id() not in material_targets


def test_ifc_box_origins_are_projectspec_lower_corners() -> None:
    model = build_openbim_model()
    products = {
        getattr(product, "Tag", None): product
        for product in model.by_type("IfcProduct")
        if getattr(product, "Tag", None)
    }
    room = next(product for product in model.by_type("IfcSpace"))

    assert box_contract(room) == ((0, 0, 0), (3000, 2100, 0), (6000, 4200, 3200))
    assert box_contract(products["equipment_ahu_001"]) == (
        (850, 780, 360),
        (750, 425, 0),
        (1500, 850, 1100),
    )


def test_validator_rejects_stale_projectspec_evidence(tmp_path: Path) -> None:
    model = build_openbim_model()
    slab = next(
        product
        for product in model.by_type("IfcSlab")
        if product.Tag == "slab_concrete_base_001"
    )
    for rel in model.by_type("IfcRelDefinesByProperties"):
        if slab not in rel.RelatedObjects or rel.RelatingPropertyDefinition.Name != "Pset_OpenBIMAsset":
            continue
        category = next(
            prop
            for prop in rel.RelatingPropertyDefinition.HasProperties
            if prop.Name == "Category"
        )
        category.NominalValue = model.create_entity("IfcLabel", "stale_category")
        break

    result = validate(write_model(model, tmp_path / "stale.ifc"))

    assert result["status"] == "failed"
    assert any(
        "slab_concrete_base_001 Pset_OpenBIMAsset mismatch" in failure
        for failure in result["failures"]
    )
