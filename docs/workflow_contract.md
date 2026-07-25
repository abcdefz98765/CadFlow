# Workflow Artifact Contract

## Authority

This document defines the current structured handoffs between CadFlow checkpoints.

It does not define the product object model or reorder workflow stages. Those responsibilities belong to:

- `architecture/cadflow-canonical-product-architecture.md`

Agent behavior and knowledge ownership belong to:

- `architecture/agent-skill-knowledge.md`

## General rules

CadFlow advances through structured artifacts, not by repeatedly re-reading the original prompt.

Each checkpoint must:

- consume accepted upstream artifacts;
- validate input sufficiency for its own responsibility;
- preserve source intent and provenance;
- write a structured output or a typed safe block;
- avoid filling decisions owned by another checkpoint;
- expose assumptions and missing information instead of hiding them;
- preserve immutable Run evidence.

Natural language enters at explicit user-input or revision boundaries. Deterministic CAD execution consumes validated CAD IR.

## Canonical handoff sequence

    prompt.txt
      -> requirement.json or requirement_vN.json
      -> planning_artifact.json / design_brief.json
      -> assembly_plan.json when decomposition is required
      -> part_create_request.json
      -> part_request_review.json
      -> reviewed_part_handoff.json
      -> part_execution_request.json
      -> cad_ir_draft.json
      -> input_ir.json after validation
      -> child Run model/report artifacts in Full mode
      -> part_result_review.json
      -> append-only user review and Work accepted-result pointer
      -> workflow_review.json / workflow_review.md
      -> rework child Run when explicitly requested

Simple single-part flows may use a compact planning path, but artifact responsibility remains unchanged.

## Prompt

`prompt.txt` preserves the original user input for one root or revision Run.

Rules:

- never overwrite an earlier prompt;
- downstream stages consume structured artifacts rather than treating prompt text as authoritative;
- a revision request starts a new child Run or explicit revision record.

## Requirement

Primary artifacts:

- `requirement.json`;
- `requirement_clarification.json`, when user answers are required;
- `requirement_vN.json`, when an accepted clarification or override creates a new active requirement version.

The requirement contract records:

- scope and object goal;
- constraints and known dimensions;
- assumptions;
- missing or risky information;
- focused clarification questions;
- flow decision: proceed, clarify, or block safely.

The original requirement artifact remains immutable.

## Planning and design brief

Primary artifacts:

- `design_brief.json`, when the detailed design-planner path is used;
- `planning_artifact.json`;
- candidate-plan artifacts where the selected pipeline supports them.

Planning records:

- engineering route and scope;
- design goals and capability boundaries;
- candidate strategies and concise trade-offs;
- selected or proposed part route;
- interface, datum, dependency, and risk summaries;
- gate state and unresolved upstream decisions.

Planning does not execute CAD or claim generated outputs.

## Assembly Plan and candidate selection

Primary artifacts:

- `assembly_plan.json`;
- optional human-readable `assembly_plan.md`;
- validated versioned overrides under the controlled edit location;
- candidate-selection metadata.

The Assembly Plan records:

- generated candidate parts;
- reference-only components;
- selected candidate;
- interfaces and preserved assembly context;
- unsupported or blocked candidates.

Opening a candidate is read-only. Explicit selection writes a validated override, preserves the original plan and old Runs, keeps accepted results, and marks dependent checkpoints stale.

## Part Request

Primary artifact:

- `part_create_request.json`.

It scopes exactly one selected part and records:

- part id and engineering role;
- intended result scope;
- constraints and interfaces;
- preserved assembly context;
- assumptions and blocked reasons.

It does not create CAD.

## Part Review

Primary artifact:

- `part_request_review.json`.

It evaluates whether the Part Request is coherent and ready for modeling.

Result semantics include:

- approved;
- needs revision;
- blocked.

This is a review of the modeling request, not a review of generated geometry.

## Reviewed Handoff

Primary artifact:

- `reviewed_part_handoff.json`.

It freezes the approved part brief and the context passed to the CAD-generation episode.

It must preserve:

- source part id and role;
- accepted scope;
- relevant constraints and interfaces;
- assembly context;
- assumptions;
- capability mode and provenance.

## Part execution request

Primary artifact:

- `part_execution_request.json`.

This is the local, sanitized execution envelope derived from the Reviewed Handoff. It identifies exactly one part and the allowed CAD IR operation.

It is not provider-generated code and does not authorize arbitrary execution.

## CAD IR draft and validation

Primary artifacts:

- `cad_ir_draft.json`;
- bounded Agent Episode artifacts;
- structured validation feedback;
- `input_ir.json` only after local validation succeeds.

Flow:

    reviewed_part_handoff
      -> bounded create_part_ir episode
      -> cad_ir_draft
      -> validate_input_ir_draft / validate_ir
      -> validated input_ir or typed safe block

Rules:

- the agent may propose or repair structured CAD IR;
- local validators decide whether it is executable;
- provider-generated Python, shell, or CadQuery cannot bypass CAD IR;
- no unrelated fallback part may replace the reviewed intent;
- validation failure preserves the best draft and evidence;
- invalid CAD IR does not produce STEP/STL.

## Part Modeling

Full mode consumes validated `input_ir.json` and may write:

- `model.py` as a generated implementation artifact;
- `model.step`;
- `model.stl` when requested;
- `report.json` and `report.md`;
- `agent_trace.json`;
- `logs/runtime.json`.

Contract mode writes validated `input_ir.json` and explicit `contract_complete` or `execution_skipped` status. STEP/STL are not expected.

Candidate execution is isolated from the Run product directory. Candidate files
become Run-level product files only after the selected candidate passes local
validation. If execution or validation ultimately fails, CadFlow preserves the
CAD IR, structured report, trace, and validation evidence, but does not leave
`model.py`, STEP, STL, or preview files in the product location.

Part Modeling does not approve its own result or claim assembly completion.

## Part Result Review

Primary artifact:

- `part_result_review.json`.

It compares one child result with the Reviewed Handoff and records:

- part id and child Run;
- product artifact availability;
- result scope;
- validation and execution status;
- limitations;
- accepted-for-preview, needs-revision, blocked, skipped, or failed semantics.

Creating this artifact does not update the Work accepted-result pointer.

## User review and accepted result

Stage reviews are append-only:

    reviews/<stage>/review_NNN.json

A latest `stage_review.json` materialization may remain for compatibility with the explicit rework pipeline.

Only explicit user approval updates:

- `accepted_part_results[part_id]` in the Work manifest.

Approval does not modify the child Run or its STEP/STL, accept sibling parts, or imply full assembly completion.

## Artifact trust and product state

File presence is not a business status. Projections keep these concepts
separate:

- `input_status` — missing, available but unverified, accepted upstream, or stale;
- `execution_status` — not started, running, completed, skipped, blocked, or failed;
- `result_status` — not created, generated, contract complete, ready for review, accepted, stale, or no trusted result;
- `agent_review_status` — the Part Result Review conclusion;
- `user_review_status` — not reviewed, approved, needs revision, or blocked;
- `capability_mode` — contract, full, deterministic fallback, or agentic where supported.

User-facing artifact roles are:

- accepted input — active upstream evidence consumed by a checkpoint;
- attempt output — a validated result available for review but not yet approved;
- final output — an explicitly approved result referenced by the Work;
- diagnostic evidence — reports and traces from blocked or failed attempts.

`accepted_for_preview` is an agent/result-review conclusion. It is not user
approval and does not update `accepted_part_results`.

## Work-level Workflow Review

Primary artifacts:

- `workflow_review.json`;
- `workflow_review.md`.

The review summarizes:

- active lineage;
- Part Jobs and accepted results;
- current checkpoint states;
- missing results and limitations;
- relevant risks and valid next actions.

It is a product-level conclusion, not a raw aggregation of internal diagnostics.

## Deliverables

Work-level Deliverables are derived only from explicit approved
`accepted_part_results` pointers. Reviewable outputs remain available from the
Part and Run Snapshot surfaces. Failed-attempt artifacts remain diagnostics and
never appear as Work deliverables.

## Rework and revision

Rework or revision creates a child Run and preserves its parent.

Common artifacts include:

- `revision_request.json`;
- `change_intent.json`;
- `revision_plan.json`;
- `patch.json`;
- `comparison.json`;
- `lineage.json`;
- `revision_report.md`.

Parent artifacts remain immutable. Structured changes record before/after values where possible. Unsupported revisions block safely rather than fabricating a child model.

See `architecture/revision-workflow.md` for the specialized revision contract.

## Provenance and path safety

Every projected artifact must preserve:

- source Work, Run, and Stage;
- original or override source type;
- relative artifact identity;
- validation status where relevant.

Public UI and route contracts use safe ids and allowlisted artifact names. They do not expose arbitrary filesystem paths, secrets, provider payloads, or raw transcripts.

## Compatibility paths

Legacy text, normalized-provider, and deterministic example pipelines may remain for tests, migration, evaluation, and fallback.

They must not redefine the canonical user workflow, silently become the primary product architecture, or claim capabilities beyond their actual artifacts.
