# Contributing to CoordProof

CoordProof welcomes narrowly scoped improvements to OpenBIM semantics, parametric
assets, drawings, validation, portability, and documentation. Every model change
must remain traceable to a stable ProjectSpec ID and include machine-checkable
evidence.

## Development setup

Supported Python versions are 3.11 and 3.12. Python 3.11 is the reference CI
environment.

```bash
make install-dev
make doctor
make spec-validate
make reconcile
make lint
make test
make validate
make preflight
```

The portable core uses Python, IfcOpenShell, CadQuery, ezdxf, ReportLab, and
Pillow. ReportLab PDFs are disposable previews under `build/portable/`, not
replacements for tracked QCAD exports. The full evidence build additionally
needs FreeCAD, OpenSCAD, and QCAD's `dwg2pdf` command:

```bash
make doctor-full
make all
```

The full build stages and validates desktop outputs before atomically replacing
tracked artifacts. Run it twice after changing a desktop generator and require
the second run to produce no tracked diff; do not bypass a strict normalizer
when a vendor changes its output shape.

Set `FREECAD_CMD`, `OPENSCAD_CMD`, or `QCAD_DWG2PDF` when those tools are not on
`PATH`. The optional OpenCAD experiment has a separate pinned environment:

```bash
make install-opencad
make opencad-pilot
```

## Change contract

For a new or changed asset:

1. Decide whether the change belongs to a reusable `asset_type`, a placed
   `occurrence`, or a generated `artifact`; do not collapse those namespaces.
2. Use stable lowercase IDs and update the canonical declaration in
   `spec/mechanical_room.project.json`.
3. Run `make spec-validate` before regeneration. If the contract itself changes,
   update `spec/project.schema.json`, the loader, migration tests, and changelog
   together; do not silently reinterpret an existing `schema_version`. Update
   the reviewed v1 migration fingerprint in `tests/test_project_spec_runtime.py`
   and explain the semantic change.
4. Update `spec/reconciliation.contract.json` when a producer input, alias, or
   type-to-occurrence relationship changes. Every scoped numeric input must be
   bound. Derived relations use the supported operator vocabulary; overrides
   require a concrete rationale.
5. Keep CadQuery `DEFAULT_PARAMETERS` synchronized as standalone fallbacks;
   production generation passes ProjectSpec parameters explicitly. OpenSCAD
   aliases must remain complete so every command-line `-D` value comes from
   ProjectSpec. Occurrence coordination dimensions may differ only when that
   distinction is explicit and tested.
6. Regenerate affected STEP/STL, manifests, IFC, reports, and drawings.
7. Add or update tests for dimensions, references, port-system bindings, and
   invalid parameter combinations.
8. Run validation and inspect both reconciliation and validation reports—not
   only screenshots.

Use `make spec-summary` to review normalized inventory counts after a model
change. `tools/asset_catalog.py` and `tools/openbim_core.py` are compatibility
projections for generators and downstream code; they are not independent places
to declare project data.

Never map long-lived IFC identity or ports to transient CAD face/edge indices.

## Pull requests

Keep unrelated generated changes out of the patch. List affected asset IDs and
include focused before/after evidence for geometry changes. Generated binaries
must come from deterministic source changes; hand-edited exports are not accepted.

By submitting a contribution, you agree that it is licensed under Apache-2.0.
See the Code of Conduct and Security Policy before participating.
