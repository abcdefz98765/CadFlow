# Milestones

## M0: Existing CadQuery MVP

Done.

- CadQuery examples.
- STEP/STL export.
- Basic validation and reports.
- FreeCAD handoff and assembly helper scripts.

## M1: Workflow-first Refocus

Done in this refactor.

- Standard workflow: `input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs`.
- Standard output directory.
- `CADBackend` abstraction.
- CadQuery backend adapter.
- `mounting_plate` demo restored.
- `knowledge/` and `policies/` directories established.
- PRD, architecture, usage, roadmap, philosophy updated.

## M2: Parser Quality

Next.

- Extract dimensions and hole intent from more natural-language variants.
- Record assumptions and unknowns more precisely.
- Keep `requirement.json` stable.

## M3: L1 Maker Checks

Next.

- Minimum wall thickness.
- Overhang/support risk.
- STL printability.
- Maker-facing review warnings.

## M4: Backend Expansion

Future.

- build123d backend.
- FreeCAD API backend.
- Browser code-CAD backend evaluation.

## Deferred

- AI Engineering OS.
- Industrial DFM/DFA.
- Full GD&T.
- FEA.
- Safety-critical release workflow.
