# CadFlow Architecture Index

This directory contains only current architecture. Git history preserves superseded designs and milestone corrections; do not keep competing current definitions in separate documents.

## Canonical product architecture

- `cadflow-canonical-product-architecture.md`

This is the authority for:

- Workspace / Work / Run / Part Job;
- active lineage and accepted results;
- Current Work and Run Snapshot;
- canonical checkpoint order;
- stage responsibility and product invariants.

No specialized document may redefine these concepts.

## Specialized architecture

- `agent-skill-knowledge.md` — logical agents, skill contracts, shared/private knowledge, Work context, and Run observations.
- `bounded-agent-loop-context-broker-and-checkpoints.md` — bounded episode orchestration, Context Broker, actions, budgets, and typed stops.
- `web-workflow-console.md` — local Web Console layers, view models, safe actions, artifacts, feedback, localization, and security.
- `revision-workflow.md` — structured child-Run revision, patches, comparison, and external-source boundaries.

## Related current contracts

- `../workflow_contract.md` — structured checkpoint artifact handoffs.
- `../ux/product-usability-principles.md` — user relevance, guidance, progressive disclosure, and feedback.
- `../ux/workflow-cockpit-design-spec.md` — current Workflow Cockpit UX specification.
- `../status/current-product-readiness.md` — implemented, verified, and usable capability status.

## Documentation rules

- Add a specialized architecture document only when it owns a stable technical concern that is not already covered.
- Do not create architecture files merely to record one milestone, correction, implementation pass, or screenshot review.
- Update an existing authority instead of appending a second competing definition.
- Remove superseded architecture from the current tree after its content is absorbed; Git retains history.
- Roadmap and readiness belong under `docs/roadmap/` and `docs/status/`, not in architecture documents.
- Detailed API usage and commands belong in `docs/usage.md`.
- Implementation details belong near code or contracts when they are not architectural invariants.

When documents conflict, stop and resolve the conflict explicitly. Do not let implementation convenience choose the architecture silently.