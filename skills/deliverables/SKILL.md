# Deliverables Skill

## Responsibility

Build a versioned Deliverable Package from exact accepted Part and Assembly
results.

## Actions

- resolve accepted inputs and requested output policy;
- generate or collect native/source models, STEP/STL, assembly, BOM, drawings,
  and reports where supported;
- validate completeness, provenance, naming, and stale-state rules;
- explain missing or blocked outputs without fabricating success.

## Outputs

A package manifest, derived products, generation evidence, limitations, and
readiness status. Every item resolves to an accepted source result and records
the generating Run.

## Boundaries

The skill does not package unaccepted candidates, infer the latest result from a
filename, hide stale inputs, or claim drawing/GD&T/release completeness without
the corresponding checks.

## Current gap

This is a target skill contract. General industrial drawings and complete
Deliverable Package generation are not yet product capabilities.

## References

- `../../docs/architecture/cadflow-canonical-product-architecture.md`
- `../../docs/workflow_contract.md`
