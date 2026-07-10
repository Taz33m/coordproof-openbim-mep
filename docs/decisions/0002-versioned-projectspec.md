# ADR 0002: Adopt a versioned ProjectSpec as the project contract

- Status: accepted
- Date: 2026-07-10

## Context

CoordProof previously declared reusable asset metadata in `asset_catalog.py` and
placed IFC schedule data in `openbim_core.py`. That separation was useful, but it
also allowed identity, dimensions, system membership, ports, and artifact
coverage to drift between independently maintained structures.

Reusable definitions and placements are not the same thing. A type can be used
more than once, and a placed occurrence can carry coordination geometry or
properties that should not mutate the reusable type. Generated documents are
deliverables, not modeled occurrences, even when older flat manifests expose all
three concepts through one `asset_id` column.

## Decision

`spec/mechanical_room.project.json` is the authoritative versioned project
contract. ProjectSpec v1 uses separate namespaces for:

- reusable asset types;
- placed occurrences;
- generated artifacts;
- systems and connections.

The JSON Schema defines the portable structure. `tools/project_spec.py` adds
semantic checks that JSON Schema alone cannot express cleanly, including
reference integrity, contiguous catalog ordering, safe export paths, complete
port-system bindings, and connection compatibility.

Generator-facing modules may expose typed or legacy-compatible projections, but
must not re-declare the same project data independently. Geometry algorithms and
tool-specific constraints remain in their CadQuery, OpenSCAD, FreeCAD, and
drawing implementations and are checked against the contract.

A breaking reinterpretation requires a new `schema_version`; changing the schema
file without changing the version does not authorize silent migration.

## Consequences

- Builds and CI validate ProjectSpec before regeneration.
- Existing flat catalog and product-schedule consumers can migrate through
  deterministic compatibility projections.
- IDs are interpreted in their typed namespaces; a type and an occurrence may
  deliberately share the same text without becoming the same entity.
- Port-to-system intent is explicit and connectivity errors fail early.
- Cross-format dimensional parity is still a separate milestone. Differences
  between type parameters, occurrence geometry, and generated solids must be
  classified as equal, derived, or intentional overrides before they can be
  considered reconciled.
