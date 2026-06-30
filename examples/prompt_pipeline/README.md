# Prompt Pipeline Examples

These examples are for manual end-to-end debugging:

```text
prompt -> requirement.json -> planning_artifact.json -> input_ir.json -> CAD Agent Loop -> STEP/STL/report/trace
```

Run all prompt cases:

```bash
python examples/prompt_pipeline/run_prompt_examples.py
```

Run one case:

```bash
python examples/prompt_pipeline/run_prompt_examples.py mounting_plate_by_holes
```

Generated artifacts are written under `outputs/prompt_pipeline/<case_id>/`:

```text
prompt.txt
requirement.json
planning_artifact.json
input_ir.json
model.py
model.step
model.stl
report.json
report.md
preview.png
agent_trace.json
prompt_summary.json
prompt_summary.md
logs/runtime.json
```

If Requirement or Planning returns a `return` gate decision, the run stops before
CAD IR and Part Modeling. The output directory still contains the reviewable
requirement/planning artifacts that exist at the blocked stage plus
`report.json`, `report.md`, and `agent_trace.json`.

This directory is intentionally ignored by git. Benchmark cases remain
IR-first and deterministic under `benchmarks/`.

The prompt summary files are debugging aids. They collect requirement status,
CAD Brief validation targets, pipeline status, attempt count, measured targets,
hole inspection, and file paths from existing artifacts.
