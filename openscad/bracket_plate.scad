// OpenSCAD bracket plate type B
// Units: millimeters

plate_length_mm = 180;
plate_width_mm = 90;
plate_thickness_mm = 10;
slot_length_mm = 30;
slot_width_mm = 11;
slot_spacing_mm = 105;

$fn = 48;

module slot(length, width, depth) {
    hull() {
        translate([-length / 2 + width / 2, 0, 0]) cylinder(h = depth, r = width / 2, center = true);
        translate([length / 2 - width / 2, 0, 0]) cylinder(h = depth, r = width / 2, center = true);
    }
}

difference() {
    cube([plate_length_mm, plate_width_mm, plate_thickness_mm], center = true);
    for (x = [-slot_spacing_mm / 2, slot_spacing_mm / 2]) {
        translate([x, 0, 0])
            slot(slot_length_mm, slot_width_mm, plate_thickness_mm + 2);
    }
}
