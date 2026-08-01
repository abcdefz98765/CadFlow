# ADR-0001: One Product Work Orchestrator

Status: accepted and implemented for M1.

Decision date: 2026-07-25. Implementation accepted: 2026-07-27.

## Context

CadFlow currently exposes several independently callable create paths:
`CADWorkflow`, prompt and IR pipelines, provider create variants, reviewed-part
bridges, revision helpers, Workflow Console routes, examples, and benchmarks.
They do not consistently share Work ownership, Part Job attempts, artifact
identity, acceptance, or publication rules.

The target product has one Work spanning Intent, Design, Build & Evaluate, and
Accept & Deliver. Multiple product orchestrators would make lineage and trust
dependent on which entry point happened to be used.

## Decision

CadFlow will have one top-level product `WorkOrchestrator`.

The orchestrator is the sole target-product authority that may coordinate:

- Work mutation and active design-lineage pointers;
- Part Job and future Assembly Job attempt creation;
- bounded Agent Episodes;
- CadFlow-controlled execution and validation requests;
- reviewable-result publication;
- explicit accepted-result pointer changes;
- accepted-result-derived Deliverable Package definitions.

It owns coordination, not all implementation. Providers, skills, context,
execution workers, validators, artifact storage, and projections remain
separate replaceable services behind typed ports.

The orchestrator accepts commands aligned to the four user phases. It persists
Work changes only after local contract validation. It never edits historical
Run evidence.

## Entry-point policy

- **Target product** entry points will become thin command adapters to the
  `WorkOrchestrator`.
- **Compatibility** entry points may remain callable for existing deterministic
  Runs, but cannot establish target product state without a versioned
  compatibility adapter.
- **Evaluation** entry points remain opt-in test or benchmark surfaces and do
  not define product behavior.
- **Removable** entry points receive no new product dependencies and may be
  deleted after their callers migrate.

The current deterministic pipeline remains usable during M1. This ADR does not
reinterpret it as Agentic.

## Implemented M1 boundary

The first reviewable package recorded this decision and added the domain
contracts. M1 subsequently implemented the orchestrator command surface and
routed target-product Work mutations through it. Existing deterministic Run
behavior is available through one typed compatibility port, and legacy product
evidence is translated by an explicit read-only projector.

M1 does not add an Agent sandbox, a new Workbench UI, Assembly generation, or a
new `part_type`.

## Architecture change protocol

- **Affected objects:** Work, Run references, Part Job, Assembly Job definition,
  Deliverable Package definition, and artifact references.
- **Affected phases:** all four phases at the coordination boundary; no new
  user-visible phase behavior.
- **Internal checkpoints:** Part Job definition and attempt, explicit
  acceptance, artifact-reference projection, Assembly Job definition, and
  Deliverable Package definition.
- **Current user goal:** keep deterministic supported-family work usable while
  establishing unambiguous domain ownership.
- **Agent freedom:** unchanged in this package; provider-selected action design
  remains unavailable.
- **CadFlow side effects:** Work manifest writes remain local and validated;
  historical Run files remain append-only.
- **Visible success:** a v2 Work manifest can retain ordered attempts and an
  accepted pointer independently.
- **Failure and recovery:** invalid or dangling domain mutations fail before
  persistence; existing v1 manifests remain readable through projection.
- **Migration effect:** v1 manifests are projected in memory and are upgraded
  only when a later Work mutation is successfully persisted. Run directories
  are not migrated or rewritten.

## Consequences

Positive:

- one place can eventually enforce budgets, trust transitions, and lineage;
- deterministic compatibility code can be isolated rather than duplicated;
- evaluation scripts cannot accidentally become a second product runtime;
- acceptance and active design lineage have separate owners.

Costs:

- existing direct pipeline calls need explicit classification and gradual
  adapters;
- the legacy Workflow Console remains a compatibility/diagnostic surface until
  the M6 Workbench is real;
- compatibility and evaluation entry points remain callable, so repository
  callers must continue to treat them as non-product authority.

## Implementation evidence

- `src/ai_native_cad/orchestration/work_orchestrator.py`
- `src/ai_native_cad/orchestration/ports.py`
- `src/ai_native_cad/workflow_console/orchestrator_adapters.py`
- `src/ai_native_cad/workflow_console/legacy_product_projector.py`
- `tests/test_work_orchestrator.py`

M1 acceptance is recorded in `../../roadmap/milestones.md` and
`../../status/current-product-readiness.md`.

## Rejected alternatives

- Keep all pipelines as peer product entry points: rejected because state,
  provider, and publication semantics would remain inconsistent.
- Make the Agent provider the orchestrator: rejected because providers do not
  own side effects, validation, acceptance, or Work mutation.
- Replace the deterministic pipeline immediately: rejected because existing
  Runs and regression behavior must remain usable during migration.
