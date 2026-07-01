# CadFlow

CadFlow is an early-stage workflow-first natural-language parametric CAD toolkit.

Python package: `ai_native_cad`

CadFlow is natural-language first for users, but structured-workflow first internally.
Users describe CAD intent in plain language. CadFlow converts that into auditable requirement, planning, CAD IR, generation, validation, repair, and report artifacts.

本项目不是宏大的 AI Engineering OS，也不是一次性 Prompt to STL。短期目标是保留一个能跑的自然语言建模 MVP，同时把工程结构调整为可追踪、可替换后端、可逐步引入知识和策略的 CAD workflow。

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
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

## 当前定位

- **Workflow First**：每次任务都保留输入、结构化需求、建模计划、模型代码、审查报告、导出文件和日志。
- **Backend Agnostic**：workflow 层不直接绑定 CadQuery、FreeCAD 或未来 build123d/JSCAD 后端。
- **Engineering over Geometry**：先表达工程意图、关键尺寸、约束和检查，再生成几何。
- **Traceable by Default**：默认输出完整项目记录，方便复核和迭代。
- **Skill Oriented**：把 requirement、planning、part modeling、assembly、review 收束为少量职责清晰的 skill。
- **Knowledge Ready / Policy Ready**：`skills/<step>/knowledge/` 放步骤内知识，顶层 `knowledge/` 只做跨 skill 索引，`policies/` 放全局策略和等级定义。

CadFlow is an AI-assisted natural-language CAD workflow system, a workflow-first CAD agent scaffold, and a STEP-first parametric CAD generation pipeline. It is not a browser CAD editor, mesh generation system, prompt-to-STL toy, production-ready CAD engineer replacement, full FreeCAD/SolidWorks replacement, or cloud SaaS platform at this stage.

## Current Limitations

- The natural-language parser is template-backed and deterministic in the MVP.
- Unknown or underspecified requests may fall back to built-in part templates.
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

## Web Workflow Console

The Web UI is a local workflow cockpit for running and visualizing CadFlow. The backend and first static console now exist under `ai_native_cad.workflow_console` and `web-viewer/`:

- run the existing workflow from natural-language prompts
- list artifact-backed runs under `outputs/` and `runs/`
- derive run status from `report.json` and `agent_trace.json`
- show compact report/trace summaries for review decisions and attempt status
- read requirement, planning, IR, report, and trace artifacts
- identify STEP-first outputs and derived preview/download files
- run local Review and Outputs check stages from existing artifacts
- show path-free stage history in the workflow timeline
- show path-free gate decision history in the workflow timeline
- edit only `requirement.json`, `planning_artifact.json`, and `input_ir.json`
- record approve/reject/return/override gate decisions in `logs/runtime.json`

Run the local console with the stdlib-only bridge:

```bash
PYTHONPATH=src python -m ai_native_cad.workflow_console.server
```

Windows PowerShell:

```powershell
$env:PYTHONPATH='src'; python -m ai_native_cad.workflow_console.server
```

Then open:

```text
http://127.0.0.1:8765/workflow-console.html
```

The bridge exposes only the existing route contract and whitelisted downloadable files. It does not add FastAPI, a database, login, cloud deployment, LLM API dependencies, API keys, or arbitrary shell command endpoints.

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
- `docs/product/roadmap.md`
- `docs/architecture.md`
- `docs/usage.md`
- `docs/philosophy.md`
- `docs/project/roadmap.md`
