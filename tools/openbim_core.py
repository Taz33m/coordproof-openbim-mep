"""IFC-first OpenBIM model builder for the mechanical room pipeline.

The FreeCAD/CadQuery/OpenSCAD assets remain important geometry sources, but this
module defines the BIM truth model directly in IFC terms: spatial hierarchy,
MEP classes, systems, properties, ports, and validation-friendly inventory.
"""

from __future__ import annotations

import csv
import json
import math
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import ifcopenshell
import ifcopenshell.guid
from project_spec import ProjectSpec, load_project_spec
from reproducibility import source_timestamp

ROOT = Path(__file__).resolve().parents[1]
IFC_PATH = ROOT / "bim" / "mechanical_room.ifc"
SUMMARY_PATH = ROOT / "bim" / "ifc_entity_summary.md"
BIM_MAP_PATH = ROOT / "bim" / "bim_object_map.csv"
INVENTORY_PATH = ROOT / "bim" / "openbim_semantic_inventory.csv"
CONNECTION_DESCRIPTION_PREFIX = "ProjectSpecConnection:"

PROJECT_SPEC = load_project_spec()


GUID_NAMESPACE = uuid.UUID("aecb7935-dd13-5b74-93af-50a8a7c9a89c")


def guid(key: str) -> str:
    """Return a stable IFC GUID for a semantic project key."""

    return ifcopenshell.guid.compress(uuid.uuid5(GUID_NAMESPACE, key).hex)


@dataclass(frozen=True)
class ProductSpec:
    asset_id: str
    name: str
    ifc_class: str
    category: str
    source_tool: str
    material: str
    system: tuple[str, ...] = ()
    object_type: str = ""
    geometry: str = "box"
    origin_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    dimensions_mm: tuple[float, ...] = (100.0, 100.0, 100.0)
    extrusion_axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    ports: tuple[str, ...] = ()
    type_id: str = ""
    port_systems: dict[str, str] = field(default_factory=dict)
    properties: dict[str, object] = field(default_factory=dict)


def connection_description(
    connection_id: str,
    system: str,
    realizing_occurrence_id: str | None,
) -> str:
    """Encode ProjectSpec connection identity as deterministic IFC evidence."""

    payload = {
        "connection_id": connection_id,
        "realizing_occurrence_id": realizing_occurrence_id,
        "system": system,
    }
    return CONNECTION_DESCRIPTION_PREFIX + json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    )


class OpenBIMBuilder:
    def __init__(self) -> None:
        self.model = ifcopenshell.file(schema="IFC4")
        self.model.header.file_name.time_stamp = source_timestamp()
        self.body_context = None
        self.materials: dict[str, object] = {}
        self.products_by_asset: dict[str, object] = {}
        self.products_by_name: dict[str, object] = {}
        self.ports: dict[tuple[str, str], object] = {}
        self.systems: dict[str, object] = {}
        self.product_specs: list[ProductSpec] = []

    def entity(self, ifc_class: str, *args, **kwargs):
        return self.model.create_entity(ifc_class, *args, **kwargs)

    def root(self, ifc_class: str, name: str, *, guid_key: str | None = None, **kwargs):
        return self.entity(
            ifc_class,
            GlobalId=guid(guid_key or f"root:{ifc_class}:{name}"),
            OwnerHistory=None,
            Name=name,
            Description=kwargs.pop("Description", None),
            **kwargs,
        )

    def direction(self, xyz: tuple[float, float, float]):
        return self.entity("IfcDirection", DirectionRatios=[float(v) for v in xyz])

    def point(self, xyz: tuple[float, float, float]):
        return self.entity("IfcCartesianPoint", Coordinates=[float(v) for v in xyz])

    def axis3d(
        self,
        xyz: tuple[float, float, float] = (0.0, 0.0, 0.0),
        axis: tuple[float, float, float] = (0.0, 0.0, 1.0),
        ref: tuple[float, float, float] = (1.0, 0.0, 0.0),
    ):
        return self.entity(
            "IfcAxis2Placement3D",
            Location=self.point(xyz),
            Axis=self.direction(axis),
            RefDirection=self.direction(ref),
        )

    @staticmethod
    def perpendicular_reference(
        axis: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        """Return a stable unit vector perpendicular to an extrusion axis."""

        magnitude = math.sqrt(sum(value * value for value in axis))
        normalized = tuple(value / magnitude for value in axis)
        candidate = (1.0, 0.0, 0.0)
        if abs(normalized[0]) > 0.9:
            candidate = (0.0, 1.0, 0.0)
        projection = sum(
            left * right for left, right in zip(candidate, normalized, strict=True)
        )
        perpendicular = tuple(
            left - projection * right
            for left, right in zip(candidate, normalized, strict=True)
        )
        reference_magnitude = math.sqrt(sum(value * value for value in perpendicular))
        return tuple(value / reference_magnitude for value in perpendicular)

    def placement(self, xyz: tuple[float, float, float]):
        return self.entity(
            "IfcLocalPlacement",
            PlacementRelTo=None,
            RelativePlacement=self.axis3d(xyz),
        )

    def value(self, raw: object):
        if isinstance(raw, bool):
            return self.entity("IfcBoolean", raw)
        if isinstance(raw, int) and not isinstance(raw, bool):
            return self.entity("IfcInteger", raw)
        if isinstance(raw, float):
            return self.entity("IfcReal", raw)
        return self.entity("IfcLabel", str(raw))

    def setup_project(self) -> tuple[object, object, object, object, object]:
        spatial = PROJECT_SPEC.spatial
        room_type = PROJECT_SPEC.asset_types_by_id[spatial.space_type_id]
        room = PROJECT_SPEC.occurrences_by_id[spatial.space_occurrence_id]
        length_unit = self.entity(
            "IfcSIUnit", UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE"
        )
        area_unit = self.entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")
        volume_unit = self.entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
        unit_assignment = self.entity(
            "IfcUnitAssignment", Units=[length_unit, area_unit, volume_unit]
        )
        self.body_context = self.entity(
            "IfcGeometricRepresentationContext",
            ContextIdentifier="Model",
            ContextType="Model",
            CoordinateSpaceDimension=3,
            Precision=1.0e-5,
            WorldCoordinateSystem=self.axis3d(),
        )

        project = self.root("IfcProject", spatial.project_ifc_name)
        project.RepresentationContexts = [self.body_context]
        project.UnitsInContext = unit_assignment

        site = self.root("IfcSite", spatial.site_ifc_name, CompositionType="ELEMENT")
        building = self.root(
            "IfcBuilding", spatial.building_ifc_name, CompositionType="ELEMENT"
        )
        storey = self.root(
            "IfcBuildingStorey",
            spatial.storey_ifc_name,
            CompositionType="ELEMENT",
            Elevation=spatial.storey_elevation_mm,
        )
        room_length, room_width, room_height = spatial.space_dimensions_mm
        space = self.root(
            "IfcSpace",
            spatial.space_ifc_name,
            guid_key=f"root:occurrence:{room.occurrence_id}",
            ObjectType=room.object_type,
            ObjectPlacement=self.placement(room.origin_mm),
            Representation=self.box_representation(
                spatial.space_ifc_name,
                room_length,
                room_width,
                room_height,
                room.extrusion_axis,
            ),
            LongName=spatial.space_long_name,
            CompositionType="ELEMENT",
            PredefinedType="INTERNAL",
            ElevationWithFlooring=0.0,
        )
        self.add_pset(
            space,
            "Pset_OpenBIMAsset",
            {
                "AssetID": room.occurrence_id,
                "TypeID": room.type_id,
                "Category": room_type.category,
                "SourceTool": spatial.semantic_source_tool,
                "SystemName": "",
                "MaterialName": room.material,
                "MachineReadable": True,
                **room.properties,
            },
        )
        self.add_pset(
            space,
            "Pset_AssetGeometry",
            {
                "GeometryKind": room.geometry,
                "DimensionScheduleMM": " x ".join(
                    str(value) for value in room.dimensions_mm
                ),
                "PlacementMM": ", ".join(str(value) for value in room.origin_mm),
            },
        )
        self.rel_aggregates("Project contains site", project, [site])
        self.rel_aggregates("Site contains building", site, [building])
        self.rel_aggregates("Building contains storey", building, [storey])
        self.rel_aggregates("Storey contains mechanical room space", storey, [space])
        self.products_by_asset[room.occurrence_id] = space
        self.products_by_name[space.Name] = space
        return project, site, building, storey, space

    def rel_aggregates(self, name: str, parent, children: list[object]) -> None:
        self.entity(
            "IfcRelAggregates",
            GlobalId=guid(f"rel-aggregates:{name}"),
            OwnerHistory=None,
            Name=name,
            Description=None,
            RelatingObject=parent,
            RelatedObjects=children,
        )

    def rel_contained(self, name: str, structure, products: list[object]) -> None:
        self.entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId=guid(f"rel-contained:{name}"),
            OwnerHistory=None,
            Name=name,
            Description=None,
            RelatedElements=products,
            RelatingStructure=structure,
        )

    def shape_representation(self, item, representation_type: str = "SweptSolid"):
        return self.entity(
            "IfcProductDefinitionShape",
            Name=None,
            Description=None,
            Representations=[
                self.entity(
                    "IfcShapeRepresentation",
                    ContextOfItems=self.body_context,
                    RepresentationIdentifier="Body",
                    RepresentationType=representation_type,
                    Items=[item],
                )
            ],
        )

    def box_representation(
        self,
        name: str,
        length: float,
        width: float,
        height: float,
        axis: tuple[float, float, float] = (0.0, 0.0, 1.0),
    ):
        profile = self.entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            ProfileName=f"{name}_Profile",
            Position=None,
            XDim=float(length),
            YDim=float(width),
        )
        solid = self.entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=self.axis3d(
                axis=axis, ref=self.perpendicular_reference(axis)
            ),
            ExtrudedDirection=self.direction((0.0, 0.0, 1.0)),
            Depth=float(height),
        )
        return self.shape_representation(solid)

    def cylinder_representation(
        self,
        name: str,
        radius: float,
        depth: float,
        axis: tuple[float, float, float],
    ):
        profile = self.entity(
            "IfcCircleProfileDef",
            ProfileType="AREA",
            ProfileName=f"{name}_Profile",
            Position=None,
            Radius=float(radius),
        )
        solid = self.entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=self.axis3d(
                axis=axis, ref=self.perpendicular_reference(axis)
            ),
            ExtrudedDirection=self.direction((0.0, 0.0, 1.0)),
            Depth=float(depth),
        )
        return self.shape_representation(solid)

    def representation_for(self, spec: ProductSpec):
        if spec.geometry == "cylinder":
            radius, depth = spec.dimensions_mm
            return self.cylinder_representation(spec.name, radius, depth, spec.extrusion_axis)
        length, width, height = spec.dimensions_mm
        return self.box_representation(
            spec.name, length, width, height, spec.extrusion_axis
        )

    def add_pset(self, product, pset_name: str, properties: dict[str, object]) -> None:
        props = [
            self.entity(
                "IfcPropertySingleValue",
                Name=name,
                Description=None,
                NominalValue=self.value(value),
                Unit=None,
            )
            for name, value in properties.items()
        ]
        pset = self.entity(
            "IfcPropertySet",
            GlobalId=guid(f"pset:{product.GlobalId}:{pset_name}"),
            OwnerHistory=None,
            Name=pset_name,
            Description=None,
            HasProperties=props,
        )
        self.entity(
            "IfcRelDefinesByProperties",
            GlobalId=guid(f"rel-pset:{product.GlobalId}:{pset_name}"),
            OwnerHistory=None,
            Name=f"{pset_name} -> {product.Name}",
            Description=None,
            RelatedObjects=[product],
            RelatingPropertyDefinition=pset,
        )

    def material(self, name: str):
        if name not in self.materials:
            self.materials[name] = self.entity("IfcMaterial", Name=name)
        return self.materials[name]

    def assign_material(self, product, material_name: str) -> None:
        self.entity(
            "IfcRelAssociatesMaterial",
            GlobalId=guid(f"rel-material:{product.GlobalId}:{material_name}"),
            OwnerHistory=None,
            Name=f"Material -> {product.Name}",
            Description=None,
            RelatedObjects=[product],
            RelatingMaterial=self.material(material_name),
        )

    def add_product(self, spec: ProductSpec):
        product = self.root(
            spec.ifc_class,
            spec.name,
            guid_key=f"root:occurrence:{spec.asset_id}",
            ObjectType=spec.object_type or spec.category,
            ObjectPlacement=self.placement(spec.origin_mm),
            Representation=self.representation_for(spec),
            Tag=spec.asset_id,
        )
        self.products_by_asset[spec.asset_id] = product
        self.products_by_name[spec.name] = product
        self.product_specs.append(spec)
        if not product.is_a("IfcVirtualElement"):
            self.assign_material(product, spec.material)
        self.add_pset(
            product,
            "Pset_OpenBIMAsset",
            {
                "AssetID": spec.asset_id,
                "TypeID": spec.type_id,
                "Category": spec.category,
                "SourceTool": spec.source_tool,
                "SystemName": ", ".join(spec.system),
                "MaterialName": spec.material,
                "MachineReadable": True,
                **spec.properties,
            },
        )
        self.add_pset(
            product,
            "Pset_AssetGeometry",
            {
                "GeometryKind": spec.geometry,
                "DimensionScheduleMM": " x ".join(str(v) for v in spec.dimensions_mm),
                "PlacementMM": ", ".join(str(v) for v in spec.origin_mm),
            },
        )
        for port_name in spec.ports:
            self.add_port(
                product,
                spec.asset_id,
                port_name,
                spec.port_systems[port_name],
            )
        return product

    def add_port(
        self,
        product,
        asset_id: str,
        port_name: str,
        system_name: str,
    ) -> None:
        port = self.root(
            "IfcDistributionPort",
            f"{product.Name}_{port_name}",
            guid_key=f"root:port:{asset_id}:{port_name}",
            ObjectType="distribution_port",
            ObjectPlacement=None,
            Representation=None,
            FlowDirection=None,
            PredefinedType=None,
            SystemType=None,
        )
        self.ports[(asset_id, port_name)] = port
        self.add_pset(
            port,
            "Pset_OpenBIMPort",
            {
                "OccurrenceID": asset_id,
                "PortName": port_name,
                "SystemName": system_name,
            },
        )
        self.entity(
            "IfcRelConnectsPortToElement",
            GlobalId=guid(f"rel-port-element:{asset_id}:{port_name}"),
            OwnerHistory=None,
            Name=f"{port.Name} -> {product.Name}",
            Description=None,
            RelatingPort=port,
            RelatedElement=product,
        )

    def add_systems(self, names: Iterable[str]) -> None:
        definitions = {system.name: system for system in PROJECT_SPEC.systems}
        for name in names:
            definition = definitions[name]
            self.systems[name] = self.root(
                "IfcDistributionSystem",
                name,
                Description=definition.description,
                ObjectType=definition.object_type,
                LongName=definition.long_name,
                PredefinedType=None,
            )

    def assign_systems(self) -> None:
        members: dict[str, list[object]] = defaultdict(list)
        for spec in self.product_specs:
            for system_name in spec.system:
                members[system_name].append(self.products_by_asset[spec.asset_id])
        for system_name, products in members.items():
            self.entity(
                "IfcRelAssignsToGroup",
                GlobalId=guid(f"rel-system-members:{system_name}"),
                OwnerHistory=None,
                Name=f"{system_name} members",
                Description=None,
                RelatedObjects=products,
                RelatedObjectsType=None,
                RelatingGroup=self.systems[system_name],
            )

    def connect_ports(
        self,
        left: tuple[str, str],
        right: tuple[str, str],
        name: str,
        connection_id: str,
        system: str,
        realizing_asset_id: str | None = None,
    ) -> None:
        self.entity(
            "IfcRelConnectsPorts",
            GlobalId=guid(f"rel-port-connection:{connection_id}"),
            OwnerHistory=None,
            Name=name,
            Description=connection_description(
                connection_id, system, realizing_asset_id
            ),
            RelatingPort=self.ports[left],
            RelatedPort=self.ports[right],
            RealizingElement=self.products_by_asset.get(realizing_asset_id)
            if realizing_asset_id
            else None,
        )


SYSTEMS = PROJECT_SPEC.system_names


def product_schedule(project_spec: ProjectSpec | None = None) -> list[ProductSpec]:
    """Project placed products onto the legacy generator-facing schedule."""

    project = project_spec or PROJECT_SPEC
    type_by_id = project.asset_types_by_id
    room_occurrence_id = project.spatial.space_occurrence_id
    schedule: list[ProductSpec] = []
    for occurrence in project.occurrences:
        if occurrence.occurrence_id == room_occurrence_id:
            continue
        asset_type = type_by_id[occurrence.type_id]
        schedule.append(
            ProductSpec(
                asset_id=occurrence.occurrence_id,
                type_id=occurrence.type_id,
                name=occurrence.ifc_name,
                ifc_class=asset_type.ifc_class,
                category=asset_type.category,
                source_tool=asset_type.source_tool,
                material=occurrence.material,
                system=occurrence.systems,
                object_type=occurrence.object_type,
                geometry=occurrence.geometry,
                origin_mm=occurrence.origin_mm,
                dimensions_mm=occurrence.dimensions_mm,
                extrusion_axis=occurrence.extrusion_axis,
                ports=occurrence.ports,
                port_systems=dict(occurrence.port_systems),
                properties=dict(occurrence.properties),
            )
        )
    return schedule


CONNECTIVITY = [
    (
        (connection.source.occurrence_id, connection.source.port),
        (connection.target.occurrence_id, connection.target.port),
        connection.name,
    )
    for connection in PROJECT_SPEC.connections
]


def build_openbim_model() -> ifcopenshell.file:
    builder = OpenBIMBuilder()
    _, _, _, storey, _ = builder.setup_project()
    builder.add_systems(SYSTEMS)
    products = [builder.add_product(spec) for spec in product_schedule()]
    builder.rel_contained("Storey contains OpenBIM mechanical room products", storey, products)
    builder.assign_systems()
    for connection in PROJECT_SPEC.connections:
        builder.connect_ports(
            (connection.source.occurrence_id, connection.source.port),
            (connection.target.occurrence_id, connection.target.port),
            connection.name,
            connection.connection_id,
            connection.system,
            connection.realizing_occurrence_id,
        )
    return builder.model


def product_system_lookup(model: ifcopenshell.file) -> dict[int, list[str]]:
    lookup: dict[int, list[str]] = defaultdict(list)
    for rel in model.by_type("IfcRelAssignsToGroup"):
        group = rel.RelatingGroup
        if not group or not group.is_a("IfcDistributionSystem"):
            continue
        for obj in rel.RelatedObjects:
            lookup[obj.id()].append(group.Name)
    return lookup


def write_summary(model: ifcopenshell.file) -> None:
    counts = Counter(entity.is_a() for entity in model)
    products = [
        product
        for product in model.by_type("IfcProduct")
        if not product.is_a("IfcDistributionPort")
    ]
    systems = model.by_type("IfcDistributionSystem")
    psets = model.by_type("IfcPropertySet")
    port_rels = model.by_type("IfcRelConnectsPorts")
    lines = [
        "# IFC Entity Summary",
        "",
        f"File: `{IFC_PATH.relative_to(ROOT)}`",
        "",
        "This IFC is generated from `spec/mechanical_room.project.json` as the semantic",
        "source of truth for the coordination package. FreeCAD/STEP artifacts are",
        "supporting CAD views of the same mechanical-room intent.",
        "",
        "## OpenBIM QA Snapshot",
        "",
        f"- Schema: `{model.schema}`",
        f"- Non-port product count: `{len(products)}`",
        f"- Distribution systems: `{len(systems)}`",
        f"- Property sets: `{len(psets)}`",
        f"- Connected port relationships: `{len(port_rels)}`",
        f"- Building element proxies: `{counts['IfcBuildingElementProxy']}`",
        "",
        "## Entity Counts",
        "",
        "| Entity | Count |",
        "| --- | ---: |",
    ]
    for entity, count in sorted(counts.items()):
        lines.append(f"| `{entity}` | {count} |")
    lines.append("")
    lines.extend(["## Distribution Systems", "", "| System | Members |", "| --- | ---: |"])
    for system in systems:
        member_count = 0
        for rel in model.by_type("IfcRelAssignsToGroup"):
            if rel.RelatingGroup == system:
                member_count += len(rel.RelatedObjects)
        lines.append(f"| `{system.Name}` | {member_count} |")
    lines.append("")
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_inventory(model: ifcopenshell.file) -> None:
    system_lookup = product_system_lookup(model)
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INVENTORY_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["asset_id", "ifc_name", "ifc_class", "systems", "category"],
            lineterminator="\n",
        )
        writer.writeheader()
        for product in model.by_type("IfcProduct"):
            if product.is_a("IfcDistributionPort"):
                continue
            if any(product.is_a(ifc_class) for ifc_class in ("IfcSite", "IfcBuilding", "IfcBuildingStorey")):
                continue
            asset_id = getattr(product, "Tag", None) or ""
            if product.is_a("IfcSpace") and product.Name == PROJECT_SPEC.spatial.space_ifc_name:
                asset_id = PROJECT_SPEC.spatial.space_occurrence_id
            if not asset_id:
                continue
            category = ""
            for rel in model.by_type("IfcRelDefinesByProperties"):
                if product not in rel.RelatedObjects:
                    continue
                pset = rel.RelatingPropertyDefinition
                if pset and pset.Name == "Pset_OpenBIMAsset":
                    for prop in pset.HasProperties:
                        if prop.Name == "Category":
                            category = str(prop.NominalValue.wrappedValue)
            writer.writerow(
                {
                    "asset_id": asset_id,
                    "ifc_name": product.Name,
                    "ifc_class": product.is_a(),
                    "systems": ";".join(system_lookup.get(product.id(), [])),
                    "category": category,
                }
            )


def patch_bim_map_from_ifc(model: ifcopenshell.file) -> None:
    if not BIM_MAP_PATH.exists():
        return
    products_by_tag = {
        getattr(product, "Tag", None): product
        for product in model.by_type("IfcProduct")
        if getattr(product, "Tag", None)
    }
    products_by_tag["room_shell_001"] = next(
        product
        for product in model.by_type("IfcSpace")
        if product.Name == PROJECT_SPEC.spatial.space_ifc_name
    )
    rows: list[dict[str, str]] = []
    with BIM_MAP_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        for row in reader:
            product = products_by_tag.get(row["asset_id"])
            if product:
                row["freecad_object_name"] = product.Name
                row["ifc_class"] = product.is_a()
            rows.append(row)
    with BIM_MAP_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_openbim_outputs(model: ifcopenshell.file) -> None:
    IFC_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.write(IFC_PATH)
    write_summary(model)
    write_inventory(model)
    patch_bim_map_from_ifc(model)
