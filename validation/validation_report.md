# Validation Report

Validation Date: deterministic report; set VALIDATION_DATE to stamp a release

Overall Status: **PASSED**

This report checks IFC readability, semantic MEP class coverage, distribution systems, port connectivity, property sets, manifest completeness, export presence, file sizes, and required asset coverage. It does not perform engineering or code-compliance validation.

## IFC Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `schema` | IFC4 |
| `entity_count` | 1283 |
| `product_count` | 43 |
| `distribution_system_count` | 5 |
| `connected_port_pair_count` | 21 |
| `manifest_ifc_asset_count` | 41 |
| `proxy_count` | 0 |
| `top_entities` | IfcAirTerminal: 2, IfcAxis2Placement3D: 81, IfcBuilding: 1, IfcBuildingElementPart: 1, IfcBuildingStorey: 1, IfcCableCarrierSegment: 2, IfcCartesianPoint: 81, IfcCircleProfileDef: 16, IfcCoil: 1, IfcDamper: 1, IfcDirection: 202, IfcDistributionPort: 51, IfcDistributionSystem: 5, IfcDoor: 1, IfcDuctSegment: 3, IfcElementAssembly: 1, IfcExtrudedAreaSolid: 40, IfcFan: 1, IfcFilter: 1, IfcFooting: 1, IfcGeometricRepresentationContext: 1, IfcLocalPlacement: 40, IfcMaterial: 17, IfcMechanicalFastener: 4, IfcPipeFitting: 2, IfcPipeSegment: 4, IfcProductDefinitionShape: 40, IfcProject: 1, IfcPropertySet: 79, IfcPropertySingleValue: 318, IfcPump: 2, IfcRectangleProfileDef: 24, IfcRelAggregates: 4, IfcRelAssignsToGroup: 5, IfcRelAssociatesMaterial: 39, IfcRelConnectsPortToElement: 51, IfcRelConnectsPorts: 21, IfcRelContainedInSpatialStructure: 1, IfcRelDefinesByProperties: 79, IfcSIUnit: 3, IfcSensor: 1, IfcShapeRepresentation: 40, IfcSite: 1, IfcSlab: 1, IfcSpace: 1, IfcUnitAssignment: 1, IfcUnitaryEquipment: 1, IfcValve: 4, IfcVirtualElement: 1, IfcWall: 4 |

### Failures

- None

### Warnings

- None

## Manifest Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `asset_count` | 55 |
| `category_count` | 15 |
| `export_reference_count` | 81 |

### Failures

- None

### Warnings

- None

## Exports Validation

Status: **PASSED**

### Summary

| Metric | Value |
| --- | --- |
| `required_file_count` | 44 |
| `generated_export_count` | 40 |
| `indexed_export_count` | 50 |

### Failures

- None

### Warnings

- None
