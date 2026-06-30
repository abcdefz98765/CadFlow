# PRD: Workflow-first Natural Language Parametric CAD

## 1. 产品定位

CadFlow 是一个开源的 IR-driven、workflow-first 自然语言参数化 CAD agent。用户通过自然语言或结构化输入描述机械零件，系统先生成 JSON CAD IR，再进入 CAD Agent Loop：生成候选实现、执行、验证、分析失败、修复 IR、重试，并最终输出 STEP-first CAD artifact、派生 STL、验证报告和 agent trace。

项目不是单纯的 Prompt to CAD，也不是 Prompt to STL，更不是宏大的 AI Engineering OS。当前阶段聚焦一个可运行、可追踪、可扩展后端、可自修复的 IR-first engineering CAD MVP。

## 2. 核心 Workflow

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

单零件生成的主路径为：

```text
text/input_ir.json
  -> CAD IR
  -> validate IR
  -> CAD Agent Loop
       -> candidate CadQuery generation
       -> execution
       -> STEP-first inspection + geometry validation
       -> failure analysis
       -> IR repair
       -> retry, max 3
  -> model.py + STEP primary artifact + STL derived artifact
  -> report + agent_trace
```

IR-first pipeline 的标准输出目录为：

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

旧 workflow 入口仍保留兼容，输出目录为：

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
    run.json
    generation.json
```

## 3. 当前版本目标

V0/V1 聚焦自然语言参数化建模和可追踪 CAD agent loop：

- 保留现有 CadQuery MVP。
- 新增 CAD IR 层，所有新生成路径先生成 IR，再生成 CadQuery 代码。
- 新增 CAD Agent Loop，沉淀 traceable attempts、failure analysis、IR repair 和 candidate scoring。
- 抽象 CAD Backend，不让上层 workflow 绑定具体 CAD 工具。
- 至少提供 `mounting_plate`、`spacer`、`simple_bracket` 三个 IR pipeline 示例并保证可运行。
- 建立 `knowledge/` 与 `policies/` 目录，但不过度实现。

## 4. 模块职责

### Requirement

负责将自然语言转化为结构化需求，并进行早期产品意图分析：单零件/装配判断、候选制造件、参考组件、关键接口、缺失信息和用户回问。当前实现可以保守地识别内置示例，并支持显式 overrides。

### Design Planner

负责生成 `plan.md`，完成设计分析、workflow routing、功能基准、接口关系、模板候选、风险和确认 gate。Planning 不做用户需求澄清，也不写具体 CAD backend 代码。

### Part Modeling

负责模板选择、参数化、单零件生成闭环、几何检查和零件级意图一致性。新主路径通过 CAD IR 驱动 CAD Agent Loop；旧路径仍可通过 CAD Backend 兼容现有 examples。当前默认 backend 是 CadQuery。

### CAD IR

负责表达后端无关的零件意图，包括 `part_type`、`unit`、`dimensions`、`features`、`outputs` 和 `check_level`。IR 必须可 JSON 序列化、可验证、可作为重试和再生成的稳定输入。新生成流程不得把自然语言直接作为主要代码生成输入。

### CAD Agent Loop

负责从 CAD IR 生成候选 CadQuery 代码、执行、验证、分析失败、修复 IR 并重试。最大尝试次数为 3。失败必须转化为结构化 root cause 和 suggested IR fix。IR repair 不改变 `part_type`，不删除必需 feature，除非失败分析明确要求，否则不简化用户意图。

### CAD Brief

后续用于承接复杂自然语言、参考图、技术图纸或多源输入。CAD Brief 是面向审查的建模意图记录，位于 Requirement 和 CAD IR 之间；它记录单位、尺寸、feature、坐标约定、假设、冲突和验证目标。CAD Brief 不替代 CAD IR，最终生成仍以 IR 为 source of truth。

### Geometry Inspector

从 STEP/model 输出路径记录可测事实。当前已覆盖 STEP/STL artifact facts、solid count、bbox、volume，并为 holes/chamfers/fillets 保留 inspection scaffold；后续继续推进孔数量、孔径、孔距、槽、倒角、关键尺寸和 repair diff 的真实拓扑验证。

### Assembly

负责装配 plan、确认 gate、零件关系、contacts、clearances、轻量 placement/constraint intent 和 backend-neutral assembly config。当前 assembly 是初版 planning/config/validation workflow scaffold，不是成熟几何约束求解器或工业装配系统。

### Reviewer

按 `check_level` 输出 `review.md`。当前支持 L0，L1 输出 maker 检查框架。

### Output / Export Utility

负责把模型导出为 STEP/STL，当前 CAD Agent Loop 直接写入 `outputs/<part_name>/model.step` 和 `model.stl`；旧 workflow 仍写入 `exports/`。`model.step` 是主 CAD artifact，`model.stl` 是派生 mesh exchange。输出路径和导出规则属于 `policies/output_contract.md`，不是独立设计 skill。

### CAD Backend

后端抽象应允许未来接入 CadQuery、build123d、FreeCAD API、JSCAD/replicad 等。

## 5. Check Levels

### L0 Playground

当前真正支持：

- 模型是否生成。
- STEP/STL 是否导出。
- 基础几何验证是否通过。
- CadQuery execution 是否成功。
- shape validity / watertight 检查是否通过或记录为不可用。
- 主要尺寸和文件路径是否记录。

### L1 Maker

当前只输出报告框架，后续补：

- 最小壁厚。
- 悬垂和支撑风险。
- STL 可打印性。
- 常见 3D 打印约束。

### L2 Engineering

预留：装配间隙、材料、制造方式、公差和基础工程约束。预留不代表当前工程放行。

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
- 成熟几何装配约束求解、任意 CAD mating 自动推断、完整 tolerance stack-up、工业 DFA 和运动仿真。
- 正式工程图自动标注。
- 完整 GD&T。
- FEA。
- 工业级 DFM。
- 安全关键件自动设计和放行。
- 多用户协同平台或 AI Engineering OS。

## 8. MVP 验收标准

- IR pipeline 可从 `input_ir.json` 生成模型。
- `examples/ir_pipeline/generate_examples.py` 可生成 mounting_plate、spacer、simple_bracket。
- `examples/parts/circular_button/model.py` 可运行，并保留开关触点/线束出口。
- workflow 可输出 `input.md`、`requirement.json`、`plan.md`、`model.py`、`review.md`、`exports/`、`logs/`。
- CAD Agent Loop 可输出 `input_ir.json`、`model.py`、`model.step`、`model.stl`、`report.json`、`report.md`、`preview.png`、`agent_trace.json`、`logs/runtime.json`。
- CAD Agent Loop 可输出 `agent_trace.json`，并记录 attempt、measured validation targets、inspection summary、failure analysis、IR repair 和 final selected candidate。
- 至少一个失败几何案例可通过 IR repair 自动恢复。
- `python examples/workflow/mounting_plate_demo.py` 可一键运行 workflow demo。
- 至少 STEP/STL 可导出。
- 现有示例和测试不被破坏。
- 文档、PRD、架构、roadmap 和 philosophy 指向同一产品方向。
