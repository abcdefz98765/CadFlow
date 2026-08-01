# Sandboxed Model Program Skill

## Responsibility

Express geometry that is awkward or premature for the structured feature graph
as an untrusted CAD program using an allowlisted API.

## Actions

- generate or patch source within the declared CAD API;
- declare parameters, expected geometry, outputs, and evaluation targets;
- submit candidates for static checks and isolated execution;
- react to compiler, runtime, geometry, and validation observations;
- simplify, repair, change strategy, ask, or stop within budget.

## Required controls

- no arbitrary filesystem, network, shell, subprocess, credentials, or dynamic
  dependency installation;
- CPU, memory, wall-time, output-size, and attempt limits;
- read-only toolchain with an isolated working directory;
- explicit output allowlist;
- source retention and complete Run evidence;
- local geometry validation before reviewable status.

## Boundaries

Source text is never trusted merely because a provider produced it. This skill
has no acceptance authority and may not bypass the Tool Broker or sandbox.

## Current gap

CadQuery v1 is now the first selected model-program API. CadFlow implements a
Broker-owned, AST-only `validate_model_program_source` tool with versioned
imports, calls, entrypoint, syntax, and size limits. It returns source hash and
sanitized policy codes without retaining, importing, bytecode-compiling, or
executing source.

The `cadquery_v1` id versions this CadFlow source policy. An exact CadQuery,
Python, OCCT, and read-only worker-image version is not bound until the
enforceable worker is implemented and verified.

This is still a target runtime skill contract. The explicit Windows execution
gate enumerates required controls and returns `sandbox_unavailable` before any
source write or process start. The enforceable sandbox profile, execution
worker, runtime skill registration, Episode actions, product routing, geometry
inspection, and publication are not implemented. A static pass grants no
execution or trust authority.

## References

- `../../docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `../../docs/workflow_contract.md`
- `../../policies/model_program_cadquery_v1.md`
