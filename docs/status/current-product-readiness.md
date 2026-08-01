# Current Product Readiness

Status date: 2026-08-01.

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

This target is documented. Its M1 runtime and domain foundation is implemented;
the Agentic design runtime and later-milestone product surfaces are not.

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

## M2 validation preview — implemented, not production usable

- `design_part` v0.1 typed registry for actions, context, tools, knowledge,
  budgets, output contracts, prohibitions, and stop reasons.
- Provider-selected next actions for semantic context, structured contract
  creation/patching, local validation, focused user questions, and typed stop.
- Observation-driven contract repair in a bounded episode.
- Context Work/Run/Part/checkpoint/trust provenance, unrelated-Work rejection,
  and request/byte budgets.
- Concise episode actions, submissions, observations, budget use, and result
  artifacts without private reasoning or raw provider traffic.
- CadFlow-owned Tool Broker definitions for structured validation and the
  future model-program execution boundary.
- Broker authorization and invocation for local structured-contract validation,
  with typed observations and persisted `tool_broker_manifest.json` evidence.
- Explicit Windows model-program capability gate that enumerates all required
  controls and returns `sandbox_unavailable` before source, candidate-directory,
  or process side effects.
- Typed `AgentDesignPort` and `WorkOrchestrator` route for an existing Part Job
  attempt, with ownership checks before provider invocation.
- Append-only episode evidence under the owning Run, path-safe idempotent
  request identity, and typed Work candidate/observation/diagnostic references.
- Protected-state postcondition checks covering active lineage, accepted-result
  pointers, Part Jobs, Assembly Job, Deliverable Packages, and Run ids.
- `cadquery_v1` selected as the first model-program source API, with a fixed
  `build_model(parameters)` entrypoint contract. This is a CadFlow policy
  version; the executable CadQuery/Python/OCCT toolchain is not yet bound.
- Broker-owned AST-only source validation for allowlisted imports/calls,
  prohibited syntax/authority, source size, and AST size. Observations retain a
  source hash and sanitized codes, not source text.

This preview is connected to the product `WorkOrchestrator`, but only for
validation and evidence registration. Its only tool enabled for the
`design_part` skill is structured-contract validation. The model-program Broker
execution entry is unavailable capability metadata, not execution authority.
The separate static source validator is not registered as a provider Episode
action. The preview cannot execute CAD, publish a reviewable result, or update
acceptance, so it must not be described as production Agentic CAD design.

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

- Product-integrated provider-selected design-to-execution Episode and
  reviewable publication.
- Runtime `model_program` skill registration and provider-selected source
  creation/patch actions.
- Tool Broker execution worker for untrusted model programs.
- Enforced Windows sandbox profile for provider-generated CAD source (the
  implemented capability gate currently reports unavailable).
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

- Automated verified: the complete suite passed with `596 passed, 2 skipped`
  in 379.72 seconds on 2026-08-01.
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
- Verified meaning: the M1 runtime/contracts and the existing deterministic
  workflow, console contracts, safety boundaries, failure isolation, and
  compatibility behavior are internally consistent.
- Not proven by those tests: real external-provider design quality or
  product-route interoperability, sandbox security, non-template geometry
  success, multi-part assembly, or drawing-package usability.
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
- A real external provider has not been manually verified through the product
  route.
- No new UI was implemented, so this package did not require a new Workbench
  visual acceptance.
- Manual browser verification: incomplete for the latest legacy Workflow
  Cockpit.
- Target architecture verification: M1 passed. The first M2 internal package is
  contract-tested; M2 acceptance and later milestone claims remain unverified.

## Current risks

- Passing workflow tests can be mistaken for progress toward Agent design
  capability.
- Provider configuration can be mistaken for an Agentic product path.
- The existing CAD IR blocks unknown designs before a capable Agent can realize
  them.
- A sandboxed code path implemented without enforceable isolation would create
  unacceptable host risk.
- Legacy documents or entry points can silently restore the former architecture.
- Assembly heuristics can be mistaken for geometric fit or motion validation.
- Generated drawings can be mistaken for checked drawings unless annotation
  provenance is explicit.

## Current milestone

M0 and M1 are complete. M2 is in progress: its provider-selected
structured-contract preview, validation Tool Broker, and fail-closed Windows
capability gate exist, while the sandbox execution/publication vertical slice
remains unimplemented.

Later milestones remain:

1. M2 provider-selected bounded design loop and enforceable execution boundary;
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
