# Planning Skill

## Role

Owned by the Planning Agent.

Canonical checkpoints:

- accepted Requirement -> Planning / Design Brief;
- Planning -> Assembly Plan and Candidate Parts when decomposition is required.

## Purpose

Translate the accepted Requirement into an engineering route, design strategy, and reviewable decomposition before CAD IR is created.

Planning owns functional decomposition, candidate/reference distinction, interface intent, datums, dependencies, risks, and concise alternatives.

It does not own requirement elicitation, detailed CAD IR synthesis, or backend-specific geometry execution.

## Inputs

- active accepted Requirement;
- accepted assumptions and clarification results;
- check level and product scope;
- relevant shared engineering vocabulary.

## Outputs

Depending on the route:

- `design_brief.json`;
- `planning_artifact.json`;
- candidate plan artifacts where supported;
- `assembly_plan.json` for assembly or multi-part scope;
- candidate parts and reference-only components;
- selected or recommended candidate;
- interfaces, dependencies, datums, risks, and capability boundaries;
- planning gate state.

## Allowed context

Shared:

- requirement and planning contracts;
- interface and reference-component vocabulary;
- shared manufacturing and check-level policy.

Private knowledge:

- decomposition patterns;
- interface-planning heuristics;
- candidate comparison guidance;
- datum, dependency, serviceability, and risk heuristics.

Runtime context:

- active Requirement and accepted clarifications;
- relevant prior planning review or user override when revising.

## Behavior

- Decide whether the request is single-part, assembly, multi-part, reference-only, or unsupported.
- Produce alternatives when meaningful and expose concise trade-offs.
- Separate generated candidates from reference-only components.
- Preserve functional interfaces and assembly context for downstream Part Jobs.
- Define the current selected or recommended candidate explicitly.
- Return to Requirement when an upstream product decision is missing.
- State capability boundaries without treating current backend support as the entire product design space.

## Boundaries

Must not:

- re-parse the prompt as a substitute for the accepted Requirement;
- generate detailed CAD IR;
- emit Python, CadQuery, or shell commands;
- silently choose an unrelated template because it is supported;
- claim that planning artifacts are generated CAD;
- perform final strength, motion, fit, tolerance-stack, or assembly validation.

## Handoff

For a single-part route, Planning hands an accepted part strategy toward CAD IR preparation.

For assembly or multi-part scope, Planning produces the Assembly Plan. Explicit candidate selection then leads to a Part Request for exactly one Part Job.

## References

- `../../docs/architecture/cadflow-canonical-product-architecture.md`
- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/workflow_contract.md`