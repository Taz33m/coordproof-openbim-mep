# Limitations

This project is a technical CAD/BIM asset pipeline, not a stamped engineering design.

The mechanical room layout is illustrative and is not intended for construction.

The IFC model is generated as an IFC-first semantic model with IfcOpenShell. It uses explicit MEP classes, systems, ports, property sets, and material associations for the implemented scope.

The FreeCAD files are still useful CAD review artifacts, but they are no longer treated as the only source of OpenBIM truth. The IFC semantic layer is the authoritative validation target.

The drawings are generated technical coordination drawings and not a full construction document set.

The validation scripts check file structure, metadata completeness, IFC readability, MEP class coverage, distribution systems, port connectivity, property sets, and asset coverage. They do not perform full engineering compliance validation.

QCAD PDF exports were generated through the installed QCAD command-line exporter. The installed cask exposes QCAD Professional trial messaging before each command-line export.

OpenSCAD 2021.01 is an Intel macOS application distributed through Homebrew and may require Rosetta on Apple Silicon systems.

`ghbalf/freecad-ai` is alpha software. Use it for guided FreeCAD modeling and review in Plan Mode, then commit only deterministic macro/source changes that can be regenerated and validated.
