# Getting Started

CadFlow 现在以 workflow-first 自然语言参数化 CAD 为主线。

推荐先读：

1. `README.md`
2. `docs/usage.md`
3. `docs/architecture.md`
4. `docs/PRD_new.md`
5. `docs/philosophy.md`

## Install

```bash
pip install -e .
```

## Run the Workflow

One-command demo:

```bash
python examples/workflow/mounting_plate_demo.py
```

Python API:

```python
from ai_native_cad import run_workflow

result = run_workflow(
    "Generate an 80x40x5 mounting plate with four M4 clearance holes.",
    output_dir="runs/mounting_plate_demo",
)
print(result.status)
print(result.output_dir)
```

输出：

```text
runs/mounting_plate_demo/
  input.md
  requirement.json
  plan.md
  model.py
  review.md
  exports/
  logs/
    run.json
    generation.json
```

## Run the Demo

```bash
python examples/workflow/mounting_plate_demo.py
python examples/parts/mounting_plate/model.py
```

The demo writes generated CAD files next to its own `model.py`. For real user
projects, pass an explicit `output_dir` to `run_workflow`.

## User Input Pattern

描述用途、关键尺寸、功能特征、制造倾向和优先级即可。不要把 CadQuery 操作步骤推给用户。

示例：

```text
生成一个 80x40x5 mm 的安装板，四角 M4 通孔，孔中心离边 8mm。
优先保证孔位和板厚准确，倒角可以简化。输出 STEP/STL，并写出假设。
```
