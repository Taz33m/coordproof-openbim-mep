# QCAD Drawing Package

The DXF files in this directory are generated as QCAD-ready technical sheets. Open them in QCAD for manual layer review, annotation polish, and final publication export.

Generate the current drawing set:

```bash
.venv/bin/python tools/generate_drawings.py
.venv/bin/python tools/export_qcad_pdfs.py
```

Required layers:

- `A-WALL`
- `A-DOOR`
- `A-SLAB`
- `M-EQUIP`
- `M-PIPE`
- `M-DUCT`
- `M-SUPPORT`
- `E-CABLETRAY`
- `CLEARANCE`
- `DIMENSIONS`
- `ANNOTATIONS`
- `CENTERLINES`
- `TITLEBLOCK`
