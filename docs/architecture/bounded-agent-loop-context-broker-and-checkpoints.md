# Bounded Agent Episodes and Context Broker

## Authority and scope

This document defines how CadFlow allows agent reasoning inside canonical checkpoint transitions.

The checkpoint order and stage responsibilities remain owned by:

- `cadflow-canonical-product-architecture.md`

Logical agents, skills, and knowledge ownership are defined by:

- `agent-skill-knowledge.md`

## Executive rule

Workflow is a set of trusted checkpoints and user decisions, not a script for every reasoning step.

CadFlow should constrain side effects, accepted contracts, tools, budgets, persistence, and approval while allowing bounded freedom in:

- interpretation;
- context requests;
- candidate comparison;
- structured proposal;
- validator-driven repair;
- asking the user;
- safe stopping.

    accepted checkpoint input
      -> bounded agent episode
      -> structured proposal
      -> local validation
      -> accepted checkpoint output or typed safe block

## Runtime layers

    Work Workflow
      -> Episode Orchestrator
           -> Context Broker
           -> skill/proposer or provider adapter
           -> Tool Broker
           -> contract validators
      -> deterministic pipeline
      -> immutable Run artifacts and Work pointers

The orchestrator owns state transitions and budgets. The agent chooses from allowlisted actions. The deterministic pipeline owns execution.

## Episode contract

Suggested provider-independent interface:

    run_agent_episode(
        objective,
        context_envelope,
        capabilities,
        budget,
    ) -> AgentEpisodeResult

Core contracts:

- `AgentObjective` — operation and product-scoped goal;
- `ContextEnvelope` — compact initial accepted context;
- `AgentCapabilities` — allowlisted actions, tools, and context keys;
- `EpisodeBudget` — limits on steps, context, submissions, repairs, tools, and time;
- `AgentAction` — one typed agent choice;
- `AgentEpisodeResult` — accepted submission or typed stop outcome.

## Allowlisted actions

Initial action vocabulary:

- `request_context` — request one semantic context item;
- `ask_user` — stop at a structured user-decision checkpoint;
- `propose_candidates` — provide concise alternatives where the skill allows it;
- `submit_contract` — submit a structured artifact proposal;
- `request_validation` — ask the system to validate the current proposal;
- `repair_contract` — submit a revision based on structured observations;
- `stop` — end with a typed reason.

Unknown actions are rejected.

Agents cannot directly:

- write arbitrary files;
- browse arbitrary paths;
- execute shell, Python, or CadQuery;
- mutate Work pointers;
- approve results;
- bypass validators;
- declare STEP/STL generation from text alone.

## Episode states

    created
      -> gathering_context
      -> proposing
      -> awaiting_validation
      -> repairing
      -> user_input_required
      -> completed
      -> safely_blocked
      -> failed

The system records concise actions and observations. It does not require or persist private chain-of-thought.

## Context Broker

The Context Broker selects dynamic Work/Run context. It is not the static knowledge selector and is not a filesystem browser.

Responsibilities:

- build a compact initial envelope;
- resolve accepted active-lineage artifacts;
- avoid superseded or unrelated Runs by default;
- provide semantic context keys instead of paths;
- summarize large artifacts;
- attach source Work, Run, Stage, and source type;
- enforce context-request budgets;
- reject arbitrary paths and private data.

Initial semantic keys may include:

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

Example context item:

    {
      "context_key": "assembly_plan",
      "source_work_id": "...",
      "source_run_id": "...",
      "source_stage_id": "assembly_plan",
      "source_type": "accepted_active_lineage",
      "summary": {}
    }

Static skill knowledge is selected separately according to `agent-skill-knowledge.md`.

## Observations and repair

System observations are distinct from agent actions.

Examples:

    {"event_type":"agent_action","action":"submit_contract"}

    {
      "event_type":"system_observation",
      "observation":"validation_failed",
      "codes":["hole_edge_margin_too_small"],
      "repairable":true
    }

After an observation, the agent may repair, ask the user, request context, or stop. The orchestrator must not fabricate an agent decision.

## Budgets

Every episode is bounded by operation-specific configuration.

A `create_part_ir` baseline may limit:

- total steps;
- context requests;
- contract submissions;
- repair attempts;
- tool calls;
- wall-clock time.

Budget exhaustion preserves the best structured draft and observations, then stops with `budget_exhausted`. Unvalidated contracts never execute CAD.

## Typed stop reasons

Supported outcomes include:

- `completed`;
- `user_input_required`;
- `unsupported_capability`;
- `insufficient_context`;
- `validation_exhausted`;
- `budget_exhausted`;
- `provider_failure`.

A safe block preserves evidence and exposes a valid next user or development decision.

## Episode artifacts

Each episode should remain auditable without storing raw reasoning.

Suggested artifacts:

    agent_episode.json
    context_manifest.json
    agent_events.jsonl
    contract_submissions/
    validation_feedback/
    agent_result.json

Record:

- objective and capability mode;
- Work/Run/part lineage;
- selected skill and knowledge ids;
- context requested and provenance;
- concise action summaries;
- contract submissions;
- validator observations;
- repair summaries;
- accepted submission id;
- stop reason and budget use.

Do not store raw chain-of-thought, secrets, arbitrary provider payloads, or unrestricted transcripts.

## Deterministic and agentic modes

### Deterministic

Use for:

- CI and tests;
- reproducible Golden examples;
- offline operation;
- explicit fallback;
- stable regression baselines.

Label it clearly as deterministic fallback or deterministic mode.

### Agentic

Use for:

- ambiguous or unknown real tasks;
- context retrieval;
- candidate comparison;
- structured user questions;
- validation-driven repair.

Both modes submit the same structured contracts to the same validators and deterministic execution boundary.

A provider failure may produce a typed failure or an explicitly configured deterministic fallback. It must not be silently represented as agentic reasoning.

## Current implementation

Implemented for `create_part_ir`:

- provider-independent episode contracts;
- semantic Context Broker;
- allowlisted actions and typed stop reasons;
- step/context/submission/repair budgets;
- dynamic scripted sequences in tests;
- validator observations returned to the proposer;
- episode lineage and audit artifacts;
- deterministic proposer compatibility.

Not yet usable as product capability:

- provider-backed agentic `create_part_ir`;
- production knowledge registry and typed skill manifest;
- agentic Planning and Requirement episodes;
- fully accepted multi-part or assembly loops.

## Next architecture step

Before provider-backed `create_part_ir` is promoted from prototype:

1. finish Workflow Cockpit manual usability acceptance;
2. implement the typed skill/knowledge registry described in `agent-skill-knowledge.md`;
3. connect one provider-backed proposer supporting only context request, structured contract submission, ask-user, repair, and stop;
4. preserve existing deterministic Golden behavior and validators;
5. expose capability mode and typed failure clearly in artifacts and UI.

Do not mix this step with new CAD families, full assembly generation, or arbitrary code execution.

## Tests

Protect:

- unknown action rejection;
- all budgets and timeout;
- active-lineage context selection;
- superseded context exclusion;
- arbitrary-path rejection;
- context affecting subsequent proposer behavior;
- system observation versus agent action separation;
- invalid contract never executing CAD;
- typed stop reasons;
- episode lineage and accepted submission;
- selected skill/knowledge ids;
- no raw chain-of-thought artifact;
- deterministic Golden compatibility.

## Invariants

1. Agents operate inside canonical checkpoint transitions.
2. Orchestrator controls state and budgets.
3. Context Broker supplies dynamic accepted context only.
4. Static knowledge follows declared skill ownership.
5. Agents propose; local validators and deterministic services decide what executes.
6. Run artifacts remain immutable and auditable.
7. Human approval remains explicit.
8. Failure preserves evidence and never fabricates CAD success.