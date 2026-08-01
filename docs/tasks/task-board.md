# CadFlow Task Board

Status date: 2026-08-01.

The ordered roadmap is `docs/roadmap/milestones.md`. Execution starts at
`docs/tasks/agent-start-here.md`. Do not pull later UI, assembly, or assurance
work ahead of the current milestone without an explicit architecture decision.

## M0 — Documentation correction

- [x] Reframe CadFlow as an Agent-first CAD design workbench.
- [x] Preserve Workspace / Work / Run / Part Job and explicit acceptance.
- [x] Add Assembly Job and Deliverable Package target objects.
- [x] Replace the fixed user workflow with four phases.
- [x] Define structured feature-graph and sandboxed model-program paths.
- [x] Define Agent-selected actions, Context Broker, and Tool Broker authority.
- [x] Rewrite PRD, canonical architecture, workflow contract, Agent architecture,
  roadmap, task board, and readiness.
- [x] Move old Workflow Cockpit work out of the current product milestone.
- [x] Complete repository-wide link and terminology checks.
- [x] Remove competing legacy PRD, architecture, roadmap, and milestone files.

## M1 — Runtime consolidation and domain model

- [x] Write an architecture decision for the one product orchestrator.
  - `../architecture/decisions/0001-single-product-orchestrator.md`
- [x] Inventory all current create, reviewed-part, revision, text, and IR entry
  points and classify product, compatibility, evaluation, or removable.
  - `../architecture/runtime-entry-point-inventory.md`
- [x] Define schema-versioned Work, Part Job, Assembly Job, and Deliverable
  Package records.
  - `../architecture/domain-record-contracts.md`
- [x] Change Part Job from one `run_id` to ordered attempt references.
- [x] Keep accepted-result pointers separate from active design lineage.
- [x] Add explicit artifact ids, trust roles, and source references.
- [x] Implement one top-level `WorkOrchestrator` and one deterministic
  compatibility port for the existing pipeline.
- [x] Route target-product Work mutations through the orchestrator:
  Work creation, Intent, Part Job attempts, candidate selection, lineage, and
  accepted-result pointers.
- [x] Replace recursive filename-driven product state with manifest/artifact
  references.
  - [x] Add the manifest-only target projector and its contract tests.
  - [x] Isolate legacy Run metadata translation in an explicit read-only
    compatibility projector; filename presence alone assigns no trust.
- [x] Add a legacy Work/Run-reference compatibility projector.
- [x] Add contract tests for ordered attempts, acceptance/lineage separation,
  immutable Run evidence, and manifest-only product state.
- [x] Preserve current failure isolation and path-safety behavior.
- [x] Keep the full deterministic regression suite green.
  - 2026-07-27: `550 passed, 2 skipped`.
- [x] Complete M1 usage acceptance.
  - Golden contract and full modes passed.
  - One real Part Job retained two attempts and accepted the older reviewable
    result without changing active root/leaf or rewriting Run evidence.

## M2 — Agentic design vertical slice

### Registry and episode

- [x] Define the minimal `design_part` skill contract.
- [x] Implement a typed registry for actions, tools, context, knowledge, budgets,
  and stop reasons used by that skill.
- [x] Remove duplicate runtime prompt text for the selected vertical slice.
  - The new action request is compiled from the typed registry; legacy provider
    operations retain compatibility prompt assembly.
- [x] Implement provider-selected actions rather than a fixed proposer sequence.
  - The provider-selected loop is product-routed for validation only; CAD
    execution and publication remain open.
- [x] Persist concise actions, observations, candidates, and budget use.
- [x] Route an owned Part Job attempt through `WorkOrchestrator` and a typed
  `AgentDesignPort` without granting execution or publication authority.
- [x] Bind path-safe request ids to canonical request fingerprints and replay
  persisted results without a second provider invocation or Work rewrite.
- [x] Register only typed candidate/observation/diagnostic artifact references
  and prove lineage, acceptance, Assembly, Deliverable, Part Job, and Run state
  remain unchanged.
- [x] Verify the validation-only product route with targeted and full regression
  tests.
  - 2026-08-01: `156 passed` targeted; `574 passed, 2 skipped` full suite.
- [x] Complete scripted-provider file-level acceptance for the product route.
  - `../status/m2-work-design-episode-package-acceptance.md`

### Context Broker

- [x] Supply active intent, Part Job, interfaces, accepted constraints, previous
  candidates, and observations through semantic keys.
- [x] Reject arbitrary paths and unrelated Work context.
- [x] Record provenance and trust role for supplied context.
- [x] Keep the complete regression suite green for package 1.
  - 2026-08-01: `558 passed, 2 skipped`.
- [x] Complete scripted-provider file-level acceptance for package 1.
  - Validated contract evidence was persisted; no STEP/CAD product was
    generated or claimed.

### Tool Broker and sandbox

- [x] Implement a typed CadFlow-owned Tool Broker catalog.
- [x] Route `design_part` structured-contract validation through Broker
  authorization and structured observations.
- [x] Add an explicit Windows model-program capability gate that fails closed
  before source, candidate-directory, or process side effects.
- [x] Verify the Tool Broker package with targeted and full regression tests.
  - 2026-08-01: `23 passed` targeted; `565 passed, 2 skipped` full suite.
- [x] Complete local Windows fail-closed acceptance.
  - `../status/m2-tool-broker-package-acceptance.md`
- [ ] Choose the first supported model-program API: CadQuery or build123d.
- [ ] Define allowlisted imports and prohibited APIs.
- [ ] Implement isolated candidate directory and execution worker.
- [ ] Disable network access.
- [ ] Block subprocess, shell, dynamic dependency installation, and writes
  outside candidate storage.
- [ ] Enforce time, memory, process, and output-size limits.
- [ ] Capture source, parameters, stdout/stderr, outputs, and exit state.
- [ ] Return structured observations to the Agent.

### Publication and UX slice

- [ ] Reuse STEP-first geometry inspection and output validation.
- [ ] Publish only locally validated candidates as reviewable results.
- [ ] Show capability mode, assumptions, observations, and one next action.
- [ ] Require explicit user acceptance.
- [ ] Support revision as a child Run.

### Benchmarks

- [ ] Define at least five non-template part prompts.
- [ ] Include brackets or mechanisms that cannot be solved by adding a new
  current `part_type` mapping.
- [ ] Require at least two observation-driven repairs.
- [ ] Require at least one focused user question.
- [ ] Add sandbox violation tests.
- [ ] Record provider/model and deterministic validator evidence separately.

## M3 — Feature-graph geometry contract

- [ ] Write v2 schema for parameters, datums, sketches, and ordered features.
- [ ] Implement extrude, revolve, holes, pockets, booleans, fillet/chamfer, and
  patterns.
- [ ] Add named interfaces and functional references.
- [ ] Declare backend capabilities by operation.
- [ ] Build deterministic executor and validator.
- [ ] Add legacy CAD IR migration adapter.
- [ ] Add feature-level revision and comparison.
- [ ] Benchmark feature graph against the sandboxed model-program path.

## M4 — Multi-part and assembly

- [ ] Support multiple accepted Part Jobs in one Work.
- [ ] Define exact accepted-result inputs for Assembly Job.
- [ ] Add placements, mates, joints, fasteners, reference components, and
  clearances.
- [ ] Integrate assembly execution.
- [ ] Generate native assembly and/or assembly STEP.
- [ ] Generate BOM.
- [ ] Mark assembly stale when an accepted part changes.
- [ ] Separate bounding-box heuristics from real geometric validation.
- [ ] Add a three-generated-part assembly acceptance example.

## M5 — Deliverables and drawings

- [ ] Define Deliverable Package manifest.
- [ ] Integrate `scripts/freecad_techdraw.py` through a controlled tool.
- [ ] Generate PDF/SVG drawings from accepted part results.
- [ ] Add assembly drawing or exploded-view support where feasible.
- [ ] Record dimension and annotation provenance.
- [ ] Package accepted STEP, assembly, BOM, drawings, and reports.
- [ ] Test drawing failure independently from model acceptance.

## M6 — Workbench UX

- [ ] Define the four-phase page/view-model contract.
- [ ] Put design conversation and geometry preview first.
- [ ] Show candidate alternatives and observation-driven repair.
- [ ] Show Part Jobs, accepted results, and assembly readiness.
- [ ] Move the fixed Workflow graph to compatibility/Diagnostics.
- [ ] Preserve Current Work and Run Snapshot boundaries.
- [ ] Verify pending, success, failure, and recovery in a real browser.
- [ ] Verify Chinese and English primary flows.
- [ ] Verify desktop, 1024px, and 390–430px layouts.

## Preserved regression responsibilities

- [ ] Historical Runs remain immutable.
- [ ] Failed candidates publish no trusted product files.
- [ ] Reviewable is distinct from accepted.
- [ ] Accepted part results may be sibling Runs.
- [ ] Contract-mode legacy examples remain honestly labeled.
- [ ] Local services bind to `127.0.0.1` by default.
- [ ] Public exposure remains explicit and off by default.
