# Getting Started

CadFlow is migrating from a workflow-first deterministic CAD application to an
Agent-first CAD design workbench.

Read in this order:

1. `../../README.md`
2. `../FINAL-PRD.md`
3. `../status/current-product-readiness.md`
4. `../usage.md`

The PRD describes the target. Readiness describes what the repository can
actually do today.

## Install the current implementation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,web]"
$env:PYTHONPATH = "src"
```

## Run current tests

```powershell
python -m pytest tests/ -q
```

## Try the current deterministic CAD path

```powershell
python examples/ir_pipeline/generate_examples.py
```

The current CAD IR uses supported `part_type` families and is a compatibility
implementation, not the target limit of CadFlow's design capability.

## Start the current browser console

```powershell
.\scripts\start_nicegui_console.ps1
```

This opens the legacy Workflow Console. It is useful for inspecting existing
Work/Run behavior but is not the target Agent Workbench UX.

## Describe a design objective

A useful design request states purpose, interfaces, important dimensions,
manufacturing preference, evaluation needs, and what may be explored:

```text
Design a compact wall-mounted enclosure for this controller board.
Keep the cable ports accessible, use four removable screws, and target FDM
printing. Show two mounting strategies, explain assumptions, and produce the
parts, assembly, BOM, and drawings when the design is accepted.
```

The target Agent should clarify only decisions that materially affect the
design, then explore and evaluate geometry through controlled tools. That
general Agentic loop is roadmap work and must not be inferred from the current
template examples.

See `../usage.md` for current APIs, artifacts, execution modes, environment
variables, and troubleshooting.
