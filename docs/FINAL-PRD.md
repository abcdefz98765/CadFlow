# FINAL PRD: Workflow-first Natural Language Parametric CAD

## Product Direction

CadFlow 是 IR-driven、workflow-first 的自然语言参数化 CAD 建模工具。用户用自然语言或结构化 JSON 描述机械零件，系统先生成 CAD IR，再生成确定性的 CadQuery 代码、STEP/STL、验证报告和可打开的导出文件。

本项目不做宏大的 AI Engineering OS。当前阶段聚焦自然语言建模 MVP，并为未来工程校核、知识库、策略文件和多 CAD 后端预留架构。

## Core Workflow

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

单零件生成主路径：

```text
text/input_ir.json -> CAD IR -> CadQuery generator -> model.py -> STEP/STL -> validation -> report
```

## Required Outputs

IR-first pipeline 每次生成产出：

```text
outputs/<part_name>/
  input_ir.json
  model.py
  model.step
  model.stl
  report.json
  report.md
  preview.png
  logs/runtime.json
```

兼容 workflow run 仍产出：

```text
input.md
requirement.json
plan.md
part_spec.json
model.py
review.md
exports/
logs/
```

`exports/` 当前包含 STEP/STL。`logs/` 当前包含结构化 JSON 日志：`run.json` 和 `generation.json`。

## Modules

- Requirement：自然语言到结构化需求、产品意图、早期拆解和缺失信息回问。
- CAD IR：稳定的 JSON 中间表示，承接自然语言解析和后端代码生成。
- Design Planner：需求到设计分析、workflow routing、接口/基准、风险和确认 gate。
- Part Modeling：模板选择、参数化、IR 到 CadQuery 代码生成、单零件生成闭环和 backend-neutral CAD 调用。
- Assembly：装配 plan、contacts、clearances、轻量 placement/constraint intent 和 backend-neutral assembly config。当前是初版 planning/config/validation scaffold，不是成熟工业装配求解器。
- Reviewer：按 check_level 审查生成结果。
- Output/Export Utility：导出 STEP/STL 等文件，遵循 `policies/output_contract.md`。
- CAD Backend：抽象 CadQuery/build123d/FreeCAD API/JSCAD 等后端。

## Check Levels

- `L0 Playground`：当前支持。
- `L1 Maker`：当前输出报告框架，不是完整 printability validation。
- `L2 Engineering`：预留，不代表工程放行。
- `L3 Industrial`：预留，不代表工业 DFM/DFA 或 production release。
- `L4 Safety Critical`：预留，不能自动放行。

## MVP Acceptance

- IR pipeline 的 mounting_plate、spacer、simple_bracket 示例可运行。
- `python examples/workflow/mounting_plate_demo.py` 可一键运行 workflow demo。
- IR pipeline 和兼容 workflow 输出目录结构稳定。
- 现有自然语言建模 demo 继续可跑。
- workflow 层不直接绑定具体 CAD 工具。
- 文档清楚说明项目方向、边界和架构。
- `knowledge/`、`policies/` 已建立但不过度实现。
