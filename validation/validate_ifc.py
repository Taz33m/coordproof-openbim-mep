"""Validate IFC evidence against the authoritative versioned ProjectSpec."""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate

ROOT = Path(__file__).resolve().parents[1]
IFC_PATH = ROOT / "bim" / "mechanical_room.ifc"
CONNECTION_DESCRIPTION_PREFIX = "ProjectSpecConnection:"

sys.path.insert(0, str(ROOT / "tools"))
from project_spec import OccurrenceSpec, ProjectSpec, load_project_spec  # noqa: E402


def nominal_value(prop) -> object:
    value = getattr(prop, "NominalValue", None)
    return getattr(value, "wrappedValue", value)


def product_psets(
    model: ifcopenshell.file,
) -> tuple[dict[int, dict[str, dict[str, object]]], list[str]]:
    lookup: dict[int, dict[str, dict[str, object]]] = defaultdict(dict)
    duplicates: list[str] = []
    for rel in model.by_type("IfcRelDefinesByProperties"):
        pset = rel.RelatingPropertyDefinition
        if not pset or not pset.is_a("IfcPropertySet"):
            continue
        props = {prop.Name: nominal_value(prop) for prop in pset.HasProperties}
        for product in rel.RelatedObjects:
            if pset.Name in lookup[product.id()]:
                duplicates.append(f"#{product.id()} {product.Name}: {pset.Name}")
            lookup[product.id()][pset.Name] = props
    return lookup, duplicates


def material_assignments(model: ifcopenshell.file) -> dict[int, list[str]]:
    assignments: dict[int, list[str]] = defaultdict(list)
    for rel in model.by_type("IfcRelAssociatesMaterial"):
        material = rel.RelatingMaterial
        name = getattr(material, "Name", None) or f"#{material.id()} {material.is_a()}"
        for product in rel.RelatedObjects:
            assignments[product.id()].append(name)
    return assignments


def placement_coordinates(product) -> tuple[float, ...] | None:
    placement = getattr(product, "ObjectPlacement", None)
    relative = getattr(placement, "RelativePlacement", None)
    location = getattr(relative, "Location", None)
    coordinates = getattr(location, "Coordinates", None)
    if coordinates is None:
        return None
    return tuple(float(value) for value in coordinates)


def same_numbers(left: object, right: object) -> bool:
    if not isinstance(left, (tuple, list)) or not isinstance(right, (tuple, list)):
        return False
    return len(left) == len(right) and all(
        math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1.0e-9)
        for actual, expected in zip(left, right, strict=True)
    )


def expected_asset_pset(
    project: ProjectSpec, occurrence: OccurrenceSpec
) -> dict[str, object]:
    asset_type = project.asset_types_by_id[occurrence.type_id]
    source_tool = asset_type.source_tool
    if occurrence.occurrence_id == project.spatial.space_occurrence_id:
        source_tool = project.spatial.semantic_source_tool
    return {
        "AssetID": occurrence.occurrence_id,
        "TypeID": occurrence.type_id,
        "Category": asset_type.category,
        "SourceTool": source_tool,
        "SystemName": ", ".join(occurrence.systems),
        "MaterialName": occurrence.material,
        "MachineReadable": True,
        **occurrence.properties,
    }


def expected_geometry_pset(occurrence: OccurrenceSpec) -> dict[str, object]:
    return {
        "GeometryKind": occurrence.geometry,
        "DimensionScheduleMM": " x ".join(
            str(value) for value in occurrence.dimensions_mm
        ),
        "PlacementMM": ", ".join(str(value) for value in occurrence.origin_mm),
    }


def validate_shape(product, occurrence: OccurrenceSpec, failures: list[str]) -> None:
    label = occurrence.occurrence_id
    representation = getattr(product, "Representation", None)
    if representation is None:
        failures.append(f"{label} is missing its geometric representation")
        return
    body_representations = [
        item
        for item in representation.Representations
        if item.RepresentationIdentifier == "Body"
    ]
    if len(body_representations) != 1:
        failures.append(
            f"{label} expected exactly one Body representation, found "
            f"{len(body_representations)}"
        )
        return
    body = body_representations[0]
    if body.RepresentationType != "SweptSolid" or len(body.Items) != 1:
        failures.append(f"{label} Body representation is not one SweptSolid item")
        return
    solid = body.Items[0]
    if not solid.is_a("IfcExtrudedAreaSolid"):
        failures.append(f"{label} expected IfcExtrudedAreaSolid, found {solid.is_a()}")
        return

    position_axis = getattr(getattr(solid, "Position", None), "Axis", None)
    actual_axis = getattr(position_axis, "DirectionRatios", None)
    if not same_numbers(actual_axis, occurrence.extrusion_axis):
        failures.append(
            f"{label} shape axis mismatch: expected {occurrence.extrusion_axis}, "
            f"found {actual_axis}"
        )
    extrusion = getattr(solid.ExtrudedDirection, "DirectionRatios", None)
    if not same_numbers(extrusion, (0.0, 0.0, 1.0)):
        failures.append(
            f"{label} local extrusion direction must be (0, 0, 1), found {extrusion}"
        )

    profile = solid.SweptArea
    if occurrence.geometry == "box":
        expected_dimensions = occurrence.dimensions_mm
        if not profile.is_a("IfcRectangleProfileDef"):
            failures.append(
                f"{label} expected IfcRectangleProfileDef, found {profile.is_a()}"
            )
            return
        actual_dimensions = (profile.XDim, profile.YDim, solid.Depth)
    elif occurrence.geometry == "cylinder":
        expected_dimensions = occurrence.dimensions_mm
        if not profile.is_a("IfcCircleProfileDef"):
            failures.append(f"{label} expected IfcCircleProfileDef, found {profile.is_a()}")
            return
        actual_dimensions = (profile.Radius, solid.Depth)
    else:  # ProjectSpec schema currently prevents this branch.
        failures.append(f"{label} has unsupported geometry kind {occurrence.geometry!r}")
        return
    if not same_numbers(actual_dimensions, expected_dimensions):
        failures.append(
            f"{label} shape dimensions mismatch: expected {expected_dimensions}, "
            f"found {actual_dimensions}"
        )


def connection_description(
    connection_id: str,
    system: str,
    realizing_occurrence_id: str | None,
) -> str:
    payload = {
        "connection_id": connection_id,
        "realizing_occurrence_id": realizing_occurrence_id,
        "system": system,
    }
    return CONNECTION_DESCRIPTION_PREFIX + json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    )


def parse_connection_description(value: object) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(value, str) or not value.startswith(CONNECTION_DESCRIPTION_PREFIX):
        return None, "missing ProjectSpecConnection prefix"
    try:
        payload = json.loads(value.removeprefix(CONNECTION_DESCRIPTION_PREFIX))
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg}"
    expected_keys = {"connection_id", "realizing_occurrence_id", "system"}
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        return None, f"expected metadata keys {sorted(expected_keys)}"
    if not isinstance(payload["connection_id"], str) or not isinstance(
        payload["system"], str
    ):
        return None, "connection_id and system must be strings"
    realizer = payload["realizing_occurrence_id"]
    if realizer is not None and not isinstance(realizer, str):
        return None, "realizing_occurrence_id must be a string or null"
    return payload, None


def formal_validation_failures(model: ifcopenshell.file) -> list[str]:
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger, express_rules=True)
    errors = [item for item in logger.statements if item.get("level") == "error"]
    results: list[str] = []
    for item in errors:
        instance = item.get("instance")
        instance_label = ""
        if instance is not None:
            instance_label = f"#{instance.id()} {instance.is_a()} "
        attribute = item.get("attribute")
        rule_label = f"[{attribute}] " if attribute else ""
        first_line = str(item.get("message", "validation error")).splitlines()[0]
        results.append(f"IFC formal validation: {instance_label}{rule_label}{first_line}")
    return results


def validate(ifc_path: str | Path | None = None) -> dict[str, object]:
    failures: list[str] = []
    warnings: list[str] = []
    path = Path(ifc_path) if ifc_path is not None else IFC_PATH
    project = load_project_spec()
    if not path.exists():
        try:
            display_path = path.relative_to(ROOT)
        except ValueError:
            display_path = path
        return {
            "name": "IFC",
            "status": "failed",
            "summary": {},
            "failures": [f"Missing {display_path}"],
            "warnings": [],
        }

    try:
        model = ifcopenshell.open(str(path))
    except Exception as exc:  # pragma: no cover - parser exceptions vary by release
        return {
            "name": "IFC",
            "status": "failed",
            "summary": {},
            "failures": [f"IfcOpenShell could not open IFC: {exc}"],
            "warnings": [],
        }

    counts = Counter(entity.is_a() for entity in model)
    if model.schema != "IFC4":
        failures.append(f"Expected IFC4 schema, found {model.schema}")
    failures.extend(formal_validation_failures(model))

    unit_assignments = model.by_type("IfcUnitAssignment")
    if len(unit_assignments) != 1:
        failures.append(
            f"Expected exactly one IfcUnitAssignment, found {len(unit_assignments)}"
        )
    else:
        length_units = [
            unit
            for unit in unit_assignments[0].Units
            if getattr(unit, "UnitType", None) == "LENGTHUNIT"
        ]
        if not any(
            getattr(unit, "Name", None) == "METRE"
            and getattr(unit, "Prefix", None) == "MILLI"
            for unit in length_units
        ):
            failures.append("No millimetre length unit detected (METRE with MILLI prefix)")

    rooted = [entity for entity in model if getattr(entity, "GlobalId", None)]
    global_ids = [entity.GlobalId for entity in rooted]
    duplicate_global_ids = sorted(
        global_id
        for global_id, count in Counter(global_ids).items()
        if count > 1
    )
    if duplicate_global_ids:
        failures.append("Duplicate IFC GlobalIds: " + ", ".join(duplicate_global_ids))

    spatial_expectations = (
        ("IfcProject", project.spatial.project_ifc_name),
        ("IfcSite", project.spatial.site_ifc_name),
        ("IfcBuilding", project.spatial.building_ifc_name),
        ("IfcBuildingStorey", project.spatial.storey_ifc_name),
    )
    for ifc_class, expected_name in spatial_expectations:
        entities = model.by_type(ifc_class)
        if len(entities) != 1:
            failures.append(f"Expected exactly one {ifc_class}, found {len(entities)}")
        elif entities[0].Name != expected_name:
            failures.append(
                f"{ifc_class} name mismatch: expected {expected_name!r}, "
                f"found {entities[0].Name!r}"
            )
    storeys = model.by_type("IfcBuildingStorey")
    if storeys and not math.isclose(
        float(storeys[0].Elevation),
        project.spatial.storey_elevation_mm,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        failures.append(
            "IfcBuildingStorey elevation does not match ProjectSpec: "
            f"{storeys[0].Elevation!r}"
        )

    psets, duplicate_psets = product_psets(model)
    if duplicate_psets:
        failures.append("Duplicate product property sets: " + ", ".join(duplicate_psets))
    non_port_products = [
        product
        for product in model.by_type("IfcProduct")
        if not product.is_a("IfcDistributionPort")
    ]
    occurrence_products = [
        product
        for product in non_port_products
        if not any(
            product.is_a(ifc_class)
            for ifc_class in ("IfcSite", "IfcBuilding", "IfcBuildingStorey")
        )
    ]
    if len(occurrence_products) != len(project.occurrences):
        failures.append(
            "IFC occurrence product count does not match ProjectSpec: expected "
            f"{len(project.occurrences)}, found {len(occurrence_products)}"
        )

    products_by_occurrence: dict[str, list[object]] = defaultdict(list)
    for product in occurrence_products:
        asset_pset = psets.get(product.id(), {}).get("Pset_OpenBIMAsset")
        if asset_pset is None:
            failures.append(
                f"#{product.id()} {product.Name or product.is_a()} is missing Pset_OpenBIMAsset"
            )
            continue
        occurrence_id = asset_pset.get("AssetID")
        if not isinstance(occurrence_id, str) or not occurrence_id:
            failures.append(
                f"#{product.id()} {product.Name or product.is_a()} has invalid AssetID evidence"
            )
            continue
        products_by_occurrence[occurrence_id].append(product)

    expected_occurrence_ids = set(project.occurrences_by_id)
    actual_occurrence_ids = set(products_by_occurrence)
    missing_occurrences = sorted(expected_occurrence_ids - actual_occurrence_ids)
    stale_occurrences = sorted(actual_occurrence_ids - expected_occurrence_ids)
    if missing_occurrences:
        failures.append("ProjectSpec occurrences missing from IFC: " + ", ".join(missing_occurrences))
    if stale_occurrences:
        failures.append("Stale/unknown IFC occurrence evidence: " + ", ".join(stale_occurrences))
    duplicated_occurrences = sorted(
        occurrence_id
        for occurrence_id, products in products_by_occurrence.items()
        if len(products) > 1
    )
    if duplicated_occurrences:
        failures.append("Duplicate IFC occurrence evidence: " + ", ".join(duplicated_occurrences))

    product_by_occurrence = {
        occurrence_id: products[0]
        for occurrence_id, products in products_by_occurrence.items()
        if len(products) == 1 and occurrence_id in expected_occurrence_ids
    }
    occurrence_by_product_id = {
        product.id(): occurrence_id
        for occurrence_id, product in product_by_occurrence.items()
    }
    materials = material_assignments(model)

    contained_by: dict[int, list[object]] = defaultdict(list)
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        for product in rel.RelatedElements:
            contained_by[product.id()].append(rel.RelatingStructure)

    for occurrence in project.occurrences:
        product = product_by_occurrence.get(occurrence.occurrence_id)
        if product is None:
            continue
        asset_type = project.asset_types_by_id[occurrence.type_id]
        if product.is_a() != asset_type.ifc_class:
            failures.append(
                f"{occurrence.occurrence_id} class mismatch: expected {asset_type.ifc_class}, "
                f"found {product.is_a()}"
            )
        if product.Name != occurrence.ifc_name:
            failures.append(
                f"{occurrence.occurrence_id} name mismatch: expected {occurrence.ifc_name!r}, "
                f"found {product.Name!r}"
            )
        expected_object_type = occurrence.object_type or asset_type.category
        if product.ObjectType != expected_object_type:
            failures.append(
                f"{occurrence.occurrence_id} ObjectType mismatch: expected "
                f"{expected_object_type!r}, found {product.ObjectType!r}"
            )
        if not product.is_a("IfcSpace") and getattr(product, "Tag", None) != occurrence.occurrence_id:
            failures.append(
                f"{occurrence.occurrence_id} Tag mismatch: {getattr(product, 'Tag', None)!r}"
            )
        actual_asset_pset = psets[product.id()].get("Pset_OpenBIMAsset")
        expected_properties = expected_asset_pset(project, occurrence)
        if actual_asset_pset != expected_properties:
            failures.append(
                f"{occurrence.occurrence_id} Pset_OpenBIMAsset mismatch: expected "
                f"{expected_properties!r}, found {actual_asset_pset!r}"
            )
        actual_geometry_pset = psets[product.id()].get("Pset_AssetGeometry")
        expected_geometry = expected_geometry_pset(occurrence)
        if actual_geometry_pset != expected_geometry:
            failures.append(
                f"{occurrence.occurrence_id} Pset_AssetGeometry mismatch: expected "
                f"{expected_geometry!r}, found {actual_geometry_pset!r}"
            )
        actual_origin = placement_coordinates(product)
        if not same_numbers(actual_origin, occurrence.origin_mm):
            failures.append(
                f"{occurrence.occurrence_id} placement mismatch: expected "
                f"{occurrence.origin_mm}, found {actual_origin}"
            )
        validate_shape(product, occurrence, failures)

        # IFC4 does not permit IfcRelAssociatesMaterial on spatial or virtual
        # elements; their material intent remains explicit in MaterialName.
        expected_materials = (
            []
            if product.is_a("IfcSpace") or product.is_a("IfcVirtualElement")
            else [occurrence.material]
        )
        actual_materials = materials.get(product.id(), [])
        if actual_materials != expected_materials:
            failures.append(
                f"{occurrence.occurrence_id} material assignment mismatch: expected "
                f"{expected_materials!r}, found {actual_materials!r}"
            )

        if occurrence.occurrence_id != project.spatial.space_occurrence_id:
            structures = contained_by.get(product.id(), [])
            if len(structures) != 1 or structures[0].Name != project.spatial.storey_ifc_name:
                names = [getattr(item, "Name", None) for item in structures]
                failures.append(
                    f"{occurrence.occurrence_id} spatial containment mismatch: {names!r}"
                )

    expected_systems = {system.name: system for system in project.systems}
    systems_by_name: dict[str, list[object]] = defaultdict(list)
    for system in model.by_type("IfcDistributionSystem"):
        systems_by_name[system.Name].append(system)
    missing_systems = sorted(set(expected_systems) - set(systems_by_name))
    stale_systems = sorted(set(systems_by_name) - set(expected_systems))
    if missing_systems:
        failures.append("Distribution systems missing from IFC: " + ", ".join(missing_systems))
    if stale_systems:
        failures.append("Stale/unknown IFC distribution systems: " + ", ".join(stale_systems))

    expected_members: dict[str, set[str]] = defaultdict(set)
    for occurrence in project.occurrences:
        for system_name in occurrence.systems:
            expected_members[system_name].add(occurrence.occurrence_id)
    actual_members: dict[str, list[str]] = defaultdict(list)
    system_relation_counts: Counter[str] = Counter()
    for rel in model.by_type("IfcRelAssignsToGroup"):
        group = rel.RelatingGroup
        if not group or not group.is_a("IfcDistributionSystem"):
            continue
        system_relation_counts[group.Name] += 1
        for product in rel.RelatedObjects:
            occurrence_id = occurrence_by_product_id.get(product.id())
            actual_members[group.Name].append(
                occurrence_id or f"<unmapped #{product.id()} {product.is_a()}>"
            )
    for system_name, definition in expected_systems.items():
        entities = systems_by_name.get(system_name, [])
        if len(entities) > 1:
            failures.append(f"Duplicate IfcDistributionSystem named {system_name}")
        if entities:
            entity = entities[0]
            actual_definition = (entity.LongName, entity.ObjectType, entity.Description)
            expected_definition = (
                definition.long_name,
                definition.object_type,
                definition.description,
            )
            if actual_definition != expected_definition:
                failures.append(
                    f"{system_name} definition mismatch: expected {expected_definition!r}, "
                    f"found {actual_definition!r}"
                )
        if system_relation_counts[system_name] != 1:
            failures.append(
                f"{system_name} expected one membership relationship, found "
                f"{system_relation_counts[system_name]}"
            )
        if set(actual_members[system_name]) != expected_members[system_name] or len(
            actual_members[system_name]
        ) != len(expected_members[system_name]):
            failures.append(
                f"{system_name} member mismatch: expected "
                f"{sorted(expected_members[system_name])!r}, found "
                f"{sorted(actual_members[system_name])!r}"
            )

    ports = model.by_type("IfcDistributionPort")
    attachments: dict[int, list[object]] = defaultdict(list)
    for rel in model.by_type("IfcRelConnectsPortToElement"):
        attachments[rel.RelatingPort.id()].append(rel.RelatedElement)
    expected_ports = {
        (occurrence.occurrence_id, port_name): system_name
        for occurrence in project.occurrences
        for port_name, system_name in occurrence.port_systems.items()
    }
    ports_by_key: dict[tuple[str, str], list[object]] = defaultdict(list)
    port_key_by_id: dict[int, tuple[str, str]] = {}
    for port in ports:
        port_pset = psets.get(port.id(), {}).get("Pset_OpenBIMPort")
        if port_pset is None:
            failures.append(f"#{port.id()} {port.Name or ''} is missing Pset_OpenBIMPort")
            continue
        occurrence_id = port_pset.get("OccurrenceID")
        port_name = port_pset.get("PortName")
        system_name = port_pset.get("SystemName")
        if not all(isinstance(item, str) and item for item in (occurrence_id, port_name, system_name)):
            failures.append(f"#{port.id()} {port.Name or ''} has invalid port identity evidence")
            continue
        key = (occurrence_id, port_name)
        ports_by_key[key].append(port)
        port_key_by_id[port.id()] = key
        expected_system = expected_ports.get(key)
        expected_port_pset = {
            "OccurrenceID": occurrence_id,
            "PortName": port_name,
            "SystemName": expected_system,
        }
        if expected_system is None:
            failures.append(f"Stale/unknown IFC port evidence: {occurrence_id}.{port_name}")
        elif port_pset != expected_port_pset:
            failures.append(
                f"{occurrence_id}.{port_name} Pset_OpenBIMPort mismatch: expected "
                f"{expected_port_pset!r}, found {port_pset!r}"
            )
        occurrence = project.occurrences_by_id.get(occurrence_id)
        expected_name = f"{occurrence.ifc_name}_{port_name}" if occurrence else None
        if port.Name != expected_name:
            failures.append(
                f"{occurrence_id}.{port_name} port name mismatch: expected "
                f"{expected_name!r}, found {port.Name!r}"
            )
        attached = attachments.get(port.id(), [])
        expected_product = product_by_occurrence.get(occurrence_id)
        if len(attached) != 1 or attached[0] != expected_product:
            actual = [f"#{item.id()} {item.Name}" for item in attached]
            failures.append(
                f"{occurrence_id}.{port_name} attachment mismatch: {actual!r}"
            )

    missing_ports = sorted(set(expected_ports) - set(ports_by_key))
    if missing_ports:
        failures.append(
            "ProjectSpec ports missing from IFC: "
            + ", ".join(f"{occurrence}.{port}" for occurrence, port in missing_ports)
        )
    duplicate_ports = sorted(
        key for key, values in ports_by_key.items() if len(values) > 1
    )
    if duplicate_ports:
        failures.append(
            "Duplicate IFC port evidence: "
            + ", ".join(f"{occurrence}.{port}" for occurrence, port in duplicate_ports)
        )
    if len(ports) != len(expected_ports):
        failures.append(
            f"IFC port count does not match ProjectSpec: expected {len(expected_ports)}, "
            f"found {len(ports)}"
        )

    connections_by_id: dict[str, list[tuple[object, dict[str, object]]]] = defaultdict(list)
    for rel in model.by_type("IfcRelConnectsPorts"):
        metadata, error = parse_connection_description(rel.Description)
        if error or metadata is None:
            failures.append(
                f"#{rel.id()} {rel.Name or 'IfcRelConnectsPorts'} connection evidence {error}"
            )
            continue
        connections_by_id[str(metadata["connection_id"])].append((rel, metadata))

    expected_connections = {
        connection.connection_id: connection for connection in project.connections
    }
    missing_connections = sorted(set(expected_connections) - set(connections_by_id))
    stale_connections = sorted(set(connections_by_id) - set(expected_connections))
    if missing_connections:
        failures.append("ProjectSpec connections missing from IFC: " + ", ".join(missing_connections))
    if stale_connections:
        failures.append("Stale/unknown IFC connection evidence: " + ", ".join(stale_connections))
    for connection_id, connection in expected_connections.items():
        evidence = connections_by_id.get(connection_id, [])
        if len(evidence) > 1:
            failures.append(f"Duplicate IFC connection evidence: {connection_id}")
        if len(evidence) != 1:
            continue
        rel, metadata = evidence[0]
        expected_source = (connection.source.occurrence_id, connection.source.port)
        expected_target = (connection.target.occurrence_id, connection.target.port)
        actual_source = port_key_by_id.get(rel.RelatingPort.id())
        actual_target = port_key_by_id.get(rel.RelatedPort.id())
        if actual_source != expected_source or actual_target != expected_target:
            failures.append(
                f"{connection_id} endpoint mismatch: expected {expected_source!r} -> "
                f"{expected_target!r}, found {actual_source!r} -> {actual_target!r}"
            )
        if rel.Name != connection.name:
            failures.append(
                f"{connection_id} name mismatch: expected {connection.name!r}, "
                f"found {rel.Name!r}"
            )
        expected_description = connection_description(
            connection_id, connection.system, connection.realizing_occurrence_id
        )
        if rel.Description != expected_description:
            failures.append(
                f"{connection_id} Description mismatch: expected "
                f"{expected_description!r}, found {rel.Description!r}"
            )
        expected_metadata = {
            "connection_id": connection_id,
            "realizing_occurrence_id": connection.realizing_occurrence_id,
            "system": connection.system,
        }
        if metadata != expected_metadata:
            failures.append(
                f"{connection_id} metadata mismatch: expected {expected_metadata!r}, "
                f"found {metadata!r}"
            )
        expected_realizer = connection.realizing_occurrence_id
        actual_realizer = None
        if rel.RealizingElement is not None:
            actual_realizer = occurrence_by_product_id.get(
                rel.RealizingElement.id(),
                f"<unmapped #{rel.RealizingElement.id()} {rel.RealizingElement.is_a()}>",
            )
        if actual_realizer != expected_realizer:
            failures.append(
                f"{connection_id} realizing occurrence mismatch: expected "
                f"{expected_realizer!r}, found {actual_realizer!r}"
            )

    connection_count = len(model.by_type("IfcRelConnectsPorts"))
    if connection_count != len(project.connections):
        failures.append(
            "IFC connection count does not match ProjectSpec: expected "
            f"{len(project.connections)}, found {connection_count}"
        )

    proxies = counts["IfcBuildingElementProxy"]
    if proxies:
        failures.append(
            f"{proxies} IfcBuildingElementProxy objects found; use specific IFC classes"
        )

    return {
        "name": "IFC",
        "status": "passed" if not failures else "failed",
        "summary": {
            "schema": model.schema,
            "entity_count": sum(counts.values()),
            "product_count": len(non_port_products),
            "project_spec_occurrence_count": len(project.occurrences),
            "distribution_system_count": len(systems_by_name),
            "declared_port_count": len(expected_ports),
            "ifc_port_count": len(ports),
            "connected_port_pair_count": connection_count,
            "project_spec_connection_count": len(project.connections),
            "proxy_count": proxies,
            "unique_global_id_count": len(set(global_ids)),
            "formal_validation_error_count": sum(
                failure.startswith("IFC formal validation:") for failure in failures
            ),
            "top_entities": dict(sorted(counts.items())),
        },
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
