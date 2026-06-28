# Agent Design Philosophy

Agents should treat CAD generation as a workflow, not as visual trial and error.

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

## Responsibilities

The user describes intent:

- purpose
- critical dimensions
- mounting faces and hole locations
- manufacturing preference
- priority and constraints

The agent produces traceable artifacts:

- `input.md`
- `requirement.json`
- `plan.md`
- `model.py`
- `review.md`
- `exports/`
- `logs/`

## Design Layers

1. Intent: what the part is for.
2. Requirement: structured dimensions, features, assumptions, product intent, candidate parts/reference components, and check level.
3. Planning: workflow route, datums, interfaces, risks, template candidates, and confirmation gates.
4. Part modeling: template-backed backend-native parametric CAD for each generated part.
5. Assembly: backend-neutral placement, constraints, contacts, clearances, and serviceability intent.
6. Review: L0/L1/L2+ checks according to maturity.
7. Outputs: STEP/STL and future formats under the output contract.

## Backend Boundary

Agents must not assume CadQuery is the product boundary. CadQuery is the current backend; workflow code should rely on the backend abstraction so future build123d, FreeCAD API, JSCAD, or replicad backends can be introduced.

## Current Check Policy

- `L0 Playground`: supported.
- `L1 Maker`: report scaffold only.
- `L2 Engineering`, `L3 Industrial`, `L4 Safety Critical`: reserved.

When checks fail, agents should fix requirements or parameters before adding cosmetic geometry. Functional geometry, traceability, and review quality matter more than pretty shapes.
