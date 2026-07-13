# Current Product Readiness

Status date: 2026-07-13. This is a capability and verification record, not a
promise that every visible control has completed manual browser acceptance.

## Usable now

- Workspace and Work creation with immutable Run storage and active-lineage
  pointers.
- Deterministic Golden Desktop Robot Arm flow in Contract and Full modes.
- One reviewed generic `link_like_part` with validated CAD IR; Full mode emits
  STEP/STL and Contract mode intentionally skips CAD execution.
- Work/Run lineage, controlled artifact reads, and the basic Workflow cockpit.

## Partially usable

- Candidate detail and selection semantics: implemented with a confirmation,
  validated versioned Assembly Plan override, stale downstream projection, and
  preserved old Runs/accepted results.
- Stage reviews and controlled artifact overrides: append-only per-stage review
  files plus latest `stage_review.json` materialization are implemented.
- Rework and artifact inspection: implemented for allowlisted contracts.
- Bounded agent episode shell: deterministic fallback and scripted dynamic
  action acceptance are automated-tested; no provider is connected.

## Not usable yet

- Full assembly generation, multi-part batch generation, motion/strength/fit
  validation, and provider-backed agentic CAD.
- Complete inline editing and all-browser manual acceptance coverage.

## Current risks

- A deterministic fallback can be mistaken for agentic capability unless the
  displayed `capability_mode` is reviewed.
- Any UI control without an explicit backend postcondition is a release blocker.
- Active-lineage ambiguity and review overwrite must remain covered by tests.
- Browser acceptance is local-environment dependent and must not be inferred
  from automated tests.

## Verification state

- Implemented: deterministic Golden flow, Workflow cockpit, controlled reads,
  reviews, and the bounded episode shell.
- Automated-tested: Golden contracts and targeted Workflow/Episode tests.
- Manually-verified: Full/Contract local Golden pages, candidate confirmation
  and stale feedback, artifact viewer, and read-only Snapshot were exercised
  in the local browser. Not every visible action or all breakpoint states has
  received exhaustive manual coverage.
- Production-usable: local deterministic single-part Golden workflow only;
  the cockpit readiness gate remains partial until full action inventory
  acceptance is completed.

## Next milestones

1. UI interaction closure.
2. Episode Phase 1.5 acceptance.
3. Provider-backed `create_part_ir` prototype.
