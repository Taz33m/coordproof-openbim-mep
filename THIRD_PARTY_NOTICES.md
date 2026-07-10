# Third-party notices

CoordProof calls or imports the following projects. Their own licenses govern
their code; they are not bundled or relicensed by CoordProof unless a release
explicitly says otherwise.

| Project | Role | License/source |
| --- | --- | --- |
| IfcOpenShell | IFC4 generation and inspection | LGPL-3.0-or-later; <https://ifcopenshell.org/> |
| CadQuery | Parametric B-rep assets | Apache-2.0; <https://github.com/CadQuery/cadquery> |
| Open CASCADE / OCP | Geometry kernel bindings | LGPL-2.1 with exception; <https://dev.opencascade.org/> |
| ezdxf | DXF generation and parsing | MIT; <https://github.com/mozman/ezdxf> |
| ReportLab | PDF generation | BSD; <https://www.reportlab.com/> |
| Pillow | Review-image generation | HPND; <https://python-pillow.github.io/> |
| FreeCAD | Native CAD review model | LGPL-2.0-or-later; <https://www.freecad.org/> |
| OpenSCAD | Declarative solid assets | GPL-2.0-or-later; <https://openscad.org/> |
| QCAD | Optional DXF-to-PDF exporter | Edition-dependent; <https://www.qcad.org/> |
| OpenCAD | Optional feature-tree pilot | Pinned source repository; <https://github.com/caid-technologies/OpenCAD> |

The pinned OpenCAD revision currently has inconsistent package metadata: its
repository `LICENSE` is Apache-2.0 while `pyproject.toml` declares MIT. CoordProof
therefore keeps it optional, unbundled, and pinned until upstream clarifies.

Dependency lists are informational, not legal advice. Release maintainers should
recheck versions and license texts when producing redistributed binaries.
