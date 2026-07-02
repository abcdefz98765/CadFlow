# Skills

This directory describes workflow skills used by the CAD agent.

Skills are organized by major workflow responsibility, not by CAD backend or
product type. Keep the list small: if a capability is only a helper for one
step, place it under that step's `knowledge/` directory.

```text
input
  -> requirement
  -> planning
  -> part_modeling
  -> assembly
  -> review
```

Each skill owns the rules, local knowledge, and prompts needed for its step.
Shared policies stay in `policies/`; top-level `knowledge/` is only an index
for cross-skill knowledge.

For provider-backed agents, a skill is also runtime context. CadFlow should send
the current stage's skill guide, operation contract guide, and selected compact
knowledge summary to the provider. It should not send every skill or the whole
knowledge tree by default.

## Current Status

- `requirement/`: requirement elicitation, product intent, early decomposition,
  check-level field policy, and missing-information behavior.
- `planning/`: design analysis, workflow routing, datums, interfaces, risk, and
  confirmation gates before geometry generation.
- `part_modeling/`: template-backed part generation and the single-part closed
  loop.
- `assembly/`: part relationships, contacts, clearances, serviceability,
  backend-neutral assembly configs, and assembly validation.
- `review/`: check-level report organization for parts and assemblies.

Export/output behavior is a shared policy in `policies/output_contract.md`, not
a standalone skill.

See `docs/architecture/agent-skill-knowledge.md` for the provider-facing
agent/skill/knowledge architecture.
