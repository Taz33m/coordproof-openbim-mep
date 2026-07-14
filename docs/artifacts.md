# Artifact policy

CoordProof separates editable sources, a small golden evidence package, and
local experimental outputs.

## Tracked source

- Python generators and validators
- FreeCAD macros and OpenSCAD source
- `spec/mechanical_room.project.json`, the independent electrical-room example,
  their shared JSON Schema, the versioned reconciliation contract/schema, and
  geometry-source implementations
- documentation, tests, and CI configuration

## Tracked golden evidence

The repository includes one synthetic mechanical-room package so IFC/CAD tools
can be evaluated without running every desktop exporter. It includes IFC, STEP,
STL, DXF, PDF, FCStd, reports, manifests, and review images. These files must be
regenerated from reviewed source changes and pass `make spec-validate`,
`make reconcile`, `make observed-geometry`, `make validate`, and
`make preflight`. The tracked observed-geometry CSV/Markdown pair must be
derived from the live committed IFC/STEP/STL/DXF files; one explicit FreeCAD assembly
exclusion remains visible until that legacy decomposition is reconciled.

`manifest/build_provenance.json` records artifact SHA-256 hashes and the software
environment used to refresh the package. `source_date` uses
`SOURCE_DATE_EPOCH`, which defaults to the reproducible Unix epoch when unset.
Use `make install-release` with `constraints-release.txt` when refreshing this
golden package; ordinary compatibility CI continues to exercise the supported
ranges in `requirements.txt`.

## Untracked local outputs

`build/` is disposable and ignored. Generic six-file `coordproof build` evidence
bundles, portable drawing previews, and optional integrations such as OpenCAD
write there so fallback tools and experiments cannot silently replace
authoritative evidence. Release CI may upload full packages as workflow/release
artifacts.

Do not commit customer models, credentials, environment files, CAD backups, or
exports whose editable source is unavailable.
