# Part Modeling Skill

## Role

Owned by the deterministic Part Modeling executor and CAD Agent Loop.

Canonical checkpoint:

- validated CAD IR -> Part Modeling -> deterministic products and execution evidence.

## Purpose

Realize validated `input_ir.json` as one part through controlled backend capability mapping, geometry generation, export, and part-level checks.

This skill is execution-focused. Product interpretation and open-ended geometry reasoning belong upstream in Requirement, Planning, and CAD IR.

## Inputs

- validated `input_ir.json` / CAD IR;
- execution mode: Full or Contract;
- selected backend capability and output policy;
- structured repair advice when explicitly accepted by the loop.

## Outputs

Full mode may produce:

- `model.py` as a generated implementation artifact;
- `model.step`;
- `model.stl` when requested;
- `report.json` and `report.md`;
- `agent_trace.json`;
- `logs/runtime.json`.

Contract mode produces:

- validated `input_ir.json`;
- explicit `contract_complete` or `execution_skipped` status;
- no expected STEP/STL.

## Allowed context

Shared:

- CAD IR schema and output contract;
- units and geometry validation policy;
- shared manufacturing checks used by Review.

Private knowledge:

- backend capabilities;
- feature implementation patterns;
- primitive and template implementation helpers;
- export and geometry-check rules;
- execution-level repair patterns.

Runtime observations:

- current validated IR;
- geometry and export failures;
- bounded repair attempts;
- execution reports.

## Behavior

- Treat validated CAD IR as the part-geometry source of truth.
- Use reusable primitives, generic families, feature implementations, or templates as execution mechanisms.
- Run preflight validation before backend execution.
- Check non-empty geometry, positive volume, solid count, bounding dimensions, and required exports where supported.
- Separate verified, assumed, and unverified intent.
- Preserve failure evidence and stop safely when the backend cannot realize the validated contract.

## Boundaries

Must not:

- redesign the product or change Planning decisions;
- re-parse the original prompt;
- silently replace the part with an unrelated supported template;
- execute arbitrary provider-generated code;
- update accepted-result pointers;
- claim assembly, motion, strength, fit, tolerance-stack, or production validation unless those checks actually ran.

A missing direct template is not, by itself, a product-level terminal reason. The CAD IR Agent must have been allowed to propose a valid generic contract first. Part Modeling may still block when no deterministic backend capability can execute that validated contract.

## Handoff

Products and reports pass to Part Result Review. User approval remains a separate Work-level decision.

## References

- `../../docs/architecture/cadflow-canonical-product-architecture.md`
- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/workflow_contract.md`
- `knowledge/feature_library.md`
- `knowledge/template_catalog.md`
- `knowledge/reference_components.md`