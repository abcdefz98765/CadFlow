# Design Part Skill

Skill id: `design_part`

Version: `0.2.0`

Role: Geometry Agent

Phase: Design

## Objective

Choose context and either a structured compatibility strategy or the declared
model-program strategy, submit candidates, and react to local observations. M2
uses the legacy CAD IR only as a compatibility output contract; it does not
make that closed schema the target geometry architecture.

## Allowed actions

- `request_context`
- `create_contract`
- `patch_contract`
- `request_validation`
- `create_model_program`
- `patch_model_program`
- `request_execution`
- `inspect_observation`
- `ask_user`
- `stop`

The provider chooses the next action. CadFlow validates the action, resolves
context, enforces budgets, asks the Tool Broker to invoke validators, and
persists concise evidence. The product route enters through `WorkOrchestrator`
and a typed `AgentDesignPort` for an existing owned Part Job attempt. A
path-safe request id makes exact retries idempotent and conflicting reuse fails
closed.

## Semantic context

- `intent_active`
- `part_job`
- `part_interfaces`
- `previous_candidates`
- `previous_validation_observations`
- `user_acceptance_or_revision`

Arbitrary paths, unrelated Works, superseded attempts, credentials, raw
provider traffic, and repository snapshots are prohibited.

## Tools and outputs

Direct tool in version `0.2.0`:

- `validate_structured_contract`

This tool is implemented as an in-process, no-filesystem, no-network local
validator behind the CadFlow Tool Broker. The Broker checks the active skill,
input contract, prohibited execution fields, and structured result before the
observation is returned.

Declared delegate:

- `model_program` v0.1, with `validate_model_program_source` and
  `execute_model_program` behind the attested Tool Broker.

Allowed output contracts:

- `cad_ir_draft` compatibility candidate
- `model_program_candidate`

A validated compatibility contract remains a candidate. Successful sandbox
execution remains a candidate until the separate CadFlow publication gate
passes; publication never implies acceptance.

## Budgets

- 16 total actions;
- 4 context requests;
- 3 contract submissions;
- 2 patches;
- 4 source submissions;
- 3 executions;
- 3 observation inspections;
- 180 seconds.

## Stop reasons

- `user_input_required`
- `unsupported_capability`
- `insufficient_context`
- `validation_exhausted`
- `budget_exhausted`
- `provider_failure`
- `policy_blocked`
- `completed`, only after successful re-import-validated execution and
  inspection, or CadFlow-owned contract validation.

## Prohibitions

- no shell, subprocess, network, dependency installation, credentials, or
  arbitrary filesystem access;
- no provider-selected path, command, environment, UID, candidate, observation,
  execution, or evidence identity;
- no provider-controlled Work mutation, publication, acceptance, or
  deliverables;
- no fabricated validation or engineering claims;
- no private chain-of-thought persistence.

## Validation and handoff

Only local validators decide whether a submission is valid. Model-program
source is a complete replacement candidate; the Broker re-runs AST policy,
requires a live digest-bound attestation, and executes only the current
CadFlow-assigned candidate. The latest execution observation must be inspected
before repair or completion. Product routing may invoke the independent
CadFlow-owned publication gate after completion. The provider cannot invoke or
bypass that gate, and neither execution nor publication may change lineage,
acceptance, Assembly, or Deliverable state.

Pre-execution submission evidence retains only source/parameter hashes. Full
values are written only by the Broker after policy and attestation gates pass.

## Knowledge

Private:

- `knowledge/structured_contract_strategy.md`

References:

- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `../../docs/workflow_contract.md`
