# Validation Report

Validation Date: deterministic report; set VALIDATION_DATE to stamp a release

Overall Status: **PASSED**

This report checks IFC readability, semantic MEP class coverage, distribution systems, port connectivity, property sets, observed IFC/STEP/STL/DXF bounding-envelope parity, manifest completeness, export presence, file sizes, and required asset coverage. It does not perform engineering or code-compliance validation.

## Sources Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `project_spec_schema_version` | 1 |
| `asset_type_count` | 44 |
| `artifact_count` | 13 |
| `source_asset_count` | 57 |
| `cadquery_asset_count` | 9 |
| `placed_occurrence_count` | 39 |
| `schema_parameter_count` | 41 |

### Failures

- None

### Warnings

- None

## Parameter Reconciliation Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `contract_schema_version` | 1 |
| `producer_count` | 13 |
| `required_producer_count` | 13 |
| `relation_count` | 17 |
| `row_count` | 95 |
| `passed_row_count` | 95 |
| `failed_row_count` | 0 |
| `scoped_numeric_parameter_count` | 75 |
| `covered_numeric_parameter_count` | 75 |
| `producer_input_count` | 78 |
| `covered_producer_input_count` | 78 |
| `excluded_producer_input_count` | 3 |
| `producer_error_count` | 0 |
| `failure_count` | 0 |
| `committed_report_count` | 2 |

### Failures

- None

### Warnings

- This v1 contract verifies CadQuery fallback mappings and canonical ProjectSpec forwarding, OpenSCAD literal declarations and deterministic -D injection, and declared type-to-occurrence relations.
- CadQuery parameter-sensitivity tests show that each current numeric input changes generated geometry, but reconciliation does not prove exact BRep/mesh dimensions or dimensional parity of committed exports by itself. The separate observed-geometry gate now checks current IFC, STEP, STL, and selected DXF bounds; FreeCAD assembly decomposition, unselected drawing entities, and topology remain outside that scope.

## IFC Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `schema` | IFC4 |
| `entity_count` | 1843 |
| `product_count` | 43 |
| `project_spec_occurrence_count` | 40 |
| `distribution_system_count` | 5 |
| `declared_port_count` | 51 |
| `ifc_port_count` | 51 |
| `connected_port_pair_count` | 22 |
| `project_spec_connection_count` | 22 |
| `proxy_count` | 0 |
| `unique_global_id_count` | 563 |
| `formal_validation_error_count` | 0 |
| `top_entities` | IfcAirTerminal: 2, IfcAxis2Placement3D: 81, IfcBuilding: 1, IfcBuildingElementPart: 1, IfcBuildingStorey: 1, IfcCableCarrierSegment: 2, IfcCartesianPoint: 81, IfcCircleProfileDef: 16, IfcCoil: 1, IfcDamper: 1, IfcDirection: 202, IfcDistributionPort: 51, IfcDistributionSystem: 5, IfcDoor: 1, IfcDuctSegment: 3, IfcElementAssembly: 1, IfcExtrudedAreaSolid: 40, IfcFan: 1, IfcFilter: 1, IfcFooting: 1, IfcGeometricRepresentationContext: 1, IfcLocalPlacement: 40, IfcMaterial: 16, IfcMechanicalFastener: 4, IfcPipeFitting: 2, IfcPipeSegment: 4, IfcProductDefinitionShape: 40, IfcProject: 1, IfcPropertySet: 171, IfcPropertySingleValue: 695, IfcPump: 2, IfcRectangleProfileDef: 24, IfcRelAggregates: 4, IfcRelAssignsToGroup: 5, IfcRelAssociatesMaterial: 38, IfcRelConnectsPortToElement: 51, IfcRelConnectsPorts: 22, IfcRelContainedInSpatialStructure: 1, IfcRelDefinesByProperties: 171, IfcSIUnit: 3, IfcSensor: 1, IfcShapeRepresentation: 40, IfcSite: 1, IfcSlab: 1, IfcSpace: 1, IfcUnitAssignment: 1, IfcUnitaryEquipment: 1, IfcValve: 4, IfcVirtualElement: 1, IfcWall: 4 |

### Failures

- None

### Warnings

- None

## Observed Geometry Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `observation_count` | 70 |
| `passing_observation_count` | 69 |
| `failed_observation_count` | 0 |
| `explicit_exclusion_count` | 1 |
| `format_observation_counts` | dxf: 7, ifc: 40, step: 10, stl: 13 |
| `committed_report_count` | 2 |
| `failure_count` | 0 |

### Failures

- None

### Warnings

- [EXPLICIT_EXCLUSION] exports/step/mechanical_room_assembly.step: The assembly combines many legacy FreeCAD primitives; it is explicitly outside v1 observed-envelope certification until its decomposition adapter is complete.

## Manifest Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `asset_count` | 57 |
| `category_count` | 15 |
| `export_reference_count` | 85 |

### Failures

- None

### Warnings

- None

## Exports Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `required_file_count` | 48 |
| `generated_export_count` | 44 |
| `indexed_export_count` | 54 |
| `indexed_export_reference_count` | 85 |

### Failures

- None

### Warnings

- None
