# Software Architecture

项目架构以 workflow 为主线，而不是以某个 CAD 工具为中心。

```text
input.md
  ↓
Requirement Agent
  ↓
requirement.json
  ↓
Design Planner
  ↓
plan.md
  ↓
Part Generation Loop
  ↓
model.py / backend-native model
  ↓
Assembly Planning Loop
  ↓
Reviewer
  ↓
review.md
  ↓
Exporter
  ↓
exports/ + logs/
```

## Layers

## Example Layout

Examples are split by scope:

```text
examples/
  parts/
    mounting_plate/
    circular_button/
  assemblies/
    enclosure/
      parts/
        enclosure_base/
        enclosure_lid/
        spacer/
        wall_bracket/
      assembly.json
      assembly_plan.json
      assembly_plan.md
      constraint_assembly.json
      README.md
```

Standalone parts live under `examples/parts/`. Assembly-owned parts, assembly placement, and constraints live together under `examples/assemblies/<assembly>/`.

### Skill Layer

`skills/`

项目规则按 workflow step 归位：

- `requirement/`：需求模板、字段等级、缺失信息回问策略。
- `planning/`：设计分析、workflow routing、基准、接口、风险和确认 gate。
- `part_modeling/`：常用零件模板、参数化入口和单零件生成闭环。
- `assembly/`：装配规则、约束、间隙和验证意图。
- `review/`：按 check_level 审查。

`requirement/knowledge/product_decomposition.md` 负责早期产品拆解，因为判断“需要哪些零件/参考件”本质上属于需求澄清。`policies/` 保存跨 skill 的全局策略，例如 check level 和输出契约。`knowledge/` 保存跨 skill 索引，具体知识优先放到所属 skill 的 `knowledge/` 下。

### Workflow Layer

`src/ai_native_cad/workflow.py`

负责端到端编排，写出标准项目目录：

```text
input.md
requirement.json
part_spec.json
plan.md
model.py
review.md
exports/
logs/
```

用户 workflow 应显式传入 `output_dir`。未传时使用 `runs/<instance_name>/` 作为 fallback。示例脚本属于 examples 自测，默认生成在各自 `model.py` 同目录，不代表任意用户项目的输出位置。

`src/ai_native_cad/requirements.py` 提供第一版 `RequirementAgent`。当前实现仍是保守的确定性解析：识别内置示例，支持 overrides，并默认落到 `mounting_plate`。它会额外写入：

- `intent`
- `field_policy`
- `missing_information`
- `follow_up_questions`
- `requirement_status`
- `assumptions`

后续可以替换为 LLM parser 或多轮交互，但输出 contract 不变。

Requirement 层也负责早期产品意图分析：判断请求是单零件、装配还是未知；识别候选制造件、参考组件、用户可见功能、关键接口和会改变拓扑的缺失信息。它不生成几何，也不决定 backend 操作。

### Planning Layer

`plan.md` 不只是步骤列表。Design Planner 负责把需求包转成工程方案：

- workflow route：单零件、多个零件、装配 loop，或需要用户确认。
- design strategy：功能基准、接口、模板候选、建模顺序和检查目标。
- risk and gate：哪些假设可以 L0 继续，哪些会改变拓扑并需要回问。

Planning 不做用户需求澄清，不参数化具体零件模板，也不写 backend CAD 代码。

### Backend Layer

`src/ai_native_cad/backends/`

上层 workflow 只依赖 `CADBackend` contract：

- `build_model(requirement)`
- `export_model(artifact, output_dir, formats)`
- `validate_model(artifact, output_dir, requirement)`

当前实现是 `CadQueryBackend`，复用现有 `examples/<part>/model.py`、`exporter.py` 和 `validator.py`。未来 build123d、FreeCAD API、JSCAD/replicad 应作为并行 backend 接入。

### Part Generation Loop

零件生成不是单次 “spec to STEP”，而是局部闭环：

```text
part_spec.json
  ↓
preflight_design_intent
  ↓
backend build_model
  ↓
validate_generated_geometry
  ↓
validate_export_files
  ↓
validate_intent_match
  ↓
review.md + logs/generation.json
```

L0 默认软失败继续：只要 backend 能生成模型就继续导出，但 `review.md`
必须标出 preflight、geometry、export 和 intent match 的状态。无法独立验证
的 feature 不应伪装为通过，而是进入 `intent_match.unverified`。

### Assembly Planning Loop

装配不是直接从零件 STEP 跳到 FreeCAD。当前 contract 是：

```text
requirement.json + part_spec.json + part reports
  ↓
assembly_plan.json / assembly_plan.md
  ↓
confirmation gate
  ↓
assembly.json / constraint_assembly.json
  ↓
assembly_validation.json / assembly_review.md
```

`assembly_plan` 记录 manufactured parts、reference components、placement intent、required contacts、required clearances、allowed overlaps、serviceability notes 和 unresolved questions。确认 gate 采用“只在高风险暂停”：开关/传感器包络、线束出口、固定方式、可拆卸方式等会改变拓扑的信息缺失时暂停；普通 L0 可视化假设继续进入 warning。

`assembly.json` 和 `constraint_assembly.json` 是 backend-neutral 配置。FreeCAD 脚本只是后续 export/backend path，不是 workflow 上层依赖。

### Existing MVP Layer

这些模块继续保留，用于稳定 demo：

- `generator.py`：内置零件规格。
- `runner.py`：旧式 part pipeline。
- `exporter.py`：STEP/STL 导出。
- `validator.py`：preflight、几何、导出和意图一致性检查。
- `assembly_planner.py`：装配意图规划、确认 gate 和 backend-neutral config 生成。
- `assembly_validator.py`：装配 preflight、零件输入、bbox 放置、轻量约束和导出声明检查。
- `report.py`：旧式 JSON/Markdown 报告。

## Data Contracts

### requirement.json

最小字段：

```json
{
  "part_type": "mounting_plate",
  "unit": "mm",
  "intent": {
    "object_goal": "mounting_plate",
    "scope": "part",
    "use_case": "mounting"
  },
  "dimensions": {},
  "features": {},
  "outputs": ["step", "stl"],
  "check_level": "L0",
  "field_policy": {},
  "missing_information": [],
  "follow_up_questions": [],
  "assumptions": [],
  "requirement_status": {
    "complete_for_generation": true,
    "needs_user_input": false,
    "blocking_fields": []
  }
}
```

### check_level

- `L0 Playground`：当前实现。
- `L1 Maker`：报告框架。
- `L2 Engineering`：预留。
- `L3 Industrial`：预留。
- `L4 Safety Critical`：预留。

## Non-Goals

当前架构不做 Agent OS、不做大规模服务化、不做复杂多 agent 调度、不把 FreeCAD 或 CadQuery 写死为唯一未来方向。
