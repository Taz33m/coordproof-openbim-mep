# OpenSCAD Asset Library

OpenSCAD is used here as a secondary code-CAD layer. These assets are intentionally small and declarative so the parameters can be inspected quickly.

Files:

- `pipe_clamp.scad`
- `bracket_plate.scad`
- `cable_tray_segment.scad`
- `duct_connector.scad`

Regenerate all OpenSCAD STL exports:

```bash
.venv/bin/python tools/generate_openscad_exports.py
```

Or export manually:

```bash
openscad -o exports/stl/openscad_pipe_clamp_type_b.stl openscad/pipe_clamp.scad
```

The source `.scad` files are also listed in the asset manifest.
