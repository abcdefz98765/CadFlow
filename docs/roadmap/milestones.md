# CadFlow Target Milestones

Status date: 2026-08-01.

This roadmap implements the Agent-first target in `docs/FINAL-PRD.md`.

## Sequencing principles

- Restore design capability before further Workflow Cockpit polish.
- Constrain side effects and publication, not the Agent's design strategy.
- Build one end-to-end vertical slice before generalizing registries.
- Measure progress with non-template geometry benchmarks.
- Make Part Job attempts first-class before claiming multi-part progression.
- Integrate assembly, BOM, and drawings into normal Work deliverables.
- Preserve legacy Runs and deterministic tests during migration.

## M0 — Documentation and architecture correction

Goal:

- replace the former fixed workflow-first target with an Agent-first design
  workbench target.

Required outcomes:

- one authoritative PRD;
- one canonical architecture;
- four user phases;
- structured and sandboxed model-program candidate paths;
- updated workflow, Agent, UX, roadmap, task, and readiness contracts;
- competing legacy architecture and roadmap documents removed;
- implementation gaps stated honestly.

Status:

- complete on 2026-07-25;
- no product behavior is changed by this milestone.

## M1 — Runtime consolidation and domain foundations

Goal:

- create one reliable execution spine for the new product.

Required outcomes:

- one top-level Work orchestrator for Intent, Design, Build & Evaluate, and
  Accept & Deliver;
- remove or isolate competing create pipelines from the product path;
- first-class Part Job attempt lists and accepted pointers;
- explicit Assembly Job schema;
- typed artifact envelope and trust roles;
- domain-state projections that do not infer trust from recursive filenames;
- legacy adapters and Runs available through compatibility boundaries.

Acceptance:

- one Work can create two attempts for one Part Job and accept either without
  rewriting history;
- product state comes from manifests and artifact references;
- existing deterministic Golden and failure-isolation tests remain green.

Status:

- accepted on 2026-07-27 for the M1 deterministic product scope;
- first work package completed on 2026-07-25:
  - accepted ADR for one product Work orchestrator;
  - classified runtime entry-point inventory;
  - Work-manifest v2 and nested domain-record v1 contracts;
  - ordered Part Job attempt mutation and acceptance/lineage separation;
  - manifest-only product-state projector;
  - v1 Work-manifest compatibility projector;
  - contract tests for attempt history, pointer separation, immutable Run
    evidence, and manifest-based state;
- one `WorkOrchestrator` now owns target-product Work creation, Intent Run
  ownership, ordered Part Job attempts, candidate selection, active-lineage
  changes, and accepted-result pointer changes;
- the deterministic workflow is isolated behind one typed compatibility port;
- legacy Run summaries are translated by an explicit, read-only compatibility
  projector before the target product view consumes artifact references;
- full deterministic suite is green at `550 passed, 2 skipped`;
- contract and full Golden Desktop Robot Arm acceptance both passed;
- a real Work acceptance retained two `upper_link` attempts, accepted the
  earlier reviewable result, registered STEP/STL/preview references, and left
  active root and leaf unchanged;
- this accepts M1 only. It does not accept Agentic design, a model-program
  sandbox, Assembly generation, a new Workbench, or any new `part_type`.

## M2 — First real Agentic design vertical slice

Goal:

- prove that a provider can design, execute, observe, and repair geometry inside
  controlled boundaries.

Scope:

- one provider;
- one `design_part` skill;
- minimal typed skill/tool/knowledge registry;
- semantic Context Broker;
- provider-selected action loop;
- sandboxed CadQuery v1 model-program candidate;
- existing STEP-first inspection and publication validators;
- explicit user acceptance.

Required Agent actions:

- request context;
- propose candidate;
- create or patch model program;
- request execution;
- inspect observation;
- repair, change strategy, ask user, or stop.

Acceptance:

- at least five non-template benchmark parts generate validated STEP;
- at least two cases require an observation-driven repair;
- at least one case asks the user rather than guessing;
- sandbox violations fail closed;
- capability mode and assumptions are visible;
- deterministic fallback remains clearly labeled.

Out of scope:

- full feature-graph IR;
- batch assembly;
- release-grade engineering validation.

Status:

- in progress;
- first internal package implemented on 2026-08-01:
  - `design_part` v0.1 skill contract and typed registry;
  - provider-selected semantic context, contract creation/patching,
    validation, focused-question, and stop actions;
  - validation-observation-driven repair behavior;
  - Work/Run/Part/checkpoint/trust context provenance and request/byte budgets;
  - deterministic fallback remains a separate, explicitly labeled path;
- full regression suite remains green at `558 passed, 2 skipped`;
- scripted-provider file-level acceptance confirmed three provider-selected
  actions, provenance-safe episode evidence, local validation, and zero CAD
  product output;
- second internal package implemented on 2026-08-01:
  - CadFlow-owned typed Tool Broker catalog;
  - structured-contract validation routed through Broker authorization;
  - tool execution-profile, filesystem/network/process, evidence, limit, and
    failure-code declarations;
  - explicit Windows model-program capability gate with all required controls
    reported missing;
  - `sandbox_unavailable` returned before candidate-directory or process side
    effects;
- package 2 verification passed with `23 passed` targeted and
  `565 passed, 2 skipped` full-suite results;
- local Windows acceptance confirmed Broker-owned validation plus
  `available=false`, `sandbox_unavailable`, `side_effect_started=false`, and no
  candidate-directory creation;
- third internal package implemented on 2026-08-01:
  - typed `AgentDesignPort` and validation-only `WorkOrchestrator` command for an
    owned Part Job attempt;
  - append-only Run evidence, idempotent request replay, and typed Work
    candidate/observation/diagnostic references;
  - explicit protected-state checks that preserve lineage, acceptance,
    Assembly Job, Deliverable Packages, Part Jobs, and Run identities;
- package 3 verification passed with `156 passed` targeted and
  `574 passed, 2 skipped` full-suite results;
- scripted-provider product-route acceptance confirmed four registered
  evidence references, exactly three provider calls, idempotent replay,
  unchanged protected Work/Run evidence, and zero CAD or accepted products;
- fourth internal package implemented on 2026-08-01:
  - selected `cadquery_v1` as the first model-program source API;
  - defined the `build_model(parameters)` contract, allowlisted imports/calls,
    prohibited syntax/authority, and source/AST limits;
  - routed AST-only validation through the Tool Broker with source hash and
    sanitized typed observations;
  - kept source retention, imports, bytecode compilation, execution, candidate
    directories, product routing, and publication unavailable;
- package 4 verification passed with `175 passed` targeted and
  `596 passed, 2 skipped` full-suite results;
- local file-level acceptance confirmed allowlisted source acceptance,
  sanitized `socket`/`open` rejection, no source retention, and an independent
  `sandbox_unavailable` execution block with no candidate directory;
- fifth internal package implemented on 2026-08-02:
  - pinned a separately imported `CadFlow-Sandbox-CQ-v1` rootfs, Python
    3.10.12, CadQuery 2.7.0, cadquery-ocp 7.8.1.1.post1, wheel lock, WSL
    configuration, worker, launcher, probes, and content-derived digests;
  - added exact-profile startup attestation, systemd mount/network isolation,
    post-bootstrap seccomp, empty capabilities, read-only system/toolchain,
    controlled environment, private temp, and fixed resource limits;
  - added strict Broker execution/context types, STEP-only worker output,
    archive validation, typed failures, and append-only candidate/diagnostic
    execution evidence;
  - kept the primitive explicitly disabled by default and outside runtime
    `model_program`, `design_part`, `WorkOrchestrator`, publication, acceptance,
    and Deliverable Package authority;
- package 5 verification passed with `53 passed` targeted and, after the STEP
  re-import upgrade, `621 passed, 2 skipped` in the full suite with live WSL2
  integration enabled;
- current-host Windows/WSL2 acceptance recorded all attack probes passing, a
  valid non-template STEP result and its hashes, and unchanged accepted-result
  and Deliverable Package state;
- this product-routed preview validates a structured legacy CAD IR candidate
  only. It cannot execute CAD or publish a reviewable result;
- M2 remains unaccepted pending runtime model-program Episode actions,
  design-to-execution routing, STEP-first publication/inspection, and the
  five-part benchmark gate.

## M3 — General structured geometry contract

Goal:

- replace the flat closed-family CAD IR with an extensible feature graph.

Initial operations:

- parameters and expressions;
- coordinate frames and datums;
- constrained 2D sketches;
- extrude and revolve;
- holes and pockets;
- booleans;
- fillet and chamfer;
- linear and circular patterns;
- named faces, axes, and interfaces.

Required outcomes:

- versioned feature-graph schema;
- backend capability declarations;
- contract validator;
- deterministic CadQuery or build123d executor;
- migration adapter for legacy `input_ir.json`;
- geometry benchmarks comparing model-program and feature-graph paths.

Acceptance:

- non-template parts can be expressed without adding a new `part_type` builder;
- unsupported operations produce typed capability feedback;
- revision can patch parameters and ordered features.

## M4 — Multi-Part Work and Assembly Job

Goal:

- progress from accepted Part Jobs to a validated assembly attempt.

Required outcomes:

- multiple Part Jobs with independent attempt and accepted-result histories;
- interface identities preserved across revisions;
- Assembly Job consumes exact accepted part-result ids;
- placement, mate, joint, fastener, reference-component, and clearance
  contracts;
- isolated assembly execution;
- native assembly and/or assembly STEP output;
- BOM generation;
- validation reports that separate heuristics from geometric checks.

Acceptance:

- one example contains at least three generated accepted parts and one reference
  component;
- changing one accepted part marks assembly evidence stale;
- assembly regeneration preserves earlier attempts;
- no fit, motion, or tolerance claim appears unless the check ran.

## M5 — Engineering deliverable package

Goal:

- turn accepted model results into usable engineering handoff artifacts.

Required outcomes:

- versioned Deliverable Package manifest;
- accepted part and assembly STEP collection;
- BOM;
- integrated FreeCAD TechDraw or equivalent drawing generation;
- PDF/SVG part drawings;
- assembly drawing or exploded view where supported;
- source-result identity and annotation provenance;
- visible limitations and missing deliverables.

Acceptance:

- drawing generation runs from accepted results inside the normal Work flow;
- drawing failures do not invalidate accepted models;
- package contents resolve only through accepted pointers;
- automated tests cover at least one part drawing and one assembly package.

## M6 — Agent-first workbench UX

Goal:

- replace the former checkpoint cockpit as the primary experience.

Primary layout:

- design objective and focused conversation;
- model or assembly preview;
- Agent actions, assumptions, and progress;
- candidate comparison;
- validation and limitations;
- Part Jobs and accepted results;
- one recommended action.

Required outcomes:

- four-phase navigation;
- old Workflow graph moved to compatibility/Diagnostics;
- real-time pending, execution, observation, and repair feedback;
- explicit acceptance and revision;
- bilingual product-critical paths;
- desktop and narrow-layout acceptance.

Acceptance:

- a user completes the M2 vertical slice without understanding legacy artifact
  names;
- no enabled action lacks a verified postcondition;
- Work and Run Snapshot boundaries remain clear.

## M7 — Engineering assurance expansion

Potential domain-specific increments:

- manufacturing checks;
- tolerance and fit evidence;
- kinematic checks;
- load and strength analysis integrations;
- GD&T assistance;
- inspection planning;
- release workflows.

Each increment requires its own validator, evidence contract, benchmark, and
claim boundary. None is implied by model generation alone.

## Deferred

- arbitrary external STEP feature-history recovery;
- general mesh reverse engineering;
- unrestricted provider code execution;
- public cloud and multi-user collaboration;
- automatic safety-critical release.
