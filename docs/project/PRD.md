# Project PRD

本文件指向当前主 PRD：`docs/PRD_new.md` 与最终版摘要 `docs/FINAL-PRD.md`。

项目方向已经调整为：

```text
input -> requirement -> planning -> part_modeling -> assembly -> review -> outputs
```

单零件生成主路径为：

```text
text/input_ir.json -> CAD IR -> CadQuery generator -> STEP/STL -> validation -> report
```

核心目标是 IR-driven、workflow-first 的自然语言参数化 CAD 建模工具，而不是 Prompt to CAD 脚本集合，也不是 AI Engineering OS。

当前验收重点：

- 保留可运行自然语言建模 MVP。
- 新增 CAD IR、workflow 层和 CAD backend 抽象。
- 固化标准输出目录。
- 支持 L0 Playground。
- 为 L1 Maker 输出报告框架。
- 建立 `knowledge/` 和 `policies/`。
- 保证 IR pipeline 的 `mounting_plate`、`spacer`、`simple_bracket` 示例可运行。
