# Requirement Skill

## Role

Owned by the Requirement Agent.

Canonical checkpoint:

- Prompt / Requirement Input -> Requirement -> optional Clarification.

## Purpose

Convert the user's natural-language engineering goal into a structured, reviewable requirement contract.

This skill owns intent capture, requirement fields, assumptions, missing information, focused clarification, and a proceed/clarify/safe-block recommendation.

It does not own final product decomposition, candidate selection, CAD IR, or geometry execution.

## Inputs

- immutable user prompt;
- optional accepted prior Work context for revision;
- controlled user overrides or clarification answers;
- requested check level when present.

## Outputs

- `requirement.json` or a new active `requirement_vN.json`;
- scope and object goal;
- known dimensions, constraints, and interfaces stated by the user;
- assumptions;
- missing or risky information;
- focused follow-up questions;
- requirement flow decision.

## Allowed context

Shared:

- global policy and check-level vocabulary;
- requirement artifact contract;
- common units and naming rules.

Private knowledge:

- requirement elicitation heuristics;
- missing-information policy;
- question prioritization;
- requirement field examples.

Runtime context:

- original prompt;
- accepted clarification answers;
- explicit prior Work decisions for revision.

## Behavior

- Preserve uncertainty instead of guessing material engineering decisions.
- Use assumptions only when they are low risk and visible.
- Ask focused questions when missing information changes topology, interfaces, intended motion, manufacturing route, safety, or acceptance criteria.
- Keep the requirement backend-neutral.
- Record what is known, assumed, missing, and blocked separately.
- Return unresolved product-architecture decisions to the user.

## Boundaries

Must not:

- choose the final decomposition into candidate parts;
- select a part for generation;
- invent safety-critical dimensions, loads, tolerances, or certification claims;
- generate CAD IR or CAD code;
- overwrite the original prompt or requirement artifact;
- reclassify browser state as accepted product context.

## Handoff

The active structured Requirement is consumed by Planning.

Planning may use Requirement-provided scope hints, but Planning owns the engineering route, decomposition, candidate/reference distinction, and design strategy.

## References

- `../../docs/architecture/cadflow-canonical-product-architecture.md`
- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/workflow_contract.md`
- `knowledge/requirement_template.md`
- `knowledge/fields_by_check_level.md`
- `knowledge/missing_info_policy.md`