# Workflow Cockpit Milestones

## Work / Run semantics and page contract

Completed: Current Work is an active-lineage aggregate; Run Snapshot is an
immutable, read-only audit mode. Workflow graph nodes, selected-stage detail,
and actions are supplied by one page view model. Each action declares scope and
target Run; `latest_attempt_run_id` never silently selects the active lineage.

Completed: the Workflow Cockpit visual and interaction layer. It provides
centralized semantic UI tokens, a responsive dot-and-connector canvas, Run
lineage strip, Current Work/Snapshot hierarchy, causal three-part stage detail,
and Work-scoped History cards. Contract mode explicitly shows execution skipped
without implying missing model files.

Current: Product Usability Stabilization and Agent Episode Architecture
Acceptance. Implemented does not imply manually verified: Golden Contract/Full
flows, the Workflow cockpit, and deterministic episode shell are
automated-tested; browser interaction closure remains the release gate.

Next: (1) close UI action/review/artifact interaction contracts, (2) accept
Episode Phase 1.5 scripted dynamics, (3) prototype provider-backed
`create_part_ir` without changing CAD execution boundaries.
