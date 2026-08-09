# CadFlow Target Milestones

Status date: 2026-08-09.

This roadmap implements `docs/FINAL-PRD.md` and the canonical architecture.

Detailed historical package evidence remains in Git history and status/acceptance records. This roadmap intentionally stays product-oriented.

## Sequencing principles

1. Turn implemented backend capability into a clear user workflow before expanding backend breadth.
2. Treat Workflow as a dynamic projection of Work/Part Job/Run/result state, not a fixed script.
3. Constrain unsafe side effects and false publication, not useful Agent design choices.
4. Prefer the smallest implementation that closes a real user loop.
5. Do not generalize one current problem into a platform/framework without demonstrated need.
6. Do not add security/audit layers after the existing trust boundary is sufficient unless a concrete gap requires them.
7. Let real Agent failures and user experience decide whether Feature Graph, additional runtime abstraction, or other architecture expansion is necessary.
8. Do not implement Assembly/Deliverables before Part Job workflows are clear and actually usable.
9. Reuse existing NiceGUI, CAD, Workflow graph, viewer, action lifecycle, and open-source tooling wherever adequate.

Current delivery order:

```text
M1 runtime/domain foundation               complete
M2 backend Agentic vertical slice          implemented, formal acceptance pending
M2.5 Workbench MVP                         complete
M2.6 Product Golden / design story         complete
M2.7 onboarding / Settings / recovery      complete
M2.8 Dynamic Work Graph                    NEXT
M2 external-provider product trial         after M2.8
M3 capability-expansion decision           evidence-driven
M4 multi-Part / Assembly                   later
M5 Deliverables                            later
```

## M0 — Architecture correction

Goal:

- establish Agent-first Work/Run/Part Job/acceptance architecture;
- remove the former fixed-stage product requirement.

Status: complete.

## M1 — Runtime/domain foundation

Goal:

- establish reliable Work, Run, Part Job, lineage, artifact-reference, and explicit-acceptance foundations.

Key accepted behavior:

- Part Jobs own ordered attempts;
- historical Runs are immutable;
- active lineage and accepted results are separate;
- Work mutations route through the product orchestrator;
- legacy deterministic paths remain compatibility evidence.

Status: complete for deterministic/domain foundation.

## M2 — First real Agentic design vertical slice

Goal:

- prove a real Provider can design, execute, observe, repair, ask the user, and produce a locally validated reviewable CAD result through controlled execution.

Implemented foundation:

- bounded provider-selected Agent Episode;
- semantic context access;
- controlled CadQuery model-program execution;
- geometry/STEP inspection;
- reviewable publication boundary;
- explicit Accept and Revise;
- Agent Output/recovery evidence;
- Provider Settings and local readiness.

Formal acceptance still requires:

- at least five genuinely non-template real-provider design cases;
- at least two observation-driven repairs;
- at least one genuine focused user clarification;
- user review/acceptance of at least one resulting reviewable result;
- honest recording of failures and unsupported cases.

Do not add more sandbox/policy/attestation architecture merely to prepare for this trial unless the trial exposes an actual security or execution defect.

Status: implemented but formal external-provider acceptance pending.

## M2.5 — Reuse-first Workbench MVP

Goal:

- make existing single-Part deterministic/Agentic state understandable and operable through the existing NiceGUI UI.

Status: complete.

## M2.6 — Product Golden / guided design story

Goal:

- make request -> Agent design -> geometry -> validation -> review/revision understandable without internal artifact vocabulary.

Status: complete.

## M2.7 — Onboarding, Settings, recovery, and Agent observability

Goal:

- make starting a design, Provider readiness, Product Examples, clarification/recovery, and Agent Output understandable.

Implemented:

- Home / Works / Settings product surfaces;
- Real Agent and Completed Product Example separation;
- developer-fixture visibility separation;
- session/environment/project `.env` credential discovery without secret persistence;
- readable sanitized Agent Output;
- clarification answer/resume history;
- typed recovery guidance.

Status: complete and merged to `main` on 2026-08-09.

## M2.8 — Dynamic Work Graph

### Why this milestone exists

The current Agent-first Workflow projection became too flat: the four canonical phases are being used like the graph itself. This makes it hard to understand Part Jobs, attempts, clarification, failure/repair, reviewable results, revision branches, and future multi-Part progression.

The correction is not a new workflow engine. It is a better projection of the domain model that already exists.

### Goal

Make Workflow the clear live map of a Work while keeping Overview as the “what matters now” view.

### Scope

- reuse the existing NiceGUI Workflow/dot graph renderer and interactions;
- build one dynamic graph projection from Work manifest, Part Jobs, Runs/lineage, artifact references, persisted Agent/user decisions, validation/recovery state, and accepted pointers;
- use Intent / Design / Build & Evaluate / Accept & Deliver as graph grouping/orientation, not as four graph nodes;
- represent current single-Part Works clearly;
- support real Part Job branching when multiple Part Jobs already exist;
- show clarification/answer, attempt/revision branch, meaningful failure/repair, reviewable, accepted, blocked/stale states when real evidence exists;
- make graph nodes selectable and reuse existing detail/viewer/Run Snapshot surfaces;
- support `Start Revision from here` through existing child-Run semantics where the selected state can legitimately seed revision;
- keep Agent turn/tool/provider detail under Agent Output/Advanced instead of graph nodes;
- keep legacy compatibility Workflow readable without forcing it into the new target projection.

### Explicit non-goals

Do not build:

- a second workflow/state engine;
- graph-specific persistence;
- graph database;
- BPMN/workflow DSL;
- configurable generic node framework;
- new security/attestation/policy layers;
- Feature Graph CAD capability;
- new CAD families;
- Assembly execution;
- Deliverable generation;
- formal external-provider benchmark logic.

### Acceptance

For real browser Works, the user can answer in a few seconds:

- where did this Work start;
- what is happening now;
- which Part/attempt/result is active;
- what was asked/answered;
- where a failure/repair/revision occurred;
- which result is reviewable/accepted;
- what is blocked/waiting;
- what can be done next.

Required scenarios:

1. beginning-state Live Agent Work;
2. clarification -> answer -> resume;
3. build/validation failure or typed stop;
4. reviewable result;
5. accepted result;
6. revision branch preserving the prior result;
7. existing multi-Part compatibility/example state without fabricating unsupported Assembly behavior;
8. Run Snapshot navigation/read-only behavior;
9. Chinese/English desktop, 1024px, and mobile acceptance.

Overview and Workflow must agree because both derive from the same domain state.

### Implementation discipline

Start with the minimum node/edge vocabulary required by the scenarios above.

Do not design the final graph schema for all future Assembly/Deliverable capabilities.

If the existing domain state cannot express one required graph fact, identify that exact gap before adding any durable field.

## M2 external-provider product trial and acceptance

After M2.8, use the real Workbench and Dynamic Work Graph to run the formal Provider trial.

The trial should happen through real Works and be inspected through the product UI, not only through offline benchmark JSON.

Use the results to decide what modeling/runtime capability should be developed next.

## M3 — Capability expansion decision

M3 is deliberately not pre-committed to a large Feature Graph implementation.

After the real-provider trial, classify actual failure modes:

- model-program generation/repair limitations;
- structured-edit/revision limitations;
- missing CAD operations;
- context/interface problems;
- UI/workflow problems;
- Provider quality problems.

Then choose the smallest useful next capability.

A structured Feature Graph is one possible direction when stable parametric editing/interoperability justifies it. It is not automatically the next large framework.

## M4 — Multi-Part and Assembly

Begin only after single-Part Agent design/revision and Workflow are genuinely usable.

Goals may include:

- Agent-driven decomposition into real Part Jobs;
- accepted-part dependency visualization;
- Assembly Job creation from exact accepted inputs;
- placement/constraint execution and honest validation;
- assembly result review/acceptance.

Do not pre-build a general assembly solver before concrete use cases require it.

## M5 — Deliverables

Begin only after accepted part/assembly flows are stable.

Potential outputs:

- accepted STEP files;
- assembly output;
- BOM;
- drawings;
- reports.

Only implement the deliverables actually needed by validated use cases.

## Roadmap change rule

A new milestone or major framework must answer:

- What current user problem does it solve?
- What real Work state/capability is missing?
- Why can the current architecture not solve it with a smaller change?
- What visible product behavior proves completion?

Do not promote infrastructure work to a milestone merely because it is technically interesting.
