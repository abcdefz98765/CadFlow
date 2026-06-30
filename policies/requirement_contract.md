# Requirement Contract

Purpose: define the Requirement Agent's handoff artifact.

The Requirement Agent is the first workflow step that turns user intent into a
structured, reviewable requirement package. It may use natural-language parsing,
rules, clarification questions, structured overrides, or future LLM assistance,
but its output is always `requirement.json`.

The full end-to-end workflow responsibility map lives in
`docs/workflow_contract.md`; this policy is limited to the Requirement Agent
handoff contract.

Downstream workflow stages must consume structured fields from
`requirement.json`. They must not re-parse `source.input_text` to infer geometry
or features.

## Boundary

```text
user natural language
  -> Requirement Agent
  -> requirement.json
  -> Planning / CAD IR / Review
```

The natural-language parser is an implementation detail of the Requirement
Agent. It is not a downstream modeling contract.

## Source Of Truth

For CAD generation, the source of truth is:

1. `requirement.json` structured fields while still in the requirement/planning
   workflow.
2. `input_ir.json` / `CADIR` after requirement fields have been normalized into
   CAD IR.

`source.input_text` is trace data. It should help review and debugging, but it
must not override `part_type`, `dimensions`, `features`, `outputs`, or
`check_level` after the Requirement Agent has produced the structured fields.

## Required Shape

Minimum `requirement.json` fields:

- `part_type`
- `unit`
- `intent`
- `dimensions`
- `features`
- `outputs`
- `check_level`
- `field_policy`
- `missing_information`
- `follow_up_questions`
- `follow_up_requests`
- `cad_brief`
- `assumptions`
- `requirement_status`
- `source`

Missing or ambiguous user decisions must be explicit in `missing_information`.
User-facing clarification items must be mirrored in `follow_up_questions` for
compatibility and `follow_up_requests` for machine-readable clients.

## Agent Behavior

- Fill structured fields when user intent is clear.
- Ask or record missing information when a field changes topology, fit,
  manufacturing method, assembly behavior, or safety review.
- Record assumptions when L0 generation proceeds with defaults.
- Keep parser diagnostics visible instead of silently changing structured
  fields.
- Emit `cad_brief` as planning metadata derived from requirement/CAD IR fields.

## Downstream Rules

- Planning may read `intent`, `dimensions`, `features`, `missing_information`,
  `follow_up_requests`, `assumptions`, `requirement_status`, and `cad_brief`.
- CAD IR conversion may read `part_type`, `unit`, `dimensions`, `features`,
  `outputs`, `check_level`, `part_name`, and `source` for traceability.
- Part modeling and validation must use CAD IR, not original prompt text.
- Benchmarks remain IR-first; parser/requirement cases belong in separate
  parser tests or prompt pipeline debug examples.
