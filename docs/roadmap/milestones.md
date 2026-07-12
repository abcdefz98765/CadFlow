# Workflow Cockpit Milestones

## Work / Run semantics and page contract

Completed: Current Work is an active-lineage aggregate; Run Snapshot is an
immutable, read-only audit mode. Workflow graph nodes, selected-stage detail,
and actions are supplied by one page view model. Each action declares scope and
target Run; `latest_attempt_run_id` never silently selects the active lineage.

Next: visual-system refinement, responsive screenshot review, and broader
Run-to-Run comparison UX.
