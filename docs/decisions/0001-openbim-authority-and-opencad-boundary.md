# ADR 0001: Keep OpenBIM semantics authoritative and OpenCAD optional

- Status: accepted
- Date: 2026-07-10

## Context

CoordProof needs richer parametric history and interactive authoring, but its
primary value is inspectable IFC semantics, stable asset identity, connectivity,
manifests, and validation. OpenCAD provides a promising feature DAG and agent/UI
surface, while its headless OCCT selection, reconstruction, topology naming, and
release process are still evolving.

## Decision

CoordProof owns `asset_id`, parameters, IFC classes, systems, ports, placements,
clearance rules, manifests, and acceptance tests. OpenCAD may consume those
parameters to create sidecar geometry and feature-tree artifacts. It cannot
overwrite authoritative STEP or IFC output unless parity tests pass and a future
decision promotes the adapter.

No IFC identity, distribution port, or persistent constraint may reference an
OpenCAD face/edge index.

## Consequences

- The first pilot is intentionally duplicated against one CadQuery asset.
- OpenCAD is a pinned optional dependency and not part of `make all`.
- Geometry parity and clean feature-tree reconstruction are executable gates.
- Upstream incompatibilities are isolated in one integration module.
