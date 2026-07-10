# Validation

Run the full validation suite from the project root:

```bash
.venv/bin/python validation/run_all.py
```

Validators:

- `validate_sources.py`: checks asset IDs, positive parameters, schema coverage, safe paths, and catalog/CadQuery default parity.
- `validate_ifc.py`: opens the IFC with IfcOpenShell and checks hierarchy, semantics, stable identity, millimetre units, ports, and connectivity.
- `validate_manifest.py`: checks required fields, categories, asset IDs, export references, and file sizes.
- `validate_exports.py`: parses STEP, STL, DXF, PDF, and FCStd structure and checks indexed deliverables.

The generated report is `validation/validation_report.md`. Validation does not
modify `manifest/asset_manifest.json`; status is reported separately.
