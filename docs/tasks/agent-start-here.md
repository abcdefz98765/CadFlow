# Agent Implementation Start Here

Status date: 2026-07-25.

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

The current milestone is M1: runtime consolidation and domain foundations.

Do not begin M2 or later work until the relevant M1 acceptance conditions pass.
In particular, do not start by:

- polishing the legacy Workflow Console;
- adding another product-specific `part_type`;
- building a general skill-registry platform;
- exposing Agent-generated source without an enforceable sandbox;
- claiming Assembly Job, drawings, or Agentic design before implementation and
  verification exist.

## First work package

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
