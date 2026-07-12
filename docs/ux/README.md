# CadFlow UX Design Pack

This directory is the product-facing UI specification for CadFlow. It sits between product intent and implementation.

The architecture documents explain how workflow data is stored and projected. The UX documents explain what the user should see, understand, and do.

## Canonical documents

- [`workflow-cockpit-design-spec.md`](workflow-cockpit-design-spec.md) — authoritative design specification for Workspace, Work, Run, workflow graph, stage detail, intervention, visual hierarchy, and acceptance.
- [`../architecture/web-console-ux-architecture.md`](../architecture/web-console-ux-architecture.md) — existing Web Console information architecture and review-surface principles.
- [`../architecture/web-workflow-console.md`](../architecture/web-workflow-console.md) — backend, lineage projection, artifact, and action architecture.

If implementation and UX copy disagree, first decide whether the problem is product design or backend projection. Do not patch the presentation layer until the expected user behavior is written here.

## Required UI design workflow

Every meaningful Web Console change should follow this order:

1. **User task** — state what the user is trying to accomplish.
2. **User journey** — state where the user came from and what should happen next.
3. **Information hierarchy** — decide what is primary, secondary, advanced, and debug-only.
4. **Interaction flow** — define default selection, click behavior, actions, and post-action navigation.
5. **View-model contract** — define required fields and fallback states before rendering.
6. **Wireframe** — provide an ASCII or visual layout before styling.
7. **State matrix** — cover loading, empty, ready, running, completed, needs-review, blocked, failed, skipped, stale, and unavailable.
8. **Visual rules** — apply consistent typography, spacing, status colors, selected state, and action hierarchy.
9. **Implementation** — connect NiceGUI to the approved view model; do not invent workflow state in the UI.
10. **Screenshot acceptance** — verify the page visually with the Golden Desktop Robot Arm flow, not only through unit tests.

## Non-negotiable product rules

- The primary workflow state is a **clickable dot-and-connector flow graph**.
- Every stage must make **user input**, **agent interpretation/decision**, and **agent output** distinguishable.
- Users must be able to identify where they can review, override, approve, rerun, or request rework.
- A **Work** and its immutable **Runs** must never be visually conflated.
- The normal UI must explain conclusions without requiring raw JSON, diagnostic codes, or provider traces.
- A graph node may never render as an unlabeled or semantically blank dot. Missing data is an explicit `unavailable` state with a human-readable explanation.
- Work-level workflow and run-level audit are separate modes:
  - **Current Work** shows the active aggregated lineage and allows actions.
  - **Run Snapshot** shows one immutable attempt and is read-only except for creating a new rework/child run.
- User edits are validated overrides. Original agent artifacts remain immutable.
- NiceGUI renders view models and calls backend actions. It does not derive business status from CSS, file names, or local component state.

## Definition of done for a UI change

A UI change is not complete because tests pass. It is complete when:

- the primary user task is obvious within five seconds;
- the current Work/Run context is unambiguous;
- all visible graph nodes have label, state, summary, and click behavior;
- stage input and output are recognizable without opening raw JSON;
- the recommended next action is clear and limited to one primary action;
- blocked, skipped, and unavailable states explain their cause and consequence;
- Contract and Full example modes are visually distinct;
- screenshots for the Golden Desktop Robot Arm flow satisfy the acceptance criteria in the canonical design specification.
