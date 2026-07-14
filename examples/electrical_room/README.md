# Electrical room ProjectSpec example

This standalone contract example proves that the generic ProjectSpec v1 loader can describe a
domain substantially different from the mechanical-room reference without a parallel
loader or domain-specific schema.

It models:

- a 480Y/277 V utility-to-switchboard-to-transformer primary path;
- a 208Y/120 V transformer-to-panelboard-to-load secondary path;
- explicit grounding and bonding connections;
- a switchboard metering network;
- four reused feeder-route occurrences;
- two equipment working-clearance volumes; and
- declared IFC, single-line, and coordination-schedule deliverables.

## Validate and build it

From the repository root:

~~~sh
.venv/bin/python -m pip install .
.venv/bin/coordproof validate examples/electrical_room/electrical_room.project.json
.venv/bin/coordproof summary examples/electrical_room/electrical_room.project.json
.venv/bin/coordproof build examples/electrical_room/electrical_room.project.json \
  --output build/electrical-room-evidence
.venv/bin/pytest tests/test_electrical_room_example.py
~~~

The expected summary is 12 asset types, 16 occurrences, 3 artifacts, 4 systems,
12 connections, and 24 declared ports.

The default generic `evidence` profile produces a deterministic six-file bundle:

- `project.normalized.json`
- `project-summary.json`
- `project.ifc`
- `ifc-entity-summary.md`
- `openbim-semantic-inventory.csv`
- `build-manifest.json`

The manifest records the SHA-256 identity of the other five files. This proves
that the electrical contract reaches real IFC and semantic evidence generation,
not only schema validation. It does not claim that the canonical mechanical
room's CadQuery, OpenSCAD, FreeCAD, QCAD, or discipline reports have become
generic; `core` and `full` remain tied to that reference project.

## Connectivity

The normal-power paths are deliberately modeled as equipment-to-route-to-equipment
chains so the feeder occurrences are first-class coordination objects:

~~~text
Utility -> service feeder -> MSB-1 -> primary feeder -> T-1
T-1 -> secondary feeder -> LP-1 -> branch feeder -> LB-1
~~~

Every declared port participates in exactly one connection. Grounding fan-out uses
three explicit ports on the main ground bar, preserving ProjectSpec v1's point-to-point
connection invariant.

## ProjectSpec v1 compatibility boundary

This example also records the current generic-contract limits rather than disguising
them:

- The v1 IFC-class vocabulary now includes the native electrical distribution
  classes used here: IfcTransformer, IfcElectricDistributionBoard,
  IfcElectricAppliance, and IfcJunctionBox. The vocabulary remains deliberately
  closed; adding another IFC class requires schema, semantic, and builder tests.
- Asset producer groups are fixed to bim, ifc_detail, cadquery, and openscad. The
  electrical definitions therefore use the domain-neutral-enough bim group; categories
  carry their electrical discipline semantics.
- Occurrence geometry is limited to boxes and cylinders. Box dimensions are
  world-aligned lower-corner envelopes and therefore use `extrusion_axis [0, 0, 1]`;
  routed feeders are compact envelopes, not detailed conductors or bend geometry.
- Ports currently carry identity and system membership, but no direction, electrical
  phase, voltage, conductor, or distribution hierarchy.
- Each port can appear in only one connection. Multi-drop buses require multiple
  explicit ports.
- Export paths are safe, repository-relative declarations. The generic evidence
  build emits its standard six-file bundle rather than materializing the three
  declared discipline-specific deliverables as bespoke drawing/report files.

Those constraints do not require a second loader, but they are clear candidates for a
future ProjectSpec schema version if full electrical authoring becomes a goal.
