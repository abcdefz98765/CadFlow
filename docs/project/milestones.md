# Milestones

## M0: Existing CadQuery MVP

Done.

- CadQuery examples.
- STEP/STL export.
- Basic validation and reports.
- FreeCAD handoff and assembly helper scripts.

## M1: Workflow-first Refocus

Done in this refactor.

- Standard workflow: `input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs`.
- Standard output directory.
- `CADBackend` abstraction.
- CadQuery backend adapter.
- `mounting_plate` demo restored.
- `knowledge/` and `policies/` directories established.
- PRD, architecture, usage, roadmap, philosophy updated.

## M1.5: IR-first CAD Pipeline

Done in this refactor.

- `CADIR` JSON schema object.
- Text/file to CAD IR parser.
- CAD IR validator.
- Deterministic IR to CadQuery source generator.
- Executor that saves `model.py` before running it in the project output workspace.
- Runtime logging for success/failure.
- Required output contract under `outputs/<part_name>/`.
- IR examples for mounting_plate, spacer, and simple_bracket.
- Pipeline tests covering IR validation, deterministic generation, and output contract.

## M1.75: CAD Agent Loop

Done in current v0.3 work.

- Stateful CAD Agent Loop with max 3 attempts.
- Candidate CadQuery generation and candidate scoring.
- Structured failure analysis from execution logs, validation errors, and missing outputs.
- IR repair engine that preserves `part_type` and only changes targeted fields.
- Enhanced validation for invalid solids, feature clearance risks, dimension deviation, boolean artifacts, and symmetry.
- Required `agent_trace.json` output with attempt history, candidate scores, repair changes, and final selected candidate.
- Regression test proving one failed geometry case can be repaired and regenerated successfully.

## M1.8: STEP-first Inspection And Trace Quality

Cleanup in progress.

- Treat `model.step` as the primary CAD artifact and STL as a derived mesh exchange.
- Add a geometry inspector that records STEP/STL artifact facts, solid count, bounding box, volume, and mounting_plate through-hole count/diameter/spacing when topology is reliable.
- Verify simple vertical edge chamfers on plate-like mounting_plate/enclosure_lid parts when the topology is reliable.
- Mark requested fillets, slots, and unsupported/general chamfer topology as unverified in inspection/report/trace without speculative inference.
- Keep placeholder `preview.png` for now and document real rendering as a deferred follow-up unless a lightweight renderer is available.
- Later verify actual feature realization for slots, general chamfers, fillets, simple pockets, and real rendered previews.
- Add repair diff checks so the system can confirm that IR repair changed only the intended geometry.
- Improve `agent_trace.json` with measured validation targets and inspection summaries.

## M1.9: CAD Benchmarks

Next.

- Create benchmark prompts, expected IR, expected checks, and golden reports.
- Start with mounting plate, spacer, L-bracket, flange, and simple enclosure base.
- Score benchmark success by valid STEP output, required features, key dimensions, trace completeness, and repair behavior.

## M1.10 / v0.4a: Local Workflow Console Backend

Backend foundation complete; HTTP server and frontend remain future work.

- Add a dependency-free Python backend scaffold for the file-first local workflow.
- Define `StageRunner` as the local execution unit: read upstream artifacts, run deterministic Python stages, write downstream artifacts, and record stage history in `logs/runtime.json`.
- Provide run creation, artifact metadata/content reads, deterministic stage execution from existing run artifacts, status derivation, and downloadable file discovery at the Python API layer.
- Provide path-safe run-id operations for future HTTP routes, creating/resolving only under configured `outputs/` and `runs/` roots while rejecting absolute paths, traversal, path separators, duplicate create targets, and unconfigured roots.
- Define a dependency-free future route contract scaffold that maps method/path semantics to by-id backend operations, provides in-process route dispatch for tests, and standardizes success/error envelopes without adding an HTTP server or framework.
- Keep workflow status values centralized for local backend/stage comparisons.
- Record local gate decisions for future staged UI workflows in `logs/runtime.json`, preserving the file-backed state model.
- Allow validated edits only for structured handoff artifacts: `requirement.json`, `planning_artifact.json`, and `input_ir.json`.
- Use the existing `run_text_pipeline` and IR pipeline paths first.
- Keep LLM workers optional and future-facing; stage outputs must still be persisted artifacts.
- Keep `AgentAdapter` separate from `StageRunner`: the adapter owns understanding/planning/explanation, while the runner owns execution/persistence.
- Do not add cloud queues, accounts, multi-user collaboration, benchmark changes, new CAD generator behavior, or a full frontend in this step.

## M1.11 / v0.4a: Web Workflow Console UI And Viewer

Initial local UI slice complete; follow-up polish and review/output stage expansion remain.

- Build a workflow cockpit with a stage timeline for Requirement, Planning, Part Modeling, Review, and Outputs.
- Let users inspect and confirm `requirement.json`, `planning_artifact.json`, `input_ir.json`, reports, and traces before advancing.
- Reuse and evolve `web-viewer` for current-run STL preview when useful; STEP remains the primary CAD artifact.
- Surface verified/unverified inspection state, warnings, errors, and rework decisions.
- Do not implement browser-side CAD editing, general assembly solving, or direct prompt-to-CAD bypasses around artifacts.
- Add `web-viewer/workflow-console.html` as the first operational console screen.
- Add a stdlib-only local bridge, `ai_native_cad.workflow_console.server`, that serves static UI files, dispatches the existing route contract, and serves only whitelisted downloadable artifacts.
- Support listing/selecting runs, creating prompt-only runs, running supported deterministic stages by id, reading artifacts, editing allowed JSON handoff artifacts, recording gate decisions, listing downloadables, and opening the existing STL viewer for `model.stl`.
- Add executable Review and Outputs check stages: Review records the report flow decision; Outputs checks publishable artifacts such as primary `model.step` without regenerating CAD.
- Expose path-free stage history in run metadata and render per-stage last status/run count in the local UI timeline.
- Expose path-free gate decision history summaries and render each stage's latest approve/reject/return/override decision in the local UI timeline.
- Expose a compact report/trace summary in run metadata and render status, flow/rework decisions, warning/error counts, attempts, and final candidate in the local UI.
- Polish artifact inspection with type labels and a useful default selection order that opens `report.md` first when present.
- Add UI running state and visible error banner so long stage actions cannot be double-clicked silently and failures are not hidden in the activity log.
- Replace the 1x1 black `preview.png` placeholder with a visible scaffold image while keeping real rendered previews deferred to the STL viewer path.
- Make the embedded STL viewer scroll-safe by default, with an explicit Interact/Release toggle for rotate and zoom.
- Collapse report, gate, downloads, and activity into a right-side Inspector tab set so the STL preview and workflow controls stay in the first viewport.

## M1.12 / v0.5: LLM Agent Adapter Foundation

Status: released in `v0.5.0` as a local deterministic foundation.

Complete as a local/mock foundation; real provider calls remain future work.

- Define a narrow structural `AgentAdapter` contract for requirement parsing, planning drafts, repair suggestions, and review explanations.
- Keep v0.5 provider identity local/mock only through `DeterministicAgentAdapter`; no API keys, network calls, or provider dependencies are required.
- Route Requirement and Planning stage drafts through the adapter while `StageRunner` remains responsible for validation, artifact persistence, and runtime tracing.
- Persist adapter outputs only through existing handoff artifacts: `requirement.json`, `planning_artifact.json`, and validated Planning-derived `input_ir.json`.
- Record sanitized adapter activity in `logs/runtime.json` without prompts, secrets, tokens, or provider transcripts.
- Reject invalid adapter output before it becomes authoritative.
- Do not let adapter output bypass schema validation, CAD IR gates, or deterministic execution.

## M2: Parser Quality

Next.

- Extract dimensions and hole intent from more natural-language variants.
- Record assumptions and unknowns more precisely.
- Add an internal CAD brief layer for ambiguous or multi-source input before final CAD IR.
- Keep CAD IR and `requirement.json` stable.

## M3: L1 Maker Checks

Next.

- Minimum wall thickness.
- Overhang/support risk.
- STL printability.
- Maker-facing review warnings.

## M4: Backend Expansion

Future.

- build123d backend.
- FreeCAD API backend.
- Browser code-CAD backend evaluation.

## Deferred

- AI Engineering OS.
- Robotics URDF/SDF expansion.
- G-code, slicer, and printer handoff.
- Industrial DFM/DFA.
- Full GD&T.
- FEA.
- Safety-critical release workflow.
