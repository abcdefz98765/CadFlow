# Agent Implementation Start Here

Status date: 2026-08-01.

This is the execution entry point after the documentation correction. It does
not replace the PRD, architecture, roadmap, or task board.

## Read in order

1. `../../AGENTS.md`
2. `../FINAL-PRD.md`
3. `../architecture/cadflow-canonical-product-architecture.md`
4. `../status/current-product-readiness.md`
5. `../roadmap/milestones.md`
6. `task-board.md`
7. the specialized architecture, skill, policy, and knowledge files named by
   the selected task.

When documents appear to conflict, stop and resolve the authority rather than
choosing the easiest implementation.

## Current execution scope

M1 runtime consolidation and domain foundations passed acceptance on
2026-07-27. M2 is now in progress. Its first internal package implements the
`design_part` typed registry and provider-selected structured-contract preview;
its second package adds Broker-owned structured validation and an explicit
fail-closed Windows model-program capability gate; its third package routes an
owned Part Job attempt through `WorkOrchestrator` for validation and evidence
registration only; its fourth package selects CadQuery v1 and adds AST-only
source-policy validation. Runtime model-program actions, an enforceable sandbox
worker, design-to-execution, publication, and benchmark acceptance remain open.

In particular, do not begin later work by:

- polishing the legacy Workflow Console;
- adding another product-specific `part_type`;
- building a general skill-registry platform;
- exposing Agent-generated source without an enforceable sandbox;
- claiming Assembly Job, drawings, or Agentic design before implementation and
  verification exist.

## M1 first work package

Status: completed on 2026-07-25. M1 then passed implementation and usage
acceptance on 2026-07-27. The accepted decision, inventory, record contracts,
orchestrator, compatibility port/projector, and verification are linked from
the M1 task board. Do not reinterpret that acceptance as permission to add the
M2 sandbox or Agentic design path.

Produce one reviewable change set that:

1. records an architecture decision for the single product orchestrator;
2. inventories every current create, prompt, reviewed-part, revision, text, and
   CAD IR entry point;
3. classifies each entry point as target product, compatibility, evaluation, or
   removable;
4. proposes schema-versioned Work, Part Job attempt, Assembly Job, Deliverable
   Package, and artifact-reference records;
5. identifies the compatibility projection required for existing Runs;
6. adds contract tests for attempt history, accepted-pointer separation,
   immutable Run evidence, and manifest-based product state.

Do not combine this work package with the Agent sandbox or new Workbench UI.

## Completed M2 internal packages

The first internal package was deliberately narrower than the full M2 gate:

1. one `design_part` skill version;
2. one typed registry rather than a general plugin platform;
3. provider-selected semantic context and structured-contract actions;
4. local validation observations and provider-selected patch/question/stop;
5. request, byte, submission, repair, time, and step budgets;
6. concise provenance-safe episode evidence;
7. no CAD/model-program execution or product publication.

The second internal package adds:

1. one typed CadFlow Tool Broker catalog;
2. Broker-owned local structured-contract validation;
3. declared filesystem, network, process, resource, evidence, and failure
   policies per tool;
4. an explicit Windows model-program capability gate that enumerates missing
   controls;
5. a `sandbox_unavailable` safe block before source write, candidate-directory
   creation, or process startup.

The third internal package adds:

1. a typed `AgentDesignPort` and validation-only `WorkOrchestrator` command;
2. Part Job attempt ownership checks before provider invocation;
3. append-only episode evidence below the owning Run;
4. idempotent request replay and conflicting request-id rejection;
5. typed candidate, observation, or diagnostic Work artifact references;
6. explicit preservation of lineage, acceptance, Assembly, Deliverable, Part
   Job, and Run state.

The fourth internal package adds:

1. `cadquery_v1` as the selected initial model-program API;
2. a fixed `build_model(parameters)` source contract;
3. versioned import, call, syntax, entrypoint, source-size, and AST-size policy;
4. Broker-owned AST-only validation with source hash and sanitized codes;
5. explicit proof that a static pass does not enable execution or create a
   candidate directory.

This is not a sandbox implementation or a design-to-execution path. The next
package should define the enforceable Windows worker/profile and evidence
protocol, remaining fail closed until every required isolation control is
independently verified. Do not route provider source into the existing host
CadQuery subprocess.

## Change discipline

Before editing behavior, state:

- affected canonical object and user phase;
- current implementation evidence;
- intended postcondition;
- migration effect on existing Runs;
- failure and recovery behavior;
- tests that will prove the change;
- capability claims that remain unavailable.

Keep the current deterministic pipeline usable while the target orchestrator is
introduced. Prefer explicit compatibility adapters to duplicated product paths.

## Definition of done

A task is complete only when:

- code and contracts agree;
- historical Runs remain readable and immutable;
- accepted-result pointers remain explicit;
- product state no longer relies on any filename heuristic changed by the task;
- automated tests pass;
- manual verification is recorded when UX or CAD execution changed;
- readiness, roadmap, task board, usage, and relevant architecture/skills are
  synchronized;
- the report distinguishes implemented, automated verified, manually verified,
  and production usable.

Passing tests alone is not permission to advance a capability claim.
