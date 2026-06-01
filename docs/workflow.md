# Workflow

This project is built as a reproducible asset pipeline rather than a one-off model.

## 1. Generate Structured Metadata

```bash
.venv/bin/python tools/build_manifest.py
```

Outputs:

- `manifest/asset_manifest.json`
- `manifest/parameter_schema.json`
- `manifest/export_index.csv`
- `bim/bim_object_map.csv`

## 2. Generate Parametric CAD Assets

```bash
.venv/bin/python cadquery/generate_all.py
.venv/bin/python tools/generate_openscad_exports.py
```

Outputs:

- STEP files in `exports/step/`
- STL files in `exports/stl/`

## 3. Generate Review Drawings

```bash
.venv/bin/python tools/generate_drawings.py
.venv/bin/python tools/export_qcad_pdfs.py
```

Outputs:

- DXF files in `qcad/`
- PDF files in `qcad/pdf_exports/`

The first command generates QCAD-ready DXF sheets. The second command uses QCAD's `dwg2pdf` command-line exporter to produce the final PDFs.

## 4. Create the FreeCAD Model

Use the deterministic macro at `freecad/build_mechanical_room.FCMacro`.

Automated FreeCAD build:

```bash
.venv/bin/python tools/generate_freecad_assets.py
```

Target outputs:

- `freecad/mechanical_room.FCStd`
- `freecad/mechanical_room_bim.FCStd`
- screenshots in `screenshots/`

## 5. Generate IFC-First OpenBIM

The primary IFC is generated from the semantic OpenBIM core:

```bash
.venv/bin/python tools/generate_ifc.py
```

This writes:

- `bim/mechanical_room.ifc`
- `bim/ifc_entity_summary.md`
- `bim/openbim_semantic_inventory.csv`

The FreeCAD BIM-organized model remains a review artifact and can still be
exported manually to `bim/mechanical_room_freecad_review.ifc`, but validation
treats `tools/openbim_core.py` as the source of truth for IFC classes, systems,
ports, properties, and manifest coverage.

## 6. Validate

```bash
.venv/bin/python validation/run_all.py
```

The report is written to `validation/validation_report.md`.
