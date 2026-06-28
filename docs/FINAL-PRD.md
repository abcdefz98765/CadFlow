# FINAL PRD: Workflow-first Natural Language Parametric CAD

## Product Direction

本项目是 Workflow-first 的自然语言参数化 CAD 建模工具。用户用自然语言描述机械零件或简单结构，系统生成结构化需求、建模计划、参数化 CAD 代码、审查报告和可打开的导出文件。

本项目不做宏大的 AI Engineering OS。当前阶段聚焦自然语言建模 MVP，并为未来工程校核、知识库、策略文件和多 CAD 后端预留架构。

## Core Workflow

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

## Required Outputs

每次 workflow run 产出：

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

`exports/` 当前包含 STEP/STL。`logs/` 当前包含 `run.log`。

## Modules

- Requirement：自然语言到结构化需求、产品意图、早期拆解和缺失信息回问。
- Design Planner：需求到设计分析、workflow routing、接口/基准、风险和确认 gate。
- Part Modeling：模板选择、参数化、单零件生成闭环和 backend-neutral CAD 调用。
- Assembly：装配 plan、contacts、clearances、constraints 和 backend-neutral assembly config。
- Reviewer：按 check_level 审查生成结果。
- Output/Export Utility：导出 STEP/STL 等文件，遵循 `policies/output_contract.md`。
- CAD Backend：抽象 CadQuery/build123d/FreeCAD API/JSCAD 等后端。

## Check Levels

- `L0 Playground`：当前支持。
- `L1 Maker`：当前输出报告框架。
- `L2 Engineering`：预留。
- `L3 Industrial`：预留。
- `L4 Safety Critical`：预留，不能自动放行。

## MVP Acceptance

- 至少一个 mounting_plate 示例可运行。
- workflow 输出目录结构稳定。
- 现有自然语言建模 demo 继续可跑。
- workflow 层不直接绑定具体 CAD 工具。
- 文档清楚说明项目方向、边界和架构。
- `knowledge/`、`policies/` 已建立但不过度实现。
