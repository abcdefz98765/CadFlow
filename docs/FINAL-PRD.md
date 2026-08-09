# FINAL PRD: CadFlow Agent CAD Workbench

Status date: 2026-08-09.

Status: target product baseline. Capability claims must follow `docs/status/current-product-readiness.md`.

## 1. Product direction

CadFlow is an Agent-first CAD design workbench.

A user should be able to describe what they want to design, let an Agent understand/decompose the task, see the proposed design and generated geometry, understand validation/recovery, revise the design, and explicitly accept useful results.

CadFlow supplies the product boundaries around that collaboration:

- durable Work / Part Job / Run state;
- controlled CAD execution;
- geometry inspection and honest validation;
- revision lineage;
- explicit review/acceptance;
- a clear visual Workflow of what happened and what can happen next.

The Agent is the design collaborator. CadFlow should not replace design freedom with a fixed template catalogue or fixed workflow script.

## 2. Product promise

For a normal Work, the user should be able to:

1. describe the intended design/change in natural language;
2. see how the Agent interprets and, when needed, decomposes the task;
3. answer only material questions;
4. let the Agent create/build/inspect/repair design candidates;
5. see generated geometry and meaningful validation/limitations;
6. understand the Work through a dynamic state graph;
7. inspect Part Jobs, attempts, failures, recovery, reviewable results, and accepted results;
8. revise from an earlier result without losing history;
9. explicitly accept a result;
10. later continue into multi-Part Assembly or Deliverables when those capabilities are actually implemented.

The default product experience is an understandable design Work, not a template wizard, artifact browser, developer console, or mandatory chain of approval screens.

## 3. Product objects

### Workspace

Local container for configuration and Works.

### Work

One mutable user-facing engineering objective. It owns/references current intent, Part Jobs, Runs/lineage, optional Assembly/Deliverables, accepted-result pointers, unresolved decisions, and the recommended next action.

### Run

One append-only attempt and audit record. Historical Run evidence is immutable.

### Part Job

One intended part inside a Work. It owns multiple attempt Run references, relevant interfaces/context, reviewable results, and one explicit accepted-result pointer or none.

### Assembly Job

Optional later Work object that consumes exact accepted part results when Assembly capability exists.

### Deliverable Package

Optional later package derived only from accepted results when Deliverable capability exists.

## 4. Workflow: live Work state graph

Workflow is a core product concept.

It is not an execution script for the Agent.

It is a live visual projection of durable Work state, including as applicable:

- user request/intent;
- Agent design/decomposition;
- Part Jobs;
- attempts and revision branches;
- focused questions and user answers;
- candidate/build/validation outcomes;
- repair/recovery points;
- reviewable results;
- accepted results;
- stale/dependent state;
- later Assembly/Deliverable states when real capability exists.

Workflow lets the user answer:

- Where did this Work start?
- What has happened?
- Which Parts/attempts/results exist?
- Why is something blocked?
- Where did a revision branch?
- What is accepted?
- What can I do next?

The graph is derived from existing Work/Part Job/Run/result evidence. It does not require a second workflow engine, graph database, BPMN layer, or separate graph-owned business state.

Selecting a graph state inspects the existing associated detail. Starting again from an earlier state creates a new revision/child Run rather than destructively rolling back history.

## 5. Four product phases

CadFlow uses four stable user-facing semantic regions:

```text
Intent
Design
Build & Evaluate
Accept & Deliver
```

These are orientation/grouping for the Work and Workflow graph. They are not four mandatory pages and are not the complete Workflow node list.

A Work may move non-linearly between them.

### Intent

Capture the goal and material constraints. Ask only questions that significantly change design, interfaces, risk, or requested output.

### Design

The Agent may understand/decompose the goal, create Part Jobs, propose design strategies, define relevant parameters/interfaces, create/patch geometry candidates, ask the user, or change strategy after observations.

### Build & Evaluate

CadFlow executes allowed candidates through controlled CAD tooling, generates geometry, measures/inspects results, and returns observations. The Agent may repair/retry within practical bounds.

### Accept & Deliver

The user reviews a validated reviewable result and explicitly accepts or revises it. Later implemented capabilities may continue from accepted results to Assembly or Deliverables.

## 6. Overview / Design experience

The primary Work page answers:

- What did I ask for?
- What is the Agent designing?
- What is happening now?
- What geometry/result exists?
- What is verified/assumed/unverified?
- Do I need to answer/review anything?
- What should happen next?

Key user-facing projections include:

- Your Request;
- Agent Design;
- Agent Activity;
- readable Agent Output for useful debugging/recovery;
- geometry preview;
- validation/limitations;
- Part Job/result summary;
- compact current Workflow state and entry into full Workflow.

Overview and Workflow must derive from the same domain state and must not contradict each other.

## 7. Agent behavior

A bounded Agent Episode may choose useful declared actions such as:

- request relevant context;
- ask the user;
- propose/decompose design;
- create/patch a structured geometry candidate;
- create/patch a controlled CAD model program;
- request execution;
- inspect observations;
- repair/change strategy;
- stop with a meaningful reason.

The Agent controls design strategy inside its allowed capability boundary.

CadFlow controls durable Work mutation and model-generated side effects.

Persist enough explicit Agent/user/validator evidence to explain and debug the Work. Do not persist/display hidden chain-of-thought or credentials.

## 8. CAD execution

CadFlow may support more than one candidate representation.

Current/near-term useful paths include:

- structured geometry contracts where implemented;
- controlled sandboxed model programs for broader design freedom.

Both converge on:

```text
candidate
  -> controlled execution
  -> geometry inspection
  -> validation
  -> reviewable result or typed block
```

A candidate that executes successfully is not automatically reviewable or accepted.

A large general Feature Graph is a possible later capability when real use demonstrates a need for more stable structured editing/interoperability. It is not automatically the next framework to build.

## 9. Trust, lineage, and acceptance

Hard product invariants:

- Current Work is actionable; historical Run Snapshot is read-only.
- Active design lineage and accepted results are distinct.
- File presence is not business status.
- Failed/unvalidated candidate output cannot become a trusted reviewable result.
- Reviewable is not accepted.
- Only explicit user acceptance changes accepted-result pointers.
- Starting a revision preserves previous accepted/history evidence.
- Engineering claims are limited to checks that actually ran.
- Credentials and unrestricted host authority are not exposed to model-generated code.

The trust boundary should remain as small as practical. Once these invariants are satisfied, additional security/audit layers require a concrete threat, defect, or new capability need.

## 10. Recovery

A stopped Work should explain:

- what happened;
- why it stopped this time;
- what had already succeeded;
- the last meaningful Agent action/observation when useful;
- whether the user, configuration, CadFlow, environment, or unsupported capability owns the resolution;
- the recommended next action.

Clarification answers and recovery history remain inspectable after execution resumes.

## 11. Part and revision progression

A typical Part Job progresses conceptually as:

```text
Part Job
  -> one or more design/build attempts
  -> validated reviewable result
  -> explicit accepted result
  -> later revision or Assembly input
```

Attempts are Runs.

Revision creates new lineage rather than editing old evidence.

## 12. Multi-Part and Assembly direction

CadFlow may support multi-Part Works and Assembly, but this must grow from real product workflows.

When intentionally implemented:

- the Agent may decompose a Work into real Part Jobs;
- Workflow shows those Part Jobs as branches;
- accepted part results become exact inputs to an Assembly Job;
- Assembly results have their own attempts, validation, reviewable/accepted state.

Do not fabricate Assembly state or pre-build a general assembly platform before validated use cases require it.

## 13. Deliverable direction

Later validated workflows may need:

- accepted part STEP;
- accepted assembly output;
- BOM;
- drawings;
- concise design/validation reports.

Implement these incrementally from real accepted-result workflows. Do not make a full engineering package a prerequisite for the current Agent design loop.

## 14. Product development discipline

CadFlow should be developed from real use, not speculative platform completeness.

Rules:

1. Close the current user workflow before expanding the framework.
2. Reuse existing libraries/components/domain objects where adequate.
3. Do not create a second state/workflow system when Work/Run/Part Job already owns the truth.
4. Do not introduce graph databases/BPMN/workflow DSLs merely to visualize Workflow.
5. Do not add more sandbox/security/attestation/audit layers without a demonstrated gap.
6. Do not expose safety/evidence internals as the main product experience.
7. Do not pre-build Feature Graph, Assembly, Deliverables, Release assurance, cloud, multi-user, or enterprise infrastructure before its milestone is justified by real usage.
8. Use real Provider/Agent failure modes to decide which modeling capability to build next.
9. Prefer a usable end-to-end Work over a theoretically complete architecture.

Future capability is allowed; speculative implementation is not required.

## 15. Current product acceptance sequence

The current sequence is:

```text
implemented Agentic backend foundation
-> usable Workbench/onboarding/recovery
-> Dynamic Work Graph
-> real external-provider product trial
-> decide next modeling capability from evidence
-> later multi-Part / Assembly
-> later Deliverables
```

The real-provider product trial should be evaluated through real Works, Workflow, Agent Output, geometry, validation, and explicit user review—not only offline benchmark files.

## 16. Non-goals for the current correction

The current correction does not require:

- production-ready arbitrary CAD;
- a generic workflow/orchestration platform;
- a graph database or BPMN engine;
- a full structured Feature Graph;
- new CAD families just for demonstration;
- Assembly execution;
- BOM/drawing/Deliverable generation;
- release-grade engineering sign-off;
- public cloud or multi-user operation;
- additional sandbox/security layers without a demonstrated defect.

The immediate goal is to make the existing Agent/CAD capabilities understandable and controllable as one coherent Work.
