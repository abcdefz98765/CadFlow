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

This is a target skill contract. CadFlow now has a typed Tool Broker definition
and an explicit Windows capability gate for the future execution tool. The gate
enumerates the required controls and returns `sandbox_unavailable` before any
source write or process start. The enforceable sandbox profile, execution
worker, runtime skill registration, and product routing are not implemented.

## References

- `../../docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `../../docs/workflow_contract.md`
