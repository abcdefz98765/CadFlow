# Agent, Skill, and Knowledge Architecture

## Authority

This document defines CadFlow's logical agents, skill ownership, and knowledge layering.

It specializes the product checkpoints in:

- `cadflow-canonical-product-architecture.md`

It does not allow agents to reorder or bypass that workflow.

## Core model

CadFlow separates five concepts:

- **Agent role** — the logical responsibility active for one checkpoint transition.
- **Skill** — the behavior contract for that role: purpose, inputs, outputs, tools, stop conditions, and prohibitions.
- **Knowledge** — selected reference material available to a skill.
- **Runtime context** — accepted Work/Run artifacts and observations for the current episode.
- **Adapter/provider** — the replaceable implementation used to produce structured agent actions or contracts.

A provider model is not itself the architecture. One adapter may implement several logical agent roles, but each operation must still use the correct skill, knowledge scope, contract, and context.

    checkpoint transition
      -> logical agent role
      -> one skill contract
      -> allowed shared and private knowledge
      -> compact runtime context
      -> structured action or artifact proposal
      -> local validation and persistence

## Logical agent roles

### Requirement Agent

Checkpoint:

- Prompt -> Requirement / Clarification.

Owns:

- interpreting user intent;
- structured requirement fields;
- assumptions, missing information, and focused questions;
- proceed, clarify, or safe-block recommendation.

Does not own:

- final design decomposition;
- candidate selection;
- CAD IR or geometry execution.

Primary operations:

- `parse_requirement`;
- structured clarification support.

### Planning Agent

Checkpoint:

- accepted Requirement -> Planning / Design Brief -> Assembly Plan candidates.

Owns:

- engineering route and scope;
- design strategy and alternatives;
- functional decomposition;
- interfaces, dependencies, datums, and risk summaries;
- candidate and reference-component planning.

Does not own:

- requirement elicitation;
- detailed CAD IR synthesis;
- backend-specific geometry execution.

Primary operations:

- `create_plan`;
- future bounded planning-candidate episode.

### CAD IR Agent

Checkpoint:

- Reviewed Handoff -> CAD IR Draft.

Owns:

- converting one accepted part intent into backend-neutral structured CAD IR;
- requesting allowlisted context;
- exposing assumptions and uncertainty;
- repairing a draft from structured validator feedback.

Does not own:

- arbitrary Python, shell, or CadQuery execution;
- user approval;
- assembly completion claims.

Primary operations:

- `create_part_ir`;
- `repair_contract` or constrained `suggest_repair`.

### Part Modeling Executor / Agent Loop

Checkpoint:

- validated CAD IR -> deterministic part artifacts.

Owns:

- backend capability mapping;
- deterministic geometry generation;
- export and geometry checks;
- structured execution observations;
- implementation-level repair within validated intent.

This role is primarily a CadFlow-owned deterministic executor. A provider may advise through structured contracts but cannot inject executable code.

### Assembly Agent, future

Checkpoint:

- multiple accepted Part Jobs -> assembly placement, constraints, and assembly validation.

Owns:

- relationships between already-defined parts;
- placements, contacts, clearances, degrees of freedom, and assembly-level checks.

Does not own:

- initial product decomposition, which belongs to Planning / Assembly Plan;
- single-part geometry generation;
- unsupported claims of full assembly generation.

Current product status:

- Assembly Plan exists as a planning artifact.
- Full assembly generation and constraint solving are not yet usable capabilities.

### Review Agent

Checkpoint:

- structured reports and evidence -> concise review explanation.

Review has three distinct scopes:

- Part Request Review — is the modeling request ready?
- Part Result Review — does one result match the Reviewed Handoff?
- Work-level Workflow Review — what is the current product state and valid next action?

The Review Agent may explain evidence and limitations. User acceptance remains an explicit human action.

Primary operation:

- `explain_review`;
- future scoped review operations.

### Revision Agent

Checkpoint:

- accepted parent result plus user change request -> structured revision child Run.

Owns:

- change-intent extraction;
- revision planning;
- structured patch proposal;
- identifying when a requested change cannot be represented safely.

Does not overwrite parent artifacts or directly edit external CAD without an explicit supported path.

Primary operations:

- `parse_revision_request`;
- `create_revision_plan`.

## Skill contract

A skill is a versioned stage behavior contract, not an informal prompt fragment.

Every `skills/<skill>/SKILL.md` should define:

- skill id and owned logical agent role;
- canonical checkpoint;
- purpose and non-goals;
- accepted input artifact types;
- output or action contracts;
- allowed tools and context requests;
- shared knowledge scopes;
- private skill knowledge scopes;
- missing-information behavior;
- validation and stop conditions;
- prohibited side effects;
- user handoff and next checkpoint.

Skills must not duplicate the entire product workflow. They reference the canonical architecture and describe only their owned responsibility.

## Knowledge layers

Knowledge is not the same as Work context. Static knowledge should be layered and selected explicitly.

### Layer 0 — Global invariants and policy

Available to every agent operation when relevant.

Examples:

- structured-output and privacy rules;
- units and naming conventions;
- CAD execution safety boundary;
- immutable Run and explicit approval rules;
- check-level vocabulary;
- output and path-safety policy.

Repository ownership:

- `policies/`;
- compact global rules compiled by provider context assembly.

This layer must stay small.

### Layer 1 — Shared workflow and contract knowledge

Shared by adjacent skills that must agree on handoffs.

Examples:

- requirement contract vocabulary used by Requirement and Planning;
- Assembly Plan and interface vocabulary used by Planning, CAD IR, and future Assembly;
- CAD IR schema vocabulary used by CAD IR, Part Modeling, Repair, and Review;
- review-state vocabulary used by Review, Workflow, and Rework.

Repository ownership:

- canonical architecture and artifact-contract documents;
- top-level `knowledge/` only when the material is genuinely cross-skill.

A shared rule has one source of truth. Do not copy independent versions into multiple skill directories.

### Layer 2 — Skill-private knowledge

Owned by exactly one skill and loaded only for that skill's operations.

Examples:

- Requirement: elicitation and missing-information heuristics;
- Planning: decomposition patterns and interface-planning heuristics;
- CAD IR: geometry-family normalization and CAD IR construction guidance;
- Part Modeling: backend capabilities, feature implementation, and export checks;
- Assembly: placement, constraint, clearance, and degree-of-freedom rules;
- Review: evidence interpretation and check presentation;
- Revision: supported patch paths and change-intent patterns.

Repository ownership:

- `skills/<skill>/knowledge/`.

When private knowledge becomes necessary to more than one skill, promote it to a shared source rather than duplicating it.

### Layer 3 — Work-scoped accepted context

Dynamic product context selected by the Context Broker.

Examples:

- active Requirement;
- accepted Planning or Assembly Plan;
- selected candidate;
- Reviewed Handoff;
- accepted part result;
- user Stage Review.

This is not static knowledge and must not be stored under `knowledge/`.

It is selected from the active Work lineage with provenance.

### Layer 4 — Run- and episode-scoped observations

Dynamic observations available only to the current attempt.

Examples:

- previous CAD IR submissions;
- validator codes and field errors;
- execution failure summaries;
- repair attempts;
- episode budgets and stop reason.

These remain Run artifacts and episode observations. They are not promoted to global knowledge automatically.

### Layer 5 — Provider-specific operational guidance

Provider formatting, timeout, retry, and response-envelope behavior belong to adapter/client configuration.

Provider quirks must not redefine product contracts or skill knowledge. A provider-specific workaround should be isolated and removable.

## Knowledge access rules

- Default context is minimal.
- An operation receives only its skill guide, contract guide, selected shared knowledge, selected private knowledge, and compact runtime context.
- No operation receives the entire repository or every skill by default.
- Arbitrary path access is prohibited.
- Every dynamic context item records source Work, Run, Stage, and source type.
- Knowledge ids included in a provider request are recorded in a privacy-safe trace summary.
- Raw provider chain-of-thought is neither required nor persisted.
- A knowledge source cannot grant execution authority; only local policy and validation can do that.

## Repository layout

    policies/
      global cross-agent invariants

    knowledge/
      README.md
      genuinely shared cross-skill references only

    skills/
      README.md
      requirement/
        SKILL.md
        knowledge/
      planning/
        SKILL.md
        knowledge/
      cad_ir/
        SKILL.md
        knowledge/
      part_modeling/
        SKILL.md
        knowledge/
      assembly/
        SKILL.md
        knowledge/
      review/
        SKILL.md
        knowledge/
      revision/
        SKILL.md
        knowledge/

    src/ai_native_cad/agents/
      adapter and provider boundaries
      bounded episode orchestration
      context and knowledge selection
      validation

## Runtime context assembly

Provider or proposer context is assembled in this order:

    global minimal rules
      -> skill guide
      -> operation-specific contract guide
      -> selected shared knowledge summaries
      -> selected skill-private knowledge summaries
      -> compact Work context envelope
      -> current Run observations
      -> sanitized user or upstream artifact payload

The Context Broker resolves dynamic context. A knowledge selector resolves static knowledge. These responsibilities should remain distinct even if they share implementation helpers.

## Current implementation

Current code provides:

- one `AgentAdapter` protocol with stage-specific operations;
- deterministic and JSON-contract adapter implementations;
- static operation-to-stage mapping in `provider_context.py`;
- compact static knowledge summaries;
- a bounded `create_part_ir` episode and semantic Context Broker.

This is a valid bootstrap, but it has limitations:

- logical roles are implemented behind one broad adapter interface;
- skill guides are partly duplicated as inline strings in `provider_context.py`;
- knowledge source paths are descriptive and are not yet a loaded registry;
- `create_part_ir` has a bounded episode, while other operations remain mostly one-shot;
- shared versus skill-private knowledge is not yet enforced by a typed registry;
- missing skill files or stale template-centric descriptions can diverge from runtime prompts.

## Required next consolidation

Before provider-backed agentic CAD is treated as usable:

1. Introduce a typed skill registry or compiled manifest containing:
   - skill id;
   - operations;
   - contract types;
   - shared knowledge ids;
   - private knowledge ids;
   - allowed context keys;
   - allowed tools and stop reasons.
2. Make one source authoritative for each skill guide; runtime prompt text should be compiled from it or tested against it.
3. Add a knowledge registry with ownership and layer metadata.
4. Reject an operation requesting knowledge outside its declared scopes.
5. Add provenance and selected knowledge ids to episode/provider traces.
6. Keep provider-specific formatting separate from skill semantics.

This consolidation is architecture work. It should not be mixed with adding new CAD families or UI features.

## Tests

Tests should prove:

- every adapter operation maps to one declared skill;
- every skill maps to canonical checkpoints and accepted artifact types;
- missing skill definitions fail fast;
- shared and private knowledge ids are unique and owned;
- operations cannot access another skill's private knowledge;
- only allowlisted dynamic context keys are supplied;
- provider-visible requests contain no secrets, absolute paths, raw logs, or transcripts;
- malformed structured output cannot reach deterministic execution;
- deterministic fallback is clearly labeled;
- adding a provider does not change the canonical workflow.

## Invariants

1. Agents operate inside checkpoint transitions; they do not redefine the workflow.
2. Skills own behavior, not persistent product state.
3. Static knowledge never substitutes for accepted Work context.
4. Work and Run artifacts never become global knowledge automatically.
5. Private skill knowledge is not visible to unrelated agents.
6. Shared knowledge has one source of truth.
7. Provider adapters are replaceable and have no execution authority.
8. Only validated structured contracts reach deterministic CAD execution.
9. Human approval remains explicit.
10. The UI shows product conclusions, not raw knowledge or provider internals.