# Workflow Cockpit Decision Layer and CAD IR Progression

This document captures two linked architecture corrections for CadFlow:

1. The Web Console should guide user decisions, not only explain workflow state.
2. Unsupported or unknown part families should not be treated as a template-library terminal stop. They should progress through an agent-driven CAD IR synthesis and validation workflow with explicit safe intermediate artifacts, repair choices, and capability boundaries.

This is a design document. It does not add CAD generation capability by itself.

## Background

CadFlow's product goal is not a deterministic template lookup system. The intended workflow is:

```text
RequirementAgent
  -> PlanningAgent
  -> CadIrAgent
  -> CAD IR validation
  -> PartModelingAgent / CAD Agent Loop
  -> Assembly / Review
  -> user review, edit, rerun, or rework
```

The deterministic parser, generic primitives, local/mock adapter, schema validators, templates, and stage gates are stability mechanisms. They are not supposed to become the primary architecture or block agent-driven CAD IR synthesis before the agent is even allowed to attempt a draft.

The Web Console has already moved toward a workflow cockpit:

```text
Workspace
  -> Work
  -> prompt
  -> Workflow graph
  -> Selected stage detail
  -> review / edit / override / action
```

The remaining gaps are:

- The UI explains stage state but does not always guide a user decision.
- Candidate part nodes are not yet first-class decision surfaces.
- Evidence is shown as artifact status instead of a cause-and-effect chain.
- Unknown part families still feel like a terminal `unsupported_part_type` block, instead of a repairable or explicitly bounded agent-CAD-IR progression.

## Key Decision

A missing deterministic template must not be the product-level reason a part cannot move forward.

Correct behavior:

```text
reviewed_part_handoff.json
  -> AgentAdapter.create_part_ir(...)
  -> cad_ir_draft.json
  -> CAD IR validation
  -> either:
       valid input_ir.json -> run_ir_pipeline(...)
     or:
       blocked_cad_ir_validation report with repair/development choices
```

Incorrect behavior:

```text
reviewed_part_handoff.json
  -> template lookup
  -> no upper_link template
  -> terminal unsupported block
```

The current safe block at `cad_ir_validation` is acceptable only if it means:

- the agent was allowed to produce a draft;
- the draft was preserved for review;
- validation explained why it could not execute;
- the UI offers decision choices and evidence;
- the next architecture step is clear.

It is not acceptable if it silently turns into:

- no agent attempt;
- no draft;
- no repair choice;
- no generic synthesis path;
- only a growing template library.

## Web Cockpit Decision Layer

The Web Console should evolve from an explanation surface into a decision cockpit.

### Problem

The selected stage detail now has human summaries, status banners, cards, and action groups. This is better than raw JSON, but it still often answers:

```text
What happened?
Why did it stop?
Which files exist?
```

It should also answer:

```text
Does the user need to decide anything?
What are the valid choices?
Which choice is recommended?
What happens next for each choice?
```

### New View-Model Concept: `decision_panel`

Every selected stage may expose a `decision_panel`:

```json
{
  "decision_panel": {
    "decision_required": true,
    "title": "Review blocked CAD IR draft",
    "summary": "This is an expected capability block. CadFlow stopped before exporting an invalid model.",
    "recommended_choice": "Save a Stage Review and continue future development on generic link-like CAD IR support.",
    "choices": [
      {
        "label": "Inspect CAD IR draft",
        "kind": "inspect",
        "action_key": "view_cad_ir_draft",
        "result": "Open the draft for review or override."
      },
      {
        "label": "Accept this block for now",
        "kind": "review",
        "action_key": "save_stage_review",
        "result": "Record that the current block is expected."
      },
      {
        "label": "Change selected part",
        "kind": "return",
        "target_stage": "assembly_plan",
        "result": "Edit the assembly plan or select a different candidate."
      }
    ]
  }
}
```

The decision panel is not a replacement for status banners or detail cards. It sits between the status hero and action buttons and provides the user's decision context.

### Decision Panel Rules

- If a stage is blocked, say whether it is an expected capability boundary, a missing prerequisite, an invalid user override, or an unexpected failure.
- If no decision is needed, say so and point to the next stage.
- Every choice must be actionable or explain why it is not yet wired.
- The recommended choice should be explicit.
- Do not show raw diagnostic codes in the panel.
- Do not show long paragraphs. Use one summary line and compact choices.

### Example: Part Modeling Blocked

For the current robot arm smoke:

```text
Decision: Review blocked CAD IR draft

This is an expected capability block. CadFlow created a draft for upper_link,
but the CAD backend cannot execute this part family yet.

Recommended:
Save Stage Review and track generic link-like CAD IR support as the next CAD capability task.

Choices:
- Inspect CAD IR draft.
- Accept this block for now.
- Return to Assembly Plan if upper_link is not the desired test part.
```

## Task State

Each selected stage should also expose a compact `task_state` for action grouping:

```json
{
  "task_state": {
    "mode": "blocked_review",
    "title": "Review blocked CAD IR draft",
    "description": "The run stopped safely before model generation.",
    "primary_goal": "Decide whether to inspect the draft, accept the block, or revise the selected part."
  }
}
```

Action buttons should serve the task state. They should not appear as an undifferentiated button list.

## Candidate Part Detail

Candidate parts should be first-class selection and review surfaces, not just chips that jump directly to `part_request`.

### Problem

When the graph shows part candidates such as `base`, `lower_link`, `upper_link`, and `gripper_mount`, clicking a candidate should explain that candidate. It should not silently jump to the part request stage.

### Candidate Detail View Model

```json
{
  "type": "part_candidate_detail",
  "part_id": "upper_link",
  "role": "upper arm link candidate",
  "status": "selected",
  "generation_strategy": "future_part_pipeline",
  "supported_candidate": true,
  "selected": true,
  "human_summary": "upper_link is the current candidate selected for the reviewed single-part pipeline.",
  "why_it_matters": "This lets CadFlow test one printable part before full assembly CAD is supported.",
  "current_pipeline_state": "CAD IR draft created; validation blocked.",
  "actions": {
    "primary": ["Open selected part pipeline"],
    "secondary": ["Edit Assembly Plan", "Save Stage Review"],
    "disabled": []
  },
  "evidence": []
}
```

### Candidate Status Semantics

- `candidate`: identified as a generated part candidate but not selected.
- `selected`: chosen for the reviewed single-part pipeline.
- `reference_only`: recorded for fit/context; not generated by CadFlow.
- `blocked`: blocked before it can enter the part pipeline.
- `generated`: has a child run with CAD outputs.
- `failed`: child run failed unexpectedly.

### Candidate Actions

Current MVP may not implement changing the selected candidate yet. If not wired, the UI must say:

```text
Select this part — disabled: candidate selection is not wired yet. Edit assembly_plan.json as an override to change the selected part.
```

Do not pretend that clicking a candidate selected it if it only opens a stage.

## Evidence Chain

Artifact status should become an evidence chain. The goal is to support the user's understanding of why the UI reached its conclusion.

### Problem

A flat artifact list says which files exist, but it does not explain the cause-and-effect workflow.

### Evidence Chain Model

```json
{
  "evidence_chain": [
    {
      "label": "Reviewed handoff",
      "artifact": "reviewed_part_handoff.json",
      "status": "present",
      "meaning": "upper_link was approved for single-part planning."
    },
    {
      "label": "Execution request",
      "artifact": "part_execution_request.json",
      "status": "present",
      "meaning": "CadFlow attempted one reviewed part create."
    },
    {
      "label": "CAD IR draft",
      "artifact": "cad_ir_draft.json",
      "status": "present",
      "meaning": "CadIrAgent produced a draft."
    },
    {
      "label": "Validated input IR",
      "artifact": "input_ir.json",
      "status": "absent",
      "meaning": "Not created because CAD IR validation blocked the draft."
    },
    {
      "label": "CAD outputs",
      "artifact": "model.step / model.stl",
      "status": "absent",
      "meaning": "Not exported because no validated input_ir.json exists."
    }
  ]
}
```

### Evidence Chain Rules

- Order by workflow causality, not by filename.
- Explain why absent files are absent.
- Link each evidence row to a readable artifact if allowlisted.
- Keep raw artifacts available only through controlled viewers.
- Do not expose absolute paths or arbitrary file browsing.

## CAD IR Progression for Unknown Part Families

### Problem

The current robot arm smoke correctly blocks at CAD IR validation for `upper_link`. This is safe. However, if every unsupported part family becomes a terminal `unsupported_part_type`, CadFlow will drift back into a template-library product.

The architecture should allow unknown or unsupported part families to progress through staged synthesis and repair attempts, while still preventing invalid CAD exports.

### Required Progression States

A reviewed part should be able to reach one of these states:

1. `cad_ir_draft_created`
   - Agent produced a draft.
   - Draft is saved for review.
   - No execution yet.

2. `cad_ir_needs_normalization`
   - Draft part type is not directly executable.
   - CadFlow may map it to a generic geometry family.
   - Example: `upper_link` -> `link_like_part` / `elongated_plate_with_end_holes`.

3. `cad_ir_repairable`
   - Draft is close but missing fields or has schema issues.
   - Repair can be attempted by CadIrAgent or deterministic normalizer.

4. `cad_ir_user_decision_required`
   - User must choose between candidates, fill dimensions, or accept assumptions.

5. `cad_ir_validation_blocked`
   - No safe executable IR is available.
   - The draft and validation report remain reviewable.

6. `cad_ir_validated`
   - A safe `input_ir.json` exists.
   - `run_ir_pipeline(...)` may execute.

### Generic Family Normalization

Unknown part names should be treated as part intent first, not as final backend part type.

Example:

```text
part_id: upper_link
role: upper arm link
intent family: link-like part
geometry family: elongated plate with end holes
backend family: link_like_part
source_part_id: upper_link
```

The goal is not to create a robot-arm-specific template. The goal is to let CadIrAgent or a normalizer classify the part into a reusable generic family.

Initial generic families may include:

- `plate_like_part`
- `link_like_part`
- `bracket_like_part`
- `spacer_like_part`
- `simple_housing_like_part`

Each generic family is still a capability boundary. It must have validated CAD IR schema and backend support before it can create STEP/STL.

### Template and Primitive Policy

Templates and primitives are allowed, but only as stability mechanisms:

- local/mock fallback;
- tests and offline CI;
- common feature emitters;
- repair aids;
- generic geometry families.

They must not become the main product gate:

```text
No template -> no agent attempt -> terminal block
```

Instead:

```text
No direct backend family -> agent draft -> normalization/repair/user decision -> validation -> execute or safe block
```

### CAD IR Attempt Record

For every reviewed-part create attempt, write a compact attempt artifact such as:

```json
{
  "artifact_type": "cad_ir_attempt",
  "version": "0.1",
  "source_part_id": "upper_link",
  "agent_operation": "create_part_ir",
  "draft_artifact": "cad_ir_draft.json",
  "normalization": {
    "attempted": true,
    "source_part_type": "upper_link",
    "candidate_family": "link_like_part",
    "status": "not_supported_yet"
  },
  "validation": {
    "status": "blocked",
    "category": "unsupported_backend_family"
  },
  "decision_options": [
    "inspect_draft",
    "edit_override",
    "return_to_assembly_plan",
    "implement_generic_family"
  ]
}
```

This attempt record should feed the Web Console `decision_panel` and `evidence_chain`.

## Repair and Normalization Loop

A future implementation should support a bounded repair/normalization loop:

```text
cad_ir_draft.json
  -> schema validation
  -> semantic validation
  -> generic family normalization
  -> missing-field question or assumption
  -> repaired cad_ir_draft.v2.json
  -> validation
  -> input_ir.json or blocked report
```

Rules:

- The loop is bounded.
- Every attempt is recorded.
- No arbitrary provider code is executed.
- No STEP/STL is exported without validated `input_ir.json`.
- User override can replace a draft, but still requires validation.
- If blocked, the UI shows decision choices and evidence.

## User Decision Options for Unsupported CAD IR

For a block such as `upper_link` unsupported, the cockpit should offer:

1. **Inspect draft**
   - Open `cad_ir_draft.json`.

2. **Edit draft override**
   - User edits allowlisted CAD IR draft.
   - Validation required before activation.

3. **Return to Assembly Plan**
   - Pick or define a different candidate.
   - Current candidate selection may require editing `assembly_plan.json` until direct candidate selection is wired.

4. **Save Stage Review**
   - Record that this is an expected capability boundary.

5. **Create Development Task**
   - Not necessarily a real issue yet; can be represented as recommended next action: implement generic family support.

6. **Run normalization / repair**
   - Future action once supported.

## Acceptance Criteria for Codex Implementation

A future implementation pass should be considered correct when:

### Web Cockpit

- Selected stage detail includes `decision_panel` and `task_state`.
- Part Modeling blocked state clearly says it is an expected capability block, not a corrupted run.
- Primary choices are inspect draft, save review, or return to assembly plan.
- Candidate part clicks open candidate detail, not an unexplained jump to part request.
- Evidence chain explains why `cad_ir_draft.json` exists but `input_ir.json`, STEP, and STL do not.
- Raw diagnostics remain available only in controlled debug/advanced contexts.

### CAD IR Progression

- `AgentAdapter.create_part_ir(...)` is called before unsupported-family blocking.
- `cad_ir_draft.json` is preserved.
- An attempt/validation artifact records draft, normalization, validation status, and user decision options.
- Unknown part names are treated as part intent and may be normalized to generic families.
- `upper_link` is not hardcoded as a robot-arm-specific template.
- No fallback to `mounting_plate` occurs.
- No `input_ir.json`, STEP, or STL is created unless validation passes.

### Tests

Add or update tests for:

- `decision_panel` exists for blocked CAD IR validation.
- `task_state.mode == "blocked_review"` for blocked reviewed-part create.
- Evidence chain contains reviewed handoff, execution request, CAD IR draft, missing input IR, and missing STEP/STL with reasons.
- Candidate part click/select view model returns part candidate detail.
- Unknown part draft records source part id and unsupported family reason.
- Normalization attempts are recorded even when the target generic family is not yet supported.
- No raw JSON braces, raw route names, or raw diagnostic code lists appear in primary cockpit text.
- Existing safety tests still pass: no arbitrary file editing, no provider code execution, no mounting_plate fallback.

## Non-Goals

Do not use this design pass to add:

- full robot arm assembly CAD;
- automatic all-part generation;
- motion simulation;
- strength validation;
- STEP assembly export;
- free chat UI;
- database, cloud, or accounts;
- provider-generated executable CAD/Python code;
- robot-arm-specific `upper_link` template.

## Recommended Next Implementation Step

Implement `Workflow Cockpit Decision Layer` first:

1. Add `decision_panel` and `task_state` to selected stage view models.
2. Add `evidence_chain` for reviewed-part create / CAD IR validation blocks.
3. Add part candidate detail when a candidate node is selected.
4. Centralize stage copy in a small copy registry so English/Chinese summaries do not drift.
5. Keep CAD behavior unchanged except for recording clearer CAD IR attempt metadata if trivial.

Then implement `CAD IR Progression for Generic Families`:

1. Treat unsupported part types as intent names, not final backend families.
2. Add normalization attempt metadata.
3. Add first generic family target such as `link_like_part` only when schema, validation, and backend support are ready.
4. Keep unsupported generic families safely blocked with reviewable draft and decision choices.
