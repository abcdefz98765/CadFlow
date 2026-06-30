# Workflow Contract

Purpose: define CadFlow workflow responsibilities, handoff artifacts, and
stage boundaries.

CadFlow is organized around explicit artifacts, not around re-parsing a prompt
at every step.

```text
user input -> requirement -> planning -> CAD IR -> part modeling -> assembly -> review -> outputs
```

Each stage owns one decision layer and hands off structured data to the next
stage. Natural language is accepted at the edge of the system, but downstream
CAD generation consumes `requirement.json` and `input_ir.json`.

## Entry Points

### prompt_pipeline

`examples/prompt_pipeline/` is a debug and exploration path from natural
language to generated artifacts.

```text
prompt -> requirement.json -> CAD IR -> model.step/model.stl -> report/trace
```

It is useful for parser and handoff development. It does not replace IR-first
benchmarks and should not be treated as the deterministic benchmark contract.

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
- `plan.md` or future structured planning artifact
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
- Future structured planning artifact when introduced.
- Workflow route.
- Design strategy.
- Part list and generation order.
- Interface map.
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
conservative generation targets. It does not consume open-ended design analysis
as authority to invent geometry.

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
