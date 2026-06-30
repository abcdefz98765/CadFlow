# Software Architecture

CadFlow 架构以 workflow 为主线，而不是以某个 CAD 工具为中心。

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

当前单零件生成的主线是 IR-first CAD Agent Loop：

```text
text/input_ir.json
  ↓
CAD IR
  ↓
validate_ir
  ↓
CAD Agent Loop
  ├─ candidate CadQuery source generation
  ├─ isolated execution inside the selected project output directory
  ├─ STEP-first geometry inspection and output validation
  ├─ failure analysis
  ├─ structured IR repair
  └─ retry, max 3 attempts
  ↓
model.py + model.step + model.stl + preview.png
  ↓
report.json + report.md + agent_trace.json
```

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
  ir_pipeline/
    mounting_plate/input_ir.json
    spacer/input_ir.json
    simple_bracket/input_ir.json
    generate_examples.py
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
IR-first examples live under `examples/ir_pipeline/` and regenerate artifacts into each example's local `outputs/` directory.

### Skill Layer

`skills/`

项目规则按 workflow step 归位：

- `requirement/`：需求模板、字段等级、缺失信息回问策略。
- `planning/`：设计分析、workflow routing、基准、接口、风险和确认 gate。
- `part_modeling/`：常用零件模板、参数化入口和单零件生成闭环。
- `assembly/`：装配意图、轻量放置/约束规则、间隙记录和基础验证意图。
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

`logs/` contains structured JSON logs such as `run.json` and `generation.json`.

用户 workflow 应显式传入 `output_dir`。未传时使用 `runs/<instance_name>/` 作为 fallback。示例脚本属于 examples 自测，默认生成在各自 `model.py` 同目录，不代表任意用户项目的输出位置。

### IR Pipeline Layer

`src/ai_native_cad/cad_ir/`

- `schema.py` 定义 JSON-serializable `CADIR`。
- `parser.py` 支持 text -> requirement -> IR，以及 file -> IR。
- `validator.py` 校验单位、part type、必需尺寸和输出格式。
- `repair.py` 根据结构化失败分析修复 IR，同时保持 `part_type` 和用户意图。

`src/ai_native_cad/cadquery/`

- `generator.py` 将 CAD IR 确定性生成 CadQuery `model.py`，并在候选模式下生成最多 3 个候选实现。
- `executor.py` 先保存生成代码，再在仓库内指定输出目录执行，并写入 `logs/runtime.json` 和错误日志。

`src/ai_native_cad/pipeline/`

- `runner.py` 编排 `Text/IR -> CAD IR -> CAD Agent Loop -> validation -> report`。
- `agent_loop.py` 负责最多 3 次尝试、候选执行、失败转移、IR 修复和 trace。
- `failure_analyzer.py` 将执行日志、验证错误和缺失文件转换为结构化根因。
- `geometry_inspector.py` 记录 `model.step` / `model.stl` artifact facts、solid count、bounding box、volume，以及 holes/chamfers/fillets inspection scaffold。
- `scorer.py` 按几何有效性、尺寸准确性、可制造简洁性、boolean 风险和对称性为候选打分。
- `report.py` 生成 `report.json` 和 `report.md`。

IR pipeline 默认输出：

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

IR example 自测输出：

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

### CAD Agent Loop

零件生成不是单次 “prompt to code”，而是局部闭环。v0.3 主路径为：

```text
Text / input_ir.json
  ↓
CAD IR
  ↓
validate_ir
  ↓
generate_cadquery_candidates
  ↓
execute candidate model.py
  ↓
validate_pipeline_outputs
  ├─ success → score/select candidate → final output
  └─ fail → failure_analyzer → repair_ir → retry
```

约束：

- IR 是 CAD 生成的 source of truth。
- 不允许 Text -> Code 绕过 IR。
- 最大重试次数为 3。
- IR repair 不改变 `part_type`，不删除必需 feature，除非失败分析明确要求，否则不简化几何。
- `model.step` 是 primary CAD artifact，`model.stl` 是 derived mesh output。
- `preview.png` 当前仍是 placeholder；真实几何渲染在不引入 Blender/FreeCAD automation 或重依赖前保持 deferred。
- 最终输出必须包含 `agent_trace.json`，记录每次 attempt、失败原因、IR 修复、measured validation targets、inspection summary 和最终候选。

`agent_trace.json` 示例：

```json
{
  "total_attempts": 2,
  "steps": [
    {
      "attempt": 1,
      "status": "failed",
      "reason": "feature_not_realized",
      "inspection_summary": {"primary_artifact": "model.step"}
    },
    {
      "attempt": 2,
      "status": "success",
      "selected_candidate": "A",
      "measured_validation_targets": [],
      "inspection_summary": {"solid_count": 1}
    }
  ],
  "final_selected_candidate": "A",
  "final_inspection_summary": {"primary_artifact": "model.step"}
}
```

兼容 workflow 的旧闭环仍保留：

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

Assembly in the current open-source baseline means assembly intent planning,
part lists, manufactured/reference component separation, backend-neutral
assembly config, basic placement and bounding-box validation, and assembly
review/report generation. It does not mean mature geometric constraint solving,
automatic mating inference for arbitrary CAD files, full tolerance stack-up,
industrial DFA, motion simulation, or production-ready assembly release.

### Existing MVP Layer

这些模块继续保留，用于稳定旧 demo 和兼容入口：

- `generator.py`：内置零件规格。
- `runner.py`：旧式 part pipeline。
- `exporter.py`：STEP/STL 导出。
- `validator.py`：preflight、几何、导出和意图一致性检查。
- `assembly_planner.py`：装配意图规划、确认 gate 和 backend-neutral config 生成。
- `assembly_validator.py`：装配 preflight、零件输入、bbox 放置、轻量约束意图和导出声明检查。
- `report.py`：旧式 JSON/Markdown 报告。

新 IR-first 层是新增主路径，不要求立即删除旧 examples 或 `run_part()`。

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

### input_ir.json

最小字段：

```json
{
  "part_type": "mounting_plate",
  "part_name": "mounting_plate",
  "unit": "mm",
  "dimensions": {
    "length": 80,
    "width": 40,
    "thickness": 5
  },
  "features": {
    "holes": {
      "diameter": 5,
      "positions": "corner_4"
    },
    "chamfer": 1
  },
  "outputs": ["step", "stl"],
  "check_level": "L0"
}
```

### check_level

- `L0 Playground`：当前唯一完整支持的检查等级。
- `L1 Maker`：当前提供报告 scaffold，不是完整可打印性验证。
- `L2 Engineering`：预留，不代表工程放行。
- `L3 Industrial`：预留，不代表工业 DFM/DFA 或生产 release。
- `L4 Safety Critical`：预留，不能自动放行。

## Non-Goals

当前架构不做 Agent OS、不做大规模服务化、不做复杂多 agent 调度、不把 FreeCAD 或 CadQuery 写死为唯一未来方向，也不声称具备成熟工业装配求解、运动仿真、完整工程校核或生产级放行能力。
