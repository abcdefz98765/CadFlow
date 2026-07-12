# Web Workflow Console

The Web Workflow Console is the future user-facing cockpit for running and reviewing CadFlow workflows.

It is not a browser CAD editor.

The current MVP treats the console as a workflow cockpit rather than just an
artifact browser. The primary user-facing surface is Workflow / Stage / Review:
each stage should expose what it consumed, what it produced, what gate decision
or diagnostic blocked it, what review state exists, and what backend action can
be taken next. Raw artifacts remain available, but they are secondary to
stage-level review cards.

The long-term UI should support iterative natural-language CAD workflow: create
a first model from a prompt, show assumptions or missing risky fields, ask
focused questions, revise a previous run, display patch diffs, compare old/new
outputs, and show lineage.

## The Web UI Is

- Workflow runner.
- Natural-language prompt interface.
- Agent status display.
- Artifact viewer.
- Report viewer.
- Agent trace viewer.
- Assumption and missing-field review surface.
- Previous-run selector for revision workflows.
- Revision plan, patch diff, comparison, and lineage viewer.
- Optional STL/preview viewer later.

## The Web UI Is Not

- Browser CAD modeling environment.
- Geometry kernel.
- Replacement for CadQuery or FreeCAD.
- Direct arbitrary code execution surface.

## Recommended v0.4 Scope

### v0.4a

- Local backend scaffold, currently dependency-free Python.
- Future simple frontend.
- Run existing `run_text_pipeline`.
- List runs from `outputs/` and `runs/`.
- Show run status from `report.json` and `agent_trace.json`.
- Show artifacts, reports, and `agent_trace`.
- Use the deterministic `StageRunner` implementation for local workflow stages.
- Identify `model.step`, `model.stl`, `preview.png`, and `model.py` as downloadable output files from the selected run directory.

### v0.4b

- Clarify LLM-first UX without adding a provider dependency.
- Natural language to structured requirement/planning through the existing
  local/mock adapter boundary.
- Assumptions and `proceed_with_assumptions` workflow design.
- User confirmation design for missing or risky fields.

### v0.4c

- Conversational CAD workflow.
- Follow-up questions.
- Confirm-before-generation.
- Compare attempts/candidates.
- Keep real provider integration behind future validated `AgentAdapter`
  contracts.

## Future Iterative Scope

The Web Console should eventually support:

- Create a new model from a prompt.
- Show assumptions made under `proceed_with_assumptions`.
- Show missing or risky fields by check level.
- Ask focused clarification questions.
- Select a previous run.
- Submit a revision prompt.
- Show Model Intake classification and editability warnings.
- Show revision plan.
- Show patch diff.
- Show old/new comparison.
- Show parent/child lineage.
- Download parent and child outputs.

This is staged roadmap work. The current console remains a local artifact-backed
workflow UI and does not yet implement the full revision experience.

## State Model

The Web Console should consume existing run artifacts instead of inventing a separate state format. The backend may index runs for convenience, but the file contract remains the source of truth:

```text
prompt.txt
requirement.json
planning_artifact.json
input_ir.json
model.py
model.step
model.stl
preview.png
report.json
report.md
agent_trace.json
logs/runtime.json
```

Revision workflows should add child-run artifacts from
`docs/architecture/revision-workflow.md` when implemented. The browser should
read those artifacts; it should not maintain a separate revision state store.

## StageRunner Boundary

The v0.4a backend can use `StageRunner` as the local execution unit behind the Web Console:

```text
Web UI -> local workflow API -> StageRunner -> artifact files
```

A `StageRunner`:

- Reads upstream artifacts such as `prompt.txt`, `requirement.json`, `planning_artifact.json`, or `input_ir.json`.
- Runs one deterministic workflow stage, such as Requirement, Planning, Part Modeling, Review, or Outputs.
- Writes downstream artifacts, stage status, flow/rework decisions, and logs into the run directory.

The first implementation should call existing deterministic Python entry points:

- `RequirementAgent`
- `create_planning_artifact()`
- `run_text_pipeline()`
- `run_ir_pipeline()`
- `run_agent_loop()`
- report/review helpers

`StageRunner` is not a replacement for `AgentAdapter`. `AgentAdapter` owns natural-language understanding, planning advice, repair suggestions, and explanations. `StageRunner` owns local workflow execution and artifact persistence.

As of v0.5, `StageRunner` can call the local/mock deterministic adapter for Requirement and Planning drafts, but the runner still validates and persists only `requirement.json`, `planning_artifact.json`, and `input_ir.json` before downstream execution. Adapter activity is recorded in `logs/runtime.json` as sanitized provider identity and operation metadata. Chat history, token streams, browser state, and provider responses must not become the cross-stage source of truth.

## v0.4a Backend Surface

The current scaffold lives under `src/ai_native_cad/workflow_console/`:

- `StageRunner`: deterministic local stage execution and artifact persistence.
- `WorkflowConsoleBackend`: local run listing, path-safe run-id resolution, artifact metadata/content reads, status derivation, and downloadable-file discovery.
- `WorkflowConsoleActions`: safe one-stage reviewed-part workflow actions over existing pipeline functions.
- `routes.py`: dependency-free future route contract specs, in-process route dispatch, response envelopes, and backend exception to HTTP-like status mapping.

Current architecture decision:

```text
Safe action backend remains authoritative.
NiceGUI is an optional local UI shell.
```

The backend surface is now FastAPI-shaped, but the server remains the existing
stdlib local bridge for this pass. The current bridge was already dependency-free,
bound to `127.0.0.1` by default, and routed through safe run ids instead of
filesystem paths, so a framework migration is deferred until the action
boundaries are stable. A future FastAPI adapter should wrap the same backend
methods and action service rather than introduce new CAD behavior. NiceGUI is
now introduced only as a local UI shell over the same backend facade and
`WorkflowConsoleActions`; it is not a replacement backend.

`StageRunner` records local stage history in the existing `logs/runtime.json` artifact under `workflow_console.stages`. This keeps stage status file-based without introducing a database or separate state store. `WorkflowConsoleBackend.list_runs(...)` and `list_runs_page(...)` expose bounded, path-free run summaries for first console load; they do not build full metadata for every run. `WorkflowConsoleBackend.read_run_metadata(...)` is the lazy detail operation for one selected run and exposes path-free `stage_history`, `gate_history`, and `report_summary` summaries for UI timelines and review panels, while the raw runtime/report/trace artifacts remain readable for audit. Stage history may include sanitized adapter activity such as operation and local/mock provider identity, but not prompts, transcripts, tokens, or provider secrets. The summary also includes compact, path-free requirement and planning metadata from `requirement.json` and `planning_artifact.json`, including assumptions, missing fields, follow-up fields, `requirement_status.flow_decision`, and planning `flow_gate_status`. When revision artifacts are present, the same summary exposes compact revision metadata such as parent/child run ids, lineage relationship, revision index, plan/status, blocked reason, and requested/actual/validation/repair change counts.

The Python facade can run supported stages from an existing run directory by reading upstream artifacts: `prompt.txt` for Requirement or full text pipeline, `requirement.json` for Planning, and `planning_artifact.json` or `input_ir.json` for Part Modeling.

It can also create a run without executing stages, writing only `prompt.txt` and local runtime status so a future UI can advance the workflow stage by stage.

For future HTTP routes, `WorkflowConsoleBackend` also exposes run-id based operations that create or resolve runs only under configured local run roots: the active `<workspace>/runs/` root plus read-compatible legacy `outputs/` and `runs/` roots. These methods reject absolute paths, traversal segments, path separators, duplicate create targets, and unconfigured run roots so routes do not need to accept arbitrary filesystem paths.

The route contract scaffold defines future method/path semantics without importing a web framework or starting an HTTP server. It also provides a small in-process dispatcher that accepts a route name plus path/body/query dictionaries and calls an explicit allowlist of by-id backend methods. The dispatcher removes local path fields such as `run_dir`, `root`, `path`, and `output_dir` from public route response data while preserving artifact content. Generated file references in route result metadata are reduced to filenames; downloadable lookup still goes through the whitelisted download route. Gate-decision payloads remain in `logs/runtime.json` for audit, but public metadata and route responses expose only compact payload summaries. The `run_revision` route can execute a structured CadFlow-native revision from a valid parent run into an explicit safe child run id, returning path-free metadata while the child run stores `model.step`, `model.stl`, comparison, lineage, revision report, and trace artifacts. Future FastAPI or other HTTP adapters must wrap the by-id backend methods only, such as `create_run_by_id`, `run_stage_by_id`, `run_revision_by_id`, `read_artifact_by_id`, `write_artifact_by_id`, and `record_gate_decision_by_id`; direct local `run_dir` operations remain internal Python APIs.

The explicit read/action API shape is:

```text
GET  /api/workspace
POST /api/workspace
POST /api/workspace/load
GET  /api/config
PUT  /api/config
GET  /api/works
POST /api/works
GET  /api/works/{work_id}
POST /api/works/{work_id}/requirement-run
POST /api/works/{work_id}/part-runs
GET  /api/runs
GET  /api/runs/{run_id}/summary
GET  /api/runs/{run_id}/artifacts/{artifact_name}
POST /api/actions/part-request
POST /api/actions/part-review
POST /api/actions/reviewed-handoff
POST /api/actions/reviewed-part-create
POST /api/actions/part-result-review
POST /api/actions/stage-review
POST /api/actions/workflow-review
POST /api/actions/rework
```

The existing `POST /api/route` bridge remains for the static frontend, and the
stdlib server also exposes the API-shaped aliases above. Each action accepts a
safe run id and optional action-specific fields; none accept arbitrary local
filesystem paths.

The Work API is a file-backed Work entity plus a deterministic view model over
existing run artifacts, not a database or migration. The active workspace may
live outside the repository and owns `workspace.json`, workspace-scoped
`config.json`, Work manifests, and new workspace run containers. A Work is the
mutable user-visible engineering task; a Run is an immutable append-only
execution record; a Part Job is a part-level task inside a Work that may have
multiple attempts/runs. `POST /api/works` creates
`<workspace>/works/<work_id>/work_manifest.json` with title, description,
status, current/root run pointers, run ids, part jobs, timestamps, advancement
mode, and metadata; it does not create a run, call a provider, or execute CAD.
Legacy manifests under
`outputs/_works/<work_id>/work_manifest.json` are read for compatibility.
Existing legacy runs remain discoverable by
inference from root-like artifacts (`assembly_plan.json`, `workflow_review.json`,
`stage_review.json`), reviewed-part lineage and bridge artifacts, child run
references, part result reviews, and `rework_decision.json`. Runs that cannot be
confidently grouped remain available only from the Runs page when unclassified
visibility is explicitly enabled; they are not mixed into the Work list.

`GET /api/works` returns sanitized Work summaries: title, overall status,
root/current run ids, part counts, review/report state, readiness/risk, next
action, last update, and diagnostic codes. `GET /api/works/{work_id}` returns
the Work detail view model: summary, current state, Parts Matrix, ordered
workflow nodes, run history, products/artifacts, available safe actions, and an
explicit history-semantics block declaring that runs are immutable and rework
creates new runs. Public Work responses contain no absolute paths, raw provider
payloads, secrets, environment values, runtime transcripts, or arbitrary
filesystem browsing. The explicit workspace display path is the only intended
absolute-path field in the local UI/API surface.

Workspace config controls workflow advancement: `manual_confirm` pauses after
file-backed requirement/split outputs so the user can inspect and confirm;
`auto_advance` may create follow-on run containers when the required split
artifacts are available. Both modes preserve append-only runs and do not imply
automatic all-part CAD generation, batch generation, assembly generation, or a
loop queue.

`WorkflowConsoleActions` maps the reviewed-part workflow to explicit one-stage
operations:

- `part-request`: reads `assembly_plan.json` or `01_design/assembly_plan.json`
  and writes `02_part_request/part_create_request.json`.
- `part-review`: reads `part_create_request.json` from the staged folder or run
  root and writes `03_review/part_request_review.json`.
- `reviewed-handoff`: reads the part request and review artifacts and writes
  `04_handoff/reviewed_part_handoff.json`.
- `reviewed-part-create`: reads one reviewed handoff, writes
  `part_execution_request.json`, calls `AgentAdapter.create_part_ir(...)`,
  writes `cad_ir_draft.json` for review, validates the returned CAD IR with
  `validate_input_ir_draft(...)` and `validate_ir(...)`, and then either calls
  `run_ir_pipeline(...)` for exactly one child part under `05_single_create/`
  or writes a `blocked_cad_ir_validation` report/trace.
- `part-result-review`: reads one reviewed handoff plus one child run identified
  by `05_single_create/lineage.json` or an explicit safe child run id, then
  writes `06_part_result_review/part_result_review.json`.
- `stage-review`: writes one local `stage_review.json` artifact that records
  user review/rework intent for an explicit stage.
- `workflow-review`: writes deterministic local `workflow_review.json` and
  `workflow_review.md` artifacts from existing run summaries and diagnostics.
- `rework`: reads a saved `stage_review.json`, requires `needs_revision`, and
  writes a sanitized `rework_decision.json`. In this MVP only
  `workflow_review` executes, by creating a child rework run with lineage and a
  refreshed deterministic workflow review. `assembly_plan` and `part_request`
  produce blocked unsupported-target decisions.

These actions wrap existing pipeline functions only. They do not add assembly
generation, automatic all-part generation, batch generation, new CAD templates,
assembly constraint solving, provider-generated code, automatic rework loops,
overnight queue execution, or free-form Web chat. The reviewed-part create path
does accept agent-generated CAD IR only through `create_part_ir(...)`, and that
IR is blocked unless local validation passes. Public action results are
sanitized summaries: no absolute paths, no API
keys, no environment values, no provider raw payloads, and no transcripts.

`stage_review.json` is the Stage Review / Rework Artifact MVP and the first
save-only user-agent negotiation surface. It allows `review_status` values
`approved`, `needs_revision`, and `blocked`; explicit `stage` values such as
`requirement`, `design_brief`, `assembly_plan`, `candidate_parts`,
`part_request`, `part_review`, `handoff`, and `single_part_result`; and explicit
`target_rework_stage` values from a controlled vocabulary that also includes
`workflow_review`. Notes and requested changes are sanitized and length-limited.
Saving this artifact does not call a provider, rerun a pipeline stage, modify
CAD artifacts, create a loop queue, or trigger batch/all-part/assembly
generation. Rework execution happens only through the separate explicit
`rework` action, and overnight one-part-at-a-time queues remain future work.

`workflow_review.json` and `workflow_review.md` are the Human-readable Workflow
Review / Agent Report MVP. The report is deterministic and local; it reads
existing allowlisted run summaries, reviewed-part summaries, stage review
summary, artifact availability, and diagnostics. It reports `overall_status`,
`readiness_score`, confidence bands, `risk_level`, summary bullets, key
diagnostics, risks, recommended next actions, and a short scoring explanation.
Readiness, confidence, and risk are explainable heuristics, not provider advice
or LLM self-evaluation. Creating the report does not call providers, call CAD
pipeline functions, modify CAD outputs, create loop queues, or add CAD
capability. A provider advisory report can be layered in later only as a
separate explicit feature.

Readable artifacts remain limited to workflow source, handoff, reviewed-part,
report, trace, and revision records: `prompt.txt`, `revision_prompt.txt`,
`requirement.json`, `design_brief.json`, `planning_artifact.json`, `input_ir.json`,
`parent_input_ir.json`, parent snapshots, `assembly_plan.json`,
`assembly_plan.md`, `part_create_request.json`, `part_request_review.json`,
`reviewed_part_handoff.json`, `part_execution_request.json`,
`part_result_review.json`, `stage_review.json`, `revision_request.json`, `change_intent.json`,
`revision_plan.json`, `patch.json`, `comparison.json`, `revision_report.md`,
`lineage.json`, `report.json`, `report.md`, `workflow_review.json`,
`workflow_review.md`, `agent_trace.json`, and
`logs/runtime.json`. Downloadable discovery remains limited to `model.step`,
`model.stl`, `preview.png`, and `model.py`.

The UI display policy is stricter than the readable-artifact allowlist. It
classifies artifacts as `human_facing`, `review_debug`, or `internal_debug`.
Human-facing artifacts are visible by default: Markdown reports, workflow
review artifacts, stage review summaries, assembly-plan/part-result summaries,
and model availability. Review-debug artifacts such as requirement/design brief,
handoff, lineage, and sanitized trace summaries are collapsed behind an explicit
debug toggle. Internal/schema-heavy artifacts such as CAD IR, planning internals,
revision internals, validation/runtime logs, and raw-ish trace internals are
hidden unless internal artifacts are explicitly enabled. This classification is
a presentation policy only; artifact reads still go through the existing
allowlist and sanitization path.

Editable artifacts are narrower than readable artifacts and are saved as
validated overrides, not in-place edits. The backend accepts only the controlled
JSON override allowlist documented in the Workflow Review Surface section;
writes must be JSON objects, pass artifact-specific validation, and are recorded
in `logs/runtime.json` under `workflow_console.artifact_edits`.

The backend exposes shared status constants for the current local status vocabulary: `created`, `completed`, `blocked`, `success`, `failed`, `running_or_incomplete`, and `unknown`.

Gate decisions are also file-backed. The backend can record `approve`, `reject`, `return`, `override`, `proceed_with_assumptions`, `ask_user`, `return_to_requirement`, `return_to_planning`, and `revise_existing_model` decisions for supported workflow stages by appending to `logs/runtime.json` under `workflow_console.gate_decisions`. Public run metadata exposes only a gate summary (`stage`, `action`, `reason`, and `timestamp`), not arbitrary decision payloads.

Requirement clarification has a separate minimal artifact contract. The
canonical question field in requirement artifacts is `follow_up_questions`;
`clarification_questions` is kept as a compatibility alias for UI summaries and
older artifacts. When a user answers focused questions, the backend writes
`requirement_clarification.json` and applies it with
`apply_requirement_clarification` to produce `requirement_v2.json`. The original
`requirement.json` remains unchanged. The runtime log records
`workflow_console.clarification_applied` entries with answer count, target
artifact, and the updated requirement flow decision.

The local backend should expose only workflow operations:

- Run management: create, open, list, and inspect local run directories.
- Stage operations: run/status/artifacts for Requirement, Planning, Part Modeling, Review, and Outputs.
- Artifact operations: read structured JSON, read Markdown reports, write confirmed user edits, and apply structured Requirement clarification answers.
- Gate operations: record approve, override, reject, or return-to-upstream decisions as artifacts.
- File serving: serve `model.step`, `model.stl`, `report.md`, `report.json`, and `agent_trace.json`.

The backend should not change benchmark contracts, add new CAD generator behavior, or make browser state authoritative.

The scaffold now includes a stdlib-only local HTTP bridge, a static frontend,
and an optional NiceGUI frontend. It still does not provide authentication, a
database, cloud deployment, or a framework-backed public web app. A FastAPI app
can be layered over the Python facade later only if the dependency is
intentionally added.

## v0.4a UI Surface

The first frontend lives in `web-viewer/workflow-console.html` and stays workflow-oriented:

- Stage timeline: Requirement -> Planning -> Part Modeling -> Review -> Outputs.
- Prompt entry and run controls.
- Artifact inspector for `requirement.json`, `planning_artifact.json`, `input_ir.json`, reports, and traces.
- Report/trace viewer that highlights verified, unverified, warning, error, and rework states.
- Reviewed-part summaries for `assembly_plan.json` candidates, reference-only
  parts, `reviewed_part_handoff.json`, child run discovery, lineage, and
  `part_result_review.json` checks.
- Right-side Inspector tabs for report/trace summary, gate decisions, downloadables, and activity.
- Scroll-safe preview surface using current-run STL or later GLB assets.

Existing `web-viewer` work can be reused or evolved for artifact preview, but preview remains secondary to the STEP-first workflow.

The UI is served by `ai_native_cad.workflow_console.server`, a stdlib-only local bridge that binds to `127.0.0.1` by default. It does not add FastAPI or any HTTP dependency. The bridge exposes:

- `POST /api/route`: a narrow JSON adapter over the existing dependency-free `dispatch_route(...)` contract.
- `GET /api/downloads/{run_id}/{filename}`: whitelisted local file serving for `model.step`, `model.stl`, `preview.png`, and `model.py` only.
- Static files from `web-viewer/`, including the existing STL viewer.

For local Windows use, `scripts/start_workflow_console.ps1` wraps the same
server entrypoint. It selects `.venv-cadflow` when present, sets
`PYTHONPATH=src`, prints the local URL, and then runs
`ai_native_cad.workflow_console.server`. It is a convenience launcher only; it
does not add provider execution, CAD generation, or new Web actions.

The NiceGUI frontend lives in
`ai_native_cad.workflow_console.nicegui_app` and is launched separately:

```powershell
.\scripts\start_nicegui_console.ps1
```

It binds to `127.0.0.1:8780` by default and uses the optional `web` dependency
group:

```bash
pip install -e ".[web]"
```

The NiceGUI UI is intentionally workspace-oriented and uses a left navigation
shell:

- Sidebar: main Workspace, Works, and Config entries; selected Work page links
  appear below the selected Work.
- Workspace: current workspace name, full local path, initialization state,
  work/run counts, advancement mode, New/Load workspace dialogs, and a Work
  list that can jump to a Work.
- Works: current workspace Work list plus Work creation.
- Overview: concise user-facing Work state, current stage, part overview, next
  action, root requirement input, and split confirmation for part run
  containers.
- Workflow: a dot-and-arrow graph with Requirement, Planning or Split/Assembly
  Plan, active part lanes, and Result/Downloads. Dot hover shows status,
  inputs, outputs, start flag, review state, and next action; clicking a node
  opens the associated review/action context.
- Parts: first-class Parts Matrix with `part_id`, role, status, current stage,
  attempt count, STEP/STL availability, STL preview when available, review
  status, next action, and downloads. Product downloads live here instead of in
  a separate Products page.
- Runs: current Work run history by default. Explicit toggles expose low-level
  details and unclassified/global runs; details are lazy-loaded only after this
  page is selected.
- Config: workspace-level provider/model/timeout/retry settings and advancement
  mode. API keys stay in environment variables and are never shown or saved by
  the UI.

### Workflow Review Surface MVP

The NiceGUI Workflow page now builds a `Workflow Stage Review` view model from
a Work-level stage projection, rather than from the selected/latest immutable
run. The projection follows the Work lineage: the root requirement run, its
nested staged artifact directories, reviewed-part child runs, part-result
review, workflow review, and rework child runs. Every artifact remains at its
original location and is represented by its source run id and source-relative
path; the console never copies nested artifacts to a run root as a display
workaround. The view model is presentation-only: it reads allowlisted artifacts
and reports action availability; it does not write files or make the browser
authoritative.

Work and Run therefore have deliberately separate meanings. The Work Workflow
page is the aggregated lineage source of truth for graph nodes and selected
stage detail. Runs / History remains a per-run, immutable audit view. A Work's
`latest_run_id` is only the default history/audit selection and must not decide
whether upstream Workflow stages appear completed.

### Work / Run semantics milestone

The NiceGUI Workflow page has an explicit `current_work` or `run_snapshot`
mode and consumes `workflow_page_view_model.py` rather than combining a Work
projection, selected Run, and action target in the presentation layer. Current
Work reads the Work manifest's `active_lineage` pointer; Run Snapshot reads only
the selected immutable Run and disables ordinary mutations. The Work manifest
stores `active_root_run_id`, `active_leaf_run_id`, accepted/superseded run ids,
and `latest_attempt_run_id`. `latest_attempt_run_id` is audit information, not
an active-lineage selector. **Work Workflow is an active-lineage aggregated
view. Run Snapshot is immutable and read-only. Actions declare their scope and
target Run.**

The MVP stage cards are Requirement, Clarification, Planning, Assembly Plan,
Part Request, Part Review, Reviewed Handoff, CAD IR Draft, Part Modeling /
Reviewed Part Create, Part Result Review, Workflow Review, and Rework. Each
card exposes stage name, status, input artifacts, output artifacts, sanitized
agent/adapter identity when present, gate decision, diagnostic codes, blocked
reasons, readable summary, available actions, and raw artifact links.

The Requirement card shows the original prompt, active requirement source
(`requirement_v2.json` over `requirement.json`), recognized `part_type`,
`part_family`, intent scope, object goal, assumptions, missing information,
follow-up questions, requirement flow decision, diagnostics, adapter identity,
and the raw requirement artifact.

The Planning / Assembly Plan cards show whether Planning used v1 or v2
requirement input, route and flow gate status, assembly-plan summary, candidate
parts, reference components, selected/primary candidate when known, supported
candidate state, blocked reasons, diagnostics, and raw planning/assembly
artifacts.

The Reviewed Part / CAD IR cards show staged reviewed-part artifacts:
`part_create_request.json`, `part_request_review.json`,
`reviewed_part_handoff.json`, `part_execution_request.json`,
`cad_ir_draft.json`, lineage, child `input_ir.json` status, STEP/STL status,
and `blocked_cad_ir_validation` details when the agent-generated CAD IR is
invalid or unsupported. This is an inspection surface only; it does not add
fallback templates or new CAD families.

The raw artifact viewer remains allowlisted and does not browse arbitrary
directories. It prioritizes prompt, requirement, clarification, planning,
assembly, reviewed-part handoff, CAD IR draft, report, trace, stage review, and
workflow review artifacts. `logs/runtime.json` is summarized by stage/action
counts rather than treated as a primary user artifact.

The console also supports a controlled artifact override MVP. This is not an
arbitrary file editor. Only selected JSON workflow artifacts can be edited:
`requirement_v2.json`, `planning_artifact.json`, `assembly_plan.json`,
`part_create_request.json`, `part_request_review.json`,
`reviewed_part_handoff.json`, `cad_ir_draft.json`, `input_ir.json`, and
`stage_review.json`. Staged aliases such as
`02_part_request/part_create_request.json`,
`03_review/part_request_review.json`,
`04_handoff/reviewed_part_handoff.json`, and
`05_single_create/cad_ir_draft.json` resolve to the same controlled artifacts.

Original agent artifacts are preserved. A valid edit writes a versioned audit
envelope under `edits/<artifact>.edit_NNN.json` with source artifact,
timestamp, user identity, edit reason, base digest, validation status, and
edited content. The current active override is also materialized as pure JSON
under `edits/active/<artifact>.json` so downstream workflow code can consume a
normal artifact without understanding the edit envelope. Runtime history records
the edit in `logs/runtime.json` under `workflow_console.artifact_edits`.

Every override is validated before it becomes active. Requirement and Planning
edits use the existing adapter draft validators; CAD IR edits use
`validate_input_ir_draft(...)` and `validate_ir(...)`; reviewed-part handoff and
request/review edits receive minimal structure checks. Edits containing secret
markers, provider raw payloads, transcripts, Python/CadQuery code, or shell
commands are rejected. Invalid edits are not saved as active overrides.

Downstream resolution is intentionally small in this MVP:

- Planning uses active `requirement_v2.json` override before
  `requirement_v2.json` or `requirement.json`.
- Part Request creation uses active `assembly_plan.json` override before the
  original assembly plan.
- Reviewed Part Create uses active `reviewed_part_handoff.json` override before
  the original handoff.
- If a valid active `cad_ir_draft.json` override exists, Reviewed Part Create
  revalidates it and can run the existing IR pipeline from that explicit user
  IR. Invalid CAD IR edits are rejected before Part Modeling.

The Workflow page marks stages with active overrides as `user_modified` and
shows which downstream stages are stale or affected. Revert/deactivate and
diff views remain future work.

Available buttons are backed by existing actions where possible:
`save_stage_review`, `create_workflow_review`, `run_rework`, `part_request`,
`part_review`, `reviewed_handoff`, `reviewed_part_create`, and
`part_result_review`. Disabled buttons include a prerequisite reason. The
`needs_revision` shortcut is intentionally disabled because it requires the
compact Stage Review form to collect a target rework stage and requested
changes.

OpenNode and raw node-graph concepts are no longer the primary user-facing
workflow language. The original graph is retained below the cards as
`Debug / Raw Workflow Graph`.

The stdlib HTML console remains available as the fallback/debug view. NiceGUI is
the preferred UI for large local output trees because it avoids loading every
run artifact on initial page load, which matters before loop queue and overnight
execution features multiply the number of file-backed runs.

The browser never becomes the source of truth. Create, stage execution, artifact edits, gate decisions, artifact reads, and downloadable discovery all round-trip through the Python backend and existing run artifacts. Editable artifacts remain limited to `requirement.json`, `planning_artifact.json`, and `input_ir.json`; the UI only enables save controls for those files and the backend remains authoritative for validation.

The current UI supports the first usable local workflow loop:

- create or load an explicit workspace, including one outside the repository;
- create Work manifests and bind root/part run containers under
  `<workspace>/runs/`;
- list workspace Works and current Work run history, with legacy/global runs
  available through explicit debug toggles;
- select a run and inspect status/current stage plus stage/gate history;
- run Requirement, Planning, Part Modeling, Review, Outputs, or the full text pipeline by safe run id;
- inspect readable artifacts;
- inspect a human-readable workflow review report;
- run explicit rework from a saved Stage Review, with unsupported targets
  recorded as blocked `rework_decision.json` artifacts;
- inspect a compact report/trace summary without opening raw JSON;
- inspect existing reviewed-part E2E artifacts, including assembly-plan parts,
  candidate status, part result review status, STEP/STL checks, single-part
  scope checks, lineage checks, and interface metadata checks;
- edit only the allowed JSON handoff artifacts;
- record approve/reject/return/override gate decisions;
- answer Requirement `follow_up_questions` through a structured form that writes
  `requirement_clarification.json` and `requirement_v2.json`;
- save a structured `stage_review.json` rework intent without rerunning stages;
- create or refresh deterministic `workflow_review.json` and
  `workflow_review.md` report artifacts without provider or CAD execution;
- list STEP-first downloadables and open the secondary STL preview when `model.stl` exists;
- use an explicit Interact/Release control before the embedded STL viewer captures pointer wheel/drag input.

Review and Outputs are executable local check stages. Review reads the existing `report.json` flow decision and records the review gate status. Outputs checks publishable artifacts, including primary `model.step`, without regenerating CAD. STEP remains the primary CAD artifact; the embedded viewer loads `model.stl` only as a secondary inspection aid.

Reviewed-part awareness includes explicit one-stage actions. The single-part
create action is agent-IR-first: it must reach `create_part_ir(...)` for a ready
handoff, then either produce a validated child `input_ir.json` and run the CAD
Agent Loop, or block at `cad_ir_validation` with diagnostics. It must not
silently fall back to `mounting_plate` or fabricate a full assembly. The console
still does not add batch generation, assembly CAD generation, assembly
constraint solving, STEP assembly export, geometric fit validation, new CAD
templates as the primary strategy, or automatic all-part generation.

The default reviewed-part CAD path is:

```text
reviewed_part_handoff.json
  -> part_execution_request.json
  -> AgentAdapter.create_part_ir(...)
  -> cad_ir_draft.json
  -> validate_input_ir_draft(...) / validate_ir(...)
  -> run_ir_pipeline(...) or blocked_cad_ir_validation
```

The normalized/extract-compile create path remains a conservative fallback and
evaluation path, not the Web reviewed-part default. Templates, primitives, and
deterministic parser/compiler paths remain guardrails, bootstrap/local mock
implementations, and offline test supports; they should stabilize agent CAD IR
synthesis rather than replace it.

Both UIs expose reviewed-part actions only when their upstream artifact is
present, and each button calls exactly one backend action. Requirement
clarification is structured form input, not chat: the browser never becomes the
source of truth and does not directly edit `requirement.json`. There is still no
chat UI, no provider calls for free-form chat, no automatic rework execution, no
loop queue, no automatic all-part generation, no batch generation, and no
assembly generation.

## Security Notes

- Bind to `127.0.0.1` by default.
- LAN or Tailscale usage is acceptable only when explicitly configured.
- Do not expose the server publicly by default.
- Do not provide an arbitrary shell command endpoint.
- Do not allow unrestricted CLI agent execution from the ordinary user workflow.
- Treat generated code and artifacts as local workflow outputs that require review.
