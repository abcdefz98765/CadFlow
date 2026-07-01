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

状态：收尾中。当前 verified 范围包括 STEP/STL artifact facts、模型 bbox/volume/solid_count inspection、trace summary、mounting_plate corner through-hole 数量/孔径/孔距，以及 mounting_plate/enclosure_lid 等简单板类竖边 chamfer。fillet、slots、general chamfer topology 和真实 rendered preview 明确保持 unverified/deferred。

目标：吸收成熟 text-to-cad/CAD agent 项目的 STEP-first、inspection、snapshot review 思路，把验证从“生成了文件和 bbox 大致正确”推进到“真实 CAD artifact 可测量、可审查、可对比”。

交付：

- 明确 `model.step` 是 primary CAD artifact，`model.stl` 是 derived mesh exchange。
- 当前 `preview.png` 保持 placeholder，并记录真实 geometry-rendered preview 的 TODO；不在本阶段引入 Blender、FreeCAD automation 或重依赖。
- `pipeline/geometry_inspector.py` 或等价模块，读取 model/STEP facts。
- topology 可靠时验证 mounting_plate 孔数量、孔径和孔距；简单板类竖边 chamfer 已进入实际测量；fillet、槽和 general chamfer topology 只在 inspection/report/trace 中标记 unverified，不做 speculative pass。
- `agent_trace.json` 增加 measured validation targets、inspection summary，以及 IR repair 的结构化 before/after diff。

验收：

- 至少 mounting_plate 的孔数量、孔径和孔距能在 simple through-hole topology 可靠时被实际验证。
- 至少一个 repair case 能证明修复只改变目标 feature。
- 失败报告能区分 bbox mismatch、missing feature、export failure 和 boolean artifact。
- repair attempt 的 trace 能记录 changed IR path、before/after value、root cause 和 affected feature。

## Phase 1.9: CAD Benchmark Suite

状态：已启动。当前实现已落地 IR-first benchmark manifests、benchmark runner、summary 输出，以及覆盖 mounting_plate、spacer、simple_bracket、enclosure_base 和 repair case 的首批固定用例。

目标：用固定 benchmark 衡量架构进步，避免每次只验证 happy path。

交付：

- `benchmarks/` 目录。
- benchmark prompts。
- expected IR 或 expected check targets。
- benchmark summary report。
- benchmark runner。

首批 benchmark：

- mounting plate with four holes。
- spacer / washer。
- simple L-bracket。
- simple enclosure base。
- repair-required mounting plate。

后续 benchmark 扩展：

- circular flange：需先补齐受支持的 IR part_type、CadQuery generator 和 validation contract。
- golden report / trace samples：在 benchmark output schema 稳定后固化。

验收：

- benchmark 可在 CI/本地一键运行。
- 每个 benchmark 检查 STEP 输出、关键尺寸、必需 feature、trace 完整性。
- 至少包含一个需要 IR repair 才能成功的 case。

## Phase 1.10 / Product v0.4a: Local Workflow Console Backend

状态：backend foundation complete。当前已落地 dependency-free Python backend scaffold、path-safe by-id API、route contract 和 in-process dispatch；HTTP server/API adapter 和前端仍是后续工作。该阶段承接 M1.8/M1.9 的 artifact、inspection、report、trace 成果，把现有 file-first workflow 暴露为本地单用户 backend；不引入云端队列、账号系统、多用户协作、LLM provider 依赖或新的 CAD generator 能力。

目标：让 Web UI 能按 workflow stage 推进，而不是一次性黑盒运行。首版本地执行单元定义为 `StageRunner`：读取上游 artifact，执行一个确定性 Python workflow step，写出下游 artifact、status、flow/rework decision 和 log。`AgentAdapter` 是自然语言理解和解释边界，`StageRunner` 是本地执行和落盘边界，两者不合并。LLM/token worker 只作为未来 `LLMApiAgentAdapter` 的可插拔实现，不能成为跨阶段状态源。

交付：

- Python run 管理：创建/打开本地 run directory，可只写入 `prompt.txt` 后再逐阶段推进，并列出当前 artifact。
- Path-safe run-id API：为后续 HTTP routes 提供按 run id 创建 run、读取 metadata/artifact/downloadables 和运行 stage 的入口，只解析 `outputs/` / `runs/` 下的单级目录名，拒绝 absolute path、`..`、path separator、重复创建目标和未配置 root。
- Route contract scaffold：用 dependency-free Python data/functions 定义后续 HTTP method/path 语义、by-id backend operation 映射、in-process route dispatch 和 success/error envelope；不引入 HTTP server、web framework 或独立 state store。
- Python `StageRunner`：运行 Requirement、Planning、Part Modeling，以及完整 `run_text_pipeline()`；可从已有 run artifact 推进下一阶段，并在 `logs/runtime.json` 记录本地 stage history。
- Python artifact API：读取 `prompt.txt`、`requirement.json`、`planning_artifact.json`、`input_ir.json`、`report.json`、`agent_trace.json`、`report.md` 和 `logs/runtime.json`。
- Python artifact edit API：只允许校验后写入 `requirement.json`、`planning_artifact.json` 和 `input_ir.json`，并把 edit history 记录到 `logs/runtime.json`。
- Python file discovery：识别当前 run 的 `model.step`、`model.stl`、`preview.png` 和 `model.py`，供后续 HTTP/file serving 使用。
- Python gate decision API：把 approve/reject/return/override 记录追加到 `logs/runtime.json` 的 `workflow_console.gate_decisions`，不新增独立 decision store。
- 后续 HTTP API：stage endpoints、gate decision endpoints、file serving。
- deterministic runtime：优先复用 `run_text_pipeline()`、`run_ir_pipeline()`、`run_agent_loop()` 和 report/review helpers。

边界：

- workflow state 仍以文件 artifact 为准。
- 不引入独立 state store；run-id API 只是对现有 artifact directories 的安全解析层。
- 后续 HTTP adapter 必须只包裹 by-id backend methods；直接 `run_dir` Python APIs 仍保持内部使用，不作为 route contract 暴露。
- 本地 workflow status vocabulary 保持集中定义，便于后续 API/UI 复用。
- 首版 StageRunner 使用现有 deterministic Python 入口；不要求 LLM provider。
- 不把聊天上下文、token 流或浏览器状态作为 source of truth。
- 不运行 benchmark，不改变 benchmark contract。
- 不提供任意 shell command endpoint 或普通用户 workflow 中的 unrestricted CLI agent execution。

## Phase 1.11 / Product v0.4a: Web Workflow Console UI + Viewer

状态：first local UI slice landed。当前已有 `web-viewer/workflow-console.html` 和 stdlib-only local bridge `ai_native_cad.workflow_console.server`，在本地 backend 之上提供 workflow cockpit；不是浏览器内 CAD 编辑器。

目标：用户可以在 Web 端输入需求、检查需求拆分、确认/修改 handoff artifact、触发下一阶段，并查看 report/trace/STL preview，形成可审查的逐步 workflow。

交付：

- stage timeline：Requirement -> Planning -> Part Modeling -> Review -> Outputs。
- artifact inspector/editor：展示 JSON/Markdown artifact；修改必须通过确认动作写回文件。
- report/trace viewer：突出 verified、unverified、warnings、errors、flow/rework decision。
- preview viewer：复用并改造 `web-viewer` 的 STL preview，加载当前 run 的 `model.stl`；STEP 仍是 primary CAD artifact。
- stage controls：run next stage、rerun current stage、approve、return upstream、open output folder。
- local bridge：使用 Python stdlib HTTP server 包裹现有 `dispatch_route(...)`，只暴露 route contract 和 whitelist downloadable files，不新增 FastAPI/HTTP dependency。

当前已完成：

- runs list/select、prompt-only create run、run status/current stage、path-free stage history timeline 和 gate decision timeline。
- run Requirement、Planning、Part Modeling、Review、Outputs 和 full text pipeline by safe run id。
- readable artifact list/read。
- artifact inspector polish：type labels and default selection order favoring `report.md`。
- compact report/trace summary：status、flow/rework decision、warnings/errors、attempts、final candidate。
- editable artifact save for `requirement.json`、`planning_artifact.json`、`input_ir.json` only。
- approve/reject/return/override gate decision recording。
- UI running state and visible error banner for stage/action failures。
- STEP/STL/preview/model.py downloadable list，`model.stl` secondary viewer link。
- scroll-safe STL preview with explicit Interact/Release mode。
- right-side Inspector tabs for summary, gate, downloads, and activity so the console remains dense without pushing the STL preview down。

边界：

- 不做浏览器内参数化建模、约束求解、装配 mating 推断或生产级 release。
- 不声称 `preview.png` 已变成真实渲染；Web viewer 是交互式 artifact preview。
- 不绕过 `requirement.json` / `planning_artifact.json` / `input_ir.json` 直接从 prompt 生成 CAD。
- Review 和 Outputs 是 local check stages：Review 读取既有 `report.json` flow decision；Outputs 检查可发布 artifact，尤其是 primary `model.step`，不重新生成 CAD。

## Phase 1.12 / Product v0.5: LLMApiAgentAdapter

状态：计划中。该阶段在 v0.4 Web Workflow Console 和 `AgentAdapter` contract 稳定后推进。

目标：把默认用户体验从确定性 parser fallback 升级为 LLM API 辅助的自然语言理解、结构化需求生成、规划生成和解释，但仍保持 CadFlow Python API 为确定性执行层。

交付：

- `LLMApiAgentAdapter` 实现 `parse_requirement()`、`create_plan()`、`suggest_repair()` 和 `explain_review()`。
- LLM 输出必须通过 schema validation 和 workflow gate。
- 对缺失、歧义、高风险或安全相关字段进入用户确认流。
- 不直接生成任意 CadQuery 代码，不绕过 CAD IR。

边界：

- 不引入 OpenCode/Codex CLI 作为默认 end-user CAD generation runtime。
- 不把 prompt/chat history 作为跨阶段 source of truth。
- 不改变 `model.step` 是 primary CAD artifact 的输出策略。

## Phase 2: Natural-language Requirement Parser

目标：增强 Requirement Parser，但保持 CAD IR 输出 contract 不变。

当前推进：

- 新增 `src/ai_native_cad/requirements.py`，把需求层从 workflow 中拆出为 Requirement Agent。
- 新增 `skills/requirement/`，沉淀需求模板、字段等级和缺失信息策略。
- `requirement.json` 开始记录 `intent`、`field_policy`、`missing_information`、`follow_up_questions`、`follow_up_requests`、`requirement_status`。
- 当前 parser 已能用确定性规则抽取 mounting_plate、spacer/washer、simple L-bracket、enclosure_base 的关键尺寸、部分孔规格、单位和 STEP/STL 输出请求。
- 对未从文本或 overrides 明确给出的必需尺寸，`missing_information` 会记录具体 `dimensions.*` 字段；L0 可保留模板默认值探索生成，L1+ 会要求用户补全关键尺寸。
- 当前 parser 会把 unsupported inch units 和冲突尺寸记录为 diagnostics，并转入 missing information，而不是猜测 CAD IR。
- `follow_up_questions` 保持字符串兼容字段，`follow_up_requests` 提供 field/category/code/source/reason 等机器可读补全请求。
- 当前 parser 会输出轻量 `cad_brief`，作为 Requirement/Planning 元数据记录 part type、intent、坐标约定、尺寸/feature 字段、保守 validation targets、假设策略和澄清状态；它不替代 CAD IR，也不参与 Text -> Code 绕过。
- 新增 `examples/prompt_pipeline/` 作为手工全链路调试入口，从 prompt 写出 `requirement.json`，再经 CAD IR 进入现有 CAD Agent Loop；benchmark 仍保持 IR-first。
- Phase 2 的核心边界明确为：用户可以自然语言输入，但 Requirement Agent 必须通过分析、追问、补全和记录假设产出规范 `requirement.json`；下游 Planning/CAD IR/Review 只消费结构化字段，不再解析 `source.input_text`。

后续任务：

- 增加 requirement-only contract/golden cases，验证规范 `requirement.json` 的字段完整性、缺失信息和追问请求。
- 扩展确定性抽取覆盖更多尺寸表达、孔位表达、厚度表达、单位和输出格式组合。
- 扩展 CAD Brief 对复杂输入的覆盖：记录建模意图、坐标约定、假设、冲突和验证目标，并持续保持 CAD IR 为生成 source of truth。
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
- Workflow 仍是编排代码和 pipeline 入口，不新增独立 Workflow Skill；routing 决策归 Planning，需求补全归 Requirement。

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
