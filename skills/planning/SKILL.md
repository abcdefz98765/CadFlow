# Design Planning Skill

Purpose: turn the requirement package into an engineering-oriented design plan
and workflow route before any CAD geometry is generated.

Planning is the bridge between "what the user wants" and "what the modeling and
assembly steps should do." It owns analysis and sequencing, not requirement
clarification and not backend-specific CAD operations.

## Inputs

- `requirement.json`
- candidate manufactured parts and reference components from Requirement
- missing-information notes and assumptions
- requested `check_level`

## Outputs

- `plan.md`
- workflow route: single-part generation, multi-part generation, assembly loop,
  or confirmation-needed
- design strategy and functional datums
- part modeling order and template candidates
- interface map between parts and reference components
- risk list and confirmation gates
- structural, motion, degree-of-freedom, fit, clearance, and serviceability
  reasonableness notes
- review targets for each downstream step

## Analysis Responsibilities

- Decide whether the request should continue as one part or an assembly.
- Choose the functional decomposition that downstream steps should follow.
- Define datums, mating intent, motion/clearance expectations, and service
  access assumptions at a backend-neutral level.
- Identify obvious structural risks, load paths, weak regions, required support
  strategy, and missing load assumptions.
- Identify intended constrained and free degrees of freedom for moving or
  assembled products.
- Identify which part templates are likely needed without parameterizing them
  in detail.
- Decide the order of generation so reference envelopes, interfaces, and carrier
  parts are available before dependent parts.
- Route missing or risky decisions back to Requirement when the plan cannot be
  stable without the user.

## Boundaries

- Requirement owns user clarification and product intent capture.
- CAD IR owns encoding resolved part-level decisions into explicit generation
  fields; it must not make design tradeoffs or invent geometry from open-ended
  analysis notes.
- Part Modeling owns template parameterization, geometry generation, and
  single-part generation checks.
- Assembly owns placement, contacts, constraints, clearances, and assembly
  validation.
- Review owns report organization and check-level presentation.

Planning must consume requirement assumptions and missing-information notes
rather than silently ignoring them.

Simulation is future validation work. Planning may define required checks,
loads, motion ranges, or unresolved engineering questions, but it does not
perform final strength simulation, motion simulation, tolerance stack-up, or
production release verification.

See also:

- `../../docs/workflow_contract.md`
