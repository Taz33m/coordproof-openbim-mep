# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and uses semantic versioning for source and evidence-contract releases.

## [Unreleased]

### Added

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
- Dependency ranges now have tested upper bounds.
- IFC semantic GlobalIds are derived from stable keys.
- Desktop CAD executables can be supplied through environment variables or PATH.
- Validation is read-only with respect to the asset manifest.
- CadQuery and OpenSCAD generation now receive authoritative ProjectSpec
  parameters explicitly instead of relying on duplicated source defaults.
- Preflight export counts are minimums so legitimate new assets do not fail.

### Fixed

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
- The development test range starts at pytest 9.0.3, which fixes
  CVE-2025-71176 temporary-directory handling on UNIX.
