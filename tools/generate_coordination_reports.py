"""Generate BOM and preliminary coordination-screening reports from the BIM schedule."""

from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from openbim_core import CONNECTIVITY, SYSTEMS, ProductSpec, product_schedule

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
BOM_PATH = REPORT_DIR / "bill_of_materials.csv"
CLASH_PATH = REPORT_DIR / "clash_clearance_report.csv"
SUMMARY_PATH = REPORT_DIR / "coordination_report.md"


@dataclass(frozen=True)
class Box:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def intersects(self, other: Box) -> bool:
        return not (
            self.max_x <= other.min_x
            or self.min_x >= other.max_x
            or self.max_y <= other.min_y
            or self.min_y >= other.max_y
            or self.max_z <= other.min_z
            or self.min_z >= other.max_z
        )

    def separation(self, other: Box) -> float:
        dx = max(other.min_x - self.max_x, self.min_x - other.max_x, 0.0)
        dy = max(other.min_y - self.max_y, self.min_y - other.max_y, 0.0)
        dz = max(other.min_z - self.max_z, self.min_z - other.max_z, 0.0)
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    @property
    def size(self) -> tuple[float, float, float]:
        return (self.max_x - self.min_x, self.max_y - self.min_y, self.max_z - self.min_z)


def bounding_box(spec: ProductSpec) -> Box:
    x, y, z = spec.origin_mm
    if spec.geometry == "cylinder":
        radius, depth = spec.dimensions_mm
        axis = spec.extrusion_axis
        if axis[0]:
            return Box(x, y - radius, z - radius, x + depth, y + radius, z + radius)
        if axis[1]:
            return Box(x - radius, y, z - radius, x + radius, y + depth, z + radius)
        return Box(x - radius, y - radius, z, x + radius, y + radius, z + depth)
    length, width, height = spec.dimensions_mm
    return Box(x, y, z, x + length, y + width, z + height)


def dimensions_text(spec: ProductSpec) -> str:
    if spec.geometry == "cylinder":
        radius, depth = spec.dimensions_mm
        return f"dia {int(radius * 2)} x {int(depth)}"
    return " x ".join(str(int(value)) for value in spec.dimensions_mm)


def write_bom(specs: list[ProductSpec]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with BOM_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "asset_id",
                "name",
                "ifc_class",
                "category",
                "systems",
                "material",
                "dimensions_mm",
                "source_tool",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for spec in specs:
            writer.writerow(
                {
                    "asset_id": spec.asset_id,
                    "name": spec.name,
                    "ifc_class": spec.ifc_class,
                    "category": spec.category,
                    "systems": ";".join(spec.system),
                    "material": spec.material,
                    "dimensions_mm": dimensions_text(spec),
                    "source_tool": spec.source_tool,
                }
            )


def relevant_pairs(specs: list[ProductSpec]) -> list[tuple[ProductSpec, ProductSpec, float, str]]:
    boxes = {spec.asset_id: bounding_box(spec) for spec in specs}
    pairs: list[tuple[ProductSpec, ProductSpec, float, str]] = []
    monitored_categories = {
        "flow_segment",
        "flow_fitting",
        "flow_controller",
        "ductwork",
        "electrical_routing",
        "clearance_zone",
        "mechanical_equipment",
    }
    for index, left in enumerate(specs):
        for right in specs[index + 1 :]:
            if not ({left.category, right.category} & monitored_categories):
                continue
            if left.category == right.category == "mechanical_equipment":
                continue
            left_box = boxes[left.asset_id]
            right_box = boxes[right.asset_id]
            distance = left_box.separation(right_box)
            status = "PASS"
            if left_box.intersects(right_box):
                status = "REVIEW"
            if "clearance_zone" in {left.category, right.category} and left_box.intersects(right_box):
                status = "FAIL"
            if distance <= 125 or status != "PASS":
                pairs.append((left, right, distance, status))
    return pairs


def clearance_rows(specs: list[ProductSpec]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    boxes = {spec.asset_id: bounding_box(spec) for spec in specs}
    ahu = next(spec for spec in specs if spec.asset_id == "equipment_ahu_001")
    zone = next(spec for spec in specs if spec.asset_id == "clearance_ahu_service_zone_001")
    zone_box = boxes[zone.asset_id]
    zone_depth = zone_box.size[1]
    zone_height = zone_box.size[2]
    rows.append(
        {
            "check_id": "CLR-AHU-001",
            "check_type": "clearance_rule",
            "left": zone.name,
            "right": ahu.name,
            "minimum_mm": "1000 depth / 1900 headroom",
            "actual_mm": f"{int(zone_depth)} depth / {int(zone_height)} headroom",
            "status": "PASS" if zone_depth >= 1000 and zone_height >= 1900 else "FAIL",
            "notes": "AHU service access zone is explicit IFC geometry and manifest asset.",
        }
    )
    for left, right, distance, status in relevant_pairs(specs):
        if status == "PASS":
            continue
        rows.append(
            {
                "check_id": f"INT-{len(rows):03d}",
                "check_type": "bbox_intersection",
                "left": left.name,
                "right": right.name,
                "minimum_mm": "0",
                "actual_mm": str(int(distance)),
                "status": status,
                "notes": "Bounding-box screen; REVIEW is acceptable for connected equipment/pipe interfaces.",
            }
        )
    monitored_separations = [
        ("pipe_supply_001", "duct_branch_001", "pipe-to-duct separation", 100),
        ("pipe_return_001", "duct_branch_001", "pipe-to-duct separation", 100),
        ("cable_tray_overhead_001", "duct_branch_001", "tray-to-duct separation", 150),
        ("cable_tray_overhead_001", "clearance_ahu_service_zone_001", "tray above clearance headroom", 0),
    ]
    by_id = {spec.asset_id: spec for spec in specs}
    for left_id, right_id, check_type, minimum in monitored_separations:
        left = by_id[left_id]
        right = by_id[right_id]
        distance = boxes[left_id].separation(boxes[right_id])
        rows.append(
            {
                "check_id": f"SEP-{len(rows):03d}",
                "check_type": check_type,
                "left": left.name,
                "right": right.name,
                "minimum_mm": str(minimum),
                "actual_mm": str(int(distance)),
                "status": "PASS" if distance >= minimum else "FAIL",
                "notes": "Rule generated from shared BIM product schedule.",
            }
        )
    return rows


def write_clash_report(rows: list[dict[str, str]]) -> None:
    with CLASH_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "check_id",
                "check_type",
                "left",
                "right",
                "minimum_mm",
                "actual_mm",
                "status",
                "notes",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_summary(specs: list[ProductSpec], checks: list[dict[str, str]]) -> None:
    by_class = Counter(spec.ifc_class for spec in specs)
    by_category = Counter(spec.category for spec in specs)
    by_material = Counter(spec.material for spec in specs)
    fail_count = sum(row["status"] == "FAIL" for row in checks)
    review_count = sum(row["status"] == "REVIEW" for row in checks)
    pass_count = sum(row["status"] == "PASS" for row in checks)
    connected_ports = len(CONNECTIVITY)
    lines = [
        "# Coordination Report",
        "",
        "This report is generated from `tools/openbim_core.py`, the same product",
        "schedule used to create `bim/mechanical_room.ifc`. It is intentionally",
        "validation-grade rather than a stamped engineering report. Clearance",
        "failures are explicit; non-clearance intersections are marked REVIEW",
        "because they are a bounding-box coordination screen, not a full clash engine.",
        "",
        "## Source Of Truth",
        "",
        "| Item | Value |",
        "| --- | ---: |",
        f"| BIM product specs | {len(specs)} |",
        f"| Distribution systems | {len(SYSTEMS)} |",
        f"| Port connections | {connected_ports} |",
        f"| Clash/clearance checks | {len(checks)} |",
        f"| Failed checks | {fail_count} |",
        f"| Review checks | {review_count} |",
        f"| Passed checks | {pass_count} |",
        "",
        "## IFC Class Schedule",
        "",
        "| IFC Class | Count |",
        "| --- | ---: |",
    ]
    for klass, count in sorted(by_class.items()):
        lines.append(f"| `{klass}` | {count} |")
    lines.extend(["", "## Category Schedule", "", "| Category | Count |", "| --- | ---: |"])
    for category, count in sorted(by_category.items()):
        lines.append(f"| `{category}` | {count} |")
    lines.extend(["", "## Material Schedule", "", "| Material | Count |", "| --- | ---: |"])
    for material, count in sorted(by_material.items()):
        lines.append(f"| `{material}` | {count} |")
    lines.extend(
        [
            "",
            "## Output Files",
            "",
            f"- `{BOM_PATH.relative_to(ROOT)}`",
            f"- `{CLASH_PATH.relative_to(ROOT)}`",
            "",
        ]
    )
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    specs = product_schedule()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    write_bom(specs)
    checks = clearance_rows(specs)
    write_clash_report(checks)
    write_summary(specs, checks)
    print(f"Wrote {SUMMARY_PATH}")
    print(f"Wrote {BOM_PATH}")
    print(f"Wrote {CLASH_PATH}")


if __name__ == "__main__":
    main()
