# CadFlow Skills

Skills are versioned behavior contracts for logical agent roles. They are organized by canonical workflow responsibility, not by provider, CAD backend, product family, or UI page.

Read first:

- `../docs/architecture/cadflow-canonical-product-architecture.md`
- `../docs/architecture/agent-skill-knowledge.md`
- `../docs/workflow_contract.md`

## Skill map

    Prompt
      -> requirement
      -> planning
      -> cad_ir
      -> part_modeling
      -> review

    accepted parent result + change request
      -> revision

    multiple accepted Part Jobs, future
      -> assembly

Current skill directories:

- `requirement/` — prompt interpretation, structured requirement, assumptions, missing information, and clarification.
- `planning/` — design route, decomposition, interfaces, candidate/reference planning, and engineering trade-offs.
- `cad_ir/` — one reviewed part intent to backend-neutral CAD IR through bounded context and validation feedback.
- `part_modeling/` — validated CAD IR to deterministic geometry, products, and execution evidence.
- `review/` — scoped Part Request, Part Result, and Work-level evidence explanation; user approval remains separate.
- `revision/` — change intent, revision plan, structured patch proposal, and parent/child lineage.
- `assembly/` — future assembly placement, constraints, clearance, and assembly-level validation after multiple Part Jobs exist.

## Ownership rules

Each `SKILL.md` defines only its owned responsibility:

- canonical checkpoint;
- accepted inputs;
- structured outputs or actions;
- allowed context and tools;
- shared knowledge scopes;
- private knowledge scopes;
- validation and stop conditions;
- prohibited side effects;
- next handoff.

A skill must not duplicate or redefine the entire product workflow.

## Knowledge placement

- Global invariants live in `policies/`.
- Cross-skill knowledge lives in top-level `knowledge/` only when multiple skills truly share one source of truth.
- Skill-private knowledge lives under `skills/<skill>/knowledge/`.
- Accepted Work artifacts are runtime context, not static knowledge.
- Validator and execution feedback are Run/episode observations, not global knowledge.

Do not duplicate the same rule in multiple knowledge directories. Promote it to a shared source instead.

## Runtime loading

A provider or proposer should receive only:

- global minimal rules;
- the current skill guide;
- the operation contract;
- selected shared knowledge;
- selected skill-private knowledge;
- compact allowlisted Work context;
- current Run observations.

It must not receive every skill, the entire knowledge tree, arbitrary files, secrets, raw transcripts, or execution authority.

## Development rule

Changing a skill responsibility or knowledge ownership is an architecture change. Update the canonical agent/skill/knowledge document, affected contracts, runtime selector or registry, tests, roadmap, and readiness status together.