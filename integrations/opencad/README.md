# OpenCAD pilot

This opt-in integration reconstructs `plate_mounting_type_a` through OpenCAD's
feature DAG and real OCCT backend. It exports sidecar STEP, feature-tree, and
CAID design JSON files under `build/opencad/`; it never overwrites CoordProof's
authoritative CadQuery export.

## Run

```bash
make install-opencad
make opencad-pilot
```

The command fails unless:

- the output is a genuine ISO 10303 STEP file rather than OpenCAD's analytic mock;
- its bounding box and volume match the canonical CadQuery plate;
- the serialized feature tree can be forced through a clean OCCT rebuild; and
- the rebuilt geometry also passes the parity thresholds.

OpenCAD is pinned to revision
`be5bbfe915f98bc61e5ea62f3c88bc6d28b96d54`. At that revision its fluent
`RuntimeContext` does not select the OCCT backend automatically, so the pilot
contains a narrowly scoped compatibility bridge. Remove the bridge only after
upstream headless real-kernel export and reconstruction are covered by tests.

CoordProof remains authoritative for parameters, `asset_id`, IFC semantics,
ports, systems, manifests, and validation. OpenCAD face or edge identifiers are
not persisted into IFC because stable topology naming remains unresolved.
