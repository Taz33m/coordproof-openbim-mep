// OpenSCAD rectangular duct connector type B
// Units: millimeters

duct_width_mm = 360;
duct_height_mm = 180;
connector_depth_mm = 50;
wall_thickness_mm = 5;
flange_extra_mm = 30;

module hollow_box(outer_x, outer_y, depth, wall) {
    difference() {
        cube([depth, outer_x, outer_y], center = true);
        cube([depth + 2, outer_x - 2 * wall, outer_y - 2 * wall], center = true);
    }
}

union() {
    hollow_box(duct_width_mm, duct_height_mm, connector_depth_mm, wall_thickness_mm);
    translate([-connector_depth_mm / 2 - wall_thickness_mm / 2, 0, 0])
        hollow_box(duct_width_mm + flange_extra_mm, duct_height_mm + flange_extra_mm, wall_thickness_mm, wall_thickness_mm);
    translate([connector_depth_mm / 2 + wall_thickness_mm / 2, 0, 0])
        hollow_box(duct_width_mm + flange_extra_mm, duct_height_mm + flange_extra_mm, wall_thickness_mm, wall_thickness_mm);
}
