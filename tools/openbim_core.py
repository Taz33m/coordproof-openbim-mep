"""IFC-first OpenBIM model builder for the mechanical room pipeline.

The FreeCAD/CadQuery/OpenSCAD assets remain important geometry sources, but this
module defines the BIM truth model directly in IFC terms: spatial hierarchy,
MEP classes, systems, properties, ports, and validation-friendly inventory.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import ifcopenshell
import ifcopenshell.guid


ROOT = Path(__file__).resolve().parents[1]
IFC_PATH = ROOT / "bim" / "mechanical_room.ifc"
SUMMARY_PATH = ROOT / "bim" / "ifc_entity_summary.md"
BIM_MAP_PATH = ROOT / "bim" / "bim_object_map.csv"
INVENTORY_PATH = ROOT / "bim" / "openbim_semantic_inventory.csv"


def guid() -> str:
    return ifcopenshell.guid.new()


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
    properties: dict[str, object] = field(default_factory=dict)


class OpenBIMBuilder:
    def __init__(self) -> None:
        self.model = ifcopenshell.file(schema="IFC4")
        self.body_context = None
        self.materials: dict[str, object] = {}
        self.products_by_asset: dict[str, object] = {}
        self.products_by_name: dict[str, object] = {}
        self.ports: dict[tuple[str, str], object] = {}
        self.systems: dict[str, object] = {}
        self.product_specs: list[ProductSpec] = []

    def entity(self, ifc_class: str, *args, **kwargs):
        return self.model.create_entity(ifc_class, *args, **kwargs)

    def root(self, ifc_class: str, name: str, **kwargs):
        return self.entity(
            ifc_class,
            GlobalId=guid(),
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

        project = self.root("IfcProject", "Project_CoordProof_MechanicalRoom")
        project.RepresentationContexts = [self.body_context]
        project.UnitsInContext = unit_assignment

        site = self.root("IfcSite", "Site_OpenBIM_Testbed", CompositionType="ELEMENT")
        building = self.root(
            "IfcBuilding", "Building_MechanicalLab", CompositionType="ELEMENT"
        )
        storey = self.root(
            "IfcBuildingStorey",
            "Storey_MechanicalLevel_01",
            CompositionType="ELEMENT",
            Elevation=0.0,
        )
        space = self.root(
            "IfcSpace",
            "Space_MechanicalRoom_001",
            ObjectType="mechanical_room",
            ObjectPlacement=self.placement((0.0, 0.0, 0.0)),
            Representation=self.box_representation("Space_MechanicalRoom_001", 6000, 4200, 3200),
            LongName="Mechanical Room Coordination Space",
            CompositionType="ELEMENT",
            PredefinedType="INTERNAL",
            ElevationWithFlooring=0.0,
        )
        self.add_pset(
            space,
            "Pset_OpenBIMAsset",
            {
                "AssetID": "room_shell_001",
                "Category": "architectural_shell",
                "SourceTool": "IfcOpenShell",
                "MachineReadable": True,
            },
        )

        self.rel_aggregates("Project contains site", project, [site])
        self.rel_aggregates("Site contains building", site, [building])
        self.rel_aggregates("Building contains storey", building, [storey])
        self.rel_aggregates("Storey contains mechanical room space", storey, [space])
        self.products_by_asset["room_shell_001"] = space
        self.products_by_name[space.Name] = space
        return project, site, building, storey, space

    def rel_aggregates(self, name: str, parent, children: list[object]) -> None:
        self.entity(
            "IfcRelAggregates",
            GlobalId=guid(),
            OwnerHistory=None,
            Name=name,
            Description=None,
            RelatingObject=parent,
            RelatedObjects=children,
        )

    def rel_contained(self, name: str, structure, products: list[object]) -> None:
        self.entity(
            "IfcRelContainedInSpatialStructure",
            GlobalId=guid(),
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

    def box_representation(self, name: str, length: float, width: float, height: float):
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
            Position=self.axis3d(),
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
            Position=self.axis3d(),
            ExtrudedDirection=self.direction(axis),
            Depth=float(depth),
        )
        return self.shape_representation(solid)

    def representation_for(self, spec: ProductSpec):
        if spec.geometry == "cylinder":
            radius, depth = spec.dimensions_mm
            return self.cylinder_representation(spec.name, radius, depth, spec.extrusion_axis)
        length, width, height = spec.dimensions_mm
        return self.box_representation(spec.name, length, width, height)

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
            GlobalId=guid(),
            OwnerHistory=None,
            Name=pset_name,
            Description=None,
            HasProperties=props,
        )
        self.entity(
            "IfcRelDefinesByProperties",
            GlobalId=guid(),
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
            GlobalId=guid(),
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
            ObjectType=spec.object_type or spec.category,
            ObjectPlacement=self.placement(spec.origin_mm),
            Representation=self.representation_for(spec),
            Tag=spec.asset_id,
        )
        self.products_by_asset[spec.asset_id] = product
        self.products_by_name[spec.name] = product
        self.product_specs.append(spec)
        self.assign_material(product, spec.material)
        self.add_pset(
            product,
            "Pset_OpenBIMAsset",
            {
                "AssetID": spec.asset_id,
                "Category": spec.category,
                "SourceTool": spec.source_tool,
                "SystemName": ", ".join(spec.system) if spec.system else "Architectural",
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
            self.add_port(product, spec.asset_id, port_name)
        return product

    def add_port(self, product, asset_id: str, port_name: str) -> None:
        port = self.root(
            "IfcDistributionPort",
            f"{product.Name}_{port_name}",
            ObjectType="distribution_port",
            ObjectPlacement=None,
            Representation=None,
            FlowDirection=None,
            PredefinedType=None,
            SystemType=None,
        )
        self.ports[(asset_id, port_name)] = port
        self.entity(
            "IfcRelConnectsPortToElement",
            GlobalId=guid(),
            OwnerHistory=None,
            Name=f"{port.Name} -> {product.Name}",
            Description=None,
            RelatingPort=port,
            RelatedElement=product,
        )

    def add_systems(self, names: Iterable[str]) -> None:
        for name in names:
            self.systems[name] = self.root(
                "IfcDistributionSystem",
                name,
                ObjectType=name.replace("System_", "").lower(),
                LongName=name.replace("_", " "),
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
                GlobalId=guid(),
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
        realizing_asset_id: str | None = None,
    ) -> None:
        self.entity(
            "IfcRelConnectsPorts",
            GlobalId=guid(),
            OwnerHistory=None,
            Name=name,
            Description=None,
            RelatingPort=self.ports[left],
            RelatedPort=self.ports[right],
            RealizingElement=self.products_by_asset.get(realizing_asset_id)
            if realizing_asset_id
            else None,
        )


SYSTEMS = (
    "System_CHWS",
    "System_CHWR",
    "System_SupplyAir",
    "System_ReturnAir",
    "System_ElectricalRouting",
)


def product_schedule() -> list[ProductSpec]:
    return [
        ProductSpec(
            "slab_concrete_base_001",
            "Slab_Concrete_Base",
            "IfcSlab",
            "architectural_shell",
            "FreeCAD BIM",
            "cast_in_place_concrete",
            dimensions_mm=(6000, 4200, 200),
        ),
        ProductSpec("wall_north_001", "Wall_North_01", "IfcWall", "architectural_shell", "FreeCAD BIM", "concrete", origin_mm=(0, 4000, 200), dimensions_mm=(6000, 200, 3000)),
        ProductSpec("wall_south_001", "Wall_South_01", "IfcWall", "architectural_shell", "FreeCAD BIM", "concrete", origin_mm=(0, 0, 200), dimensions_mm=(6000, 200, 3000)),
        ProductSpec("wall_east_001", "Wall_East_01", "IfcWall", "architectural_shell", "FreeCAD BIM", "concrete", origin_mm=(5800, 0, 200), dimensions_mm=(200, 4200, 3000)),
        ProductSpec("wall_west_001", "Wall_West_01", "IfcWall", "architectural_shell", "FreeCAD BIM", "concrete", origin_mm=(0, 0, 200), dimensions_mm=(200, 4200, 3000)),
        ProductSpec("door_access_001", "Door_Access_01", "IfcDoor", "architectural_shell", "FreeCAD BIM", "painted_hollow_metal", origin_mm=(2500, 0, 200), dimensions_mm=(1000, 70, 2100)),
        ProductSpec("equipment_base_type_a", "EquipmentPad_AHU_01", "IfcFooting", "mechanical_equipment", "CadQuery", "concrete", origin_mm=(650, 580, 200), dimensions_mm=(1800, 1100, 160)),
        ProductSpec("equipment_ahu_001", "Equipment_AHU_01", "IfcUnitaryEquipment", "mechanical_equipment", "FreeCAD BIM", "painted_steel", system=("System_SupplyAir", "System_ReturnAir"), origin_mm=(850, 780, 360), dimensions_mm=(1500, 850, 1100), ports=("return_air_in", "supply_air_out", "chws_in", "chwr_out")),
        ProductSpec("ahu_filter_001", "AHU_Filter_01", "IfcFilter", "mechanical_equipment", "IfcOpenShell", "filter_media", system=("System_SupplyAir",), origin_mm=(890, 805, 500), dimensions_mm=(120, 800, 760), ports=("air_in", "air_out")),
        ProductSpec("ahu_coil_001", "AHU_Coil_01", "IfcCoil", "mechanical_equipment", "IfcOpenShell", "copper_aluminum_coil", system=("System_SupplyAir", "System_CHWS", "System_CHWR"), origin_mm=(1040, 805, 500), dimensions_mm=(160, 800, 760), ports=("air_in", "air_out", "water_in", "water_out")),
        ProductSpec("ahu_fan_001", "AHU_Fan_01", "IfcFan", "mechanical_equipment", "IfcOpenShell", "painted_steel", system=("System_SupplyAir",), geometry="cylinder", origin_mm=(1280, 1175, 760), dimensions_mm=(260, 420), extrusion_axis=(1.0, 0.0, 0.0), ports=("air_in", "air_out")),
        ProductSpec("equipment_pump_skid_001", "Equipment_PumpSkid_01", "IfcElementAssembly", "mechanical_equipment", "CadQuery", "painted_steel", system=("System_CHWS",), origin_mm=(3600, 650, 220), dimensions_mm=(1400, 800, 180)),
        ProductSpec("pump_chws_duty_001", "Pump_CHWS_Duty_01", "IfcPump", "mechanical_equipment", "IfcOpenShell", "painted_steel", system=("System_CHWS",), geometry="cylinder", origin_mm=(4050, 930, 560), dimensions_mm=(170, 460), extrusion_axis=(1.0, 0.0, 0.0), ports=("suction", "discharge")),
        ProductSpec("pump_chws_standby_001", "Pump_CHWS_Standby_01", "IfcPump", "mechanical_equipment", "IfcOpenShell", "painted_steel", system=("System_CHWS",), geometry="cylinder", origin_mm=(4050, 1160, 560), dimensions_mm=(170, 460), extrusion_axis=(1.0, 0.0, 0.0), ports=("suction", "discharge")),
        ProductSpec("pipe_supply_001", "Pipe_Supply_01", "IfcPipeSegment", "flow_segment", "FreeCAD BIM", "carbon_steel_chws", system=("System_CHWS",), geometry="cylinder", origin_mm=(900, 2860, 1560), dimensions_mm=(40, 3600), extrusion_axis=(1.0, 0.0, 0.0), ports=("in", "out")),
        ProductSpec("pipe_return_001", "Pipe_Return_01", "IfcPipeSegment", "flow_segment", "FreeCAD BIM", "carbon_steel_chwr", system=("System_CHWR",), geometry="cylinder", origin_mm=(900, 3060, 1410), dimensions_mm=(40, 3920), extrusion_axis=(1.0, 0.0, 0.0), ports=("in", "out")),
        ProductSpec("pipe_supply_drop_001", "Pipe_Supply_Drop_01", "IfcPipeSegment", "flow_segment", "IfcOpenShell", "carbon_steel_chws", system=("System_CHWS",), geometry="cylinder", origin_mm=(4500, 1320, 760), dimensions_mm=(40, 800), ports=("top", "bottom")),
        ProductSpec("pipe_return_drop_001", "Pipe_Return_Drop_01", "IfcPipeSegment", "flow_segment", "IfcOpenShell", "carbon_steel_chwr", system=("System_CHWR",), geometry="cylinder", origin_mm=(4820, 1320, 600), dimensions_mm=(40, 810), ports=("top", "bottom")),
        ProductSpec("valve_chws_isolation_001", "Valve_CHWS_Isolation_01", "IfcValve", "flow_controller", "IfcOpenShell", "bronze_valve_body", system=("System_CHWS",), geometry="cylinder", origin_mm=(2550, 2860, 1560), dimensions_mm=(80, 140), extrusion_axis=(1.0, 0.0, 0.0), ports=("in", "out")),
        ProductSpec("valve_chws_balancing_001", "Valve_CHWS_Balancing_01", "IfcValve", "flow_controller", "IfcOpenShell", "bronze_valve_body", system=("System_CHWS",), geometry="cylinder", origin_mm=(3120, 2860, 1560), dimensions_mm=(80, 140), extrusion_axis=(1.0, 0.0, 0.0), ports=("in", "out")),
        ProductSpec("valve_chwr_isolation_001", "Valve_CHWR_Isolation_01", "IfcValve", "flow_controller", "IfcOpenShell", "bronze_valve_body", system=("System_CHWR",), geometry="cylinder", origin_mm=(3020, 3060, 1410), dimensions_mm=(80, 140), extrusion_axis=(1.0, 0.0, 0.0), ports=("in", "out")),
        ProductSpec("valve_chwr_balancing_001", "Valve_CHWR_Balancing_01", "IfcValve", "flow_controller", "IfcOpenShell", "bronze_valve_body", system=("System_CHWR",), geometry="cylinder", origin_mm=(3650, 3060, 1410), dimensions_mm=(80, 140), extrusion_axis=(1.0, 0.0, 0.0), ports=("in", "out")),
        ProductSpec("pipe_fitting_chws_elbow_001", "PipeFitting_CHWS_Elbow_01", "IfcPipeFitting", "flow_fitting", "IfcOpenShell", "carbon_steel_chws", system=("System_CHWS",), geometry="cylinder", origin_mm=(4480, 2860, 1540), dimensions_mm=(60, 120), ports=("in", "out")),
        ProductSpec("pipe_fitting_chwr_elbow_001", "PipeFitting_CHWR_Elbow_01", "IfcPipeFitting", "flow_fitting", "IfcOpenShell", "carbon_steel_chwr", system=("System_CHWR",), geometry="cylinder", origin_mm=(4800, 3060, 1390), dimensions_mm=(60, 120), ports=("in", "out")),
        ProductSpec("sensor_chws_pressure_001", "Sensor_CHWS_Pressure_01", "IfcSensor", "instrumentation", "IfcOpenShell", "stainless_steel", system=("System_CHWS",), geometry="cylinder", origin_mm=(2100, 2860, 1650), dimensions_mm=(55, 80), ports=("process",)),
        ProductSpec("duct_main_001", "Duct_Main_01", "IfcDuctSegment", "ductwork", "CadQuery", "galvanized_sheet_metal", system=("System_SupplyAir",), origin_mm=(900, 3300, 1800), dimensions_mm=(3600, 420, 220), ports=("in", "out")),
        ProductSpec("duct_branch_001", "Duct_Branch_01", "IfcDuctSegment", "ductwork", "IfcOpenShell", "galvanized_sheet_metal", system=("System_SupplyAir",), origin_mm=(2550, 2920, 1710), dimensions_mm=(650, 360, 180), ports=("in", "out")),
        ProductSpec("duct_return_001", "Duct_Return_01", "IfcDuctSegment", "ductwork", "IfcOpenShell", "galvanized_sheet_metal", system=("System_ReturnAir",), origin_mm=(760, 3060, 1640), dimensions_mm=(1350, 340, 180), ports=("in", "out")),
        ProductSpec("damper_fire_001", "Damper_Fire_01", "IfcDamper", "flow_controller", "IfcOpenShell", "galvanized_sheet_metal", system=("System_SupplyAir",), origin_mm=(2400, 3300, 1800), dimensions_mm=(120, 420, 220), ports=("in", "out")),
        ProductSpec("air_terminal_supply_001", "AirTerminal_SupplyDiffuser_01", "IfcAirTerminal", "terminal", "IfcOpenShell", "powder_coated_steel", system=("System_SupplyAir",), origin_mm=(3130, 2920, 1680), dimensions_mm=(450, 450, 60), ports=("in",)),
        ProductSpec("air_terminal_return_001", "AirTerminal_ReturnGrille_01", "IfcAirTerminal", "terminal", "IfcOpenShell", "powder_coated_steel", system=("System_ReturnAir",), origin_mm=(790, 3060, 1620), dimensions_mm=(420, 420, 60), ports=("out",)),
        ProductSpec("cable_tray_overhead_001", "CableTray_Overhead_01", "IfcCableCarrierSegment", "electrical_routing", "CadQuery", "perforated_aluminum", system=("System_ElectricalRouting",), origin_mm=(1200, 2200, 2150), dimensions_mm=(3200, 220, 80), ports=("in", "out")),
        ProductSpec("cable_tray_drop_001", "CableTray_Drop_01", "IfcCableCarrierSegment", "electrical_routing", "IfcOpenShell", "perforated_aluminum", system=("System_ElectricalRouting",), origin_mm=(4320, 2140, 1650), dimensions_mm=(120, 120, 520), ports=("top", "bottom")),
        ProductSpec("support_pipe_bracket_type_a", "Support_PipeBracket_01", "IfcMechanicalFastener", "mechanical_support", "CadQuery", "painted_steel", origin_mm=(1800, 2780, 200), dimensions_mm=(220, 120, 300)),
        ProductSpec("support_duct_hanger_type_a", "Support_DuctHanger_01", "IfcMechanicalFastener", "mechanical_support", "CadQuery", "galvanized_steel", origin_mm=(1950, 3260, 1750), dimensions_mm=(520, 60, 520)),
        ProductSpec("pipe_clamp_type_a", "PipeClamp_TypeA_01", "IfcMechanicalFastener", "mechanical_support", "CadQuery", "galvanized_steel", origin_mm=(1880, 2820, 1500), geometry="cylinder", dimensions_mm=(55, 45), extrusion_axis=(0.0, 1.0, 0.0)),
        ProductSpec("plate_mounting_type_a", "Plate_Mounting_01", "IfcMechanicalFastener", "mechanical_support", "CadQuery", "steel", origin_mm=(3380, 2640, 200), dimensions_mm=(260, 160, 12)),
        ProductSpec("sleeve_wall_penetration_type_a", "Sleeve_WallPenetration_01", "IfcBuildingElementPart", "penetration", "CadQuery", "steel_sleeve", origin_mm=(5800, 2600, 1440), geometry="cylinder", dimensions_mm=(85, 220), extrusion_axis=(1.0, 0.0, 0.0)),
        ProductSpec("clearance_ahu_service_zone_001", "Clearance_ServiceZone_AHU_01", "IfcVirtualElement", "clearance_zone", "FreeCAD BIM", "clearance_volume", origin_mm=(650, 1700, 200), dimensions_mm=(1800, 1000, 1900), properties={"IsClearanceZone": True, "Rule": "1000 mm AHU service zone with 1900 mm clear headroom"}),
    ]


CONNECTIVITY = [
    (("pump_chws_duty_001", "discharge"), ("pipe_supply_001", "in"), "Duty pump feeds CHWS supply"),
    (("pipe_supply_001", "out"), ("valve_chws_isolation_001", "in"), "CHWS supply enters isolation valve"),
    (("valve_chws_isolation_001", "out"), ("valve_chws_balancing_001", "in"), "CHWS isolation to balance valve"),
    (("valve_chws_balancing_001", "out"), ("pipe_fitting_chws_elbow_001", "in"), "CHWS balance valve to elbow"),
    (("pipe_fitting_chws_elbow_001", "out"), ("pipe_supply_drop_001", "top"), "CHWS elbow to drop"),
    (("pipe_supply_drop_001", "bottom"), ("ahu_coil_001", "water_in"), "CHWS drop to coil"),
    (("ahu_coil_001", "water_out"), ("pipe_return_drop_001", "bottom"), "Coil return to CHWR drop"),
    (("pipe_return_drop_001", "top"), ("pipe_fitting_chwr_elbow_001", "in"), "CHWR drop to elbow"),
    (("pipe_fitting_chwr_elbow_001", "out"), ("valve_chwr_isolation_001", "in"), "CHWR elbow to isolation valve"),
    (("valve_chwr_isolation_001", "out"), ("pipe_return_001", "in"), "CHWR valve to return pipe"),
    (("pipe_return_001", "out"), ("pump_chws_duty_001", "suction"), "CHWR return to pump suction"),
    (("equipment_ahu_001", "supply_air_out"), ("ahu_filter_001", "air_in"), "AHU supply path starts at filter"),
    (("ahu_filter_001", "air_out"), ("ahu_coil_001", "air_in"), "Filter to coil"),
    (("ahu_coil_001", "air_out"), ("ahu_fan_001", "air_in"), "Coil to fan"),
    (("ahu_fan_001", "air_out"), ("damper_fire_001", "in"), "Fan to fire damper"),
    (("damper_fire_001", "out"), ("duct_main_001", "in"), "Fire damper to main duct"),
    (("duct_main_001", "out"), ("duct_branch_001", "in"), "Main duct to branch"),
    (("duct_branch_001", "out"), ("air_terminal_supply_001", "in"), "Branch duct to diffuser"),
    (("air_terminal_return_001", "out"), ("duct_return_001", "in"), "Return grille to return duct"),
    (("duct_return_001", "out"), ("equipment_ahu_001", "return_air_in"), "Return duct to AHU"),
    (("cable_tray_overhead_001", "out"), ("cable_tray_drop_001", "top"), "Overhead tray to drop"),
]


def build_openbim_model() -> ifcopenshell.file:
    builder = OpenBIMBuilder()
    _, _, _, storey, _ = builder.setup_project()
    builder.add_systems(SYSTEMS)
    products = [builder.add_product(spec) for spec in product_schedule()]
    builder.rel_contained("Storey contains OpenBIM mechanical room products", storey, products)
    builder.assign_systems()
    for left, right, name in CONNECTIVITY:
        builder.connect_ports(left, right, name)
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
        "This IFC is generated from `tools/openbim_core.py` as the semantic",
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
            if product.is_a("IfcSpace") and product.Name == "Space_MechanicalRoom_001":
                asset_id = "room_shell_001"
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
        product for product in model.by_type("IfcSpace") if product.Name == "Space_MechanicalRoom_001"
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
