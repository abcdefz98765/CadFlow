# Usage

## Scope of this guide

This file documents commands and behavior that exist in the current
implementation. It is not the target product workflow. The Agent-first target is
defined in `FINAL-PRD.md`; the implementation gap is tracked in
`status/current-product-readiness.md`.

The current compatibility pipeline advances through:

```text
input -> requirement -> planning -> part_modeling -> review -> outputs
```

The current supported single-part prompt path uses structured handoff gates:

```text
prompt
  -> requirement.json
  -> Requirement gate
  -> planning_artifact.json
  -> Planning -> CAD IR gate
  -> input_ir.json
  -> CAD Agent Loop
  -> report + agent_trace
```

Requirement 或 Planning gate 返回 `return` 时，流程停止在该 gate：不会写
`input_ir.json`，也不会进入 Part Modeling。输出目录保留已经生成的
`requirement.json` / `planning_artifact.json`、`report.json` / `report.md` 和
`agent_trace.json` 供复核。

Requirement gate 返回 `ask_user` 或 `return_to_requirement` 时，Planning 会先
阻塞，直到用户通过 Web Console 的结构化 Requirement Clarification 表单提交
回答。后端会写入 `requirement_clarification.json`，再生成
`requirement_v2.json`；Planning 优先读取 `requirement_v2.json`。canonical 问题
字段是 `follow_up_questions`，`clarification_questions` 仅作为兼容别名展示。
这个流程不是聊天 UI，也不会把浏览器状态、provider raw response、API key 或
chat transcript 写入公开 artifact。

The current CAD Agent Loop remains legacy IR-first:

```text
input_ir.json
  -> CAD IR
  -> validate IR
  -> candidate CadQuery generation
  -> execution
  -> STEP-first inspection + validation
  -> failure analysis + IR repair + retry, max 3
  -> primary STEP + derived STL
  -> report + agent_trace
```

Assembly 在当前开源初版中表示 assembly intent planning、manufactured/reference parts 列表、backend-neutral assembly config、基础放置和 bounding-box validation、以及 assembly review/report。它不是成熟几何约束求解器，不自动推断任意 CAD 文件的 mating，也不提供完整 tolerance stack-up、工业 DFA、运动仿真或生产级装配放行。

## Run the CAD Agent Loop Pipeline

Generate the tracked examples:

```bash
python examples/ir_pipeline/generate_examples.py
```

Each tracked example writes artifacts beside its own `input_ir.json`:

```text
examples/ir_pipeline/<part_name>/outputs/
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

Python API:

```python
from ai_native_cad.pipeline import run_ir_pipeline

result = run_ir_pipeline({
    "part_type": "mounting_plate",
    "part_name": "mounting_plate",
    "unit": "mm",
    "dimensions": {"length": 80, "width": 40, "thickness": 5},
    "features": {
        "holes": {"diameter": 5, "positions": "corner_4"},
        "chamfer": 1,
    },
    "outputs": ["step", "stl"],
})
print(result["status"])
print(result["output_dir"])
```

Output:

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

The generated `model.py` is saved before execution. Execution runs from the
selected output directory inside the project workspace and logs runtime failures
for analysis, IR repair, and retry. `agent_trace.json` records attempt history,
candidate scores, measured validation targets, inspection summaries, failure
analysis, repair changes, and the final selected candidate. `model.step` is the
primary CAD artifact; `model.stl` is a derived mesh output. For example-local generation, pass
`output_dir="examples/ir_pipeline/<part_name>/outputs"` to `run_ir_pipeline`.

## Run the Prompt Pipeline

Prompt examples use the formal structured path:

```bash
python examples/prompt_pipeline/run_prompt_examples.py
python examples/prompt_pipeline/run_prompt_examples.py mounting_plate_by_holes
```

Python API:

```python
from ai_native_cad.pipeline import run_text_pipeline

result = run_text_pipeline(
    "Generate an 80x40x5 mm mounting plate with four M4 holes.",
    output_dir="outputs/prompt_pipeline/mounting_plate_by_holes",
)
print(result["status"])
```

Successful output:

```text
outputs/prompt_pipeline/<case_id>/
  prompt.txt
  requirement.json
  planning_artifact.json
  input_ir.json
  model.py
  model.step
  model.stl
  report.json
  report.md
  agent_trace.json
```

Benchmarks remain IR-first and continue to consume benchmark `input_ir.json`
cases directly.

## Run the Web Workflow Console

The Console stores user-visible work in a Work-contained layout. Each Work owns
its root and part runs; project-level `outputs/` is for local development and
is not indexed by the Console.

```text
workspace/
  workspace.json
  config.json
  works/
    <work_id>/
      work_manifest.json
      runs/
        <run_id>/
```

Newly created or subsequently mutated Works use Work manifest schema v2.
`part_jobs[].attempts` is the canonical ordered attempt history;
`accepted_part_results` is independent from `active_lineage`; optional
`assembly_job`, `deliverable_packages`, and `artifact_references` fields are
present even when empty. Existing schema-v1 Work manifests are projected in
memory and remain readable. A later successful Work mutation may persist the
projected v2 manifest, but files inside historical Run directories are not
rewritten.

M1 Work mutations enter one `WorkOrchestrator`. Existing deterministic Run
creation and stages are reached through a controlled compatibility adapter.
The internal route contracts are:

```text
POST /api/works
POST /api/works/{work_id}/requirement-run
POST /api/works/{work_id}/part-runs
POST /api/works/{work_id}/parts/{part_job_id}/attempts
POST /api/works/{work_id}/parts/{part_job_id}/design-episodes
```

The Part Job attempt route accepts optional JSON fields `prompt`, `role`, and
`run_id`. It appends an attempt to `part_jobs[].attempts` and does not change
`accepted_part_results`. Successful mutation responses include:

```json
{
  "orchestration": {
    "orchestrator": "work_orchestrator",
    "status": "completed",
    "command": "create_part_attempt",
    "phase": "design",
    "checkpoint": "part_job_attempt",
    "postcondition": "...",
    "next_action": "Build and evaluate this attempt"
  }
}
```

The stdlib Web Console bridge invokes these contracts through
`POST /api/route`. For a later Part Job attempt, send:

```json
{
  "route": "create_work_part_attempt",
  "path_params": {
    "work_id": "fixture_work",
    "part_job_id": "clamp"
  },
  "body": {
    "prompt": "Create another clamp attempt.",
    "run_id": "clamp_attempt_2"
  }
}
```

The equivalent local Python API is:

```python
attempt = backend.create_work_part_attempt(
    "fixture_work",
    "clamp",
    prompt="Create another clamp attempt.",
    run_id="clamp_attempt_2",
)
```

To route a provider-selected design episode for an existing Part Job
attempt, send a path-safe `request_id` and optionally select an owned
`attempt_run_id` and objective override:

```json
{
  "route": "run_work_part_design_episode",
  "path_params": {
    "work_id": "fixture_work",
    "part_job_id": "clamp"
  },
  "body": {
    "request_id": "clamp_design_001",
    "attempt_run_id": "clamp_attempt_2",
    "objective": "Design the clamp around the accepted interfaces."
  }
}
```

The local Python equivalent is
`backend.run_work_part_design_episode("fixture_work", "clamp",
request_id="clamp_design_001", attempt_run_id="clamp_attempt_2")`.
The attempt must already belong to that Part Job. Evidence is appended below
`runs/<run_id>/episodes/design_part/<request_id>/` and registered in the Work as
typed candidate, observation, diagnostic, or gated reviewable-result
references. Repeating the exact request returns persisted evidence without a
second provider call, execution, publication rewrite, or Work rewrite; reusing
the id with different input is rejected.

This route lets the provider choose structured-contract validation or the
registered `model_program` strategy. Model-program execution remains disabled
unless that process explicitly requests the exact attested WSL2 capability.
After successful execution and observation inspection, the CadFlow publication
gate cross-checks lineage, source/parameter/profile/toolchain/attestation
digests, Broker evidence, STEP hash/size, limits, and in-sandbox re-import
facts. Only then can the route register `reviewable_result.json` and its STEP.
Publication does not modify active lineage, accepted-result pointers, or
Deliverable Packages. It has no new Workbench UI action.

Accept one registered reviewable result explicitly with
`POST /api/works/{work_id}/parts/{part_job_id}/reviewable-results/{reviewable_result_id}/accept`.
The body must be empty. This is the only Package 3 route that changes the Part
Job's accepted-result pointer; active design lineage and Run evidence are not
rewritten.

Create a revision attempt with
`POST /api/works/{work_id}/parts/{part_job_id}/reviewable-results/{reviewable_result_id}/revisions`
and body `{"revision_prompt":"...","run_id":"optional_path_safe_id"}`. This
does not change any prior accepted result.

## Evaluate the M2 provider-selected design preview

`run_design_part_episode` remains the lower-level evaluation API behind the M2
preview. It asks an injected JSON-contract provider to choose each next action,
while CadFlow enforces the registered `design_part` capability, semantic
context, budgets, and CadFlow Tool Broker-owned validation and attested
model-program execution.

```python
from pathlib import Path

from ai_native_cad.agents import (
    JsonContractAgentAdapter,
    run_design_part_episode,
)

adapter = JsonContractAgentAdapter(your_injected_json_client)
result = run_design_part_episode(
    adapter=adapter,
    handoff=reviewed_part_handoff,
    artifact_dir=Path("outputs/design_part_preview"),
)
print(result.stop_reason.value, result.validated)
```

The injected client receives registry-compiled JSON action requests. Allowed
actions are `request_context`, `create_contract`, `patch_contract`,
`request_validation`, `create_model_program`, `patch_model_program`,
`request_execution`, `inspect_observation`, `ask_user`, and `stop`. Model
program submissions must contain exactly `api_id`, complete `source`, finite
JSON `parameters`, and `requested_outputs=["step"]`. Execution and inspection
actions contain no provider-selected identity, path, command, environment, or
UID.

With the sandbox capability disabled, execution fails closed before source is
written by the Broker or a candidate process starts. With a valid attestation,
the Episode may execute source only through the fixed worker. Completion then
requires a successful STEP re-import-validated observation and a subsequent
`inspect_observation` action. A validated `cad_ir_draft` remains candidate
evidence. A successful model-program STEP remains candidate evidence until the
independent publication gate passes; reviewable still does not mean accepted.

Each episode now writes `tool_broker_manifest.json`. It records the active
skill's allowed tool definitions and the model-program sandbox capability gate.
The gate is disabled by default and reports unavailable unless the exact
dedicated WSL2 profile passes a fresh startup attestation. The `design_part`
manifest declares only the CadFlow-owned `model_program` delegate; it never
grants direct provider tool, process, or filesystem authority.

The capability can be inspected without providing source or starting a process:

```python
from ai_native_cad.agents import (
    MODEL_PROGRAM_TOOL,
    CadFlowToolBroker,
)

capability = CadFlowToolBroker().capability(MODEL_PROGRAM_TOOL)
assert capability["capability"]["available"] is False
assert "sandbox_unavailable" in capability["capability"]["reason_codes"]
```

CadQuery v1 is the first selected model-program source API. Static policy can be
checked locally without writing, importing, bytecode-compiling, or executing the
source:

```python
from ai_native_cad.agents import (
    CADQUERY_MODEL_PROGRAM_API,
    MODEL_PROGRAM_SOURCE_TOOL,
    CadFlowToolBroker,
)

source = """\
import cadquery as cq

def build_model(parameters):
    width = float(parameters["width"])
    return cq.Workplane("XY").box(width, 20.0, 5.0)
"""

observation = CadFlowToolBroker().invoke(
    MODEL_PROGRAM_SOURCE_TOOL,
    skill_id="model_program",
    payload={"api_id": CADQUERY_MODEL_PROGRAM_API, "source": source},
)
assert observation.success is True
assert observation.output["executed"] is False
assert observation.output["source_retained"] is False
```

The static observation contains a source SHA-256, metrics, policy manifest, and
typed codes; it does not echo the source. The authoritative contract is
`policies/model_program_cadquery_v1.md`. The registered Episode execution action
still re-runs this policy in the Broker; a static success does not make the
sandbox available.

Calling the model-program tool while the profile is disabled, missing,
mismatched, tampered, or fails a probe returns `sandbox_unavailable` with
`side_effect_started=false`. It does not write request source, create a request
candidate directory, invoke the deterministic host CadQuery subprocess, or
publish artifacts.

### Provision and accept the internal WSL2 execution primitive

The runtime uses a dedicated distro named `CadFlow-Sandbox-CQ-v1`. It does not
reuse the user's normal Ubuntu distro. The repository contains only the
manifest, hashes, lock, policy, worker, and scripts; the rootfs cache,
wheelhouse, and VHDX are stored below
`%LOCALAPPDATA%\CadFlow\sandbox`.

Verify repository content binding, then perform the explicit deployment phase:

```powershell
F:\Tools\PowerShell\7\pwsh.exe -NoProfile -Command `
  ".venv-cadflow\Scripts\python.exe sandbox\wsl2\verify_manifest.py"

F:\Tools\PowerShell\7\pwsh.exe -NoProfile -File `
  sandbox\wsl2\provision.ps1
```

Provisioning is the only phase that downloads the pinned rootfs/wheels or uses
package repositories. It verifies hashes, imports WSL2, installs exact package
versions, disables DrvFs automount and Windows interop, seals the runtime, and
runs the full attack probe. It never automatically overwrites or unregisters
an existing distro. A name/path/state conflict fails closed. `-ResumeExisting
-RepairUnattested` is only for a partial deployment from this script that has
no `/opt/cadflow/ATTESTED` marker; it refuses an already attested runtime.

Execution is opt-in per CadFlow process. Run the current-host acceptance in a
fresh PowerShell process rather than setting the variable globally:

```powershell
F:\Tools\PowerShell\7\pwsh.exe -NoProfile -Command `
  '$env:PYTHONPATH="src"; $env:CADFLOW_MODEL_PROGRAM_SANDBOX="1"; `
  .venv-cadflow\Scripts\python.exe sandbox\wsl2\acceptance.py'
```

`CADFLOW_MODEL_PROGRAM_SANDBOX=1` merely requests a live probe; it cannot
override the manifest, hashes, active controls, or attestation. The optional
`CADFLOW_MODEL_PROGRAM_SANDBOX_MANIFEST` path exists for controlled testing and
must still match the sealed distro attestation. No execution-phase network,
shell, arbitrary command, provider path, dependency installation, or host
filesystem authority is exposed.

Successful execution first produces only Run-relative
`candidate/execution_observation` evidence and `model.step`. The Episode stores
complete candidate submissions and sanitized structured observations. The
product route may then publish a separate reviewable record only after the
local gate passes. Candidate evidence remains `reviewable=false`; the published
record remains `accepted=false` and `deliverable=false` until explicit user
acceptance.

Repeat the registered Episode's current-host live acceptance with:

```powershell
$env:PYTHONPATH = "src"
$env:CADFLOW_MODEL_PROGRAM_SANDBOX = "1"
.venv-cadflow\Scripts\python.exe examples\provider_smoke\model_program_episode_eval.py
```

The script uses a credential-free scripted action provider and verifies the
complete Episode → Broker → WSL worker → STEP re-import → inspection path. It
also asserts that no reviewable, accepted, or deliverable record is created.

Repeat the Package 3 product-route publication acceptance with:

```powershell
$env:PYTHONPATH = "src"
$env:CADFLOW_MODEL_PROGRAM_SANDBOX = "1"
.venv-cadflow\Scripts\python.exe examples\provider_smoke\reviewable_product_route_eval.py
```

The script uses a temporary Workspace and scripted provider. It verifies
reviewable publication, STEP identity, unchanged pointers/deliverables before
acceptance, exact replay, the explicit acceptance route, and revision pointer
preservation. Its acceptance mutation exists only in that temporary test Work.

Repeat the local acceptance check with:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe examples\provider_smoke\tool_broker_gate_eval.py
```

The command creates no durable output. Its JSON summary must report
`passed=true`, `available=false`, `sandbox_unavailable`,
`side_effect_started=false`, and `candidate_directory_created=false`.

Repeat the CadQuery v1 static-policy acceptance check with:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe examples\provider_smoke\model_program_policy_eval.py
```

Its summary must report `passed=true`, allowlisted source accepted, forbidden
source rejected with sanitized codes, `source_retained=false`, and a separate
execution result of `sandbox_unavailable` with no candidate directory.

Repeat the original structured-contract WorkOrchestrator acceptance check with:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe examples\provider_smoke\work_design_episode_eval.py
```

Its summary must report `passed=true`, one idempotent replay, exactly three
scripted provider calls, four registered evidence references, unchanged
protected Work state and original Run prompt bytes, and zero accepted,
deliverable, STEP, STL, or model-program products.

The Console presents workflow summaries and final STEP, STL, and preview
deliverables. Raw JSON, agent traces, runtime logs, and generated scripts stay
in the local run directory for developer inspection.

For the NiceGUI Workbench:

```powershell
.\scripts\start_nicegui_console.ps1
```

Select a Work to open **Overview / Design**, the primary Agent-first surface.
It shows the objective, compact four-phase orientation, current recommendation,
Agent activity, geometry, reviewable or accepted result, validation and
limitations, primary action, and Part Job summary. The four phases are not a
wizard. **Workflow**, **Parts**, and **History** remain reachable as detailed
secondary views, and Historical Run Snapshot remains read-only.

The existing Workflow page still provides the detailed graph for Requirement,
Clarification, Planning, Assembly Plan, reviewed-part handoff, CAD IR draft,
part result review, workflow review, and rework. Selecting a node opens the
existing stage detail and controlled artifact viewer. Raw ids, paths, Episode
evidence, Broker/WSL2/toolchain/attestation data, hashes, and validator details
are collapsed under Advanced/Evidence.

The page now leads with a Work hero, active lineage Run strip, one recommended
action, and a horizontally scrollable dot workflow graph. The selected stage is
read left-to-right as **User Input → Agent Interpretation / Decision → Agent
Output**. On a narrow screen, the same blocks stack in that causal order while
the graph and Run strip retain their topology through horizontal scrolling.
Contract examples explicitly say that CAD IR was validated and CAD execution
was skipped; `input_ir.json` is present while STEP/STL are not expected.

The Console separates accepted inputs, execution state, result state, agent
review, and user approval. A generated STEP/STL result appears as reviewable
output until the user explicitly approves it. Only the Run referenced by
`accepted_part_results[part_id]` appears under Accepted Deliverables. Failed
candidate execution preserves report and trace evidence but does not publish
`model.py`, STEP, STL, or preview files in the Run product location.

Registered reviewable model-program output contains STEP only. For visual
inspection, the Workbench resolves the exact manifest-owned, validated STEP by
Work and artifact id, creates an ephemeral STL in the system temporary
directory, and displays it through the existing STL viewer. That temporary mesh
is deleted after the response and is never registered as evidence, accepted as
a result, or treated as a deliverable.

The corresponding local-only NiceGUI routes are:

- `GET /api/work-artifacts/{work_id}/{artifact_id}/download` for an exact
  registered reviewable or accepted artifact;
- `GET /api/work-artifacts/{work_id}/{artifact_id}/preview.stl` for the
  ephemeral viewer mesh of a registered, validated reviewable or accepted STEP.

Neither route accepts a filesystem path. Existing deterministic downloads and
STL preview continue to use `GET /api/downloads/{run_id}/{filename}`.

For local visual acceptance, open deterministic and scripted-provider Works in
Overview / Design, then inspect desktop (1440/1024) and mobile (390–430) widths.
Confirm objective, capability label, phase orientation, geometry, Agent
activity, reviewable versus accepted state, Accept, natural-language Revise,
Part Jobs, collapsed Advanced/Evidence, detailed Workflow, and Current Work
versus read-only Snapshot context.

Workflow has two explicit contexts. **Current Work** shows the Work manifest's
active aggregated lineage and allows workflow actions against the action's
displayed target Run. Clicking a Run in History opens a **Historical Run
Snapshot**: it is immutable and read-only, does not claim to represent the
complete current Work, and only permits returning to Current Work or creating a
new rework attempt when available. A newer failed attempt never replaces the
accepted active lineage merely because it has the latest timestamp.

Artifacts remain the source of truth. The UI does not create a database, cloud
state, account system, free chat transcript, or browser-owned workflow state.

The raw artifact viewer includes a controlled override editor for selected JSON
intermediate artifacts only. A user can edit `requirement_v2.json`,
`planning_artifact.json`, `assembly_plan.json`, reviewed-part request/review
handoff artifacts, `cad_ir_draft.json`, `input_ir.json`, and
`stage_review.json`. The editor validates JSON and schema/safety rules before
saving. It writes versioned files under `edits/` and an active pure-JSON
override under `edits/active/`; it does not overwrite the original artifact.
Reports, traces, prompts, runtime logs, generated code, STEP/STL files,
provider raw payloads, transcripts, secrets, Python/CadQuery code, and shell
commands are rejected.

Downstream stages resolve overrides explicitly: Planning prefers a valid
`requirement_v2.json` override; Part Request creation prefers an
`assembly_plan.json` override; Reviewed Part Create prefers a
`reviewed_part_handoff.json` override and can use a validated
`cad_ir_draft.json` override as explicit user CAD IR. Runtime logs record when
an override is saved or consumed.

Reviewed-part actions still follow the existing backend path:

```text
reviewed_part_handoff.json
  -> part_execution_request.json
  -> AgentAdapter.create_part_ir(...)
  -> cad_ir_draft.json
  -> validate_input_ir_draft / validate_ir
  -> run_ir_pipeline or blocked_cad_ir_validation
```

Current CAD limitations are unchanged: no full robot-arm assembly generation,
no automatic all-part generation, no batch queue, no new `upper_link` template,
and no automatic fallback to `mounting_plate`.

## Run the Legacy Workflow

One-command demo:

```bash
python examples/workflow/mounting_plate_demo.py
```

Python API:

```python
from ai_native_cad import run_workflow

result = run_workflow(
    "Generate an 80 mm x 40 mm x 5 mm mounting plate with four M4 clearance holes.",
    output_dir="runs/mounting_plate_demo",
)
print(result.status)
print(result.output_dir)
```

输出目录：

```text
runs/mounting_plate_demo/
  input.md
  requirement.json
  part_spec.json
  plan.md
  model.py
  review.md
  exports/
    model.step
    model.stl
  logs/
    run.json
    generation.json
```

## Run the Mounting Plate Demo

```bash
python examples/workflow/mounting_plate_demo.py
python examples/parts/mounting_plate/model.py
```

## Run the Pet Button Concept Part

```bash
python examples/parts/circular_button/model.py
```

This pet communication button uses a large low round press surface, an underside
6x6mm tactile-switch pocket, a central actuator post, terminal/solder clearance
slots, anti-slip pad recesses, and a side wire-harness outlet. It is a printable
concept part, not a chew-proof or sealed product.

## Run the Pet Button Assembly

```bash
python examples/assemblies/pet_button/parts/pet_button_base/model.py
python examples/assemblies/pet_button/parts/pet_button_switch_plate/model.py
python examples/assemblies/pet_button/parts/pet_button_tactile_switch/model.py
python examples/assemblies/pet_button/parts/pet_button_cap/model.py
python -m ai_native_cad.assembly_validator examples/assemblies/pet_button/assembly.json
```

This is the preferred structure for a real pet button because it separates the
base, moving cap, switch carrier, and tactile switch reference envelope.
Review `examples/assemblies/pet_button/assembly_plan.md` before treating the
placement configs as approved assembly intent. The validator writes
`assembly_validation.json`, `assembly_validation.md`, and `assembly_review.md`.

The assembly loop is:

```text
part reports -> assembly_plan -> high-risk confirmation gate -> assembly.json / constraint_assembly.json -> basic validation -> assembly_review.md
```

Example scripts generate artifacts next to their own `model.py` files:

```text
examples/parts/mounting_plate/model.step
examples/parts/mounting_plate/model.stl
examples/parts/mounting_plate/report.json
examples/parts/mounting_plate/report.md
```

## Run Tests

```bash
python -m pytest tests/ -q
```

## Windows / CadQuery Environment Note

CadQuery may be sensitive to Python environment conflicts. Prefer a clean virtual
environment:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip setuptools wheel
python -m pip install -e ".[dev]"
```

If pip-based installation fails, create a clean conda environment and install
CadQuery from conda-forge:

```bash
conda create -n cadflow python=3.11 -c conda-forge cadquery pytest
conda activate cadflow
python -m pip install -e . --no-deps
```

Avoid repairing a conflicted base conda environment in place.

## Good User Input

推荐描述：

```text
生成一个 80x40x5 mm 的安装板，四角 M4 通孔，孔中心离边 8mm。
优先保证孔位和板厚准确，倒角可以简化。输出 STEP/STL，并写出假设。
```

Agent 应输出或保留：

- 原始输入：`input.md`
- CAD IR：`input_ir.json`
- 结构化需求：`requirement.json`
- 单零件规格：`part_spec.json`
- 建模计划：`plan.md`
- 参数化模型源码：`model.py`
- 审查报告：`review.md`
- 导出文件：`exports/`
- 运行日志：`logs/run.json`、`logs/generation.json`

IR-first pipeline 应输出或保留：

- CAD IR：`input_ir.json`
- 生成代码：`model.py`
- Primary CAD artifact / FreeCAD-compatible exchange：`model.step`
- Derived mesh exchange：`model.stl`
- 验证报告：`report.json`、`report.md`
- 预览占位图：`preview.png`，真实几何渲染 deferred
- agent loop 追踪：`agent_trace.json`，包含 measured validation targets 和 inspection summary
- 执行日志：`logs/runtime.json`

Prompt pipeline 还应输出或保留：

- 原始 prompt：`prompt.txt`
- 结构化需求：`requirement.json`
- 规划交接物：`planning_artifact.json`
- CAD IR：`input_ir.json`，其 `source.planning_handoff` 记录 Planning -> CAD IR trace

## Check Levels

当前代码仍使用 legacy `L0`–`L4` 字段：只真正支持 `L0 Playground`。
`L1 Maker` 会输出报告框架，提醒后续需要补最小壁厚、悬垂、支撑和 STL
可打印性检查。

`L2/L3/L4` 是架构预留，不代表当前可以自动完成工程放行。

目标产品对用户采用 `Explore / Engineer / Release` assurance：

- 当前 L0 能力大致属于 Explore；
- Engineer 需要明确接口、材料、工艺、公差、载荷和实际测量证据；
- Release 是未来的领域专用验证配置，不能从 L2/L3/L4 标签自动推导。

权威规则见 `../policies/check_levels.md`。
