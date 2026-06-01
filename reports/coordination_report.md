# Coordination Report

This report is generated from `tools/openbim_core.py`, the same product
schedule used to create `bim/mechanical_room.ifc`. It is intentionally
validation-grade rather than a stamped engineering report. Clearance
failures are explicit; non-clearance intersections are marked REVIEW
because they are a bounding-box coordination screen, not a full clash engine.

## Source Of Truth

| Item | Value |
| --- | ---: |
| BIM product specs | 39 |
| Distribution systems | 5 |
| Port connections | 21 |
| Clash/clearance checks | 20 |
| Failed checks | 0 |
| Review checks | 15 |
| Passed checks | 5 |

## IFC Class Schedule

| IFC Class | Count |
| --- | ---: |
| `IfcAirTerminal` | 2 |
| `IfcBuildingElementPart` | 1 |
| `IfcCableCarrierSegment` | 2 |
| `IfcCoil` | 1 |
| `IfcDamper` | 1 |
| `IfcDoor` | 1 |
| `IfcDuctSegment` | 3 |
| `IfcElementAssembly` | 1 |
| `IfcFan` | 1 |
| `IfcFilter` | 1 |
| `IfcFooting` | 1 |
| `IfcMechanicalFastener` | 4 |
| `IfcPipeFitting` | 2 |
| `IfcPipeSegment` | 4 |
| `IfcPump` | 2 |
| `IfcSensor` | 1 |
| `IfcSlab` | 1 |
| `IfcUnitaryEquipment` | 1 |
| `IfcValve` | 4 |
| `IfcVirtualElement` | 1 |
| `IfcWall` | 4 |

## Category Schedule

| Category | Count |
| --- | ---: |
| `architectural_shell` | 6 |
| `clearance_zone` | 1 |
| `ductwork` | 3 |
| `electrical_routing` | 2 |
| `flow_controller` | 5 |
| `flow_fitting` | 2 |
| `flow_segment` | 4 |
| `instrumentation` | 1 |
| `mechanical_equipment` | 8 |
| `mechanical_support` | 4 |
| `penetration` | 1 |
| `terminal` | 2 |

## Material Schedule

| Material | Count |
| --- | ---: |
| `bronze_valve_body` | 4 |
| `carbon_steel_chwr` | 3 |
| `carbon_steel_chws` | 3 |
| `cast_in_place_concrete` | 1 |
| `clearance_volume` | 1 |
| `concrete` | 5 |
| `copper_aluminum_coil` | 1 |
| `filter_media` | 1 |
| `galvanized_sheet_metal` | 4 |
| `galvanized_steel` | 2 |
| `painted_hollow_metal` | 1 |
| `painted_steel` | 6 |
| `perforated_aluminum` | 2 |
| `powder_coated_steel` | 2 |
| `stainless_steel` | 1 |
| `steel` | 1 |
| `steel_sleeve` | 1 |

## Output Files

- `reports/bill_of_materials.csv`
- `reports/clash_clearance_report.csv`
