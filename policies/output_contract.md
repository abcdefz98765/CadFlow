# Output Contract

Purpose: define traceable output artifacts and path behavior without becoming a
separate design skill.

Export is a utility capability. It writes exchange files and reports requested
by workflow steps, but it must not make requirement, planning, modeling,
assembly, or review decisions.

Standard output shape:

```text
input.md
requirement.json
plan.md
model.py
review.md
exports/
logs/
```

For assemblies, outputs may also include BOM, assembly reports,
backend-neutral assembly configs, and backend-native assembly files.

Path policy:

- User workflow runs should receive an explicit `output_dir`.
- Missing workflow `output_dir` falls back to `runs/<instance_name>/`.
- Example scripts write generated artifacts next to their own `model.py`.
- `examples/` is not the default destination for arbitrary user projects.
- `outputs/` is not the primary path for new generated artifacts.
