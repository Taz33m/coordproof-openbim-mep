# Validation Report

Validation Date: deterministic report; set VALIDATION_DATE to stamp a release

Overall Status: **PASSED**

This report checks IFC readability, semantic MEP class coverage, distribution systems, port connectivity, property sets, manifest completeness, export presence, file sizes, and required asset coverage. It does not perform engineering or code-compliance validation.

## Sources Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `project_spec_schema_version` | 1 |
| `asset_type_count` | 44 |
| `artifact_count` | 12 |
| `source_asset_count` | 56 |
| `cadquery_asset_count` | 9 |
| `placed_occurrence_count` | 39 |
| `schema_parameter_count` | 40 |

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
- CadQuery parameter-sensitivity tests show that each current numeric input changes generated geometry, but reconciliation does not prove exact BRep/mesh dimensions or dimensional parity of committed exports; FreeCAD, drawings, and observed-export measurement remain future scope.

## IFC Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `schema` | IFC4 |
| `entity_count` | 1623 |
| `product_count` | 43 |
| `project_spec_occurrence_count` | 40 |
| `distribution_system_count` | 5 |
| `declared_port_count` | 51 |
| `ifc_port_count` | 51 |
| `connected_port_pair_count` | 22 |
| `project_spec_connection_count` | 22 |
| `proxy_count` | 0 |
| `unique_global_id_count` | 483 |
| `formal_validation_error_count` | 0 |
| `top_entities` | IfcAirTerminal: 2, IfcAxis2Placement3D: 81, IfcBuilding: 1, IfcBuildingElementPart: 1, IfcBuildingStorey: 1, IfcCableCarrierSegment: 2, IfcCartesianPoint: 81, IfcCircleProfileDef: 16, IfcCoil: 1, IfcDamper: 1, IfcDirection: 202, IfcDistributionPort: 51, IfcDistributionSystem: 5, IfcDoor: 1, IfcDuctSegment: 3, IfcElementAssembly: 1, IfcExtrudedAreaSolid: 40, IfcFan: 1, IfcFilter: 1, IfcFooting: 1, IfcGeometricRepresentationContext: 1, IfcLocalPlacement: 40, IfcMaterial: 16, IfcMechanicalFastener: 4, IfcPipeFitting: 2, IfcPipeSegment: 4, IfcProductDefinitionShape: 40, IfcProject: 1, IfcPropertySet: 131, IfcPropertySingleValue: 555, IfcPump: 2, IfcRectangleProfileDef: 24, IfcRelAggregates: 4, IfcRelAssignsToGroup: 5, IfcRelAssociatesMaterial: 38, IfcRelConnectsPortToElement: 51, IfcRelConnectsPorts: 22, IfcRelContainedInSpatialStructure: 1, IfcRelDefinesByProperties: 131, IfcSIUnit: 3, IfcSensor: 1, IfcShapeRepresentation: 40, IfcSite: 1, IfcSlab: 1, IfcSpace: 1, IfcUnitAssignment: 1, IfcUnitaryEquipment: 1, IfcValve: 4, IfcVirtualElement: 1, IfcWall: 4 |

### Failures

- None

### Warnings

- None

## Manifest Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `asset_count` | 56 |
| `category_count` | 15 |
| `export_reference_count` | 83 |

### Failures

- None

### Warnings

- None

## Exports Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `required_file_count` | 46 |
| `generated_export_count` | 42 |
| `indexed_export_count` | 52 |

### Failures

- None

### Warnings

- None
