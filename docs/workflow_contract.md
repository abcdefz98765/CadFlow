# Workflow Contract

Purpose: define CadFlow workflow responsibilities, handoff artifacts, and
stage boundaries.

CadFlow is organized around explicit artifacts, not around re-parsing a prompt
at every step. The main future UX is LLM-first, artifact-first, and
validation-backed: the agent proposes intent, assumptions, candidate plans, and
revisions; CadFlow validates, normalizes, executes, compares, and records.

```text
user prompt -> intent -> design brief -> candidate plans -> selected plan
  -> CAD IR -> part modeling -> review -> outputs
```

Each stage owns one decision layer and hands off structured data to the next
stage. Natural language is accepted at the edge of the system, but downstream
CAD generation consumes `requirement.json` and `input_ir.json`.

Every stage starts with an input-sufficiency gate before doing its main work.
The gate answers three questions:

- Is the upstream package complete enough for this stage's declared
  responsibilities?
- If not, which stage owns the missing decision?
- Can the current stage safely continue with a recorded assumption or internal
  retry, or must it return the package upstream?

Stages must not fill missing upstream-owned decisions by re-reading free-form
text, design notes, or earlier prompts.

## Entry Points

### Agent Create Pipeline

`run_agent_create_pipeline(...)` is the documented v0.5 LLM-shaped create entry
point.

```text
prompt.txt
  -> intent.json
  -> design_brief.json
  -> candidate_plans.json
  -> selected_plan.json
  -> input_ir.json
  -> run_ir_pipeline(...)
  -> report.json/report.md/agent_trace.json
```

The planning artifacts are distinct:

- `intent.json` records interpreted user intent, recognized part family,
  constraints, assumptions, and open questions.
- `design_brief.json` turns intent into design goals, functional requirements,
  geometry constraints, validation targets, and planning assumptions.
- `candidate_plans.json` records multiple candidate design plans and tradeoffs.
- `selected_plan.json` records the candidate chosen for CAD IR conversion.
- `input_ir.json` is the validated CAD generation source of truth.

`agent_trace.json` records the agent create stage list and selected candidate
under `agent_create` so the Web Workflow Console can display planning stages
without inventing a separate state store.

### Provider Normalized Create Pipeline

`run_provider_normalized_create_pipeline(...)` is the recommended
provider-backed create workflow option.

```text
prompt
  -> provider extraction
  -> local requirement/planning compiler
  -> deterministic CAD IR conversion
  -> run_ir_pipeline(...)
  -> report.json/report.md/agent_trace.json
```

This path is explicit `extract_then_compile` mode. The provider extracts
structured intent, fields, and constraints; CadFlow compiles and validates
`requirement.json` and `planning_artifact.json` locally before CAD IR
conversion. Provider-generated CAD IR, provider-generated CadQuery/Python code,
and arbitrary provider fields are not accepted as generation authority.

`run_provider_create_pipeline(...)` remains available in `strict` mode for
provider contract compliance testing:

```text
strict:
  Direct provider-to-CadFlow-contract mode.
  Useful for provider/schema compliance testing.
  Not the recommended default user path.

extract_then_compile:
  Provider extracts structured intent/fields/constraints.
  CadFlow compiles and validates internal contracts locally.
  Recommended provider-backed create workflow path.
```

The fixed provider eval interpretation is intentionally narrow: 8/10 pipeline
success + 2 expected blocked means all supported eval cases passed and
unsupported/unsafe cases blocked correctly. It does not claim production
readiness.

### Provider Normalized Design Create Pipeline

`run_provider_normalized_design_create_pipeline(...)` is a small normalized
design-planner MVP. It extends the provider-backed path with local design
artifacts while keeping execution constrained:

```text
prompt
  -> provider extraction of design intent / constraints / assumptions
  -> local compiler creates intent.json
  -> local compiler creates design_brief.json
  -> local compiler creates candidate_plans.json
  -> deterministic candidate selection
  -> local planning_artifact.json for supported single-part requests
  -> deterministic CAD IR conversion for supported single-part requests
  -> run_ir_pipeline(...) for supported single-part requests
```

The provider may contribute design-level signals, but the official
`intent.json`, `design_brief.json`, `candidate_plans.json`, `selected_plan.json`,
`requirement.json`, `planning_artifact.json`, and `input_ir.json` artifacts are
compiled and validated by CadFlow. Provider-generated CAD IR and
CadQuery/Python code are not accepted.

For `multi_part` or `assembly` scope, this MVP writes a local
`assembly_plan.json` and blocks before part generation. `assembly_plan.json` is
a planning artifact only: it preserves sanitized parts, interfaces, fasteners,
clearance notes, risk notes, and blocked reasons. It does not mean CadFlow can
generate multi-part CAD, solve assembly constraints, or export a STEP assembly.
Those capabilities remain future work, and the workflow must not fabricate
`input_ir.json` for an unsupported assembly request.

Assembly plans use a deliberately small, non-executable surface. Parts expose
only `part_id`, `role`, `generation_strategy`, `part_status`,
`supported_candidate`, `part_brief`, and `blocked_reasons`. Interfaces expose
only `from`, `to`, `kind`, and `notes`, with `kind` constrained to known
advisory labels such as `screw_fastened`, `pinned_joint`, `sliding_fit`,
`snap_fit`, `stacked`, or `unknown`. Reports include sanitized quality counts
for assembly plans, parts, interfaces, fasteners, risk notes, and blocked
reason codes.

`run_assembly_part_request_pipeline(...)` is the planning-only bridge from an
existing `assembly_plan.json` toward future single-part generation:

```text
assembly_plan.json
  -> select one supported candidate part
  -> part_create_request.json
  -> ready_for_review or blocked_no_candidate_part
  -> part_request_review.json
  -> approved, needs_revision, or blocked
  -> reviewed_part_handoff.json
  -> ready_for_single_part_planning or blocked/needs_revision
  -> explicit reviewed single-part create
  -> one child normalized single-part CAD run
```

`part_create_request.json` is locally compiled and sanitized. It records one
candidate part, relevant interface constraints, preserved assembly context, and
diagnostic codes such as `part_request.created`,
`part_request.no_candidate_part`,
`part_request.reference_only_not_selectable`,
`part_request.blocked_part_not_selectable`, and
`part_request.interface_constraints_preserved`. It does not call
`run_ir_pipeline(...)`, does not write per-part `input_ir.json`, and does not
generate STEP/STL or CadQuery/Python code. Actual part-level CAD generation
remains future work.

`run_part_request_review_pipeline(...)` adds a local review gate before any
future part-level generation. It writes `part_request_review.json`,
`report.json`, `report.md`, and `agent_trace.json`. The review approves only
requests with a selected non-reference, non-blocked part, a reviewable
`part_brief`, no provider-generated CAD IR or code, no arbitrary provider
fields, and either preserved interface constraints or an explicit context where
interfaces are not needed. Incomplete assembly-derived requests return
`needs_revision`; reference-only, unsupported, safety-critical, or
provider-executable requests return `blocked`. This gate still does not call
`run_ir_pipeline(...)`, write `input_ir.json`, or generate CAD artifacts.

`run_reviewed_part_handoff_pipeline(...)` compiles an approved
`part_create_request.json` plus `part_request_review.json` into
`reviewed_part_handoff.json`. The handoff is locally compiled and sanitized; it
preserves the selected part brief, interface constraints, and assembly context
needed for future explicit single-part planning. Non-approved reviews,
reference-only parts, unsupported/blocked parts, missing assembly interfaces, or
provider-generated CAD IR/code remain blocked or `needs_revision`. This handoff
is still planning-only and does not call `run_ir_pipeline(...)`, write
`input_ir.json`, or generate STEP/STL artifacts.

`run_reviewed_part_single_create_pipeline(...)` is the first explicit execution
bridge from a reviewed assembly-derived part handoff into CAD generation. It
accepts exactly one `reviewed_part_handoff.json`, requires status
`ready_for_single_part_planning`, compiles a local `part_execution_request.json`,
then calls the existing `run_provider_normalized_create_pipeline(...)` for one
child single-part run directory. The bridge writes `lineage.json`,
`report.json`, `report.md`, and `agent_trace.json` that link back to
`assembly_plan.json`, `part_create_request.json`, `part_request_review.json`,
and `reviewed_part_handoff.json`. Non-ready, unsafe, reference-only, blocked,
unsupported, multi-part, or assembly-shaped handoffs are blocked before provider
or CAD execution. This bridge does not batch parts, generate assemblies, solve
assembly constraints, or export STEP assemblies.

`run_part_result_review_pipeline(...)` is a local deterministic review of that
one child single-part run. It consumes `reviewed_part_handoff.json`, the child
single-part run artifacts, and nearby lineage metadata, then writes
`part_result_review.json`, `report.json`, `report.md`, and `agent_trace.json`.
It checks that the child run exists, `model.step` exists, `model.stl` exists
when expected, `input_ir.json` and child `report.json` exist, only one
single-part child run was created, no batch or assembly artifacts were written,
lineage points back to `reviewed_part_handoff.json`, `part_create_request.json`,
and `assembly_plan.json` where available, and interface constraints are
preserved in metadata or prompt artifacts. It does not run CAD generation,
call providers, solve assembly constraints, export STEP assemblies, or
geometrically validate fit between parts.

The current Reviewed Part Single-Part E2E MVP is:

```text
multi-part prompt
  -> normalized provider design create
  -> assembly_plan.json
  -> part_create_request.json
  -> part_request_review.json
  -> reviewed_part_handoff.json
  -> one child single-part run
  -> model.step / model.stl
  -> part_result_review.json
```

The boundary remains explicit: this MVP does not generate a full assembly, does
not generate all parts, does not solve assembly constraints, does not export a
STEP assembly, and does not geometrically validate fit between parts yet.

### Text Pipeline Fallback

`examples/prompt_pipeline/` is a debug and exploration path from natural
language to generated artifacts.

```text
prompt -> requirement.json -> CAD IR -> model.step/model.stl -> report/trace
```

It is useful for parser and handoff development, legacy demos, and fallback
execution. It is not the main future UX and should not consume the majority of
v0.5+ product work.

### IR Pipeline

`examples/ir_pipeline/` and `src/ai_native_cad/pipeline/` are the current
single-part generation mainline.

```text
input_ir.json -> CADIR -> CAD Agent Loop -> STEP/STL/report/trace
```

The IR pipeline starts after requirements and planning have been normalized
into CAD IR. It does not re-interpret the user's original prompt.

### Legacy CADWorkflow

`src/ai_native_cad/workflow.py` and the legacy `CADWorkflow` shape remain for
compatibility with older demos and reports.

```text
input.md -> requirement.json -> plan.md -> part_spec.json -> model/review/exports
```

This path may be consolidated later, but this document only clarifies its
relationship to the IR-first mainline. It does not require runtime changes.

## Artifact Hierarchy

`requirement.json` is the first formal handoff artifact. It captures user
intent as structured, reviewable data after analysis, clarification,
assumptions, and overrides.

`input_ir.json` / `CADIR` is the CAD generation source of truth. It is narrower
than `requirement.json`: it contains the normalized part type, dimensions,
features, outputs, and check level needed for deterministic part generation.

`report.json` / `report.md` summarize what was generated and what was verified,
assumed, or left unverified.

`agent_trace.json` records loop execution: attempts, candidate status, failures,
repairs, measured validation targets, inspection summaries, and final
selection.

`source.input_text`, when present, is trace/debug data only. Downstream stages
must not re-parse it to override structured fields.

## Handoff Packages And Flow Conditions

Each transition passes a named package and has an explicit proceed condition.
When the condition is not met, the stage must either return to the owning stage
or record the limitation instead of silently inventing missing decisions.

### Rework Decision Model

Each stage boundary may record a structured `flow_decision` or
`rework_decision`:

- `action: proceed` means the package satisfies the next stage's entry
  condition.
- `action: return` means the current stage cannot own the missing decision and
  must route the package back to the owning stage.
- `action: retry` means the same stage can make an implementation-level repair
  without changing product intent or planning decisions.

The decision records `from_stage`, `to_stage`, `owner_stage`, and structured
`reasons`. Current single-part handoff ownership is:

- Requirement returns to the user / Requirement when structured requirement
  fields are incomplete for the requested check level.
- Planning returns to Requirement when topology, interface, motion, fit,
  manufacturing, assembly, or safety decisions need user confirmation.
- CAD IR returns to Planning when explicit part-level fields are missing,
  unsupported, or ambiguous.
- Part Modeling retries internally for implementation-level IR or mapping
  repairs that preserve the resolved design intent.
- Part Modeling returns to Planning when retries cannot realize the selected
  CAD IR or when a template/backend gap would require redesign.
- Assembly returns to Part Modeling for missing/invalid part artifacts and to
  Planning or Requirement for unresolved placement, interface, or high-risk
  assembly decisions.

Current gate artifacts:

- Requirement writes `requirement_status.flow_decision`.
- Planning writes `planning_artifact.flow_gate_status.rework_decision`.
- CAD IR validation writes pipeline `flow_decision` and, on failure,
  `agent_trace.rework_decision`.
- Part Modeling writes per-attempt `rework_decision` for retries and
  `agent_trace.final_flow_decision`.
- Assembly planning writes `assembly_plan.flow_decision`.
- Assembly validation writes `assembly_validation.flow_decision`.
- Review writes `report.flow_decision`.

### Requirement -> Planning

Package:

- `requirement.json`
- optional clarification answers and overrides already merged into structured
  fields

Proceed when:

- `requirement_status.complete_for_generation` is true, or unresolved items are
  non-blocking for the requested `check_level`.
- Any blocking topology, interface, safety, manufacturing, or assembly decision
  is represented in `follow_up_requests` and routed back to the user instead of
  being assumed.

### Planning -> CAD IR

Package:

- `requirement.json`
- `plan.md` and/or `planning_artifact.json`
- selected part intent, route, functional datums, template candidates,
  interfaces, conservative generation targets, and risk notes

Proceed when:

- The route is selected: single part, multi-part, assembly loop, or
  confirmation-needed.
- For each part entering CAD IR, the design choice is resolved enough to encode
  explicit part type, units, dimensions, features, interfaces, outputs, and
  check level.
- Open structural, motion, degree-of-freedom, or fit risks are recorded as
  planning risk notes or review targets. If they change topology or required
  interfaces, Planning returns to Requirement for confirmation.

### CAD IR -> Part Modeling

Package:

- `input_ir.json` / `CADIR`
- trace link to requirement/planning artifacts when available

Proceed when:

- CAD IR validates against schema and required fields.
- The IR is narrow enough to drive deterministic single-part generation.
- Unsupported or ambiguous fields are reported before generation, or routed back
  to Planning when they require design decisions.

### Part Modeling -> Assembly

Package:

- generated part artifacts
- part-level `report.json` / `report.md`
- `agent_trace.json`
- measured bounding boxes, validation status, and unresolved part issues

Proceed when:

- Required part artifacts exist or missing parts are explicitly marked as
  blockers.
- Geometry facts needed by Assembly, such as bounding boxes and artifact paths,
  are available or recorded as unverified.
- Part failures that affect placement, interfaces, or clearances are routed
  back to Part Modeling or Planning before assembly claims success.

### Part Modeling Rework Boundary

Part Modeling owns implementation-level failures only. It may retry or repair
when the selected CAD IR can still be realized without changing design intent:
backend execution errors, boolean/export failures, conservative mapping fixes,
or feature parameter repairs that preserve the requested topology, interfaces,
and dimensions.

Part Modeling must return to Planning for design/planning-level failures. This
includes unsupported `part_type`, unsupported feature names, unsupported
template/backend capability, feature parameter semantics the current generator
cannot map, or any recovery that would require changing topology, interfaces,
part structure, or resolved dimensions. In these cases the pipeline writes
`agent_trace.rework_decision` and report `rework_decision` with
`action: return`, `owner_stage: planning`, and `to_stage: planning`; candidate
generation and `fallback_simplified` redesign are not used.

CAD IR conversion remains narrow: it consumes only
`planning_artifact.selected_parts[].resolved_decisions` as geometry authority.
`planning_artifact.part_modeling_context` may be copied into trace context, but
Part Modeling cannot use it to override CAD IR geometry fields.

### Assembly -> Review

Package:

- `assembly_plan.json` / `assembly_plan.md`
- `assembly.json`
- `constraint_assembly.json`
- part report summaries and assembly validation results

Proceed when:

- Required manufactured and reference components are identified.
- Placement relationships, required contacts, clearances, allowed overlaps, and
  unresolved questions are recorded.
- Missing high-risk assembly decisions are blocked or returned to Requirement /
  Planning instead of hidden in outputs.

### Review -> Outputs

Package:

- reports, generated artifacts, validation results, inspection summaries, logs,
  and trace files

Proceed when:

- Outputs can distinguish verified, assumed, unverified, failed, and skipped
  items.
- Artifact paths and trace links are present.
- Unsupported checks for future levels are labeled as not implemented or
  unverified, not passed.

## Requirement

### Responsibilities

- Understand the user's natural-language product or part intent.
- Ask clarification questions when missing information changes topology, fit,
  manufacturing strategy, assembly behavior, serviceability, or safety review.
- Apply explicit overrides and earlier clarification answers.
- Record missing information, assumptions, parser diagnostics, and field policy.
- Produce `cad_brief` as requirement/planning metadata.
- Decide whether the request appears to be a single part, assembly, or unknown
  scope.

### Inputs

- User natural language.
- Structured overrides.
- Clarification answers from previous turns.
- Requested or default `check_level`.

### Outputs

- `requirement.json`
- `intent`
- `dimensions`
- `features`
- `outputs`
- `check_level`
- `field_policy`
- `missing_information`
- `follow_up_questions`
- `follow_up_requests`
- `cad_brief`
- `assumptions`
- `requirement_status`
- `source` for trace/debug

### Does Not Own

- CAD geometry generation.
- Backend operation selection.
- Assembly placement or constraint solving.
- Re-parsing after the structured requirement has been produced.

### Downstream Consumption

Planning consumes intent, scope, missing information, follow-up requests,
assumptions, status, and `cad_brief`.

CAD IR conversion consumes part type, unit, dimensions, features, outputs,
check level, part name, and trace metadata.

Review may consume assumptions and requirement status to explain what is known,
assumed, or unresolved.

## Planning

### Responsibilities

- Choose workflow route: single part, multi-part, assembly loop, or
  confirmation-needed.
- Convert the requirement package into design strategy.
- Define functional datums, interfaces, reference envelopes, modeling order,
  and review targets.
- Analyze design reasonableness at the strategy level: structural load paths,
  obvious weak points, motion intent, degrees of freedom, interface constraints,
  service access, and fit risks.
- Identify risk gates and decisions that must return to Requirement for user
  confirmation.
- Split product intent into single-part and assembly work when appropriate.

### Inputs

- `requirement.json`
- Requirement assumptions and missing-information notes.
- Candidate manufactured parts and reference components.
- Requested `check_level`.

### Outputs

- `plan.md`
- `planning_artifact.json`
- Workflow route.
- Design strategy.
- Part list and generation order.
- Interface map.
- Part Modeling context: template candidates, functional datums, interfaces,
  and review targets for the selected part.
- Risk list and confirmation gates.
- Design-reasonableness notes, including structural, motion, degree-of-freedom,
  fit, clearance, and serviceability concerns.
- Downstream review targets.

### Does Not Own

- User requirement clarification.
- CAD code generation.
- Backend-specific modeling operations.
- Single-part geometry validation.
- Final strength simulation, motion simulation, tolerance stack-up, or
  production release verification. These are future validation/simulation
  capabilities, not current Planning outputs.

### Downstream Consumption

CAD IR conversion consumes only the selected part-level decisions needed to
encode geometry fields: part type, units, dimensions, features, interfaces, and
conservative generation targets. `planning_artifact.part_modeling_context` may
be copied into CAD IR source trace for Part Modeling template/review context,
but it is not geometry authority. CAD IR conversion does not consume open-ended
design analysis as authority to invent geometry.

Part Modeling consumes part order, template candidates, reference envelopes,
and per-part review targets.

Assembly consumes interface maps, assembly intent, clearances, contacts, and
serviceability assumptions.

## CAD IR

### Responsibilities

- Encode selected requirement and planning decisions into the part-level CAD
  source of truth.
- Provide a JSON-serializable `CADIR` that can be validated, repaired, and
  regenerated deterministically.
- Keep geometry-relevant fields explicit and narrow.
- Preserve the chosen design intent without becoming a second planning layer.

### Inputs

- Structured requirement fields.
- Selected part-level planning decisions that are already resolved enough to
  become explicit CAD fields.
- Existing `input_ir.json` when running IR-first.

### Outputs

- `input_ir.json`
- `CADIR`

### Does Not Own

- Full product requirement semantics.
- Design strategy, tradeoff analysis, structural reasoning, motion reasoning,
  or risk gate decisions.
- User clarification.
- Assembly-level decisions.
- Reinterpreting original prompt text.

### Downstream Consumption

Part Modeling consumes `input_ir.json` / `CADIR` for generation, execution,
validation, repair, and retry. Review consumes it to explain what was requested
and compare it to measured artifacts.

## Part Modeling

Part Modeling is the realization loop for CAD IR. It may consult template,
feature, reference-component, and backend knowledge to implement the selected
geometry, but it must not reopen product design decisions.

### Responsibilities

- Realize individual parts from `input_ir.json` / `CADIR` or legacy part-level
  specifications.
- Search and apply reusable part templates, feature implementations, reference
  component envelopes, and backend-specific generation patterns.
- Map declarative CAD IR fields to backend-native model code or model objects.
- Generate `model.py`, execute it, export STEP/STL, inspect geometry, and record
  failures.
- Repair CAD IR only for implementation-level issues found through structured
  failure analysis, while preserving user intent and selected design strategy.
- Produce part-level report and trace artifacts.

### Inputs

- `input_ir.json` / `CADIR`
- Part-level spec from Planning or legacy workflow.
- Template candidates and reference envelopes.
- Template, feature, and reference-component knowledge.
- Backend capability notes or generation patterns.

### Outputs

- `model.py`
- `model.step`
- `model.stl`
- `preview.png` when available
- Part-level `report.json`
- Part-level `report.md`
- `agent_trace.json`
- `logs/runtime.json`

### Does Not Own

- Product-level requirement changes.
- Part structure, dimensions, feature semantics, or design strategy once CAD IR
  is established.
- User clarification.
- Assembly-level placement, mating, clearance, or serviceability decisions.
- Treating unmeasured features as verified.
- Simplifying or changing geometry because a template is easier, unless that
  change is explicitly recorded as unresolved or returned to Planning.

### Downstream Consumption

Assembly consumes generated part reports, bounding boxes, artifact paths,
status, and validation summaries.

Review consumes generated artifacts, inspection summaries, measured validation
targets, unverified items, failures, and repairs.

## Assembly

### Responsibilities

- Define how generated parts and reference components relate to each other.
- Record placement intent, contacts, constraints, clearances, allowed overlaps,
  serviceability notes, and unresolved assembly questions.
- Produce backend-neutral assembly configuration.
- Validate basic part input availability, placement relationships, constraint
  intent, and declared exports.

### Inputs

- `requirement.json`
- Part specs or part metadata.
- Part reports and generated artifact summaries.
- Assembly intent from Planning.

### Outputs

- `assembly_plan.json`
- `assembly_plan.md`
- `assembly.json`
- `constraint_assembly.json`
- `assembly_review.md`

### Does Not Own

- Single-part geometry generation.
- Single-part feature validation.
- Full industrial constraint solving, motion simulation, tolerance stack-up, or
  production release.

### Downstream Consumption

Review consumes assembly plan, backend-neutral assembly config, validation
status, unresolved questions, assumptions, and declared limits.

Output/export utilities consume assembly configs and selected backend paths to
write exchange files.

## Review

### Responsibilities

- Present results according to `check_level`.
- Separate verified, assumed, and unverified request items.
- Summarize validation, inspection, execution trace, generated artifacts, and
  known limitations.
- Ensure failed or unmeasured features are visible instead of reported as
  passing.

### Inputs

- `requirement.json`
- `input_ir.json` / `CADIR`
- Generated part and assembly artifacts.
- Validation results.
- Inspection summaries.
- Runtime logs.
- `agent_trace.json`

### Outputs

- `report.json`
- `report.md`
- `assembly_review.md` when applicable.
- Final artifact manifest or artifact list.

### Does Not Own

- Changing requirements to match generated geometry.
- Repairing CAD IR without structured failure analysis.
- Treating future check levels as production release.

### Downstream Consumption

Users, benchmark tools, and future automation consume reports and traces to
understand what was generated, what passed, what was assumed, and what still
requires confirmation.

## Outputs

### Responsibilities

- Write artifacts inside the selected output directory.
- Preserve traceability between inputs, generated code, exchange files, reports,
  logs, and trace data.
- Keep path behavior predictable for user runs, examples, and benchmarks.

### Inputs

- CAD IR.
- Generated model source.
- Exported CAD artifacts.
- Validation and inspection data.
- Review summaries.
- Runtime trace data.

### Outputs

Typical IR pipeline single-part output:

```text
outputs/<part_name>/
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

### Does Not Own

- Requirement, planning, modeling, assembly, or review decisions.
- Changing generated geometry.
- Hiding missing or unverified artifacts.

### Downstream Consumption

Users consume STEP/STL, reports, and trace files. Benchmarks consume artifact
paths, measured facts, report fields, and trace summaries.
