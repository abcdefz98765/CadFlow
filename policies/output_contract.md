# Output Contract

Purpose: define traceable output artifacts and path behavior without becoming a
separate design skill.

Export is a utility capability. It writes exchange files and reports requested
by workflow steps, but it must not make requirement, planning, modeling,
assembly, or review decisions.

CAD Agent Loop single-part output shape:

```text
outputs/<part_name>/
  input_ir.json
  model.py
  model.step
  model.stl
  report.json
  report.md
  preview.png
  agent_trace.json
  logs/
    runtime.json
```

`model.py` must be written before execution. Execution must run from the part
output directory inside the project workspace. Runtime errors must be logged so
the same IR can be analyzed, repaired, retried, or regenerated.

`model.step` is the primary CAD artifact. `model.stl` is a derived mesh output
for downstream exchange and preview use. Validation and trace summaries should
prefer measured CAD facts over mesh-only facts.

Phase 1.8 inspection records STEP/STL artifact facts, solid count, bounding
box, volume, and mounting_plate through-hole count/diameter when the CadQuery
topology is reliable. Unreliable feature topology must be recorded as
unverified instead of guessed.

`preview.png` is still a placeholder snapshot in Phase 1.8 unless a lightweight
geometry renderer is available. Real preview rendering is intentionally deferred
from this slice because Blender and FreeCAD automation are out of scope.

`agent_trace.json` must record the loop history:

- total attempts, capped at 3
- per-attempt status
- selected candidate and candidate scores when candidate mode is used
- measured validation targets
- inspection summary for generated geometry and STEP/STL artifacts
- feature inspection status, including mounting_plate hole inspection when available
- structured failure analysis for failed attempts
- IR repair changes
- final selected candidate

The IR is the source of truth for generated CAD. Text-to-code bypass is outside
the supported output contract.

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
- Missing CAD Agent Loop output root falls back to `outputs/`.
- Example scripts write generated artifacts next to their own `model.py`.
- `examples/` is not the default destination for arbitrary user projects.
- `outputs/` is the primary path for CAD Agent Loop generated artifacts.
- Generated code and exchange files must stay inside the project workspace unless the user explicitly chooses another approved location.
