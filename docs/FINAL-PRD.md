# FINAL PRD: CadFlow Agent CAD Workbench

Status date: 2026-08-01.

Status: target product baseline. The repository is migrating from the former
workflow-first single-part product to this Agent-first architecture. Capability
claims must continue to follow `docs/status/current-product-readiness.md`.

## 1. Product direction

CadFlow is an Agent-first CAD design workbench.

It helps a user turn an incomplete engineering goal into:

- explored and compared design strategies;
- parametric part models;
- accepted part results;
- assemblies made from accepted parts;
- reviewable engineering deliverables such as STEP, BOM, and drawings;
- an auditable history of attempts, observations, decisions, and acceptance.

The Agent is the primary design collaborator. CadFlow supplies context,
geometry tools, isolated execution, validation, artifact management, lineage,
and approval boundaries.

CadFlow must not reduce an unfamiliar design to the nearest built-in part
template merely because that template is executable.

## 2. Product promise

For a normal Work, the user should be able to:

1. describe the intended product or change in natural language;
2. answer only questions that materially affect topology, interfaces, risk, or
   acceptance;
3. let the Agent explore, model, inspect, and repair candidate designs;
4. compare meaningful alternatives and understand important assumptions;
5. accept individual part results without losing earlier attempts;
6. continue from accepted parts into assembly and deliverable generation;
7. revise any accepted result through a traceable child Run.

The default experience is a design conversation with visible geometry and
evidence, not a form wizard, template catalogue, artifact browser, or mandatory
sequence of review screens.

## 3. Product objects

### Workspace

A local container for configuration, Works, safe runtime storage, and optional
provider settings.

### Work

One mutable user-facing engineering objective. A Work owns or references:

- its current intent and accepted decisions;
- Runs and active design lineage;
- Part Jobs;
- an optional Assembly Job;
- accepted part and assembly result pointers;
- deliverable packages;
- the current recommendation and unresolved user decisions.

### Run

One append-only attempt and audit record. A Run may contain one or more bounded
Agent Episodes, candidate executions, observations, and review evidence.
Historical execution evidence is immutable.

### Part Job

One intended part within a Work. A Part Job owns:

- a stable part identity and role;
- interface and assembly context;
- multiple attempt Run references;
- candidate results;
- one explicit accepted-result pointer or no accepted result.

### Assembly Job

An optional Work-level task that combines accepted part results and reference
components. It owns:

- assembly intent and interfaces;
- part-result inputs;
- placement and constraint attempts;
- validation evidence;
- one explicit accepted assembly result or no accepted result.

### Deliverable Package

A versioned package derived only from accepted results. Depending on available
capability it may contain:

- part STEP files;
- assembly STEP or native assembly files;
- STL preview files;
- BOM;
- PDF/SVG drawings;
- model and validation reports;
- explicit limitations and unverified claims.

## 4. User-facing design loop

CadFlow has four user-facing phases:

```text
Intent
  -> Design
  -> Build & Evaluate
  -> Accept & Deliver
       ↘ revise / continue another Part Job / assemble
```

These phases describe the user journey. They are not a fixed script for every
model call or artifact.

### Intent

Capture the goal, known constraints, desired deliverables, and risk level.
Clarification appears only when missing information materially changes the
design or the requested assurance.

Visible success:

- the Agent can state what it is trying to create;
- important assumptions and unresolved decisions are visible;
- the next design action is clear.

### Design

The Agent explores geometry and engineering strategies. It may:

- request allowlisted context;
- decompose an assembly into Part Jobs;
- compare candidate concepts;
- define parameters, datums, interfaces, and manufacturing assumptions;
- create or patch a structured geometry contract;
- create or patch a sandboxed CAD model program;
- ask the user when a material decision cannot be made safely.

Visible success:

- at least one coherent design candidate exists;
- the candidate preserves the user's intent and relevant interfaces;
- alternatives and trade-offs are concise and meaningful.

### Build & Evaluate

CadFlow executes candidates in isolation, generates geometry, inspects results,
and returns structured observations to the Agent.

The Agent may repair and retry within budgets. The system, not the provider,
decides whether a candidate is valid and reviewable.

Visible success:

- a candidate has measured geometry and requested exports; or
- a typed block explains what is missing and how to recover.

### Accept & Deliver

The user reviews outcomes rather than internal ceremony. Explicit acceptance:

- updates the accepted result pointer;
- never rewrites a Run;
- does not automatically accept sibling parts;
- does not imply assembly or engineering release unless those results exist.

After part acceptance, the recommended action may be:

- revise the part;
- continue another Part Job;
- create or update the Assembly Job;
- generate a deliverable package.

## 5. Internal checkpoints

CadFlow persists trusted internal checkpoints, but they are not all mandatory
user-visible stages:

- intent snapshot;
- clarification decision when required;
- design brief and candidate set;
- selected Part Job or Assembly Job;
- model contract or model-program candidate;
- execution request;
- validation and inspection observations;
- reviewable result;
- explicit acceptance;
- assembly result;
- deliverable package.

Requirement, Planning, Part Request, Reviewed Handoff, CAD IR Draft, and Review
artifacts may remain as compatibility or specialized artifacts. They must not
force every low-risk design through a fixed fifteen-step UI.

## 6. Geometry execution architecture

CadFlow supports two controlled candidate paths.

### Structured geometry path

The Agent submits a backend-neutral geometry contract. The target contract is a
feature and assembly graph rather than a closed `part_type` template selector.

The evolving contract should support:

- typed parameters and units;
- datums and coordinate frames;
- sketches and constraints;
- extrude, revolve, sweep, loft, shell, and boolean operations;
- holes, pockets, fillets, chamfers, ribs, patterns, and transforms;
- named faces, axes, interfaces, and functional features;
- manufacturing and inspection intent;
- assembly placements, joints, mates, and reference components.

### Sandboxed CAD program path

For geometry not yet expressible in the structured contract, the Agent may
submit a CAD model program as an untrusted candidate.

The Tool Broker must enforce:

- isolated process or container execution;
- no network by default;
- allowlisted imports and CAD APIs;
- explicit CPU, memory, step, and wall-clock budgets;
- a dedicated writable candidate directory;
- no arbitrary workspace mutation;
- captured source, parameters, logs, and outputs;
- local geometry and artifact validation before publication.

Provider-generated code is never trusted merely because it executed. It becomes
a reviewable result only after local policy, geometry, and output checks pass.

### Shared publication boundary

Both paths converge on:

```text
untrusted candidate
  -> isolated execution
  -> geometry inspection
  -> policy and result validation
  -> reviewable Run result or typed safe block
```

Only accepted results become Work deliverables.

## 7. Agent behavior

A bounded Agent Episode may choose among declared actions such as:

- request context;
- ask the user;
- propose or compare candidates;
- create or patch a geometry contract;
- create or patch a sandboxed model program;
- request candidate execution;
- inspect structured observations;
- repair and retry;
- create Part Jobs;
- propose assembly operations;
- request drawing or deliverable generation;
- stop with a typed reason.

The orchestrator controls budgets and side effects. The Agent controls design
strategy inside those boundaries.

A fixed one-shot adapter call wrapped in episode metadata is not sufficient to
claim Agentic design.

## 8. Assurance modes

### Explore

- optimized for rapid concept iteration;
- permits visible low-risk assumptions;
- may use the sandboxed CAD program path;
- requires geometry and export validation;
- never claims manufacturing release.

### Engineer

- requires explicit functional interfaces and acceptance criteria;
- applies stricter dimensional, manufacturing, and assembly checks;
- unresolved material engineering decisions require user input;
- deliverables state verified and unverified properties separately.

### Release

A future mode. It may be enabled only for declared domains with implemented and
verified release checks. It must never be inferred from a successful STEP
export.

Legacy Contract and Full execution modes may remain during migration, but they
describe execution behavior rather than the user-facing product architecture.

## 9. Trust, lineage, and approval

- Current Work is actionable; Run Snapshot is read-only.
- Work pointers may change; historical Run evidence may not.
- Active design lineage and accepted part or assembly results are distinct.
- File presence is not business status.
- Candidate execution outputs are untrusted until validation passes.
- A reviewable result is not an accepted result.
- Only explicit user acceptance changes accepted-result pointers.
- Deliverables resolve through accepted-result pointers.
- Upstream changes mark dependent evidence stale without deleting history.
- Failed attempts retain diagnostic evidence but do not publish product-looking
  deliverables.

## 10. Industrial deliverable direction

The target product output is an engineering package, not merely STL.

Progressive deliverables are:

1. validated parametric part and STEP;
2. multiple accepted parts with stable interfaces;
3. assembly placement/constraint result and assembly STEP/native file;
4. BOM and reference-component list;
5. part and assembly drawings;
6. declared inspection, tolerance, manufacturing, and release evidence where
   corresponding checks exist.

CadFlow must distinguish model generation from claims about fit, motion,
strength, tolerance stack, DFM/DFA, GD&T, FEA, or safety. Unsupported claims
remain explicit limitations.

## 11. UX requirements

The primary surface must answer:

1. What is the Agent designing now?
2. What geometry or assembly result exists?
3. What did the Agent assume or change?
4. What validation or limitation matters?
5. Does the user need to decide anything?
6. What is the recommended next action?

Primary surfaces:

- design conversation and focused questions;
- live or recent model preview;
- current candidate and concise alternatives;
- current Part Jobs and accepted results;
- validation summary and important limitations;
- one recommended action.

Secondary or advanced surfaces:

- full artifact lineage;
- raw JSON and model source;
- episode events;
- validator payloads;
- provider and audit metadata.

## 12. Current implementation reality

The current repository does not yet implement this target architecture.

Implemented foundations worth retaining:

- Workspace, Work, Run, Work-manifest v2, and ordered Part Job attempt storage;
- schema-versioned Assembly Job and Deliverable Package definitions plus typed
  artifact references;
- a v1 Work-manifest compatibility projector that does not rewrite Run
  evidence;
- append-only evidence and explicit accepted-result pointers;
- deterministic CadQuery execution for a small set of part families;
- STEP-first output and basic geometry inspection;
- isolated candidate execution and failure cleanup;
- controlled artifact access and a tested local console.
- an internal `design_part` v0.1 typed skill registry and provider-selected
  structured-contract episode preview with semantic context and local
  validation observations;
- a CadFlow-owned Tool Broker for that preview's structured-contract validator,
  plus an explicit model-program capability gate that reports the current
  Windows sandbox profile unavailable and fails closed before execution;
- a validation-only product route from an owned Part Job attempt through
  `WorkOrchestrator` into the provider-selected episode, with idempotent request
  identity, append-only Run evidence, and typed Work artifact references;
- a selected CadQuery v1 model-program source contract and Broker-owned static
  AST validator with explicit imports, calls, entrypoint, syntax, and size
  policy; static success grants no execution authority.

Major migration gaps:

- the current CAD IR is a closed part-family selector;
- the current product Agent Episode is effectively one-shot;
- the product-routed provider-selected episode still stops at structured
  contract validation and has no usable sandboxed execution tool;
- the model-program execution entry remains capability metadata and a safe
  block; the new static source validator is not a Windows sandbox or source
  executor;
- provider-backed Agentic design is not product-usable;
- the UI is organized around the former fixed workflow;
- ordered Part Job attempts and the deterministic product `WorkOrchestrator`
  are implemented; normal Assembly Job progression remains incomplete;
- FreeCAD assembly and TechDraw scripts are not integrated deliverables;
- compatibility/evaluation execution paths remain callable outside product
  authority, and the current UI remains a legacy workflow surface.

## 13. Product acceptance milestones

CadFlow may claim the Agent-first vertical slice only when:

- one provider-backed Design Episode performs more than a fixed adapter call;
- the Agent can observe validation feedback and choose repair, context, user
  input, or stop;
- at least five non-template benchmark parts reach validated STEP output;
- failed candidates cannot mutate trusted Work state;
- capability mode and assumptions are visible;
- the user can accept a result and revise it through a child Run.

CadFlow may claim multi-part assembly only when:

- Part Jobs own multiple attempts and accepted results;
- an Assembly Job consumes accepted part-result identities;
- placement or constraint evidence is persisted and validated;
- an assembly deliverable is produced without implying unsupported fit or
  motion validation.

CadFlow may claim drawing-package support only when drawing generation is in
the normal Work flow, tested on accepted results, and included in the
Deliverable Package.

## 14. Non-goals for the correction phase

The architecture correction does not immediately promise:

- production-ready arbitrary CAD;
- automatic engineering sign-off;
- complete surface modeling;
- robust feature recovery from arbitrary STEP;
- mesh reverse engineering;
- full GD&T, FEA, kinematics, or safety release;
- public cloud or multi-user operation.

The immediate goal is to restore Agent design breadth while preserving trusted
execution and honest capability boundaries.
