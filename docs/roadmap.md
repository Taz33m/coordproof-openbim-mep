# Roadmap

## Current release: trustworthy reference package

- Portable source validation, IFC inspection, and format-aware artifact checks
- Stable IFC semantic identities
- Versioned ProjectSpec v1 separating reusable asset types, placed occurrences,
  generated artifacts, and system connectivity
- JSON Schema plus semantic validation for IDs, references, parameters, export
  paths, and port-to-system bindings
- Community health, CI, dependency bounds, and provenance
- Guarded OpenCAD feature-tree pilot for one canonical asset

## Next: cross-format parameter reconciliation

ProjectSpec now establishes the authoritative type/occurrence boundary, but
dimensions still cross several geometry implementations and evidence formats.
Some differences are legitimate occurrence-level coordination overrides; others
are legacy duplication that should be removed. The next milestone is to make
every difference explicit and machine-checkable:

- publish a generated type-to-occurrence-to-export parameter matrix;
- classify each repeated dimension as equal, derived, or an intentional
  occurrence override;
- reconcile CadQuery defaults, OpenSCAD parameters, FreeCAD macro geometry,
  drawing annotations, IFC quantities, and manifest values;
- add parity tolerances and focused diagnostics for every supported format;
- eliminate remaining hardcoded project values from generators once their
  ProjectSpec projection is covered by tests.

This milestone is complete when a contributor can change a declared parameter,
regenerate the package, and receive either matching evidence everywhere or a
clear validation error identifying the intended override contract.

## Later milestones

- Clean staging-directory builds with atomic publication
- A supported `coordproof` CLI and installable `src/coordproof` package
- Move the mechanical room into an example-project directory and support
  additional ProjectSpec files without library changes
- Multi-platform external-tool adapters and containerized portable builds
- AP242/IFC geometry and semantic round-trip inspection
- Project-level clash/clearance rules with explainable results
- Versioned releases, SBOMs, signatures, and downloadable evidence bundles
- Browser-based review once the OpenCAD backend and topology contracts mature

## OpenCAD promotion criteria

OpenCAD stays optional until upstream offers a tested real-OCCT headless runtime,
reliable feature-tree reconstruction, a clarified license, stable supported
platforms, and passing upstream tests. CoordProof additionally requires geometry
parity, deterministic rebuilds, and no use of transient topology IDs for IFC
identity or ports.
