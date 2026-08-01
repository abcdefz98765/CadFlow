# CadFlow Architecture Index

This directory contains the Agent-first target architecture. Git history
preserves the superseded fixed workflow-first design.

## Canonical product architecture

- `cadflow-canonical-product-architecture.md`

This is the authority for:

- Workspace / Work / Run / Part Job / Assembly Job / Deliverable Package;
- active lineage and accepted results;
- Current Work and Run Snapshot;
- four user phases and internal trust checkpoints;
- structured and sandboxed geometry candidate paths;
- product invariants and migration rules.

No specialized document may redefine these concepts.

## Specialized architecture

- `agent-skill-knowledge.md` — logical Agents, skills, tools, knowledge, runtime context, and provider boundaries.
- `bounded-agent-loop-context-broker-and-checkpoints.md` — provider-selected episodes, Context Broker, Tool Broker, sandbox, budgets, and typed stops.
- `domain-record-contracts.md` — schema-versioned Work, Part Job attempt,
  Assembly Job definition, Deliverable Package definition, artifact reference,
  and legacy manifest projection contracts.
- `runtime-entry-point-inventory.md` — classified runtime migration inventory
  for the single product orchestrator.
- `web-workflow-console.md` — Agent Workbench Web target and legacy NiceGUI migration boundary.
- `revision-workflow.md` — structured child-Run revision, patches, comparison, and external-source boundaries.

Accepted architecture decisions:

- `decisions/0001-single-product-orchestrator.md`

## Related current contracts

- `../workflow_contract.md` — artifact trust roles, candidate lifecycle, lineage,
  and compatibility contracts.
- `../ux/product-usability-principles.md` — user relevance, guidance, progressive disclosure, and feedback.
- `../ux/workflow-cockpit-design-spec.md` — Agent Workbench UX target; filename retained temporarily for compatibility.
- `../status/current-product-readiness.md` — implemented, verified, and usable capability status.

## Documentation rules

- Add a specialized architecture document only when it owns a stable technical
  concern not already covered.
- Do not create architecture files merely to record one milestone, correction, implementation pass, or screenshot review.
- Update an existing authority instead of appending a second competing definition.
- Remove superseded architecture after its content is absorbed; Git retains
  history.
- Roadmap and readiness belong under `docs/roadmap/` and `docs/status/`, not in architecture documents.
- Detailed API usage and commands belong in `docs/usage.md`.
- Implementation details belong near code or contracts when they are not architectural invariants.

When documents conflict, stop and resolve the conflict explicitly. Do not let implementation convenience choose the architecture silently.
