// OpenSCAD cable tray segment type B
// Units: millimeters

tray_length_mm = 500;
tray_width_mm = 160;
tray_height_mm = 60;
wall_thickness_mm = 4;
hole_diameter_mm = 16;
hole_pitch_mm = 80;

$fn = 36;

module perforated_floor() {
    difference() {
        cube([tray_length_mm, tray_width_mm, wall_thickness_mm], center = true);
        for (x = [-tray_length_mm / 2 + hole_pitch_mm : hole_pitch_mm : tray_length_mm / 2 - hole_pitch_mm]) {
            for (y = [-tray_width_mm / 4, tray_width_mm / 4]) {
                translate([x, y, 0])
                    cylinder(h = wall_thickness_mm + 2, r = hole_diameter_mm / 2, center = true);
            }
        }
    }
}

union() {
    perforated_floor();
    translate([0, -tray_width_mm / 2 + wall_thickness_mm / 2, tray_height_mm / 2])
        cube([tray_length_mm, wall_thickness_mm, tray_height_mm], center = true);
    translate([0, tray_width_mm / 2 - wall_thickness_mm / 2, tray_height_mm / 2])
        cube([tray_length_mm, wall_thickness_mm, tray_height_mm], center = true);
}
