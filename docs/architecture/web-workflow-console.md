# Web Workflow Console

The Web Workflow Console is the future user-facing cockpit for running and reviewing CadFlow workflows.

It is not a browser CAD editor.

## The Web UI Is

- Workflow runner.
- Natural-language prompt interface.
- Agent status display.
- Artifact viewer.
- Report viewer.
- Agent trace viewer.
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

- Add `LLMApiAgentAdapter`.
- Natural language to structured requirement/planning.
- User confirmation for missing or risky fields.

### v0.4c

- Conversational CAD workflow.
- Follow-up questions.
- Confirm-before-generation.
- Compare attempts/candidates.

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

Even when a future stage uses `LLMApiAgentAdapter`, its output must be persisted as a validated artifact before the next stage runs. Chat history, token streams, or browser state must not become the cross-stage source of truth.

## v0.4a Backend Surface

The current scaffold lives under `src/ai_native_cad/workflow_console/`:

- `StageRunner`: deterministic local stage execution and artifact persistence.
- `WorkflowConsoleBackend`: local run listing, artifact metadata/content reads, status derivation, and downloadable-file discovery.

`StageRunner` records local stage history in the existing `logs/runtime.json` artifact under `workflow_console.stages`. This keeps stage status file-based without introducing a database or separate state store.

The Python facade can run supported stages from an existing run directory by reading upstream artifacts: `prompt.txt` for Requirement or full text pipeline, `requirement.json` for Planning, and `planning_artifact.json` or `input_ir.json` for Part Modeling.

It can also create a run without executing stages, writing only `prompt.txt` and local runtime status so a future UI can advance the workflow stage by stage.

The local backend should expose only workflow operations:

- Run management: create, open, list, and inspect local run directories.
- Stage operations: run/status/artifacts for Requirement, Planning, Part Modeling, Review, and Outputs.
- Artifact operations: read structured JSON, read Markdown reports, and write confirmed user edits.
- Gate operations: record approve, override, reject, or return-to-upstream decisions as artifacts.
- File serving: serve `model.step`, `model.stl`, `report.md`, `report.json`, and `agent_trace.json`.

The backend should not change benchmark contracts, add new CAD generator behavior, or make browser state authoritative.

The scaffold does not yet provide HTTP routes, authentication, a database, or a frontend. A FastAPI app can be layered over the Python facade later if the dependency is intentionally added.

## v0.4a UI Surface

The first frontend should stay workflow-oriented:

- Stage timeline: Requirement -> Planning -> Part Modeling -> Review -> Outputs.
- Prompt entry and run controls.
- Artifact inspector for `requirement.json`, `planning_artifact.json`, `input_ir.json`, reports, and traces.
- Report/trace viewer that highlights verified, unverified, warning, error, and rework states.
- Optional preview surface using current-run STL or later GLB assets.

Existing `web-viewer` work can be reused or evolved for artifact preview, but preview remains secondary to the STEP-first workflow.

## Security Notes

- Bind to `127.0.0.1` by default.
- LAN or Tailscale usage is acceptable only when explicitly configured.
- Do not expose the server publicly by default.
- Do not provide an arbitrary shell command endpoint.
- Do not allow unrestricted CLI agent execution from the ordinary user workflow.
- Treat generated code and artifacts as local workflow outputs that require review.
