# Validation

Run the full validation suite from the project root:

```bash
.venv/bin/python validation/run_all.py
```

Validators:

- `validate_sources.py`: checks asset IDs, positive parameters, schema coverage, safe paths, and catalog/CadQuery default parity.
- `validate_reconciliation.py`: checks the required producer inventory, 75/75
  canonical engineering-parameter bindings, accounting for 78/78 observed
  top-level numeric inputs (including three explicit OpenSCAD `$fn` technical
  exclusions), bounded CadQuery input consumption, safe derived relations, and
  justified occurrence overrides. Geometry sensitivity is exercised by the
  test suite; direct committed-export inspection is handled separately below.
- `validate_ifc.py`: opens the IFC with IfcOpenShell and checks hierarchy, semantics, stable identity, millimetre units, ports, and connectivity.
- `validate_observed_geometry.py`: derives expected minimum/maximum bounds from
  ProjectSpec, reads committed IFC/STEP/STL and selected DXF geometry, rejects
  failing or stale evidence, and reports the one explicit legacy FreeCAD
  assembly exclusion. The current matrix is 69 PASS, 0 FAIL, and 1 EXCLUDED.
- `validate_manifest.py`: checks required fields, file sizes, and exact catalog
  field/order parity with the ProjectSpec projection.
- `validate_exports.py`: parses STEP, STL, DXF, PDF, and FCStd structure and
  requires the export index to match every ProjectSpec export reference exactly.

The generated report is `validation/validation_report.md`. Validation does not
modify `manifest/asset_manifest.json`; status is reported separately.
