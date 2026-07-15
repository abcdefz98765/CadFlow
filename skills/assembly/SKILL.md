# Assembly Skill

## Role

Owned by the future Assembly Agent.

Canonical checkpoint:

- multiple accepted Part Jobs -> assembly placement, constraints, and assembly-level validation.

Current status:

- Planning already produces `assembly_plan.json` as decomposition and interface context.
- Full assembly generation, constraint solving, and assembly STEP export are not yet usable product capabilities.

## Purpose

Define how accepted parts relate after they exist: placement, contacts, mating intent, clearances, degrees of freedom, fastener alignment, serviceability, and assembly-level checks.

This skill does not own the initial decomposition of a product into candidate parts. That belongs to Planning / Assembly Plan.

## Inputs

Future inputs include:

- accepted Part Job results;
- active Assembly Plan and interfaces;
- reference-component envelopes;
- placement and constraint intent;
- assembly review targets.

## Outputs

Future structured outputs may include:

- backend-neutral assembly placement contract;
- constraint contract;
- clearance and degree-of-freedom observations;
- assembly validation report;
- assembly products only when a deterministic backend supports them.

## Allowed context

Shared:

- Assembly Plan interface vocabulary;
- accepted-result and lineage rules;
- shared units, check-level, and output policy.

Private knowledge:

- placement and mating rules;
- constraint patterns;
- clearance and interference guidance;
- degree-of-freedom reasoning;
- assembly serviceability and access rules.

Runtime context:

- accepted Part Job products and reports;
- active assembly interfaces;
- assembly validator observations.

## Behavior

- Operate only on accepted or explicitly selected part results.
- Preserve the difference between reference components and generated products.
- Make constrained and free degrees of freedom explicit.
- Record assumptions and unsupported checks.
- Stop safely when part interfaces or accepted results are insufficient.

## Boundaries

Must not:

- redefine product decomposition owned by Planning;
- generate missing individual parts as a hidden side effect;
- move single-part geometry checks into assembly validation;
- claim fit, motion, strength, or tolerance validation unless corresponding deterministic checks ran;
- imply current product support before implementation and acceptance exist.

## References

- `../../docs/architecture/cadflow-canonical-product-architecture.md`
- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/workflow_contract.md`
- `knowledge/assembly_rules.md`
- `knowledge/constraints.md`
- `knowledge/clearances.md`