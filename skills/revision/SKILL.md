# Revision Skill

## Role

Owned by the Revision Agent.

Canonical checkpoint:

- accepted parent result + explicit user change request -> revision child Run.

## Purpose

Translate a user-requested change into structured revision intent and a safe revision plan while preserving parent artifacts and lineage.

## Inputs

- user revision prompt;
- sanitized parent Run context;
- accepted parent CAD IR and result metadata when available;
- explicit revision scope and check level;
- previous revision feedback when retrying.

## Outputs

- `revision_request.json`;
- `change_intent.json`;
- `revision_plan.json`;
- structured patch proposal where supported;
- typed blocked or user-input-required outcome when no safe structured change exists;
- parent/child lineage metadata after deterministic execution.

## Allowed context

Shared:

- revision and lineage contracts;
- CAD IR field vocabulary;
- immutable Run and explicit-approval policy.

Private knowledge:

- supported change-intent patterns;
- safe field-path and patch guidance;
- revision strategy selection;
- comparison and before/after reporting rules.

Runtime context:

- selected parent Run and accepted result;
- parent `input_ir.json` and relevant reports;
- prior revision submissions and validator feedback.

## Behavior

- Preserve the user's requested change separately from system repair changes.
- Prefer explicit field-level patches when the source model is CadFlow-native.
- Record before/after values where possible.
- Ask or block when the requested edit cannot be represented safely.
- Create a child Run for execution and comparison.
- Keep external STEP/STL as reference-only unless an explicit supported import/edit path exists.

## Boundaries

Must not:

- overwrite the parent Run;
- silently regenerate everything without a structured change record;
- execute provider-generated code;
- claim robust feature recovery from STEP or mesh files;
- accept an unsupported free-form edit by fabricating a patch;
- automatically replace the accepted result without user approval.

## Handoff

A validated revision plan and patch enter deterministic revision execution. The child Run records lineage, comparison, reports, and products or a typed safe block.

## References

- `../../docs/architecture/cadflow-canonical-product-architecture.md`
- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/architecture/revision-workflow.md`
- `../../docs/workflow_contract.md`