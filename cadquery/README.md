# CadQuery Asset Library

This directory contains reusable parametric mechanical room assets. Each script:

- defines a clear parameter block in millimeters,
- exposes a `build(parameters=None)` function,
- exports STEP and STL when run directly,
- maps to an entry in `manifest/asset_manifest.json`.

Regenerate all assets from the project root:

```bash
.venv/bin/python cadquery/generate_all.py
```

The geometry is intentionally compact and inspectable. These are structured CAD/AEC assets for the generated coordination package, not decorative product renderings.
