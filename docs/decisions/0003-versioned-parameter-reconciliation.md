# ADR 0003: Use a Separate Versioned Parameter Reconciliation Contract

- Status: Accepted
- Date: 2026-07-10

## Context

ProjectSpec is the numeric authority, but supported geometry producers use
different parameter names and some placed occurrences intentionally differ from
their reusable types. Copying expected values into validators would create
another source of truth, while arbitrary expressions would make validation hard
to audit and unsafe to extend.

## Decision

CoordProof keeps relationships and producer selectors in
`spec/reconciliation.contract.json`, validated by
`spec/reconciliation.schema.json`. The contract contains no duplicate expected
geometry values. It points to ProjectSpec values, producer inputs, and declared
type-to-occurrence endpoints.

Producer adapters must account for every numeric canonical parameter and every
numeric input in their declared scope. Relations are classified as `equal`,
`derived`, or `override`. Derived relations use only a small operator vocabulary;
arbitrary expression evaluation is prohibited. Overrides require a nonempty
rationale.

CadQuery and OpenSCAD are the first enforced producer scope. FreeCAD and drawing
adapters will be added as their legacy composition and annotation contracts are
made explicit.

The CadQuery adapter accepts a deliberately bounded source shape: an
undecorated `build(parameters=None)` must begin with the trusted merge helper,
the merged mapping may only be read through literal known keys, and every
numeric fallback input must be consumed. Differential geometry tests perturb
each current numeric CadQuery input and require the generated shape signature to
change. The OpenSCAD adapter verifies literal top-level declarations while the
generator injects mapped ProjectSpec values with deterministic `-D` arguments.

This contract proves declared fallback alignment, supported input plumbing, and
the classified relations in its report. It does not prove exact BRep/mesh
dimensions or that committed exports geometrically match every declared value;
those require format-specific observed-geometry checks.

## Consequences

- Changing a scoped fallback or supported producer binding produces matching
  evidence or a producer-specific failure.
- OpenSCAD aliases remain explicit without leaking tool-specific names into the
  domain model.
- Intentional occurrence envelopes are distinguishable from unexplained drift.
- The reconciliation report is deterministic, reviewable, provenance-hashed,
  and gated in CI.
- The contract must evolve through versioned schemas and migration tests as new
  adapters and relationship types are added.
