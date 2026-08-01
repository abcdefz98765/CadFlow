# CadFlow Design and Artifact Contract

## Authority

This document defines durable handoffs, artifacts, and trust transitions for the
Agent-first CadFlow product.

Product objects and user phases are defined by:

- `architecture/cadflow-canonical-product-architecture.md`

Agent behavior and knowledge ownership are defined by:

- `architecture/agent-skill-knowledge.md`
- `architecture/bounded-agent-loop-context-broker-and-checkpoints.md`

## Core rule

Artifacts establish trust, recovery, and lineage. They do not prescribe a fixed
user-facing wizard.

A Work normally progresses through:

```text
Intent
  -> Design
  -> Build & Evaluate
  -> Accept & Deliver
```

Within Design and Build & Evaluate, the Agent may repeat context, proposal,
execution, inspection, and repair actions without creating a new user-visible
stage for every turn.

## Artifact trust roles

Every artifact has one role:

- `accepted_input` — an explicit Work decision or accepted upstream result;
- `candidate` — an untrusted design contract, model program, or assembly
  proposal;
- `observation` — validator, execution, inspection, or comparison evidence;
- `reviewable_result` — a locally validated result available for user review;
- `accepted_result` — a result reached through an explicit Work pointer;
- `deliverable` — an accepted-result-derived file in a versioned package;
- `diagnostic` — blocked or failed attempt evidence.

File presence does not determine the role.

## Common artifact envelope

New durable artifacts should expose:

```json
{
  "artifact_type": "design_candidate",
  "schema_version": 1,
  "work_id": "...",
  "run_id": "...",
  "part_job_id": null,
  "assembly_job_id": null,
  "phase": "design",
  "checkpoint": "geometry_candidate",
  "trust_role": "candidate",
  "source_artifact_ids": [],
  "created_at": "...",
  "content": {}
}
```

Large binary files may use a metadata record plus a controlled relative
artifact identity.

The envelope must not expose secrets, provider payloads, unrestricted paths, or
private reasoning.

## Implemented domain manifest records

The implemented M1 runtime uses:

- Work manifest schema v2;
- nested Part Job, Part Job attempt, accepted part result, Assembly Job
  definition, Deliverable Package definition, and artifact-reference schema v1;
- an explicit v1-to-v2 compatibility projector;
- one top-level `WorkOrchestrator`;
- one typed deterministic compatibility port for existing Run behavior.

The concrete fields and migration behavior are defined in
`architecture/domain-record-contracts.md`.

Part Job attempt order is stored in `part_jobs[].attempts`; a singular legacy
`run_id` is not canonical product state. Accepted part-result pointers remain
in `accepted_part_results` and do not update active design lineage.

The M1 `project_product_state` contract consumes only manifest pointers and
artifact ids. It does not receive a directory or filename list. Older Run
summaries pass through an explicit read-only compatibility projector that
creates in-memory observation, diagnostic, candidate, or reviewable references
from already-sanitized metadata. Filename presence alone never creates an
accepted result; only an explicit accepted-result pointer does.

## Intent artifacts

### Input

Primary artifact:

- `intent_input.json` for new Runs;
- legacy `prompt.txt` remains readable during migration.

Records:

- original user request;
- requested output scope;
- optional references;
- assurance mode;
- revision parent when applicable.

### Intent snapshot

Primary artifact:

- `intent_snapshot.json`.

Records:

- concise object goal;
- known constraints and interfaces;
- assumptions;
- unresolved material decisions;
- focused questions;
- recommendation to design, ask, or stop.

Legacy `requirement.json`, clarification artifacts, and accepted requirement
overrides map into this checkpoint during migration.

Rules:

- original input is immutable;
- low-risk exploration may proceed with visible assumptions;
- engineering-critical missing information requires a question or limitation;
- no supported template may replace unknown intent.

## Design artifacts

### Design brief

Primary artifact:

- `design_brief.json`.

Records:

- design objective;
- functional requirements;
- constraints and priorities;
- candidate strategies and trade-offs;
- intended manufacturing route;
- validation targets;
- relevant capability limitations.

### Candidate set

Primary artifact:

- `candidate_set.json`.

Each candidate records:

- stable candidate id;
- concept summary;
- part or assembly scope;
- parameters and interfaces;
- execution path: structured contract or sandboxed model program;
- assumptions and known risks;
- reason it differs from other candidates.

Candidate inspection is read-only. Selecting a strategy or result is an
explicit episode or user action depending on consequence.

### Part Job definitions

Primary Work artifact:

- `part_jobs.json` or equivalent first-class Work records.

Each Part Job records:

- stable part id and role;
- interface context;
- attempt Run ids;
- current design attempt when applicable;
- accepted-result pointer;
- stale dependencies.

Legacy Assembly Plan, Part Request, Part Review, and Reviewed Handoff artifacts
may supply migration context. New Part Jobs must not require those as separate
user approvals unless risk or policy requires it.

### Assembly Job definition

Primary Work artifact:

- `assembly_job.json`.

Records:

- exact accepted part-result inputs;
- reference components;
- placements, joints, mates, fasteners, and clearance intent;
- assembly validation targets;
- attempt Runs and accepted assembly pointer.

## Geometry candidate contracts

### Structured geometry candidate

Primary artifact:

- `geometry_contract.json`.

Target representation:

- typed parameters and units;
- coordinate frames and datums;
- sketches and constraints;
- ordered features and boolean operations;
- named interfaces and functional features;
- manufacturing and inspection intent.

Legacy `cad_ir_draft.json` and `input_ir.json` map to this artifact role but
remain limited closed-family contracts until the v2 feature graph is
implemented.

### Sandboxed model-program candidate

Primary artifacts:

- `model_program_manifest.json`;
- `candidate_model.py` or another allowlisted source format.

The manifest records:

- target CAD API and version;
- entry point;
- parameter values;
- allowed imports and tools;
- expected outputs;
- source hash;
- execution profile;
- source context and candidate id.

The source is untrusted. It may be executed only through the Tool Broker in an
isolated candidate directory.

Forbidden:

- credentials and environment inspection;
- network access unless a future operation explicitly allows it;
- arbitrary subprocess or shell control;
- writes outside the candidate directory;
- Work or Run pointer mutation;
- dynamic dependency installation;
- self-declared validation success.

## Execution request

Primary artifact:

- `execution_request.json`.

Records:

- exact candidate artifact id and hash;
- target backend;
- execution profile;
- output contract;
- resource budgets;
- validation plan;
- source Work, Run, Part Job, or Assembly Job.

The request is created by CadFlow after action validation. Candidate source
cannot grant itself execution authority.

## Episode artifacts

A bounded Agent Episode records:

```text
agent_episode.json
context_manifest.json
agent_events.jsonl
candidates/
observations/
agent_result.json
```

Record:

- objective and assurance mode;
- selected skill and knowledge ids;
- allowed actions and tools;
- requested context and provenance;
- concise action summaries;
- candidate submissions;
- validator and execution observations;
- repair summaries;
- budgets used;
- final result or typed stop.

Do not record private chain-of-thought, secrets, unrestricted transcripts, or
raw provider payloads.

M2 currently implements an internal `design_part` v0.1 episode preview. Its
typed registry allows semantic context requests, structured compatibility
contract creation/patching, local validation, focused questions, and typed
stops. Context manifest entries record Work, Run, Part Job, checkpoint, trust
role, and compact summary. Request and byte budgets are enforced.

This preview has no execution tool. A validated `cad_ir_draft` remains a
candidate contract; it is not geometry, a reviewable result, or an accepted
result.

## Build and evaluation artifacts

Candidate execution occurs in an isolated staging directory.

Possible outputs:

- generated model source;
- STEP;
- STL or preview mesh;
- native backend file;
- geometry measurements;
- feature and interface inspection;
- execution log;
- structured validation result.

Before publication, CadFlow verifies:

- source and execution identity;
- non-empty and valid geometry;
- expected solid/body count;
- requested bounding or dimensional targets where implemented;
- expected exports;
- declared features or interfaces where inspection supports them;
- path and output policy;
- absence of prohibited side effects.

Successful publication creates:

- `reviewable_result.json`;
- controlled product artifacts inside the Run.

Final failure creates diagnostic evidence only. Product-looking files remain in
isolated candidate storage or are removed according to retention policy.

## Observation contract

Observations are system evidence, not Agent decisions.

Example:

```json
{
  "observation_type": "geometry_validation_failed",
  "candidate_id": "candidate_002",
  "codes": ["hole_edge_margin_too_small"],
  "measurements": {},
  "repairable": true,
  "owner": "local_validator"
}
```

After an observation the Agent chooses to:

- repair;
- change strategy;
- request context;
- ask the user;
- stop.

The orchestrator must not fabricate that choice.

## Reviewable result

Primary artifact:

- `reviewable_result.json`.

Records:

- exact candidate and execution identity;
- output artifacts;
- measured and validated facts;
- assumptions;
- unverified or unsupported claims;
- comparison with the prior accepted result when revising;
- recommended next action.

A reviewable result is not accepted.

Legacy `part_result_review.json` may map to this role.

## Acceptance

Acceptance records are append-only:

```text
reviews/<scope>/acceptance_NNN.json
```

An explicit acceptance may update:

- `accepted_part_results[part_job_id]`;
- the accepted Assembly Job result;
- an accepted Deliverable Package pointer.

Acceptance:

- does not rewrite the Run;
- does not automatically change active design lineage;
- does not accept sibling results;
- does not imply engineering release;
- records the accepted evidence and known limitations.

## Revision

A revision creates a child Run from an explicit parent result.

Preferred artifacts:

```text
revision_request.json
change_intent.json
revision_plan.json
candidate patch or new candidate
comparison.json
lineage.json
```

A revision may patch:

- a structured feature graph;
- a sandboxed model program;
- declared parameters;
- an Assembly Job definition.

It must preserve requested changes separately from validator-driven repairs.
Creating a successful revision does not automatically replace the accepted
result.

## Assembly artifacts

Assembly candidates consume exact accepted part-result identities.

Possible artifacts:

- `assembly_candidate.json`;
- `assembly_execution_request.json`;
- placement and constraint source;
- native assembly file;
- `assembly.step`;
- `assembly_validation.json`;
- `assembly_reviewable_result.json`.

Reports must distinguish:

- placement validation;
- bounding-box heuristics;
- actual geometric interference;
- constraint or degree-of-freedom checks;
- fit, tolerance, or motion checks.

Only checks that ran may be claimed.

## Deliverable Package

Primary manifest:

- `deliverable_package.json`.

May reference:

- accepted part STEP;
- accepted assembly STEP or native file;
- STL and preview assets;
- BOM;
- PDF/SVG drawings;
- validation and limitation reports.

Every item records:

- human purpose;
- source accepted result;
- source Run;
- generator or tool;
- validation state;
- deliverable role.

Drawing output is not trusted solely because a PDF or SVG exists. It must
reference an accepted model and state which dimensions or annotations are
generated, measured, or manually reviewed.

## State dimensions

Projections keep these concepts separate:

- `input_status`;
- `design_status`;
- `execution_status`;
- `result_status`;
- `agent_status`;
- `user_decision_status`;
- `assurance_mode`;
- `capability_mode`;
- `stale_status`.

Compatibility `status` fields may remain but must not be derived from filenames
alone.

## Provenance and path safety

Every public artifact reference preserves:

- source Work and Run;
- Part Job or Assembly Job where applicable;
- checkpoint and trust role;
- original, Agent, user override, validator, or tool source;
- relative controlled identity;
- validation status.

Public routes and UI use safe ids and allowlisted artifact identities. They do
not expose arbitrary browsing, absolute paths, secrets, provider payloads, or
unrestricted model-program execution.

## Compatibility

The following legacy artifacts remain readable during migration:

- `prompt.txt`;
- `requirement*.json`;
- `planning_artifact.json`;
- `assembly_plan.json`;
- `part_create_request.json`;
- `part_request_review.json`;
- `reviewed_part_handoff.json`;
- `part_execution_request.json`;
- `cad_ir_draft.json`;
- `input_ir.json`;
- `part_result_review.json`;
- `workflow_review.json`.

Compatibility artifacts do not define the target product phases. New code
should write new contracts or an explicit versioned compatibility projection.
