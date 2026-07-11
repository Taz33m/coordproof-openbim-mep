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
- Versioned parameter-reconciliation contract with 75/75 canonical engineering
  parameters, 78/78 observed top-level producer numeric inputs accounted for,
  three explicit OpenSCAD `$fn` technical exclusions, and 17 declared
  type-to-occurrence relationships
- Bounded CadQuery input consumption plus differential geometry sensitivity for
  all 53 current numeric CadQuery inputs

## Next: complete cross-format parameter reconciliation

ProjectSpec now establishes the authoritative type/occurrence boundary, but
dimensions still cross several geometry implementations and evidence formats.
Some differences are legitimate occurrence-level coordination overrides; others
are legacy duplication that should be removed. The next milestone is to make
every remaining difference explicit and machine-checkable. The portable first
slice is complete: it publishes deterministic CSV/Markdown evidence, passes
ProjectSpec parameters into CadQuery and OpenSCAD generators, rejects unmapped
producer inputs or unexplained technical exclusions, and requires justified
occurrence overrides. Remaining work:

- publish a generated type-to-occurrence-to-export parameter matrix;
- classify each repeated dimension as equal, derived, or an intentional
  occurrence override;
- add FreeCAD primitive/decomposition adapters and reconcile its legacy model;
- derive engineering drawing annotations from declared type or occurrence values;
- expand the relation matrix until every type-to-occurrence dimension is
  classified;
- reconcile committed STEP/STL/DXF/FCStd observed geometry with format-specific
  tolerances;
- add parity tolerances and focused diagnostics for every supported format;
- eliminate remaining hardcoded project values from FreeCAD and drawing
  generators once their
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
