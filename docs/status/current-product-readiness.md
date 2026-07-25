# Current Product Readiness

Status date: 2026-07-25.

This document distinguishes the Agent-first target architecture from the
currently implemented workflow-first product.

## Target status

The authoritative target is now:

- Agent-first CAD design workbench;
- Intent, Design, Build & Evaluate, Accept & Deliver;
- provider-selected bounded design actions;
- structured feature-graph and sandboxed model-program candidate paths;
- first-class Part Job attempts and Assembly Job;
- accepted-result-derived STEP, assembly, BOM, and drawing packages.

This target is documented, not implemented.

## Implemented and usable now

- Local Workspace and Work creation.
- Append-only Run storage and active-lineage pointers.
- Initial Part Job and accepted part-result records.
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

- local deterministic supported-family single-part generation and review.

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

- Work / Part Job projection: Part Jobs do not yet own complete ordered attempt
  histories.
- Current Work state: parts of the projection still infer state through file
  discovery and compatibility heuristics.
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
- First-class Part Job attempt lists.
- Assembly Job with accepted input identities.
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

The following current behavior does not conform to the target architecture:

- fixed fifteen-checkpoint primary Workflow;
- flat closed-family CAD IR;
- deterministic fixed-action episode behavior;
- product-state inference from artifact filenames;
- singular Part Job `run_id` storage;
- hard-coded capability labeling in reviewed-part results;
- multiple competing create and execution paths;
- disconnected assembly and drawing utilities.

These are migration tasks, not accepted target behavior.

## Verification state

- Automated verified: full suite reports `541 passed, 2 skipped`.
- Verified meaning: the current deterministic workflow, console contracts,
  safety boundaries, and compatibility behavior are internally consistent.
- Not proven by those tests: Agent design breadth, provider-selected actions,
  sandbox security, non-template geometry success, multi-part assembly, or
  drawing-package usability.
- Manual browser verification: incomplete for the latest legacy Workflow
  Cockpit.
- Target architecture verification: not started.

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

M0 documentation correction is complete. Current implementation work begins at:

1. runtime and domain-model consolidation;
2. first provider-backed Agentic design vertical slice;
3. feature-graph geometry contract;
4. multi-Part Job and Assembly Job progression;
5. integrated Deliverable Package and drawings;
6. Agent-first workbench UX.

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
