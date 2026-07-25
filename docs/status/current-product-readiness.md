# Current Product Readiness

Status date: 2026-07-25.

This is a capability and verification record, not a promise that every visible control has completed manual browser acceptance.

## Usable now

- Local Workspace and Work creation with immutable Run storage and active-lineage pointers.
- Deterministic Golden Desktop Robot Arm in Contract and Full modes.
- One reviewed generic `link_like_part` with validated CAD IR; Full mode emits STEP/STL and Contract mode intentionally skips CAD execution.
- Work/Run lineage, controlled artifact reads, append-only reviews, and basic Workflow cockpit inspection.
- Deterministic bounded `create_part_ir` episode infrastructure.
- Explicit separation between accepted inputs, execution state, reviewable results, user approval, and accepted Work deliverables.
- Isolated candidate execution; terminal validation failure does not publish model source, STEP, STL, or preview product files.

## Partially usable

- Candidate detail and selection: implemented with confirmation, validated Assembly Plan override, stale downstream projection, and preserved old Runs/accepted results.
- Workflow write-action lifecycle: confirming, pending, succeeded, failed, duplicate-click protection, persistent feedback, and selected postcondition verification are implemented on the primary v2 path.
- Work-page navigation now rejects event objects and unknown pages, preserves the selected Work, and reaches the unified Workflow renderer from Overview, Parts, and History navigation.
- Workflow guidance and default information reduction are implemented in the unified page view model: each visible stage has bilingual user-facing purpose, conclusion, decision, next-action, result, recovery, and limitation fields; audit details are expandable.
- Stage Review and controlled artifact overrides are implemented with append-only history and compatibility materialization.
- Rework and revision exist for narrow allowlisted contracts, not general CAD editing.
- Bounded Agent Episode dynamic action behavior is automated-tested; no provider-backed agentic CAD is product-usable.

## Architecture status

Canonical current sources:

- `docs/architecture/cadflow-canonical-product-architecture.md`;
- `docs/architecture/agent-skill-knowledge.md`;
- `docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`;
- `docs/architecture/web-workflow-console.md`;
- `docs/architecture/revision-workflow.md`;
- `docs/workflow_contract.md`.

Superseded milestone architecture documents were removed rather than retained as competing current definitions.

Agent roles, skills, shared knowledge, skill-private knowledge, Work context, and Run observations now have explicit architectural ownership. The runtime still uses static mappings and summaries in `provider_context.py`; a typed skill/knowledge registry has not yet been implemented.

## Not usable yet

- Full assembly generation, multi-part batch generation, motion/strength/fit validation, and assembly STEP export.
- Provider-backed agentic `create_part_ir` as an accepted product path.
- Typed runtime skill and knowledge registry with enforced private/shared scopes.
- Complete inline editing and complete browser acceptance of every visible action.
- General external STEP editing or mesh reverse engineering.

## Current risks

- A deterministic fallback can be mistaken for agentic capability unless `capability_mode` is visible.
- Runtime static skill/knowledge summaries can drift from repository skill documents until one typed registry becomes authoritative.
- Any UI control without an explicit postcondition and visible feedback is a release blocker.
- Active-lineage, accepted-result, stale-state, and review-history semantics must remain covered by tests.
- Legacy Runs may contain product-looking files from failed attempts; projections must keep those files diagnostic and untrusted.
- Browser usability cannot be inferred from automated tests.

## Verification state

- Implemented: deterministic Golden flow, Workflow cockpit contracts, candidate selection, controlled reads/overrides, isolated candidate execution, reviewable-versus-accepted product projection, accepted-result pointer, and bounded episode shell.
- Automated verified: targeted state, product-trust, Workflow, and Golden regressions pass; the final full suite reports `541 passed, 2 skipped`.
- Manually verified: earlier Full/Contract pages, candidate confirmation and stale behavior, artifact viewer, and Snapshot boundaries were exercised.
- Not currently re-verified: the latest Workflow renderer, complete enabled-action inventory, successful Contract Golden selection, Run Snapshot, failure/recovery journey, 1024px layout, and 390–430px responsive pass. Earlier debug screenshots did not provide valid acceptance evidence and were removed from the product tree.
- Production usable: local deterministic single-part Golden workflow only. Workflow Cockpit readiness remains partial.

## Next milestones

1. Complete real-browser Workflow Cockpit action, localization, failure-path, and 1024px acceptance.
2. Implement the typed Agent Skill and Knowledge registry and remove duplicated runtime skill/knowledge definitions.
3. Prototype provider-backed bounded `create_part_ir` using the same validators and deterministic pipeline.
