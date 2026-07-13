# CadFlow Agent Rules

These are high-frequency rules for Codex and other coding agents. Keep this file short. Read the linked architecture and UX documents when the task touches those areas.

## Mandatory architecture baseline

Before changing product behavior, workflow, UI, agents, artifacts, lineage, reviews, or CAD execution, read:

- `docs/architecture/cadflow-canonical-product-architecture.md`

This document is the source of truth for the product object model, workflow checkpoints, and stage responsibilities.

Canonical object model:

- Workspace contains many Works and workspace configuration.
- Work is one mutable user-facing engineering task.
- Work contains or references Runs and Part Jobs.
- Run is one append-only execution attempt and audit record.
- Part Job is one intended part with multiple attempts and an explicit accepted-result pointer.
- Current Work is actionable and aggregates the active lineage.
- Run Snapshot is immutable and read-only.
- Active lineage and accepted part results are different concepts.

Canonical workflow:

- Prompt / Requirement Input
- Requirement
- Clarification when required
- Planning / Design Brief
- Assembly Plan and Candidate Parts
- Explicit Part Selection
- Part Request
- Part Review
- Reviewed Handoff
- CAD IR Draft
- CAD IR Validation and Part Modeling
- Part Result Review
- User Approval / Accepted Part Result
- Work-level Workflow Review
- Rework or next Part Job
- Deliverables

Do not add, remove, reorder, merge, or redefine these responsibilities as an incidental implementation change. An architecture change requires an explicit proposal and synchronized updates to the canonical architecture, contracts, projections, tests, UX, roadmap, task board, and readiness status.

## Product goal

CadFlow is a user-facing CAD workflow product, not an artifact browser, debug console, template catalogue, or collection of disconnected buttons.

The primary user experience must always answer:

1. What is the current result?
2. Why is the workflow in this state?
3. Does the user need to decide anything?
4. What is the recommended next action?
5. What visible result will that action produce?

## Before changing UI or workflow

Write down the following for the affected user task:

- affected canonical object: Workspace, Work, Run, or Part Job;
- affected canonical checkpoint;
- stage input, output, and user decision;
- user goal;
- information the user actually needs now;
- decision required, if any;
- one recommended next action;
- success postcondition visible in the UI;
- failure feedback and recovery path.

Do not begin by exposing every available field, artifact, action, Run id, internal status, or diagnostic.

## User relevance gate

For every visible item, ask:

- Does the user need this to understand the current state?
- Does the user need this to make the current decision?
- Does the user need this to verify the result?

If all answers are no, move it to Advanced / Diagnostics or remove it from the primary surface.

Internal implementation details such as backend action names, raw enum values, absolute paths, provider payloads, trace ids, and repetitive provenance must not dominate the main UI.

## Progressive disclosure

Use this priority order:

1. current conclusion;
2. recommended action;
3. user input, agent decision, and agent output;
4. directly relevant artifacts and review state;
5. alternatives and secondary actions;
6. diagnostics, raw JSON, lineage detail, and internal metadata.

Hover text should clarify an action, not dump the entire action contract. It should normally explain:

- what the action does;
- the important consequence;
- whether it creates a new Run or changes Current Work;
- why it is unavailable, when disabled.

Keep detailed target ids, audit metadata, and low-level side effects in an expandable details area.

## Workflow semantics

The product Workflow represents trusted checkpoints and user decisions. It is not the agent's full reasoning trace.

Every visible stage and action must match the real workflow:

- actions operate on the correct Work, Run, Stage, and part;
- Current Work is actionable;
- Run Snapshot is immutable and read-only;
- Work pointers may change, historical Run artifacts may not;
- accepted part results are distinct from the current active lineage;
- changing an upstream decision marks affected downstream stages stale;
- no stage may look completed if its own output did not complete;
- upstream limitations must not be shown as the selected stage's execution failure;
- creating a result does not automatically approve it;
- a single generated part is not a complete assembly;
- Contract mode does not expect STEP/STL and is not a failure.

## Interaction closure

No enabled write action may be silent.

Required lifecycle:

- confirmation when consequential;
- immediate pending feedback;
- duplicate-click protection;
- backend execution;
- postcondition verification;
- persistent success or failure feedback;
- refreshed visible workflow state;
- clear next action.

A returned function result is not sufficient proof of success. Verify the user-visible postcondition.

## Buttons and actions

- One visually dominant primary action per current task.
- Separate navigation, structured input, workflow commands, and disabled future actions.
- Do not show an enabled button without a real handler and visible postcondition.
- Dangerous or consequential decisions belong in a form or confirmation dialog.
- Do not place inspect, approve, block, retry, and debug actions at equal visual weight.

## Artifacts

Input, output, evidence, and review artifacts shown to users must be directly openable through controlled viewers.

- Show a human summary before raw content.
- Show provenance only when it helps distinguish artifacts.
- Group repeated filenames by meaning and source instead of rendering duplicate names.
- Keep arbitrary file browsing disabled.
- Never expose absolute local paths in the product UI.

## Language

When a language switch exists, all primary UI labels, actions, tooltips, dialogs, validation feedback, pending states, success messages, failure messages, and disabled reasons must switch consistently.

Do not fall back to backend keys, `Available`, raw enums, or English-only tooltips in Chinese mode.

## Agent capability boundary

Constrain side effects, not useful reasoning.

- Agent reasoning may request context, compare candidates, submit structured proposals, and repair from validation feedback within a bounded episode.
- Agents operate inside checkpoint transitions; they do not redefine or bypass the product workflow.
- Only validated structured contracts may reach deterministic CAD execution.
- Do not allow provider-generated Python, shell, or CadQuery to bypass CAD IR.
- Deterministic adapters are tests, CI, examples, and fallback behavior; they are not the product capability ceiling.

## Verification

Automated tests are necessary but do not prove product usability.

For UI and workflow changes, distinguish:

- implemented;
- automated verified;
- manually verified;
- production usable.

Manually verify the affected user journey in a real browser whenever possible. Do not claim manual verification or screenshots that were not completed.

## Documentation sync

After changing code, behavior, workflow, artifacts, actions, ports, configuration, or user-visible semantics, inspect and update the relevant documents:

- `docs/architecture/cadflow-canonical-product-architecture.md`
- `docs/usage.md`
- `FINAL-PRD.md`
- `docs/status/current-product-readiness.md`
- `docs/roadmap/milestones.md`
- `docs/tasks/task-board.md`
- relevant files under `docs/product/`, `docs/architecture/`, and `docs/ux/`

New commands, ports, deployment modes, environment variables, cache/data files, API paths, and error codes require `docs/usage.md` updates.

Interface or data-structure changes require contract, projection, migration, and test review.

## Required reading by task

For every product task:

- `docs/architecture/cadflow-canonical-product-architecture.md`
- `docs/status/current-product-readiness.md`

For Workflow Cockpit work:

- `docs/ux/product-usability-principles.md`
- `docs/ux/workflow-cockpit-design-spec.md`
- `docs/architecture/web-workflow-console.md`

For agent architecture work:

- `docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `docs/architecture/workflow-cockpit-decision-and-cad-ir-progress.md`

## Safety defaults

- Web services default to `127.0.0.1`.
- Tailnet access is preferred for remote use.
- Do not enable Funnel by default.
- Public exposure must be explicit and documented with risks.

## Final self-review

Before reporting completion, answer:

- Does the change preserve the canonical Workspace / Work / Run / Part Job model?
- Does it preserve the canonical checkpoint order and stage responsibility?
- Is the primary user task clearer than before?
- Can the user identify the current state and next action without reading diagnostics?
- Does every enabled action produce immediate and final feedback?
- Are important artifacts directly inspectable?
- Does the UI reflect the real Workflow and Work/Run semantics?
- Is nonessential information progressively disclosed?
- Are Chinese and English experiences consistent?
- Were architecture, UX, readiness, roadmap, and tests synchronized?
- Were manual verification limits reported honestly?
