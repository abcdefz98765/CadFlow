# Project PRD

本文件指向当前主 PRD：`docs/PRD_new.md` 与最终版摘要 `docs/FINAL-PRD.md`。

项目方向已经调整为：

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

单零件生成主路径为：

```text
text/input_ir.json
  -> CAD IR
  -> CAD Agent Loop
       -> candidate code generation
       -> execution
       -> validation
       -> failure analysis
       -> IR repair
       -> retry, max 3
  -> STEP-first output
  -> report + agent_trace
```

核心目标是 IR-driven、workflow-first 的自然语言参数化 CAD agent，而不是 Prompt to CAD 脚本集合，也不是 AI Engineering OS。

当前验收重点：

- 保留可运行自然语言建模 MVP。
- 新增 CAD IR、workflow 层和 CAD backend 抽象。
- 固化标准输出目录。
- 支持 L0 Playground。
- 为 L1 Maker 输出报告框架。
- 建立 `knowledge/` 和 `policies/`。
- 保证 IR pipeline 的 `mounting_plate`、`spacer`、`simple_bracket` 示例可运行。
- 保证 CAD Agent Loop 可以记录失败、修复 IR、重试并输出 `agent_trace.json`。

下一阶段重点：

- STEP-first inspection：以 `model.step` 为主验证对象，STL 作为派生 mesh 输出。
- CAD brief：在复杂自然语言或多源输入时，先形成可审查的建模 brief，再落到 CAD IR。
- Geometry inspector：真实测量孔、槽、倒角、关键距离和 repair diff，而不是只依赖 bbox/volume。
- Real preview/viewer：用真实生成几何渲染 `preview.png` 或 viewer snapshot。
- Benchmark suite：用固定 prompts、expected IR 和 expected checks 衡量架构进步。
