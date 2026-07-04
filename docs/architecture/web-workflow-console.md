# Web Workflow Console

The Web Workflow Console is the future user-facing cockpit for running and reviewing CadFlow workflows.

It is not a browser CAD editor.

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

`StageRunner` records local stage history in the existing `logs/runtime.json` artifact under `workflow_console.stages`. This keeps stage status file-based without introducing a database or separate state store. `WorkflowConsoleBackend.read_run_metadata(...)` exposes path-free `stage_history`, `gate_history`, and `report_summary` summaries for UI timelines and review panels, while the raw runtime/report/trace artifacts remain readable for audit. Stage history may include sanitized adapter activity such as operation and local/mock provider identity, but not prompts, transcripts, tokens, or provider secrets. The summary also includes compact, path-free requirement and planning metadata from `requirement.json` and `planning_artifact.json`, including assumptions, missing fields, follow-up fields, `requirement_status.flow_decision`, and planning `flow_gate_status`. When revision artifacts are present, the same summary exposes compact revision metadata such as parent/child run ids, lineage relationship, revision index, plan/status, blocked reason, and requested/actual/validation/repair change counts.

The Python facade can run supported stages from an existing run directory by reading upstream artifacts: `prompt.txt` for Requirement or full text pipeline, `requirement.json` for Planning, and `planning_artifact.json` or `input_ir.json` for Part Modeling.

It can also create a run without executing stages, writing only `prompt.txt` and local runtime status so a future UI can advance the workflow stage by stage.

For future HTTP routes, `WorkflowConsoleBackend` also exposes run-id based operations that create or resolve runs only under configured local run roots, currently `outputs/` and `runs/`. These methods reject absolute paths, traversal segments, path separators, duplicate create targets, and unconfigured run roots so routes do not need to accept arbitrary filesystem paths.

The route contract scaffold defines future method/path semantics without importing a web framework or starting an HTTP server. It also provides a small in-process dispatcher that accepts a route name plus path/body/query dictionaries and calls an explicit allowlist of by-id backend methods. The dispatcher removes local path fields such as `run_dir`, `root`, `path`, and `output_dir` from public route response data while preserving artifact content. Generated file references in route result metadata are reduced to filenames; downloadable lookup still goes through the whitelisted download route. Gate-decision payloads remain in `logs/runtime.json` for audit, but public metadata and route responses expose only compact payload summaries. The `run_revision` route can execute a structured CadFlow-native revision from a valid parent run into an explicit safe child run id, returning path-free metadata while the child run stores `model.step`, `model.stl`, comparison, lineage, revision report, and trace artifacts. Future FastAPI or other HTTP adapters must wrap the by-id backend methods only, such as `create_run_by_id`, `run_stage_by_id`, `run_revision_by_id`, `read_artifact_by_id`, `write_artifact_by_id`, and `record_gate_decision_by_id`; direct local `run_dir` operations remain internal Python APIs.

The explicit read/action API shape is:

```text
GET  /api/runs
GET  /api/runs/{run_id}/summary
GET  /api/runs/{run_id}/artifacts/{artifact_name}
POST /api/actions/part-request
POST /api/actions/part-review
POST /api/actions/reviewed-handoff
POST /api/actions/reviewed-part-create
POST /api/actions/part-result-review
POST /api/actions/stage-review
```

The existing `POST /api/route` bridge remains for the static frontend, and the
stdlib server also exposes the API-shaped aliases above. Each action accepts a
safe run id and optional action-specific fields; none accept arbitrary local
filesystem paths.

`WorkflowConsoleActions` maps the reviewed-part workflow to explicit one-stage
operations:

- `part-request`: reads `assembly_plan.json` or `01_design/assembly_plan.json`
  and writes `02_part_request/part_create_request.json`.
- `part-review`: reads `part_create_request.json` from the staged folder or run
  root and writes `03_review/part_request_review.json`.
- `reviewed-handoff`: reads the part request and review artifacts and writes
  `04_handoff/reviewed_part_handoff.json`.
- `reviewed-part-create`: reads one reviewed handoff and calls the existing
  reviewed single-part create bridge once, writing under `05_single_create/`.
- `part-result-review`: reads one reviewed handoff plus one child run identified
  by `05_single_create/lineage.json` or an explicit safe child run id, then
  writes `06_part_result_review/part_result_review.json`.
- `stage-review`: writes one local `stage_review.json` artifact that records
  user review/rework intent for an explicit stage.

These actions wrap existing pipeline functions only. They do not add assembly
generation, automatic all-part generation, batch generation, new CAD templates,
assembly constraint solving, provider-generated CAD IR/code, or free-form Web
chat. Public action results are sanitized summaries: no absolute paths, no API
keys, no environment values, no provider raw payloads, and no transcripts.

`stage_review.json` is the Stage Review / Rework Artifact MVP and the first
save-only user-agent negotiation surface. It allows `review_status` values
`approved`, `needs_revision`, and `blocked`; explicit `stage` values such as
`requirement`, `design_brief`, `assembly_plan`, `candidate_parts`,
`part_request`, `part_review`, `handoff`, and `single_part_result`; and explicit
`target_rework_stage` values from the same controlled vocabulary. Notes and
requested changes are sanitized and length-limited. Saving this artifact does
not call a provider, rerun a pipeline stage, modify CAD artifacts, create a loop
queue, or trigger batch/all-part/assembly generation. Rework execution and
overnight one-part-at-a-time queues remain future work.

Readable artifacts remain limited to workflow source, handoff, reviewed-part,
report, trace, and revision records: `prompt.txt`, `revision_prompt.txt`,
`requirement.json`, `design_brief.json`, `planning_artifact.json`, `input_ir.json`,
`parent_input_ir.json`, parent snapshots, `assembly_plan.json`,
`assembly_plan.md`, `part_create_request.json`, `part_request_review.json`,
`reviewed_part_handoff.json`, `part_execution_request.json`,
`part_result_review.json`, `stage_review.json`, `revision_request.json`, `change_intent.json`,
`revision_plan.json`, `patch.json`, `comparison.json`, `revision_report.md`,
`lineage.json`, `report.json`, `report.md`, `agent_trace.json`, and
`logs/runtime.json`. Downloadable discovery remains limited to `model.step`,
`model.stl`, `preview.png`, and `model.py`.

Editable artifacts are narrower than readable artifacts. The backend can write only `requirement.json`, `planning_artifact.json`, and `input_ir.json`; writes must be JSON objects, pass artifact-specific validation, and are recorded in `logs/runtime.json` under `workflow_console.artifact_edits`.

The backend exposes shared status constants for the current local status vocabulary: `created`, `completed`, `blocked`, `success`, `failed`, `running_or_incomplete`, and `unknown`.

Gate decisions are also file-backed. The backend can record `approve`, `reject`, `return`, and `override` decisions for supported workflow stages by appending to `logs/runtime.json` under `workflow_console.gate_decisions`; no separate decision store or new readable artifact has been added. Public run metadata exposes only a gate summary (`stage`, `action`, `reason`, and `timestamp`), not arbitrary decision payloads.

Future gate actions should expand to include `proceed_with_assumptions`,
`ask_user`, `return_to_requirement`, `return_to_planning`, and
`revise_existing_model` once the backend supports the richer workflow decision
contract.

The local backend should expose only workflow operations:

- Run management: create, open, list, and inspect local run directories.
- Stage operations: run/status/artifacts for Requirement, Planning, Part Modeling, Review, and Outputs.
- Artifact operations: read structured JSON, read Markdown reports, and write confirmed user edits.
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

The NiceGUI UI is intentionally paged:

- Runs: compact run selection, status, child runs, reviewed-part status, and
  STEP/STL availability.
- Requirement Review: read-only original prompt and available negotiation fields
  such as assumptions, missing information, clarification questions, blocked
  reason, and diagnostics, plus save-only Stage Review controls.
- Assembly Plan: compact assembly status and a parts table, not full JSON by
  default, plus save-only Stage Review controls.
- Part Workflow: one-stage reviewed-part action cards gated by upstream
  artifacts.
- Artifacts: collapsed/on-demand allowlisted artifacts and model-file
  availability.

The browser never becomes the source of truth. Create, stage execution, artifact edits, gate decisions, artifact reads, and downloadable discovery all round-trip through the Python backend and existing run artifacts. Editable artifacts remain limited to `requirement.json`, `planning_artifact.json`, and `input_ir.json`; the UI only enables save controls for those files and the backend remains authoritative for validation.

The current UI supports the first usable local workflow loop:

- list existing runs under `outputs/` and `runs/`;
- create a run from a prompt without executing stages;
- select a run and inspect status/current stage plus stage/gate history;
- run Requirement, Planning, Part Modeling, Review, Outputs, or the full text pipeline by safe run id;
- inspect readable artifacts;
- inspect a compact report/trace summary without opening raw JSON;
- inspect existing reviewed-part E2E artifacts, including assembly-plan parts,
  candidate status, part result review status, STEP/STL checks, single-part
  scope checks, lineage checks, and interface metadata checks;
- edit only the allowed JSON handoff artifacts;
- record approve/reject/return/override gate decisions;
- save a structured `stage_review.json` rework intent without rerunning stages;
- list STEP-first downloadables and open the secondary STL preview when `model.stl` exists;
- use an explicit Interact/Release control before the embedded STL viewer captures pointer wheel/drag input.

Review and Outputs are executable local check stages. Review reads the existing `report.json` flow decision and records the review gate status. Outputs checks publishable artifacts, including primary `model.step`, without regenerating CAD. STEP remains the primary CAD artifact; the embedded viewer loads `model.stl` only as a secondary inspection aid.

Reviewed-part awareness is read-only in this slice. The console can inspect
manual-smoke artifacts and discover generated STEP/STL files, but it does not
add batch generation, assembly CAD generation, assembly constraint solving, STEP
assembly export, geometric fit validation, new CAD templates, or automatic
all-part generation.

Both UIs expose reviewed-part actions only when their upstream artifact is
present, and each button calls exactly one backend action. There is still no
chat UI, no editable clarification pipeline, no provider calls for free-form
chat, no automatic rework execution, no loop queue, no automatic all-part
generation, no batch generation, and no assembly generation.

## Security Notes

- Bind to `127.0.0.1` by default.
- LAN or Tailscale usage is acceptable only when explicitly configured.
- Do not expose the server publicly by default.
- Do not provide an arbitrary shell command endpoint.
- Do not allow unrestricted CLI agent execution from the ordinary user workflow.
- Treat generated code and artifacts as local workflow outputs that require review.
