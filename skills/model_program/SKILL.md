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

## Current implementation boundary

CadQuery v1 is now the first selected model-program API. CadFlow implements a
Broker-owned, AST-only `validate_model_program_source` tool with versioned
imports, calls, entrypoint, syntax, and size limits. It returns source hash and
sanitized policy codes without retaining, importing, bytecode-compiling, or
executing source.

The repository now also contains an internal `wsl2_cadquery_v1` worker profile
with pinned Python/CadQuery/OCP dependencies, content digests, active
attestation, seccomp, systemd isolation, resource limits, fixed STEP export,
isolated STEP re-import comparison, and Broker-owned candidate/diagnostic
evidence. It is available only after an
exact dedicated WSL2 distro passes the trusted startup probe; otherwise the
Broker remains fail closed.

This is now the registered CadFlow-owned `model_program` v0.1 delegate of
`design_part` v0.2. The provider may create or fully replace source and
parameters, request execution of only the current CadFlow-assigned candidate,
and inspect only the latest uninspected observation. CadFlow assigns every
candidate, observation, execution, lineage, and evidence identity and enforces
separate budgets. Successful internal execution does not itself make a result
reviewable, accepted, or deliverable. The product route now has a separate
CadFlow-owned publication gate that can promote only fully cross-checked
evidence to reviewable status. Explicit user acceptance and the benchmark gate
remain outside this skill's authority.

## References

- `../../docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md`
- `../../docs/workflow_contract.md`
- `../../policies/model_program_cadquery_v1.md`
