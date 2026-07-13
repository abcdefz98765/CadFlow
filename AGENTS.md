# CadFlow Agent Rules

Read this file before changing the repository. Keep it short and enforceable.

## Mandatory architecture

Before changing product behavior, Workflow, UI, agents, skills, knowledge, artifacts, lineage, reviews, or CAD execution, read:

- `docs/architecture/cadflow-canonical-product-architecture.md`
- `docs/status/current-product-readiness.md`

Canonical object model:

- Workspace contains many Works and workspace configuration.
- Work is one mutable user-facing engineering task.
- Work references Runs and Part Jobs.
- Run is one append-only execution attempt and audit record.
- Part Job is one intended part with multiple attempts and an explicit accepted-result pointer.
- Current Work is actionable and aggregates the active lineage.
- Run Snapshot is immutable and read-only.
- Active lineage and accepted part results are distinct.

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

Do not add, remove, reorder, merge, or redefine these responsibilities as an incidental change. Architecture changes require explicit synchronized updates to architecture, contracts, projections, tests, UX, roadmap, task board, and readiness.

## Agent, skill, and knowledge boundary

For Agent or provider work, also read:

- `docs/architecture/agent-skill-knowledge.md`
- `docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`

Rules:

- A provider is replaceable; logical agent roles and skills are CadFlow-owned.
- Each operation maps to one declared skill and canonical checkpoint.
- Skills define behavior, inputs, outputs, allowed context/tools, stop conditions, and prohibitions.
- Global invariants live in `policies/`.
- Cross-skill knowledge has one source under top-level `knowledge/`.
- Skill-private knowledge lives under `skills/<skill>/knowledge/` and is not exposed to unrelated agents.
- Accepted Work artifacts are runtime context, not static knowledge.
- Validator feedback is Run/episode observation, not global knowledge.
- Default context is minimal and allowlisted; do not load every skill or the repository.
- Agents may request context, compare candidates, submit structured proposals, and repair within bounded episodes.
- Only validated structured contracts reach deterministic CAD execution.
- Provider-generated Python, shell, or CadQuery cannot bypass CAD IR.
- Agents operate inside checkpoint transitions; they do not redefine the product Workflow.

## Product goal

CadFlow is a user-facing CAD workflow product, not a raw artifact browser, debug console, template catalogue, or collection of disconnected buttons.

The primary experience must answer:

1. What is the current result?
2. Why is the Workflow in this state?
3. Does the user need to decide anything?
4. What is the recommended next action?
5. What visible result will that action produce?

## Before changing UI or Workflow

Write down:

- affected canonical object and checkpoint;
- stage input, output, and user decision;
- current user goal;
- information needed now;
- one recommended action;
- visible success postcondition;
- failure feedback and recovery path.

For every visible item, ask whether it helps the user understand the state, make the current decision, or verify the result. If none apply, move it to Advanced / Diagnostics or remove it.

Information order:

1. current conclusion;
2. recommended action;
3. user input, agent decision, and agent output;
4. relevant artifacts and review state;
5. alternatives and secondary actions;
6. raw JSON, lineage detail, audit metadata, and diagnostics.

Hover text explains the action and important consequence. Detailed ids and audit fields belong in expandable details.

For Workflow Cockpit work, read:

- `docs/ux/product-usability-principles.md`
- `docs/ux/workflow-cockpit-design-spec.md`
- `docs/architecture/web-workflow-console.md`

## Workflow invariants

- Actions target the correct Work, Run, Stage, and part.
- Current Work is actionable; Run Snapshot is read-only.
- Work pointers may change; historical Run artifacts may not.
- Changing upstream meaning marks affected downstream stages stale.
- Creating a result does not approve it.
- A single generated part is not a complete assembly.
- Contract mode does not expect STEP/STL and is not a failure.
- Upstream limitations must not appear as the selected stage's execution failure.

## Interaction closure

No enabled write action may be silent.

Required lifecycle:

- confirmation when consequential;
- immediate pending feedback;
- duplicate-click protection;
- backend execution;
- refreshed projection and postcondition verification;
- persistent success or failure feedback;
- clear next action.

A returned function value is not proof of product success.

Use one dominant primary action. Separate navigation, structured input, workflow commands, review decisions, and disabled future actions. Do not show an enabled control without a real handler and visible postcondition.

## Artifacts and language

- User-visible input, output, evidence, and review artifacts are directly openable through controlled viewers.
- Show human purpose before filename and raw content.
- Show provenance only when it distinguishes results.
- Group duplicate filenames by role and source.
- Never expose arbitrary browsing or absolute paths.
- When a language switch exists, primary labels, actions, help, dialogs, validation, pending, success, failure, and disabled reasons switch consistently.
- Do not fall back to backend keys, raw enums, `Available`, or English-only Hover in Chinese mode.

## Verification and documentation

Automated tests are necessary but do not prove product usability. Distinguish:

- implemented;
- automated verified;
- manually verified;
- production usable.

After changes, inspect and update as applicable:

- `docs/architecture/cadflow-canonical-product-architecture.md`
- `docs/architecture/agent-skill-knowledge.md`
- `docs/workflow_contract.md`
- `docs/usage.md`
- `FINAL-PRD.md`
- `docs/status/current-product-readiness.md`
- `docs/roadmap/milestones.md`
- `docs/tasks/task-board.md`
- relevant `docs/product/`, `docs/architecture/`, `docs/ux/`, `skills/`, `knowledge/`, and `policies/` files.

New commands, ports, deployment modes, environment variables, cache/data files, API paths, and error codes require `docs/usage.md` updates.

Before reporting completion, confirm that the change preserves the canonical object model, checkpoint responsibilities, skill/knowledge ownership, user guidance, interaction feedback, artifact safety, language consistency, and honest verification status.

## Safety defaults

- Web services default to `127.0.0.1`.
- Tailnet access is preferred for remote use.
- Do not enable Funnel or public exposure by default.
- Public exposure must be explicit and documented with risks.