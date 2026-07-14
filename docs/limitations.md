# Limitations

This project is a technical CAD/BIM asset pipeline, not a stamped engineering design.

The mechanical room layout is illustrative and is not intended for construction.

The IFC model is generated as an IFC-first semantic model with IfcOpenShell. It uses explicit MEP classes, systems, ports, property sets, and material associations for the implemented scope.

The FreeCAD files are still useful CAD review artifacts, but they are no longer treated as the only source of OpenBIM truth. The IFC semantic layer is the authoritative validation target.

The drawings are generated technical coordination drawings and not a full construction document set.

The validation scripts check file structure, metadata completeness, IFC
readability, MEP class coverage, distribution systems, port connectivity,
property sets, asset coverage, and selected cross-format geometry envelopes.
They do not perform full engineering compliance validation.

The installable `coordproof validate`, `summary`, and default `build` commands
accept ProjectSpec v1 files within the versioned class, geometry, and port-host
vocabulary. The generic build intentionally
produces a compact six-file IFC evidence bundle; it does not synthesize a
project-specific CadQuery, OpenSCAD, FreeCAD, QCAD, BOM, or coordination-report
pipeline. The `core` and `full` profiles still target the canonical mechanical
room. The independent electrical-room example proves generic contract and
formally valid IFC generation with native electrical distribution classes, but
its README records the remaining closed class vocabulary, producer, port
metadata, and routed-geometry constraints.

Evidence-bundle publication is currently certified only on POSIX filesystems
that provide directory-relative operations and no-follow directory handles.
The builder fails closed on platforms without those primitives rather than
falling back to pathname-based replacement that could be redirected through a
concurrently swapped parent. Windows evidence publication remains unsupported
until an equivalent junction-safe directory-handle backend is implemented.

QCAD is an optional desktop exporter, not part of the portable core. Its license
and command-line availability depend on the installed edition; contributors
must review those terms before redistributing it or automating hosted exports.
The portable core writes ReportLab previews under `build/portable/`; only QCAD
writes the canonical PDFs under `qcad/pdf_exports/`.

OpenSCAD 2021.01 is an Intel macOS application distributed through Homebrew and may require Rosetta on Apple Silicon systems.

The optional OpenCAD integration is experimental and pinned. CoordProof does not
persist OpenCAD topology IDs, execute agent-generated code, or treat OpenCAD as
the authority for IFC identity, systems, ports, or validation.

Reusable asset-type parameters and placed occurrence dimensions are separated in
the versioned ProjectSpec. The reconciliation contract provides complete numeric
input coverage for CadQuery and OpenSCAD and validates selected equal, derived,
and intentional occurrence relationships. CadQuery sensitivity tests establish
that each current numeric input changes generated geometry.

Cross-format geometry is now inspected directly, but not completely. The
observed-geometry matrix verifies full axis-aligned minimum and maximum bounds
for all 40 canonical IFC occurrences, mapped STEP/STL assets, OpenSCAD STL
envelopes, and seven selected floor-plan DXF entities. Its current result is 69
PASS, 0 FAIL, and one explicit exclusion. Envelope equality does not prove
topology, voids, wall thickness, feature identity, manifold quality, assembly
decomposition, fabrication intent, or the correctness of drawing annotations.
The excluded `mechanical_room_assembly.step`, native FCStd structure, and
unselected drawing geometry/annotations remain visible work on the
[roadmap](roadmap.md).

The IFC box-placement correction makes `origin_mm` the lower minimum corner in
the IFC representation, matching ProjectSpec, reports, drawings, and FreeCAD.
ProjectSpec v1 boxes are world-aligned and must declare `extrusion_axis [0, 0, 1]`.
The observed matrix guards this placement contract as well as overall size.
Cylinder origins continue to represent the start of the axis centerline.

`coordproof clash` is a bounded interoperability pilot, not a full clash
coordination platform. It compares exactly two distinct, uncompressed IFC STEP
files, performs only A-versus-B checks, assumes a shared coordinate frame,
rejects ambiguous shared selected GlobalIds, and filters by IFC class rather
than a selector-query language. It does not support intra-model checks,
federation alignment transforms, multi-model rulesets, snapshots, or an
interactive assignment/approval workflow. Resource counts are bounded, but the
triangle gate is checked only after each selected element has been tessellated,
so these limits are not a peak-memory or hostile-input sandbox. The pilot does
not yet impose a wall-clock deadline. JSON output needs no optional package; BCF
3.0 output requires the tested `bcf-client` 0.8.x dependency. When both are
requested, both are staged before either is published.
