# Product Decomposition

Product decomposition is owned by the Planning Skill.

Requirement may identify scope hints, user-stated components, and missing topology decisions, but Planning decides the engineering decomposition used by the Assembly Plan and downstream Part Jobs.

## Outputs

- product route: single part, multi-part assembly, reference-only, unknown, or unsupported;
- generated candidate parts;
- reference-only components;
- interfaces and dependencies;
- selected or recommended candidate;
- generation order and preserved assembly context;
- risks and user decisions required before a stable plan exists.

## Guidance

- Do not turn a functional assembly into one monolithic part merely because one-part generation is easier.
- Generated candidates are parts CadFlow may attempt through Part Jobs.
- Reference components are purchased, existing, or context-only items represented for fit and interface reasoning.
- Preserve service access, wiring, motion, fastening, and replacement intent.
- Expose alternatives and trade-offs when more than one decomposition is plausible.
- Return to Requirement when the missing decision belongs to user intent rather than engineering planning.
- Do not treat current backend templates as the complete product design space.

## Handoff

The accepted decomposition is recorded in Planning and, for assembly scope, `assembly_plan.json`. Explicit candidate selection then creates one scoped Part Request.