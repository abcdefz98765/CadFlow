# Bounded Design Episodes, Context Broker, and Tool Broker

## Authority and scope

This document defines how CadFlow gives an Agent meaningful design freedom
inside controlled context, tool, execution, and publication boundaries.

Read with:

- `cadflow-canonical-product-architecture.md`
- `agent-skill-knowledge.md`
- `../workflow_contract.md`

## Executive rule

CadFlow constrains authority, not design thought.

The Agent may choose how to investigate, model, compare, execute, inspect, and
repair a design. CadFlow controls:

- what context can be retrieved;
- which tools can be called;
- where candidate code can run;
- budgets and stop conditions;
- what evidence is persisted;
- what becomes reviewable or accepted.

```text
accepted objective and compact context
  -> Agent chooses an action
  -> Context Broker or Tool Broker responds
  -> Agent observes and chooses again
  -> reviewable result or typed stop
```

## Runtime layers

```text
Work / Part Job / Assembly Job
  -> Episode Orchestrator
       -> Skill Registry
       -> Context Broker
       -> Provider Adapter
       -> Tool Broker
            -> isolated execution worker
            -> contract validators
            -> geometry inspectors
            -> assembly and drawing tools
  -> publication validator
  -> immutable Run evidence
  -> explicit Work acceptance
```

## Episode contract

```text
run_design_episode(
    objective,
    context_envelope,
    capabilities,
    budget,
) -> AgentEpisodeResult
```

Core types:

- `AgentObjective`;
- `ContextEnvelope`;
- `AgentCapabilities`;
- `EpisodeBudget`;
- `AgentAction`;
- `SystemObservation`;
- `CandidateReference`;
- `AgentEpisodeResult`.

## Agent actions

Initial action vocabulary:

- `request_context`;
- `ask_user`;
- `propose_candidates`;
- `create_contract`;
- `patch_contract`;
- `create_model_program`;
- `patch_model_program`;
- `request_validation`;
- `request_execution`;
- `inspect_artifact`;
- `create_part_jobs`;
- `propose_assembly`;
- `request_deliverables`;
- `stop`.

Each action requires a skill declaration and typed payload.

Unknown or undeclared actions are rejected.

## Real Agentic behavior

An Agentic episode must let the provider choose at least:

- which allowed action to take next;
- which semantic context to request;
- which candidate strategy to pursue;
- whether to repair, change strategy, ask the user, or stop after an
  observation.

The following sequence is deterministic orchestration, not Agentic design:

```text
request one fixed context
  -> call adapter once
  -> validate once
  -> stop on failure
```

It may remain as an offline fallback but must be labeled accordingly.

## Context Broker

The Context Broker resolves semantic Work and Run context.

Responsibilities:

- build a compact initial envelope;
- resolve accepted Work decisions;
- provide Part Job and Assembly Job context;
- exclude superseded or unrelated attempts by default;
- summarize large artifacts;
- enforce access and token budgets;
- attach provenance and trust role;
- reject arbitrary paths and private data.

Example semantic keys:

- `intent_active`;
- `accepted_constraints`;
- `part_job`;
- `part_interfaces`;
- `assembly_job`;
- `accepted_part_results`;
- `reference_component_summary`;
- `previous_candidates`;
- `previous_validation_observations`;
- `previous_geometry_measurements`;
- `user_acceptance_or_revision`;

Static skill knowledge is selected separately by the Skill Registry.

## Tool Broker

The Tool Broker is the only route from Agent action to side effects.

Responsibilities:

- validate action and tool input;
- select the execution profile;
- create an isolated candidate directory;
- enforce import, filesystem, network, process, and resource policy;
- capture source, parameters, logs, outputs, and exit state;
- invoke local validators and inspectors;
- return a structured observation;
- prevent candidate code from mutating Work state.

Tool categories:

- validate structured geometry contract;
- execute feature graph;
- execute sandboxed CadQuery/build123d model program;
- inspect STEP or native geometry;
- compare candidates or revisions;
- execute assembly placement/constraints;
- generate drawings and BOM;
- package accepted deliverables.

## Sandboxed execution profile

The initial model-program profile must provide:

- dedicated writable directory;
- read-only or copied declared inputs;
- no network;
- no credential or environment exposure;
- allowlisted Python modules and CAD APIs;
- blocked subprocess and shell APIs;
- time, memory, output-size, and process-count limits;
- captured stdout/stderr without secrets;
- deterministic cleanup or quarantine;
- explicit generated-file allowlist.

On platforms where the required isolation cannot be enforced, the model-program
action is unavailable. The system must not silently run with host authority.

## Candidate lifecycle

```text
proposed
  -> source_or_contract_validated
  -> queued
  -> executing
  -> execution_completed
  -> inspected
  -> result_validated
  -> reviewable
```

Failure states:

- contract rejected;
- sandbox policy rejected;
- execution failed;
- geometry invalid;
- output incomplete;
- inspection unsupported;
- budget exhausted.

Only `reviewable` candidates may be presented for acceptance.

## Observations

System observations are separate from Agent actions.

Examples:

```json
{
  "event_type": "system_observation",
  "observation": "execution_failed",
  "candidate_id": "candidate_003",
  "codes": ["boolean_operation_failed"],
  "repairable": true
}
```

```json
{
  "event_type": "system_observation",
  "observation": "geometry_measured",
  "candidate_id": "candidate_004",
  "measurements": {
    "solid_count": 1,
    "volume_mm3": 12840.4
  }
}
```

The Agent may repair, change strategy, ask, request context, or stop. The
orchestrator does not invent the decision.

## Budgets

Every episode declares operation-specific limits:

- total actions;
- context requests and bytes;
- candidate submissions;
- contract or program patches;
- execution calls;
- inspection calls;
- wall-clock time;
- candidate storage;
- provider retries.

Budget exhaustion preserves the best candidate and observations, then stops
with `budget_exhausted`.

## Typed stop reasons

Initial stop outcomes:

- `completed_with_reviewable_result`;
- `user_input_required`;
- `unsupported_capability`;
- `insufficient_context`;
- `validation_exhausted`;
- `execution_exhausted`;
- `sandbox_unavailable`;
- `budget_exhausted`;
- `provider_failure`;
- `policy_blocked`;

A stop result includes a concise recovery action.

## Persistence

Suggested Run layout:

```text
episodes/<episode_id>/
  objective.json
  capabilities.json
  context_manifest.json
  events.jsonl
  candidates/
  observations/
  result.json
```

Persist:

- objective and capability mode;
- selected skill, knowledge, actions, and tools;
- context provenance;
- candidate contract or source;
- validation and execution observations;
- repair summaries;
- budget use and stop reason.

Do not persist:

- private chain-of-thought;
- secrets;
- raw unrestricted provider traffic;
- undeclared environment state;
- arbitrary repository content.

## Deterministic fallback

Deterministic adapters remain useful for:

- tests and CI;
- offline examples;
- stable regression baselines;
- explicit fallback.

They use the same validators and publication boundary, but must be labeled
`deterministic_fallback`.

Fallback must not replace unknown intent with unrelated geometry or be reported
as Agentic design.

## Current implementation gap

Implemented:

- initial episode types and budgets;
- allowlisted context keys;
- structured validation observations;
- deterministic proposer compatibility;
- isolated deterministic candidate execution in the existing CAD pipeline.
- `design_part` v0.1 typed capability registry;
- an explicit provider-selected structured-contract loop with context choice,
  contract creation/patching, validation observation, focused questions, and
  typed stops;
- semantic context provenance, trust role, Work identity checks, and request/
  byte budgets;
- a CadFlow-owned Tool Broker catalog and brokered local structured-contract
  validation observations;
- an explicit Windows model-program capability gate covering filesystem,
  environment, network, subprocess, dependency, resource, and output controls;
- fail-closed `sandbox_unavailable` observations before candidate-directory or
  process side effects when that profile is unavailable.

Not implemented:

- product-integrated provider-selected design-to-execution Episode;
- Tool Broker execution worker for untrusted model programs;
- enforceable Windows sandbox profile (the implemented gate reports it
  unavailable);
- feature-graph geometry contract;
- Agentic assembly and drawing tools;
- real branching repair behavior in the product path.

The current provider-selected loop is an internal preview. It can branch after
contract-validator observations, but it cannot request CAD execution and does
not publish a reviewable result.

The existing deterministic CadQuery executor is not sandbox evidence: it uses
the host Python executable and inherits the host environment. The capability
gate deliberately excludes it from provider-source authority.

## Acceptance tests

The first Agentic vertical slice must prove:

- the provider chooses different valid action sequences for different states;
- requested context changes subsequent action;
- a failed validation can lead to repair or strategy change;
- the Agent can ask the user and resume in a new episode;
- sandbox policy violations fail closed;
- candidate code cannot write outside its directory or access the network;
- invalid geometry never becomes reviewable;
- successful reviewable output still requires explicit user acceptance;
- episode evidence contains no private reasoning or secrets.
