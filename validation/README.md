# Validation

Run the full validation suite from the project root:

```bash
.venv/bin/python validation/run_all.py
```

Validators:

- `validate_ifc.py`: opens the IFC with IfcOpenShell and checks hierarchy, entities, object names, and units.
- `validate_manifest.py`: checks required fields, categories, asset IDs, export references, and file sizes.
- `validate_exports.py`: checks STEP, STL, DXF, PDF, and IFC deliverables.

The generated report is `validation/validation_report.md`.
