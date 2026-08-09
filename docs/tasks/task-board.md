# CadFlow Task Board

Status date: 2026-08-09.

Ordered milestones are in `docs/roadmap/milestones.md`.

This board intentionally tracks product work rather than repeating every historical internal package. Detailed acceptance history remains in Git/status records.

## Completed foundation

- [x] Workspace / Work / immutable Run model.
- [x] Ordered Part Job attempts.
- [x] Accepted-result pointers separate from active lineage.
- [x] WorkOrchestrator product mutation boundary.
- [x] Deterministic compatibility CAD path and regression coverage.
- [x] Provider-selected bounded Agent Episode foundation.
- [x] Controlled model-program execution and STEP inspection.
- [x] Reviewable publication boundary.
- [x] Explicit Accept / Revise preserving history.
- [x] Reuse-first NiceGUI Workbench.
- [x] Product Golden / request -> design -> geometry story.
- [x] Home / Works / Settings onboarding.
- [x] Real Agent and Completed Product Example separation.
- [x] Developer fixture separation.
- [x] Provider credential discovery from session -> process environment -> project `.env` without secret persistence.
- [x] Readable sanitized Agent Output.
- [x] Clarification answer/resume evidence.
- [x] Typed recovery guidance.
- [x] M2.7 merged to `main`.

## Current milestone — M2.8 Dynamic Work Graph

### Product goal

Workflow must become the live state map originally intended for CadFlow:

- user request / intent;
- Agent design/decomposition;
- Part Jobs;
- attempts and revision branches;
- clarification and user answers;
- meaningful build/validation/recovery state;
- reviewable and accepted results;
- later Assembly/Deliverable state only when real capability exists.

The graph is a projection of current domain state, not a second workflow engine.

### First: implementation audit

- [ ] Inventory the existing target Agent-first Workflow projection and legacy Workflow graph renderer.
- [ ] Document which existing graph/layout/selection/detail components can be reused as-is.
- [ ] Identify the exact reason the current Agent-first projection collapses to four phase nodes.
- [ ] Confirm the current sources of truth for:
  - Work intent;
  - Part Jobs;
  - attempts/Run lineage;
  - clarification question/answer;
  - Agent design/output;
  - validation/recovery;
  - reviewable results;
  - accepted pointers.
- [ ] Identify any required graph fact that genuinely cannot be derived from existing durable evidence before adding new persistence.

### Projection

- [ ] Replace the four-node Agent-first Workflow projection with a dynamic Work graph projection.
- [ ] Keep Intent / Design / Build & Evaluate / Accept & Deliver as graph grouping/orientation, not the whole graph.
- [ ] Use a deliberately small semantic node vocabulary for current behavior.
- [ ] Use a deliberately small edge/transition vocabulary derived from real state.
- [ ] Do not render provider turns/tool calls/log events as Workflow nodes.
- [ ] Preserve existing compatibility Workflow projection for legacy Runs where appropriate.

### Single-Part user flows

- [ ] New/ready-to-design Work shows a clear beginning state.
- [ ] Agent design evidence appears without fabricating future checkpoints.
- [ ] Clarification appears as a meaningful branch/state and the submitted answer remains visible.
- [ ] Resume after clarification updates the same Work graph.
- [ ] Build/validation failure or typed stop shows where/why execution stopped.
- [ ] Repair/retry appears only when it actually occurred.
- [ ] Reviewable result is visually distinct from accepted result.
- [ ] Accept updates graph state only after persisted accepted pointer verification.
- [ ] Revision creates a new branch/attempt while preserving the previous branch/result.

### Part Jobs / branching

- [ ] Existing multiple Part Jobs render as real branches rather than a flat list when Work state contains them.
- [ ] Part branches show current attempt/result/attention state without inventing unsupported steps.
- [ ] Selecting a Part/result node reuses existing Workbench/Parts/geometry/result detail.
- [ ] Accepted Part state remains independent of active attempt state.

Do not implement new Agent multi-Part decomposition merely to make this graph look more impressive. The graph should be ready to display real decomposition when the runtime creates it later.

### Node interaction and revision

- [ ] Clicking a node selects detail without mutating business state.
- [ ] Historical attempt/result nodes can navigate to existing read-only Run Snapshot/evidence.
- [ ] Where valid, provide `Start Revision from here` using existing child-Run/attempt semantics.
- [ ] Never delete or rewrite downstream historical evidence to simulate rollback.

### Overview consistency

- [ ] Overview and Workflow derive from the same current Work state.
- [ ] Current phase/status/recovery/result shown in Overview agrees with graph state.
- [ ] No state such as `Ready for review` may coexist with a contradictory `Design not started` graph unless the user is explicitly viewing a historical Run.

### UX / visual design

- [ ] Reuse the current dot graph visual vocabulary rather than building a new graph framework.
- [ ] Make active/blocked/reviewable/accepted/revision branches understandable at a glance.
- [ ] Use progressive disclosure so simple Works stay visually simple.
- [ ] Make selected node detail useful without duplicating the entire Overview.
- [ ] Keep Agent Output / technical evidence inspectable but out of the primary graph.
- [ ] Preserve Chinese/English support.
- [ ] Verify desktop, 1024px, and mobile behavior.

### Browser acceptance

Manually verify at least:

- [ ] beginning-state Real Agent Example;
- [ ] clarification -> answer -> resumed Work;
- [ ] typed failure/block with real reason;
- [ ] reviewable Product Golden state;
- [ ] accepted result;
- [ ] revision branch preserving prior accepted state;
- [ ] a Work containing more than one Part Job if existing fixture/evidence provides one;
- [ ] node -> detail navigation;
- [ ] node -> Run Snapshot -> Current Work navigation;
- [ ] Chinese critical path;
- [ ] 1440px / 1024px / 390–430px.

### Tests

- [ ] Graph state comes from domain/evidence rather than browser-owned business state.
- [ ] Four phases are grouping metadata, not the complete graph node list.
- [ ] Clarification/answer history projects correctly.
- [ ] Reviewable/accepted are distinct.
- [ ] Revision produces a branch and preserves history.
- [ ] Multi-Part branch projection works on existing real fixture/domain state.
- [ ] Overview/Workflow consistency contracts.
- [ ] Run Snapshot remains read-only.
- [ ] No graph database/workflow engine/parallel persistence introduced.
- [ ] Full relevant regression remains green.

### M2.8 explicit non-goals

Do not add during this milestone unless a demonstrated bug makes it unavoidable:

- [ ] no new sandbox/security/attestation architecture;
- [ ] no new Provider abstraction layer;
- [ ] no graph DB;
- [ ] no BPMN/workflow DSL;
- [ ] no graph-specific durable state model;
- [ ] no Feature Graph CAD implementation;
- [ ] no new CAD families for the sake of the demo;
- [ ] no new Assembly execution;
- [ ] no Deliverable/BOM/drawing implementation;
- [ ] no formal five-case external-provider benchmark.

## After M2.8 — M2 real-provider product trial

- [ ] Run at least five non-template real-provider designs through real Works.
- [ ] Require at least two real observation-driven repairs.
- [ ] Obtain at least one genuine focused clarification rather than fabricating it.
- [ ] Inspect Agent Output, Dynamic Workflow, geometry, validation, and recovery through the actual product UI.
- [ ] Explicitly accept or revise resulting reviewable results as a user.
- [ ] Record failure modes before choosing M3.

## M3 — capability decision from evidence

Do not assume a large Feature Graph is automatically next.

After the product trial:

- [ ] classify actual modeling/revision failures;
- [ ] decide whether the smallest next improvement is:
  - better Agent context/skill behavior;
  - model-program repair improvements;
  - a limited structured feature representation;
  - missing deterministic CAD operations;
  - UI/workflow improvements;
  - Provider change/evaluation.
- [ ] write a narrow milestone only after this evidence exists.

## Later — Multi-Part / Assembly

- [ ] Let the Agent create multiple real Part Jobs from a Work when this capability is intentionally implemented.
- [ ] Visualize those Part Jobs naturally in Dynamic Workflow.
- [ ] Create Assembly Job only from real accepted inputs.
- [ ] Add the minimum placement/constraint/validation behavior required by actual use cases.

Do not pre-build a general assembly solver.

## Later — Deliverables

- [ ] Generate only deliverables required by validated workflows.
- [ ] Resolve final outputs through accepted results.
- [ ] Add BOM/drawings/reports incrementally when users actually need them.

## Product discipline checklist

Before accepting a new task, answer:

- [ ] What current user problem does this solve?
- [ ] Can existing Work/Run/Part Job state express it?
- [ ] Can existing libraries/components solve it?
- [ ] Is a new abstraction genuinely required?
- [ ] Is this needed now, or only a plausible future capability?
- [ ] Will the change make a real Work easier to understand/use?

If these answers are unclear, do not expand the architecture yet.
