# CadFlow Canonical Product Architecture

## Status and authority

This document is the canonical target architecture for CadFlow.

Status date: 2026-08-01.

CadFlow is migrating from a fixed workflow-first single-part product to an
Agent-first CAD design workbench. This document defines the target. The current
implementation gap is recorded in:

- `../status/current-product-readiness.md`
- `../roadmap/milestones.md`
- `../tasks/task-board.md`

No implementation, test fixture, legacy document, UI layout, or Golden example
may silently redefine this architecture.

## Architectural objective

CadFlow should maximize Agent freedom in design reasoning while constraining:

- context access;
- side effects;
- execution environment;
- resource budgets;
- trusted publication;
- lineage mutation;
- engineering claims;
- user acceptance.

The core boundary is:

```text
Agent chooses design actions and candidate strategy
  -> CadFlow brokers context and tools
  -> candidate executes in isolation
  -> local services inspect and validate evidence
  -> user accepts a reviewable result
  -> accepted results feed assembly and deliverables
```

The product must not confuse a controlled side-effect boundary with a closed
design space.

## Canonical product objects

### Workspace

A Workspace is the local product container.

It owns:

- workspace identity and safe storage root;
- Work index;
- provider, model, runtime, and assurance-mode configuration safe to persist;
- optional examples and operational metadata.

A Workspace contains many Works. It is not one design task or execution
attempt.

### Work

A Work is one mutable user-facing engineering objective.

It owns or references:

- title, description, and current intent;
- active design lineage;
- all associated Runs;
- Part Jobs;
- an optional Assembly Job;
- accepted part-result pointers;
- an accepted assembly-result pointer when one exists;
- deliverable packages;
- current assumptions, unresolved decisions, and recommended action.

Work mutation changes pointers and current decisions. It never rewrites
historical Run evidence.

### Run

A Run is one append-only attempt and audit record.

A Run may contain:

- the prompt or revision request that initiated it;
- compact accepted context snapshots;
- one or more bounded Agent Episodes;
- design candidates and candidate source;
- structured contracts or model programs;
- validator and execution observations;
- geometry, reports, drawings, or assembly artifacts;
- parent/child lineage and comparison evidence.

Run rules:

- historical execution evidence is immutable;
- edits create versioned artifacts or child Runs;
- a failed Run remains inspectable;
- a newer Run is not automatically accepted;
- Run Snapshot is read-only.

### Part Job

A Part Job is the Work-level identity of one intended part.

It owns:

- stable part id, role, and purpose;
- functional interfaces and assembly context;
- accepted constraints and assumptions;
- zero or more attempt Run ids;
- reviewable candidate results;
- one accepted-result pointer or no accepted result.

Creating an attempt does not accept it. Accepting another part does not replace
this Part Job's accepted result.

### Assembly Job

An Assembly Job is an optional Work-level identity for assembling accepted part
results and reference components.

It owns:

- assembly intent;
- exact accepted part-result inputs;
- reference-component identities or envelopes;
- placement, joint, mate, fastener, clearance, and serviceability intent;
- attempt Run ids;
- assembly observations;
- one accepted assembly-result pointer or no accepted result.

Changing a part accepted-result pointer marks dependent assembly attempts stale.
It does not mutate them.

### Deliverable Package

A Deliverable Package is a versioned Work artifact derived from accepted
results.

It records:

- exact accepted part and assembly inputs;
- included files;
- verification evidence;
- unverified or unsupported claims;
- creation Run and timestamp;
- supersession relationship when regenerated.

A package cannot contain failed or merely reviewable candidates as final
deliverables.

## Lineage and acceptance

### Active design lineage

The active lineage identifies the design or rework path currently being
advanced.

It answers:

- which root and child Runs form the current attempt path;
- which Run receives the next design action;
- which observations and candidates belong to the current session.

### Accepted results

Accepted pointers identify user-approved results:

- `accepted_part_results[part_id]`;
- optional accepted assembly result;
- accepted deliverable package when supported.

Accepted results may belong to sibling Runs. Therefore:

- accepted result does not have to equal the active-lineage leaf;
- approval should not implicitly rewrite active lineage;
- starting a new revision does not remove the prior accepted result;
- only explicit user acceptance changes an accepted-result pointer.

### Current Work and Run Snapshot

Current Work is the actionable aggregate over Work decisions, Part Jobs,
Assembly Job, accepted results, and active lineage.

Run Snapshot is an immutable audit view of one attempt. It may offer navigation,
comparison, or an explicit "start revision" action, but it cannot mutate the
historical Run.

## Canonical user journey

The user-facing product has four phases:

```text
Intent -> Design -> Build & Evaluate -> Accept & Deliver
```

The phases are stable. Internal checkpoints are capability-driven and may be
compact, repeated, or omitted when they add no user decision.

### Intent

Purpose:

- capture the user's goal and desired deliverables;
- identify important constraints, references, risk, and assurance mode;
- ask only material clarification questions.

Inputs:

- user prompt or revision request;
- optional accepted Work context or reference files.

Outputs:

- immutable input artifact;
- active intent summary;
- assumptions and focused unresolved decisions;
- initial design objective.

User decision:

- answer a material question;
- accept a visible low-risk assumption;
- change the goal;
- begin design.

Must not:

- require complete specifications for low-risk exploration;
- silently invent safety-critical information;
- choose a supported template as a substitute for the requested object.

### Design

Purpose:

- let the Agent understand, decompose, and explore the design;
- create meaningful candidate strategies;
- define parameters, datums, interfaces, and acceptance targets;
- prepare executable geometry or assembly candidates.

Inputs:

- accepted intent;
- allowlisted Work context;
- selected knowledge and tools;
- prior candidate and observation summaries when revising.

Outputs may include:

- design brief;
- candidate concepts and trade-offs;
- Part Jobs and optional Assembly Job;
- geometry-contract candidates;
- sandboxed model-program candidates;
- explicit assumptions and unresolved decisions.

Agent freedom:

- request semantic context;
- propose and compare candidates;
- create or patch design artifacts;
- select a geometry strategy;
- ask the user;
- stop safely.

User decision appears only when:

- topology, interfaces, manufacturing route, material risk, or acceptance
  criteria require it;
- the user wants to choose among materially different alternatives;
- a consequential Work pointer will change.

Must not:

- treat a fixed template catalogue as the available design space;
- hide a product-changing assumption;
- claim that a design proposal is generated or validated geometry.

### Build & Evaluate

Purpose:

- execute a design candidate in isolation;
- measure and inspect geometry;
- validate requested outputs and declared properties;
- let the Agent repair from structured observations within budgets.

Inputs:

- selected geometry contract or sandboxed model program;
- exact parameters and context manifest;
- execution policy and assurance mode.

Outputs:

- candidate source and execution record;
- STEP-first geometry products when successful;
- inspection and validation reports;
- drawings or assembly artifacts when the operation supports them;
- best candidate and structured failure evidence;
- typed stop reason.

Agent freedom:

- request execution;
- inspect observations;
- repair the contract or model program;
- change candidate strategy;
- request additional context;
- ask the user;
- stop safely.

System authority:

- Tool Broker controls execution and side effects;
- validators decide what can be published as reviewable;
- Work pointers and acceptance remain outside the Agent Episode.

Must not:

- run provider content with unrestricted host authority;
- publish failed candidate files as Work products;
- fabricate successful validation or unsupported engineering claims;
- continue without budgets.

### Accept & Deliver

Purpose:

- present the result, important evidence, and limitations;
- record explicit acceptance;
- continue to another Part Job, Assembly Job, revision, or deliverable package.

Inputs:

- validated reviewable candidate;
- comparison and relevant evidence;
- current accepted-result pointers.

Outputs:

- append-only user decision;
- updated accepted-result pointer when approved;
- next Work recommendation;
- optional Assembly Job attempt or Deliverable Package.

Must not:

- equate reviewable with accepted;
- accept sibling parts or assembly implicitly;
- claim complete assembly from one part;
- include unaccepted candidates in final deliverables.

## Internal checkpoint model

Internal checkpoints provide trust and recovery without becoming a mandatory
wizard:

- `intent_snapshot`;
- `clarification_decision`;
- `design_brief`;
- `candidate_set`;
- `part_job_definition`;
- `assembly_job_definition`;
- `geometry_candidate`;
- `execution_request`;
- `validation_observation`;
- `reviewable_result`;
- `acceptance_decision`;
- `assembly_result`;
- `deliverable_package`.

Rules:

- a checkpoint exists because it establishes a trust boundary, durable decision,
  or recovery point;
- a provider call, context request, retry, or repair turn is an episode event,
  not a user-facing phase;
- legacy artifact names may map into these checkpoints during migration;
- UI stages must be derived from domain state, not from recursive filename
  discovery.

## Geometry candidate paths

### Structured feature and assembly graph

The target structured representation is extensible and operation-based.

It must evolve beyond a flat `part_type + dimensions + features` object and
support:

- parameters, expressions, and units;
- datums, planes, axes, and coordinate systems;
- sketches and constraints;
- ordered features and boolean operations;
- reusable feature patterns;
- named interfaces and functional references;
- manufacturing and inspection intent;
- assembly components, placements, joints, mates, and degrees of freedom.

Backends declare which operations they support. Unsupported operations produce
typed capability observations rather than unrelated fallback geometry.

### Sandboxed model program

An Agent may submit CAD source as an untrusted model candidate when:

- the selected skill and operation allow it;
- the Tool Broker uses an isolated execution profile;
- source, dependencies, parameters, and outputs are captured;
- imports and filesystem access are constrained;
- network access is disabled by default;
- resource limits are enforced;
- local geometry and artifact validators run before publication.

The model program may target an allowlisted CAD API such as CadQuery or
build123d. It may not contain arbitrary workflow mutations, credentials,
external process control, or unrestricted I/O.

### Publication boundary

Both paths follow:

```text
candidate proposal
  -> contract/source validation
  -> isolated execution
  -> geometry inspection
  -> result validation
  -> reviewable result or typed safe block
```

No candidate becomes accepted automatically.

## Agent Episode architecture

A bounded episode receives:

- an objective;
- compact accepted context;
- selected skill and knowledge;
- declared actions and tools;
- execution and context budgets;
- current observations.

Initial action vocabulary:

- `request_context`;
- `ask_user`;
- `propose_candidates`;
- `create_contract`;
- `patch_contract`;
- `create_model_program`;
- `patch_model_program`;
- `request_execution`;
- `inspect_observation`;
- `create_part_jobs`;
- `propose_assembly`;
- `request_deliverables`;
- `stop`.

The Agent chooses actions. The orchestrator:

- validates action contracts;
- enforces budgets;
- brokers tools;
- persists concise events;
- returns observations;
- stops on policy or resource violation.

An implementation that always requests one fixed context, submits once,
validates once, and stops on failure is deterministic orchestration, not an
Agentic episode.

## Assurance and claims

### Explore

Allows rapid candidate iteration and visible low-risk assumptions. It requires
safe execution and geometry validation but does not imply manufacturing
readiness.

### Engineer

Requires explicit functional interfaces, acceptance criteria, and stricter
checks. Missing material engineering information requires user input or a typed
limitation.

### Release

Future and domain-specific. It requires implemented release checks and explicit
user authorization. A successful export is never sufficient.

Every report separates:

- verified;
- assumed;
- unverified;
- unsupported;
- not requested.

## Part and assembly progression

### Part progression

```text
Part Job
  -> design attempts
  -> validated reviewable result
  -> explicit accepted part result
  -> revision or assembly input
```

Each attempt is a Run. The Part Job stores all attempt references, not only one
current run id.

### Assembly progression

```text
accepted part results + reference components
  -> Assembly Job candidate
  -> placement / constraints / validation
  -> reviewable assembly result
  -> explicit accepted assembly result
```

Assembly validation must distinguish:

- placement facts;
- bounding-box heuristics;
- geometric interference checks;
- joint or degree-of-freedom checks;
- fit or tolerance checks;
- motion checks.

It may claim only checks that actually ran.

## Deliverables

A Deliverable Package may include:

- accepted part STEP files;
- accepted assembly STEP or native assembly file;
- BOM;
- PDF/SVG drawings;
- preview meshes and images;
- design, validation, and limitation reports.

Drawing generation is a product capability, not an orphan utility script. A
drawing is deliverable only when:

- it references an accepted result;
- generation completed through an allowlisted tool;
- its source model identity is recorded;
- dimensions and annotations are labeled as generated or verified;
- failures and omissions are visible.

## UX implications

The primary product surface is a design workbench.

Default information order:

1. current design objective;
2. current geometry or assembly preview;
3. Agent progress, assumptions, and concise decisions;
4. one recommended user action;
5. validation summary and important limitations;
6. Part Jobs, alternatives, and accepted results;
7. history, raw artifacts, and diagnostics.

The UI must not:

- make internal artifact handoffs the main navigation;
- require a manual approval screen for every low-risk internal checkpoint;
- expose a template catalogue as if it were Agent capability;
- infer trusted state from file presence;
- expose arbitrary paths, secrets, or unrestricted execution.

## Migration from the former architecture

The current implementation still contains:

- a fixed fifteen-checkpoint Workflow Cockpit;
- flat closed-family CAD IR;
- effectively one-shot `create_part_ir` episode behavior;
- legacy stage/availability presentation derived from sanitized Run metadata;
- incomplete Part Job ownership in historical v1 evidence;
- disconnected FreeCAD assembly and TechDraw helpers;
- multiple compatibility/evaluation entry points outside target-product
  authority.

M1 now provides a Work-manifest v2 domain foundation:
ordered Part Job attempts, acceptance separated from active lineage,
schema-versioned Assembly Job and Deliverable Package definitions, typed
artifact references, and v1 compatibility projection. One `WorkOrchestrator`
owns the target-product mutation path and invokes the existing deterministic
runtime through one compatibility port. Legacy Run metadata is translated by
an explicit read-only projector; target product trust and acceptance are
resolved from manifest pointers and artifact references. This is runtime
consolidation, not Agentic design or Assembly generation.

The first M2 package adds a typed `design_part` v0.1 capability registry and an
internal provider-selected structured-contract loop. It demonstrates semantic
context choice, validation-observation branching, focused user questions, and
budgeted evidence. It is not yet a product path and exposes no CAD execution or
model-program authority, so it does not satisfy the M2 vertical-slice gate.

The second M2 package establishes a CadFlow-owned Tool Broker catalog and
routes the preview's local structured-contract validation through it. Tool
definitions declare skill authorization, input/output contracts, execution
profile, filesystem/network/process policy, evidence, limits, and failure
codes. An explicit model-program capability record enumerates every required
isolation control and reports the current Windows profile unavailable. A
model-program request therefore returns `sandbox_unavailable` before candidate
storage or process startup. This is a fail-closed capability gate, not a
sandbox implementation, CAD execution path, or publication boundary.

Migration rules:

1. preserve existing Runs and artifacts as immutable legacy evidence;
2. add explicit schema versions and compatibility projections;
3. do not reinterpret legacy deterministic output as Agentic;
4. consolidate execution behind one orchestrator;
5. implement first-class Part Job attempts before multi-part claims;
6. expose the four-phase workbench only when its actions have real handlers;
7. keep the legacy console available as Diagnostics during transition.

## Architecture change protocol

An architecture change must state:

- affected product objects;
- affected user phase and internal checkpoint;
- input, output, and user decision;
- Agent freedom added or removed;
- side-effect and trust boundary;
- migration impact;
- visible success and failure recovery.

Synchronize:

- this document;
- `docs/FINAL-PRD.md`;
- `docs/workflow_contract.md`;
- Agent, skill, and knowledge contracts;
- projections and tests when implementation changes;
- UX specification;
- roadmap, task board, and readiness.

Documentation may define a target before implementation only when readiness and
tasks explicitly mark the implementation as nonconforming or pending.

## Required implementation self-check

Before reporting product work complete, answer:

- Which Work, Run, Part Job, Assembly Job, or Deliverable Package changed?
- Which of the four user phases owns the behavior?
- Which internal trust checkpoint is created or consumed?
- What design choice remains with the Agent?
- What side effect remains under CadFlow authority?
- Can failed or unaccepted output appear as a deliverable?
- Does the change preserve historical evidence and accepted pointers?
- What automated and manual evidence exists?
- Which target capability remains unimplemented?
