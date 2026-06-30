# Roadmap

## Phase 0: Current Baseline

状态：已有 CadQuery MVP、STEP/STL 导出、基础 validator/report、FreeCAD handoff 和初版 assembly planning/config/validation scaffold。

主要入口：

- `python examples/<part>/model.py`
- `ai_native_cad.runner.run_part()`
- `scripts/freecad_*.py`

## Phase 1: Workflow-first MVP

目标：把项目方向从 Prompt to CAD 收束为自然语言参数化 CAD workflow。

交付：

- `src/ai_native_cad/workflow.py`
- `src/ai_native_cad/backends/`
- 标准输出目录：`input.md`、`requirement.json`、`plan.md`、`model.py`、`review.md`、`exports/`、`logs/run.json`
- `examples/parts/mounting_plate/`
- `examples/parts/circular_button/`
- `knowledge/` 和 `policies/`
- 更新 README、usage、architecture、philosophy、FINAL-PRD

验收：

- mounting_plate demo 可运行。
- `python examples/workflow/mounting_plate_demo.py` 一键 workflow demo 可运行。
- workflow 输出稳定。
- 上层 workflow 不直接绑定 CadQuery。
- L0 真正支持，L1 有报告框架。

## Phase 1.5: IR-first CAD Pipeline

状态：已完成基础实现。

目标：让所有新单零件生成先经过稳定 JSON CAD IR，而不是以自然语言直接生成代码作为主路径。

交付：

- `src/ai_native_cad/cad_ir/schema.py`
- `src/ai_native_cad/cad_ir/parser.py`
- `src/ai_native_cad/cad_ir/validator.py`
- `src/ai_native_cad/cadquery/generator.py`
- `src/ai_native_cad/cadquery/executor.py`
- `src/ai_native_cad/pipeline/runner.py`
- `src/ai_native_cad/pipeline/report.py`
- `examples/ir_pipeline/`
- 标准输出目录：`outputs/<part_name>/input_ir.json`、`model.py`、`model.step`、`model.stl`、`report.json`、`report.md`、`preview.png`、`logs/runtime.json`

验收：

- mounting_plate、spacer、simple_bracket 可由 IR pipeline 生成。
- CadQuery 代码在执行前保存。
- 执行目录限制在项目 workspace。
- runtime errors 进入日志，便于失败后重试或再生成。
- validation 自动检查 STEP/STL、bounding box、volume、single solid 和 shape validity/watertight。

## Phase 2: Natural-language Requirement Parser

目标：增强 Requirement Parser，但保持 CAD IR 输出 contract 不变。

当前推进：

- 新增 `src/ai_native_cad/requirements.py`，把需求层从 workflow 中拆出为 Requirement Agent。
- 新增 `skills/requirement/`，沉淀需求模板、字段等级和缺失信息策略。
- `requirement.json` 开始记录 `intent`、`field_policy`、`missing_information`、`follow_up_questions`、`requirement_status`。

后续任务：

- 更可靠地抽取尺寸、孔位、厚度、单位和输出格式。
- 将自然语言稳定转为 CAD IR，而不是直接生成 CadQuery 代码。
- 对关键缺失信息进入多轮用户补全。
- 在 Requirement Skill 内完成早期产品拆解：识别制造件、参考组件、关键接口和会改变拓扑的缺失信息。

## Phase 2.5: Skill Consolidation And Library Scaffolding

目标：把工程规则收束到少量职责清晰的 workflow skill，避免目录数量掩盖真实流程。

交付：

- `skills/planning/`
- `skills/part_modeling/`
- `skills/assembly/`
- `skills/review/`
- `skills/part_modeling/knowledge/`
- `policies/output_contract.md`

要求：

- 早期产品拆解归 Requirement Skill。
- Planning Skill 负责设计分析、workflow routing、接口/基准和风险 gate。
- 装配规则放在 Assembly Skill，但公开表述限定为 assembly intent planning、part/reference list、backend-neutral config、基础 placement/bounding-box validation 和 review/report。
- 常用零件模板和参考组件知识放在 Part Modeling Skill 的 `knowledge/` 下。
- 全局 check level 仍由 `policies/check_levels.md` 定义。
- 输出目录和导出路径是 policy/utility，不作为单独 skill。

## Phase 3: Maker L1 Checks

目标：让 L1 Maker 真正可用。

候选任务：

- 最小壁厚检查。
- 3D 打印悬垂/支撑风险提示。
- STL 网格有效性检查。
- 常见 fastener clearance 表沉淀到 `knowledge/` 或 `policies/`。

## Phase 4: Backend Expansion

目标：验证 backend 抽象是否足够。

候选 backend：

- build123d
- FreeCAD API
- JSCAD / replicad

要求：

- 不破坏 workflow 输出结构。
- 不把 backend 细节泄漏到 Requirement Parser 或 Design Planner。

## Phase 5: Engineering L2 Exploration

目标：只在 L0/L1 稳定后推进。

候选能力：

- 装配间隙。
- 材料和制造方式约束。
- 公差策略。
- 简单 BOM 与评审记录。

## Deferred

- AI Engineering OS。
- 多 agent 平台化调度。
- 工业级 DFM/DFA。
- 成熟工业装配约束求解、任意 CAD mating 自动推断和运动仿真。
- 完整 GD&T。
- FEA。
- 安全关键件自动放行。
