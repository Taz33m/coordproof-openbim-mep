# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and uses semantic versioning for source and evidence-contract releases.

## [Unreleased]

## [0.2.0] - 2026-07-13

### Added

- Installable `coordproof` CLI with `validate`, `summary`, and deterministic
  `build` commands for supported, semantically valid ProjectSpec v1 files.
- Generic six-file OpenBIM evidence bundles containing a normalized contract,
  inventory summary, IFC, IFC entity summary, semantic inventory, and SHA-256
  manifest, published through a guarded staging boundary.
- Independent electrical-room ProjectSpec example with 12 asset types, 16
  occurrences, 3 artifacts, 4 systems, 12 connections, and 24 connected ports.
- Native IFC electrical distribution classes and formal EXPRESS validation for
  every generic evidence build before publication.
- Bounded external two-IFC clash pilot using IfcOpenShell's compiled geometry
  tree, with deterministic JSON, collision/intersection/clearance modes,
  resource limits, stable clash identities, and optional deterministic BCF 3.0.
- Direct observed-geometry CSV/Markdown evidence for IFC, STEP, STL, and selected
  DXF envelopes, currently reporting 69 PASS, 0 FAIL, and one explicit legacy
  FreeCAD assembly exclusion.
- Versioned ProjectSpec v1 and JSON Schema separating reusable asset types,
  placed occurrences, generated artifacts, systems, ports, and connections.
- Structural and semantic ProjectSpec validation with inventory summaries and
  early build/CI gates.
- Optional, pinned OpenCAD mounting-plate pilot with real STEP, feature-tree
  reconstruction, and CadQuery geometry-parity gates.
- Source-contract, geometry, IFC identity, and artifact-structure tests.
- Linux CI, CodeQL, Dependabot, issue forms, and a pull-request evidence template.
- Build doctor, portable core profile, and SHA-256 build provenance.
- Provenance schema v2 records sanitized desktop-tool versions and the OCCT and
  IfcOpenShell versions embedded by FreeCAD exports.
- Apache-2.0 licensing and community health documentation.
- Versioned cross-format reconciliation contract, deterministic CSV/Markdown
  evidence, safe derived relations, and mandatory override rationales.
- Complete reconciliation of 75/75 canonical engineering parameters across all
  required CadQuery and OpenSCAD producers, including ten previously undeclared
  OpenSCAD parameters.
- Complete accounting for 78/78 observed top-level producer numeric inputs,
  including three explicitly excluded OpenSCAD `$fn` facet controls.

### Changed

- Asset-catalog and OpenBIM schedules are compatibility projections of the
  authoritative mechanical-room ProjectSpec.
- OpenBIM generation accepts a validated ProjectSpec instance and scopes
  noncanonical IFC identities to that project while preserving the reviewed
  mechanical-room identity contract.
- The canonical mechanical-room ProjectSpec now declares 44 asset types, 40
  occurrences, 13 artifacts, and 57 catalog records.
- Dependency ranges now have tested upper bounds.
- IFC semantic GlobalIds are derived from stable keys.
- Desktop CAD executables can be supplied through environment variables or PATH.
- Validation is read-only with respect to the asset manifest.
- CadQuery and OpenSCAD generation now receive authoritative ProjectSpec
  parameters explicitly instead of relying on duplicated source defaults.
- Preflight export counts are minimums so legitimate new assets do not fail.
- ProjectSpec semantic validation now rejects unbuildable placed classes,
  unsupported box axes, ports on non-distribution elements, and ports on the
  spatial occurrence before generation.
- Manifest and export-index validation now require exact ProjectSpec catalog
  projection rather than only a minimum required subset.

### Fixed

- IFC box profiles are translated so ProjectSpec `origin_mm` denotes the lower
  minimum corner, matching reports, drawings, FreeCAD placement, and observed
  cross-format bounds instead of centering the box around its placement.
- Generated DXF rectangle entities now carry a real closed-polyline flag, and
  observed DXF certification rejects open outlines.
- CHWR topology now routes through both isolation and balancing valves instead
  of leaving the balancing valve outside the machine-readable network.
- Catalog parameters now cover every CadQuery builder input.
- Cable-tray range generation rejects zero, negative, and non-finite pitches.
- Export validation parses STEP/STL/DXF/PDF/FCStd structure instead of accepting
  every non-empty file.
- Reconciliation rejects shadowed CadQuery modules, unscanned OpenSCAD inputs,
  producer-mapping mutation, invalid relation topology, and status laundering.
- CadQuery producer checks require canonical ProjectSpec forwarding, bounded
  numeric-input consumption, and per-parameter geometry sensitivity.
- DXF class serialization is stable across Python hash seeds.
- Desktop exports normalize OpenSCAD facet order, volatile QCAD PDF metadata,
  FreeCAD containers, assembly STEP headers, and review-IFC identities before
  atomically replacing tracked artifacts.
- FCStd XML parsing rejects entity expansion and external references through a
  hardened parser.
- ASCII STL validation bounds numeric tokens, uses exact signed-volume
  predicates, and rejects disconnected inward-wound shells until strict cavity
  containment is proven.
- The development test range starts at pytest 9.0.3, which fixes
  CVE-2025-71176 temporary-directory handling on UNIX.

[Unreleased]: https://github.com/Taz33m/coordproof-openbim-mep/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Taz33m/coordproof-openbim-mep/releases/tag/v0.2.0
