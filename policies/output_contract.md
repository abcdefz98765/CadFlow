# Output Contract

Purpose: define traceable output artifacts and path behavior without becoming a
separate design skill.

Export is a utility capability. It writes exchange files and reports requested
by workflow steps, but it must not make requirement, planning, modeling,
assembly, or review decisions.

IR-first single-part output shape:

```text
outputs/<part_name>/
  input_ir.json
  model.py
  model.step
  model.stl
  report.json
  report.md
  preview.png
  logs/
    runtime.json
```

`model.py` must be written before execution. Execution must run from the part
output directory inside the project workspace. Runtime errors must be logged so
the same IR can be retried or regenerated.

Legacy workflow output shape:

```text
input.md
requirement.json
plan.md
model.py
review.md
exports/
logs/
```

`logs/` stores structured JSON logs. The workflow-level run record is
`logs/run.json`; generation-loop details are also written to
`logs/generation.json`.

For assemblies, outputs may also include BOM, assembly reports,
backend-neutral assembly configs, and backend-native assembly files.

Path policy:

- User workflow runs should receive an explicit `output_dir`.
- Missing workflow `output_dir` falls back to `runs/<instance_name>/`.
- Missing IR pipeline output root falls back to `outputs/`.
- Example scripts write generated artifacts next to their own `model.py`.
- `examples/` is not the default destination for arbitrary user projects.
- `outputs/` is the primary path for IR-first generated artifacts.
- Generated code and exchange files must stay inside the project workspace unless the user explicitly chooses another approved location.
