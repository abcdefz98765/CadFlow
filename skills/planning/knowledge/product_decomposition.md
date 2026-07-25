# Product Decomposition

Product decomposition is owned by the Design Skill.

Intent may identify scope hints, user-stated components, and missing topology
decisions, but Design decides the engineering decomposition used by Part Jobs
and Assembly Jobs.

## Outputs

- product route: single part, multi-part assembly, reference-only, unknown, or unsupported;
- generated candidate parts;
- reference-only components;
- interfaces and dependencies;
- alternatives and selected or recommended concept;
- generation order and preserved assembly context;
- risks and user decisions required before a stable plan exists.

## Guidance

- Do not turn a functional assembly into one monolithic part merely because one-part generation is easier.
- Generated candidates are parts CadFlow may attempt through Part Jobs.
- Reference components are purchased, existing, or context-only items represented for fit and interface reasoning.
- Preserve service access, wiring, motion, fastening, and replacement intent.
- Expose alternatives and trade-offs when more than one decomposition is plausible.
- Ask a focused user question when the missing decision belongs to user intent
  rather than engineering strategy.
- Do not treat current backend templates as the complete product design space.

## Handoff

The active decomposition is recorded as design state. It may create or revise
multiple Part Job proposals and an Assembly Job proposal. Only explicit user
action accepts Part or Assembly results.
