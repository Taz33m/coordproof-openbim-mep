# Asset Taxonomy

## Categories

| Category | Meaning | Examples |
| --- | --- | --- |
| `architectural_shell` | Room boundary and access elements | slab, walls, door, room shell |
| `mechanical_equipment` | Major named equipment, sections, and support frames | AHU, filter, coil, fan, pumps, skid, equipment base |
| `mechanical_support` | Reusable supports and mounting hardware | pipe bracket, duct hanger, pipe clamp |
| `flow_segment` | Generic pipe or routed flow assets | supply pipe, return pipe |
| `ductwork` | Air distribution assets | rectangular duct, duct connector |
| `electrical_routing` | Cable/control routing assets | cable tray |
| `penetration` | Wall/floor service openings | wall sleeve |
| `clearance_zone` | Service and maintenance volume | AHU clearance zone |
| `drawing` | Technical documentation sheets | floor plan, support details |
| `bim_export` | IFC-level deliverables | mechanical room IFC |

## Naming Convention

FreeCAD object names should follow:

```text
Category_System_Instance
```

Manifest asset IDs should stay lowercase with underscores:

```text
support_pipe_bracket_type_a
```

The object name describes the CAD-visible object. The asset ID gives scripts, manifests, and validation a stable machine-readable key.
