# Web Console UX Architecture

CadFlow Web Console is a local workflow cockpit for AI-assisted CAD work. It is not a browser CAD editor, a raw artifact browser, or a debug log viewer as the primary experience.

This document defines the user-facing information architecture for the Web Console so implementation work can stay aligned with the product goal:

```text
Workspace
  -> Work
  -> Requirement prompt
  -> Workflow graph
  -> Selected stage detail
  -> Review / edit / rerun / rework actions
```

The source of truth remains file-backed workflow artifacts and validated backend actions. The UI presents safe view models derived from those artifacts.

## UX Goals

The Web Console must answer, in the first screen of a selected Work:

1. What is this Work trying to create?
2. Where is the workflow now?
3. What did the agents decide?
4. What is blocked, if anything?
5. What can the user do next?
6. Which artifacts support this conclusion?
7. Where can an advanced user inspect or edit structured artifacts?

The UI should not make users read raw JSON, diagnostic code lists, provider identity blobs, or internal traces to understand the current state.

## Core Principles

1. **Artifacts are source of truth, but not the primary UI.**
   Raw artifacts are audit records. User-facing pages should show stage summaries, key decisions, actions, and selected artifacts.

2. **Workflow graph first.**
   The Workflow page should lead with a graph or graph-like stage flow. Users navigate by selecting stages, not by scrolling through every expanded card.

3. **Selected stage detail second.**
   A selected node opens a stage detail panel. The detail panel shows human summary, key decisions, actions, and user-facing artifacts.

4. **Human summary before raw data.**
   Gate decisions, blocked reasons, diagnostics, and adapter identity must be translated into short user-readable text before raw JSON is shown.

5. **Action availability must be explicit.**
   Every button should show whether it is enabled and why it is disabled. Disabled actions are useful if they teach the user the missing prerequisite.

6. **User edits are controlled overrides.**
   Users may edit allowlisted structured artifacts through validated override records. They must not overwrite original agent artifacts or edit generated code, reports, traces, binary exports, or arbitrary files.

7. **Debug stays outside the user Console.**
   Raw JSON, raw workflow graph nodes, diagnostics, traces, adapter metadata, and runtime logs are inspected from the local development environment, not downloaded or browsed from normal Console pages.

8. **NiceGUI is presentation.**
   It should render view models and call backend/action routes. It should not become the source of workflow state or directly mutate business artifacts.

## Page-Level Information Architecture

### Workspace Page

Purpose:

- Load or initialize a local workspace.
- Show workspace identity and safe display path.
- Let the user create or select a Work.

Primary content:

- Current workspace summary.
- Work list.
- Create Work form.
- Work structure map: inputs, planning, parts, deliverables, and immutable history.
- Provider/config status, if relevant.

Not primary:

- Run-level debug details.
- Raw artifacts.
- Workflow internals.

### Work Overview Page

Purpose:

- Summarize one Work.
- Show current state, latest run, part counts, products, and recommended next action.

Primary content:

- Work title and description.
- Overall status.
- Current run pointer.
- Readiness/risk summary, if available.
- Primary next action.
- Human-facing products.

Secondary content:

- Compact part matrix.
- Recent run history.
- Links to Workflow, Parts, Runs.

### Workflow Page

Purpose:

- Main cockpit for agent workflow review and intervention.

Primary layout:

```text
[Work header + current status + next recommended action]

[Workflow graph / stage flow]
  Stage spine:
    Requirement -> Clarification -> Planning -> Assembly Plan
                                             |
  Part branch:                               v
    Candidate Parts: base / lower_link / upper_link / ...
    Reference Lane: reference_servo / reference_gripper / ...
                                             |
                                             v
  Selected Part Pipeline:
    Part Request -> Part Review -> Reviewed Handoff
      -> CAD IR Draft -> Part Modeling -> Part Result Review
                                             |
                                             v
  Review tail:
    Workflow Review -> Rework

[Selected stage detail]
  Human Summary
  Why it matters
  Current Status
  Current Block
  Key Decisions (human-readable)
  Progress / Limitations / Safety
  User Actions
  Important Artifacts
  Advanced / Raw JSON
  Debug / Diagnostics
```

The Workflow page must not default to a long list of fully expanded stage cards. Stage cards can be implementation units, but the user experience should be graph-first and selected-node-detail.
For assembly workflows, the graph must make the part branch visible rather than presenting every stage as one linear sequence. Internal route names, gate actions, raw candidate lists, diagnostics, and artifact-state fields belong in collapsed Advanced or Debug sections.

### Parts Page

Purpose:

- Summarize part jobs within the Work.

Primary content:

- Part matrix.
- Generated / blocked / reference-only / needs-review states.
- Per-part latest artifact availability.
- Link from a part to the relevant workflow node or run.

Not primary:

- Full raw JSON for every stage.

### Work History Page

Purpose:

- Show immutable Work attempts.

Primary content:

- Immutable run history.
- Run status, active part, and delivery availability.
- Rework attempts belonging to the selected Work.

Work history must never show unclassified, project-level, or debug runs.

## Workflow Graph Model

The workflow graph is a user-facing navigation model, not necessarily the raw internal graph.

Each graph node should have:

```json
{
  "stage_id": "cad_ir_draft",
  "label": "CAD IR Draft",
  "status": "blocked",
  "short_summary": "Agent generated a CAD IR draft, but validation blocked it.",
  "primary_artifact": "cad_ir_draft.json",
  "primary_action": "Review CAD IR draft",
  "has_override": false,
  "has_debug": true
}
```

Expected statuses:

- `not_started`
- `ready`
- `running`
- `completed`
- `completed_with_assumptions`
- `needs_review`
- `user_modified`
- `stale`
- `blocked`
- `failed`
- `reference_only`

Status labels should be consistent across Work Overview, Workflow graph, Stage Detail, and Parts page.

## Stage Detail View Model

Every selected stage detail should follow the same shape:

```json
{
  "stage_id": "planning",
  "stage_name": "Planning",
  "status": "completed",
  "human_summary": "Planning completed and identified candidate generated parts plus reference components.",
  "current_block": null,
  "status_banner": {
    "status": "completed",
    "title": "Assembly plan completed with downstream limitation",
    "summary": "CadFlow decomposed the request into generated part candidates and reference components.",
    "consequence": "The workflow continues with one selected part.",
    "badges": []
  },
  "detail_cards": [
    {"title": "What happened", "items": []},
    {"title": "Artifact status", "items": []}
  ],
  "action_groups": {
    "primary": [],
    "secondary": [],
    "disabled": [],
    "advanced": []
  },
  "advanced": {},
  "debug": {}
}
```

### Human Summary

A short explanation of what happened in this stage. It should be written for the user, not the developer.

Bad:

```text
Gate decision: {"action": "proceed_with_assumptions", ...}
```

Good:

```text
Requirement completed with assumptions. CadFlow recognized this as a desktop robotic-arm assembly task and kept low-risk assumptions visible for review.
```

### Status Banner

The top of the detail must make the current status, its one-sentence summary, and its consequence visible together. Use compact chips for selected part, artifact availability, and validation state.

Bad:

```text
blocked_reasons: [{"code": "assembly_route_not_part_level"}, ...]
```

Good:

```text
Blocked at CAD IR validation. The agent generated a draft for `upper_link`, but the current CAD backend cannot execute this part type yet.
```

### Detail Cards

Use a responsive card grid rather than a linear report. Cards should contain two to five concise items and be grouped as:

- What happened.
- Why it stopped, or why it matters.
- Recommended next step.
- Artifact status.
- Key decisions.
- Review state and safety guardrails.

For assembly plans, candidate parts and reference components should be compact chips or rows, never one comma-separated raw field. Do not show raw provider identity, full diagnostic code lists, route names, gate actions, or raw blocked reason objects in these cards.

### User Actions

Group actions by primary, secondary, disabled, and advanced. For a CAD IR validation block, viewing the allowlisted draft and saving a stage review are primary; approval stays disabled until STEP/STL exists.

The Web Console may switch between English and Chinese for selected-stage and artifact-audit presentation copy. This changes only labels and human summaries; artifact names, source artifacts, backend action contracts, and debug data remain unchanged.

Action examples:

- Apply clarification.
- Edit artifact.
- Save stage review.
- Approve stage.
- Mark blocked.
- Create part request.
- Review part request.
- Create reviewed handoff.
- Create reviewed part.
- Review part result.
- Create / refresh workflow review.
- Run rework.
- Rerun downstream stage, when supported.

Disabled action example:

```text
Rerun Planning — disabled: stage rerun is not wired from this card yet.
```

### Important Artifacts

Show stage-relevant artifacts first. Each artifact row should show:

- Name.
- Present / absent.
- Source: original / user override.
- Editable / read-only.
- Validation status, if available.
- Short description.

Raw JSON should be collapsed under Advanced.

### Advanced / Raw JSON

Collapsed by default. Contains raw artifact viewer for allowlisted artifacts.

### Debug / Diagnostics

Collapsed by default. Contains:

- Raw diagnostic codes.
- Raw blocked reason objects.
- Adapter/provider identity.
- Agent trace stage names.
- Runtime summaries.
- Raw workflow graph / OpenNode-style data.

Debug content must be sanitized and path-safe.

## Stage-Specific Content Requirements

### Requirement

Human summary should answer:

- What did the agent understand?
- What is the scope?
- What assumptions were made?
- What still needs user confirmation?

Key fields:

- Original prompt.
- Requirement source: `requirement.json`, `requirement_v2.json`, or active override.
- `part_type`, `part_family`, `product_family`.
- `intent.scope` and `object_goal`.
- Assumptions.
- Missing information.
- Follow-up questions.
- Gate action.

Primary actions:

- Apply clarification.
- Edit requirement artifact.
- Save stage review.
- Continue / rerun Planning, when wired.

### Clarification

Human summary should explain whether user answers were applied.

Key fields:

- `requirement_clarification.json`.
- `requirement_v2.json`.
- Resolved and unresolved fields.
- Whether downstream Planning is stale after edits.

### Planning / Assembly Plan

Human summary should answer:

- What route was selected?
- What parts were found?
- Which are generated candidates?
- Which are reference-only?
- Which candidate is recommended next?
- Is full assembly CAD unsupported?

Key fields:

- Requirement source used.
- `planning_artifact.json`.
- `assembly_plan.json`.
- Candidate parts.
- Reference components.
- Selected / primary candidate.
- Assembly limitations.

Primary actions:

- Edit assembly plan.
- Create part request.
- Return to Requirement.
- Save stage review.

### Part Request / Part Review / Reviewed Handoff

Human summary should answer:

- Which part is selected?
- Is the request approved for single-part planning?
- What assembly context is preserved?

Primary actions:

- Create part request.
- Review part request.
- Create reviewed handoff.
- Save stage review.

### CAD IR Draft / Part Modeling

Human summary should answer:

- Did the CadIrAgent run?
- Was `cad_ir_draft.json` created?
- Did validation pass?
- Was child `input_ir.json` created?
- Were STEP/STL generated?
- If blocked, why?

For the current robot arm smoke, the correct user-facing summary is:

```text
Blocked at CAD IR validation. The agent produced a CAD IR draft for `upper_link`, but the current CAD backend does not support this part type yet. No child input_ir.json, STEP, or STL was created. This is expected for the current MVP and did not fallback to mounting_plate.
```

Primary actions:

- View CAD IR draft.
- Edit CAD IR draft override.
- Save stage review.
- Create / refresh workflow review.
- Continue implementation work on generic link-like CAD IR family.

### Workflow Review / Rework

Human summary should answer:

- What is the overall readiness?
- What risks remain?
- What is the recommended next action?
- Was rework requested or executed?

Primary actions:

- Create / refresh workflow review.
- Save stage review.
- Run rework, if supported.

## Diagnostics Translation

Raw diagnostic codes must not be the primary UI. They should be grouped and translated.

Suggested groups:

### Progress

Examples:

- `assembly.plan_created` -> Assembly plan created.
- `assembly.parts_detected` -> Candidate/reference parts detected.
- `part_request.created` -> Part request created.
- `part_handoff.ready_for_single_part_planning` -> Reviewed handoff ready.

### Limitations

Examples:

- `assembly.generation_not_supported_yet` -> Full assembly CAD is not supported yet.
- `reviewed_part_single_create.agent_ir_invalid` -> Agent-generated CAD IR did not pass validation.
- `reviewed_part_single_create.blocked_at_cad_ir_validation` -> Reviewed part create stopped at CAD IR validation.

### Safety

Examples:

- No fallback to `mounting_plate`.
- No STEP/STL generated after validation block.
- Provider-generated code rejected.
- User-edited executable code rejected.

### Debug

Raw code list remains accessible in Debug.

## Artifact Editing and Overrides

The Web Console may allow controlled edits to allowlisted intermediate JSON artifacts.

Rules:

- Original artifacts are preserved.
- User edits are saved as versioned overrides.
- Active overrides are explicit.
- Validation is required before an override becomes active.
- Downstream stages must record whether they used an original artifact or an override.
- Revert/deactivate override should be supported in a future UX pass.
- Diff original vs override should be supported in a future UX pass.

Editable artifacts are limited to structured workflow handoff artifacts such as:

- `requirement_v2.json`
- `planning_artifact.json`
- `assembly_plan.json`
- `part_create_request.json`
- `part_request_review.json`
- `reviewed_part_handoff.json`
- `cad_ir_draft.json`
- `input_ir.json`
- `stage_review.json`

Never edit directly:

- `prompt.txt`
- `model.py`
- `model.step`
- `model.stl`
- `report.json`
- `report.md`
- `agent_trace.json`
- `logs/runtime.json`
- provider transcripts or raw payloads
- arbitrary paths

## OpenNode / Raw Workflow Graph Policy

OpenNode-style or raw workflow graph data is useful for debugging but should not be the main user concept.

User-facing language should be:

- Work
- Workflow
- Stage
- Part
- Review
- Artifact
- Action
- Rework

Raw node data belongs under:

```text
Debug / Raw Workflow Graph
```

## UX Acceptance Criteria

A selected Work's Workflow page passes UX review when a user can answer these questions without opening raw JSON:

1. What did the Requirement agent understand?
2. Did the user already apply clarification?
3. Which requirement artifact did Planning use?
4. What parts did Planning identify?
5. Which part is recommended or selected next?
6. What has been reviewed or approved?
7. Did CadIrAgent create a draft?
8. If blocked, what blocked it in human language?
9. Did any user override affect this stage?
10. What is the next recommended action?

## Implementation Guidance

Prefer this layering:

```text
Artifact Layer
  Raw JSON/text files under a Work-contained run directory.

Backend Summary Layer
  Safe, path-free artifact summaries and action availability.

Stage View Model Layer
  User-facing workflow nodes, human summaries, key decisions, actions, and delivery state.

Presentation Layer
  NiceGUI graph, selected stage detail, work directory map, and delivery actions.
```

Do not let the Presentation Layer directly invent workflow state. It should render the Stage View Model and call backend/action routes.

## Recommended Next Implementation Step

Implement `Workflow Graph + Selected Stage Detail UX`:

1. Keep the Work-level Workflow graph as the primary navigation surface.
2. Selecting a graph node selects one stage.
3. Render only the selected stage's detail by default.
4. Keep raw graph and debug records outside the normal Console.
5. Convert gate decisions, blocked reasons, diagnostics, and adapter identity into human-readable summaries.
6. Show only final STEP, STL, and preview files as user-downloadable products.

No CAD generation capability should be added as part of this UX pass.
