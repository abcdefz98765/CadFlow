# Design Part Skill

Skill id: `design_part`

Version: `0.1.0`

Role: Geometry Agent

Phase: Design

## Objective

Choose context and a structured part-design strategy, submit a candidate
contract, and react to local validation observations. This first M2 package
uses the legacy CAD IR only as a compatibility output contract; it does not
make that closed schema the target geometry architecture.

## Allowed actions

- `request_context`
- `create_contract`
- `patch_contract`
- `request_validation`
- `ask_user`
- `stop`

The provider chooses the next action. CadFlow validates the action, resolves
context, enforces budgets, invokes validators, and persists concise evidence.

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

Allowed tool in version `0.1.0`:

- `validate_structured_contract`

Allowed output contract:

- `cad_ir_draft` compatibility candidate

No CAD execution or model-program tool is enabled. A validated contract is a
candidate, not geometry, a reviewable result, or an accepted result.

## Budgets

- 10 total actions;
- 4 context requests;
- 3 contract submissions;
- 2 patches;
- 180 seconds.

## Stop reasons

- `user_input_required`
- `unsupported_capability`
- `insufficient_context`
- `validation_exhausted`
- `budget_exhausted`
- `provider_failure`
- `policy_blocked`

## Prohibitions

- no Python/CAD source, shell, subprocess, network, or dependency installation;
- no filesystem access or paths;
- no Work mutation, execution, publication, acceptance, or deliverables;
- no fabricated validation or engineering claims;
- no private chain-of-thought persistence.

## Validation and handoff

Only the local structured-contract validators decide whether a submission is
valid. This skill stops after a validated compatibility contract or a typed
safe block. Controlled execution and geometry publication remain later M2
work behind the Tool Broker and sandbox.

## Knowledge

Private:

- `knowledge/structured_contract_strategy.md`

References:

- `../../docs/architecture/agent-skill-knowledge.md`
- `../../docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `../../docs/workflow_contract.md`
