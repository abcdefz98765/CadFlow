# Bounded Agent Loop, Context Broker, and Checkpoint Workflow

## Status

Architecture direction for the next CadFlow agent iteration.

This document does not add a new CAD family, change the CAD IR contract, or enable unrestricted code execution. It defines how CadFlow should increase agent capability without weakening validation, lineage, user review, or deterministic execution boundaries.

## Executive Decision

CadFlow should not use the product workflow as a fixed script for agent reasoning.

The product workflow should represent stable, reviewable checkpoints:

```text
Requirement accepted
  -> Plan accepted
  -> Part selected
  -> CAD IR validated
  -> CAD generated
  -> Result reviewed
```

Inside each checkpoint transition, an agent may use a bounded, dynamic episode:

```text
understand objective
  -> inspect relevant context
  -> form or compare candidates
  -> submit a structured proposal
  -> receive validation feedback
  -> repair, request information, or stop safely
```

The architecture rule is:

> Workflow is a set of checkpoints and trust boundaries, not a rail that dictates every reasoning step.

CadFlow should strictly constrain side effects and accepted outputs, while allowing more freedom in interpretation, exploration, candidate generation, context retrieval, and repair.

## Why This Correction Is Needed

The current `AgentAdapter` boundary is directionally correct: agents translate user language and workflow context into structured contracts, while the deterministic pipeline owns execution.

However, the current method shape is mostly one-shot:

```text
parse_requirement(...)
create_plan(...)
create_part_ir(...)
suggest_repair(...)
```

A one-shot adapter call is easy to validate and test, but it can become too restrictive for real engineering tasks. Complex CAD work may require the agent to:

- request missing assembly context;
- inspect an accepted upstream artifact;
- compare multiple design candidates;
- explain assumptions;
- react to schema or geometry validation;
- revise a draft more than once;
- ask the user for a decision;
- stop because the available evidence is insufficient.

The deterministic adapter must remain available for tests, CI, offline demos, and fallback execution. It must not silently become the ceiling of CadFlow's product capability.

A rule such as:

```text
upper_link name contains link
  -> link_like_part
  -> elongated_plate_with_end_holes
```

is useful as a deterministic fallback and regression fixture. It is not a substitute for an agent understanding interfaces, constraints, assembly role, previous failures, and user intent.

## Design Principles

### 1. Constrain side effects, not useful reasoning

Strictly constrain:

- file writes;
- active-lineage updates;
- external tool execution;
- CAD execution;
- schema acceptance;
- model export;
- approval state;
- budget and retry count.

Allow bounded freedom in:

- interpreting the objective;
- identifying missing information;
- requesting relevant context;
- proposing alternatives;
- comparing trade-offs;
- generating structured drafts;
- reacting to validator feedback;
- choosing whether to repair, replan, ask the user, or stop.

### 2. Agent proposes; CadFlow decides what may execute

The agent may propose a plan, CAD IR draft, repair, clarification request, or next action.

The system remains authoritative for:

```text
schema validation
  -> policy validation
  -> deterministic execution
  -> artifact persistence
  -> lineage update
  -> user-visible status
```

An agent must never be able to declare success merely because it produced text or code.

### 3. Fixed checkpoints, dynamic transitions

The Workflow graph should continue to show stable product checkpoints. It should not attempt to expose every internal agent turn as a primary node.

For example, the visible transition:

```text
Reviewed Handoff -> CAD IR Draft -> Part Modeling
```

may contain an internal episode:

```text
inspect handoff
  -> request assembly interfaces
  -> compare two geometry concepts
  -> submit CAD IR draft
  -> receive hole-margin validation failure
  -> repair dimensions
  -> resubmit
  -> pass validation
```

The Workflow graph shows the trusted result of the episode. A compact episode trace remains available under Advanced / Diagnostics.

### 4. Small default context, on-demand retrieval

Do not place the entire Work, all Runs, all artifacts, and all traces into every model call.

Each episode begins with a compact context envelope. The agent may request allowlisted additional context through a Context Broker.

This avoids both failure modes:

```text
too much context -> noise, stale data, wrong Run, high cost

too little context -> name-based guessing, weak engineering understanding
```

### 5. Deterministic and agentic modes are both first-class

CadFlow should explicitly support:

- `deterministic`: stable local/mock behavior for tests, CI, examples, and fallback;
- `agentic`: provider-backed bounded episodes with context requests and repair loops.

The UI, reports, and traces must state which capability mode produced the result.

### 6. Preserve concise decisions, not hidden reasoning

CadFlow must not require or persist private chain-of-thought.

Persist only reviewable, product-relevant records:

- objective;
- context items requested;
- action selected;
- proposal summary;
- assumptions;
- alternatives considered at a concise level;
- validator feedback;
- repair summary;
- stop reason;
- final submitted contract.

## Architecture Layers

```text
User / Web Console
  -> Work Workflow and Checkpoints
  -> Agent Episode Orchestrator
       -> Context Broker
       -> Agent Adapter / Provider
       -> Tool Broker
       -> Contract Validators
  -> Deterministic CAD Pipeline
  -> Artifacts, Run Lineage, Reviews, and Products
```

### Work Workflow and Checkpoints

Responsibilities:

- define the current trusted product state;
- expose user review and intervention points;
- maintain active lineage;
- decide which checkpoint is current;
- display accepted results and limitations.

It must not encode the agent's complete internal strategy.

### Agent Episode Orchestrator

Responsibilities:

- start an episode with a clear objective;
- enforce step, token, time, context, and tool budgets;
- accept only allowlisted agent actions;
- route context requests through the Context Broker;
- route validation and execution requests through deterministic services;
- persist concise episode events;
- stop safely with a typed outcome.

Suggested interface:

```python
run_agent_episode(
    objective: AgentObjective,
    context_envelope: ContextEnvelope,
    capabilities: AgentCapabilities,
    budget: EpisodeBudget,
) -> AgentEpisodeResult
```

### Context Broker

Responsibilities:

- build the initial compact context envelope;
- resolve accepted Work-lineage artifacts;
- prevent accidental use of superseded or unrelated Runs;
- summarize large artifacts before model use;
- expose only allowlisted artifact types;
- record which context was supplied;
- reject arbitrary path access.

The Context Broker is not a general filesystem browser.

### Tool Broker

Responsibilities:

- expose safe, typed tools to the episode;
- validate tool arguments;
- enforce read/write boundaries;
- return structured observations;
- prevent provider-generated executable code from bypassing CAD IR.

Initial tools should be read-oriented and validation-oriented. Direct arbitrary Python, shell, or CadQuery execution is out of scope.

### Contract Validators and Deterministic Pipeline

Responsibilities remain unchanged:

- validate requirement, plan, CAD IR, and review contracts;
- reject unsafe or unsupported outputs;
- execute only validated CAD IR;
- produce STEP/STL and reports deterministically;
- preserve failure evidence;
- never replace an unsupported intent with an unrelated fallback part.

## Context Envelope

A compact initial envelope should contain only the information required to begin the episode.

Example:

```json
{
  "schema_version": 1,
  "objective": {
    "operation": "create_part_ir",
    "summary": "Create a reviewed CAD IR draft for upper_link"
  },
  "workflow": {
    "work_id": "golden_desktop_robot_arm",
    "checkpoint": "cad_ir_draft",
    "active_root_run_id": "run_2",
    "active_leaf_run_id": "run_3"
  },
  "accepted_decisions": [
    "The request is an assembly-level desktop robot arm",
    "upper_link is the selected candidate",
    "The result is a concept part for FDM"
  ],
  "selected_part": {
    "part_id": "upper_link",
    "role": "upper arm link",
    "review_status": "approved_for_single_part_create"
  },
  "constraints": [
    "Do not claim full assembly generation",
    "Do not claim strength validation",
    "Output must be CAD IR, not executable Python"
  ],
  "previous_attempts": [],
  "available_context": [
    "reviewed_part_handoff",
    "assembly_plan_summary",
    "requirement_summary",
    "previous_validation_feedback"
  ]
}
```

The initial envelope should not contain every raw artifact by default.

## Context Request Actions

The agent may request additional context through allowlisted actions.

Examples:

```json
{
  "action": "request_context",
  "context_key": "assembly_plan",
  "reason": "Need the selected part interfaces and related components"
}
```

```json
{
  "action": "request_context",
  "context_key": "previous_validation_feedback",
  "reason": "Need to avoid repeating the last geometry failure"
}
```

Supported context keys should be semantic, not arbitrary paths. Initial keys may include:

- `requirement_active`;
- `requirement_clarification`;
- `planning_active`;
- `assembly_plan`;
- `selected_part_request`;
- `reviewed_part_handoff`;
- `accepted_part_result`;
- `previous_cad_ir_attempts`;
- `previous_validation_feedback`;
- `reference_component_summary`;
- `user_stage_review`.

Every returned context item should include provenance:

```json
{
  "context_key": "assembly_plan",
  "source_run_id": "run_2",
  "source_stage_id": "assembly_plan",
  "source_type": "accepted_active_lineage",
  "summary": {},
  "raw_artifact_available": true
}
```

## Allowlisted Agent Actions

An episode should accept only typed actions.

### `request_context`

Request one semantic context item from the Context Broker.

### `ask_user`

Stop the episode at a user-decision checkpoint with structured questions.

```json
{
  "action": "ask_user",
  "questions": [
    {
      "field": "joint_hole_diameter_mm",
      "question": "What joint fastener diameter should the link use?",
      "reason": "The accepted context does not specify the interface"
    }
  ]
}
```

### `propose_candidates`

Submit a concise set of design or planning alternatives.

### `submit_contract`

Submit a structured requirement, plan, CAD IR, repair, or review contract for validation.

```json
{
  "action": "submit_contract",
  "contract_type": "cad_ir_draft",
  "contract": {},
  "assumptions": [],
  "confidence": "medium"
}
```

### `request_validation`

Ask CadFlow to validate the current structured draft. The system, not the model, performs validation.

### `repair_contract`

Submit a revised structured contract based on validator feedback.

### `stop`

Stop safely with a typed reason:

- `completed`;
- `user_input_required`;
- `unsupported_capability`;
- `insufficient_context`;
- `validation_exhausted`;
- `budget_exhausted`;
- `provider_failure`.

## Episode State Model

Suggested states:

```text
created
  -> gathering_context
  -> proposing
  -> awaiting_validation
  -> repairing
  -> user_input_required
  -> completed
  -> safely_blocked
  -> failed
```

The agent chooses actions. The orchestrator owns state transitions.

## Episode Budgets

Every agentic episode must be bounded.

Suggested initial defaults for `create_part_ir`:

```json
{
  "max_steps": 8,
  "max_context_requests": 4,
  "max_contract_submissions": 3,
  "max_repair_attempts": 2,
  "max_tool_calls": 6,
  "timeout_seconds": 180
}
```

Budgets should be configurable by operation and provider.

When a budget is exhausted, preserve the best draft and validation evidence, then stop with `budget_exhausted`. Do not silently continue or export an unvalidated model.

## Checkpoint Contracts

### Requirement Checkpoint

Accepted result:

- structured active requirement;
- visible assumptions;
- unresolved questions either answered or explicitly accepted;
- user can review or override.

Internal agent loop may:

- reinterpret the prompt;
- request prior user constraints;
- ask clarification questions;
- revise the draft.

### Planning Checkpoint

Accepted result:

- one or more candidate plans;
- concise trade-offs;
- selected route or user decision request;
- assembly candidate/reference distinction when applicable.

Internal agent loop may:

- request active requirement context;
- generate alternatives;
- compare manufacturability and capability boundaries;
- replan after user review.

### Part Selection Checkpoint

Accepted result:

- selected part intent;
- preserved assembly context;
- explicit user or agent selection rationale;
- downstream stale semantics when selection changes.

### CAD IR Checkpoint

Accepted result:

- preserved source intent;
- structured CAD IR draft;
- assumptions and normalization trace;
- validator result;
- either validated `input_ir.json` or a typed safe block.

Internal agent loop may:

- request interface and dimension context;
- propose generic geometry families;
- submit multiple drafts;
- repair schema or geometry issues;
- ask the user for missing dimensions.

### Result Checkpoint

Accepted result:

- deterministic execution report;
- generated products, when successful;
- limitations;
- user review state;
- accepted result pointer at Work level.

## Artifact and Trace Model

Each agentic episode should produce compact, auditable artifacts.

Suggested files:

```text
agent_episode.json
context_manifest.json
agent_events.jsonl
contract_submissions/
  submission_001.json
  submission_002.json
validation_feedback/
  validation_001.json
agent_result.json
```

### `agent_episode.json`

```json
{
  "schema_version": 1,
  "episode_id": "...",
  "operation": "create_part_ir",
  "mode": "agentic",
  "status": "completed",
  "step_count": 5,
  "context_request_count": 2,
  "contract_submission_count": 2,
  "stop_reason": "validated_contract_accepted"
}
```

### `agent_events.jsonl`

Store concise events, not hidden reasoning:

```json
{"step": 1, "action": "request_context", "context_key": "assembly_plan", "reason": "Need interface context"}
{"step": 2, "action": "submit_contract", "contract_type": "cad_ir_draft", "summary": "Link-like part with two joint interfaces"}
{"step": 3, "observation": "validation_failed", "codes": ["hole_edge_margin_too_small"]}
{"step": 4, "action": "repair_contract", "summary": "Increased width and adjusted hole spacing"}
{"step": 5, "observation": "validation_passed"}
```

Do not persist raw provider chain-of-thought or unrestricted transcripts as a product artifact.

## Deterministic Mode vs Agentic Mode

### Deterministic Mode

Use for:

- unit and integration tests;
- CI;
- offline examples;
- reproducible smoke tests;
- provider failure fallback;
- known simple families when explicitly configured.

Characteristics:

- one-shot or small fixed logic;
- stable output;
- no provider network requirement;
- capability label: `deterministic_fallback`.

### Agentic Mode

Use for:

- real user tasks;
- unknown or ambiguous part intent;
- multi-candidate planning;
- context retrieval;
- validation-driven repair;
- user-question generation.

Characteristics:

- bounded episode;
- dynamic context requests;
- structured proposals only;
- explicit budgets;
- capability label: `agentic`.

### Routing

Initial routing should be explicit and conservative:

```text
configured deterministic mode -> deterministic adapter
configured agentic mode -> bounded agent episode
provider unavailable -> typed provider failure or explicit deterministic fallback
```

Do not silently report deterministic fallback output as provider-agent reasoning.

## UI and Workflow Implications

The primary Workflow graph continues to show checkpoints, not every episode step.

Selected Stage Detail should show:

- capability mode: deterministic or agentic;
- episode outcome;
- context used;
- concise agent decision summary;
- submitted contract;
- validator feedback;
- user decision required, when applicable.

Advanced / Diagnostics may show the compact episode event timeline.

The UI must not display hidden reasoning or raw provider payloads as the explanation.

Example:

```text
CAD IR Draft · Agentic episode

Context used:
- Reviewed Handoff
- Assembly Plan
- Previous validation feedback

Decision:
Classified upper_link as a link-like concept part with two joint interfaces.

Repair:
Increased width after hole-margin validation failed.

Result:
CAD IR validated after 2 submissions.
```

## Failure and Safety Semantics

An agentic episode may end safely without a model.

Typed outcomes:

### `user_input_required`

The agent found a specific missing decision that should not be guessed.

### `unsupported_capability`

The agent produced a coherent proposal, but no validated backend family or operation can execute it.

### `validation_exhausted`

The allowed repair attempts did not produce a valid contract.

### `budget_exhausted`

The bounded episode reached a configured limit.

### `provider_failure`

The provider failed or returned an invalid response.

In every safe block:

- preserve the best structured draft;
- preserve validation feedback;
- expose the next valid user or development choice;
- do not generate STEP/STL;
- do not substitute an unrelated template.

## Migration Plan

### Phase 0 — Architecture and contract tests

No product behavior change.

Add:

- episode schemas;
- context-envelope schema;
- allowlisted action schema;
- typed stop reasons;
- unit tests for budgets and invalid actions.

### Phase 1 — Context Broker and dry-run episode shell

Scope only `create_part_ir`.

The episode shell may initially use the deterministic adapter internally, but it must:

- build a compact context envelope;
- process semantic `request_context` actions;
- persist episode/context artifacts;
- submit the final CAD IR through existing validators;
- preserve current deterministic output compatibility.

Do not add new CAD families in this phase.

### Phase 2 — Provider-backed agentic `create_part_ir`

Add a provider implementation that can:

- request allowlisted context;
- submit a CAD IR draft;
- ask the user for missing dimensions;
- stop with typed outcomes.

The provider must not emit executable CadQuery/Python as the accepted product path.

### Phase 3 — Validation-driven CAD IR repair loop

Allow up to the configured repair budget:

```text
submit draft
  -> validate
  -> return structured feedback
  -> repair
  -> validate again
```

Keep deterministic `repair_ir(...)` available as a fallback or comparison baseline.

### Phase 4 — Agentic planning candidates

Extend bounded episodes to planning:

- multiple candidates;
- concise trade-offs;
- context requests;
- user selection checkpoint.

Do not remove existing deterministic planning tests.

### Phase 5 — Requirement clarification loop

Extend to requirement interpretation only after the episode and context contracts are stable.

## Recommended Next Implementation Step

Implement Phase 0 and the minimal Phase 1 shell only.

The first development task should not attempt to make every AgentAdapter method agentic. It should prove one vertical slice:

```text
reviewed_part_handoff
  -> create_part_ir episode
  -> compact context envelope
  -> optional semantic context request
  -> CAD IR contract submission
  -> existing validation
  -> episode artifacts
  -> existing deterministic CAD execution or safe block
```

Success criteria:

- existing deterministic Golden examples remain reproducible;
- no new CAD family is added;
- the same validated CAD IR contract reaches the existing pipeline;
- episode steps are bounded;
- context provenance is recorded;
- invalid or unknown actions are rejected;
- raw provider chain-of-thought is not persisted;
- the system can later replace the deterministic internal proposer with a provider-backed proposer without changing the CAD pipeline.

## Acceptance Tests

### Episode boundary

- unknown action is rejected;
- step budget is enforced;
- context-request budget is enforced;
- contract-submission budget is enforced;
- timeout produces a typed stop reason;
- an unvalidated contract cannot execute CAD.

### Context Broker

- only accepted active-lineage artifacts are used by default;
- superseded Run artifacts are not silently supplied;
- semantic context keys resolve to provenance-bearing summaries;
- arbitrary paths are rejected;
- large artifacts are summarized or truncated safely.

### Deterministic compatibility

- deterministic adapter output remains stable for existing fixtures;
- Golden contract mode remains fast;
- Full Golden mode still reaches the existing CadQuery pipeline;
- capability mode is visible in artifacts and reports.

### Agentic readiness

- episode orchestrator can process `request_context` and `submit_contract` without depending on a specific provider;
- provider output must validate against the action schema;
- concise events and contract submissions are persisted;
- no raw chain-of-thought artifact is required.

## Non-Goals

This architecture does not authorize:

- arbitrary shell or Python execution by a provider;
- provider-generated CadQuery as the primary accepted output;
- bypassing CAD IR validation;
- bypassing Work/Run lineage;
- unbounded autonomous loops;
- automatic approval of generated results;
- hidden modification of accepted user inputs;
- loading the entire repository or workspace into every model call;
- replacing deterministic tests with nondeterministic provider tests;
- claiming engineering strength, fit, or motion validation without the corresponding deterministic checks.

## Architecture Invariants

The following must remain true throughout implementation:

1. Run artifacts are immutable; Work pointers may identify the accepted active lineage.
2. Original user and agent artifacts are preserved; overrides and revisions are versioned.
3. Only validated structured contracts may reach deterministic CAD execution.
4. The agent may request context but may not browse arbitrary paths.
5. The agent may propose repairs but may not bypass validator feedback.
6. A missing template is not a product-level terminal reason before an agent attempt.
7. A deterministic fallback is labeled as deterministic fallback.
8. The Workflow graph represents trusted checkpoints, not hidden model reasoning.
9. User approval remains an explicit checkpoint.
10. Safety blocks preserve evidence and provide a valid next decision.

## Summary

CadFlow should evolve from one-shot structured agent calls toward bounded agent episodes.

The intended balance is:

```text
more freedom:
  interpretation, context retrieval, alternatives, repair, replan

strict control:
  actions, budgets, validation, execution, persistence, lineage, approval
```

The product workflow remains essential, but its role is to define trusted checkpoints and user decisions. It should not limit the agent to a prewritten reasoning path.
