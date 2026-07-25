# FINAL PRD: CadFlow Workflow-first Parametric CAD

Status date: 2026-07-25.

## Product direction

CadFlow is a local, IR-driven workflow product that turns a natural-language or
structured engineering request into reviewable, traceable parametric CAD
results.

CadFlow is not a prompt-to-code tool, a raw artifact browser, a complete
industrial CAD replacement, or an unbounded autonomous coding agent. Agent or
provider output reaches CAD execution only through validated structured
contracts. Deterministic services remain authoritative for model generation,
inspection, and export.

## Product objects

- Workspace contains many Works and safe workspace configuration.
- Work is one mutable user-facing engineering task.
- Run is one append-only execution attempt and audit record.
- Part Job is one intended part with multiple attempts and one explicit accepted-result pointer.
- Current Work aggregates the actionable active lineage.
- Run Snapshot is immutable and read-only.
- Active lineage and accepted part results are separate.

## Canonical workflow

```text
Prompt / Requirement Input
  -> Requirement
  -> Clarification when required
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
```

Simple single-part work may present compact Planning and Assembly Plan
information, but checkpoint responsibilities remain distinct.

## Trusted CAD boundary

```text
reviewed part handoff
  -> bounded create_part_ir episode or deterministic proposer
  -> CAD IR draft
  -> local schema and policy validation
  -> isolated deterministic candidate execution
  -> geometry inspection and result validation
  -> validated reviewable result or typed safe block
```

Provider-generated Python, shell, CadQuery, or arbitrary file operations cannot
bypass CAD IR.

## State and artifact semantics

CadFlow does not infer product trust from file presence.

- Input state records whether upstream evidence is missing, unverified, accepted, or stale.
- Execution state records not started, running, completed, skipped, blocked, or failed.
- Result state records draft, generated, contract complete, ready for review, accepted, stale, or no trusted result.
- Agent review and user approval are separate.
- Only explicit user approval updates `accepted_part_results`.

Artifacts are projected as:

- accepted inputs;
- reviewable attempt outputs;
- final approved deliverables;
- diagnostic evidence from failed or blocked attempts.

Failed candidates execute in isolation. A final failure preserves reports,
trace, CAD IR, and validation evidence but does not publish `model.py`, STEP,
STL, or preview files as Run products.

## Execution modes

### Contract

- validates and records CAD IR;
- reports `contract_complete` or `execution_skipped`;
- does not expect STEP/STL;
- is not a failure;
- does not offer part-result approval without a reviewable generated result.

### Full

- validates CAD IR;
- executes deterministic CAD generation;
- may produce STEP as the primary CAD artifact and STL as a derived artifact;
- requires Part Result Review and explicit user approval before Work-level delivery.

### Agentic

Provider-backed bounded `create_part_ir` remains a prototype milestone, not a
production-usable capability. Deterministic fallback must be labeled.

## Current product scope

Usable:

- local Workspace/Work creation and append-only Run storage;
- deterministic Golden single-part Contract and Full flows;
- CAD IR validation and deterministic CadQuery generation;
- candidate selection through versioned Assembly Plan override;
- Part Review, Part Result Review, explicit approval, and accepted-result pointers;
- controlled artifact reads and Run Snapshot inspection;
- bounded deterministic `create_part_ir` episode infrastructure.

Partial:

- Workflow Cockpit browser usability and complete bilingual acceptance;
- narrow allowlisted revision/rework;
- feature-level geometry inspection;
- skill and knowledge runtime ownership enforcement.

Not usable:

- provider-backed agentic CAD as an accepted product path;
- full assembly generation or assembly STEP export;
- multi-part batch generation;
- motion, strength, tolerance-stack, fit, DFM/DFA, or safety release;
- arbitrary external STEP editing or mesh reverse engineering.

## Output contracts

Successful Full part result:

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

Failed part attempt:

```text
input_ir.json or best CAD IR draft
report.json
report.md when produced
agent_trace.json
structured validation / episode evidence
```

Failure output must not contain product-positioned STEP/STL/model source or
preview files.

Compatibility workflow outputs may remain for examples and migration, but do
not redefine Current Work, approval, or Deliverables semantics.

## Check levels

- L0 Playground: implemented baseline generation and artifact/geometry facts.
- L1 Maker: report framework only; not complete printability validation.
- L2 Engineering: reserved; no engineering release claim.
- L3 Industrial: reserved; no industrial DFM/DFA claim.
- L4 Safety Critical: reserved; never automatically released.

## Current acceptance gate

- Full and Contract Golden flows preserve canonical status semantics.
- Failed validation publishes no untrusted product files.
- Reviewable output does not become accepted without an explicit Work pointer.
- Deliverables contain only approved accepted-part results.
- Current Work remains actionable and Run Snapshot remains read-only.
- Candidate selection preserves old Runs and accepted results and marks downstream stages stale.
- Automated regression is green.
- Workflow Cockpit is not marked usable until real-browser action, localization, failure/recovery, Snapshot, 1024px, and mobile checks pass.

## Near-term roadmap

1. Close Workflow Cockpit browser and bilingual usability acceptance.
2. Implement the typed Skill and Knowledge Registry.
3. Prototype provider-backed bounded `create_part_ir` behind existing validators.
4. Progress multiple Part Jobs before any assembly-generation claim.

The detailed architecture, contracts, readiness, and milestone sources remain:

- `docs/architecture/cadflow-canonical-product-architecture.md`;
- `docs/architecture/agent-skill-knowledge.md`;
- `docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`;
- `docs/workflow_contract.md`;
- `docs/status/current-product-readiness.md`;
- `docs/roadmap/milestones.md`.
