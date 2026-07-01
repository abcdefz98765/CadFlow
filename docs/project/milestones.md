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

In progress.

- Add a dependency-free Python backend scaffold for the file-first local workflow.
- Define `StageRunner` as the local execution unit: read upstream artifacts, run deterministic Python stages, write downstream artifacts, and record stage history in `logs/runtime.json`.
- Provide run creation, artifact metadata/content reads, deterministic stage execution from existing run artifacts, status derivation, and downloadable file discovery at the Python API layer.
- Provide path-safe run-id operations for future HTTP routes, creating/resolving only under configured `outputs/` and `runs/` roots while rejecting absolute paths, traversal, path separators, duplicate create targets, and unconfigured roots.
- Keep workflow status values centralized for local backend/stage comparisons.
- Use the existing `run_text_pipeline` and IR pipeline paths first.
- Keep LLM workers optional and future-facing; stage outputs must still be persisted artifacts.
- Keep `AgentAdapter` separate from `StageRunner`: the adapter owns understanding/planning/explanation, while the runner owns execution/persistence.
- Do not add cloud queues, accounts, multi-user collaboration, benchmark changes, new CAD generator behavior, or a full frontend in this step.

## M1.11 / v0.4a: Web Workflow Console UI And Viewer

Next.

- Build a workflow cockpit with a stage timeline for Requirement, Planning, Part Modeling, Review, and Outputs.
- Let users inspect and confirm `requirement.json`, `planning_artifact.json`, `input_ir.json`, reports, and traces before advancing.
- Reuse and evolve `web-viewer` for current-run STL preview when useful; STEP remains the primary CAD artifact.
- Surface verified/unverified inspection state, warnings, errors, and rework decisions.
- Do not implement browser-side CAD editing, general assembly solving, or direct prompt-to-CAD bypasses around artifacts.

## M1.12 / v0.5: LLM Agent Adapter

Next after the local Web Workflow Console foundation.

- Add `LLMApiAgentAdapter` behind the stable `AgentAdapter` contract.
- Convert natural language into validated requirement and planning JSON.
- Ask for user confirmation when fields are missing, ambiguous, risky, or safety-relevant.
- Do not let LLM output bypass schema validation, CAD IR gates, or deterministic execution.

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
