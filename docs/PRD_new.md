# PRD: CadFlow Workflow-first Parametric CAD

Status date: 2026-07-25.

`FINAL-PRD.md` is the concise product baseline. This document records the
current product requirements without redefining the canonical architecture in
`architecture/cadflow-canonical-product-architecture.md`.

## 1. User problem

A user needs to turn an engineering request into a CAD result while retaining:

- the interpreted requirement and assumptions;
- design and part-decomposition decisions;
- the exact part selected for modeling;
- validated CAD IR;
- deterministic execution and inspection evidence;
- explicit review and approval;
- immutable attempt history and a clear recovery path.

A directory containing generated files is not sufficient because it does not
answer which result is current, trusted, approved, stale, failed, or safe to
deliver.

## 2. Product outcome

For every Work, the primary experience must answer:

1. What is being created?
2. What checkpoint is current?
3. Which accepted inputs were used?
4. Did execution complete, skip, block, or fail?
5. Is there a generated result, a reviewable result, or an approved deliverable?
6. What limitation matters?
7. Does the user need to decide anything?
8. What is the recommended next action and visible success condition?

## 3. Product model and workflow

CadFlow uses Workspace, Work, Run, and Part Job. A Work is mutable; Run evidence
is append-only. Current Work is actionable; Run Snapshot is read-only.

The required checkpoint sequence is:

```text
Prompt -> Requirement -> Clarification -> Planning / Design Brief
-> Assembly Plan / Candidate Parts -> Explicit Part Selection
-> Part Request -> Part Review -> Reviewed Handoff -> CAD IR Draft
-> CAD IR Validation / Part Modeling -> Part Result Review
-> User Approval -> Work-level Review -> Rework / Next Part -> Deliverables
```

Stages may be visually compact, but responsibilities may not be merged or
silently skipped.

## 4. Functional requirements

### Requirement and planning

- Preserve the original prompt in a Run.
- Produce structured requirements with assumptions and focused missing information.
- Keep requirement interpretation separate from design decomposition.
- Preserve assembly interfaces and distinguish generated candidates from reference-only components.
- Candidate inspection is read-only; candidate selection is explicit and versioned.

### Reviewed part handoff

- Scope exactly one part.
- Preserve relevant requirement and assembly context.
- Require Part Review before creating the Reviewed Handoff.
- Never replace unknown intent with an unrelated template.

### CAD IR and execution

- Agent/provider output is structured CAD IR only.
- Local validators decide whether CAD execution is allowed.
- Candidate execution is isolated from the Run product directory.
- Only a validated selected candidate is materialized as `model.py`, STEP, STL, and preview.
- A terminal failure preserves structured evidence but publishes no untrusted product files.
- Maximum deterministic repair attempts remain bounded.

### Reviews and approval

- Part Result Review is an agent/system assessment.
- `accepted_for_preview` means ready for user review, not approved.
- User approval is an explicit append-only action.
- Only approval updates `accepted_part_results[part_id]`.
- Creating or reviewing a result never approves it automatically.

### Products and Deliverables

- Reviewable outputs remain attached to their immutable Run.
- Failed attempt files are diagnostics.
- Work Products and Deliverables include only approved accepted-result pointers.
- One accepted part does not imply a complete assembly.
- Contract mode does not expect STEP/STL and is not a missing-output failure.

### Workflow Cockpit

- Current Work and Run Snapshot are visually and behaviorally distinct.
- One dominant recommended action is shown.
- Write actions use confirmation, pending, duplicate protection, backend execution, refreshed projection, postcondition verification, and persistent success/failure feedback.
- Primary UI does not expose absolute paths, backend keys, raw enums, provider payloads, or unrestricted artifact browsing.
- Chinese and English primary paths remain semantically consistent.

## 5. State contract

Implementations and projections keep these dimensions separate:

```text
input_status
execution_status
result_status
agent_review_status
user_review_status
capability_mode
```

Compatibility `status` fields may remain, but must be derived from these
dimensions rather than from filenames.

## 6. Output contract

Validated Full result:

```text
input_ir.json
model.py
model.step
model.stl
report.json
report.md
preview.png
agent_trace.json
logs/runtime.json
```

Failed result:

```text
input_ir.json or best structured draft
report / validation evidence
agent_trace / episode evidence
```

No product-positioned `model.py`, STEP, STL, or preview may remain after final
validation failure.

## 7. Capability boundary

Currently usable:

- deterministic Golden single-part flow;
- supported CAD IR part families;
- local workflow storage, lineage, reviews, and explicit accepted pointers;
- Contract and Full execution semantics;
- controlled artifact viewing and downloading.

Partial or prototype:

- complete browser acceptance;
- generalized natural-language coverage;
- bounded agent episode beyond deterministic proposer behavior;
- revision/rework beyond allowlisted fields;
- deeper feature-level inspection.

Not currently usable:

- provider-backed agentic CAD product path;
- full assembly generation;
- multi-part batch generation;
- strength, motion, fit, tolerance-stack, DFM/DFA, GD&T, FEA, or safety release;
- arbitrary external CAD editing.

## 8. Acceptance requirements

- Failed validation leaves no product files.
- A generated STEP without explicit approval remains `needs_review`.
- Approved Deliverables resolve through `accepted_part_results`.
- Contract modeling is `execution_skipped` / `contract_complete`.
- Run history remains immutable.
- Upstream selection changes mark downstream stages stale.
- Tests cover the state dimensions and product trust boundary.
- Browser acceptance is reported honestly and separately from automated tests.

## 9. Current roadmap

1. Finish Workflow Cockpit action, failure/recovery, localization, Snapshot, 1024px, and mobile acceptance.
2. Implement a typed Skill and Knowledge Registry.
3. Add one provider-backed bounded CAD IR proposer behind the same contracts and validators.
4. Add multiple Part Job progression before assembly execution.

Historical version-number roadmaps under `docs/project/` are reference material
only and must not override `docs/roadmap/milestones.md`.
