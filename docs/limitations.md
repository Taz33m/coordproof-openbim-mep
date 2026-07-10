# Limitations

This project is a technical CAD/BIM asset pipeline, not a stamped engineering design.

The mechanical room layout is illustrative and is not intended for construction.

The IFC model is generated as an IFC-first semantic model with IfcOpenShell. It uses explicit MEP classes, systems, ports, property sets, and material associations for the implemented scope.

The FreeCAD files are still useful CAD review artifacts, but they are no longer treated as the only source of OpenBIM truth. The IFC semantic layer is the authoritative validation target.

The drawings are generated technical coordination drawings and not a full construction document set.

The validation scripts check file structure, metadata completeness, IFC readability, MEP class coverage, distribution systems, port connectivity, property sets, and asset coverage. They do not perform full engineering compliance validation.

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
the versioned ProjectSpec. The reconciliation contract now provides complete
numeric input coverage for CadQuery and OpenSCAD and validates selected equal,
derived, and intentional occurrence relationships. Cross-format geometry is not
yet fully reconciled: legacy values remain in the FreeCAD macro and several
drawing details. Those formats are identified as uncovered scope in the report
and remain the next parameter-parity milestone on the [roadmap](roadmap.md).
