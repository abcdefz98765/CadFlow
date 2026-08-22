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

- [x] Inventory the existing target Agent-first Workflow projection and legacy Workflow graph renderer.
- [x] Document which existing graph/layout/selection/detail components can be reused as-is.
- [x] Identify the exact reason the current Agent-first projection collapses to four phase nodes.
- [x] Confirm the current sources of truth for:
  - Work intent;
  - Part Jobs;
  - attempts/Run lineage;
  - clarification question/answer;
  - Agent design/output;
  - validation/recovery;
  - reviewable results;
  - accepted pointers.
- [x] Identify any required graph fact that genuinely cannot be derived from existing durable evidence before adding new persistence.

### Projection

- [x] Replace the four-node Agent-first Workflow projection with a dynamic Work graph projection.
- [x] Keep Intent / Design / Build & Evaluate / Accept & Deliver as graph grouping/orientation, not the whole graph.
- [x] Use a deliberately small semantic node vocabulary for current behavior.
- [x] Use a deliberately small edge/transition vocabulary derived from real state.
- [x] Do not render provider turns/tool calls/log events as Workflow nodes.
- [x] Preserve existing compatibility Workflow projection for legacy Runs where appropriate.

### Single-Part user flows

- [x] New/ready-to-design Work shows a clear beginning state.
- [x] Agent design evidence appears without fabricating future checkpoints.
- [x] Clarification appears as a meaningful branch/state and the submitted answer remains visible.
- [x] Resume after clarification updates the same Work graph.
- [x] Build/validation failure or typed stop shows where/why execution stopped.
- [x] Repair/retry appears only when it actually occurred.
- [x] Reviewable result is visually distinct from accepted result.
- [x] Accept updates graph state only after persisted accepted pointer verification.
- [x] Revision creates a new branch/attempt while preserving the previous branch/result.

### Part Jobs / branching

- [x] Existing multiple Part Jobs render as real branches rather than a flat list when Work state contains them.
- [x] Part branches show current attempt/result/attention state without inventing unsupported steps.
- [x] Selecting a Part/result node reuses existing Workbench/Parts/geometry/result detail.
- [x] Accepted Part state remains independent of active attempt state.

Do not implement new Agent multi-Part decomposition merely to make this graph look more impressive. The graph should be ready to display real decomposition when the runtime creates it later.

### Node interaction and revision

- [x] Clicking a node selects detail without mutating business state.
- [x] Historical attempt/result nodes can navigate to existing read-only Run Snapshot/evidence.
- [x] Where valid, provide `Start Revision from here` using existing child-Run/attempt semantics.
- [x] Never delete or rewrite downstream historical evidence to simulate rollback.

### Overview consistency

- [x] Overview and Workflow derive from the same current Work state.
- [x] Current phase/status/recovery/result shown in Overview agrees with graph state.
- [x] No state such as `Ready for review` may coexist with a contradictory `Design not started` graph unless the user is explicitly viewing a historical Run.

### UX / visual design

- [x] Reuse the current dot graph visual vocabulary rather than building a new graph framework.
- [x] Make active/blocked/reviewable/accepted/revision branches understandable at a glance.
- [x] Use progressive disclosure so simple Works stay visually simple.
- [x] Make selected node detail useful without duplicating the entire Overview.
- [x] Keep Agent Output / technical evidence inspectable but out of the primary graph.
- [x] Preserve Chinese/English support.
- [x] Verify desktop, 1024px, and mobile behavior.

### Browser acceptance

Manually verify at least:

- [x] beginning-state Real Agent Example;
- [x] clarification -> answer -> resumed Work;
- [x] typed failure/block with real reason;
- [x] reviewable Product Golden state;
- [x] accepted result;
- [x] revision branch preserving prior accepted state;
- [x] a Work containing more than one Part Job if existing fixture/evidence provides one;
- [x] node -> detail navigation;
- [x] node -> Run Snapshot -> Current Work navigation;
- [x] Chinese critical path;
- [x] 1440px / 1024px / 390–430px.

### Tests

- [x] Graph state comes from domain/evidence rather than browser-owned business state.
- [x] Four phases are grouping metadata, not the complete graph node list.
- [x] Clarification/answer history projects correctly.
- [x] Reviewable/accepted are distinct.
- [x] Revision produces a branch and preserves history.
- [x] Multi-Part branch projection works on existing real fixture/domain state.
- [x] Overview/Workflow consistency contracts.
- [x] Run Snapshot remains read-only.
- [x] No graph database/workflow engine/parallel persistence introduced.
- [x] Full relevant regression remains green.

### M2.8 explicit non-goals

Do not add during this milestone unless a demonstrated bug makes it unavoidable:

- [x] no new sandbox/security/attestation architecture;
- [x] no new Provider abstraction layer;
- [x] no graph DB;
- [x] no BPMN/workflow DSL;
- [x] no graph-specific durable state model;
- [x] no Feature Graph CAD implementation;
- [x] no new CAD families for the sake of the demo;
- [x] no new Assembly execution;
- [x] no Deliverable/BOM/drawing implementation;
- [x] no formal five-case external-provider benchmark.

Status: complete on 2026-08-09. The graph is a read-only presentation
projection. The only domain extension is optional Part-attempt revision
provenance (`parent_run_id` and `source_result_id`), added because revision
causality cannot be inferred safely from prompts, ordering, or timestamps.
The current product entry remains Part-first after Work creation; Work-level
Agent decomposition is still an explicit runtime/product debt for later
evidence-driven work, not hidden behind legacy planning.

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
