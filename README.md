# llm2cad

Workflow-first 的自然语言参数化 CAD 建模工具。

本项目不是宏大的 AI Engineering OS，也不是一次性 Prompt to STL。短期目标是保留一个能跑的自然语言建模 MVP，同时把工程结构调整为可追踪、可替换后端、可逐步引入知识和策略的 CAD workflow。

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

零件生成阶段内部是一个小闭环：

```text
part_spec -> preflight -> generate -> geometry check -> intent match -> export/report
```

装配阶段也按闭环推进：

```text
requirement + part reports -> assembly_plan -> confirmation gate -> assembly configs -> validation -> assembly_review
```

## 当前定位

- **Workflow First**：每次任务都保留输入、结构化需求、建模计划、模型代码、审查报告、导出文件和日志。
- **Backend Agnostic**：workflow 层不直接绑定 CadQuery、FreeCAD 或未来 build123d/JSCAD 后端。
- **Engineering over Geometry**：先表达工程意图、关键尺寸、约束和检查，再生成几何。
- **Traceable by Default**：默认输出完整项目记录，方便复核和迭代。
- **Skill Oriented**：把 requirement、planning、part modeling、assembly、review 收束为少量职责清晰的 skill。
- **Knowledge Ready / Policy Ready**：`skills/<step>/knowledge/` 放步骤内知识，顶层 `knowledge/` 只做跨 skill 索引，`policies/` 放全局策略和等级定义。

## 安装

```bash
pip install -e .
```

开发与测试：

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

## 可运行入口

### 1. Workflow 入口

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
    run.log
    generation.json
```

### 2. 现有单零件 demo

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

### 3. 程序化旧入口

```python
from ai_native_cad.generator import get_part_spec
from ai_native_cad.runner import run_part

spec = get_part_spec("mounting_plate")
result = run_part("mounting_plate", spec)
```

### 4. FreeCAD/装配辅助

FreeCAD handoff、TechDraw 和装配脚本仍在 `scripts/` 中，属于工程承接层，不是主 workflow 的强依赖。

## 当前 check_level

- `L0 Playground`：当前真正支持。检查模型是否生成、能否导出、基础验证是否通过。
- `L1 Maker`：当前输出报告框架，后续补最小壁厚、悬垂、STL 可打印性。
- `L2 Engineering`：预留。
- `L3 Industrial`：预留。
- `L4 Safety Critical`：预留，不自动放行安全关键件。

## 项目结构

```text
llm2cad/
  README.md
  pyproject.toml
  docs/
    PRD_new.md
    FINAL-PRD.md
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

当前阶段不做完整工业 CAD 替代、复杂自由曲面、正式工程图自动标注、完整 GD&T、FEA、工业级 DFM 或安全关键件自动设计放行。CadQuery 是当前默认后端，FreeCAD 用作工程承接平台，未来可并行接入其他 CAD backend。

## Skill 结构

当前已开始把 workflow 规则拆到 `skills/`：

- `skills/requirement/`：需求澄清、产品意图、早期拆解、等级字段策略和缺失信息回问。
- `skills/planning/`：设计分析、workflow routing、基准/接口、风险和确认 gate。
- `skills/part_modeling/`：模板选择、参数化、单零件生成闭环和零件级检查。
- `skills/assembly/`：装配 plan、确认 gate、约束、间隙和验证意图。
- `skills/review/`：按 check_level 审查。

输出和导出路径是共享 contract，见 `policies/output_contract.md`，不再作为单独 skill。

更多说明见：

- `docs/PRD_new.md`
- `docs/architecture.md`
- `docs/usage.md`
- `docs/philosophy.md`
- `docs/project/roadmap.md`
