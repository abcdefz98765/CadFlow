# Agent, Skill, Tool, and Knowledge Architecture

## Authority

This document defines CadFlow's logical Agent roles, skill contracts, tool
authority, and knowledge ownership.

It specializes:

- `cadflow-canonical-product-architecture.md`
- `bounded-agent-loop-context-broker-and-checkpoints.md`
- `../workflow_contract.md`

## Core model

CadFlow separates:

- **Agent role** — the design responsibility active for an objective;
- **Skill** — a versioned behavior and capability contract;
- **Knowledge** — selected static engineering reference material;
- **Runtime context** — accepted Work state and current Run observations;
- **Tool** — an allowlisted capability brokered by CadFlow;
- **Provider** — a replaceable model implementation;
- **Validator** — local authority over contracts, geometry, and claims.

A provider is not the architecture. A capable provider may perform several
logical roles, but every episode still declares the active skill, context,
tools, budgets, and output contract.

## Logical Agent roles

### Intent Agent

Owns:

- understanding the requested product or change;
- visible assumptions and focused questions;
- assurance-mode recommendation;
- deciding whether design can begin.

Does not own final geometry or acceptance.

### Design Agent

Owns:

- design strategy and alternatives;
- decomposition into Part Jobs and optional Assembly Job;
- parameters, datums, interfaces, manufacturing intent, and validation targets;
- choosing between structured geometry and sandboxed model-program candidates.

This is the primary creative role.

### Geometry Agent

Owns:

- structured feature/assembly graph proposals;
- model-program proposals where the selected operation permits them;
- candidate comparison;
- validator-driven repair;
- requesting execution and interpreting observations.

It does not own unrestricted host execution or user acceptance.

### Assembly Agent

Owns:

- assembly design using exact accepted part results;
- placements, joints, mates, fasteners, contacts, clearances, and degrees of
  freedom;
- assembly candidate repair from structured observations.

It does not silently generate or accept missing parts.

### Evaluation Agent

Owns:

- explaining geometry, execution, assembly, and drawing evidence;
- distinguishing verified, assumed, unverified, unsupported, and not requested;
- proposing recovery or additional checks.

Local validators remain the authority over measured facts.

### Revision Agent

Owns:

- change-intent extraction;
- structured contract, parameter, model-program, or assembly patch proposals;
- parent/child comparison;
- deciding when a revision requires user input or a new strategy.

It never overwrites the parent or replaces the accepted result automatically.

### Deliverable Agent

Owns:

- proposing a deliverable package from accepted results;
- drawing-view and annotation intent;
- BOM and product-document summaries;
- identifying missing or unsupported deliverables.

It may not promote unaccepted results or claim unverified drawing content.

## Skill contract

Each skill declares:

- skill id and version;
- logical role;
- supported user phase and internal checkpoints;
- accepted objectives and input artifact types;
- allowed Agent actions;
- allowed semantic context keys;
- allowed tools and execution profiles;
- structured outputs;
- shared and private knowledge ids;
- budgets and stop reasons;
- prohibited side effects;
- validation and publication conditions.

Skills describe capability, not a fixed end-to-end workflow. They do not
duplicate the entire product architecture.

## Required initial skills

Target skills:

- `intent`;
- `design`;
- `geometry_contract`;
- `model_program`;
- `part_evaluation`;
- `assembly`;
- `revision`;
- `deliverables`.

Current legacy skills map as follows:

- `requirement` -> `intent`;
- `planning` -> `design`;
- `cad_ir` -> early `geometry_contract`;
- `part_modeling` -> Tool Broker execution plus `part_evaluation`;
- `review` -> `part_evaluation`;
- `revision` remains revision;
- `assembly` expands from planning references to real Assembly Job work.

Migration should preserve legacy skill ids only as versioned compatibility
aliases.

## Tool authority

Tools are CadFlow-owned. Skills may request them; providers never receive their
authority directly.

Initial tool categories:

- semantic context retrieval;
- structured contract validation;
- isolated CAD model-program execution;
- deterministic feature-graph execution;
- geometry inspection and measurement;
- STEP/STL/native export;
- assembly execution and validation;
- drawing generation;
- controlled artifact comparison.

Every tool declares:

- input and output schema;
- permitted skill ids;
- execution profile;
- filesystem, network, and process policy;
- resource limits;
- persisted evidence;
- failure codes.

## Sandboxed model-program skill

The `model_program` skill permits Agent-generated CAD source only as an
untrusted candidate.

Allowed:

- use an allowlisted CAD API;
- create or patch a candidate model in a dedicated directory;
- request isolated execution;
- receive structured execution and geometry observations;
- repair and retry within budget.

Prohibited:

- arbitrary shell or subprocess control;
- network access by default;
- reading secrets or environment configuration;
- writing outside candidate storage;
- installing dependencies dynamically;
- mutating Work pointers;
- declaring its own result trusted.

The local Tool Broker and validators decide publication.

The first selected API contract is `cadquery_v1` with entrypoint
`build_model(parameters)`. Its current implementation is static policy
validation only: AST parsing checks allowlisted imports/calls and prohibited
authority without retaining or executing source. This does not register the
runtime skill or satisfy the isolated-execution requirement.

## Knowledge layers

### Layer 0 — Global policy

Repository ownership:

- `policies/`

Contains small cross-Agent invariants such as lineage, approval, units, privacy,
execution safety, and claim vocabulary.

### Layer 1 — Shared engineering vocabulary

Repository ownership:

- top-level `knowledge/`;
- canonical contracts when the vocabulary is architectural.

Examples:

- coordinate frames and units;
- feature graph vocabulary;
- interface and assembly vocabulary;
- verification-state vocabulary.

### Layer 2 — Skill-private knowledge

Repository ownership:

- `skills/<skill>/knowledge/`

Examples:

- intent elicitation;
- design decomposition patterns;
- feature-graph construction;
- CadQuery/build123d modeling patterns;
- assembly constraint patterns;
- drawing-view rules;
- revision strategies.

### Layer 3 — Work-scoped accepted context

Dynamic context such as:

- active intent;
- accepted constraints;
- Part Jobs and interfaces;
- accepted part results;
- Assembly Job inputs;
- user decisions.

This is runtime context, not static knowledge.

### Layer 4 — Run and episode observations

Dynamic attempt-local evidence such as:

- previous candidates;
- validator codes;
- execution failures;
- geometry measurements;
- repair history;
- budget use.

Observations are not promoted to global knowledge automatically.

### Layer 5 — Provider-specific operation guidance

Formatting, timeout, retry, and response-envelope behavior belongs to provider
adapters. Provider quirks must not redefine skill semantics.

## Context assembly

Default context is minimal:

```text
global policy
  -> active skill contract
  -> selected shared knowledge
  -> selected private knowledge
  -> compact accepted Work context
  -> current Run observations
  -> sanitized user payload
```

Agents request semantic items, not arbitrary paths.

Every supplied context item records:

- context key;
- source Work and Run;
- Part Job or Assembly Job when applicable;
- source checkpoint and trust role;
- compact summary;
- content budget.

## Runtime registry

One typed registry must be authoritative for:

- skill ids and versions;
- operation and role mapping;
- actions and tools;
- context keys;
- knowledge ownership;
- artifact contracts;
- execution profiles;
- budgets and stop reasons.

Runtime prompt text should be compiled from this registry and source skill
documents. Inline duplicated skill guides in provider adapters are migration
debt, not an acceptable second authority.

The registry is an enabling slice of the Agentic vertical milestone. It must not
become a long standalone governance project that delays the first real Design
Episode.

## Provider boundary

Provider output may include:

- typed Agent actions;
- structured design contracts;
- untrusted model-program source;
- structured questions;
- candidate summaries and repair proposals.

Provider output may not directly:

- mutate Work or Run state;
- execute host tools;
- approve a result;
- publish deliverables;
- fabricate validator facts;
- access undeclared context or tools.

## Trace and privacy

Persist:

- selected skill, knowledge, actions, and tools;
- compact context provenance;
- candidate source or structured contract;
- system observations;
- budgets and stop reason.

Do not persist:

- private chain-of-thought;
- secrets;
- unrestricted provider payloads;
- arbitrary repository snapshots;
- raw environment or credential data.

## Current implementation gap

Current code provides:

- one broad `AgentAdapter`;
- deterministic and JSON-contract adapters;
- static inline skill/knowledge summaries;
- a bounded episode state machine;
- a deterministic one-shot proposer around `create_part_ir`;
- deterministic template-backed CAD execution.
- a typed `design_part` v0.1 runtime skill definition;
- a provider-selected structured-contract episode preview in which the
  provider may request semantic context, create or patch a candidate, react to
  validator observations, ask the user, or stop;
- context provenance, trust roles, Work filtering, and byte/request budgets for
  that preview;
- a typed CadFlow Tool Broker catalog whose tool definitions declare skill
  authorization, input/output contracts, execution profile, side-effect
  policies, limits, persisted evidence, and failure codes;
- Broker-owned invocation of the local legacy CAD IR compatibility validator;
- a Windows model-program capability gate that enumerates required controls and
  returns `sandbox_unavailable` without writing source or starting a process;
- a typed `AgentDesignPort` used by `WorkOrchestrator` to route an owned Part
  Job attempt into the provider-selected validation episode, persist append-only
  Run evidence, and register typed candidate/observation/diagnostic references;
- a versioned CadQuery v1 source policy and Broker-owned AST-only validator that
  returns source hash, metrics, and sanitized violations without source
  retention, imports, bytecode compilation, execution, or side effects.

It does not yet provide:

- product-integrated provider-selected design-to-execution and reviewable
  publication;
- an enforceable Windows sandbox or any provider model-program execution;
- feature-graph CAD IR;
- Agentic assembly or deliverable episodes.

The product-routed preview validates only the legacy structured CAD IR
compatibility contract. The separate model-program static validator is not
registered as an Episode action. Its execution tool entry is unavailable
capability metadata, not execution authority. It has no CAD execution or
publication tool and is not production-usable Agentic CAD design.

No current deterministic fallback may be presented as these target
capabilities.

## Tests

Tests must prove:

- every episode selects one declared skill version;
- actions, tools, and context remain inside declared capability;
- another skill's private knowledge cannot be loaded;
- provider source cannot bypass the Tool Broker;
- sandbox policy violations fail closed;
- invalid or failed candidates never become reviewable products;
- validator observations are distinct from Agent decisions;
- Agent behavior can branch after observations;
- acceptance remains an explicit Work action;
- adding a provider does not change trust or lineage semantics.
