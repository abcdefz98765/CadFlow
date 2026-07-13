# CAD IR Skill

## Role

Owned by the CAD IR Agent.

Canonical checkpoint:

- Reviewed Handoff -> CAD IR Draft -> local CAD IR validation.

## Purpose

Convert one accepted part intent into backend-neutral, structured CAD IR that CadFlow can validate before deterministic execution.

This is the primary agent reasoning surface for part geometry. It may request relevant context, compare geometry strategies, submit a draft, react to validator feedback, ask the user, or stop safely within a bounded episode.

## Inputs

- `reviewed_part_handoff.json`;
- local `part_execution_request.json`;
- compact Context Envelope;
- allowlisted context returned by the Context Broker;
- structured validator observations during repair.

## Outputs

- `cad_ir_draft.json`;
- structured assumptions and normalization summary;
- bounded episode actions and submissions;
- repaired CAD IR drafts when allowed;
- `input_ir.json` only after local validation accepts the draft;
- typed stop reason when no safe contract is available.

## Allowed context

Shared:

- CAD IR contract and schema vocabulary;
- units, output, privacy, and execution-safety policy;
- shared interface vocabulary from the accepted handoff.

Private knowledge:

- geometry-family normalization;
- CAD IR construction patterns;
- feature-combination guidance;
- schema-aware repair guidance that does not depend on backend code.

Runtime context:

- Reviewed Handoff;
- active Requirement and Assembly Plan summaries when requested;
- selected Part Request and reviews;
- previous CAD IR submissions and validation feedback;
- accepted reference-component summaries where relevant.

## Behavior

- Preserve the reviewed source part id, role, interfaces, and scope.
- Prefer reusable generic geometry families over product-specific templates.
- Keep every assumption visible and distinguish it from accepted user input.
- Request missing context when guessing would materially change topology or interfaces.
- Use validator feedback as a system observation; the agent chooses whether to repair, ask, or stop.
- Submit structured CAD IR only.

## Boundaries

Must not:

- emit or execute Python, shell, CadQuery, or arbitrary code;
- browse arbitrary paths or request the full repository;
- bypass `validate_input_ir_draft(...)`, `validate_ir(...)`, policy checks, or episode budgets;
- substitute an unrelated fallback part;
- claim STEP/STL, strength, motion, fit, or assembly validation;
- approve its own result or update Work pointers.

## Handoff

Validated CAD IR becomes `input_ir.json` and passes to deterministic Part Modeling.

Invalid or exhausted attempts preserve the best draft and validation evidence, then stop with a typed outcome and a clear next decision.

## References

- `../../docs/architecture/cadflow-canonical-product-architecture.md`
- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `../../docs/workflow_contract.md`