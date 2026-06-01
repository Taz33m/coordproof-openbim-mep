// OpenSCAD pipe clamp type B
// Units: millimeters

pipe_diameter_mm = 50;
clamp_thickness_mm = 8;
clamp_width_mm = 35;
ear_length_mm = 28;
bolt_diameter_mm = 8;

$fn = 72;

module clamp_ring() {
    difference() {
        cylinder(h = clamp_width_mm, r = pipe_diameter_mm / 2 + clamp_thickness_mm);
        translate([0, 0, -1])
            cylinder(h = clamp_width_mm + 2, r = pipe_diameter_mm / 2);
    }
}

module ears() {
    outer_r = pipe_diameter_mm / 2 + clamp_thickness_mm;
    for (side = [-1, 1]) {
        translate([side * (outer_r + ear_length_mm / 2 - 2), 0, clamp_width_mm / 2])
            difference() {
                cube([ear_length_mm, clamp_thickness_mm * 2.2, clamp_width_mm], center = true);
                rotate([0, 0, 0])
                    cylinder(h = clamp_width_mm + 2, r = bolt_diameter_mm / 2, center = true);
            }
    }
}

union() {
    clamp_ring();
    ears();
}
