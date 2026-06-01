# Modeling Assumptions

- Units are millimeters across CAD, BIM, drawings, and metadata.
- The mechanical room is illustrative and sized for technical inspection, not construction.
- Equipment geometry is coordination-level and named/parameterized for data reuse; it is not manufacturer-fabrication geometry.
- Pipe and duct routes represent coordinated flow paths and IFC connectivity, not engineered hydraulic or airflow calculations.
- Clearance volumes are modeled as explicit assets because AI/CAD workflows often need machine-readable spatial intent.
- IFC classification is explicit for the authoritative OpenBIM scope. The semantic model uses specific IFC4 MEP classes and the validator fails if major systems fall back to generic `IfcBuildingElementProxy` objects. FreeCAD visual helpers are supporting review artifacts, not the source of the zero-proxy validation result.
- Flow connectivity is represented as a validation-grade network of systems and ports, not as engineered hydraulic or airflow sizing.
- QCAD drawings are generated as DXF/PDF review sheets and should receive a final QCAD drafting pass before public submission.
