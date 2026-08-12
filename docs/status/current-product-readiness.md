# Current Product Readiness

Status date: 2026-08-13.

This document distinguishes the Agent-first target architecture from the
implemented deterministic product, accepted M1 runtime foundation, bounded M2
backend preview, reuse-first M2.5 Workbench MVP, the M2.6 completed Product
Golden, and the M2.7 onboarding/settings/recovery integration gate.

## Target status

The authoritative target is now:

- Agent-first CAD design workbench;
- Intent, Design, Build & Evaluate, Accept & Deliver;
- provider-selected bounded design actions;
- structured feature-graph and sandboxed model-program candidate paths;
- first-class Part Job attempts and Assembly Job;
- accepted-result-derived STEP, assembly, BOM, and drawing packages.

This target is documented. Its M1 runtime/domain foundation, a bounded M2
execution/publication preview, the M2.5 single-Part Job Workbench surface, and
the M2.6 canonical Product Golden and M2.7 usability integration are implemented;
external-provider M2
acceptance and later-milestone modeling, Assembly, and Deliverable capabilities
are not.

## V1 canonical consolidation — implemented and automated verified

- Normal Current Work reads schema-v2 Work manifests, Part Jobs, accepted
  pointers, and registered artifact references directly. It does not invoke the
  legacy product projector, infer lineage from directories/timestamps, scan
  filenames for product state, or build the fixed-stage Run review surface.
- The manifest exposes `state_authority` as `canonical` or `compatibility`.
  Legacy/imported Works remain readable, but their projector and fixed-stage
  review model are confined to the compatibility boundary and Run Snapshot.
- A small canonical interaction projection owns current state facts and
  state-changing command keys/targets. Overview, Workflow selected nodes, and
  Part scope consume that inventory; selected historical evidence remains
  inspectable and cannot invent a mutation.
- Normal selected-Work navigation is Overview and Workflow. Parts appears as a
  contextual destination when decomposition is meaningful; History remains a
  subordinate immutable-evidence destination. Current Work no longer eagerly
  loads a selected Run merely because a legacy run id is present.
- Explicit developer/test Works are written under
  `workspace/.internal/dev-works` and enter the index only when developer
  content is requested. Existing user workspace material was not deleted or
  moved by this migration.
- The registered Work Design Skill now owns concise missing-information,
  analysis, decomposition, risk/confirmation, and routing knowledge. A neutral
  provider-sanitization module and registered-Skill request compiler separate
  provider transport from Skill semantics; the JSON-contract adapter retains
  only compatibility wrappers around that compiler.
- No Assembly, Deliverable, Feature Graph, provider framework, workflow engine,
  graph persistence, or trust-boundary expansion was introduced. Controlled
  execution, inspection, reviewable publication, explicit acceptance, revision
  lineage, immutable history, secret handling, and Broker boundaries remain in
  place.
- Automated verification passed with `688 passed, 9 skipped`. The final
  clean-suite result and real-browser evidence are recorded in the Verification
  state section.

## M2.7 onboarding, Settings, recovery, and Live Agent Example — implemented and verified

- The existing NiceGUI shell presents Home / Works / Settings and prioritizes
  New Design, two distinct teaching cards, real Provider/local-CAD readiness,
  and recent product-language Work cards. The Real Agent example is variable;
  the Completed Product Example is a reproducible no-Provider snapshot.
- DeepSeek is the default external-provider choice and `deepseek-v4-flash` is
  the requested default model path. Test checks the current unsaved draft. Save
  & Verify repeats the real check, persists only non-secret configuration plus
  safe connection evidence, and restores the Connected status and adapter after
  process restart when a credential is still available from the environment.
- API keys resolve from a Settings session value, `DEEPSEEK_API_KEY` /
  `OPENAI_API_KEY` in the process environment, or an allowlisted project-root
  `.env`, in that order. Settings displays only the source and variable name.
  Values entered in Settings remain only in backend/browser session memory. They are not
  written to workspace configuration, Work manifests, Run evidence, provider
  traces, logs, or screenshots. Secret-bearing generic gate payloads now fail
  before any Run log mutation.
- Start Product Example creates a new micro-servo bracket Work with the original
  request and no preselected Part Job. It does not preload a design brief,
  candidate source, STEP/STL, reviewable result, or accepted pointer. Continue
  uses the configured adapter and existing bounded Design Episode, Tool Broker,
  sandbox, inspection, publication, Accept, and Revise boundaries.
- Agent-first Works project the actual evidence into Intent, Design, Build &
  Evaluate, and Accept & Deliver; compatibility Run Snapshots retain the legacy
  checkpoint graph. Reviewable and accepted status come from the same manifest
  references used by Overview.
- Recovery projection covers user, configuration, CadFlow, environment, and
  unsupported owners. Settings, Retry, Modify request, environment guidance,
  and technical details route to real behavior. Focused `ask_user` questions are
  persisted, answered as append-only accepted input, and resumed through the
  existing bounded episode route.
- `agent_exchange.jsonl` now records a sanitized external Agent response before
  strict action-contract validation, including for safely blocked malformed
  turns. Workbench Agent Output projects responses, questions, durable answers,
  observations, resumed attempts, and typed stops chronologically. Candidate
  source/parameters remain hash-only and private reasoning/credentials are not
  retained.
- Normal Works contain user Works and Product Examples. Developer fixtures,
  compatibility regressions, and infrastructure tests are hidden until the
  developer-content toggle is enabled, then display category and purpose.
- The reproducible M2.6 Completed Product Golden remains available as a
  secondary scripted snapshot. No M3, new CAD family, Assembly, Deliverable,
  BOM/drawing, sandbox-authority, or Tool-Broker-authority expansion was made.
- Automated verification after the focused correction: `659 passed, 9 skipped`
  in the complete repository suite, plus `203 passed, 2 skipped` across the
  expanded M2.7/console/Agent-evidence regression selection.
- Live-provider verification: the official DeepSeek endpoint accepted Save &
  Verify with `deepseek-v4-flash`; changing the model invalidated the status and
  restoring/saving it re-established Connected. A real beginning-state Live
  Product Example entered the bounded Agent route and stopped with
  `policy_blocked`. CadFlow published no reviewable result, accepted pointer,
  model, or deliverable, which is the required safe behavior for that outcome.
- Browser verification: English/Chinese critical paths were exercised at
  1440px, 1024px, and 414px. Home, Works, Settings, provider setup/connected
  states, live-example start/running/safe-stop states, four-phase Workflow, user
  clarification, unsupported capability, and configuration recovery are saved
  under `docs/ux/screenshots/onboarding-settings-recovery-live-example/`.
- The correction pass re-audited the real in-app Home, Works, Settings, Agent
  Output, and typed recovery-detail surfaces in English and Chinese. Eight
  repo-owned screenshots are under
  `docs/ux/screenshots/onboarding-settings-recovery-live-example/correction/`.
  A hidden scripted developer fixture proves question, answer, resumed external
  response, and second typed stop without another external Provider request.
- After the final recovery-action polish, the directly affected browser/Agent
  regression set also passed with `68 passed`.
- The formal five-case M2 external-provider benchmark remains unrun and is still
  the next acceptance milestone; M2 is not complete. The live screenshot named
  `live-example-design-and-model-zh.png` intentionally shows the honest
  no-candidate safe-stop state because the real run did not reach geometry.

## M2.8 UI convergence — implemented and verified

- Overview now owns one dominant Work-level action. Agent Activity explains
  progress without repeating the command, Part cards navigate to Workflow, and
  empty Agent Design, geometry, and Agent Output states remain compact until
  durable evidence exists.
- Current Attention remains a derived presentation projection. A single-Part
  Work uses one compact current-task row; a multi-Part Work uses an independent
  per-Part index. Ready, Running, Needs you, Review, Blocked, Accepted, and
  completed presentation states do not alter domain status or persist UI state.
- The Dynamic Work Graph renders its existing nodes, edges, branches, and
  revision provenance as compact topology instead of four fixed equal-width
  state columns. The four phases remain orientation chips.
- Desktop Workflow uses graph-and-inspector master-detail; 1024px and mobile
  stack without page-level horizontal overflow. Node detail prioritizes state,
  explanation, valid action, and relevant result before technical ids.
- Real in-app browser verification covered beginning/ready Overview,
  clarification, reviewable geometry and acceptance, accepted-result revision,
  two-Part attention/branching, selected-node changes, immutable Run Snapshot,
  Chinese, 1440px, 1024px, and 414px layouts. Eleven screenshots are under
  `../ux/screenshots/ui-convergence/`.
- Focused behavior verification passed with `32 passed`. The clean complete
  suite result is recorded in the Verification state section below.
- No workflow/domain architecture, graph persistence, Work decomposition,
  Assembly, Deliverable, Provider, Agent-role, or security capability was added.

## M2.9 Work Design and skill/knowledge consolidation — implemented and verified

- Normal New Design and Live Product Example entry now create a Work before any
  Part Job. The registered `work_design` v0.1 Episode reasons over the whole
  objective, generated versus reference components, interfaces, dependencies,
  assumptions, and material ambiguity.
- The provider may request semantic Work context, propose a strict Work Design,
  ask one focused Work-scoped clarification, request Part Job creation, or stop
  honestly. It cannot assign Work/Part/Run identities or mutate the manifest.
- `WorkOrchestrator` owns the durable transition: it validates a completed
  proposal, assigns stable Part Job and initial Run identities, preserves
  append-only history and accepted pointers, and creates no Assembly Job.
- Overview and Dynamic Workflow project the same `work_design` record. The
  graph shows User request → Work Design → optional clarification/recovery →
  Part decomposition → real Part branches; Part Design begins only after the
  Part Jobs exist.
- Runtime Skill knowledge comes from bounded repository-contained Markdown
  sources declared by the active Skill. Legacy stage prompt builders and the
  fake planner remain explicitly labeled compatibility/test support rather than
  parallel authorities.
- A deterministic two-Part example uses the same product backend, Episode,
  Orchestrator, manifest, and projection path. It treats the camera and 2020
  extrusion as references and does not claim Assembly execution.
- Automated verification passed with `684 passed, 9 skipped` in the clean
  complete suite. The focused Work Design matrix covers single-Part,
  multi-Part, reference-component, clarification/resume, unsupported, and
  insufficient-context cases.
- Real in-app browser verification covered the normal 0-Part New Design entry,
  confirmation boundary, completed two-Part Overview, visible Work Design →
  Part decomposition graph path, English/Chinese, and 1440px/1024px/414px
  layouts. No page-level overflow or browser warning/error was observed.

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
- Local NiceGUI Agent-first Workbench built by evolving the existing Workflow
  Console shell, Work selection, Work header, Overview, Workflow graph, Parts,
  History, Run Snapshot, artifact viewer, action feedback, i18n, and responsive
  CSS.

Production-usable scope:

- local deterministic supported-family single-part generation and review;
- local manifest-backed Work/Intent creation, ordered Part Job attempts,
  explicit accepted-result changes, and accepted artifact projection through
  the existing backend/API and Workflow Console actions.

The deterministic scope remains compatibility-labeled. The same Workbench can
also present the bounded reviewable model-program result described below, but
that Agentic route remains experimental until external-provider acceptance.

## M2.6 canonical Product Golden — implemented and verified

- **Open Product Example / 打开产品示例** directly creates or reopens one
  compact micro-servo mounting-bracket Work and navigates to Overview / Design;
  no external provider credentials are required and the result is not
  auto-accepted.
- The reproducible scripted provider exercises the existing Work → Part Job →
  design episode → attested `cadquery_v1` model-program → STEP inspection →
  reviewable publication path. It proves the product journey and presentation,
  not external-provider design quality.
- Overview projects the durable original prompt and current revision under
  **Your Request**, and a registered concise `design_brief` under **Agent
  Design**. The latter contains persisted concept, geometry strategy,
  parameters, features, interfaces, assumptions, trade-offs, repair count, and
  capability mode; it contains no private reasoning.
- A compact **What happened** progression separates design transformation from
  Agent Activity. The existing STL viewer remains the visual anchor with the
  registered STEP, 58 × 42 × 34 mm bounding box, one solid, and 26 faces.
- Result presentation separates checks that ran from assumptions, unverified
  manufacturer-specific fit, unsupported release validation, and not-requested
  strength/tolerance/motion analysis.
- Detailed Workflow remains secondary but reachable. Existing explicit Accept
  and Revise routes are reused; starting revision creates attempt 2 while the
  accepted attempt-1 model and evidence remain visible.
- The example index classifies the servo bracket as Product Golden, provider
  routes as benchmark/evaluation, Desktop Robot Arm and older scripted flows as
  compatibility/regression, and broker/episode/policy checks as infrastructure
  smoke.

Capability classification for M2.6:

- implemented: yes;
- automated verified: `148 passed, 2 skipped` in focused Product Golden,
  Workbench, route, and old-Golden regression tests, followed by `657 passed,
  2 skipped` in the complete suite with the existing WSL2 sandbox enabled on
  2026-08-08;
- manually verified: the real in-app browser opened the example, displayed the
  original request, Agent Design, event progression, generated geometry,
  measured and scoped validation facts, opened Detailed Workflow, returned to
  Overview with context intact, explicitly accepted the result, then created a
  Chinese natural-language revision while retaining the prior accepted result;
  Advanced still exposed runtime and attestation evidence;
- responsive verified: English and Chinese critical paths passed at 1440px,
  1024px, and 414px without page-level horizontal overflow. The ten requested
  screenshots are saved under `docs/ux/screenshots/product-golden/`;
- production usable: a normal user can directly inspect and operate the current
  local single-Part Job example. The Agentic route and general CAD capability
  remain experimental pending the external-provider benchmark.

## M2.5 reuse-first Workbench MVP — implemented and verified

- Existing Overview is now the primary Overview / Design surface; no second
  NiceGUI app, shell, action lifecycle, artifact viewer, CSS system, or parallel
  browser-owned domain state was created.
- Work Header shows title, active Part Job, accepted count, concise status, one
  recommendation, and a compact four-phase indicator.
- Intent, Design, Build & Evaluate, and Accept & Deliver are orientation derived
  from current Work/Part Job state, not four pages or a linear wizard.
- Primary information order is objective, recommendation, Agent activity,
  geometry, current result, validation/limitations, primary action, Part Jobs,
  detailed Workflow, then Advanced/Evidence.
- Agent activity maps persisted candidate/observation/reviewable/diagnostic
  evidence to concise product language. Raw provider traffic and private
  reasoning are not exposed.
- Deterministic STEP/STL uses the existing STL viewer. A registered, validated
  reviewable or accepted STEP can be converted to an ephemeral temporary STL
  presentation mesh for that same viewer; the mesh is not Work evidence or a
  deliverable.
- Reviewable Result distinguishes measured geometry, validation that actually
  ran, assumptions, important limitations, and unverified fit/strength/
  tolerance/motion claims.
- Accept calls the existing explicit acceptance route and reports success only
  after the persisted Part Job accepted pointer matches.
- Revise collects natural language, calls the existing revision route, and
  reports success only after one new attempt exists and prior acceptance is
  unchanged.
- Workflow remains a reachable detailed process view. Parts reuses the existing
  cards and preview details. History and immutable Run Snapshot remain
  reachable and read-only.
- Run/Episode/candidate/observation ids, artifact paths, Broker evidence,
  runtime/toolchain/attestation data, hashes, and raw validator evidence are
  under collapsed Advanced/Evidence.
- Product-critical English and Chinese copy is supplied by the existing
  `i18n.py` catalog.

Capability classification for M2.5:

- implemented: yes;
- automated verified: `179 passed` targeted and `644 passed, 9 skipped` in the
  complete suite on 2026-08-08;
- manually verified: deterministic compatibility, M2 reviewable geometry,
  Accept, accepted-result Revise, Agent activity, Advanced/Evidence, Workflow,
  Parts, History, and immutable Run Snapshot passed in the real in-app browser;
  1440px, 1024px, and 397px viewport evidence is saved under
  `docs/ux/screenshots/workbench-mvp/`;
- production usable: the local single-Part Job Workbench MVP is usable on the
  current host. The Agentic route remains experimental and the overall product
  is not production-ready until the external-provider M2 benchmark and later
  capability gates pass.

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
  artifact-reference based. Legacy stage/availability presentation is confined
  to compatibility reads and immutable Run Snapshot.
- Provider usage: different entry points do not consistently use the configured
  adapter.
- Revision: narrow field-level native CAD IR patches only.
- Assembly: planning helpers, bounding-box validation, and external FreeCAD
  scripts exist but are not a normal Assembly Job flow.
- Drawings: TechDraw helper exists but is not integrated into accepted-result
  Deliverable Packages.
- Browser usability: M2.5 real-browser acceptance passed for deterministic,
  reviewable, accepted, revision, Advanced/Evidence, Workflow, Parts, History,
  Run Snapshot, 1440px, 1024px, and mobile cases. M2.6 additionally passed the
  directly loadable Product Golden critical path in English and Chinese at
  1440px, 1024px, and 414px. Browser usability beyond the single-Part Job
  Workbench remains later-milestone scope.

## Not implemented

- Five non-template benchmark acceptance with a real external provider.
- Explicit user acceptance of at least one external-provider benchmark
  reviewable result and the final M2 acceptance record.
- General feature-graph geometry contract.
- Non-template general CAD design capability.
- Executable Assembly Job flow with accepted input identities.
- Integrated assembly STEP or native assembly deliverable.
- Integrated BOM and drawing package.
- Engineering release checks for fit, tolerance, motion, strength, DFM/DFA,
  GD&T, FEA, or safety.

## Code concentration risk

Current approximate Python line distribution:

- Workflow Console: 14.5k lines;
- Agent layer: 3.2k lines;
- CAD IR: 0.6k lines;
- CadQuery and backend layer: 0.5k lines.

The M2.9 audit measured `41,702` source Python lines across `79`
modules versus the `39,762`-line M2.8 baseline: `+1,940` lines (`+4.88%`) for
the registered Skill, bounded Work Episode, durable record/Orchestrator route,
API/UI projection, and compatibility integration. Tests moved from `15,409` to
`15,632` Python lines (`+223`), plus an 85-line deterministic acceptance script
and a 33-line Skill contract. No workflow engine, graph persistence, provider
framework, Assembly runtime, or new source module was introduced.

The largest source modules after M2.9 are `nicegui_app.py` (5,954),
`pipeline/runner.py` (4,344), `workflow_console/backend.py` (2,815),
`agents/episode.py` (1,913), `workflow_page_view_model.py` (1,841), and
`review_surface.py` (1,613). This is acceptable for the narrow milestone but is
a real concentration signal: the next change to Work Episode or graph behavior
should prefer focused extraction/reuse rather than extending these files with a
second runtime model.

The V1 consolidation measures approximately `42,945` source Python lines across
`82` modules, `81` top-level source classes, and `16,029` test lines with the
same counting method used by the pre-change audit (`42,338` source lines, `79`
modules, `81` top-level source classes, `15,935` test lines).
The `+598` source-line and `+3` module change reflects three narrow boundaries:
canonical interaction, registered-Skill request compilation, and neutral
provider sanitization. The largest files remain `nicegui_app.py` (6,840
physical lines), `pipeline/runner.py` (4,732), `backend.py` (3,125),
`agents/episode.py` (2,054), `workflow_page_view_model.py` (2,050), and
`product_usability.py` (2,028). This consolidation removed dead legacy Work
scanning helpers, but further decomposition of the NiceGUI and backend modules
remains warranted only when it closes a concrete product loop.

This reflects the former product priority. Further Workflow Cockpit polish is
not the current milestone unless required to preserve safe operation during
migration.

## Architecture conformance gaps

The following current behavior still does not conform to the target
architecture:

- flat closed-family CAD IR;
- deterministic fixed-action behavior in the current `create_part_ir`
  compatibility product path;
- compatibility Run Snapshot retains legacy fixed-stage presentation; normal
  Current Work Workflow does not;
- hard-coded capability labeling in reviewed-part results;
- multiple compatibility/evaluation entry points remain callable outside
  product authority;
- disconnected assembly and drawing utilities.

These are migration tasks, not accepted target behavior.

## Verification state

- V1 canonical consolidation passed on 2026-08-13 with `688 passed, 9 skipped`
  in the complete repository suite. Real NiceGUI verification covered Home,
  0-Part New Work, completed Work Design, multi-Part branches, focused
  clarification recovery, Part design, reviewable geometry and Accept,
  selected Workflow nodes, and immutable History. Chinese and English were
  exercised; 1440px, 1024px, and 414px had no page-level horizontal overflow;
  no browser warning/error was recorded. Eleven screenshots are under
  `../ux/screenshots/v1-canonical-consolidation/`. Browser verification exposed
  and then re-verified the isolated developer-Work index/detail resolver.
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
- M2.5 Workbench verification passed on 2026-08-08. The automated counts are
  recorded in the capability classification above; real-browser deterministic,
  reviewable, accepted, revision, Advanced/Evidence, secondary navigation,
  1440px, 1024px, and 397px checks passed with saved screenshots.
- M2.6 Product Golden verification passed on 2026-08-08. Focused tests passed
  with `148 passed, 2 skipped`; the complete suite passed with `657 passed,
  2 skipped`. Real-browser Product Golden, bilingual, Detailed Workflow,
  Accept, accepted-result Revise, Advanced/Evidence, 1440px, 1024px, and 414px
  checks passed with the ten requested screenshots.
- M2.8 Dynamic Work Graph verification passed on 2026-08-09. Current Work now
  projects request, Part Job, attempt, clarification/answer/resume,
  design/candidate/build, typed recovery, reviewable, accepted, and explicit
  revision nodes only when their durable evidence exists. Four canonical
  phases are orientation regions, not graph nodes. Historical Run Snapshots
  retain the read-only compatibility graph. Real NiceGUI browser verification
  passed for beginning, blocked, clarification/resume, reviewable, accepted,
  revision with the accepted pointer preserved, real two-Part branching,
  selected-node detail, Run Snapshot return, Chinese, 1440px, 1024px, and
  390px layouts; screenshots are saved under
  `../ux/screenshots/dynamic-work-graph/`. Focused verification passed with
  `84 passed`; the complete suite passed with `661 passed, 9 skipped`.
- The M2.8 Workflow Command Surface correction passed on 2026-08-09. Current
  Attention is now a derived per-Part presentation rather than a second global
  state; selecting request, active attempt, clarification, recovery,
  reviewable, accepted, or historical nodes exposes only commands already
  authorized by the Work/Part/Run/result domain. Historical Run Snapshots show
  the Run request, meaningful outcome, validation/stop state, and available
  geometry before the collapsed legacy compatibility graph. Real NiceGUI
  browser verification covered beginning Work, unanswered and answered
  clarification, retryable and unsupported stops, reviewable acceptance,
  accepted-result revision with the accepted pointer retained, two parallel
  Part attention points, and a read-only historical Run. Nine screenshots are
  saved under `../ux/screenshots/workflow-command-surface/`. Focused
  verification passed with `69 passed`; the complete suite passed with `663
  passed, 9 skipped`.
- The M2.8 UI convergence pass completed on 2026-08-09. Focused behavior tests
  passed with `32 passed`; the clean complete suite passed with `664 passed, 9
  skipped`. Real-browser verification and screenshots cover the simplified
  Overview, compact Current Attention, topology-first graph, nearby node
  inspector, all required owner states, and 1440px/1024px/414px layouts.
- M2.9 Work Design verification passed on 2026-08-10. The normal UI begins
  with the durable Work request and no Part Job, then a completed provider-
  selected Work Design is projected through CadFlow-owned decomposition into
  the exact real Part branches. The clean complete suite passed with `674
  passed, 9 skipped`; the deterministic multi-Part acceptance script reported
  `passed=true`, two generated Part Jobs, two reference components, no Assembly
  Job, and no accepted pointer. Real in-app browser checks covered the 0-Part
  action, completed Overview/Agent Output, visible Work path, bilingual copy,
  and 1440px/1024px/414px responsive layouts without page overflow or console
  warnings/errors.
- The M2.9 Workflow interaction-integrity correction passed on 2026-08-12.
  Selected Work Design, Part, attempt, recovery, and result nodes now project
  only evidence and actions owned by their exact durable Work/Part/Run/result
  scope. Workflow commands retain those exact target identities through
  confirmation and execution. Pending commands render an acknowledged Running
  state with duplicate protection, while typed Episode outcomes replace it with
  an honest reviewable, clarification, blocked, or failed terminal state. Real
  in-app browser verification covered independent Camera Cradle and Extrusion
  Adapter branches, exact empty/output states, exact retry targeting, reload
  reprojection, duplicate prevention, provider failure, and clarification
  answer/resume evidence. Focused verification passed with `109 passed, 1
  skipped`; the clean complete suite passed with `684 passed, 9 skipped`.
- M2.8 added only optional durable revision provenance on Part attempts because
  parent Run/result causality cannot be recovered honestly from prompt text,
  attempt order, or timestamps. No graph persistence, workflow engine, Agent
  framework, Provider abstraction, Assembly execution, Deliverables, or new
  security layer was introduced.
- The normal product entry creates a 0-Part Work and runs Work Design before
  durable Part Job creation. Legacy planning is not treated as hidden canonical
  decomposition, and multi-Part graph truth comes only from durable Part Jobs
  and their independent attempts/results.
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

M0 and M1 are complete. The M2 backend vertical slice is implemented through
reviewable publication and explicit accept/revise routes. The M2.5 Workbench,
M2.6 Product Golden, M2.7 onboarding/recovery, and M2.8 Dynamic Work Graph
product gates are complete. The external-provider M2 benchmark is now the
current milestone; M2 itself remains unaccepted until that benchmark and an
explicit user acceptance pass.

Delivery order:

1. run the M2 external-provider benchmark and explicit user acceptance;
2. preserve the completed M2.5–M2.9 and V1 consolidation product gates while fixing any
   benchmark-driven usability defects;
3. M3 feature-graph/model-program geometry paths;
4. M4 multi-Part Job and Assembly Job progression;
5. M5 integrated Deliverable Package and drawings;
6. M6 Workbench expansion beyond the current Work Design/Part Job MVP.

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
