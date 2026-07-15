# CadFlow Canonical Product Architecture

## Status and authority

This document is the canonical product-architecture baseline for CadFlow.

It defines:

- the Workspace / Work / Run object model;
- the user-facing workflow checkpoints;
- the responsibility of each stage;
- the relationship between agent reasoning, deterministic execution, artifacts, reviews, and lineage;
- the boundaries that UI and implementation changes must preserve.

When another document, implementation shortcut, test fixture, or UI layout conflicts with this document, do not silently invent a new interpretation. Resolve the conflict explicitly and update this document, the relevant contracts, migrations, tests, roadmap, and readiness status together.

## Product objective

CadFlow turns a natural-language engineering request into reviewable, traceable CAD results.

The product is not merely:

- a text-to-template lookup;
- a raw artifact browser;
- a fixed linear script;
- a browser CAD editor;
- an unbounded autonomous coding agent.

The intended product loop is:

    user intent
      -> structured engineering understanding
      -> design and assembly planning
      -> selected part or assembly task
      -> agent-proposed structured CAD contract
      -> deterministic validation and CAD execution
      -> user review and acceptance
      -> revision or rework when needed

The natural-language experience may become conversational and agentic, but all trusted results remain represented by structured contracts, artifacts, reviews, and lineage.

## Canonical object model

### Workspace

A Workspace is the local product container.

It owns:

- workspace configuration;
- the Work index;
- provider/model/runtime settings that are safe to persist;
- workspace-scoped run storage;
- product examples and local operational metadata.

A Workspace is not one design task and is not one execution attempt.

Canonical relationship:

    Workspace
      -> many Works
      -> workspace configuration
      -> run storage and indexes

### Work

A Work is one mutable, user-visible engineering task or project.

Examples:

- design a desktop robot arm;
- revise an enclosure;
- generate and review one mounting bracket;
- continue a multi-part product design across several attempts.

A Work owns or references:

- title, description, and current product intent;
- root and active-lineage pointers;
- all Runs associated with the task;
- Part Jobs;
- candidate-selection state and versioned user overrides;
- accepted part-result pointers;
- current review state and recommended next action;
- product-level status and readiness summaries.

A Work is mutable because the user may:

- clarify a requirement;
- select another candidate;
- approve a result;
- request revision;
- create a rework attempt;
- choose which result is currently accepted.

Work state must never rewrite historical execution evidence.

### Run

A Run is one append-only execution attempt and audit record.

A Run contains or references:

- the prompt or revision request that started the attempt;
- structured stage artifacts;
- agent episode records;
- validator observations;
- deterministic CAD outputs;
- reports and review evidence;
- parent/child lineage metadata.

Run rules:

- existing execution artifacts are never edited in place;
- user edits are stored as versioned override artifacts, not replacements of originals;
- review records are append-only;
- an alternate execution or rework attempt creates a new Run;
- a Run Snapshot is read-only in the UI;
- `latest attempt` is audit information and does not automatically become the accepted or active result.

### Part Job

A Part Job is the Work-level task for one intended part.

A Part Job may have:

- a part id and engineering role;
- preserved assembly context;
- multiple candidate concepts;
- multiple child Runs or attempts;
- one currently accepted result pointer;
- no accepted result yet.

Part Jobs allow future multi-part Works to have sibling accepted results without forcing every accepted part to be the single active-lineage leaf.

### Canonical relationship

    Workspace
      -> Work A
           -> root Run
           -> active workflow / rework lineage
           -> Part Job: upper_link
                -> child Run attempt 1
                -> child Run attempt 2
                -> accepted result pointer
           -> Part Job: lower_link
                -> child Runs
                -> accepted result pointer
           -> Work-level reviews and deliverables
      -> Work B
           -> its own Runs and Part Jobs

## Active lineage and accepted results

These are distinct concepts.

### Active lineage

The active lineage identifies the workflow/rework path currently being advanced and shown by Current Work.

It answers:

- which root attempt is active;
- which rework branch is current;
- which Run should receive the next workflow action;
- which lineage is aggregated into the Current Work view.

### Accepted part results

`accepted_part_results` identifies the user-approved result for each part id.

It answers:

- which child Run result is approved for `upper_link`;
- which child Run result is approved for `base`;
- whether a part has no approved result yet.

Multiple accepted part results may be sibling Runs. Therefore:

- accepted result does not always equal active-lineage leaf;
- creating a child Run does not automatically accept it;
- selecting another candidate does not delete earlier accepted results;
- only an explicit user approval updates an accepted result pointer.

## Current Work and Run Snapshot

### Current Work

Current Work is the actionable, aggregated product view over the active lineage and Work-level decisions.

It may show information originating from several Runs, but every item must preserve provenance.

It is the only normal place for workflow mutations.

### Run Snapshot

Run Snapshot is one immutable audit view.

It shows what that Run knew and produced. It does not pretend to be the complete current Work.

Normal write actions are disabled. A user may return to Current Work, compare results, or explicitly create a new rework attempt.

## Canonical workflow

The user-facing Workflow represents trusted product checkpoints. It does not display every model call, context request, validator retry, or repair turn.

Canonical current workflow:

    Prompt / Requirement Input
      -> Requirement
      -> Clarification, when required
      -> Planning / Design Brief
      -> Assembly Plan and Candidate Parts
      -> Explicit Part Selection
      -> Part Request
      -> Part Review
      -> Reviewed Handoff
      -> CAD IR Draft
      -> CAD IR Validation and Part Modeling
      -> Part Result Review
      -> User Approval / Accepted Part Result
      -> Work-level Workflow Review
      -> Rework or next Part Job
      -> Deliverables

For a simple single-part request, Planning and Assembly Plan may be compact, but their responsibilities remain distinct.

For Contract mode, CAD IR may validate while deterministic CAD execution is intentionally skipped. This is `contract_complete` or `execution_skipped`, not a failure.

For Full mode, validated CAD IR proceeds to deterministic CAD execution and may produce STEP/STL.

## Stage responsibilities

### 1. Prompt / Requirement Input

Purpose:

- capture the user's original natural-language goal;
- start or revise a Work through an explicit Run.

Input:

- user prompt;
- optional prior accepted Work context for revision.

Output:

- immutable prompt artifact;
- root or revision Run identity.

User decision:

- submit, cancel, or revise the prompt.

Must not:

- silently generate all parts;
- overwrite an earlier prompt;
- treat browser state as the source of truth.

### 2. Requirement

Purpose:

- convert the prompt into a structured engineering requirement contract;
- identify scope, goals, constraints, assumptions, missing information, and risk.

Input:

- prompt;
- approved prior context when revising.

Output:

- active requirement artifact;
- assumptions;
- missing or risky fields;
- flow decision: proceed, clarify, or block safely.

User decision:

- approve the interpreted requirement;
- answer focused clarification questions;
- override a controlled field;
- return to prompt.

Must not:

- invent critical dimensions without exposing assumptions;
- choose final geometry;
- execute CAD.

### 3. Clarification, conditional

Purpose:

- collect only the information needed to resolve material ambiguity or risk.

Input:

- unresolved requirement fields and focused questions.

Output:

- append-only clarification artifact;
- a new active requirement version.

User decision:

- answer, accept an assumption, or stop.

Must not:

- become a generic chat transcript;
- overwrite the original requirement artifact.

### 4. Planning / Design Brief

Purpose:

- translate the accepted requirement into an engineering approach;
- define design goals, constraints, candidate strategies, and capability boundaries.

Input:

- active accepted requirement.

Output:

- design brief or planning artifact;
- candidate approaches and concise trade-offs;
- route toward single-part, multi-part, reference-only, or unsupported scope.

User decision:

- inspect or approve the approach;
- request revision when the route is wrong.

Must not:

- be reduced to a filename list;
- silently select unrelated templates;
- claim CAD generation.

### 5. Assembly Plan and Candidate Parts

Purpose:

- decompose an assembly-level request into generated candidates and reference-only components;
- preserve interfaces and assembly context;
- identify a selected candidate for the current part pipeline.

Input:

- planning result;
- active requirement.

Output:

- assembly plan;
- candidate part list;
- reference component list;
- selected candidate;
- interface and dependency context.

User decision:

- inspect candidates;
- explicitly choose another supported candidate;
- return to planning when decomposition is wrong.

Changing the selected candidate:

- writes a validated, versioned override;
- preserves the original plan;
- preserves old Runs and accepted results;
- marks affected downstream stages stale;
- recommends creating a new Part Request.

Must not:

- select a candidate merely because its node was opened;
- treat reference-only components as generated parts;
- automatically start CAD generation.

### 6. Part Request

Purpose:

- create the scoped task contract for exactly one selected part.

Input:

- active assembly plan;
- selected candidate;
- preserved assembly context.

Output:

- `part_create_request` describing the intended part, role, constraints, interfaces, and requested result scope.

User decision:

- inspect the request;
- continue to Part Review;
- return to Assembly Plan.

Must not:

- generate the part;
- discard assembly context;
- automatically approve the request.

### 7. Part Review

Purpose:

- evaluate whether the Part Request is coherent and ready for modeling.

Input:

- Part Request;
- relevant requirement and assembly context.

Output:

- Part Request Review;
- approved, needs revision, or blocked conclusion;
- concise issues and assumptions.

User decision:

- approve the request;
- request changes;
- block or return upstream.

Must not:

- substitute for final model-result review;
- create CAD.

### 8. Reviewed Handoff

Purpose:

- freeze the approved modeling brief and context passed into the CAD-generation episode.

Input:

- approved Part Request;
- Part Review;
- preserved assembly context.

Output:

- reviewed part handoff;
- explicit part id, scope, assumptions, interfaces, and capability mode.

User decision:

- inspect the handoff;
- proceed to CAD IR Draft;
- return upstream when it is incorrect.

Must not:

- be regenerated from unrelated defaults;
- lose the source part intent.

### 9. CAD IR Draft

Purpose:

- let the bounded agent episode propose a structured, reviewable CAD contract.

Input:

- Reviewed Handoff;
- compact context envelope;
- allowlisted context requested through the Context Broker.

Output:

- CAD IR draft;
- assumptions and normalization summary;
- episode records and contract submissions.

Agent freedom:

- request relevant context;
- compare candidate geometry strategies;
- submit or repair structured contracts;
- ask the user for missing information;
- stop safely.

System constraints:

- no arbitrary shell, Python, or direct CadQuery execution;
- no bypass of CAD IR validation;
- bounded steps, context requests, submissions, repairs, tools, and time.

### 10. CAD IR Validation and Part Modeling

Purpose:

- validate the proposed CAD IR;
- execute deterministic CAD generation only when the contract is valid.

Input:

- CAD IR draft;
- validator feedback;
- execution mode.

Output in Full mode:

- validated `input_ir`;
- deterministic execution report;
- STEP/STL when supported and successful.

Output in Contract mode:

- validated `input_ir`;
- explicit `execution_skipped` / `contract_complete` state;
- no STEP/STL expected.

Output on safe block:

- preserved best draft;
- typed validation failure;
- repair, user-input, or development options;
- no invalid CAD output.

Must not:

- treat missing templates as the product-level terminal reason before an agent attempt;
- replace unknown intent with an unrelated fallback part;
- claim strength, fit, motion, or assembly validation unless those checks ran.

### 11. Part Result Review

Purpose:

- assess one generated or contract-complete child result against the Reviewed Handoff.

Input:

- Reviewed Handoff;
- child Run result;
- validation and execution reports;
- product artifacts.

Output:

- Part Result Review;
- scope and limitations;
- accepted-for-preview, needs revision, blocked, skipped, or failed result semantics.

User decision:

- inspect artifacts;
- approve the result;
- request revision;
- leave it unaccepted.

Must not:

- automatically update `accepted_part_results`;
- imply full assembly generation from one part;
- show Contract mode as a missing-output error.

### 12. User Approval / Accepted Part Result

Purpose:

- record the user's explicit acceptance of a part result.

Input:

- a reviewable Part Result Review and its child Run.

Output:

- append-only approval review;
- Work-level accepted result pointer for the part id.

Effect:

- updates Work state only;
- does not rewrite the child Run or STEP/STL;
- does not automatically accept sibling parts;
- does not claim assembly completion.

### 13. Work-level Workflow Review

Purpose:

- summarize the current Work lineage, accepted results, missing results, limitations, risks, and valid next actions.

Input:

- active lineage;
- Part Jobs and accepted pointers;
- stage reviews;
- artifact availability and diagnostics.

Output:

- work-level review artifacts;
- plain-language conclusion;
- recommended next action.

User decision:

- accept the current scope;
- continue with another Part Job;
- request rework;
- inspect deliverables.

Must not:

- inherit an upstream block as its own execution failure when the review itself completed;
- pretend a deterministic heuristic is an independent LLM judgment;
- generate CAD.

### 14. Rework

Purpose:

- create a traceable new attempt from an explicit review decision.

Input:

- stage review with `needs_revision`;
- target rework checkpoint;
- requested changes;
- accepted upstream context.

Output:

- child rework Run;
- parent/child lineage;
- new stage artifacts and comparisons where supported.

User decision:

- confirm consequential rework;
- compare attempts;
- accept or reject the new result.

Must not:

- modify the historical parent Run;
- silently switch active lineage on failed execution;
- run an unbounded loop.

### 15. Deliverables

Purpose:

- present accepted products and their review scope.

Input:

- accepted part-result pointers;
- validated output artifacts;
- work-level review.

Output:

- controlled preview and download actions;
- explicit distinction between generated parts, reference components, contract-only results, and missing deliverables.

Must not:

- expose arbitrary files;
- present unapproved attempts as accepted deliverables;
- claim a full assembly deliverable before one exists.

## Stage state dimensions

Do not collapse all meanings into one `status` string.

A stage may need separate dimensions:

- `execution_status`: not_started, ready, running, completed, skipped, blocked, failed;
- `result_status`: draft, contract_complete, generated, ready_for_review, accepted_for_preview, stale;
- `user_review_status`: not_reviewed, approved, needs_revision, blocked;
- `attention`: none, in_progress, required;
- `capability_mode`: deterministic_fallback, agentic, contract, full.

Example:

    Workflow Review
      execution_status = completed
      result_status = ready_for_review
      user_review_status = not_reviewed
      limitation = full assembly not generated

Do not render the upstream limitation as `Workflow Review = blocked`.

## Agent architecture within the workflow

Agents operate inside checkpoint transitions; they do not replace the product workflow.

The canonical agent boundary is:

    objective and compact context
      -> bounded agent episode
      -> allowlisted context/tool actions
      -> structured contract submission
      -> deterministic validation
      -> deterministic execution or typed safe block
      -> persisted concise evidence

The Workflow records trusted results and user decisions. Advanced diagnostics may show concise episode events, but private chain-of-thought is neither required nor persisted.

## UI architecture implications

The primary Workflow page must answer:

1. What is the current Work trying to create?
2. What checkpoint is current?
3. What result exists now?
4. What limitation materially matters?
5. Does the user need to decide anything?
6. What is the one recommended next action?
7. What visible change proves that action succeeded?

The UI should derive from the canonical stage responsibilities rather than from whatever files happen to exist.

Primary surfaces:

- Current Work conclusion;
- recommended next action;
- stable Workflow checkpoint graph;
- selected checkpoint detail;
- relevant artifacts and review;
- Parts and accepted results;
- Run history and immutable snapshots.

Advanced surfaces:

- full provenance;
- raw JSON;
- validator payloads;
- episode events;
- action audit metadata;
- internal ids and diagnostic codes.

## Architecture invariants

The following require an explicit architecture change, not an incidental implementation edit:

1. Workspace contains Works; a Work contains/references Runs and Part Jobs.
2. Work is mutable; Run execution evidence is append-only and historical artifacts are not overwritten.
3. Current Work is actionable; Run Snapshot is read-only.
4. User prompt enters through an explicit root or revision Run.
5. Requirement, Planning, Assembly Plan, Part pipeline, Review, Rework, and Deliverables have distinct responsibilities.
6. Workflow nodes are trusted checkpoints, not every internal agent step.
7. Agent output reaches CAD only through validated structured contracts.
8. Deterministic execution remains authoritative for CAD files and validation claims.
9. Candidate inspection and candidate selection are different operations.
10. Changing upstream accepted input marks dependent downstream evidence stale.
11. Creating a result does not automatically approve it.
12. Accepted part results are explicit Work pointers and may belong to sibling Runs.
13. Rework creates a new Run and preserves the parent.
14. Contract mode does not expect STEP/STL and is not a failure.
15. A single generated part is not a complete assembly.
16. Reference-only components are not generated deliverables.
17. User-visible state must reflect real workflow postconditions.
18. Architecture, contracts, projections, tests, UX, roadmap, and readiness documentation must remain synchronized.

## Architecture change protocol

Before changing any of the following, state the proposed architecture delta explicitly:

- Workspace / Work / Run / Part Job ownership;
- stage names or stage order;
- stage input/output responsibilities;
- active-lineage semantics;
- accepted-result semantics;
- artifact mutability;
- candidate-selection semantics;
- review and rework semantics;
- agent execution boundaries;
- CAD validation or execution authority.

Required work for an approved architecture change:

- update this document;
- update contracts and view models;
- assess existing data and migration compatibility;
- update automated tests;
- update the Workflow UX specification;
- update milestone, task-board, and product-readiness status;
- perform a real user-journey check.

Do not let a UI convenience, Golden fixture, local fallback, or one-off bug fix silently redefine the architecture.

## Required implementation self-check

Before reporting a task complete, answer:

- Which canonical object does this change affect: Workspace, Work, Run, or Part Job?
- Which workflow checkpoint owns the behavior?
- What is the stage input, output, and user decision?
- Does the change preserve Run history and Work-pointer semantics?
- Does it preserve active-lineage versus accepted-result separation?
- Does the Agent remain behind structured contracts and validation?
- Does the UI show the current checkpoint and one valid next action?
- Were architecture, UX, readiness, roadmap, and tests synchronized?
