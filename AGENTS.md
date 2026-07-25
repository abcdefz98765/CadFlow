# CadFlow Agent Rules

Read this file before changing the repository.

## Mandatory target architecture

Before changing product behavior, UI, Agents, skills, knowledge, artifacts,
lineage, CAD execution, assembly, or deliverables, read:

- `docs/FINAL-PRD.md`
- `docs/architecture/cadflow-canonical-product-architecture.md`
- `docs/status/current-product-readiness.md`

CadFlow is migrating to an Agent-first CAD design workbench.

Canonical objects:

- Workspace contains Works and safe configuration.
- Work is one mutable engineering objective.
- Run is one append-only attempt and audit record.
- Part Job owns one intended part, multiple attempt Runs, and one accepted-result
  pointer.
- Assembly Job consumes exact accepted part results and owns assembly attempts
  and one accepted-result pointer.
- Deliverable Package contains accepted-result-derived models, assembly, BOM,
  drawings, and reports.
- Current Work is actionable; Run Snapshot is immutable.
- Active design lineage and accepted results are distinct.

Canonical user phases:

- Intent
- Design
- Build & Evaluate
- Accept & Deliver

Internal artifacts establish trust and recovery but must not force every task
through a fixed user-visible stage sequence.

Architecture changes require synchronized updates to PRD, canonical
architecture, contracts, UX, roadmap, task board, and readiness. Code,
projections, and tests follow when behavior changes. Documentation may define a
target before implementation only when readiness states the gap explicitly.

## Product priority

Prioritize:

1. capable Agent design;
2. visible geometry and meaningful alternatives;
3. controlled execution and measured evidence;
4. explicit acceptance and revision;
5. multi-Part Job and assembly progression;
6. engineering deliverables.

Do not spend the current milestone adding legacy Workflow cards, review forms,
graph states, or compatibility paths unless required for safety, migration, or
a release-blocking bug.

Do not add a new `part_type` template as the default response to a general
design-capability request. Use a benchmark to decide whether the feature graph
or sandboxed model-program path should express it.

## Agent, skill, context, and tools

For Agent or provider work, also read:

- `docs/architecture/agent-skill-knowledge.md`
- `docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `docs/workflow_contract.md`

Rules:

- Providers are replaceable; roles, skills, tools, contracts, and validators are
  CadFlow-owned.
- Skills declare actions, context, tools, budgets, outputs, and prohibitions.
- Global invariants live in `policies/`.
- Shared knowledge has one source under top-level `knowledge/`.
- Skill-private knowledge lives under `skills/<skill>/knowledge/`.
- Accepted Work state is runtime context, not static knowledge.
- Validator and execution feedback are episode observations, not global
  knowledge.
- Agents request semantic context, not arbitrary paths.
- Tool Broker controls all side effects.
- Provider-generated CAD source is an untrusted candidate and may run only
  through an enforceable sandbox profile.
- Local validators decide whether a candidate becomes reviewable.
- Only explicit user action changes accepted-result pointers.

An episode is not Agentic merely because it has steps and artifacts. A real
Agentic episode lets the provider choose actions, context, strategy, and its
response to observations.

## CAD execution

Target candidate paths:

- structured feature/assembly graph;
- sandboxed model program using an allowlisted CAD API.

Both paths converge on:

```text
candidate
  -> source/contract validation
  -> isolated execution
  -> geometry inspection
  -> result validation
  -> reviewable result or typed safe block
```

Never:

- run provider source with unrestricted host authority;
- expose credentials, arbitrary filesystem access, network, shell, subprocess,
  or dynamic dependency installation to a model program;
- publish failed candidates as trusted products;
- claim fit, motion, strength, tolerance, DFM/DFA, GD&T, FEA, or safety checks
  that did not run.

## Before changing UI

Read:

- `docs/ux/product-usability-principles.md`
- `docs/ux/workflow-cockpit-design-spec.md`
- `docs/architecture/web-workflow-console.md`

Write down:

- affected Work, Run, Part Job, Assembly Job, or Deliverable Package;
- affected user phase and internal trust checkpoint;
- current user goal;
- Agent action and CadFlow-controlled side effect;
- one recommended user action;
- visible success postcondition;
- failure feedback and recovery.

Default information order:

1. design objective;
2. geometry or assembly preview;
3. Agent progress, decisions, and assumptions;
4. recommended action or focused question;
5. validation and limitations;
6. alternatives, Parts, and assembly readiness;
7. history, artifacts, and diagnostics.

## Interaction closure

No enabled write or execution action may be silent.

Required lifecycle:

- confirmation when consequential;
- immediate pending feedback;
- duplicate-action protection;
- Agent/backend activity;
- refreshed domain state;
- postcondition verification;
- persistent success or failure;
- clear recovery or next action.

A returned function value or present file is not proof of product success.

## Artifact and lineage invariants

- Historical Run evidence is immutable.
- Work pointers may change.
- Part and Assembly attempts remain inspectable.
- Reviewable is distinct from accepted.
- Accepted results may belong to sibling Runs.
- Starting a revision does not remove the prior accepted result.
- Upstream changes mark dependent evidence stale.
- Deliverable Packages resolve only through accepted results.
- Legacy artifacts remain readable but do not redefine target architecture.
- Product state must not be inferred from filenames alone.

## Verification and documentation

Distinguish:

- implemented;
- automated verified;
- manually verified;
- production usable.

After changes, update as applicable:

- `docs/FINAL-PRD.md`
- `docs/architecture/cadflow-canonical-product-architecture.md`
- `docs/architecture/agent-skill-knowledge.md`
- `docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `docs/workflow_contract.md`
- `docs/status/current-product-readiness.md`
- `docs/roadmap/milestones.md`
- `docs/tasks/task-board.md`
- relevant UX, skill, knowledge, policy, and usage files.

New commands, ports, environment variables, execution profiles, cache/data
files, API paths, and error codes require `docs/usage.md` updates.

Before reporting completion, confirm:

- Agent design freedom was not replaced by a new closed template;
- side effects remain locally controlled;
- failed or unaccepted output cannot become a deliverable;
- Work/Run/Part/Assembly lineage is preserved;
- capability claims match verification evidence;
- readiness records what remains unimplemented.

## Safety defaults

- Web services default to `127.0.0.1`.
- Tailnet access is preferred for remote use.
- Public exposure is off by default and requires explicit documentation.
- Model-program network access is off by default.
