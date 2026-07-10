# Workflow

This project is built as a reproducible asset pipeline rather than a one-off model.

Check the portable environment with `make doctor`. Use `make core` for the
Python/IfcOpenShell/CadQuery path. `make all` is the complete desktop profile and
requires FreeCAD, OpenSCAD, and QCAD; run `make doctor-full` first.

## 1. Validate the Project Contract

```bash
make spec-validate
make spec-summary
```

`spec/mechanical_room.project.json` is the versioned source of truth for reusable
asset types, placed occurrences, artifact inventory, systems, ports, connections,
and required coverage. Structural rules live in `spec/project.schema.json`; the
loader also enforces semantic rules such as reference integrity, safe export
paths, and complete port-to-system bindings. Both `make core` and `make all`
validate this contract before running generators.

## 2. Generate Structured Metadata

```bash
.venv/bin/python tools/build_manifest.py
```

Outputs:

- `manifest/asset_manifest.json`
- `manifest/parameter_schema.json`
- `manifest/export_index.csv`
- `bim/bim_object_map.csv`

## 3. Generate Parametric CAD Assets

```bash
.venv/bin/python cadquery/generate_all.py
.venv/bin/python tools/generate_openscad_exports.py
```

Outputs:

- STEP files in `exports/step/`
- STL files in `exports/stl/`

## 4. Generate Review Drawings

```bash
.venv/bin/python tools/generate_drawings.py
.venv/bin/python tools/export_qcad_pdfs.py
```

Outputs:

- DXF files in `qcad/`
- Portable PDF previews in `build/portable/qcad_pdf_previews/`
- Canonical QCAD PDF files in `qcad/pdf_exports/` after the second command

The first command generates QCAD-ready DXF sheets and disposable ReportLab
previews. The second command uses QCAD's `dwg2pdf` command-line exporter to
produce the final PDFs. Portable/core builds never overwrite canonical QCAD
exports.

## 5. Create the FreeCAD Model

Use the deterministic macro at `freecad/build_mechanical_room.FCMacro`.

Automated FreeCAD build:

```bash
.venv/bin/python tools/generate_freecad_assets.py
```

Target outputs:

- `freecad/mechanical_room.FCStd`
- `freecad/mechanical_room_bim.FCStd`
- screenshots in `screenshots/`

## 6. Generate IFC-First OpenBIM

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
treats the ProjectSpec as the source of truth for IFC classes, systems, ports,
connections, properties, and manifest coverage. `tools/openbim_core.py` is its
typed generator-facing projection.

## 7. Validate

```bash
.venv/bin/python validation/run_all.py
```

The report is written to `validation/validation_report.md`.

## 8. Record Provenance

```bash
.venv/bin/python tools/build_provenance.py
```

This writes hashes and tool versions to `manifest/build_provenance.json`.
Set `SOURCE_DATE_EPOCH` when producing a reproducibly timestamped release.

## 9. Optional OpenCAD Feature-Tree Pilot

```bash
make install-opencad
make opencad-pilot
```

The pilot writes disposable sidecars under `build/opencad/` and validates real
STEP plus feature-tree reconstruction parity. It does not replace authoritative
CadQuery or IFC artifacts.
