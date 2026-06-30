# Requirement Skill

Purpose: turn a user's natural-language product idea into a structured,
traceable requirement package that later steps can safely plan from.

This skill owns requirement elicitation, product intent, early decomposition,
and missing-information questions. It must not generate CAD geometry and must
not choose backend-specific modeling operations.

The handoff artifact is `requirement.json`. Natural-language parsing is only an
input-understanding mechanism inside this skill; downstream workflow steps must
consume the structured requirement fields instead of re-parsing the original
prompt.

## Inputs

- Natural-language user request.
- Optional structured overrides.
- Requested `check_level`, defaulting to `L0`.
- Existing user decisions from earlier clarification turns.

## Outputs

- `requirement.json`
- product scope: single part, assembly, or unknown
- candidate manufactured parts and reference components
- functional interfaces and required user-facing behavior
- `missing_information`
- `follow_up_questions`
- `cad_brief`
- `assumptions`
- `field_policy`
- `requirement_status`

## Behavior

- Treat L0 as playground generation: missing non-critical information may use
  template defaults, but assumptions must be recorded.
- Ask the user when missing information changes topology, interfaces, assembly
  feasibility, manufacturing strategy, serviceability, wiring/sensor access, or
  safety review.
- For product requests, identify likely parts and reference components before
  planning. Example: a pet button likely needs a base, cap, switch or sensor
  envelope, wiring outlet, and a retention/fastening intent.
- Do not require surface finish, precise tolerances, or certification context in
  L0/L1 unless the user explicitly requests them.
- Attach tolerances and surface finish to functional faces or interfaces, not as
  vague global fields.
- Return unresolved decisions to the user when an assumption would change the
  product architecture.
- Emit `cad_brief` as requirement/planning metadata only. It may summarize
  intent, coordinate convention, parsed fields, conservative validation targets,
  assumptions, and clarification state, but CAD IR remains the source of truth
  for generated geometry.
- Treat `source.input_text` as trace/debug data after `requirement.json` has
  been authored. It must not override structured fields in later stages.

See also:

- `../../docs/workflow_contract.md`
- `../../policies/requirement_contract.md`
- `knowledge/requirement_template.md`
- `knowledge/fields_by_check_level.md`
- `knowledge/missing_info_policy.md`
- `knowledge/product_decomposition.md`
