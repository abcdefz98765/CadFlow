# FINAL PRD: Workflow-first Natural Language Parametric CAD

## Product Direction

CadFlow 是 IR-driven、workflow-first 的自然语言参数化 CAD agent。用户用自然语言或结构化 JSON 描述机械零件，系统先生成 CAD IR，再进入 CAD Agent Loop：候选代码生成、执行、验证、失败分析、IR 修复、重试，并最终输出 STEP-first CAD artifact、派生 STL、验证报告和可追踪 trace。

本项目不做宏大的 AI Engineering OS。当前阶段聚焦自然语言建模 MVP 和自修复 CAD agent loop，并为未来 STEP inspection、工程校核、知识库、策略文件和多 CAD 后端预留架构。

## Core Workflow

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

单零件生成主路径：

```text
text/input_ir.json
  -> CAD IR
  -> CAD Agent Loop
       -> candidate generation
       -> execution
       -> validation
       -> failure analysis
       -> IR repair
       -> retry, max 3
  -> STEP primary artifact + STL derived artifact
  -> report + agent_trace
```

## Required Outputs

CAD Agent Loop 每次生成产出：

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
- CAD Agent Loop：从 IR 生成候选实现、执行、验证、失败分析、IR 修复、最多 3 次重试和候选选择。
- Part Modeling：模板选择、参数化、IR 到 CAD agent loop、单零件生成闭环和 backend-neutral CAD 调用。
- Geometry Inspector：后续从 STEP/model 中真实测量孔、槽、倒角、关键尺寸和 repair diff。
- CAD Brief：后续在复杂输入时记录建模意图、假设、坐标、验证目标，再落到 CAD IR。
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
- CAD Agent Loop 能记录失败、修复 IR、重试，并输出 `agent_trace.json`。
- 至少一个失败几何案例可以自动修复并生成有效 STEP/STL。
- 现有自然语言建模 demo 继续可跑。
- workflow 层不直接绑定具体 CAD 工具。
- 文档清楚说明项目方向、边界和架构。
- `knowledge/`、`policies/` 已建立但不过度实现。

## Near-term Roadmap

- v0.3.1：STEP-first output contract、真实 preview/snapshot、trace quality、benchmark scaffold。
- v0.4：Geometry Inspector，真实 feature-level validation 和 repair diff checks。
- v0.5：backend abstraction hardening，评估 build123d backend，但不替换当前 CadQuery 主线。

暂不扩展到 URDF/SDF、G-code、slicer/printer handoff、机器人工作流或多技能平台化。
