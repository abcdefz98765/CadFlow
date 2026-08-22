# CadFlow Canonical Product Architecture

## Status and authority

This document is the canonical target architecture for CadFlow.

Status date: 2026-08-09.

Implementation status belongs in:

- `../status/current-product-readiness.md`
- `../roadmap/milestones.md`
- `../tasks/task-board.md`

No implementation, test fixture, legacy document, UI layout, or example may silently redefine this architecture.

## Product objective

CadFlow is an Agent-first CAD design workbench.

The user describes an engineering goal. The Agent helps understand and decompose it, proposes and builds geometry, observes validation feedback, asks the user when needed, and iterates. CadFlow owns durable Work state, controlled execution, validation, lineage, and explicit acceptance.

The product should maximize useful design freedom while keeping a small number of hard boundaries:

- model-generated side effects remain controlled;
- credentials and unrelated local data are not exposed;
- failed or unvalidated output is not presented as accepted product state;
- historical Run evidence is not silently rewritten;
- only explicit user action changes accepted-result pointers;
- engineering claims are limited to checks that actually ran.

These boundaries support the design workflow. They are not the product itself.

## Canonical product objects

### Workspace

A Workspace is the local container for:

- Works;
- safe local configuration;
- provider/runtime readiness;
- optional examples and operational metadata.

### Work

A Work is one mutable user-facing engineering objective.

It owns or references:

- title, description, and current intent;
- active design lineage;
- all associated Runs;
- Part Jobs;
- optional Assembly Job;
- accepted part-result pointers;
- optional accepted assembly-result pointer;
- optional Deliverable Packages;
- assumptions, unresolved decisions, and current recommendation.

The Work is the main product state.

### Run

A Run is one append-only attempt and audit record.

A Run may contain:

- the prompt or revision request that initiated it;
- bounded Agent Episodes;
- candidate proposals and source;
- execution/validator observations;
- geometry and reports;
- parent/child lineage;
- user/Agent interaction evidence required to understand or resume the attempt.

Historical Run evidence is immutable. A failed Run remains inspectable.

### Part Job

A Part Job is the Work-level identity of one intended part.

It owns:

- stable part identity, role, and purpose;
- interfaces and relevant assembly context;
- accepted constraints and assumptions;
- ordered attempt Run references;
- reviewable results;
- one accepted-result pointer or none.

Creating or revising an attempt does not accept it.

### Assembly Job

Assembly Job is an optional later Work-level object. It consumes exact accepted part results and owns assembly attempts/results when assembly capability exists.

Do not fabricate Assembly state for a Work whose runtime has not actually created or executed an Assembly Job.

### Deliverable Package

Deliverable Package is an optional versioned product artifact derived from accepted results when deliverable capability exists.

It must not contain failed or merely reviewable candidates as final accepted outputs.

## Lineage and acceptance

### Active design lineage

Active lineage identifies the attempt path currently being advanced.

### Accepted results

Accepted pointers identify user-approved results and are independent of active lineage.

Therefore:

- the accepted result does not have to be the active-lineage leaf;
- starting a revision does not remove the previous accepted result;
- accepting a result does not rewrite historical Runs;
- only explicit user acceptance changes accepted-result pointers.

### Current Work and Run Snapshot

Current Work is actionable.

Run Snapshot is read-only historical evidence. It may offer an explicit action such as `Start Revision`, which creates a new child Run; it never edits the historical Run in place.

## Canonical Workflow: dynamic Work state graph

Workflow is a first-class product view of the Work.

It is **not** a script the Agent must execute and it is **not** a fixed list of required screens.

Workflow is a live graph projected from durable domain state. It helps the user understand:

- what the Work started from;
- what the Agent decided or asked;
- which Part Jobs exist;
- which attempts were made;
- where build/validation succeeded or failed;
- which results are reviewable or accepted;
- where revision branches occurred;
- what is currently blocked or waiting;
- what transitions are currently available;
- later, where Assembly or Deliverables depend on accepted inputs.

### Workflow is a projection, not a second engine

The source of truth remains existing domain state:

- Work manifest;
- Part Jobs;
- Runs and parent/child lineage;
- accepted pointers;
- artifact references/checkpoints;
- persisted Agent/user decisions and observations.

Do not introduce graph-specific business state merely to render the graph.

Do not build a second workflow engine, graph database, BPMN system, or generic workflow DSL unless a concrete future requirement cannot be met by the existing domain model.

Workflow is also the primary command surface for valid user-driven progress and
revision. The interaction dependency is strictly one-way:

```text
Domain State -> Workflow Projection -> Node Interaction Projection
             -> existing domain/orchestrator command -> re-projected Domain State
```

The graph projects which existing commands are valid; it does not own or
execute business transitions itself. Selected nodes, available buttons, graph
layout, and **Current Attention** are presentation state and are never persisted
as Work state. Current Attention may contain several nodes when parallel Part
Jobs simultaneously need input, review, or continued work.

### Four phases are graph grouping, not four nodes

The user-facing phases remain:

```text
Intent -> Design -> Build & Evaluate -> Accept & Deliver
```

They are stable semantic regions/orientation for the Work.

They may be rendered as labels, lanes, backgrounds, or a compact orientation indicator around the Workflow graph.

They are not the complete graph and must not reduce Workflow to four dots.

A Work may move between regions non-linearly:

- Build observation can return a Part Job to Design;
- clarification can pause and resume Design;
- one Part Job may be reviewable while another is still in Design;
- revision may branch from an older accepted/reviewable result;
- Assembly may wait for several accepted Part Jobs.

### Graph nodes

Use only nodes that help the user understand a durable state, decision, result, or recovery point.

Typical semantic nodes include:

- user intent/request;
- focused clarification / user answer;
- design decision or decomposition;
- Part Job;
- attempt / revision branch;
- meaningful candidate/build state;
- validation failure / recovery point;
- reviewable result;
- accepted result;
- Assembly Job/result when implemented;
- Deliverable Package when implemented.

Do not render every model turn, context read, provider request, log line, or tool invocation as a Workflow node. Those belong in Agent Output/Advanced evidence.

### Graph edges

Edges express meaningful state transitions such as:

- created;
- decomposed;
- asked / answered;
- generated;
- validated / failed;
- repaired;
- published reviewable;
- accepted;
- revised;
- superseded/stale;
- assembled.

The exact edge vocabulary should stay small and emerge from real product behavior.

### Dynamic complexity

The graph adapts to the Work instead of forcing every Work into the same topology.

A simple single-part Work should stay simple.

A multi-Part Work may branch only after the Agent/runtime actually creates Part Jobs.

Assembly/Deliverable branches appear only after those capabilities and domain objects actually exist.

The UI must never create fake progress or fake future nodes to make the graph look complete.

### Graph interaction

Selecting a node should inspect the existing associated state/evidence:

- user input;
- Agent Design/Output;
- Part Job/attempt;
- geometry;
- validation;
- result;
- recovery details;
- historical Run Snapshot.

A graph node selection is interaction state, not business state. Its normal
detail surface explains the state, why it matters, whether the user must act,
one dominant valid action when applicable, relevant result/evidence, and why an
expected action is unavailable.

Starting from an earlier node is offered only where an existing domain command
has durable provenance. It is a branch/revision operation that creates new
immutable lineage, preserves prior evidence and accepted pointers, and is not
destructive rollback. Other historical nodes remain inspection-only.

## Overview and Workflow

Overview and Workflow are complementary first-class views over the same Work.

### Overview / Design

Answers:

- what are we designing now;
- what did the user ask;
- what is the Agent proposing/doing;
- what geometry/result exists;
- what validation matters;
- what should the user do next.

### Workflow

Answers:

- how did the Work get here;
- which Parts/attempts/results exist;
- what is blocked, waiting, reviewable, accepted, or stale;
- where did revisions branch;
- what transitions are available next.

The two views must never contradict each other because both derive from the same domain state.

## User-facing design loop

### Intent

Capture the user goal and material constraints. Ask only questions that materially affect the design or requested assurance.

### Design

The Agent may:

- understand/decompose the goal;
- create Part Jobs when decomposition is needed;
- propose and compare design strategies;
- define interfaces and relevant parameters;
- create or patch executable geometry candidates;
- ask the user;
- change strategy after observations;
- stop with a meaningful reason.

The system must not force the Agent through a fixed template catalogue or fixed stage sequence.

The implemented normal entry expresses this as a Work-scoped Design Episode
before Part Jobs. The provider proposes the concept, generated/reference
component distinction, interfaces, and decomposition; CadFlow validates the
proposal and owns identity assignment and manifest mutation. Only then do
Part-scoped Design Episodes operate on the resulting Part Jobs. This is one
live Work state graph, not a second planning workflow.

### Build & Evaluate

CadFlow executes allowed candidates through the existing controlled execution boundary, generates geometry, measures/inspects it, and returns observations to the Agent.

The Agent may repair/retry within practical budgets.

### Accept & Deliver

The user reviews a result and explicitly accepts or revises it.

Acceptance changes only the relevant accepted pointer.

Later capabilities may continue from accepted parts into Assembly or Deliverables.

## Internal checkpoints and Agent events

Internal checkpoints exist only when they establish a durable decision, trust boundary, result, or recovery point.

Useful examples include:

- intent snapshot;
- clarification decision;
- design brief/decomposition;
- Part Job definition;
- geometry candidate;
- validation observation;
- reviewable result;
- acceptance decision;
- later Assembly/Deliverable results.

A provider call, context request, repair turn, or tool invocation is normally an Agent Episode event, not automatically a user-facing Workflow node.

Persist enough external Agent/user/validator evidence to explain behavior and debug failures, but never private chain-of-thought or credentials.

## CAD candidate paths

CadFlow may use whichever implemented path best serves the design:

- structured geometry contract where useful and supported;
- sandboxed model program using an allowlisted CAD API for broader Agent freedom.

Both converge on the same product boundary:

```text
candidate
  -> controlled execution
  -> geometry inspection
  -> validation
  -> reviewable result or typed block
```

A future general Feature Graph is optional capability work. It should be expanded only when real usage shows that structured editing/interoperability needs justify it. It is not a prerequisite for every current design.

## Trust boundary

Keep the trust model small and explicit:

- model-generated code does not receive unrestricted host authority;
- credentials are not exposed to model context or persisted Work evidence;
- failed/unvalidated candidate output cannot become a trusted reviewable result;
- reviewable does not mean accepted;
- history is immutable;
- engineering claims match actual checks.

Do not keep adding security, attestation, policy, evidence, or identity layers after these requirements are already satisfied unless a concrete threat, defect, or new capability requires them.

Security infrastructure should be largely invisible to normal users and remain under Advanced/Diagnostics when inspectable.

## Development discipline / avoid over-engineering

CadFlow should evolve from real user workflows and observed Agent failures, not from speculative platform design.

Rules:

1. Build the smallest capability that closes the current user loop.
2. Reuse existing open-source libraries, NiceGUI components, CAD tools, and domain objects when adequate.
3. Do not generalize a one-provider/one-runtime problem into a large provider framework without demonstrated need.
4. Do not generalize Workflow into a generic orchestration platform. Work/Run/Part Job remain the product state model.
5. Do not create new persistence objects when the existing domain state can express the fact.
6. Do not add more audit/safety layers without a concrete gap.
7. Do not let internal safety/evidence machinery dominate product UI or roadmap.
8. Do not implement Assembly, Deliverables, Release assurance, cloud/multi-user permissions, or enterprise workflow infrastructure ahead of validated product need.
9. Do not pre-build a large Feature Graph merely because it is a plausible future architecture; use real Agent/modeling failures to choose its scope.
10. Prefer a usable end-to-end Work over a theoretically complete framework.

Future capability is allowed. Premature capability is not a requirement.

## Current migration rule

Legacy fixed Workflow evidence and deterministic paths remain readable for compatibility.

They do not define the target product.

Every loaded Work must expose its state authority. Schema-v2 Works created by
the current product are `canonical`; explicitly imported, migrated, or
deterministic compatibility Works are `compatibility`. Normal Current Work may
derive presentation only from the canonical Work manifest, Part Jobs, accepted
pointers, and registered artifact references. It must not call a compatibility
projector as a fallback, infer active lineage from directory order or
timestamps, or infer product state from filenames. Compatibility projection is
allowed only after the Work has been classified as compatibility data and must
not mutate historical evidence.

The target Workflow is the dynamic Work graph described above. Existing graph/rendering/navigation components should be reused where possible rather than discarded.

Current implementation gaps belong in readiness/task documents, not in this canonical contract.

## Architecture change protocol

A real architecture change must state:

- affected canonical object(s);
- affected user phase / graph state;
- input and output;
- Agent freedom added/removed;
- side-effect/trust boundary change;
- lineage impact;
- visible user success/failure.

Do not treat a layout change, graph projection improvement, new copy, or reuse of existing evidence as a canonical architecture change.

## Required implementation self-check

Before reporting product work complete, answer:

- What user workflow became easier or newly possible?
- Which existing Work/Part Job/Run/result state is the source of truth?
- Does Workflow visualize real state instead of fabricated progress?
- Did the change add any parallel state/workflow infrastructure that can be avoided?
- What design choice remains with the Agent?
- What side effect remains controlled by CadFlow?
- Are failed/unaccepted outputs kept out of accepted product state?
- Is history preserved?
- Were any new security/framework abstractions actually necessary?
- What remains intentionally unimplemented?
