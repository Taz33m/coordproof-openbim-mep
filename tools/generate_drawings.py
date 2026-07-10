"""Generate QCAD-ready DXF drawings and portable PDF previews."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import ezdxf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas

# ezdxf otherwise embeds wall-clock timestamps and random document GUIDs on
# every save. Fixed metadata keeps source-equivalent DXF rebuilds reviewable.
ezdxf.options.write_fixed_meta_data_for_testing = True

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from openbim_core import CONNECTIVITY, ProductSpec, product_schedule  # noqa: E402

QCAD_DIR = ROOT / "qcad"
PORTABLE_PDF_DIR = ROOT / "build" / "portable" / "qcad_pdf_previews"
SPECS = {spec.asset_id: spec for spec in product_schedule()}

LAYERS = {
    "A-WALL": (7, 35),
    "A-DOOR": (3, 18),
    "A-SLAB": (8, 13),
    "M-EQUIP": (5, 25),
    "M-PIPE-SUPPLY": (4, 35),
    "M-PIPE-RETURN": (1, 35),
    "M-PIPE-FITTING": (30, 25),
    "M-DUCT": (9, 25),
    "M-SUPPORT": (2, 25),
    "E-CABLETRAY": (30, 25),
    "CLEARANCE": (96, 13),
    "DIMENSIONS": (1, 18),
    "ANNOTATIONS": (7, 18),
    "CENTERLINES": (6, 13),
    "HIDDEN": (8, 13),
    "TITLEBLOCK": (7, 35),
}


def spec(asset_id: str) -> ProductSpec:
    return SPECS[asset_id]


def box_xywh(asset_id: str) -> tuple[float, float, float, float]:
    item = spec(asset_id)
    x, y, _ = item.origin_mm
    length, width, _ = item.dimensions_mm
    return x, y, length, width


def pipe_plan(asset_id: str) -> tuple[tuple[float, float], tuple[float, float], float]:
    item = spec(asset_id)
    x, y, _ = item.origin_mm
    radius, depth = item.dimensions_mm
    if item.extrusion_axis[0]:
        return (x, y), (x + depth, y), radius * 2
    if item.extrusion_axis[1]:
        return (x, y), (x, y + depth), radius * 2
    return (x, y), (x, y), radius * 2


def setup_doc() -> ezdxf.EzDxfDocument:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for name, (color, lineweight) in LAYERS.items():
        if name not in doc.layers:
            doc.layers.add(name=name, color=color, lineweight=lineweight)
        else:
            layer = doc.layers.get(name)
            layer.dxf.color = color
            layer.dxf.lineweight = lineweight
    return doc


def rect(msp, x: float, y: float, w: float, h: float, layer: str, close: bool = True) -> None:
    points = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    if close:
        points.append((x, y))
    msp.add_lwpolyline(points, dxfattribs={"layer": layer})


def label(msp, text: str, x: float, y: float, height: float = 90, layer: str = "ANNOTATIONS") -> None:
    msp.add_text(text, dxfattribs={"layer": layer, "height": height}).set_placement((x, y))


def callout(msp, text: str, x: float, y: float, tx: float, ty: float) -> None:
    msp.add_line((x, y), (tx - 40, ty - 20), dxfattribs={"layer": "ANNOTATIONS"})
    msp.add_circle((x, y), 28, dxfattribs={"layer": "ANNOTATIONS"})
    label(msp, text, tx, ty, 60, "ANNOTATIONS")


def dim_h(msp, x1: float, x2: float, y: float, text: str) -> None:
    msp.add_line((x1, y), (x2, y), dxfattribs={"layer": "DIMENSIONS"})
    msp.add_line((x1, y - 45), (x1, y + 45), dxfattribs={"layer": "DIMENSIONS"})
    msp.add_line((x2, y - 45), (x2, y + 45), dxfattribs={"layer": "DIMENSIONS"})
    label(msp, text, (x1 + x2) / 2 - 135, y + 58, 70, "DIMENSIONS")


def dim_v(msp, x: float, y1: float, y2: float, text: str) -> None:
    msp.add_line((x, y1), (x, y2), dxfattribs={"layer": "DIMENSIONS"})
    msp.add_line((x - 45, y1), (x + 45, y1), dxfattribs={"layer": "DIMENSIONS"})
    msp.add_line((x - 45, y2), (x + 45, y2), dxfattribs={"layer": "DIMENSIONS"})
    label(msp, text, x + 58, (y1 + y2) / 2, 70, "DIMENSIONS")


def door_swing(msp, x: float, y: float, width: float) -> None:
    msp.add_line((x, y), (x + width, y), dxfattribs={"layer": "A-DOOR"})
    msp.add_arc((x, y), width, 0, 90, dxfattribs={"layer": "A-DOOR"})


def pipe_run(msp, start: tuple[float, float], end: tuple[float, float], layer: str, diameter: float = 80) -> None:
    x1, y1 = start
    x2, y2 = end
    if y1 == y2:
        offset = diameter / 2
        msp.add_line((x1, y1 - offset), (x2, y2 - offset), dxfattribs={"layer": layer})
        msp.add_line((x1, y1 + offset), (x2, y2 + offset), dxfattribs={"layer": layer})
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "CENTERLINES"})
    elif x1 == x2:
        offset = diameter / 2
        msp.add_line((x1 - offset, y1), (x2 - offset, y2), dxfattribs={"layer": layer})
        msp.add_line((x1 + offset, y1), (x2 + offset, y2), dxfattribs={"layer": layer})
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "CENTERLINES"})
    else:
        msp.add_line(start, end, dxfattribs={"layer": layer})


def valve_symbol(msp, x: float, y: float, layer: str) -> None:
    msp.add_lwpolyline([(x - 70, y - 55), (x, y), (x - 70, y + 55), (x - 70, y - 55)], dxfattribs={"layer": layer})
    msp.add_lwpolyline([(x + 70, y - 55), (x, y), (x + 70, y + 55), (x + 70, y - 55)], dxfattribs={"layer": layer})
    msp.add_circle((x, y + 95), 28, dxfattribs={"layer": layer})


def pump_symbol(msp, x: float, y: float, tag: str) -> None:
    msp.add_circle((x, y), 150, dxfattribs={"layer": "M-EQUIP"})
    msp.add_circle((x, y), 68, dxfattribs={"layer": "CENTERLINES"})
    rect(msp, x - 350, y - 95, 180, 190, "M-EQUIP")
    rect(msp, x + 155, y - 55, 220, 110, "M-EQUIP")
    label(msp, tag, x - 92, y - 28, 72, "M-EQUIP")


def ahu_plan(msp) -> None:
    ahu_x, ahu_y, ahu_l, ahu_w = box_xywh("equipment_ahu_001")
    rect(msp, ahu_x, ahu_y, ahu_l, ahu_w, "M-EQUIP")
    for asset_id in ["ahu_filter_001", "ahu_coil_001", "ahu_fan_001"]:
        item = spec(asset_id)
        x, _, _ = item.origin_mm
        if item.geometry == "cylinder":
            x += item.dimensions_mm[1] / 2
        msp.add_line((x, ahu_y), (x, ahu_y + ahu_w), dxfattribs={"layer": "M-EQUIP"})
    label(msp, "AHU-1", ahu_x + 350, ahu_y + 400, 110, "M-EQUIP")
    label(msp, "FILTER", spec("ahu_filter_001").origin_mm[0] + 5, ahu_y + ahu_w - 45, 52, "M-EQUIP")
    label(msp, "COIL", spec("ahu_coil_001").origin_mm[0] + 280, ahu_y + ahu_w - 45, 52, "M-EQUIP")
    label(msp, "FAN", spec("ahu_fan_001").origin_mm[0] + 760, ahu_y + ahu_w - 45, 52, "M-EQUIP")
    clear_x, clear_y, clear_l, clear_w = box_xywh("clearance_ahu_service_zone_001")
    rect(msp, clear_x, clear_y, clear_l, clear_w, "CLEARANCE")
    label(msp, "SERVICE CLEARANCE", clear_x + 170, clear_y + 440, 70, "CLEARANCE")


def room_shell(msp) -> None:
    slab_x, slab_y, room_l, room_w = box_xywh("slab_concrete_base_001")
    rect(msp, slab_x, slab_y, room_l, room_w, "A-WALL")
    rect(msp, slab_x + 200, slab_y + 200, room_l - 400, room_w - 400, "A-SLAB")
    door_x, door_y, door_w, door_d = box_xywh("door_access_001")
    rect(msp, door_x - 200, door_y - 80, door_w, door_d + 90, "A-DOOR")
    door_swing(msp, door_x - 200, slab_y, door_w)
    for x, label_text in [(slab_x, "A"), (slab_x + room_l / 2, "B"), (slab_x + room_l, "C")]:
        msp.add_line((x, slab_y - 250), (x, room_w + 250), dxfattribs={"layer": "CENTERLINES"})
        label(msp, label_text, x - 30, 4560, 90, "CENTERLINES")
    for y, label_text in [(slab_y, "1"), (slab_y + room_w / 2, "2"), (slab_y + room_w, "3")]:
        msp.add_line((slab_x - 350, y), (room_l + 250, y), dxfattribs={"layer": "CENTERLINES"})
        label(msp, label_text, -520, y - 30, 90, "CENTERLINES")


def north_arrow(msp, x: float, y: float) -> None:
    msp.add_line((x, y), (x, y + 360), dxfattribs={"layer": "ANNOTATIONS"})
    msp.add_lwpolyline(
        [(x, y + 430), (x - 90, y + 260), (x, y + 320), (x + 90, y + 260), (x, y + 430)],
        dxfattribs={"layer": "ANNOTATIONS"},
    )
    label(msp, "N", x - 38, y + 470, 100, "ANNOTATIONS")


def layer_table(msp, x: float, y: float) -> None:
    label(msp, "LAYER / SYSTEM", x, y + 420, 64, "ANNOTATIONS")
    items = [
        ("A-WALL", "architectural boundary"),
        ("M-EQUIP", "mechanical equipment"),
        ("M-PIPE-SUPPLY", "CHWS supply"),
        ("M-PIPE-RETURN", "CHWR return"),
        ("M-DUCT", "ductwork"),
        ("E-CABLETRAY", "cable tray"),
        ("CLEARANCE", "service clearance"),
    ]
    for i, (layer, text) in enumerate(items):
        yy = y + 350 - i * 70
        msp.add_line((x, yy), (x + 250, yy), dxfattribs={"layer": layer})
        label(msp, text, x + 300, yy - 24, 50, "ANNOTATIONS")


def title_block(msp, title: str, scale: str, sheet: str) -> None:
    rect(msp, 0, -1050, 6000, 800, "TITLEBLOCK")
    rect(msp, 3650, -1050, 2350, 800, "TITLEBLOCK")
    rect(msp, 5050, -1050, 950, 800, "TITLEBLOCK")
    label(msp, title, 180, -500, 140, "TITLEBLOCK")
    label(msp, f"Scale: {scale}", 3820, -500, 85, "TITLEBLOCK")
    label(msp, "Units: millimeters", 3820, -640, 75, "TITLEBLOCK")
    label(msp, "Revision: P01", 3820, -780, 70, "TITLEBLOCK")
    label(msp, f"Sheet: {sheet}", 5220, -500, 85, "TITLEBLOCK")
    label(msp, "Status: Portfolio QA", 5220, -640, 65, "TITLEBLOCK")
    label(msp, "Source: openbim_core.py", 5220, -780, 55, "TITLEBLOCK")
    label(msp, "CoordProof MEP Coordination Package", 180, -760, 80, "TITLEBLOCK")
    label(msp, "Generated for CAD/BIM asset review", 180, -900, 65, "TITLEBLOCK")


def legend(msp, x: float, y: float) -> None:
    items = [
        ("M-PIPE-SUPPLY", "CHWS / supply pipe"),
        ("M-PIPE-RETURN", "CHWR / return pipe"),
        ("M-DUCT", "sheet metal duct"),
        ("E-CABLETRAY", "cable tray"),
        ("CLEARANCE", "service clearance"),
    ]
    label(msp, "LEGEND", x, y + 250, 70, "ANNOTATIONS")
    for i, (layer, text) in enumerate(items):
        yy = y + 190 - i * 80
        msp.add_line((x, yy), (x + 250, yy), dxfattribs={"layer": layer})
        label(msp, text, x + 310, yy - 24, 58, "ANNOTATIONS")


def floor_plan(doc) -> None:
    msp = doc.modelspace()
    room_shell(msp)
    ahu_plan(msp)
    pump_x, pump_y, pump_l, pump_w = box_xywh("equipment_pump_skid_001")
    rect(msp, pump_x, pump_y, pump_l, pump_w, "M-EQUIP")
    for asset_id, tag in [("pump_chws_duty_001", "P-1"), ("pump_chws_standby_001", "P-2")]:
        item = spec(asset_id)
        px, py, _ = item.origin_mm
        pump_symbol(msp, px + item.dimensions_mm[1] / 2, py, tag)
    for asset_id in ["duct_main_001", "duct_branch_001"]:
        rect(msp, *box_xywh(asset_id), "M-DUCT")
    tray_x, tray_y, tray_l, tray_w = box_xywh("cable_tray_overhead_001")
    rect(msp, tray_x, tray_y, tray_l, tray_w, "E-CABLETRAY")
    for x in range(int(tray_x + 250), int(tray_x + tray_l - 100), 450):
        msp.add_line((x, tray_y), (x, tray_y + tray_w), dxfattribs={"layer": "E-CABLETRAY"})
    supply_start, supply_end, supply_diameter = pipe_plan("pipe_supply_001")
    return_start, return_end, return_diameter = pipe_plan("pipe_return_001")
    pipe_run(msp, supply_start, supply_end, "M-PIPE-SUPPLY", supply_diameter)
    pipe_run(msp, return_start, return_end, "M-PIPE-RETURN", return_diameter)
    supply_drop = spec("pipe_supply_drop_001").origin_mm
    return_drop = spec("pipe_return_drop_001").origin_mm
    pipe_run(msp, (supply_end[0], supply_end[1]), (supply_drop[0], supply_drop[1]), "M-PIPE-SUPPLY", supply_diameter)
    pipe_run(msp, (return_end[0], return_end[1]), (return_drop[0], return_drop[1]), "M-PIPE-RETURN", return_diameter)
    for asset_id, layer in [
        ("valve_chws_isolation_001", "M-PIPE-FITTING"),
        ("valve_chwr_isolation_001", "M-PIPE-FITTING"),
    ]:
        x, y, _ = spec(asset_id).origin_mm
        valve_symbol(msp, x, y, layer)
    for x in [1800, 3300, 4450]:
        rect(msp, x, 2780, 220, 120, "M-SUPPORT")
    for x in [1950, 3450, 4300]:
        rect(msp, x, 3260, 520, 60, "M-SUPPORT")
    _, _, room_l, room_w = box_xywh("slab_concrete_base_001")
    clear_x, clear_y, clear_l, clear_w = box_xywh("clearance_ahu_service_zone_001")
    dim_h(msp, 0, room_l, 4500, f"{int(room_l)} mm")
    dim_v(msp, -250, 0, room_w, f"{int(room_w)} mm")
    dim_h(msp, clear_x, clear_x + clear_l, clear_y + 140, f"AHU service zone {int(clear_l)}")
    dim_v(msp, clear_x - 40, clear_y, clear_y + clear_w, f"{int(clear_w)} mm clear")
    callout(msp, "AHU-1 with filter/coil/fan sections", 1780, 1200, 260, 4340)
    callout(msp, "duplex pump skid on housekeeping pad", 4300, 1020, 3320, 4340)
    callout(msp, "parallel supply/return hydronic pipe rack", 3150, 2960, 2820, 4140)
    callout(msp, "main duct with return branch and hangers", 3300, 3520, 3920, 4440)
    legend(msp, 4350, 3880)
    north_arrow(msp, 5520, 3360)
    layer_table(msp, 120, 3320)
    title_block(msp, "MECHANICAL ROOM FLOOR PLAN", "1:50", "M-101")


def equipment_layout(doc) -> None:
    msp = doc.modelspace()
    room_shell(msp)
    ahu_plan(msp)
    rect(msp, 700, 650, 1700, 1100, "HIDDEN")
    rect(msp, 3600, 650, 1400, 800, "HIDDEN")
    rect(msp, 3650, 600, 1500, 900, "CLEARANCE")
    pump_symbol(msp, 4080, 1030, "P-1")
    pump_symbol(msp, 4620, 1030, "P-2")
    dim_h(msp, 850, 2350, 560, "AHU casing 1500")
    skid_x, _, skid_length, _ = box_xywh("equipment_pump_skid_001")
    dim_h(
        msp,
        skid_x,
        skid_x + skid_length,
        520,
        f"pump skid {int(skid_length)}",
    )
    dim_v(msp, 550, 780, 1630, "850")
    dim_v(msp, 5250, 650, 1450, "800")
    callout(msp, "filter access side", 900, 1610, 720, 3020)
    callout(msp, "fan/motor access panel", 2150, 1600, 1820, 3020)
    callout(msp, "dual pumps with motor/volute/coupling guard", 4320, 1030, 3440, 3020)
    label(msp, "Equipment tags are stable names used by manifest and IFC validation.", 760, 3420, 78)
    north_arrow(msp, 5520, 3360)
    layer_table(msp, 120, 3320)
    title_block(msp, "EQUIPMENT LAYOUT AND CLEARANCES", "1:50", "M-102")


def pipe_support_detail(doc) -> None:
    msp = doc.modelspace()
    label(msp, "SECTION A - PIPE SUPPORT BRACKET", 1180, 3600, 115)
    rect(msp, 1500, 760, 3000, 95, "M-SUPPORT")
    rect(msp, 2100, 855, 110, 1180, "M-SUPPORT")
    rect(msp, 3790, 855, 110, 1180, "M-SUPPORT")
    rect(msp, 1880, 2035, 2240, 150, "M-SUPPORT")
    msp.add_circle((3000, 2620), 330, dxfattribs={"layer": "M-PIPE-SUPPLY"})
    msp.add_circle((3000, 2620), 215, dxfattribs={"layer": "CENTERLINES"})
    rect(msp, 2450, 2310, 1100, 620, "M-PIPE-FITTING")
    rect(msp, 2520, 2185, 960, 125, "M-PIPE-FITTING")
    rect(msp, 2520, 2930, 960, 125, "M-PIPE-FITTING")
    for x in [1800, 2400, 3600, 4200]:
        msp.add_circle((x, 690), 42, dxfattribs={"layer": "M-SUPPORT"})
    msp.add_line((1500, 620), (4500, 620), dxfattribs={"layer": "A-SLAB"})
    dim_h(msp, 1500, 4500, 500, "base plate 3000")
    dim_h(msp, 1880, 4120, 3220, "clamp saddle 2240")
    dim_v(msp, 4740, 760, 3055, "overall 2295")
    callout(msp, "slotted base plate with four anchors", 1800, 690, 4300, 1250)
    callout(msp, "welded twin upright frame", 3845, 1500, 4300, 1760)
    callout(msp, "two-piece pipe clamp around CHWS", 3000, 2940, 4300, 2480)
    title_block(msp, "PIPE SUPPORT BRACKET DETAIL", "1:10", "M-501")


def wall_penetration_detail(doc) -> None:
    msp = doc.modelspace()
    label(msp, "SECTION B - WALL PENETRATION SLEEVE", 1050, 3600, 115)
    rect(msp, 2280, 760, 520, 2500, "A-WALL")
    rect(msp, 2800, 760, 260, 2500, "HIDDEN")
    msp.add_circle((2540, 2010), 560, dxfattribs={"layer": "M-SUPPORT"})
    msp.add_circle((2540, 2010), 405, dxfattribs={"layer": "M-PIPE-SUPPLY"})
    msp.add_circle((2540, 2010), 250, dxfattribs={"layer": "CENTERLINES"})
    msp.add_circle((2540, 2010), 475, dxfattribs={"layer": "M-PIPE-FITTING"})
    msp.add_line((1300, 2010), (3850, 2010), dxfattribs={"layer": "CENTERLINES"})
    msp.add_line((2540, 1000), (2540, 3020), dxfattribs={"layer": "CENTERLINES"})
    dim_v(msp, 2050, 760, 3260, "wall section 2500")
    dim_h(msp, 2280, 2800, 600, "wall 520")
    dim_h(msp, 1980, 3100, 3260, "sleeve OD 1120")
    callout(msp, "galvanized sleeve through wall", 2800, 2010, 4020, 2550)
    callout(msp, "pipe centered in sleeve", 2540, 2010, 4020, 2100)
    callout(msp, "annular firestop seal zone", 2160, 2340, 4020, 1620)
    title_block(msp, "WALL PENETRATION SLEEVE DETAIL", "1:10", "M-502")


def duct_hanger_detail(doc) -> None:
    msp = doc.modelspace()
    label(msp, "SECTION C - DUCT HANGER/TRAPEZE", 1100, 3600, 115)
    rect(msp, 1600, 940, 2800, 120, "M-SUPPORT")
    rect(msp, 1880, 1060, 75, 1940, "M-SUPPORT")
    rect(msp, 4045, 1060, 75, 1940, "M-SUPPORT")
    rect(msp, 2200, 1420, 1600, 720, "M-DUCT")
    rect(msp, 2100, 1320, 1800, 920, "M-DUCT")
    rect(msp, 1600, 3000, 2800, 120, "M-SUPPORT")
    for x in [1880, 4045]:
        msp.add_circle((x + 38, 3195), 60, dxfattribs={"layer": "M-SUPPORT"})
    msp.add_line((2100, 1780), (3900, 1780), dxfattribs={"layer": "CENTERLINES"})
    msp.add_line((3000, 1320), (3000, 2240), dxfattribs={"layer": "CENTERLINES"})
    dim_h(msp, 2200, 3800, 780, "duct clear 1600")
    dim_h(msp, 1600, 4400, 620, "trapeze 2800")
    dim_v(msp, 4140, 1320, 2240, "duct depth 920")
    dim_v(msp, 4700, 940, 3120, "hanger drop 2180")
    callout(msp, "threaded rod pair with top inserts", 1918, 2600, 4550, 2550)
    callout(msp, "unistrut trapeze channel below duct", 3000, 980, 4550, 1900)
    callout(msp, "rectangular duct with flanged casing", 3800, 2140, 4550, 1380)
    title_block(msp, "DUCT HANGER SECTION DETAIL", "1:10", "M-503")


def section_aa(doc) -> None:
    msp = doc.modelspace()
    label(msp, "SECTION A-A - MECHANICAL ROOM COORDINATION", 600, 3650, 115)
    rect(msp, 450, 620, 5100, 120, "A-SLAB")
    rect(msp, 650, 740, 260, 2700, "A-WALL")
    rect(msp, 5250, 740, 260, 2700, "A-WALL")
    rect(msp, 1100, 900, 1500, 900, "M-EQUIP")
    rect(msp, 1180, 990, 140, 720, "M-EQUIP")
    rect(msp, 1450, 990, 160, 720, "M-EQUIP")
    msp.add_circle((2240, 1340), 190, dxfattribs={"layer": "M-EQUIP"})
    rect(msp, 3020, 900, 1400, 260, "M-EQUIP")
    msp.add_circle((3420, 1380), 160, dxfattribs={"layer": "M-EQUIP"})
    msp.add_circle((3950, 1380), 160, dxfattribs={"layer": "M-EQUIP"})
    rect(msp, 900, 2860, 3600, 360, "M-DUCT")
    rect(msp, 1200, 2450, 3200, 110, "E-CABLETRAY")
    pipe_run(msp, (2920, 2220), (4550, 2220), "M-PIPE-SUPPLY")
    pipe_run(msp, (2920, 2050), (4820, 2050), "M-PIPE-RETURN")
    rect(msp, 920, 870, 1800, 1900, "CLEARANCE")
    dim_h(msp, 920, 2720, 820, "AHU clearance 1800")
    dim_v(msp, 560, 870, 2770, "1900 clear")
    dim_v(msp, 5650, 620, 3440, "room height 2820 shown")
    dim_v(msp, 4680, 2450, 3220, "tray below duct")
    label(msp, "AHU-01", 1540, 1260, 90, "M-EQUIP")
    label(msp, "PS-01", 3525, 990, 70, "M-EQUIP")
    label(msp, "DUCT-01", 2400, 3030, 70, "M-DUCT")
    label(msp, "CT-01", 2620, 2490, 62, "E-CABLETRAY")
    callout(msp, "clearance volume stops below overhead tray", 1880, 2540, 3340, 3480)
    callout(msp, "CHWS/CHWR rack is outside AHU service-clearance plan zone", 3000, 2130, 3340, 3060)
    callout(msp, "duct and tray separated in elevation", 3300, 3040, 3340, 2640)
    title_block(msp, "SECTION A-A COORDINATION", "1:25", "M-301")


def system_riser(doc) -> None:
    msp = doc.modelspace()
    label(msp, "SYSTEM RISER / CONNECTIVITY DIAGRAM", 900, 3650, 115)
    systems = [
        ("CHWS", "M-PIPE-SUPPLY", 3050),
        ("CHWR", "M-PIPE-RETURN", 2700),
        ("SUPPLY AIR", "M-DUCT", 2250),
        ("RETURN AIR", "M-DUCT", 1900),
        ("ELECTRICAL ROUTING", "E-CABLETRAY", 1550),
    ]
    for name, layer, y in systems:
        msp.add_line((850, y), (5150, y), dxfattribs={"layer": layer})
        label(msp, name, 250, y - 28, 70, "ANNOTATIONS")
    nodes = [
        ("P-1", 1100, 3050, "M-EQUIP"),
        ("V-CHWS", 1800, 3050, "M-PIPE-FITTING"),
        ("COIL", 2550, 3050, "M-EQUIP"),
        ("AHU", 3250, 2250, "M-EQUIP"),
        ("FD", 3950, 2250, "M-DUCT"),
        ("DIFF", 4750, 2250, "M-DUCT"),
        ("GRILLE", 4750, 1900, "M-DUCT"),
        ("TRAY", 3250, 1550, "E-CABLETRAY"),
    ]
    for text, x, y, layer in nodes:
        rect(msp, x - 150, y - 95, 300, 190, layer)
        label(msp, text, x - 95, y - 25, 60, "ANNOTATIONS")
    msp.add_line((2550, 3050), (2550, 2700), dxfattribs={"layer": "M-PIPE-RETURN"})
    msp.add_line((3250, 2250), (3250, 1900), dxfattribs={"layer": "M-DUCT"})
    callout(
        msp,
        f"{len(CONNECTIVITY)} IFC port-to-port connections generated from ProjectSpec",
        3400,
        2250,
        3550,
        3420,
    )
    callout(msp, "5 IfcDistributionSystem groups validated", 3250, 1550, 3550, 3150)
    label(msp, "This sheet is a schematic connectivity view; IFC ports carry the machine-readable network.", 820, 980, 76)
    title_block(msp, "MEP SYSTEM RISER / IFC CONNECTIVITY", "NTS", "M-601")


DRAWINGS = {
    "floor_plan": ("Mechanical Room Floor Plan", floor_plan),
    "equipment_layout": ("Equipment Layout and Clearances", equipment_layout),
    "section_aa": ("Section A-A Coordination", section_aa),
    "system_riser": ("MEP System Riser and IFC Connectivity", system_riser),
    "pipe_support_detail": ("Pipe Support Bracket Detail", pipe_support_detail),
    "wall_penetration_detail": ("Wall Penetration Sleeve Detail", wall_penetration_detail),
    "duct_hanger_detail": ("Duct Hanger Section Detail", duct_hanger_detail),
}


def write_pdf(name: str, title: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{name}.pdf"
    c = canvas.Canvas(str(path), pagesize=landscape(A3))
    w, h = landscape(A3)
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.rect(36, 36, w - 72, h - 72)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(60, h - 80, title)
    c.setFont("Helvetica", 10)
    c.drawString(
        60,
        h - 105,
        "Portable preview only. Use QCAD's exporter for the canonical PDF drawing.",
    )
    c.drawString(60, 70, "CoordProof MEP Coordination Package")
    c.drawString(w - 210, 70, "Units: millimeters")
    c.showPage()
    c.save()
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf-output-dir",
        type=Path,
        default=PORTABLE_PDF_DIR,
        help="portable preview directory (default: build/portable/qcad_pdf_previews)",
    )
    parser.add_argument(
        "--skip-pdf",
        action="store_true",
        help="generate DXF sources only; the full build uses QCAD for canonical PDFs",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    pdf_output_dir = args.pdf_output_dir
    if not pdf_output_dir.is_absolute():
        pdf_output_dir = ROOT / pdf_output_dir
    QCAD_DIR.mkdir(parents=True, exist_ok=True)
    for name, (title, draw_fn) in DRAWINGS.items():
        doc = setup_doc()
        draw_fn(doc)
        dxf_path = QCAD_DIR / f"{name}.dxf"
        doc.saveas(dxf_path)
        if args.skip_pdf:
            print(f"Wrote {dxf_path}")
            continue
        pdf_path = write_pdf(name, title, pdf_output_dir)
        print(f"Wrote {dxf_path} and portable preview {pdf_path}")


if __name__ == "__main__":
    main()
