# Usage

## Recommended Workflow

自然语言 CAD 任务按下面的阶段推进：

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

用户只需要描述工程目标、关键尺寸、功能特征、制造倾向和优先级。系统负责把描述转成结构化需求、建模计划、参数化代码和审查报告。

Requirement 阶段负责澄清需求、识别候选零件/参考组件和缺失信息。Planning 阶段负责设计分析、workflow routing、接口/基准、风险和确认 gate。Part Modeling 再进入模板选择、参数化和单零件生成闭环。

## Run the Workflow

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
    run.log
    generation.json
```

## Run the Mounting Plate Demo

```bash
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
placement configs as approved assembly intent. The validator writes both
`assembly_validation.md` and `assembly_review.md`.

The assembly loop is:

```text
part reports -> assembly_plan -> high-risk confirmation gate -> assembly.json / constraint_assembly.json -> assembly_review.md
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

## Good User Input

推荐描述：

```text
生成一个 80x40x5 mm 的安装板，四角 M4 通孔，孔中心离边 8mm。
优先保证孔位和板厚准确，倒角可以简化。输出 STEP/STL，并写出假设。
```

Agent 应输出或保留：

- 原始输入：`input.md`
- 结构化需求：`requirement.json`
- 单零件规格：`part_spec.json`
- 建模计划：`plan.md`
- 参数化模型源码：`model.py`
- 审查报告：`review.md`
- 导出文件：`exports/`
- 运行日志：`logs/`

## Check Levels

当前只真正支持 `L0 Playground`。`L1 Maker` 会输出报告框架，提醒后续需要补最小壁厚、悬垂、支撑和 STL 可打印性检查。

`L2/L3/L4` 是架构预留，不代表当前可以自动完成工程放行。
