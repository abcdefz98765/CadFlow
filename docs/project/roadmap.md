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

## Phase 1.75: CAD Agent Loop System

状态：基础实现已完成。

目标：把 IR-first 单次 pipeline 升级为带失败分析、IR 修复、候选评分和多轮重试的 CAD engineering agent。

交付：

- `src/ai_native_cad/pipeline/agent_loop.py`
- `src/ai_native_cad/pipeline/failure_analyzer.py`
- `src/ai_native_cad/pipeline/scorer.py`
- `src/ai_native_cad/cad_ir/repair.py`
- `cadquery/generator.py` 支持 deterministic single candidate 和最多 3 个候选实现。
- `pipeline/runner.py` 改为通过 CAD Agent Loop 执行。
- 标准输出增加 `agent_trace.json`。

验收：

- 每次运行保留 `input_ir.json`、`model.py`、`model.step`、`model.stl`、`preview.png`、`report.json`、`report.md`、`agent_trace.json`。
- 失败时生成结构化 failure analysis。
- IR repair 保留 `part_type` 和用户意图，只改必要字段。
- 最大尝试次数固定为 3。
- 至少一个失败几何案例可以通过 IR repair 自动恢复。
- 多候选生成和评分可以参与最终候选选择。

后续任务：

- 把 failure taxonomy 扩展到更多 CadQuery/OpenCascade 失败类型。
- 用真实几何检查验证孔、槽、倒角等 feature 是否实际存在，而不是只做参数风险判断。
- 让候选 B/C 产生更有差异的实现策略，同时不删除必需 feature。

## Phase 1.8: STEP-first Inspection And Trace Quality

状态：已启动。当前实现已落地 STEP/STL artifact facts、模型 bbox/volume/solid_count inspection、trace summary，并在 topology 可靠时验证 mounting_plate corner through-hole 数量、孔径和孔距；preview 渲染继续保持 deferred。

目标：吸收成熟 text-to-cad/CAD agent 项目的 STEP-first、inspection、snapshot review 思路，把验证从“生成了文件和 bbox 大致正确”推进到“真实 CAD artifact 可测量、可审查、可对比”。

交付：

- 明确 `model.step` 是 primary CAD artifact，`model.stl` 是 derived mesh exchange。
- 当前 `preview.png` 保持 placeholder，并记录真实 geometry-rendered preview 的 TODO；不在本阶段引入 Blender、FreeCAD automation 或重依赖。
- `pipeline/geometry_inspector.py` 或等价模块，读取 model/STEP facts。
- topology 可靠时验证 mounting_plate 孔数量、孔径和孔距；槽、倒角、关键尺寸和 repair diff 后续继续推进。
- `agent_trace.json` 增加 measured validation targets、inspection summary；repair before/after summary 后续补齐。

验收：

- 至少 mounting_plate 的孔数量、孔径和孔距能在 simple through-hole topology 可靠时被实际验证。
- 至少一个 repair case 能证明修复只改变目标 feature。
- 失败报告能区分 bbox mismatch、missing feature、export failure 和 boolean artifact。

## Phase 1.9: CAD Benchmark Suite

状态：下一阶段。

目标：用固定 benchmark 衡量架构进步，避免每次只验证 happy path。

交付：

- `benchmarks/` 目录。
- benchmark prompts。
- expected IR 或 expected check targets。
- golden reports / trace samples。
- benchmark runner。

首批 benchmark：

- mounting plate with four holes。
- spacer / washer。
- simple L-bracket。
- circular flange。
- simple enclosure base。

验收：

- benchmark 可在 CI/本地一键运行。
- 每个 benchmark 检查 STEP 输出、关键尺寸、必需 feature、trace 完整性。
- 至少包含一个需要 IR repair 才能成功的 case。

## Phase 2: Natural-language Requirement Parser

目标：增强 Requirement Parser，但保持 CAD IR 输出 contract 不变。

当前推进：

- 新增 `src/ai_native_cad/requirements.py`，把需求层从 workflow 中拆出为 Requirement Agent。
- 新增 `skills/requirement/`，沉淀需求模板、字段等级和缺失信息策略。
- `requirement.json` 开始记录 `intent`、`field_policy`、`missing_information`、`follow_up_questions`、`requirement_status`。

后续任务：

- 更可靠地抽取尺寸、孔位、厚度、单位和输出格式。
- 为复杂输入增加 CAD Brief：记录建模意图、坐标约定、假设、冲突和验证目标，再落到 CAD IR。
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
- Robotics URDF/SDF workflow。
- G-code、slicer、printer handoff。
- 工业级 DFM/DFA。
- 成熟工业装配约束求解、任意 CAD mating 自动推断和运动仿真。
- 完整 GD&T。
- FEA。
- 安全关键件自动放行。
