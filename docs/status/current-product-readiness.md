# Current Product Readiness

Status date: 2026-07-27.

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

- Agent-selected multi-action Design Episode.
- Tool Broker for untrusted model programs.
- Enforced sandbox profile for provider-generated CAD source.
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
- deterministic fixed-action episode behavior;
- legacy Workflow Console stage/availability presentation outside the new
  manifest-derived product projection;
- hard-coded capability labeling in reviewed-part results;
- multiple compatibility/evaluation entry points remain callable outside
  product authority;
- disconnected assembly and drawing utilities.

These are migration tasks, not accepted target behavior.

## Verification state

- Automated verified: all test files passed in exhaustive shards with
  `550 passed, 2 skipped` on 2026-07-27.
- New contract tests cover ordered Part Job attempt history, acceptance-pointer
  separation, immutable Run evidence, v1 projection, schema definitions,
  manifest-only product state, orchestrator routing, and retry idempotency.
- Golden contract and full-mode tests remain green; the two skipped tests are
  opt-in/environment-gated checks, not M1 failures.
- Verified meaning: the M1 runtime/contracts and the existing deterministic
  workflow, console contracts, safety boundaries, failure isolation, and
  compatibility behavior are internally consistent.
- Not proven by those tests: Agent design breadth, provider-selected actions,
  sandbox security, non-template geometry success, multi-part assembly, or
  drawing-package usability.
- Manually verified for this package:
  - Golden Desktop Robot Arm contract mode passed;
  - full mode passed and produced STEP, STL, and preview output;
  - a real Golden Work retained two `upper_link` attempts;
  - accepting the earlier `single_part_upper_link` result registered explicit
    STEP/STL/preview artifact ids and left active root and leaf unchanged;
  - the returned completion came from `work_orchestrator`.
- No new UI was implemented, so this package did not require a new Workbench
  visual acceptance.
- Manual browser verification: incomplete for the latest legacy Workflow
  Cockpit.
- Target architecture verification: M1 passed. M2 and later milestone claims
  remain unverified.

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

M0 and M1 are complete. The next milestone is M2, the first provider-backed
Agentic design vertical slice. It has not started in this package.

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
