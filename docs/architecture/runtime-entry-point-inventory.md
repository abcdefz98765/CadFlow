# Runtime Entry-Point Inventory

Status date: 2026-08-01.

Scope: every current product-facing or public Python entry point that creates a
Work/Run, accepts a prompt, creates or executes CAD IR, performs the
reviewed-part bridge, or creates a revision. Read-only routes and pure
validators are omitted unless they expose one of those paths.

Classifications:

- **target product** — retained as a user-facing command adapter and later
  routed through the single Work orchestrator;
- **compatibility** — retained for deterministic and historical Run support,
  but not allowed to define new target architecture;
- **evaluation** — opt-in example, smoke, benchmark, or golden verification;
- **removable** — duplicated transitional path with no future product authority.

This inventory began as the migration baseline. M1 dispositions below now
record the implemented orchestrator boundary.

## Work and Run creation surfaces

| Entry point | Current caller/surface | Classification | M1 disposition |
| --- | --- | --- | --- |
| `WorkflowConsoleBackend.create_work` / `POST /api/works` | Legacy console | target product | Thin adapter to `WorkOrchestrator.create_work`. |
| `create_work_requirement_run` / `POST /api/works/{work_id}/requirement-run` | Legacy console | target product | Thin adapter to `WorkOrchestrator.begin_intent`; manifest owns the Run reference. |
| `create_work_part_runs` / `POST /api/works/{work_id}/part-runs` | Legacy console | target product | Thin adapter that appends first-class Part Job attempts. |
| `create_work_part_attempt` / `POST /api/works/{work_id}/parts/{part_job_id}/attempts` | Backend/API | target product | Appends a later ordered attempt through `WorkOrchestrator.create_part_attempt`; acceptance is unchanged. |
| `run_work_part_design_episode` / `POST /api/works/{work_id}/parts/{part_job_id}/design-episodes` | Backend/API | target product | Routes an owned attempt through `WorkOrchestrator` and `AgentDesignPort` for validation-only provider-selected evidence; no CAD execution, reviewable publication, lineage change, or acceptance authority. |
| `WorkflowConsoleBackend.create_golden_example` / example API route | Legacy console | evaluation | Keep opt-in; it must not become a product create path. |
| `WorkflowConsoleBackend.create_run_by_id` / `POST /workflow/runs/{run_id}` | Low-level console/developer run | compatibility | Isolate behind compatibility/diagnostics; it has no Work ownership by itself. |
| `StageRunner.create_run` | Stage runner | compatibility | Same low-level Run creation path; no new product callers. |
| `run_golden_desktop_robot_arm` and `scripts/run_golden_desktop_robot_arm.py` | Executable golden | evaluation | Preserve deterministic regression evidence. |

## Prompt and text create surfaces

| Entry point | Current behavior | Classification | M1 disposition |
| --- | --- | --- | --- |
| `run_text_pipeline` | prompt → requirement → CAD IR → deterministic execution | compatibility | Preserve supported-family fallback; future product calls it only through a compatibility adapter. |
| `StageRunner.run_text_pipeline` and `run_stage(..., "text_pipeline")` | Console wrapper over `run_text_pipeline` | compatibility | Keep for legacy Workflow Diagnostics. |
| `run_agent_create_pipeline` | prompt → adapter planning → CAD IR → execution | compatibility | Name does not imply Agentic design; keep honestly labeled one-shot orchestration. |
| `run_provider_create_pipeline` | provider-backed prompt create | evaluation | Manual/provider evaluation only until the M2 loop is product-integrated. |
| `run_provider_normalized_create_pipeline` | provider normalization plus deterministic CAD IR | removable | Freeze and migrate evaluation callers; do not add product dependencies. |
| `run_provider_normalized_design_create_pipeline` | normalized design/assembly evaluation | evaluation | Keep only for opt-in quality evaluation; it does not generate an Assembly Job. |
| `CADWorkflow.run` / `run_workflow` | older prompt workflow | compatibility | Preserve library compatibility; no target-product state authority. |
| `ir_from_text` | text-to-legacy CAD IR parser helper | compatibility | Retain for deterministic tests and old callers only. |
| `RequirementAgent.parse` and adapter `parse_requirement` | prompt interpretation | compatibility | Becomes an Intent service behind the future orchestrator; not a peer product path. |
| `examples/prompt_pipeline/run_prompt_examples.py` | prompt examples | evaluation | Keep as regression/evaluation. |
| `examples/provider_smoke/create_workflow_smoke.py` | manual provider create | evaluation | Keep opt-in and provider-evidence-only. |
| `examples/provider_smoke/provider_create_eval.py` | provider quality evaluation | evaluation | Keep opt-in; no product claims. |
| `examples/provider_smoke/normalized_design_eval.py` | complex normalized design evaluation | evaluation | Keep opt-in; no assembly-generation claim. |
| `examples/provider_smoke/parse_requirement_smoke.py` | provider requirement smoke | evaluation | Keep opt-in. |

## CAD IR creation and execution surfaces

| Entry point | Current behavior | Classification | M1 disposition |
| --- | --- | --- | --- |
| `run_ir_pipeline` | validates and executes legacy closed-family CAD IR | compatibility | Canonical deterministic execution service during M1; future orchestrator invokes it through a typed compatibility port. |
| `StageRunner.run_part_modeling` and `run_planning_to_part_modeling` | console wrappers over CAD IR conversion/execution | compatibility | Keep for Diagnostics; no new product orchestration. |
| `DesignPlannerFakeAgentAdapter.generate_candidate_plans` / conversion to IR | deterministic plan-to-IR | compatibility | Retain for supported-family regression. |
| `AgentAdapter.create_part_ir` implementations | reviewed handoff → one legacy CAD IR | compatibility | Retain as one-shot M1 behavior; not a real Agentic Design Episode. |
| `run_create_part_ir_episode` | fixed request/submit/validate episode | compatibility | Preserve for regression; M2 replaces the proposer behavior, not M1. |
| `run_design_part_episode` | provider-selected structured-contract episode preview | evaluation service | Called through the target-product `AgentDesignPort` for validation-only evidence and remains directly usable for evaluation; no CAD execution or publication authority. |
| `ir_from_file`, `ir_from_planning_artifact` | legacy CAD IR constructors | compatibility | Retain for old examples and migrations. |
| `runner.run_part` | old `part_type` dynamic builder path | removable | Freeze; migrate callers to the deterministic IR compatibility executor. |
| `CADGenerator.build` | old workflow CAD builder | compatibility | Retain only through `CADWorkflow`. |
| `examples/ir_pipeline/generate_examples.py` | IR examples | evaluation | Keep as regression/evaluation. |
| `benchmarks.runner` | deterministic IR benchmark | evaluation | Keep; benchmark output is not Work product state. |
| part and assembly example `model.py` files | direct example model execution | evaluation | Keep as fixtures/examples, never provider authority. |

## Reviewed-part bridge surfaces

| Entry point | Current behavior | Classification | M1 disposition |
| --- | --- | --- | --- |
| `create_part_request_from_assembly_plan` / `run_assembly_part_request_pipeline` | legacy Assembly Plan → one Part Request | compatibility | Preserve for existing Runs; does not create an Assembly Job. |
| `review_part_create_request` / `run_part_request_review_pipeline` | deterministic part-request review | compatibility | Preserve as legacy checkpoint. |
| `create_reviewed_part_handoff` / `run_reviewed_part_handoff_pipeline` | reviewed request → handoff | compatibility | Preserve as legacy checkpoint. |
| `run_reviewed_part_single_create_pipeline` | handoff → CAD IR → deterministic child result | compatibility | Preserve, routed through Part Job attempt compatibility metadata. |
| `run_reviewed_part_agent_ir_create_pipeline` | alias to reviewed-part create | removable | Keep the alias temporarily; migrate callers to the single compatibility bridge. |
| `review_part_result` / `run_part_result_review_pipeline` | deterministic child-result review | compatibility | Preserve; reviewable remains distinct from accepted. |
| `WorkflowConsoleActions.create_part_request`, `review_part_request`, `create_reviewed_handoff`, `create_reviewed_part`, `review_part_result` and matching `/api/actions/*` routes | legacy console action chain | compatibility | Keep in Workflow Diagnostics; do not reproduce in the new Workbench. |
| `WorkflowConsoleActions.approve_part_result` | explicit accepted-part pointer mutation | target product | Calls `WorkOrchestrator.accept_part_result`, registers explicit output references, and leaves active lineage unchanged. |
| `WorkflowConsoleActions.select_candidate_part` | explicit Work candidate selection | target product | Preserves versioned Run override evidence and routes the Work pointer through `WorkOrchestrator.select_candidate`. |
| `examples/provider_smoke/reviewed_part_single_create_smoke.py` | manual bridge smoke | evaluation | Keep opt-in. |

## Revision and rework surfaces

| Entry point | Current behavior | Classification | M1 disposition |
| --- | --- | --- | --- |
| `run_agent_revision_pipeline` | field-level legacy CAD IR revision into child Run | compatibility | Preserve narrow revision behavior and immutable parent evidence. |
| `WorkflowConsoleBackend.run_revision_by_id` / `POST /workflow/runs/{run_id}/revisions/{child_run_id}` | console revision wrapper | compatibility | Keep in Diagnostics; future product revision becomes an orchestrator command. |
| adapter `parse_revision_request` and `create_revision_plan` | one-shot revision intent/plan | compatibility | Keep behind the deterministic revision adapter. |
| `WorkflowConsoleActions.run_rework` / `/api/actions/rework` | stage-review-driven rework | compatibility | Preserve legacy Run recovery; it may advance active lineage but never acceptance. |
| `WorkflowConsoleActions.save_stage_review` | writes rework intent | compatibility | Preserve append-only review evidence. |

## Direct assembly and drawing executables

These are not create paths for the current product:

| Entry point | Classification | M1 disposition |
| --- | --- | --- |
| `assembly_planner.create_assembly_plan` and `create_assembly_configs` | compatibility | Planning/config helpers only; they do not establish Assembly Job product state. |
| `scripts/freecad_assembly.py`, `scripts/freecad_constraint_assembly.py` | evaluation | Remain disconnected manual utilities; no Assembly-generation claim. |
| `scripts/freecad_techdraw.py` | evaluation | Remains a disconnected helper; no Deliverable Package claim. |

## Required consolidation sequence

1. Keep the deterministic compatibility spine green. **Complete.**
2. Introduce `WorkOrchestrator` commands using the v2 Work records.
   **Complete.**
3. Adapt target-product Work mutations to those commands. **Complete.**
4. Put product use of deterministic pipelines behind one typed compatibility
   port. **Complete.**
5. Keep evaluation scripts opt-in and outside Work publication.
6. Remove the two duplicated aliases only after repository callers migrate.

Steps 5–6 are ongoing repository hygiene and do not create a competing product
authority. M1 runtime consolidation passed acceptance on 2026-07-27.
