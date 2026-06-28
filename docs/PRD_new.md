# PRD: Workflow-first Natural Language Parametric CAD

## 1. 产品定位

本项目是一个开源的 Workflow-first 自然语言参数化 CAD 建模工具。用户通过自然语言描述机械零件或简单结构，系统将需求转化为结构化设计说明、建模计划、参数化 CAD 代码、审查报告和可打开的模型导出文件。

项目不是单纯的 Prompt to CAD，也不是 Prompt to STL，更不是宏大的 AI Engineering OS。当前阶段聚焦一个可运行、可追踪、可扩展后端的自然语言 CAD MVP。

## 2. 核心 Workflow

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

每个阶段都必须有明确输入、输出和日志。当前标准输出目录为：

```text
project/
  input.md
  requirement.json
  plan.md
  part_spec.json
  model.py
  review.md
  exports/
    model.step
    model.stl
  logs/
    run.log
```

## 3. 当前版本目标

V0/V1 聚焦自然语言参数化建模：

- 保留现有 CadQuery MVP。
- 新增 workflow 层，沉淀 traceable outputs。
- 抽象 CAD Backend，不让上层 workflow 绑定具体 CAD 工具。
- 至少提供一个 `mounting_plate` 示例并保证 demo 可运行。
- 建立 `knowledge/` 与 `policies/` 目录，但不过度实现。

## 4. 模块职责

### Requirement

负责将自然语言转化为结构化需求，并进行早期产品意图分析：单零件/装配判断、候选制造件、参考组件、关键接口、缺失信息和用户回问。当前实现可以保守地识别内置示例，并支持显式 overrides。

### Design Planner

负责生成 `plan.md`，完成设计分析、workflow routing、功能基准、接口关系、模板候选、风险和确认 gate。Planning 不做用户需求澄清，也不写具体 CAD backend 代码。

### Part Modeling

负责模板选择、参数化、单零件生成闭环、几何检查和零件级意图一致性。通过 CAD Backend 生成模型。当前默认 backend 是 CadQuery。

### Assembly

负责装配 plan、确认 gate、零件关系、contacts、clearances、constraints 和 backend-neutral assembly config。

### Reviewer

按 `check_level` 输出 `review.md`。当前支持 L0，L1 输出 maker 检查框架。

### Output / Export Utility

负责把 backend-native 模型导出到 `exports/`，当前支持 STEP/STL。输出路径和导出规则属于 `policies/output_contract.md`，不是独立设计 skill。

### CAD Backend

后端抽象应允许未来接入 CadQuery、build123d、FreeCAD API、JSCAD/replicad 等。

## 5. Check Levels

### L0 Playground

当前真正支持：

- 模型是否生成。
- STEP/STL 是否导出。
- 基础几何验证是否通过。
- 主要尺寸和文件路径是否记录。

### L1 Maker

当前只输出报告框架，后续补：

- 最小壁厚。
- 悬垂和支撑风险。
- STL 可打印性。
- 常见 3D 打印约束。

### L2 Engineering

预留：装配间隙、材料、制造方式、公差和基础工程约束。

### L3 Industrial

预留：DFM/DFA、BOM、工艺路线、粗糙度、GD&T、设计评审记录。

### L4 Safety Critical

预留：FMEA、可追溯性、独立 Review、验证记录和标准符合性。当前不得自动放行安全关键件。

## 6. 架构原则

- **Workflow First**：先有流程和记录，再有几何。
- **Backend Agnostic**：CAD 后端可替换。
- **Engineering over Geometry**：工程意图和检查优先于形状表演。
- **Traceable by Default**：默认输出全链路记录。
- **Knowledge Ready**：预留知识库结构。
- **Policy Ready**：预留策略文件和校核等级。

## 7. 非目标

当前不追求：

- 完整工业 CAD 替代。
- 复杂自由曲面建模。
- 完整装配设计自动化。
- 正式工程图自动标注。
- 完整 GD&T。
- FEA。
- 工业级 DFM。
- 安全关键件自动设计和放行。
- 多用户协同平台或 AI Engineering OS。

## 8. MVP 验收标准

- `examples/parts/mounting_plate/model.py` 可运行。
- `examples/parts/circular_button/model.py` 可运行，并保留开关触点/线束出口。
- workflow 可输出 `input.md`、`requirement.json`、`plan.md`、`model.py`、`review.md`、`exports/`、`logs/`。
- 至少 STEP/STL 可导出。
- 现有示例和测试不被破坏。
- 文档、PRD、架构、roadmap 和 philosophy 指向同一产品方向。
