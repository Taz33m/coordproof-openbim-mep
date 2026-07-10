# Parameter Reconciliation Report

Overall Status: **PASSED**

This report compares authoritative ProjectSpec values with declared producer
inputs and explicit type-to-occurrence relationships. No arbitrary expressions
are evaluated; derived values use the contract's small transform vocabulary.

## Summary

| Metric | Value |
| --- | ---: |
| `contract_schema_version` | 1 |
| `producer_count` | 13 |
| `required_producer_count` | 13 |
| `relation_count` | 17 |
| `row_count` | 92 |
| `passed_row_count` | 92 |
| `failed_row_count` | 0 |
| `scoped_numeric_parameter_count` | 75 |
| `covered_numeric_parameter_count` | 75 |
| `producer_input_count` | 78 |
| `covered_producer_input_count` | 78 |
| `excluded_producer_input_count` | 3 |
| `producer_error_count` | 0 |
| `failure_count` | 0 |

## Failures

- None

## Scope Warnings

- This v1 contract gates CadQuery engineering inputs, all top-level OpenSCAD numeric inputs or justified exclusions, and declared type-to-occurrence relations; FreeCAD and drawing adapters remain the next scope.

## Evidence

| Relation | Subject | Canonical | Producer | Relation | Expected | Actual | Status | Reason |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| cadquery.cable_tray.height_mm | asset_type:cable_tray_overhead_001 | $.asset_types[cable_tray_overhead_001].parameters.height_mm | cadquery/cable_tray.py::DEFAULT_PARAMETERS.height_mm | equal | 80 | 80 | passed |  |
| cadquery.cable_tray.hole_diameter_mm | asset_type:cable_tray_overhead_001 | $.asset_types[cable_tray_overhead_001].parameters.hole_diameter_mm | cadquery/cable_tray.py::DEFAULT_PARAMETERS.hole_diameter_mm | equal | 20 | 20 | passed |  |
| cadquery.cable_tray.hole_pitch_mm | asset_type:cable_tray_overhead_001 | $.asset_types[cable_tray_overhead_001].parameters.hole_pitch_mm | cadquery/cable_tray.py::DEFAULT_PARAMETERS.hole_pitch_mm | equal | 110 | 110 | passed |  |
| cadquery.cable_tray.length_mm | asset_type:cable_tray_overhead_001 | $.asset_types[cable_tray_overhead_001].parameters.length_mm | cadquery/cable_tray.py::DEFAULT_PARAMETERS.length_mm | equal | 900 | 900 | passed |  |
| cadquery.cable_tray.thickness_mm | asset_type:cable_tray_overhead_001 | $.asset_types[cable_tray_overhead_001].parameters.thickness_mm | cadquery/cable_tray.py::DEFAULT_PARAMETERS.thickness_mm | equal | 4 | 4 | passed |  |
| cadquery.cable_tray.width_mm | asset_type:cable_tray_overhead_001 | $.asset_types[cable_tray_overhead_001].parameters.width_mm | cadquery/cable_tray.py::DEFAULT_PARAMETERS.width_mm | equal | 220 | 220 | passed |  |
| cadquery.duct_hanger.duct_height_mm | asset_type:support_duct_hanger_type_a | $.asset_types[support_duct_hanger_type_a].parameters.duct_height_mm | cadquery/duct_hanger.py::DEFAULT_PARAMETERS.duct_height_mm | equal | 220 | 220 | passed |  |
| cadquery.duct_hanger.duct_width_mm | asset_type:support_duct_hanger_type_a | $.asset_types[support_duct_hanger_type_a].parameters.duct_width_mm | cadquery/duct_hanger.py::DEFAULT_PARAMETERS.duct_width_mm | equal | 420 | 420 | passed |  |
| cadquery.duct_hanger.height_mm | asset_type:support_duct_hanger_type_a | $.asset_types[support_duct_hanger_type_a].parameters.height_mm | cadquery/duct_hanger.py::DEFAULT_PARAMETERS.height_mm | equal | 520 | 520 | passed |  |
| cadquery.duct_hanger.rod_diameter_mm | asset_type:support_duct_hanger_type_a | $.asset_types[support_duct_hanger_type_a].parameters.rod_diameter_mm | cadquery/duct_hanger.py::DEFAULT_PARAMETERS.rod_diameter_mm | equal | 12 | 12 | passed |  |
| cadquery.duct_hanger.strap_thickness_mm | asset_type:support_duct_hanger_type_a | $.asset_types[support_duct_hanger_type_a].parameters.strap_thickness_mm | cadquery/duct_hanger.py::DEFAULT_PARAMETERS.strap_thickness_mm | equal | 8 | 8 | passed |  |
| cadquery.duct_hanger.strap_width_mm | asset_type:support_duct_hanger_type_a | $.asset_types[support_duct_hanger_type_a].parameters.strap_width_mm | cadquery/duct_hanger.py::DEFAULT_PARAMETERS.strap_width_mm | equal | 38 | 38 | passed |  |
| cadquery.equipment_base.bolt_diameter_mm | asset_type:equipment_base_type_a | $.asset_types[equipment_base_type_a].parameters.bolt_diameter_mm | cadquery/equipment_base.py::DEFAULT_PARAMETERS.bolt_diameter_mm | equal | 18 | 18 | passed |  |
| cadquery.equipment_base.bolt_offset_mm | asset_type:equipment_base_type_a | $.asset_types[equipment_base_type_a].parameters.bolt_offset_mm | cadquery/equipment_base.py::DEFAULT_PARAMETERS.bolt_offset_mm | equal | 120 | 120 | passed |  |
| cadquery.equipment_base.height_mm | asset_type:equipment_base_type_a | $.asset_types[equipment_base_type_a].parameters.height_mm | cadquery/equipment_base.py::DEFAULT_PARAMETERS.height_mm | equal | 160 | 160 | passed |  |
| cadquery.equipment_base.length_mm | asset_type:equipment_base_type_a | $.asset_types[equipment_base_type_a].parameters.length_mm | cadquery/equipment_base.py::DEFAULT_PARAMETERS.length_mm | equal | 1200 | 1200 | passed |  |
| cadquery.equipment_base.width_mm | asset_type:equipment_base_type_a | $.asset_types[equipment_base_type_a].parameters.width_mm | cadquery/equipment_base.py::DEFAULT_PARAMETERS.width_mm | equal | 800 | 800 | passed |  |
| cadquery.mounting_plate.bolt_diameter_mm | asset_type:plate_mounting_type_a | $.asset_types[plate_mounting_type_a].parameters.bolt_diameter_mm | cadquery/mounting_plate.py::DEFAULT_PARAMETERS.bolt_diameter_mm | equal | 14 | 14 | passed |  |
| cadquery.mounting_plate.bolt_spacing_mm | asset_type:plate_mounting_type_a | $.asset_types[plate_mounting_type_a].parameters.bolt_spacing_mm | cadquery/mounting_plate.py::DEFAULT_PARAMETERS.bolt_spacing_mm | equal | 190 | 190 | passed |  |
| cadquery.mounting_plate.length_mm | asset_type:plate_mounting_type_a | $.asset_types[plate_mounting_type_a].parameters.length_mm | cadquery/mounting_plate.py::DEFAULT_PARAMETERS.length_mm | equal | 260 | 260 | passed |  |
| cadquery.mounting_plate.slot_length_mm | asset_type:plate_mounting_type_a | $.asset_types[plate_mounting_type_a].parameters.slot_length_mm | cadquery/mounting_plate.py::DEFAULT_PARAMETERS.slot_length_mm | equal | 34 | 34 | passed |  |
| cadquery.mounting_plate.thickness_mm | asset_type:plate_mounting_type_a | $.asset_types[plate_mounting_type_a].parameters.thickness_mm | cadquery/mounting_plate.py::DEFAULT_PARAMETERS.thickness_mm | equal | 12 | 12 | passed |  |
| cadquery.mounting_plate.width_mm | asset_type:plate_mounting_type_a | $.asset_types[plate_mounting_type_a].parameters.width_mm | cadquery/mounting_plate.py::DEFAULT_PARAMETERS.width_mm | equal | 160 | 160 | passed |  |
| cadquery.pipe_clamp.bolt_diameter_mm | asset_type:pipe_clamp_type_a | $.asset_types[pipe_clamp_type_a].parameters.bolt_diameter_mm | cadquery/pipe_clamp.py::DEFAULT_PARAMETERS.bolt_diameter_mm | equal | 10 | 10 | passed |  |
| cadquery.pipe_clamp.ear_length_mm | asset_type:pipe_clamp_type_a | $.asset_types[pipe_clamp_type_a].parameters.ear_length_mm | cadquery/pipe_clamp.py::DEFAULT_PARAMETERS.ear_length_mm | equal | 34 | 34 | passed |  |
| cadquery.pipe_clamp.pipe_diameter_mm | asset_type:pipe_clamp_type_a | $.asset_types[pipe_clamp_type_a].parameters.pipe_diameter_mm | cadquery/pipe_clamp.py::DEFAULT_PARAMETERS.pipe_diameter_mm | equal | 60 | 60 | passed |  |
| cadquery.pipe_clamp.thickness_mm | asset_type:pipe_clamp_type_a | $.asset_types[pipe_clamp_type_a].parameters.thickness_mm | cadquery/pipe_clamp.py::DEFAULT_PARAMETERS.thickness_mm | equal | 10 | 10 | passed |  |
| cadquery.pipe_clamp.width_mm | asset_type:pipe_clamp_type_a | $.asset_types[pipe_clamp_type_a].parameters.width_mm | cadquery/pipe_clamp.py::DEFAULT_PARAMETERS.width_mm | equal | 45 | 45 | passed |  |
| cadquery.pipe_support.base_thickness_mm | asset_type:support_pipe_bracket_type_a | $.asset_types[support_pipe_bracket_type_a].parameters.base_thickness_mm | cadquery/pipe_support.py::DEFAULT_PARAMETERS.base_thickness_mm | equal | 16 | 16 | passed |  |
| cadquery.pipe_support.bolt_diameter_mm | asset_type:support_pipe_bracket_type_a | $.asset_types[support_pipe_bracket_type_a].parameters.bolt_diameter_mm | cadquery/pipe_support.py::DEFAULT_PARAMETERS.bolt_diameter_mm | equal | 14 | 14 | passed |  |
| cadquery.pipe_support.bolt_spacing_mm | asset_type:support_pipe_bracket_type_a | $.asset_types[support_pipe_bracket_type_a].parameters.bolt_spacing_mm | cadquery/pipe_support.py::DEFAULT_PARAMETERS.bolt_spacing_mm | equal | 150 | 150 | passed |  |
| cadquery.pipe_support.clearance_mm | asset_type:support_pipe_bracket_type_a | $.asset_types[support_pipe_bracket_type_a].parameters.clearance_mm | cadquery/pipe_support.py::DEFAULT_PARAMETERS.clearance_mm | equal | 8 | 8 | passed |  |
| cadquery.pipe_support.height_mm | asset_type:support_pipe_bracket_type_a | $.asset_types[support_pipe_bracket_type_a].parameters.height_mm | cadquery/pipe_support.py::DEFAULT_PARAMETERS.height_mm | equal | 300 | 300 | passed |  |
| cadquery.pipe_support.length_mm | asset_type:support_pipe_bracket_type_a | $.asset_types[support_pipe_bracket_type_a].parameters.length_mm | cadquery/pipe_support.py::DEFAULT_PARAMETERS.length_mm | equal | 220 | 220 | passed |  |
| cadquery.pipe_support.pipe_diameter_mm | asset_type:support_pipe_bracket_type_a | $.asset_types[support_pipe_bracket_type_a].parameters.pipe_diameter_mm | cadquery/pipe_support.py::DEFAULT_PARAMETERS.pipe_diameter_mm | equal | 60 | 60 | passed |  |
| cadquery.pipe_support.web_thickness_mm | asset_type:support_pipe_bracket_type_a | $.asset_types[support_pipe_bracket_type_a].parameters.web_thickness_mm | cadquery/pipe_support.py::DEFAULT_PARAMETERS.web_thickness_mm | equal | 12 | 12 | passed |  |
| cadquery.pipe_support.width_mm | asset_type:support_pipe_bracket_type_a | $.asset_types[support_pipe_bracket_type_a].parameters.width_mm | cadquery/pipe_support.py::DEFAULT_PARAMETERS.width_mm | equal | 120 | 120 | passed |  |
| cadquery.pump_skid_frame.crossmember_count | asset_type:equipment_pump_skid_001 | $.asset_types[equipment_pump_skid_001].parameters.crossmember_count | cadquery/pump_skid_frame.py::DEFAULT_PARAMETERS.crossmember_count | equal | 3 | 3 | passed |  |
| cadquery.pump_skid_frame.height_mm | asset_type:equipment_pump_skid_001 | $.asset_types[equipment_pump_skid_001].parameters.height_mm | cadquery/pump_skid_frame.py::DEFAULT_PARAMETERS.height_mm | equal | 180 | 180 | passed |  |
| cadquery.pump_skid_frame.length_mm | asset_type:equipment_pump_skid_001 | $.asset_types[equipment_pump_skid_001].parameters.length_mm | cadquery/pump_skid_frame.py::DEFAULT_PARAMETERS.length_mm | equal | 1100 | 1100 | passed |  |
| cadquery.pump_skid_frame.rail_width_mm | asset_type:equipment_pump_skid_001 | $.asset_types[equipment_pump_skid_001].parameters.rail_width_mm | cadquery/pump_skid_frame.py::DEFAULT_PARAMETERS.rail_width_mm | equal | 70 | 70 | passed |  |
| cadquery.pump_skid_frame.width_mm | asset_type:equipment_pump_skid_001 | $.asset_types[equipment_pump_skid_001].parameters.width_mm | cadquery/pump_skid_frame.py::DEFAULT_PARAMETERS.width_mm | equal | 520 | 520 | passed |  |
| cadquery.rectangular_duct.duct_height_mm | asset_type:duct_main_001 | $.asset_types[duct_main_001].parameters.duct_height_mm | cadquery/rectangular_duct.py::DEFAULT_PARAMETERS.duct_height_mm | equal | 220 | 220 | passed |  |
| cadquery.rectangular_duct.duct_width_mm | asset_type:duct_main_001 | $.asset_types[duct_main_001].parameters.duct_width_mm | cadquery/rectangular_duct.py::DEFAULT_PARAMETERS.duct_width_mm | equal | 420 | 420 | passed |  |
| cadquery.rectangular_duct.flange_depth_mm | asset_type:duct_main_001 | $.asset_types[duct_main_001].parameters.flange_depth_mm | cadquery/rectangular_duct.py::DEFAULT_PARAMETERS.flange_depth_mm | equal | 26 | 26 | passed |  |
| cadquery.rectangular_duct.length_mm | asset_type:duct_main_001 | $.asset_types[duct_main_001].parameters.length_mm | cadquery/rectangular_duct.py::DEFAULT_PARAMETERS.length_mm | equal | 900 | 900 | passed |  |
| cadquery.rectangular_duct.wall_thickness_mm | asset_type:duct_main_001 | $.asset_types[duct_main_001].parameters.wall_thickness_mm | cadquery/rectangular_duct.py::DEFAULT_PARAMETERS.wall_thickness_mm | equal | 6 | 6 | passed |  |
| cadquery.wall_sleeve.clearance_mm | asset_type:sleeve_wall_penetration_type_a | $.asset_types[sleeve_wall_penetration_type_a].parameters.clearance_mm | cadquery/wall_sleeve.py::DEFAULT_PARAMETERS.clearance_mm | equal | 30 | 30 | passed |  |
| cadquery.wall_sleeve.flange_diameter_mm | asset_type:sleeve_wall_penetration_type_a | $.asset_types[sleeve_wall_penetration_type_a].parameters.flange_diameter_mm | cadquery/wall_sleeve.py::DEFAULT_PARAMETERS.flange_diameter_mm | equal | 190 | 190 | passed |  |
| cadquery.wall_sleeve.flange_thickness_mm | asset_type:sleeve_wall_penetration_type_a | $.asset_types[sleeve_wall_penetration_type_a].parameters.flange_thickness_mm | cadquery/wall_sleeve.py::DEFAULT_PARAMETERS.flange_thickness_mm | equal | 8 | 8 | passed |  |
| cadquery.wall_sleeve.pipe_diameter_mm | asset_type:sleeve_wall_penetration_type_a | $.asset_types[sleeve_wall_penetration_type_a].parameters.pipe_diameter_mm | cadquery/wall_sleeve.py::DEFAULT_PARAMETERS.pipe_diameter_mm | equal | 110 | 110 | passed |  |
| cadquery.wall_sleeve.sleeve_wall_mm | asset_type:sleeve_wall_penetration_type_a | $.asset_types[sleeve_wall_penetration_type_a].parameters.sleeve_wall_mm | cadquery/wall_sleeve.py::DEFAULT_PARAMETERS.sleeve_wall_mm | equal | 6 | 6 | passed |  |
| cadquery.wall_sleeve.wall_thickness_mm | asset_type:sleeve_wall_penetration_type_a | $.asset_types[sleeve_wall_penetration_type_a].parameters.wall_thickness_mm | cadquery/wall_sleeve.py::DEFAULT_PARAMETERS.wall_thickness_mm | equal | 200 | 200 | passed |  |
| openscad.bracket_plate.length_mm | asset_type:openscad_bracket_plate_type_b | $.asset_types[openscad_bracket_plate_type_b].parameters.length_mm | openscad/bracket_plate.scad::plate_length_mm | equal | 180 | 180 | passed |  |
| openscad.bracket_plate.slot_length_mm | asset_type:openscad_bracket_plate_type_b | $.asset_types[openscad_bracket_plate_type_b].parameters.slot_length_mm | openscad/bracket_plate.scad::slot_length_mm | equal | 30 | 30 | passed |  |
| openscad.bracket_plate.slot_spacing_mm | asset_type:openscad_bracket_plate_type_b | $.asset_types[openscad_bracket_plate_type_b].parameters.slot_spacing_mm | openscad/bracket_plate.scad::slot_spacing_mm | equal | 105 | 105 | passed |  |
| openscad.bracket_plate.slot_width_mm | asset_type:openscad_bracket_plate_type_b | $.asset_types[openscad_bracket_plate_type_b].parameters.slot_width_mm | openscad/bracket_plate.scad::slot_width_mm | equal | 11 | 11 | passed |  |
| openscad.bracket_plate.thickness_mm | asset_type:openscad_bracket_plate_type_b | $.asset_types[openscad_bracket_plate_type_b].parameters.thickness_mm | openscad/bracket_plate.scad::plate_thickness_mm | equal | 10 | 10 | passed |  |
| openscad.bracket_plate.width_mm | asset_type:openscad_bracket_plate_type_b | $.asset_types[openscad_bracket_plate_type_b].parameters.width_mm | openscad/bracket_plate.scad::plate_width_mm | equal | 90 | 90 | passed |  |
| openscad.cable_tray.height_mm | asset_type:openscad_cable_tray_segment_type_b | $.asset_types[openscad_cable_tray_segment_type_b].parameters.height_mm | openscad/cable_tray_segment.scad::tray_height_mm | equal | 60 | 60 | passed |  |
| openscad.cable_tray.hole_diameter_mm | asset_type:openscad_cable_tray_segment_type_b | $.asset_types[openscad_cable_tray_segment_type_b].parameters.hole_diameter_mm | openscad/cable_tray_segment.scad::hole_diameter_mm | equal | 16 | 16 | passed |  |
| openscad.cable_tray.hole_pitch_mm | asset_type:openscad_cable_tray_segment_type_b | $.asset_types[openscad_cable_tray_segment_type_b].parameters.hole_pitch_mm | openscad/cable_tray_segment.scad::hole_pitch_mm | equal | 80 | 80 | passed |  |
| openscad.cable_tray.length_mm | asset_type:openscad_cable_tray_segment_type_b | $.asset_types[openscad_cable_tray_segment_type_b].parameters.length_mm | openscad/cable_tray_segment.scad::tray_length_mm | equal | 500 | 500 | passed |  |
| openscad.cable_tray.wall_thickness_mm | asset_type:openscad_cable_tray_segment_type_b | $.asset_types[openscad_cable_tray_segment_type_b].parameters.wall_thickness_mm | openscad/cable_tray_segment.scad::wall_thickness_mm | equal | 4 | 4 | passed |  |
| openscad.cable_tray.width_mm | asset_type:openscad_cable_tray_segment_type_b | $.asset_types[openscad_cable_tray_segment_type_b].parameters.width_mm | openscad/cable_tray_segment.scad::tray_width_mm | equal | 160 | 160 | passed |  |
| openscad.duct_connector.connector_depth_mm | asset_type:openscad_duct_connector_type_b | $.asset_types[openscad_duct_connector_type_b].parameters.connector_depth_mm | openscad/duct_connector.scad::connector_depth_mm | equal | 50 | 50 | passed |  |
| openscad.duct_connector.duct_height_mm | asset_type:openscad_duct_connector_type_b | $.asset_types[openscad_duct_connector_type_b].parameters.duct_height_mm | openscad/duct_connector.scad::duct_height_mm | equal | 180 | 180 | passed |  |
| openscad.duct_connector.duct_width_mm | asset_type:openscad_duct_connector_type_b | $.asset_types[openscad_duct_connector_type_b].parameters.duct_width_mm | openscad/duct_connector.scad::duct_width_mm | equal | 360 | 360 | passed |  |
| openscad.duct_connector.flange_extra_mm | asset_type:openscad_duct_connector_type_b | $.asset_types[openscad_duct_connector_type_b].parameters.flange_extra_mm | openscad/duct_connector.scad::flange_extra_mm | equal | 30 | 30 | passed |  |
| openscad.duct_connector.thickness_mm | asset_type:openscad_duct_connector_type_b | $.asset_types[openscad_duct_connector_type_b].parameters.thickness_mm | openscad/duct_connector.scad::wall_thickness_mm | equal | 5 | 5 | passed |  |
| openscad.pipe_clamp.bolt_diameter_mm | asset_type:openscad_pipe_clamp_type_b | $.asset_types[openscad_pipe_clamp_type_b].parameters.bolt_diameter_mm | openscad/pipe_clamp.scad::bolt_diameter_mm | equal | 8 | 8 | passed |  |
| openscad.pipe_clamp.ear_length_mm | asset_type:openscad_pipe_clamp_type_b | $.asset_types[openscad_pipe_clamp_type_b].parameters.ear_length_mm | openscad/pipe_clamp.scad::ear_length_mm | equal | 28 | 28 | passed |  |
| openscad.pipe_clamp.pipe_diameter_mm | asset_type:openscad_pipe_clamp_type_b | $.asset_types[openscad_pipe_clamp_type_b].parameters.pipe_diameter_mm | openscad/pipe_clamp.scad::pipe_diameter_mm | equal | 50 | 50 | passed |  |
| openscad.pipe_clamp.thickness_mm | asset_type:openscad_pipe_clamp_type_b | $.asset_types[openscad_pipe_clamp_type_b].parameters.thickness_mm | openscad/pipe_clamp.scad::clamp_thickness_mm | equal | 8 | 8 | passed |  |
| openscad.pipe_clamp.width_mm | asset_type:openscad_pipe_clamp_type_b | $.asset_types[openscad_pipe_clamp_type_b].parameters.width_mm | openscad/pipe_clamp.scad::clamp_width_mm | equal | 35 | 35 | passed |  |
| cable_tray_height | occurrence:cable_tray_overhead_001 | $.asset_types[cable_tray_overhead_001].parameters.height_mm | $.occurrences[cable_tray_overhead_001].dimensions_mm[2] | equal | 80 | 80 | passed |  |
| cable_tray_length_override | occurrence:cable_tray_overhead_001 | $.asset_types[cable_tray_overhead_001].parameters.length_mm | $.occurrences[cable_tray_overhead_001].dimensions_mm[0] | override | 900 | 3200 | passed | The placed overhead route is assembled from repeated reusable tray segments. |
| cable_tray_width | occurrence:cable_tray_overhead_001 | $.asset_types[cable_tray_overhead_001].parameters.width_mm | $.occurrences[cable_tray_overhead_001].dimensions_mm[1] | equal | 220 | 220 | passed |  |
| duct_main_height | occurrence:duct_main_001 | $.asset_types[duct_main_001].parameters.duct_height_mm | $.occurrences[duct_main_001].dimensions_mm[2] | equal | 220 | 220 | passed |  |
| duct_main_width | occurrence:duct_main_001 | $.asset_types[duct_main_001].parameters.duct_width_mm | $.occurrences[duct_main_001].dimensions_mm[1] | equal | 420 | 420 | passed |  |
| duct_main_length_override | occurrence:duct_main_001 | $.asset_types[duct_main_001].parameters.length_mm | $.occurrences[duct_main_001].dimensions_mm[0] | override | 900 | 3600 | passed | The placed main duct run is assembled from repeated reusable segments. |
| ahu_pad_length_override | occurrence:equipment_base_type_a | $.asset_types[equipment_base_type_a].parameters.length_mm | $.occurrences[equipment_base_type_a].dimensions_mm[0] | override | 1200 | 1800 | passed | The placed AHU housekeeping pad is larger than the reusable base type. |
| ahu_pad_width_override | occurrence:equipment_base_type_a | $.asset_types[equipment_base_type_a].parameters.width_mm | $.occurrences[equipment_base_type_a].dimensions_mm[1] | override | 800 | 1100 | passed | The placed AHU housekeeping pad is larger than the reusable base type. |
| pump_skid_length_override | occurrence:equipment_pump_skid_001 | $.asset_types[equipment_pump_skid_001].parameters.length_mm | $.occurrences[equipment_pump_skid_001].dimensions_mm[0] | override | 1100 | 1400 | passed | The placed skid coordination envelope includes service and connection space. |
| pump_skid_width_override | occurrence:equipment_pump_skid_001 | $.asset_types[equipment_pump_skid_001].parameters.width_mm | $.occurrences[equipment_pump_skid_001].dimensions_mm[1] | override | 520 | 800 | passed | The placed skid coordination envelope includes service and connection space. |
| pipe_return_length_override | occurrence:pipe_return_001 | $.asset_types[pipe_return_001].parameters.length_mm | $.occurrences[pipe_return_001].dimensions_mm[1] | override | 3600 | 3920 | passed | The placed return route extends to the duty-pump connection. |
| pipe_return_diameter_to_radius | occurrence:pipe_return_001 | $.asset_types[pipe_return_001].parameters.pipe_diameter_mm | $.occurrences[pipe_return_001].dimensions_mm[0] | derived | 40.0 | 40 | passed |  |
| pipe_supply_length | occurrence:pipe_supply_001 | $.asset_types[pipe_supply_001].parameters.length_mm | $.occurrences[pipe_supply_001].dimensions_mm[1] | equal | 3600 | 3600 | passed |  |
| pipe_supply_diameter_to_radius | occurrence:pipe_supply_001 | $.asset_types[pipe_supply_001].parameters.pipe_diameter_mm | $.occurrences[pipe_supply_001].dimensions_mm[0] | derived | 40.0 | 40 | passed |  |
| mounting_plate_length | occurrence:plate_mounting_type_a | $.asset_types[plate_mounting_type_a].parameters.length_mm | $.occurrences[plate_mounting_type_a].dimensions_mm[0] | equal | 260 | 260 | passed |  |
| mounting_plate_thickness | occurrence:plate_mounting_type_a | $.asset_types[plate_mounting_type_a].parameters.thickness_mm | $.occurrences[plate_mounting_type_a].dimensions_mm[2] | equal | 12 | 12 | passed |  |
| mounting_plate_width | occurrence:plate_mounting_type_a | $.asset_types[plate_mounting_type_a].parameters.width_mm | $.occurrences[plate_mounting_type_a].dimensions_mm[1] | equal | 160 | 160 | passed |  |
