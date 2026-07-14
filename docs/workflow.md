# Workflow

This project is built as a reproducible asset pipeline rather than a one-off model.

Check the portable environment with `make doctor`. Use `make core` for the
Python/IfcOpenShell/CadQuery path. `make all` is the complete desktop profile and
requires FreeCAD, OpenSCAD, and QCAD; run `make doctor-full` first.

## 0. Use the Installable ProjectSpec CLI

Install CoordProof from a checkout:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install .
```

The default CLI workflow applies to ProjectSpec v1 files that satisfy the
versioned class, geometry, and port-host contract:

```bash
.venv/bin/coordproof validate PROJECT.json
.venv/bin/coordproof summary PROJECT.json
.venv/bin/coordproof build PROJECT.json --output build/project-evidence
```

The `evidence` build publishes a normalized ProjectSpec, JSON summary, IFC,
IFC entity summary, semantic inventory, and SHA-256 build manifest. The source
file is snapshotted before generation, publication uses a staging directory,
the normalized contract records the schema's stable HTTPS ID, the IFC receives
formal EXPRESS validation before publication, and the output is independent of
the caller's working directory. The generic
path is exercised by both the mechanical-room contract and
`examples/electrical_room/electrical_room.project.json`.

The repository's multi-tool `core` and `full` profiles remain canonical
mechanical-room builds. They can be requested with `--profile core` or
`--profile full` for `spec/mechanical_room.project.json` from a source checkout,
but noncanonical ProjectSpec files must use the `evidence` profile until the CAD,
drawing, and report adapters are generalized.

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

## 2. Reconcile Producer Parameters

```bash
make reconcile
```

`spec/reconciliation.contract.json` binds 75 canonical ProjectSpec engineering
parameters to producer inputs and to explicit type-to-occurrence relations. It
also accounts for all 78 observed top-level producer numeric inputs: 75 mapped
values plus three explicitly excluded OpenSCAD `$fn` facet controls. Those
controls affect tessellation rather than engineering dimensions. The contract
never repeats expected engineering values. The reconciler rejects unmapped
inputs, unexplained exclusions or differences, unsafe transforms, and overrides
without a rationale, then writes:

- `reports/parameter_reconciliation.csv`
- `reports/parameter_reconciliation.md`

The first enforced scope covers all required CadQuery and OpenSCAD producers,
75/75 canonical engineering parameters, 78/78 observed top-level numeric inputs,
and selected occurrence relations. FreeCAD and drawing adapters remain an
explicit follow-up boundary.

For CadQuery, the source gate requires canonical ProjectSpec forwarding, bounded
literal reads of the merged mapping, consumption of every numeric fallback, and
a differential test showing that each current numeric input changes the shape
signature. For OpenSCAD, it validates literal declarations and the generator's
`-D` injection boundary. This source-level reconciliation remains distinct from
the direct observed-geometry inspection in step 8.

## 3. Generate Structured Metadata

```bash
.venv/bin/python tools/build_manifest.py
```

Outputs:

- `manifest/asset_manifest.json`
- `manifest/parameter_schema.json`
- `manifest/export_index.csv`
- `bim/bim_object_map.csv`

## 4. Generate Parametric CAD Assets

```bash
.venv/bin/python cadquery/generate_all.py
.venv/bin/python tools/generate_openscad_exports.py
```

Outputs:

- STEP files in `exports/step/`
- STL files in `exports/stl/`

CadQuery builders receive ProjectSpec parameters explicitly. OpenSCAD commands
inject every mapped value through deterministic `-D` arguments; source-file
assignments remain readable defaults, not an independent build authority.

## 5. Generate Review Drawings

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

## 6. Create the FreeCAD Model

Use the deterministic macro at `freecad/build_mechanical_room.FCMacro`.

Automated FreeCAD build:

```bash
.venv/bin/python tools/generate_freecad_assets.py
```

Target outputs:

- `freecad/mechanical_room.FCStd`
- `freecad/mechanical_room_bim.FCStd`
- screenshots in `screenshots/`

## 7. Generate IFC-First OpenBIM

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

## 8. Measure Observed Geometry

```bash
make observed-geometry
```

`tools/generate_observed_geometry_matrix.py` derives expected bounds from
ProjectSpec and compares them with geometry read directly from the committed
IFC, STEP, STL, and selected floor-plan DXF entities. It writes:

- `reports/observed_geometry_matrix.csv`
- `reports/observed_geometry_matrix.md`

The current matrix contains 69 passing observations, no failures, and one
explicit exclusion for `mechanical_room_assembly.step`, whose legacy FreeCAD
decomposition has not yet been completely projected from ProjectSpec. Bounds
parity verifies placement and envelope dimensions; it does not certify topology,
fabrication readiness, or engineering performance.

These reviewed adapters currently certify only the canonical mechanical-room
package. Passing another `--project-spec` fails cleanly until project-scoped CAD
and drawing observation adapters are available.

## 9. Validate

```bash
.venv/bin/python validation/run_all.py
```

The report is written to `validation/validation_report.md` and includes live
reconciliation and observed-geometry results. Validation also rejects a stale
committed geometry matrix.

## 10. Record Provenance

```bash
.venv/bin/python tools/build_provenance.py
```

This writes hashes and tool versions to `manifest/build_provenance.json`.
Set `SOURCE_DATE_EPOCH` when producing a reproducibly timestamped release.

## 11. Compare Two External IFC Models

The installable clash pilot performs a bounded cross-model set with the compiled
IfcOpenShell geometry tree:

```bash
.venv/bin/coordproof clash architecture.ifc mep.ifc \
  --a-label Architecture --b-label MEP \
  --a-class IfcBuildingElement --b-class IfcDistributionElement \
  --mode intersection --output clashes.json --fail-on-clash
```

JSON output is deterministic and identifies both inputs by SHA-256 rather than
embedding local paths. Install the optional BCF writer and add `--bcf` for a BCF
3.0 issue package:

```bash
.venv/bin/python -m pip install -e '.[bcf]'
.venv/bin/coordproof clash architecture.ifc mep.ifc \
  --output clashes.json --bcf clashes.bcfzip
```

The pilot accepts two distinct, uncompressed IFC files in one coordinate frame.
It does not run intra-model checks, align federated coordinates, or implement a
complete issue-management workflow. Its triangle limit is a post-tessellation
count gate, not a hard memory/time sandbox. See [limitations](limitations.md)
before using it as a project gate.

## 12. Optional OpenCAD Feature-Tree Pilot

```bash
make install-opencad
make opencad-pilot
```

The pilot writes disposable sidecars under `build/opencad/` and validates real
STEP plus feature-tree reconstruction parity. It does not replace authoritative
CadQuery or IFC artifacts.
