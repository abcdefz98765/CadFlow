# CadFlow UX Design Pack

This directory defines what users should see, understand, and do. Product objects and checkpoint responsibilities are defined by the canonical architecture; technical storage and action boundaries are defined by specialized architecture documents.

## Authoritative documents

Read in this order:

1. `../architecture/cadflow-canonical-product-architecture.md` — Workspace, Work, Run, Part Job, checkpoint order, and stage responsibility.
2. `product-usability-principles.md` — information relevance, guidance, progressive disclosure, Hover, and action feedback.
3. `workflow-cockpit-design-spec.md` — Workflow Cockpit pages, graph, stage detail, interaction, responsive behavior, and acceptance.
4. `../architecture/web-workflow-console.md` — view-model, renderer, action, artifact, and runtime feedback boundaries.
5. `../status/current-product-readiness.md` — what is implemented, verified, and actually usable now.

Do not patch presentation behavior until the expected user task and canonical checkpoint are clear.

## Required UI design workflow

Every meaningful Web Console change follows:

1. Identify the affected canonical object and checkpoint.
2. State the user's goal and current decision.
3. Define primary, secondary, advanced, and diagnostic information.
4. Define one recommended action and its visible postcondition.
5. Define failure feedback and recovery.
6. Confirm the view-model contract and immutable Work/Run boundaries.
7. Cover loading, empty, ready, running, completed, needs-review, blocked, failed, skipped, stale, and unavailable states as applicable.
8. Implement through the shared renderer and action lifecycle.
9. Run automated contract tests.
10. Exercise the affected journey in a real browser and record verification honestly.

## Non-negotiable rules

- Workflow is a clickable checkpoint graph, not a raw backend route diagram.
- Current Work is actionable; Run Snapshot is immutable and read-only.
- Every selected stage distinguishes user input, agent interpretation/decision, agent output, review, and evidence.
- The primary screen explains the current conclusion and next action without raw JSON or diagnostics.
- One action is visually dominant for the current task.
- Candidate inspection and candidate selection are distinct.
- User edits are validated, versioned overrides; original Run artifacts remain immutable.
- Enabled write actions provide confirmation when needed, immediate pending state, postcondition verification, persistent success/failure, and refreshed workflow state.
- Important artifacts are directly inspectable through controlled viewers.
- Contract and Full modes are visually and semantically distinct.
- Chinese and English primary UI experiences switch consistently.
- NiceGUI renders approved view models and calls safe actions; it does not invent business state.

## Definition of done

A UI change is not complete only because tests pass.

It is complete when:

- the user can identify the current state and recommended action quickly;
- the action has a real backend target and visible result;
- success and failure are unambiguous;
- the relevant artifact or review can be inspected;
- Work/Run semantics remain correct;
- responsive behavior is usable at the affected widths;
- manual verification limits and screenshots are reported honestly;
- readiness, roadmap, tasks, and affected architecture/UX documents are synchronized.