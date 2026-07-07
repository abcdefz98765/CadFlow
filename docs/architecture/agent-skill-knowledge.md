# Agent, Skill, and Knowledge Architecture

CadFlow should integrate provider-backed LLMs through narrow stage agents, not a
single broad agent. Each workflow stage owns one agent role, one skill guide,
selected knowledge, and one or more structured JSON contracts.

```text
Workflow stage
  -> stage agent
  -> skill guide + selected knowledge
  -> JSON contract artifact
  -> local validation and gate
  -> next stage
```

The provider is replaceable. CadFlow owns context assembly, privacy filtering,
local validation, artifact persistence, gates, and deterministic execution.

For provider-backed whole-prompt create, the conservative fallback path is the
explicit normalized workflow:

```text
prompt
  -> provider extraction
  -> local requirement/planning compiler
  -> deterministic CAD IR conversion
  -> run_ir_pipeline
```

This is exposed as `run_provider_normalized_create_pipeline(...)` and maps to
`extract_then_compile` mode internally. It is useful for stable fallback,
offline tests, and provider extraction evaluation, but it is not the primary
architecture for Web reviewed-part CAD generation. Strict provider contract
mode remains available for compliance testing, where provider outputs must
directly satisfy CadFlow contracts and no silent fallback is allowed.

For reviewed-part create, the primary CAD entry is:

```text
reviewed_part_handoff.json
  -> CadIrAgent / AgentAdapter.create_part_ir
  -> CAD IR draft
  -> validate_input_ir_draft + validate_ir
  -> run_ir_pipeline
```

Templates, deterministic parsers, and primitive compilers stabilize and test the
system; they must not block agent CAD IR synthesis by default or silently
replace unsupported reviewed parts with unrelated templates.

## Concepts

### Agent

An agent is the runtime role for one workflow responsibility. It turns user
intent and artifact context into structured JSON. It does not execute CAD code,
write files directly, call shell commands, or decide what is persisted.

Initial stage agents:

- `RequirementAgent`: user prompt to `requirement.json`.
- `PlanningAgent`: `requirement.json` to `planning_artifact.json`.
- `CadIrAgent`: planning or reviewed-part handoff to `input_ir.json` through
  agent-generated CAD IR synthesis plus local validation. Deterministic
  primitive/template conversion is a local/mock fallback and guardrail, not the
  product's primary architecture.
- `PartModelingAgent`: validated CAD IR to generated artifacts through the CAD
  Agent Loop.
- `RepairAgent`: validation or execution failures to constrained repair
  suggestions.
- `ReviewAgent`: reports and traces to review explanations and gate summaries.
- `RevisionIntentAgent`: user revision text plus parent context to
  `change_intent.json`.
- `RevisionPlanAgent`: change intent plus parent context to
  `revision_plan.json`.

### Skill

A skill is the agent's behavior guide for one stage. It explains how to reason
for that stage, what to output, what to ask, and what not to do. For provider
requests, this is CadFlow-owned runtime context sent to the external model. It
is separate from Codex development-time skills.

Every provider-facing skill guide must include:

- Agent role and operation.
- Required JSON artifact contract.
- Required and optional fields.
- Missing-information behavior.
- Gate behavior.
- Safety and manufacturing boundaries.
- Explicit prohibitions against CAD code, Python code, shell commands, local
  absolute paths, provider transcripts, secrets, and free-form prose.

### Knowledge

Knowledge is selected reference material for a stage. It is not automatically
sent in full. CadFlow should send compact summaries that are useful for the
current operation.

Knowledge has two levels:

- Global knowledge: cross-stage rules and vocabularies.
- Stage knowledge: local references owned by a skill.

The first provider-ready implementation should start with skill guides and
artifact contracts. Knowledge injection can remain small and explicit until a
real retrieval layer exists.

## Repository Layout

Use the existing layout:

```text
knowledge/
  README.md
  parts/

skills/
  requirement/
    SKILL.md
    knowledge/

  planning/
    SKILL.md
    knowledge/

  part_modeling/
    SKILL.md
    knowledge/

  revision/
    SKILL.md
    knowledge/

  assembly/
    SKILL.md
    knowledge/

  review/
    SKILL.md
```

Top-level `knowledge/` is an index for references shared by more than one
skill. Stage-specific references stay under the owning skill.

## Provider Context Assembly

Provider requests should be assembled in this order:

```text
system:
  global minimal rules
  stage skill guide
  operation-specific JSON contract guide
  selected compact knowledge summary

user:
  sanitized user prompt or upstream artifact
  sanitized model context when needed

request metadata:
  operation name
  response format
  non-secret provider options
```

The context assembler must run before the injected provider client sees the
request. It must use allowlisted structured data and the existing privacy
sanitizer.

The first runtime implementation lives in
`src/ai_native_cad/agents/provider_context.py`. It uses a static
operation-to-skill mapping and compact operation-specific knowledge summaries;
it does not perform embedding search, vector retrieval, auto-indexing, external
search, or long-document stuffing.

Provider-visible context must not include:

- API keys, tokens, passwords, or secret values.
- Environment variable names used for API keys.
- Local absolute paths.
- `run_dir`, `output_dir`, `output_root`, `project_root`, `workspace_root`,
  `root`, or filesystem `path` fields.
- Raw transcripts, chat logs, runtime logs, or provider responses.

Structured CAD paths such as `dimensions.thickness` are allowed only where the
artifact contract explicitly requires field paths, such as revision operations.

## Stage Responsibilities

### Requirement

Input:

- User prompt.
- Optional non-secret overrides.
- Minimal workflow context.

Output:

- `requirement.json`.

Skill behavior:

- Preserve abstract user intent as structured uncertainty.
- Use `assumptions` for low-risk defaults.
- Use `missing_information` and `follow_up_questions` when the request is
  under-specified.
- Do not invent safety-critical, load-bearing, fit, material, tolerance, or
  certification details.

### Planning

Input:

- Validated `requirement.json`.
- Selected compact template or routing knowledge.

Output:

- `planning_artifact.json`.

Skill behavior:

- Select route, template candidates, datums, interfaces, and resolved design
  decisions.
- Convert requirement uncertainty into gate status and rework decisions.
- Keep geometry decisions structured in `resolved_decisions`.

### CAD IR

Input:

- Validated planning artifact or reviewed-part handoff.

Output:

- `input_ir.json`.

Skill behavior:

- Synthesize backend-neutral CAD IR for the selected part or reviewed handoff.
- Keep CAD IR normalized and backend-neutral.
- Do not allow provider text to bypass local CAD IR validation.
- Do not generate CadQuery/Python code, shell commands, raw provider payloads,
  transcripts, secrets, or local paths.
- Unsupported agent-generated IR should block at CAD IR validation with clear
  diagnostics rather than falling back to an unrelated supported template.

### Part Modeling

Input:

- Validated CAD IR.

Output:

- `model.py`, `model.step`, derived outputs, `report.json`, and trace
  artifacts.

Skill behavior:

- Execution stays in CadFlow Python code and CAD Agent Loop.
- Provider advice may help repair or explain, but provider output must not be
  executed as arbitrary code.

### Repair

Input:

- Validation or execution failure.
- Current CAD IR.

Output:

- Repair suggestion with analysis and constrained repaired IR or patch intent.

Skill behavior:

- Map failure context to small, structured changes.
- Preserve user intent and do not silently change unrelated geometry.

### Review

Input:

- Report and trace summaries.

Output:

- Review explanation or gate summary.

Skill behavior:

- Explain status, errors, warnings, and publishability.
- Keep summaries path-free and secret-free.

### Revision

Input:

- User revision prompt.
- Sanitized parent model context.

Output:

- `change_intent.json`.
- `revision_plan.json`.
- Later deterministic patch artifacts.

Skill behavior:

- Express user change as field-level operations where possible.
- Use CAD field paths such as `dimensions.thickness`.
- Block or ask when the requested change cannot be mapped safely.
- Never overwrite parent artifacts.

## Runtime Implementation

The first runtime implementation uses a provider context module rather than
expanding inline strings in `json_contract.py`:

```text
src/ai_native_cad/agents/provider_context.py
```

Current responsibilities:

- `system_prompt_for(operation)`: combine global rules and the stage skill
  guide.
- `contract_guide_for(operation)`: return the compact operation-specific
  contract guide.
- `knowledge_summary_for(operation, context)`: return a small static summary
  selected for the stage.
- `provider_messages_for(...)`: build provider-visible system/user messages
  containing selected context and the sanitized operation payload.

This first version is static and deterministic. It does not implement
general RAG, long knowledge stuffing, background indexing, or provider-side
memory. Selection should use an explicit operation-to-skill mapping, for
example `parse_requirement -> requirement`, `create_plan -> planning`,
`parse_revision_request -> revision`, and `create_revision_plan -> revision`.
Each mapped operation should receive only a small hand-written summary of the
relevant skill and knowledge. Embeddings, vector databases, model-driven
retrieval, and automatic repository indexing are later options, not part of the
first implementation.

## Testing Requirements

Each operation should have fake-client tests proving:

- The provider-visible system prompt includes the expected skill and contract
  guide.
- Sensitive fields are removed before request construction.
- Abstract user prompts can be represented as structured missing-information
  contracts.
- Local validation rejects malformed or bypassing provider outputs.

Real provider smoke tests remain manual or explicitly opt-in. They must not run
in CI and must not require secrets.
