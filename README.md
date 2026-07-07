# CadFlow

CadFlow is an early-stage workflow-first natural-language parametric CAD toolkit.

Python package: `ai_native_cad`

CadFlow is natural-language first for users, but structured-workflow first internally.
Users describe CAD intent in plain language. CadFlow converts that into auditable requirement, planning, CAD IR, generation, validation, repair, and report artifacts.

The product direction is iterative natural-language CAD workflow, not one-shot
Text-to-CAD. Users may start with incomplete intent, review explicit
assumptions, revise a generated or imported model later, and compare parent and
child runs through traceable artifacts.

本项目不是宏大的 AI Engineering OS，也不是一次性 Prompt to STL。短期目标是保留一个能跑的自然语言建模 MVP，同时把工程结构调整为可追踪、可替换后端、可逐步引入知识和策略的 CAD workflow。

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
      -> feedback / revision -> child run -> comparison
```

Core architecture:

```text
User Prompt
  ↓
Agent Adapter
  ↓
Requirement + Planning
  ↓
CAD IR
  ↓
CAD Agent Loop
  ↓
STEP-first artifacts
  ↓
Web Workflow Console
```

自然语言 prompt 现在先走结构化 handoff：

```text
prompt
  -> requirement.json
  -> Requirement gate
  -> planning_artifact.json
  -> Planning -> CAD IR gate
  -> input_ir.json
  -> CAD Agent Loop
```

Requirement 或 Planning gate 返回 `return` 时，流程停止在该 gate：不会写
`input_ir.json`，也不会进入 Part Modeling，但会保留可审查的 artifact、
report 和 trace。CAD Agent Loop 和 benchmark 仍保持 IR-first：

```text
input_ir.json
  -> CAD IR
  -> validate IR
  -> CAD Agent Loop
       -> candidate CadQuery generation
       -> execution
       -> STEP-first inspection + geometry validation
       -> failure analysis
       -> IR repair
       -> retry, max 3 attempts
  -> primary STEP + derived STL
  -> report + agent_trace
```

Future workflow decisions are richer than only proceed/return:

- `proceed`
- `proceed_with_assumptions`
- `ask_user`
- `return_to_requirement`
- `return_to_planning`
- `revise_existing_model`

For L0 Playground and early L1 Maker workflows, CadFlow may proceed with
explicit assumptions when the risk is low. Those assumptions must be written into
artifacts and shown to the user. For L2/L3/L4 workflows, missing engineering
critical fields such as material, loads, tolerances, fit, safety constraints, or
certification requirements must block or require focused confirmation.

Requirement clarification is now artifact-backed for the local Web Console:
focused `follow_up_questions` can be answered as structured form fields, saved
to `requirement_clarification.json`, and applied to produce `requirement_v2.json`
before Planning continues. This is intentionally not a chat UI or cloud state.

Desktop 2DOF Robot Arm smoke coverage is documented in
[`docs/smoke-tests/desktop-robot-arm.md`](docs/smoke-tests/desktop-robot-arm.md).
That path validates Requirement clarification and assembly candidate planning
through one reviewed part request; it does not mean CadFlow generates a complete
robot arm assembly.

装配阶段也按闭环推进：

```text
requirement + part reports -> assembly_plan -> confirmation gate -> assembly configs -> validation -> assembly_review
```

Assembly in the current open-source baseline means:

- assembly intent planning
- part list / manufactured parts / reference components
- backend-neutral assembly config
- basic placement and bounding-box validation
- assembly review/report generation

It does not currently mean:

- mature geometric constraint solving
- automatic mating inference for arbitrary CAD files
- full tolerance stack-up
- industrial DFA
- motion simulation
- production-ready assembly release

Reviewed Part Single-Part E2E MVP:

```text
multi-part prompt
  -> normalized provider design create
  -> assembly_plan.json
  -> part_create_request.json
  -> part_request_review.json
  -> reviewed_part_handoff.json
  -> CadIrAgent / AgentAdapter.create_part_ir
  -> validated child input_ir.json
  -> one child STEP-first single-part run
  -> model.step / model.stl
  -> part_result_review.json
```

This checkpoint supports planning a multi-part prompt, selecting one reviewed
candidate part, asking the active agent adapter to synthesize CAD IR for that
reviewed handoff, validating the IR locally, generating only that child
single-part STEP/STL through the CAD Agent Loop, and reviewing the child result
locally. It does not generate a full assembly, generate all parts, solve
assembly constraints, export a STEP assembly, or geometrically validate fit
between parts yet. The normalized/extract-compile create pipeline remains a
conservative fallback and provider evaluation path; it is not the default Web
reviewed-part CAD entry.

NiceGUI Work Dashboard MVP:

```text
Work / Project
  mutable user-visible engineering task with an optional manifest
  -> current state pointer, part matrix, workflow nodes, products, actions

Run
  immutable append-only execution record
  -> one attempt, stage, action result, or rework child

Part Job
  part-level task inside a Work
  -> may have multiple attempts/runs
```

The NiceGUI console now defaults to a workspace-oriented local console instead
of a raw run list. Workspace state lives under the explicitly selected
workspace root, which may be outside the repository: `workspace.json`
identifies the local workspace, `config.json` stores provider/model/retry
settings plus the workflow advancement mode, and new Works are real local
entities backed by `<workspace>/works/<work_id>/work_manifest.json`. Older Works
can still be
inferred from existing artifacts such as `assembly_plan.json`,
`workflow_review.json`, `stage_review.json`, lineage, reviewed-part bridge
artifacts, part result reviews, and rework decisions. The dashboard shows
overall status, part counts, readiness/risk, current/latest run, next action,
ordered workflow nodes, a first-class Parts Matrix, human-facing products, and
append-only run history. Low-level and unclassified runs are available from the
Runs page behind explicit detail toggles, not mixed into the Work list.
Legacy manifests under `outputs/_works/<work_id>/work_manifest.json` are read
for compatibility, but new project/work state belongs under the selected
workspace. Work requirement input creates a root run under `<workspace>/runs/`;
part split confirmation creates per-part run containers there. `manual_confirm`
pauses for user confirmation, while `auto_advance` can create follow-on run
containers when split artifacts are available. Neither mode adds automatic
all-part CAD generation.

Rework creates new runs/attempts and may update the inferred Work current state;
old run artifacts are not overwritten or mutated. This MVP adds no new CAD
capability: no loop queue, overnight execution, automatic all-part generation,
batch generation, assembly generation, STEP assembly export, new CAD templates,
or lid/cover support.

## 当前定位

- **Workflow First**：每次任务都保留输入、结构化需求、建模计划、模型代码、审查报告、导出文件和日志。
- **Backend Agnostic**：workflow 层不直接绑定 CadQuery、FreeCAD 或未来 build123d/JSCAD 后端。
- **Engineering over Geometry**：先表达工程意图、关键尺寸、约束和检查，再生成几何。
- **Traceable by Default**：默认输出完整项目记录，方便复核和迭代。
- **Iterative by Default**：支持 first draft、用户反馈、修订计划、patch、child run、old/new comparison。
- **Skill Oriented**：把 requirement、planning、part modeling、assembly、review 收束为少量职责清晰的 skill。
- **Knowledge Ready / Policy Ready**：`skills/<step>/knowledge/` 放步骤内知识，顶层 `knowledge/` 只做跨 skill 索引，`policies/` 放全局策略和等级定义。

CadFlow is an AI-assisted natural-language CAD workflow system, a workflow-first CAD agent scaffold, and a STEP-first parametric CAD generation pipeline. It is not a browser CAD editor, mesh generation system, prompt-to-STL toy, production-ready CAD engineer replacement, full FreeCAD/SolidWorks replacement, or cloud SaaS platform at this stage.

## Current Limitations

- Local/mock workflows include deterministic parser/template fallbacks for CI,
  offline development, and guardrails; these are not the primary product
  architecture for reviewed-part CAD IR synthesis.
- Unknown or underspecified requests may block at Requirement, Planning, or CAD
  IR validation rather than silently falling back to an unrelated template.
- Revision workflow, model intake, and external CAD-file editing are documented
  product directions; full revision execution is not implemented yet.
- Current generated models are suitable for exploration and review, not production release.
- L0 Playground is the only fully supported check level today.
- L1 Maker currently provides a report scaffold, not complete printability validation.
- L2/L3/L4 are reserved workflow levels and do not imply engineering sign-off.
- Assembly support exists in the initial open-source version, but it is a basic planning/config/validation workflow, not a full constraint solver or industrial assembly system.
- All outputs require human review before manufacturing or real-world use.

## 安装

```bash
pip install -e .
```

开发与测试：

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

In constrained Windows/CadQuery/tool-timeout environments, the monolithic
pytest command can exceed the runner timeout even when the tests are healthy.
Use the command above for normal local testing. If the runner times out, run
the same suite split by file or small file groups, for example:

```bash
python -m pytest tests/test_agent_adapter.py -q
python -m pytest tests/test_ir_pipeline.py tests/test_runner.py -q
python -m pytest tests/test_workflow.py tests/test_workflow_console.py tests/test_requirement_parser.py -q
python -m pytest tests/test_exporter.py tests/test_design_checks.py tests/test_benchmarks.py tests/test_assembly_validator.py tests/test_agent_loop.py -q
```

The split fallback should not change test selection or expectations; it only
keeps long-running CAD-related files inside short command time limits.

### Experimental provider-backed adapter

The default workflow remains deterministic and offline. For provider debugging,
construct a JSON-contract adapter explicitly:

```python
from ai_native_cad.agents import make_json_contract_adapter_from_env
from ai_native_cad.workflow_console.stage_runner import StageRunner

adapter = make_json_contract_adapter_from_env("deepseek")  # or "openai"
runner = StageRunner(agent_adapter=adapter)
result = runner.run_requirement("Make a spacer washer.")
```

Environment variables:

```bash
# DeepSeek, OpenAI-compatible chat completions
set DEEPSEEK_API_KEY=...
set CADFLOW_DEEPSEEK_MODEL=deepseek-chat

# OpenAI API model testing through Responses API
set OPENAI_API_KEY=...
set CADFLOW_OPENAI_MODEL=gpt-5.1
```

The provider clients use standard-library HTTP calls and are opt-in only. API
keys are read at request time and are not written into artifacts, runtime
activity, provider identity, or JSON-contract context.

The OpenAI path uses the OpenAI API and consumes the API project's quota or
billing. It does not use ChatGPT or Codex product quotas. To test a Codex-family
model, set `CADFLOW_OPENAI_MODEL` or the Web Console model field to a model name
available to that API project.

In the Web Workflow Console, the Provider panel can switch between `local/mock`,
`deepseek`, and `openai api` for the current local server process. The page only
accepts non-secret provider settings; API keys must remain in environment
variables before the server starts. Use the Provider panel's `Test` button to
run a minimal JSON-contract connectivity check before running workflow stages;
the check does not write workflow artifacts.

### Windows / CadQuery environment note

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

## 可运行入口

### 1. One-command workflow demo

```bash
python examples/workflow/mounting_plate_demo.py
```

### 2. Python workflow API

```python
from ai_native_cad import run_workflow

result = run_workflow(
    "Generate an 80x40x5 mounting plate with four M4 holes.",
    output_dir="runs/mounting_plate_demo",
)
print(result.output_dir)
```

默认输出：

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

### 3. 现有单零件 demo

```bash
python examples/parts/mounting_plate/model.py
python examples/parts/circular_button/model.py
python examples/assemblies/pet_button/parts/pet_button_base/model.py
python examples/assemblies/pet_button/parts/pet_button_switch_plate/model.py
python examples/assemblies/pet_button/parts/pet_button_tactile_switch/model.py
python examples/assemblies/pet_button/parts/pet_button_cap/model.py
python examples/assemblies/enclosure/parts/enclosure_lid/model.py
python examples/assemblies/enclosure/parts/spacer/model.py
python examples/assemblies/enclosure/parts/wall_bracket/model.py
```

示例脚本默认把生成物写在自己的 `model.py` 同目录，例如 `examples/parts/mounting_plate/model.step`。用户 workflow 应显式传入 `output_dir`；未传时才使用 `runs/<instance_name>/` 作为 fallback。

### 4. 程序化旧入口

```python
from ai_native_cad.generator import get_part_spec
from ai_native_cad.runner import run_part

spec = get_part_spec("mounting_plate")
result = run_part("mounting_plate", spec)
```

### 5. CAD Agent Loop pipeline

```python
from ai_native_cad.pipeline import run_ir_pipeline

result = run_ir_pipeline({
    "part_type": "mounting_plate",
    "part_name": "mounting_plate",
    "unit": "mm",
    "dimensions": {"length": 80, "width": 40, "thickness": 5},
    "features": {"holes": {"diameter": 5, "positions": "corner_4"}, "chamfer": 1},
    "outputs": ["step", "stl"],
})
```

Default output contract:

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

`agent_trace.json` records every generation attempt, candidate scores, failure
analysis, IR repair changes, measured validation targets, inspection summaries,
and the final selected candidate. `model.step` is the primary CAD artifact and
`model.stl` is a derived mesh output. `preview.png` is a visible placeholder
image until a lightweight real geometry renderer is added; use the Web STL
viewer for live geometry inspection. The IR remains the source of truth; the
system does not bypass IR by generating CAD code directly from text.

Prompt/text input should use the structured pipeline:

```python
from ai_native_cad.pipeline import run_text_pipeline

result = run_text_pipeline(
    "Generate an 80x40x5 mounting plate with four M4 holes.",
    output_dir="outputs/prompt_pipeline/mounting_plate_by_holes",
)
```

This writes `requirement.json`, `planning_artifact.json`, `input_ir.json`,
`report.json` / `report.md`, and `agent_trace.json` on successful runs.
`input_ir.json` is produced only after the Planning -> CAD IR gate proceeds, and
its `source.planning_handoff` records the consumed structured planning fields.

Tracked IR examples use local output folders instead:

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

## Agent runtime model

CadFlow separates agent reasoning from deterministic CAD execution:

- The deterministic parser exists as fallback and test mode. It is useful for CI, demos, and offline development.
- The future `LLMApiAgentAdapter` is the intended user-facing natural-language mode. It should convert user prompts into validated requirement and planning JSON.
- CLI agents are for repository development, not default CAD generation runtime. They may help modify CadFlow source, add templates, write tests, or refactor code, but they should not be the ordinary end-user model generation path.

Agent output must become validated structured contracts before the CAD Agent Loop executes. The execution layer should not rely on unconstrained free-form LLM behavior or direct arbitrary CadQuery code produced from user text.

The AgentAdapter direction includes iterative CAD operations: interpreting
ambiguous first prompts, proposing assumptions, asking focused questions,
parsing revision requests, creating revision plans, proposing constrained
patches, and explaining old/new comparisons. CadFlow still owns validation,
normalization, CAD execution, and artifact contracts.

## Web Workflow Console

CadFlow includes a lightweight Web Workflow Console for staged workflow
artifact inspection, operation, and review. It is meant to help users inspect
file-backed workflow runs, review reports and traces, and operate approval
points around structured artifacts. It is not a full browser CAD editor.

The backend and first static console now exist under
`ai_native_cad.workflow_console` and `web-viewer/`:

- run the existing workflow from natural-language prompts
- list artifact-backed runs under `outputs/` and `runs/`, including nested
  manual smoke output runs
- derive run status from `report.json` and `agent_trace.json`
- show compact report/trace summaries for review decisions and attempt status
- read requirement, planning, IR, reviewed-part, report, and trace artifacts
- summarize reviewed-part assembly plans, candidate part statuses, lineage, child
  runs, and `part_result_review.json` checks
- run explicit one-stage reviewed-part actions when upstream artifacts are present:
  part request, part review, reviewed handoff, reviewed single-part create, and
  part result review
- identify STEP-first outputs and derived preview/download files
- run local Review and Outputs check stages from existing artifacts
- support provider-backed workflow modes where implemented
- show path-free stage history in the workflow timeline
- show path-free gate decision history in the workflow timeline
- edit only `requirement.json`, `planning_artifact.json`, and `input_ir.json`
- record approve/reject/return/override gate decisions in `logs/runtime.json`
- apply structured Requirement clarification answers into `requirement_v2.json`

Future Web Console stages should add iterative workflow support: select a
previous run, submit a revision prompt, display the revision plan and patch diff,
compare old/new outputs, show lineage, and download parent/child artifacts. It
is also the intended future review surface for reviewed-part and staged approval
workflows such as the Reviewed Part Single-Part E2E MVP.

For the Reviewed Part Single-Part E2E MVP, the console can inspect and operate
the existing artifact chain from `assembly_plan.json` through
`part_result_review.json`, including candidate parts, reference-only parts, child
run summaries, and STEP/STL download links when present. Each backend action is
one stage only; there is no single "run everything" reviewed-part action.
The reviewed single-part create action now enters CAD through
`AgentAdapter.create_part_ir(...)`: `reviewed_part_handoff.json` is converted to
an agent-generated CAD IR draft, validated by `validate_input_ir_draft(...)` and
`validate_ir(...)`, and only then passed to `run_ir_pipeline(...)`. If the IR is
unsupported, the workflow blocks at `cad_ir_validation`; it must not fall back
to `mounting_plate` or fabricate a complete assembly.

Boundaries are explicit: the Web Workflow Console does not add full assembly
generation, automatic all-part generation, assembly constraint solving, STEP
assembly export, geometric fit validation, a new CAD backend, or browser-native
CAD editing. The current reviewed-part E2E milestone remains validated by
CLI/manual smoke tests.

Architecture decision for this slice:

```text
Safe action backend remains authoritative.
NiceGUI is an optional local UI shell.
```

The stdlib HTML console remains available as the fallback/debug view. It exposes
a FastAPI-style read/action shape over the existing safe route contract:

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
POST /api/actions/workflow-review
POST /api/actions/rework
```

An experimental-but-supported NiceGUI console is also available for local use.
It is paged into Runs, Requirement Review, Assembly Plan, Part Workflow, and
Artifacts so reviewed-part work is less dense than the single-page HTML console.
The Runs page uses bounded run listing by default and lazy-loads full summaries,
artifacts, and review panels only for the selected run. This keeps large local
`outputs/` trees usable before loop queues or overnight execution are added.
NiceGUI does not bypass `WorkflowConsoleActions`, does not add CAD capability,
and does not provide batch generation, assembly generation, provider-generated
CAD/code, or free-form chat.

The first user-agent negotiation surface is the Stage Review / Rework Artifact
MVP. From the NiceGUI Requirement Review and Assembly Plan pages, a user can save
a structured `stage_review.json` with an explicit stage, review status
(`approved`, `needs_revision`, or `blocked`), optional rework target, notes, and
requested changes.

The Rework Execution MVP is explicit and user-triggered only. `Run Rework`
reads the saved `stage_review.json`, validates that it is `needs_revision`,
and writes a sanitized `rework_decision.json`. The only executable target in
this pass is `workflow_review`, which creates a child rework run and writes a
refreshed deterministic `workflow_review.json` / `workflow_review.md` there
with parent lineage preserved. `assembly_plan` and `part_request` are recorded
as blocked unsupported targets until safe deterministic rework paths exist. The
original run's CAD outputs are not overwritten, and this does not enqueue jobs,
start an autonomous loop, call providers, or generate batches/assemblies.

NiceGUI also includes a Human-readable Workflow Review / Agent Report MVP. The
explicit Create / Refresh Workflow Review action writes deterministic local
`workflow_review.json` and `workflow_review.md` artifacts from existing
allowlisted run summaries. The report shows overall status, readiness score,
confidence bands, risk level, summary bullets, risks, and recommended next
actions. These readiness/confidence/risk values are local heuristics, not LLM
self-certification, and the action does not call a provider, rerun CAD, or add
new CAD capability.

Artifact display is intentionally tiered. Human-facing artifacts such as
`workflow_review.md`, `workflow_review.json`, `stage_review.json`,
`rework_decision.json`, `report.md`, assembly-plan summaries, part-result
summaries, and STEP/STL availability are
shown by default. Review/debug artifacts such as `requirement.json`,
`design_brief.json`, handoff JSON, lineage, and sanitized trace summaries are
collapsed behind "Show debug artifacts". Internal/schema-heavy artifacts such as
`input_ir.json`, planning internals, revision internals, and runtime logs remain
hidden unless "Show internal artifacts" is explicitly enabled.

Run the local console with the stdlib-only bridge:

```bash
PYTHONPATH=src python -m ai_native_cad.workflow_console.server
```

Windows PowerShell:

```powershell
.\scripts\start_workflow_console.ps1
```

Optional host/port and browser launch:

```powershell
.\scripts\start_workflow_console.ps1 -Port 8770 -Open
```

Then open:

```text
http://127.0.0.1:8765/workflow-console.html
```

Run the NiceGUI console after installing the optional web extra:

```bash
pip install -e ".[web]"
PYTHONPATH=src python -m ai_native_cad.workflow_console.nicegui_app
```

Windows PowerShell:

```powershell
.\scripts\start_nicegui_console.ps1
```

Then open:

```text
http://127.0.0.1:8780/
```

Both local consoles expose only the existing route/action contract and
whitelisted downloadable files. They do not add FastAPI, a database, login,
cloud deployment, API keys, arbitrary filesystem browsing, provider raw payloads,
or arbitrary shell command endpoints.

It is not a browser CAD editor, not a new CAD backend, and not a direct arbitrary code execution surface. Artifacts remain file-based and traceable so CLI, Python API, tests, and the future Web Console all inspect the same run contract.

### 6. FreeCAD/装配辅助

FreeCAD handoff、TechDraw 和装配脚本仍在 `scripts/` 中，属于工程承接层，不是主 workflow 的强依赖。当前 assembly 是初版 workflow scaffold：记录装配意图、生成 backend-neutral config、执行基础放置和包围盒验证，并输出 review/report；它不是成熟工业装配求解器。

## 当前 check_level

- `L0 Playground`：当前真正支持。检查模型是否生成、能否导出、基础验证是否通过。
- `L1 Maker`：当前输出报告框架，后续补最小壁厚、悬垂、STL 可打印性。
- `L2 Engineering`：预留。
- `L3 Industrial`：预留。
- `L4 Safety Critical`：预留，不自动放行安全关键件。

## 项目结构

```text
CadFlow/
  README.md
  pyproject.toml
  docs/
    PRD_new.md
    FINAL-PRD.md
    architecture/
      overview.md
      agent-adapter.md
      web-workflow-console.md
      workflow-contract.md
      workflow-decisions.md
      revision-workflow.md
      model-intake.md
    product/
      positioning.md
      roadmap.md
    architecture.md
    usage.md
    philosophy.md
    project/
  examples/
    parts/
      mounting_plate/
      circular_button/
    assemblies/
      pet_button/
        parts/
          pet_button_base/
          pet_button_cap/
          pet_button_switch_plate/
          pet_button_tactile_switch/
        assembly_plan.json
        assembly_plan.md
        assembly.json
        constraint_assembly.json
      enclosure/
        parts/
          enclosure_base/
          enclosure_lid/
          spacer/
          wall_bracket/
        assembly.json
        constraint_assembly.json
        README.md
  knowledge/
  policies/
  skills/
    requirement/
    planning/
    part_modeling/
    assembly/
    review/
  scripts/
  src/ai_native_cad/
    agents/
      base.py
      deterministic.py
    requirements.py
    workflow.py
    backends/
      base.py
      cadquery_backend.py
    generator.py
    runner.py
    exporter.py
    validator.py
    report.py
  tests/
  runs/
```

## 设计边界

当前阶段不做完整工业 CAD 替代、复杂自由曲面、成熟几何装配约束求解、自动任意 CAD 配合推断、正式工程图自动标注、完整 GD&T、FEA、工业级 DFM/DFA、运动仿真或安全关键件自动设计放行。CadQuery 是当前默认后端，FreeCAD 用作工程承接平台，未来可并行接入其他 CAD backend。

## Skill 结构

当前已开始把 workflow 规则拆到 `skills/`：

- `skills/requirement/`：需求澄清、产品意图、早期拆解、等级字段策略和缺失信息回问。
- `skills/planning/`：设计分析、workflow routing、基准/接口、风险和确认 gate。
- `skills/part_modeling/`：模板选择、参数化、单零件生成闭环和零件级检查。
- `skills/assembly/`：装配 plan、确认 gate、轻量放置/约束意图、间隙记录和基础验证意图。
- `skills/review/`：按 check_level 审查。

输出和导出路径是共享 contract，见 `policies/output_contract.md`，不再作为单独 skill。

更多说明见：

- `docs/PRD_new.md`
- `docs/product/positioning.md`
- `docs/architecture/overview.md`
- `docs/architecture/agent-adapter.md`
- `docs/architecture/web-workflow-console.md`
- `docs/architecture/workflow-contract.md`
- `docs/architecture/workflow-decisions.md`
- `docs/architecture/revision-workflow.md`
- `docs/architecture/model-intake.md`
- `docs/product/roadmap.md`
- `docs/architecture.md`
- `docs/usage.md`
- `docs/philosophy.md`
- `docs/project/roadmap.md`
