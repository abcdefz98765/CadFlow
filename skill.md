# CadFlow Workflow Skill Index

This file is the top-level compatibility entry for agents that look for a
single `skill.md` at the repository root.

The project is now organized as workflow-step skills. Do not treat this file as
the full rulebook; route step-specific decisions to the owning skill.

## Workflow

```text
input
  -> requirement
  -> planning
  -> part_modeling
  -> assembly
  -> review
```

## Skill Locations

- Requirement: `skills/requirement/`
- Planning: `skills/planning/`
- Part modeling, templates, and reference components: `skills/part_modeling/`
- Assembly rules and constraints: `skills/assembly/`
- Review/check levels: `skills/review/` and `policies/check_levels.md`
- Output/export contract: `policies/output_contract.md`

## Output Policy

- User workflow runs should receive an explicit `output_dir` whenever possible.
- If a workflow run does not provide `output_dir`, it falls back to `runs/<instance_name>/`.
- Example scripts generate local artifacts next to their own `model.py` files.
- Do not use `examples/` as the default destination for arbitrary user projects.
- Do not use `outputs/` as the primary path for new generated artifacts.

## Source Of Truth

- Shared policies live in `policies/`.
- Step-owned knowledge lives in `skills/<step>/knowledge/`.
- Top-level `knowledge/` is only an index for cross-skill references.
