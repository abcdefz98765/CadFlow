# Prompt Pipeline Examples

These examples are for manual end-to-end debugging:

```text
prompt -> requirement.json + CAD IR -> CAD Agent Loop -> STEP/STL/report/trace
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

This directory is intentionally ignored by git. Benchmark cases remain
IR-first and deterministic under `benchmarks/`.

The prompt summary files are debugging aids. They collect requirement status,
CAD Brief validation targets, pipeline status, attempt count, measured targets,
hole inspection, and file paths from existing artifacts.
