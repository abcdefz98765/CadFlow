# Structured Geometry Skill

Compatibility directory: `cad_ir/`.

## Responsibility

Express a part candidate as a backend-neutral structured feature graph, validate
it, and revise it in response to observations.

## Actions

- choose primitives, sketches, features, datums, references, and parameters;
- request only relevant design and interface context;
- submit and compare structured candidates;
- react to schema, topology, geometry, and manufacturability observations;
- repair, change strategy, ask the user, or stop safely.

## Candidate output

The target output is a versioned feature graph with stable feature identifiers,
explicit references, units, parameters, interfaces, and evaluation intent.
Validated candidates may become reviewable results only after controlled build
and geometry checks.

## Boundaries

This skill has no execution or acceptance authority. It must not browse
arbitrary paths, bypass validators, substitute unrelated fallback geometry, or
claim assembly, strength, fit, or tolerance evidence that was not measured.

## Current gap

The current CAD IR is a closed schema centered on a small set of part families.
It remains a compatibility representation while the generalized feature graph
is built. New general capabilities should not default to another `part_type`.

## References

- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `../../docs/workflow_contract.md`
