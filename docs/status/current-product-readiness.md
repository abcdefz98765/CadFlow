# Current Product Readiness

Status date: 2026-08-08.

This document distinguishes the Agent-first target architecture from the
currently implemented deterministic product and the accepted M1 runtime
foundation.

## Target status

The authoritative target is now:

- Agent-first CAD design workbench;
- Intent, Design, Build & Evaluate, Accept & Deliver;
- provider-selected bounded design actions;
- structured feature-graph and sandboxed model-program candidate paths;
- first-class Part Job attempts and Assembly Job;
- accepted-result-derived STEP, assembly, BOM, and drawing packages.

This target is documented. Its M1 runtime/domain foundation and a bounded M2
execution/publication preview are implemented; the accepted Agentic product
slice and later-milestone surfaces are not.

## Implemented and usable now

- Local Workspace and Work creation.
- Append-only Run storage and active-lineage pointers.
- Work-manifest v2 with ordered Part Job attempt records.
- Explicit accepted part-result pointers separated from active design lineage.
- Typed artifact references and manifest-only product-state projection.
- Schema-versioned Assembly Job and Deliverable Package definitions.
- Read-only v1 Work-manifest compatibility projection that preserves Run
  evidence.
- One top-level `WorkOrchestrator` for target-product Work mutations.
- One typed deterministic compatibility port for current Run creation and
  stage execution.
- Explicit read-only projection of legacy Run metadata into artifact
  references before product-state rendering.
- Backend/API creation of later attempts for the same Part Job.
- Deterministic prompt and CAD IR pipelines.
- Eight supported deterministic CAD IR part families.
- STEP-first generation for supported families.
- Basic geometry, export, and selected feature inspection.
- Isolated deterministic candidate execution.
- Final failure cleanup that avoids publishing untrusted product files.
- Explicit part-result acceptance and accepted-pointer-only Deliverables.
- Controlled artifact reads, overrides, and Run Snapshot boundaries.
- Local NiceGUI Workflow Console for the legacy workflow.

Production-usable scope:

- local deterministic supported-family single-part generation and review;
- local manifest-backed Work/Intent creation, ordered Part Job attempts,
  explicit accepted-result changes, and accepted artifact projection through
  the existing backend/API and Workflow Console actions.

This is a deterministic local product scope. It is not the Agent-first
Workbench and does not execute provider-generated model programs.

## Implemented but not Agentic

- `AgentAdapter` abstraction;
- JSON-contract provider clients;
- provider configuration in the local console;
- bounded episode state machine;
- semantic Context Broker prototype;
- `create_part_ir` episode artifacts;
- validator observations.

## M2 execution-aware preview — implemented, not production usable

- `design_part` v0.2 typed registry for actions, context, tools, knowledge,
  budgets, output contracts, prohibitions, and stop reasons.
- Provider-selected next actions for semantic context, structured contract
  creation/patching, local validation, focused user questions, and typed stop.
- Observation-driven contract repair in a bounded episode.
- Context Work/Run/Part/checkpoint/trust provenance, unrelated-Work rejection,
  and request/byte budgets.
- Concise episode actions, submissions, observations, budget use, and result
  artifacts without private reasoning or raw provider traffic.
- CadFlow-owned Tool Broker definitions for structured validation and the
  internal model-program execution boundary.
- Broker authorization and invocation for local structured-contract validation,
  with typed observations and persisted `tool_broker_manifest.json` evidence.
- Explicit Windows model-program capability gate that is disabled by default
  and returns `sandbox_unavailable` before request-side source,
  candidate-directory, or process side effects unless a fresh attestation
  proves the exact profile and every required control.
- Typed `AgentDesignPort` and `WorkOrchestrator` route for an existing Part Job
  attempt, with ownership checks before provider invocation.
- Append-only episode evidence under the owning Run, path-safe idempotent
  request identity, and typed Work candidate/observation/diagnostic references.
- Protected-state postcondition checks covering active lineage, accepted-result
  pointers, Part Jobs, Assembly Job, Deliverable Packages, and Run ids.
- `cadquery_v1` selected as the first model-program source API, with a fixed
  `build_model(parameters)` entrypoint contract and pinned Python 3.10.12,
  CadQuery 2.7.0, and cadquery-ocp 7.8.1.1.post1 internal toolchain.
- Broker-owned AST-only source validation for allowlisted imports/calls,
  prohibited syntax/authority, source size, and AST size. Observations retain a
  source hash and sanitized codes, not source text.
- Dedicated `CadFlow-Sandbox-CQ-v1` WSL2 runtime with repository-owned rootfs
  and wheel hashes, content-derived profile/toolchain digests, disabled DrvFs
  automount/interop, and a fixed root-owned launcher.
- Attested systemd worker boundary with private network/mount/temp/devices,
  hidden Windows integration mounts, read-only system/toolchain, controlled
  environment, empty capabilities, `NoNewPrivileges`, process-clone/socket/
  exec/mount seccomp denials, and CPU/memory/swap/task/output limits.
- Strict model-program request and trusted invocation-context contracts,
  STEP-only output, archive allowlist/path/symlink/size validation, typed exit
  observations, sanitized logs, and append-only candidate/diagnostic evidence.
- The sealed worker re-imports each exported STEP and requires valid solid
  geometry plus bounded solid-count, bounding-box, and volume agreement before
  a successful execution observation can leave the sandbox.
- Registered CadFlow-owned `model_program` v0.1 delegate with strict complete
  create/replace submissions, execution of only the current CadFlow-assigned
  candidate, and inspection of only the latest uninspected observation.
- Independent limits of 16 actions, four source submissions, three executions,
  three inspections, and two repairs; repair and completion require inspection
  of the latest observation.
- Source/parameter hashes in pre-execution submission evidence and full values
  only in canonical Broker execution evidence after policy and attestation
  gates, plus sanitized observation artifacts without raw provider traffic or
  private reasoning; the provider never supplies path,
  command, environment, UID, evidence root, candidate, observation, or
  execution identity.
- CadFlow-owned reviewable publication for completed model-program episodes.
  The gate cross-checks Work/Run/Part/Episode/candidate/execution identity,
  source/parameter/profile/toolchain/attestation digests, Broker manifest,
  limits, STEP hash/size, valid solid facts, and STEP re-import tolerances.
- Immutable `reviewable_result.json` and registered reviewable STEP references;
  publication failure or tampering creates diagnostic evidence only.
- Explicit by-id acceptance and revision routes. Only acceptance changes the
  Part Job accepted-result pointer; revision creates a new attempt and
  preserves historical Runs and any prior accepted result.

This preview is connected to the product `WorkOrchestrator` for validation,
attested execution, evidence registration, and gated reviewable publication.
The model-program Broker primitive remains disabled unless a fresh attestation
proves the exact sealed profile. Reviewable publication does not accept or
deliver the result. The slice must not be described as production Agentic CAD
design until the real external-provider benchmark and explicit user acceptance
gates pass.

Capability classification for this section:

- implemented: yes, for the bounded Episode, attested execution, publication,
  explicit acceptance route, and revision route described above;
- automated verified: yes, with unit/contract/tamper/route tests and live WSL2
  integration; final complete-suite numbers are recorded below;
- manually verified: yes, on the current Windows/WSL2 host with a scripted
  provider and temporary Work;
- production usable: only the attestation-constrained internal execution and
  publication primitive. The Agentic product path is not production usable
  until the external-provider benchmark and explicit user acceptance pass.

The product `create_part_ir` path currently follows a fixed proposer sequence:
one fixed context request, one adapter submission, one validation request, and
no real provider-selected repair loop. It must be labeled deterministic or
one-shot orchestration, not Agentic design.

## Partial or migration-only

- Work / Part Job projection: v2 manifests own ordered attempt histories, while
  legacy evidence with incomplete ownership remains compatibility-projected.
- Current Work presentation: the target product projection is manifest and
  artifact-reference based. Legacy stage/availability presentation still reads
  sanitized Run metadata through an explicit compatibility boundary.
- Provider usage: different entry points do not consistently use the configured
  adapter.
- Revision: narrow field-level native CAD IR patches only.
- Assembly: planning helpers, bounding-box validation, and external FreeCAD
  scripts exist but are not a normal Assembly Job flow.
- Drawings: TechDraw helper exists but is not integrated into accepted-result
  Deliverable Packages.
- Browser usability: the legacy Workflow Cockpit has automated coverage but its
  latest complete manual acceptance remains unfinished.

## Not implemented

- Five non-template benchmark acceptance with a real external provider.
- Explicit user acceptance of at least one external-provider benchmark
  reviewable result and the final M2 acceptance record.
- General feature-graph geometry contract.
- Non-template general CAD design capability.
- Executable Assembly Job flow with accepted input identities.
- Integrated assembly STEP or native assembly deliverable.
- Integrated BOM and drawing package.
- Agent-first four-phase workbench UI.
- Engineering release checks for fit, tolerance, motion, strength, DFM/DFA,
  GD&T, FEA, or safety.

## Code concentration risk

Current approximate Python line distribution:

- Workflow Console: 14.5k lines;
- Agent layer: 3.2k lines;
- CAD IR: 0.6k lines;
- CadQuery and backend layer: 0.5k lines.

This reflects the former product priority. Further Workflow Cockpit polish is
not the current milestone unless required to preserve safe operation during
migration.

## Architecture conformance gaps

The following current behavior still does not conform to the target
architecture:

- fixed fifteen-checkpoint primary Workflow;
- flat closed-family CAD IR;
- deterministic fixed-action behavior in the current `create_part_ir`
  compatibility product path;
- legacy Workflow Console stage/availability presentation outside the new
  manifest-derived product projection;
- hard-coded capability labeling in reviewed-part results;
- multiple compatibility/evaluation entry points remain callable outside
  product authority;
- disconnected assembly and drawing utilities.

These are migration tasks, not accepted target behavior.

## Verification state

- Automated verified for Package 3 on 2026-08-08: `160 passed` targeted,
  including live WSL2 product/attack coverage, and `644 passed, 2 skipped` in
  576.21 seconds for the complete suite with the live sandbox enabled.
- Previous Package 2 baseline: the complete suite passed with the live WSL2
  sandbox explicitly enabled at `633 passed, 2 skipped` in 516.74 seconds on
  2026-08-02.
- The M1 acceptance baseline was `550 passed, 2 skipped` on 2026-07-27.
- New contract tests cover ordered Part Job attempt history, acceptance-pointer
  separation, immutable Run evidence, v1 projection, schema definitions,
  manifest-only product state, orchestrator routing, and retry idempotency.
- Golden contract and full-mode tests remain green; the two skipped tests are
  opt-in/environment-gated checks, not M1 failures.
- M2 package tests prove provider-selected action sequences, context-dependent
  behavior, observation-driven patching, focused user questions, knowledge
  isolation, unrelated-Work rejection, byte/request/action/repair budgets,
  forbidden execution-field rejection, and provider-failure redaction.
  Provider-visible action state is also tested for secret and local-path
  redaction.
- Model-program Episode tests prove strict action fields, CadFlow-assigned
  identity, execution/inspection ordering, observation-driven complete-source
  replacement, budget accounting, path removal from provider observations,
  source-free event summaries, and mandatory STEP re-import evidence before
  completion.
- The live suite includes the complete provider-selected Episode → Broker →
  dedicated WSL2 worker → STEP re-import → observation-inspection path.
- M2 Tool Broker tests prove skill authorization, strict input contracts,
  prohibited execution-field rejection, validator-failure redaction, typed
  observations, required sandbox-control completeness, Windows capability
  reporting, and no candidate-directory side effect on an unavailable
  model-program request.
- M2 product-route tests prove Part Job attempt ownership, provider-selected
  validation routing, path-safe idempotency, conflicting request rejection,
  tampered evidence rejection, protected Work state, immutable original Run
  prompt bytes, mismatched request/path identity rejection, typed artifact
  registration, diagnostic safe blocks, and no duplicate provider call on
  replay.
- CadQuery v1 source-policy tests prove allowlisted source acceptance, import/
  call/syntax/entrypoint/size rejection, source redaction, Broker authorization,
  internal-exception redaction, static-versus-execution capability separation,
  and no candidate-directory side effect after a static pass.
- WSL2 sandbox tests prove repository/profile/toolchain digest binding, fake
  capability rejection, startup and active control probes, legal non-template
  STEP execution, host/mount/environment/symlink escape denial, socket/
  subprocess/shell/pip/fork denial, CPU and memory termination, strict request
  and context contracts, archive traversal rejection, output allowlisting,
  sanitized diagnostic logs, and append-only Broker observations.
- Verified meaning: the M1 runtime/contracts and the existing deterministic
  workflow, console contracts, safety boundaries, failure isolation, and
  compatibility behavior are internally consistent.
- Not proven by those tests: real external-provider design quality,
  portability beyond the
  recorded Windows/WSL2 host, an independent security audit, the five-part
  non-template benchmark gate, multi-part assembly, or drawing-package
  usability.
- Manually verified for this package:
  - Golden Desktop Robot Arm contract mode passed;
  - full mode passed and produced STEP, STL, and preview output;
  - a real Golden Work retained two `upper_link` attempts;
  - accepting the earlier `single_part_upper_link` result registered explicit
    STEP/STL/preview artifact ids and left active root and leaf unchanged;
  - the returned completion came from `work_orchestrator`.
- Manually verified for the M2 internal package with a scripted provider:
  - the provider selected `request_context`, `create_contract`, and
    `request_validation` across three calls;
  - the episode persisted skill `design_part` v0.1.0, `part_job` provenance,
    and `accepted_input` trust role;
  - local contract validation passed;
  - no `model.step` or other CAD product was created, matching the declared
    no-execution boundary.
- Manually verified for the Tool Broker package on Windows:
  - Broker-owned structured-contract validation passed;
  - model-program capability reported `available=false` and
    `sandbox_unavailable`;
  - `side_effect_started=false` and the requested candidate directory was not
    created;
  - the reproducible record is
    `m2-tool-broker-package-acceptance.md`.
- Manually verified for the validation-only WorkOrchestrator package with a
  scripted provider:
  - the product route registered four candidate/observation references after
    exactly three provider-selected calls;
  - exact replay reused persisted evidence without another provider call or
    Work manifest rewrite;
  - protected Work state and original Run prompt bytes remained unchanged;
  - no accepted, deliverable, STEP, STL, or model-program product was created;
  - the reproducible record is
    `m2-work-design-episode-package-acceptance.md`.
- Manually verified for the CadQuery v1 static source-policy package:
  - allowlisted source passed without import, bytecode compilation, execution,
    retention, or side effects;
  - `socket` and `open` source returned sanitized typed rejections;
  - the subsequent execution request still returned `sandbox_unavailable` and
    created no candidate directory;
  - the reproducible record is
    `m2-cadquery-source-policy-package-acceptance.md`.
- Manually verified for the WSL2 model-program sandbox package on the current
  Windows/WSL2 host:
  - all active isolation and attack probes passed for the pinned distro,
    profile, toolchain, worker, launcher, and configuration digests;
  - a non-template hexagonal solid with a central bore produced one valid STEP
    solid through the attested Broker primitive;
  - source, parameters, STEP, geometry, logs, limits, exit state, and lineage
    hashes were recorded as candidate execution evidence;
  - reviewable, accepted, and deliverable state remained false, while the
    existing accepted-result pointer and Deliverable Package remained
    byte-identical;
  - the reproducible record is
    `m2-wsl2-model-program-sandbox-package-acceptance.md`.
- Manually verified for the registered model-program Episode on the current
  Windows/WSL2 host:
  - `design_part` v0.2 assigned `candidate_001` and `observation_001`, executed
    one non-template hex-bore candidate, inspected the structured observation,
    and completed only after valid STEP re-import evidence;
  - STEP SHA-256 was
    `4cf93de774fec54d2d9b260e2a050bd568fc1da500aa62b36d8d319f57ae9410`;
  - no reviewable, accepted, or deliverable record was created;
  - the reproducible record is
    `m2-model-program-episode-package-acceptance.md`.
- Manually verified for reviewable publication on the current Windows/WSL2
  host:
  - a scripted provider drove the complete Work → Episode → Tool Broker →
    dedicated WSL2 worker → STEP re-import → publication route;
  - publication produced one reviewable STEP with SHA-256
    `3dfc3bed636bb8995f9325b61bbe22eb72a03097fabfe0fec8891d4cf909826c`;
  - accepted pointers, active lineage, and Deliverable Packages were unchanged
    before the explicit acceptance call;
  - exact replay made no provider call and did not rewrite the Work;
  - isolated temporary-Work tests proved explicit acceptance and revision
    authority while revision preserved the accepted pointer;
  - the reproducible record is
    `m2-reviewable-publication-package-acceptance.md`.
- A real external provider has not been manually verified through the product
  route.
- No new UI was implemented, so this package did not require a new Workbench
  visual acceptance.
- Manual browser verification: incomplete for the latest legacy Workflow
  Cockpit.
- Target architecture verification: M1 passed. Seven bounded M2 internal
  packages are contract-tested, and execution/publication have current-host
  WSL2 acceptance. The external-provider benchmark and user acceptance remain
  unverified, so M2 is not complete.

## Current risks

- Passing workflow tests can be mistaken for progress toward Agent design
  capability.
- Provider configuration can be mistaken for an Agentic product path.
- The existing CAD IR blocks unknown designs before a capable Agent can realize
  them.
- The implemented reviewable product path can be mistaken for completed M2
  even though external-provider quality, benchmark acceptance, and explicit
  user acceptance remain absent.
- Legacy documents or entry points can silently restore the former architecture.
- Assembly heuristics can be mistaken for geometric fit or motion validation.
- Generated drawings can be mistaken for checked drawings unless annotation
  provenance is explicit.

## Current milestone

M0 and M1 are complete. M2 is in progress: its provider-selected contract and
model-program Episode, validation Tool Broker, static source policy, and
attested WSL2 execution path, reviewable publication, and explicit accept/revise
routes exist. The external-provider benchmark gate and explicit user acceptance
of one resulting reviewable result remain unfinished.

Later milestones remain:

1. M2 external-provider benchmark and explicit user acceptance;
2. M3 feature-graph/model-program geometry paths;
3. M4 multi-Part Job and Assembly Job progression;
4. M5 integrated Deliverable Package and drawings;
5. M6 Agent-first workbench UX.

See:

- `../roadmap/milestones.md`
- `../tasks/task-board.md`

## Release language

Until the corresponding acceptance gate passes, do not claim:

- Agentic CAD design;
- arbitrary or general CAD generation;
- assembly generation;
- engineering drawing-package support;
- fit, motion, strength, tolerance, manufacturing, or release validation.

Allowed current description:

> CadFlow has a tested deterministic single-part CAD workflow foundation and is
> migrating to an Agent-first design workbench.
