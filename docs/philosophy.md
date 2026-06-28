# Philosophy

## Workflow First

CAD 生成不是一次 prompt 的结果，而是一条可检查的工程记录。输入、需求、设计分析、零件生成、装配、审查、导出和日志都应该保留下来。

## Backend Agnostic

CadQuery 是当前 MVP 后端，不是产品边界。workflow 层不能直接绑定某个 CAD 工具，未来可以接入 build123d、FreeCAD API、JSCAD 或 replicad。

## Engineering over Geometry

项目优先处理工程意图：用途、关键尺寸、孔位、安装面、零件/参考件、接口、制造方式、检查等级和假设。几何只是这些决策的表达。

## Traceable by Default

每次生成默认写出：

```text
input.md
requirement.json
plan.md
model.py
review.md
exports/
logs/
```

这让用户、工程师和 Agent 都能复盘“为什么这样建模”。

## Knowledge Ready

`knowledge/` 用来承载未来的材料、紧固件、制造规则、标准尺寸和设计模式。当前不急于实现复杂知识库，只保留结构。

## Policy Ready

`policies/` 用来承载校核等级、输出规则、安全边界和审核流程。规则应逐步从 prompt 中沉淀成可维护文件。

## Current Bias

短期宁愿做一个窄而清晰、可运行、可追踪的自然语言 CAD MVP，也不扩张成笼统的 AI 工程平台。
