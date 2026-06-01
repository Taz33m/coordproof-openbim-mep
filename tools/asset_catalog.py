"""Canonical asset catalog for manifest and validation generation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Asset:
    asset_id: str
    display_name: str
    category: str
    source_tool: str
    ifc_class: str
    parameters: dict[str, object] = field(default_factory=dict)
    exports: dict[str, str] = field(default_factory=dict)
    notes: str = ""


CADQUERY_ASSETS: list[Asset] = [
    Asset(
        "support_pipe_bracket_type_a",
        "Pipe Support Bracket Type A",
        "mechanical_support",
        "CadQuery",
        "IfcMechanicalFastener",
        {
            "length_mm": 220,
            "width_mm": 120,
            "height_mm": 300,
            "pipe_diameter_mm": 60,
            "bolt_spacing_mm": 150,
            "material_tag": "painted_steel",
        },
        {
            "step": "exports/step/support_pipe_bracket_type_a.step",
            "stl": "exports/stl/support_pipe_bracket_type_a.stl",
        },
        "Parametric floor-mounted support bracket for a horizontal pipe run.",
    ),
    Asset(
        "support_duct_hanger_type_a",
        "Duct Hanger Type A",
        "mechanical_support",
        "CadQuery",
        "IfcMechanicalFastener",
        {
            "duct_width_mm": 420,
            "duct_height_mm": 220,
            "height_mm": 520,
            "rod_diameter_mm": 12,
            "material_tag": "galvanized_steel",
        },
        {
            "step": "exports/step/support_duct_hanger_type_a.step",
            "stl": "exports/stl/support_duct_hanger_type_a.stl",
        },
        "Simple trapeze hanger assembly for rectangular ductwork.",
    ),
    Asset(
        "cable_tray_overhead_001",
        "Overhead Cable Tray Segment",
        "electrical_routing",
        "CadQuery",
        "IfcCableCarrierSegment",
        {
            "length_mm": 900,
            "width_mm": 220,
            "height_mm": 80,
            "thickness_mm": 4,
            "material_tag": "perforated_aluminum",
        },
        {
            "step": "exports/step/cable_tray_overhead_001.step",
            "stl": "exports/stl/cable_tray_overhead_001.stl",
        },
        "Perforated U-channel tray segment for control/electrical routing.",
    ),
    Asset(
        "equipment_base_type_a",
        "Equipment Base Type A",
        "mechanical_equipment",
        "CadQuery",
        "IfcFooting",
        {
            "length_mm": 1200,
            "width_mm": 800,
            "height_mm": 160,
            "bolt_diameter_mm": 18,
            "material_tag": "concrete",
        },
        {
            "step": "exports/step/equipment_base_type_a.step",
            "stl": "exports/stl/equipment_base_type_a.stl",
        },
        "Concrete housekeeping pad with anchor bolt holes.",
    ),
    Asset(
        "equipment_pump_skid_001",
        "Pump Skid Frame",
        "mechanical_equipment",
        "CadQuery",
        "IfcElementAssembly",
        {
            "length_mm": 1100,
            "width_mm": 520,
            "height_mm": 180,
            "rail_width_mm": 70,
            "material_tag": "painted_steel",
        },
        {
            "step": "exports/step/equipment_pump_skid_001.step",
            "stl": "exports/stl/equipment_pump_skid_001.stl",
        },
        "Steel skid frame placeholder for pump assembly support.",
    ),
    Asset(
        "sleeve_wall_penetration_type_a",
        "Wall Penetration Sleeve Type A",
        "penetration",
        "CadQuery",
        "IfcBuildingElementPart",
        {
            "pipe_diameter_mm": 110,
            "wall_thickness_mm": 200,
            "clearance_mm": 30,
            "material_tag": "steel_sleeve",
        },
        {
            "step": "exports/step/sleeve_wall_penetration_type_a.step",
            "stl": "exports/stl/sleeve_wall_penetration_type_a.stl",
        },
        "Cylindrical sleeve for pipe or duct penetration through a wall.",
    ),
    Asset(
        "pipe_clamp_type_a",
        "Pipe Clamp Type A",
        "mechanical_support",
        "CadQuery",
        "IfcMechanicalFastener",
        {
            "pipe_diameter_mm": 60,
            "width_mm": 45,
            "thickness_mm": 10,
            "bolt_diameter_mm": 10,
            "material_tag": "galvanized_steel",
        },
        {
            "step": "exports/step/pipe_clamp_type_a.step",
            "stl": "exports/stl/pipe_clamp_type_a.stl",
        },
        "Ring clamp with mounting ears for small-diameter pipe support.",
    ),
    Asset(
        "duct_main_001",
        "Main Rectangular Duct Segment",
        "ductwork",
        "CadQuery",
        "IfcDuctSegment",
        {
            "length_mm": 900,
            "duct_width_mm": 420,
            "duct_height_mm": 220,
            "wall_thickness_mm": 6,
            "material_tag": "galvanized_sheet_metal",
        },
        {
            "step": "exports/step/duct_main_001.step",
            "stl": "exports/stl/duct_main_001.stl",
        },
        "Hollow rectangular duct segment for main air distribution route.",
    ),
    Asset(
        "plate_mounting_type_a",
        "Mounting Plate Type A",
        "mechanical_support",
        "CadQuery",
        "IfcMechanicalFastener",
        {
            "length_mm": 260,
            "width_mm": 160,
            "thickness_mm": 12,
            "bolt_diameter_mm": 14,
            "bolt_spacing_mm": 190,
            "material_tag": "steel",
        },
        {
            "step": "exports/step/plate_mounting_type_a.step",
            "stl": "exports/stl/plate_mounting_type_a.stl",
        },
        "Generic slotted support plate for wall or floor mounting.",
    ),
]


OPENSCAD_ASSETS: list[Asset] = [
    Asset(
        "openscad_pipe_clamp_type_b",
        "OpenSCAD Pipe Clamp Type B",
        "mechanical_support",
        "OpenSCAD",
        "IfcMechanicalFastener",
        {"pipe_diameter_mm": 50, "thickness_mm": 8, "width_mm": 35},
        {
            "scad": "openscad/pipe_clamp.scad",
            "stl": "exports/stl/openscad_pipe_clamp_type_b.stl",
        },
        "Declarative OpenSCAD pipe clamp component example.",
    ),
    Asset(
        "openscad_bracket_plate_type_b",
        "OpenSCAD Bracket Plate Type B",
        "mechanical_support",
        "OpenSCAD",
        "IfcMechanicalFastener",
        {"length_mm": 180, "width_mm": 90, "thickness_mm": 10},
        {
            "scad": "openscad/bracket_plate.scad",
            "stl": "exports/stl/openscad_bracket_plate_type_b.stl",
        },
        "Slotted bracket plate with top-level parameters.",
    ),
    Asset(
        "openscad_cable_tray_segment_type_b",
        "OpenSCAD Cable Tray Segment Type B",
        "electrical_routing",
        "OpenSCAD",
        "IfcCableCarrierSegment",
        {"length_mm": 500, "width_mm": 160, "height_mm": 60},
        {
            "scad": "openscad/cable_tray_segment.scad",
            "stl": "exports/stl/openscad_cable_tray_segment_type_b.stl",
        },
        "Simple U-channel cable tray with repeated perforations.",
    ),
    Asset(
        "openscad_duct_connector_type_b",
        "OpenSCAD Duct Connector Type B",
        "ductwork",
        "OpenSCAD",
        "IfcFlowFitting",
        {"duct_width_mm": 360, "duct_height_mm": 180, "thickness_mm": 5},
        {
            "scad": "openscad/duct_connector.scad",
            "stl": "exports/stl/openscad_duct_connector_type_b.stl",
        },
        "Flanged rectangular duct connector.",
    ),
]


BIM_ASSETS: list[Asset] = [
    Asset(
        "room_shell_001",
        "Mechanical Room Shell",
        "architectural_shell",
        "FreeCAD BIM",
        "IfcSpace",
        {"length_mm": 6000, "width_mm": 4200, "height_mm": 3200},
        {
            "ifc": "bim/mechanical_room.ifc",
            "freecad_review_ifc": "bim/mechanical_room_freecad_review.ifc",
            "freecad": "freecad/mechanical_room.FCStd",
            "freecad_bim": "freecad/mechanical_room_bim.FCStd",
            "step": "exports/step/mechanical_room_assembly.step",
        },
        "Room volume and enclosing architectural shell.",
    ),
    Asset(
        "slab_concrete_base_001",
        "Concrete Slab Base",
        "architectural_shell",
        "FreeCAD BIM",
        "IfcSlab",
        {"length_mm": 6000, "width_mm": 4200, "height_mm": 200},
        {"ifc": "bim/mechanical_room.ifc"},
        "Base slab for the mechanical room.",
    ),
    Asset(
        "wall_north_001",
        "North Wall",
        "architectural_shell",
        "FreeCAD BIM",
        "IfcWall",
        {"length_mm": 6000, "height_mm": 3200, "thickness_mm": 200},
        {"ifc": "bim/mechanical_room.ifc"},
        "North architectural boundary wall.",
    ),
    Asset(
        "wall_south_001",
        "South Wall",
        "architectural_shell",
        "FreeCAD BIM",
        "IfcWall",
        {"length_mm": 6000, "height_mm": 3200, "thickness_mm": 200},
        {"ifc": "bim/mechanical_room.ifc"},
        "South architectural boundary wall.",
    ),
    Asset(
        "wall_east_001",
        "East Wall",
        "architectural_shell",
        "FreeCAD BIM",
        "IfcWall",
        {"length_mm": 4200, "height_mm": 3200, "thickness_mm": 200},
        {"ifc": "bim/mechanical_room.ifc"},
        "East architectural boundary wall.",
    ),
    Asset(
        "wall_west_001",
        "West Wall",
        "architectural_shell",
        "FreeCAD BIM",
        "IfcWall",
        {"length_mm": 4200, "height_mm": 3200, "thickness_mm": 200},
        {"ifc": "bim/mechanical_room.ifc"},
        "West architectural boundary wall.",
    ),
    Asset(
        "door_access_001",
        "Access Door",
        "architectural_shell",
        "FreeCAD BIM",
        "IfcDoor",
        {"width_mm": 1000, "height_mm": 2100},
        {"ifc": "bim/mechanical_room.ifc"},
        "Primary access opening in the south wall.",
    ),
    Asset(
        "equipment_ahu_001",
        "Air Handling Unit AHU-1",
        "mechanical_equipment",
        "FreeCAD BIM",
        "IfcUnitaryEquipment",
        {"length_mm": 1500, "width_mm": 850, "height_mm": 1100},
        {"ifc": "bim/mechanical_room.ifc"},
        "Main packaged air-handling unit with filter, coil, fan, and service-access context in the IFC schedule.",
    ),
    Asset(
        "pipe_supply_001",
        "Supply Pipe Run",
        "flow_segment",
        "FreeCAD BIM",
        "IfcPipeSegment",
        {"pipe_diameter_mm": 80, "length_mm": 3600},
        {"ifc": "bim/mechanical_room.ifc"},
        "CHWS supply pipe route coordinated with valves, support, and AHU coil connection.",
    ),
    Asset(
        "pipe_return_001",
        "Return Pipe Run",
        "flow_segment",
        "FreeCAD BIM",
        "IfcPipeSegment",
        {"pipe_diameter_mm": 80, "length_mm": 3600},
        {"ifc": "bim/mechanical_room.ifc"},
        "CHWR return pipe route coordinated with valves, support, and AHU coil connection.",
    ),
    Asset(
        "clearance_ahu_service_zone_001",
        "AHU Service Clearance Zone",
        "clearance_zone",
        "FreeCAD BIM",
        "IfcVirtualElement",
        {"length_mm": 1800, "width_mm": 1000, "height_mm": 1900},
        {"ifc": "bim/mechanical_room.ifc"},
        "Rule-based transparent clearance volume for AHU service access.",
    ),
    Asset(
        "mechanical_room_ifc_001",
        "Mechanical Room IFC Export",
        "bim_export",
        "IfcOpenShell",
        "IfcProject",
        {},
        {
            "ifc": "bim/mechanical_room.ifc",
            "semantic_inventory_csv": "bim/openbim_semantic_inventory.csv",
            "entity_summary_md": "bim/ifc_entity_summary.md",
        },
        "Programmatic IFC export used for validation and review.",
    ),
]


IFC_DETAIL_ASSETS: list[Asset] = [
    Asset("ahu_filter_001", "AHU Filter 01", "mechanical_equipment", "IfcOpenShell", "IfcFilter", {"length_mm": 120, "width_mm": 800, "height_mm": 760}, {"ifc": "bim/mechanical_room.ifc"}, "Filter section tracked as an individual IFC product."),
    Asset("ahu_coil_001", "AHU Coil 01", "mechanical_equipment", "IfcOpenShell", "IfcCoil", {"length_mm": 160, "width_mm": 800, "height_mm": 760}, {"ifc": "bim/mechanical_room.ifc"}, "Cooling coil section connected to CHWS/CHWR ports."),
    Asset("ahu_fan_001", "AHU Fan 01", "mechanical_equipment", "IfcOpenShell", "IfcFan", {"radius_mm": 260, "length_mm": 420}, {"ifc": "bim/mechanical_room.ifc"}, "Fan section connected to the supply-air system."),
    Asset("pump_chws_duty_001", "Pump CHWS Duty 01", "mechanical_equipment", "IfcOpenShell", "IfcPump", {"radius_mm": 170, "length_mm": 460}, {"ifc": "bim/mechanical_room.ifc"}, "Duty chilled-water pump with connected distribution ports."),
    Asset("pump_chws_standby_001", "Pump CHWS Standby 01", "mechanical_equipment", "IfcOpenShell", "IfcPump", {"radius_mm": 170, "length_mm": 460}, {"ifc": "bim/mechanical_room.ifc"}, "Standby chilled-water pump tracked in the IFC product schedule."),
    Asset("pipe_supply_drop_001", "Pipe Supply Drop 01", "flow_segment", "IfcOpenShell", "IfcPipeSegment", {"pipe_radius_mm": 40, "length_mm": 800}, {"ifc": "bim/mechanical_room.ifc"}, "Vertical CHWS drop connecting the overhead pipe rack to the AHU coil."),
    Asset("pipe_return_drop_001", "Pipe Return Drop 01", "flow_segment", "IfcOpenShell", "IfcPipeSegment", {"pipe_radius_mm": 40, "length_mm": 810}, {"ifc": "bim/mechanical_room.ifc"}, "Vertical CHWR drop connecting the AHU coil back to the return rack."),
    Asset("valve_chws_isolation_001", "Valve CHWS Isolation 01", "flow_controller", "IfcOpenShell", "IfcValve", {"radius_mm": 80, "length_mm": 140}, {"ifc": "bim/mechanical_room.ifc"}, "CHWS isolation valve tracked as a flow controller."),
    Asset("valve_chws_balancing_001", "Valve CHWS Balancing 01", "flow_controller", "IfcOpenShell", "IfcValve", {"radius_mm": 80, "length_mm": 140}, {"ifc": "bim/mechanical_room.ifc"}, "CHWS balancing valve tracked as a flow controller."),
    Asset("valve_chwr_isolation_001", "Valve CHWR Isolation 01", "flow_controller", "IfcOpenShell", "IfcValve", {"radius_mm": 80, "length_mm": 140}, {"ifc": "bim/mechanical_room.ifc"}, "CHWR isolation valve tracked as a flow controller."),
    Asset("valve_chwr_balancing_001", "Valve CHWR Balancing 01", "flow_controller", "IfcOpenShell", "IfcValve", {"radius_mm": 80, "length_mm": 140}, {"ifc": "bim/mechanical_room.ifc"}, "CHWR balancing valve tracked as a flow controller."),
    Asset("pipe_fitting_chws_elbow_001", "Pipe Fitting CHWS Elbow 01", "flow_fitting", "IfcOpenShell", "IfcPipeFitting", {"radius_mm": 60, "length_mm": 120}, {"ifc": "bim/mechanical_room.ifc"}, "CHWS elbow fitting at the pipe-drop transition."),
    Asset("pipe_fitting_chwr_elbow_001", "Pipe Fitting CHWR Elbow 01", "flow_fitting", "IfcOpenShell", "IfcPipeFitting", {"radius_mm": 60, "length_mm": 120}, {"ifc": "bim/mechanical_room.ifc"}, "CHWR elbow fitting at the pipe-drop transition."),
    Asset("sensor_chws_pressure_001", "Sensor CHWS Pressure 01", "instrumentation", "IfcOpenShell", "IfcSensor", {"radius_mm": 55, "length_mm": 80}, {"ifc": "bim/mechanical_room.ifc"}, "Pressure sensor on the CHWS rack."),
    Asset("duct_branch_001", "Duct Branch 01", "ductwork", "IfcOpenShell", "IfcDuctSegment", {"length_mm": 650, "width_mm": 360, "height_mm": 180}, {"ifc": "bim/mechanical_room.ifc"}, "Branch duct segment connected to the supply terminal."),
    Asset("duct_return_001", "Duct Return 01", "ductwork", "IfcOpenShell", "IfcDuctSegment", {"length_mm": 1350, "width_mm": 340, "height_mm": 180}, {"ifc": "bim/mechanical_room.ifc"}, "Return-air duct segment connected to the AHU return path."),
    Asset("damper_fire_001", "Damper Fire 01", "flow_controller", "IfcOpenShell", "IfcDamper", {"length_mm": 120, "width_mm": 420, "height_mm": 220}, {"ifc": "bim/mechanical_room.ifc"}, "Fire damper tracked in the supply-air distribution system."),
    Asset("air_terminal_supply_001", "Air Terminal Supply Diffuser 01", "terminal", "IfcOpenShell", "IfcAirTerminal", {"length_mm": 450, "width_mm": 450, "height_mm": 60}, {"ifc": "bim/mechanical_room.ifc"}, "Supply diffuser terminal connected to the branch duct."),
    Asset("air_terminal_return_001", "Air Terminal Return Grille 01", "terminal", "IfcOpenShell", "IfcAirTerminal", {"length_mm": 420, "width_mm": 420, "height_mm": 60}, {"ifc": "bim/mechanical_room.ifc"}, "Return grille terminal connected to the return-air system."),
    Asset("cable_tray_drop_001", "Cable Tray Drop 01", "electrical_routing", "IfcOpenShell", "IfcCableCarrierSegment", {"length_mm": 120, "width_mm": 120, "height_mm": 520}, {"ifc": "bim/mechanical_room.ifc"}, "Vertical tray drop connected to the overhead cable tray route."),
]


DRAWING_ASSETS: list[Asset] = [
    Asset(
        "drawing_floor_plan_001",
        "Floor Plan Drawing",
        "drawing",
        "QCAD-compatible DXF",
        "IfcDocumentReference",
        {"scale": "1:50"},
        {"dxf": "qcad/floor_plan.dxf", "pdf": "qcad/pdf_exports/floor_plan.pdf"},
        "Room layout with walls, door, major equipment, and clearance zones.",
    ),
    Asset(
        "drawing_equipment_layout_001",
        "Equipment Layout Drawing",
        "drawing",
        "QCAD-compatible DXF",
        "IfcDocumentReference",
        {"scale": "1:50"},
        {
            "dxf": "qcad/equipment_layout.dxf",
            "pdf": "qcad/pdf_exports/equipment_layout.pdf",
        },
        "Equipment arrangement and service zones.",
    ),
    Asset(
        "drawing_section_aa_001",
        "Section A-A Coordination Drawing",
        "drawing",
        "QCAD-compatible DXF",
        "IfcDocumentReference",
        {"scale": "1:25"},
        {
            "dxf": "qcad/section_aa.dxf",
            "pdf": "qcad/pdf_exports/section_aa.pdf",
        },
        "Coordinated section showing vertical separation, room height, clearance headroom, pipe rack, duct, and tray.",
    ),
    Asset(
        "drawing_system_riser_001",
        "MEP System Riser Drawing",
        "drawing",
        "QCAD-compatible DXF",
        "IfcDocumentReference",
        {"scale": "NTS"},
        {
            "dxf": "qcad/system_riser.dxf",
            "pdf": "qcad/pdf_exports/system_riser.pdf",
        },
        "Schematic riser/connectivity sheet documenting IFC distribution systems and port relationships.",
    ),
    Asset(
        "drawing_pipe_support_detail_001",
        "Pipe Support Detail Drawing",
        "drawing",
        "QCAD-compatible DXF",
        "IfcDocumentReference",
        {"scale": "1:10"},
        {
            "dxf": "qcad/pipe_support_detail.dxf",
            "pdf": "qcad/pdf_exports/pipe_support_detail.pdf",
        },
        "Pipe support bracket dimensions and anchor layout.",
    ),
    Asset(
        "drawing_wall_penetration_detail_001",
        "Wall Penetration Detail Drawing",
        "drawing",
        "QCAD-compatible DXF",
        "IfcDocumentReference",
        {"scale": "1:10"},
        {
            "dxf": "qcad/wall_penetration_detail.dxf",
            "pdf": "qcad/pdf_exports/wall_penetration_detail.pdf",
        },
        "Sleeve and wall penetration detail.",
    ),
    Asset(
        "drawing_duct_hanger_detail_001",
        "Duct Hanger Detail Drawing",
        "drawing",
        "QCAD-compatible DXF",
        "IfcDocumentReference",
        {"scale": "1:10"},
        {
            "dxf": "qcad/duct_hanger_detail.dxf",
            "pdf": "qcad/pdf_exports/duct_hanger_detail.pdf",
        },
        "Trapeze hanger and duct support dimensions.",
    ),
]


REPORT_ASSETS: list[Asset] = [
    Asset(
        "report_coordination_001",
        "Coordination Report",
        "report",
        "Python",
        "IfcDocumentReference",
        {"source_of_truth": "tools/openbim_core.py"},
        {"md": "reports/coordination_report.md"},
        "Generated source-of-truth summary tying IFC products, systems, connections, BOM, and clearance checks together.",
    ),
    Asset(
        "report_bom_001",
        "Bill of Materials",
        "report",
        "Python",
        "IfcDocumentReference",
        {"source_of_truth": "tools/openbim_core.py"},
        {"csv": "reports/bill_of_materials.csv"},
        "Generated BOM from the same semantic product schedule used for IFC output.",
    ),
    Asset(
        "report_clash_clearance_001",
        "Clash and Clearance Report",
        "report",
        "Python",
        "IfcDocumentReference",
        {"source_of_truth": "tools/openbim_core.py"},
        {"csv": "reports/clash_clearance_report.csv"},
        "Generated bounding-box clearance and coordination checks for the mechanical-room layout.",
    ),
]


ALL_ASSETS: list[Asset] = (
    BIM_ASSETS
    + IFC_DETAIL_ASSETS
    + CADQUERY_ASSETS
    + OPENSCAD_ASSETS
    + DRAWING_ASSETS
    + REPORT_ASSETS
)

REQUIRED_CATEGORIES = {
    "architectural_shell",
    "mechanical_equipment",
    "mechanical_support",
    "flow_segment",
    "flow_controller",
    "flow_fitting",
    "ductwork",
    "electrical_routing",
    "instrumentation",
    "penetration",
    "clearance_zone",
    "drawing",
    "bim_export",
    "terminal",
    "report",
}

REQUIRED_ASSET_IDS = {
    "room_shell_001",
    "slab_concrete_base_001",
    "wall_north_001",
    "door_access_001",
    "equipment_ahu_001",
    "equipment_pump_skid_001",
    "pipe_supply_001",
    "pipe_return_001",
    "duct_main_001",
    "cable_tray_overhead_001",
    "support_pipe_bracket_type_a",
    "support_duct_hanger_type_a",
    "sleeve_wall_penetration_type_a",
    "plate_mounting_type_a",
    "clearance_ahu_service_zone_001",
}
