# CadFlow Skills

Skills are CadFlow-owned behavior contracts for logical Agent roles. They
describe what an Agent may decide, which context and tools it may request, what
it must return, and when it must ask, stop, or hand off.

Read first:

- `../docs/architecture/agent-skill-knowledge.md`
- `../docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `../docs/workflow_contract.md`

## Runtime authority map

```text
Work request
  -> work_design (whole-Work concept, references, interfaces, decomposition)
  -> Part Jobs assigned by CadFlow
  -> design_part (one owned Part attempt)
  -> model_program or structured compatibility geometry
  -> Evaluation
  -> Revision

accepted Part results
  -> Assembly
  -> Evaluation

accepted Part / Assembly results
  -> Deliverables
```

Canonical runtime Skills:

- `work_design/` — version 0.1 Work-scoped provider-selected design,
  clarification, reference-component classification, interface reasoning, and
  Part decomposition. It cannot assign product identities or mutate a Work;
  CadFlow validates the proposal and creates Part Jobs.
- `design_part/` — version 0.2 design of one already-owned Part Job attempt.
- `model_program/` — version 0.1 controlled CAD source delegate.

Compatibility documentation retained during migration:

- `requirement/` — compatibility name for Intent interpretation and focused
  clarification.
- `planning/` — compatibility name for Design exploration, decomposition,
  interfaces, and alternatives.
- `cad_ir/` — structured Geometry candidate skill; currently limited to the
  legacy closed CAD IR.
- `part_modeling/` — controlled candidate execution and geometry evidence;
  currently deterministic CAD IR execution.
- `review/` — compatibility name for Evaluation and evidence explanation.
- `revision/` — child-Run change intent and candidate revision.
- `assembly/` — Assembly Job planning, placement, constraints, and checks.

Test/example support such as `DesignPlannerFakeAgentAdapter` is not a runtime
Skill authority. `agents.provider_context` remains a compatibility compiler for
legacy stage calls; canonical Episodes compile their Skill and knowledge from
the typed runtime registry.

Target additions still required by the roadmap:

- a deliverables skill for accepted-result-derived drawings, BOMs, and packages.

The runtime now includes a narrow CadFlow Tool Broker, a CadQuery v1 AST-only
source validator, a fail-closed Windows capability gate, and the registered
`model_program` delegate backed only by the exact attested
`CadFlow-Sandbox-CQ-v1` worker. CadFlow, not the provider, owns execution,
publication, and acceptance boundaries.

## Skill contract

Each `SKILL.md` declares:

- owned Agent role and supported actions;
- accepted inputs and candidate outputs;
- allowed context requests and tools;
- episode budgets and stop conditions;
- shared and private knowledge scopes;
- prohibited authority and side effects;
- validation and handoff rules;
- current implementation gaps.

Skills do not own execution authority. Side effects go through the Tool Broker,
and accepted-result pointers change only through explicit user action.

## Knowledge placement

- Global invariants live in `policies/`.
- Cross-skill knowledge has one source under top-level `knowledge/`.
- Skill-private knowledge lives under `skills/<skill>/knowledge/`.
- Accepted Work artifacts are runtime context, not static knowledge.
- Validator and execution feedback are episode observations, not knowledge.
- The runtime loader reads only knowledge ids declared by the active Skill,
  resolves only repository-contained Markdown sources, and applies fixed text
  bounds. Python summaries are not an independent knowledge source.

Do not load every skill or the whole repository into a provider context.
Runtime context is minimal, semantic, allowlisted, and auditable.

## Migration rule

A fixed sequence that merely calls a provider once is not an Agentic episode.
Target skills must support provider-chosen actions, context requests, strategy
changes, and responses to observations within CadFlow-controlled budgets.

Changing skill responsibility or authority is an architecture change. Update
the canonical architecture, contracts, registry/runtime routing, tests, roadmap,
and readiness together.
