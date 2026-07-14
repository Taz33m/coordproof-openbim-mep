# Observed Geometry Matrix

This deterministic report compares authoritative ProjectSpec geometry with
the bounding envelopes measured directly from committed IFC, STEP, STL, and
selected DXF entities. Embedded property-set values are not treated as observed
geometry. Envelope parity does not certify topology, fabrication readiness,
engineering performance, or code compliance.

## Result

- Status: `PASSED`
- Passing observations: `69`
- Failed observations: `0`
- Explicit exclusions: `1`
- Formats: `dxf, ifc, step, stl`

## Observations

| Format | Subject | Occurrence | Expected size (mm) | Observed size (mm) | Max delta (mm) | Status |
| --- | --- | --- | --- | --- | ---: | --- |
| `dxf` | `cable_tray_overhead_001` | `cable_tray_overhead_001` | 3200 × 220 × 0 | 3200 × 220 × 0 | 0 | `PASS` |
| `dxf` | `clearance_ahu_service_zone_001` | `clearance_ahu_service_zone_001` | 1800 × 1000 × 0 | 1800 × 1000 × 0 | 0 | `PASS` |
| `dxf` | `duct_branch_001` | `duct_branch_001` | 650 × 360 × 0 | 650 × 360 × 0 | 0 | `PASS` |
| `dxf` | `duct_main_001` | `duct_main_001` | 3600 × 420 × 0 | 3600 × 420 × 0 | 0 | `PASS` |
| `dxf` | `equipment_ahu_001` | `equipment_ahu_001` | 1500 × 850 × 0 | 1500 × 850 × 0 | 0 | `PASS` |
| `dxf` | `equipment_pump_skid_001` | `equipment_pump_skid_001` | 1400 × 800 × 0 | 1400 × 800 × 0 | 0 | `PASS` |
| `dxf` | `slab_concrete_base_001` | `slab_concrete_base_001` | 6000 × 4200 × 0 | 6000 × 4200 × 0 | 0 | `PASS` |
| `ifc` | `ahu_coil_001` | `ahu_coil_001` | 160 × 800 × 760 | 160 × 800 × 760 | 0 | `PASS` |
| `ifc` | `ahu_fan_001` | `ahu_fan_001` | 420 × 520 × 520 | 420 × 520 × 520 | 0 | `PASS` |
| `ifc` | `ahu_filter_001` | `ahu_filter_001` | 120 × 800 × 760 | 120 × 800 × 760 | 0 | `PASS` |
| `ifc` | `air_terminal_return_001` | `air_terminal_return_001` | 420 × 420 × 60 | 420 × 420 × 60 | 0 | `PASS` |
| `ifc` | `air_terminal_supply_001` | `air_terminal_supply_001` | 450 × 450 × 60 | 450 × 450 × 60 | 0 | `PASS` |
| `ifc` | `cable_tray_drop_001` | `cable_tray_drop_001` | 120 × 120 × 520 | 120 × 120 × 520 | 0 | `PASS` |
| `ifc` | `cable_tray_overhead_001` | `cable_tray_overhead_001` | 3200 × 220 × 80 | 3200 × 220 × 80 | 0 | `PASS` |
| `ifc` | `clearance_ahu_service_zone_001` | `clearance_ahu_service_zone_001` | 1800 × 1000 × 1900 | 1800 × 1000 × 1900 | 0 | `PASS` |
| `ifc` | `damper_fire_001` | `damper_fire_001` | 120 × 420 × 220 | 120 × 420 × 220 | 0 | `PASS` |
| `ifc` | `door_access_001` | `door_access_001` | 1000 × 70 × 2100 | 1000 × 70 × 2100 | 0 | `PASS` |
| `ifc` | `duct_branch_001` | `duct_branch_001` | 650 × 360 × 180 | 650 × 360 × 180 | 0 | `PASS` |
| `ifc` | `duct_main_001` | `duct_main_001` | 3600 × 420 × 220 | 3600 × 420 × 220 | 0 | `PASS` |
| `ifc` | `duct_return_001` | `duct_return_001` | 1350 × 340 × 180 | 1350 × 340 × 180 | 0 | `PASS` |
| `ifc` | `equipment_ahu_001` | `equipment_ahu_001` | 1500 × 850 × 1100 | 1500 × 850 × 1100 | 0 | `PASS` |
| `ifc` | `equipment_base_type_a` | `equipment_base_type_a` | 1800 × 1100 × 160 | 1800 × 1100 × 160 | 0 | `PASS` |
| `ifc` | `equipment_pump_skid_001` | `equipment_pump_skid_001` | 1400 × 800 × 180 | 1400 × 800 × 180 | 0 | `PASS` |
| `ifc` | `pipe_clamp_type_a` | `pipe_clamp_type_a` | 110 × 45 × 110 | 110 × 45 × 110 | 0 | `PASS` |
| `ifc` | `pipe_fitting_chwr_elbow_001` | `pipe_fitting_chwr_elbow_001` | 120 × 120 × 120 | 120 × 120 × 120 | 0 | `PASS` |
| `ifc` | `pipe_fitting_chws_elbow_001` | `pipe_fitting_chws_elbow_001` | 120 × 120 × 120 | 120 × 120 × 120 | 0 | `PASS` |
| `ifc` | `pipe_return_001` | `pipe_return_001` | 3920 × 80 × 80 | 3920 × 80 × 80 | 0 | `PASS` |
| `ifc` | `pipe_return_drop_001` | `pipe_return_drop_001` | 80 × 80 × 810 | 80 × 80 × 810 | 0 | `PASS` |
| `ifc` | `pipe_supply_001` | `pipe_supply_001` | 3600 × 80 × 80 | 3600 × 80 × 80 | 0 | `PASS` |
| `ifc` | `pipe_supply_drop_001` | `pipe_supply_drop_001` | 80 × 80 × 800 | 80 × 80 × 800 | 0 | `PASS` |
| `ifc` | `plate_mounting_type_a` | `plate_mounting_type_a` | 260 × 160 × 12 | 260 × 160 × 12 | 0 | `PASS` |
| `ifc` | `pump_chws_duty_001` | `pump_chws_duty_001` | 460 × 340 × 340 | 460 × 340 × 340 | 0 | `PASS` |
| `ifc` | `pump_chws_standby_001` | `pump_chws_standby_001` | 460 × 340 × 340 | 460 × 340 × 340 | 0 | `PASS` |
| `ifc` | `room_shell_001` | `room_shell_001` | 6000 × 4200 × 3200 | 6000 × 4200 × 3200 | 0 | `PASS` |
| `ifc` | `sensor_chws_pressure_001` | `sensor_chws_pressure_001` | 110 × 110 × 80 | 110 × 110 × 80 | 0 | `PASS` |
| `ifc` | `slab_concrete_base_001` | `slab_concrete_base_001` | 6000 × 4200 × 200 | 6000 × 4200 × 200 | 0 | `PASS` |
| `ifc` | `sleeve_wall_penetration_type_a` | `sleeve_wall_penetration_type_a` | 220 × 170 × 170 | 220 × 170 × 170 | 0 | `PASS` |
| `ifc` | `support_duct_hanger_type_a` | `support_duct_hanger_type_a` | 520 × 60 × 520 | 520 × 60 × 520 | 0 | `PASS` |
| `ifc` | `support_pipe_bracket_type_a` | `support_pipe_bracket_type_a` | 220 × 120 × 300 | 220 × 120 × 300 | 0 | `PASS` |
| `ifc` | `valve_chwr_balancing_001` | `valve_chwr_balancing_001` | 140 × 160 × 160 | 140 × 160 × 160 | 0 | `PASS` |
| `ifc` | `valve_chwr_isolation_001` | `valve_chwr_isolation_001` | 140 × 160 × 160 | 140 × 160 × 160 | 0 | `PASS` |
| `ifc` | `valve_chws_balancing_001` | `valve_chws_balancing_001` | 140 × 160 × 160 | 140 × 160 × 160 | 0 | `PASS` |
| `ifc` | `valve_chws_isolation_001` | `valve_chws_isolation_001` | 140 × 160 × 160 | 140 × 160 × 160 | 0 | `PASS` |
| `ifc` | `wall_east_001` | `wall_east_001` | 200 × 4200 × 3000 | 200 × 4200 × 3000 | 0 | `PASS` |
| `ifc` | `wall_north_001` | `wall_north_001` | 6000 × 200 × 3000 | 6000 × 200 × 3000 | 0 | `PASS` |
| `ifc` | `wall_south_001` | `wall_south_001` | 6000 × 200 × 3000 | 6000 × 200 × 3000 | 0 | `PASS` |
| `ifc` | `wall_west_001` | `wall_west_001` | 200 × 4200 × 3000 | 200 × 4200 × 3000 | 0 | `PASS` |
| `step` | `cable_tray_overhead_001` | `cable_tray_overhead_001` | 900 × 220 × 82 | 900 × 220 × 82 | 0 | `PASS` |
| `step` | `duct_main_001` | `duct_main_001` | 952 × 456 × 256 | 952 × 456 × 256 | 0 | `PASS` |
| `step` | `equipment_base_type_a` | `equipment_base_type_a` | 1200 × 800 × 160 | 1200 × 800 × 160 | 0 | `PASS` |
| `step` | `equipment_pump_skid_001` | `equipment_pump_skid_001` | 1170 × 520 × 180 | 1170 × 520 × 180 | 0 | `PASS` |
| `step` | `pipe_clamp_type_a` | `pipe_clamp_type_a` | 144 × 80 × 45 | 144 × 80 × 45 | 0 | `PASS` |
| `step` | `plate_mounting_type_a` | `plate_mounting_type_a` | 260 × 160 × 12 | 260 × 160 × 12 | 0 | `PASS` |
| `step` | `sleeve_wall_penetration_type_a` | `sleeve_wall_penetration_type_a` | 190 × 190 × 200 | 190 × 190 × 200 | 0 | `PASS` |
| `step` | `support_duct_hanger_type_a` | `support_duct_hanger_type_a` | 540 × 228 × 528 | 540 × 228 × 528 | 0 | `PASS` |
| `step` | `support_pipe_bracket_type_a` | `support_pipe_bracket_type_a` | 220 × 120 × 341 | 220 × 120 × 341 | 0 | `PASS` |
| `step` | `room_shell_001` | `room_shell_001` | — | — | — | `EXCLUDED` |
| `stl` | `cable_tray_overhead_001` | `cable_tray_overhead_001` | 900 × 220 × 82 | 900 × 220 × 82 | 0 | `PASS` |
| `stl` | `duct_main_001` | `duct_main_001` | 952 × 456 × 256 | 952 × 456 × 256 | 0 | `PASS` |
| `stl` | `equipment_base_type_a` | `equipment_base_type_a` | 1200 × 800 × 160 | 1200 × 800 × 160 | 0 | `PASS` |
| `stl` | `equipment_pump_skid_001` | `equipment_pump_skid_001` | 1170 × 520 × 180 | 1170 × 520 × 180 | 0 | `PASS` |
| `stl` | `openscad_bracket_plate_type_b` | `—` | 180 × 90 × 10 | 180 × 90 × 10 | 0 | `PASS` |
| `stl` | `openscad_cable_tray_segment_type_b` | `—` | 500 × 160 × 62 | 500 × 160 × 62 | 0 | `PASS` |
| `stl` | `openscad_duct_connector_type_b` | `—` | 60 × 390 × 210 | 60 × 390 × 210 | 0 | `PASS` |
| `stl` | `openscad_pipe_clamp_type_b` | `—` | 118 × 66 × 35 | 118 × 66 × 35 | 0 | `PASS` |
| `stl` | `pipe_clamp_type_a` | `pipe_clamp_type_a` | 144 × 80 × 45 | 144 × 80 × 45 | 0 | `PASS` |
| `stl` | `plate_mounting_type_a` | `plate_mounting_type_a` | 260 × 160 × 12 | 260 × 160 × 12 | 0 | `PASS` |
| `stl` | `sleeve_wall_penetration_type_a` | `sleeve_wall_penetration_type_a` | 190 × 190 × 200 | 189.881904602 × 189.940948486 × 200 | 0.118095398 | `PASS` |
| `stl` | `support_duct_hanger_type_a` | `support_duct_hanger_type_a` | 540 × 228 × 528 | 540 × 228 × 528 | 0 | `PASS` |
| `stl` | `support_pipe_bracket_type_a` | `support_pipe_bracket_type_a` | 220 × 120 × 341 | 220 × 120 × 341 | 0 | `PASS` |

## Explicit Boundary

`mechanical_room_assembly.step` remains an explicit exclusion because its
legacy FreeCAD decomposition is not yet projected completely from ProjectSpec.
The exclusion is visible in the CSV and cannot be mistaken for a passing check.
