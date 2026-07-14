# Roadmap

## Current release: installable evidence builder and trustworthy reference package

- Installable `coordproof validate`, `summary`, `build`, and `clash` commands
- Deterministic six-file IFC evidence bundles for supported, semantically valid
  ProjectSpec v1 contracts, with staged publication, formal IFC validation, and
  a SHA-256 manifest
- A substantially different electrical-room contract proving that generic
  validation and evidence generation do not require a second loader
- Portable source validation, IFC inspection, and format-aware artifact checks
- Stable IFC semantic identities
- Versioned ProjectSpec v1 separating reusable asset types, placed occurrences,
  generated artifacts, and system connectivity
- JSON Schema plus semantic validation for IDs, references, parameters, export
  paths, and port-to-system bindings
- Community health, CI, dependency bounds, and provenance
- Guarded OpenCAD feature-tree pilot for one canonical asset
- Versioned parameter-reconciliation contract with 75/75 canonical engineering
  parameters, 78/78 observed top-level producer numeric inputs accounted for,
  three explicit OpenSCAD `$fn` technical exclusions, and 17 declared
  type-to-occurrence relationships
- Bounded CadQuery input consumption plus differential geometry sensitivity for
  all 53 current numeric CadQuery inputs
- Direct observed-geometry evidence across IFC, STEP, STL, and selected DXF:
  69 PASS, 0 FAIL, and one explicit legacy FreeCAD assembly exclusion
- A bounded external two-IFC clash pilot with deterministic JSON, optional BCF
  3.0, collision/intersection/clearance modes, and explicit resource limits
- Corrected IFC box placement so ProjectSpec lower-corner origins agree with
  reports, drawings, FreeCAD, and directly observed IFC bounds
- Versioned installable release assets: wheel, source distribution, mechanical
  and electrical evidence bundles, and a SHA-256 checksum manifest

## Next: generalize the full pipeline and complete observed parity

The generic evidence profile now validates and builds supported ProjectSpec v1
files, while the multi-tool `core` and `full` profiles still know the canonical
mechanical-room adapters. The observed matrix closes the first direct-geometry
slice, but envelope parity is intentionally narrower than complete model parity.
Remaining work:

- replace fixed mechanical-room generator/output registries with project-scoped
  adapter discovery and clean output layouts;
- make report, drawing, CadQuery/OpenSCAD, and desktop-tool adapters selectable
  from generic ProjectSpec declarations rather than checkout globals;
- add FreeCAD primitive/decomposition adapters and reconcile its legacy model;
- inspect the native FCStd assembly and remove the explicit assembly STEP
  exclusion;
- derive all engineering drawing geometry and annotations from declared type or
  occurrence values, then extend DXF observation beyond the seven selected
  floor-plan entities;
- expand the relation matrix until every type-to-occurrence dimension is
  classified;
- add topology- and feature-aware checks where axis-aligned bounds cannot detect
  void, wall-thickness, connectivity, or decomposition regressions;
- eliminate remaining hardcoded project values from FreeCAD and drawing
  generators once their ProjectSpec projection is covered by tests;
- evolve the external clash pilot with alignment transforms, selector/ruleset
  configuration, intra-model and multi-model sets, snapshots, and workflow
  integration without weakening deterministic or resource-limit contracts;
- design a future ProjectSpec schema version with an extensible IFC-class
  vocabulary, producer kinds, routed geometry, and richer port/system metadata
  exposed by the electrical-room example.

This milestone is complete when a contributor can change a declared parameter,
regenerate the package, and receive either matching evidence everywhere or a
clear validation error identifying the intended override contract.

## Later milestones

- Multi-platform external-tool adapters and containerized portable builds
- AP242/IFC geometry and semantic round-trip inspection
- SBOMs and artifact signatures
- Browser-based review once the OpenCAD backend and topology contracts mature

## OpenCAD promotion criteria

OpenCAD stays optional until upstream offers a tested real-OCCT headless runtime,
reliable feature-tree reconstruction, a clarified license, stable supported
platforms, and passing upstream tests. CoordProof additionally requires geometry
parity, deterministic rebuilds, and no use of transient topology IDs for IFC
identity or ports.
