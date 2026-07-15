# Product Usability and Workflow Guidance Principles

## Purpose

This document defines how CadFlow should decide what to show, what to hide, how to guide the user, and how to keep the product Workflow aligned with the real engineering workflow.

CadFlow should not optimize for displaying all available data. It should optimize for helping a user understand the current result, make the next valid decision, and verify what changed.

## Product usability test

A normal user should be able to answer the following without opening Diagnostics:

1. What am I trying to create?
2. What has CadFlow completed?
3. What has not been completed?
4. What result is currently accepted?
5. What requires my review or input?
6. What should I do next?
7. What will happen if I click the recommended action?
8. How will I know whether it succeeded?

If the primary screen cannot answer these questions, adding more fields, badges, artifacts, or buttons usually makes the problem worse.

## User relevance filter

Before placing information on the primary surface, classify it.

### Decision-critical

The user needs it to make the current decision.

Examples:

- selected candidate;
- missing required dimension;
- generated result scope;
- important limitation;
- current review state;
- stale downstream stages;
- recommended next action.

Show prominently.

### Verification-critical

The user needs it to confirm that an action or result is correct.

Examples:

- accepted part result;
- selected candidate after an override;
- generated STEP/STL availability;
- review saved successfully;
- source artifact when two results could be confused.

Show near the result or action feedback.

### Contextual

Useful for understanding, but not required for the current decision.

Examples:

- concise agent assumptions;
- alternative candidates;
- related artifacts;
- previous accepted result;
- short provenance.

Show in secondary sections or expandable panels.

### Operational / diagnostic

Primarily useful to developers or advanced troubleshooting.

Examples:

- backend action name;
- raw enum values;
- internal Run identifiers repeated on every row;
- trace ids;
- validation payloads;
- raw JSON;
- absolute paths;
- low-level timing and action audit fields.

Keep under Advanced / Diagnostics. Do not use these as the main explanation.

## Information hierarchy

The default page order should follow the user's decision process:

### 1. Current conclusion

State what CadFlow has concluded in plain language.

Good:

- One generic upper-link concept part was generated successfully.
- The CAD IR contract is valid, but CAD execution was intentionally skipped.
- The selected candidate changed to lower_link; downstream part stages are now stale.

Poor:

- completed
- ready_for_review
- upper_link, accepted_for_preview

### 2. Current limitation or scope

Only show limitations that materially affect the user's interpretation.

Examples:

- This is not a complete robot-arm assembly.
- Strength and motion were not validated.
- Contract mode does not produce STEP/STL.

Do not repeat every warning from every upstream stage.

### 3. Recommended next action

There should normally be one clearly recommended action.

It should say what the user is trying to accomplish, not expose an internal method name.

Good:

- Review this stage
- Create the part request
- Inspect the CAD IR draft
- Select this part for the next step

Poor:

- save_stage_review
- reviewed_handoff
- run_rework

### 4. Causal detail

Use the sequence:

- USER INPUT
- AGENT INTERPRETATION / DECISION
- AGENT OUTPUT

Each block should explain meaning, not merely list fields.

### 5. Evidence and artifacts

Show only the artifacts that substantiate the current conclusion or enable the next decision.

### 6. Advanced detail

Place raw contracts, complete provenance, diagnostics, traces, and audit fields here.

## Workflow guidance model

Each visible stage should answer:

- Purpose: why this stage exists.
- Entry condition: what must already be true.
- Result: what this stage produces.
- Review: whether a user decision is required.
- Next: what normally follows.
- Failure/recovery: what the user can do when it cannot proceed.

Example:

### Assembly Plan

Purpose:
Break the assembly request into generated candidates and reference-only components.

Entry condition:
An accepted requirement and planning result exist.

Result:
A selected candidate and preserved assembly context.

Review:
The user may inspect candidates or explicitly change the selected candidate.

Next:
Create a Part Request for the selected candidate.

Failure/recovery:
Edit the requirement or plan when the candidate split is incorrect.

## Checkpoints versus internal agent steps

The Workflow graph represents trusted product checkpoints.

It should not expand every internal model call, context request, validation retry, or repair attempt into a primary workflow node.

Internal agent episode events belong in an expandable trace.

The user-facing Workflow should remain stable even as the Agent becomes more capable.

## Action design

### Primary action

One action should dominate when one next step is recommended.

### Secondary actions

Use for legitimate alternatives that do not deserve equal weight.

Examples:

- inspect artifact;
- choose another candidate;
- refresh review.

### Review decisions

Approve, Needs Revision, and Blocked belong in a dedicated review interaction, not mixed indiscriminately with navigation and debug actions.

### Dangerous or consequential actions

Require confirmation when an action:

- changes an accepted upstream decision;
- marks downstream stages stale;
- creates a new Run;
- updates an accepted pointer;
- starts a long-running CAD execution;
- initiates rework.

The confirmation should describe only consequences the user cares about.

Do not lead with internal implementation details such as exact metadata filenames.

## Hover and help text

Hover text is a compact explanation, not a substitute for information architecture.

A useful Hover normally contains:

- one sentence describing the action;
- one sentence describing the important result;
- a short note when it creates a Run, changes Current Work, or is disabled.

Example:

Select this candidate for the next part workflow. CadFlow will preserve the original plan, mark downstream stages stale, and recommend creating a new Part Request. Existing Runs and accepted results are retained.

Do not include all of the following by default:

- full Work id;
- full Run id;
- target Stage id;
- backend action;
- action category;
- expected postcondition object;
- audit timestamps.

Those belong in Action Details or Diagnostics.

## Action feedback

Every write action should produce feedback at three moments.

### Immediate

The interface acknowledges the click and shows pending state.

### Final

The interface clearly shows success or failure.

### Verified result

The relevant page state visibly changes.

Examples:

- selected candidate label changes;
- downstream nodes become stale;
- review status becomes Approved;
- accepted result appears in Parts;
- a new Run appears in lineage.

A success toast without a visible state change is insufficient.

## Artifact presentation

Artifacts should be presented by purpose, not only filename.

Good:

- Active Assembly Plan
- Reviewed Part Handoff
- CAD IR Draft
- Part Result Review
- Work-level Review

The filename can remain as secondary metadata.

When repeated filenames exist, distinguish them by role first and provenance second.

Example:

- Root workflow report
- Upper-link child result report
- Rework attempt report

Do not render four indistinguishable `report.json` entries.

## Candidate parts

A candidate node should support two distinct concepts:

### Inspect candidate

Read-only. Explains role, support status, selection state, interfaces, current pipeline state, and limitations.

### Select candidate

Explicit write action. Requires confirmation and explains stale consequences.

Clicking the node itself must not silently change the selected candidate.

Reference-only components may be inspected but may not offer generation or selection actions.

## Reviews

Agent review and user review are different concepts.

### Agent review

CadFlow assesses evidence, completeness, validation, risks, and confidence.

### User review

The user decides whether to:

- approve;
- request revision;
- mark blocked.

The UI must not make the user appear responsible for assigning an engineering score that should be produced by deterministic validation or the review agent.

## Copywriting rules

Prefer concrete language:

- what happened;
- what it means;
- what remains incomplete;
- what to do next.

Avoid unexplained internal terms:

- active lineage leaf;
- materialization;
- adapter operation;
- route selected;
- projection unavailable;
- stage_count.

When an internal term is necessary, introduce it with a user-facing explanation.

## Empty, blocked, stale, and skipped states

### Empty

Explain what has not started and how to start it.

### Blocked

Explain the blocking category:

- missing user input;
- missing prerequisite;
- invalid override;
- validation failure;
- unsupported capability;
- unexpected runtime failure.

Offer only valid recovery choices.

### Stale

Explain which upstream decision changed and what must be regenerated or reviewed.

### Skipped

Explain whether it is intentional.

Contract mode `execution_skipped` is a successful contract outcome, not a failure.

## Localization

Localization includes meaning, not only labels.

The Chinese UI must also localize:

- action consequences;
- disabled reasons;
- state explanations;
- confirmation details;
- validation errors;
- success/failure feedback;
- empty and skipped explanations.

Do not concatenate translated labels with untranslated sentences into a mixed-language primary surface.

## Product readiness review

For every significant UI or Workflow change, review the affected journey with this table:

| Question | Required evidence |
| --- | --- |
| Can the user identify the current state? | Screenshot or browser verification |
| Is the recommended next action obvious? | One primary action in the relevant state |
| Does the action explain its consequence? | Label, concise help, or confirmation |
| Is pending state visible? | Runtime verification |
| Is success/failure explicit? | Runtime verification |
| Is the postcondition visible? | Refreshed state verification |
| Are nonessential details hidden? | Primary/Advanced inspection |
| Are artifacts directly inspectable? | Viewer verification |
| Does the Workflow match backend semantics? | Projection and browser verification |
| Are both languages coherent? | English and Chinese browser verification |
| Were docs synchronized? | Relevant documentation diff |

## Anti-patterns

Avoid:

- adding a card for every available data structure;
- placing every action on the same visual level;
- using Hover to expose the full backend contract;
- showing raw JSON as the default success result;
- using tests as proof that a user understands the page;
- presenting a deterministic fallback as full agentic capability;
- mixing Current Work and historical Run Snapshot actions;
- showing a selected stage as failed because an upstream limitation exists;
- hiding important consequences only in a tooltip;
- assuming more provenance always improves clarity;
- adding workflow stages that represent implementation functions rather than user-visible checkpoints.

## Completion checklist

Before completing a UI or Workflow task:

- Confirm the user goal and checkpoint.
- Remove information unrelated to the current decision.
- State the current conclusion in plain language.
- Provide at most one dominant recommended action.
- Explain important action consequences.
- Show pending, success, failure, and verified postcondition.
- Make relevant artifacts directly inspectable.
- Keep debug data under Advanced.
- Verify Work/Run and stale/accepted semantics.
- Verify Chinese and English experiences.
- Update readiness, roadmap, task board, usage, architecture, or UX documents as applicable.
- Report what was not manually verified.

## Workflow guidance and information reduction gate

Each visible Workflow stage projection provides a localized Guidance Contract:
purpose, current conclusion, why it matters, whether a user decision is
required, decision summary, one recommended next action, expected result,
normal next stage, blocked reason, recovery action, and limitations. These
fields explain the user's engineering workflow; they do not expose action keys,
Run ids, artifact paths, or backend state as the explanation.

The selected-stage primary order is: current conclusion, user decision,
recommended action, expected result, user input, agent interpretation, agent
output, related review and evidence, alternatives, then Advanced. Action hover
remains concise. Full action targets, internal action keys, expected
postconditions, and audit metadata stay available in expandable Action Details.
