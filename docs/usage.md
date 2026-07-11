# Usage

## Recommended Workflow

自然语言 CAD 任务按下面的阶段推进：

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

用户只需要描述工程目标、关键尺寸、功能特征、制造倾向和优先级。系统负责把描述转成结构化需求、建模计划、参数化代码和审查报告。

Requirement 阶段负责澄清需求、识别候选零件/参考组件和缺失信息。Planning 阶段负责设计分析、workflow routing、接口/基准、风险和确认 gate。Part Modeling 再进入模板选择、参数化和单零件生成闭环。

当前推荐的新单零件 prompt 路径先经过结构化 handoff gates：

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

CAD Agent Loop 本身仍是 IR-first：

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

The Console presents workflow summaries and final STEP, STL, and preview
deliverables. Raw JSON, agent traces, runtime logs, and generated scripts stay
in the local run directory for developer inspection.

For the NiceGUI cockpit:

```powershell
.\scripts\start_nicegui_console.ps1
```

The console is a workflow cockpit, not just an artifact browser. The Workflow
page leads with a Workflow Graph for Requirement, Clarification, Planning,
Assembly Plan, reviewed-part handoff, CAD IR draft, part result review,
workflow review, and rework. Selecting a graph node opens that stage's detail:
human summary, current status, key decisions, user actions, important artifacts,
and collapsed Advanced / Debug sections. The full stage list, raw workflow
graph, raw diagnostics, and raw allowlisted artifacts are secondary surfaces.

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

当前只真正支持 `L0 Playground`。`L1 Maker` 会输出报告框架，提醒后续需要补最小壁厚、悬垂、支撑和 STL 可打印性检查。

`L2/L3/L4` 是架构预留，不代表当前可以自动完成工程放行。
