# M2 WSL2 Model-Program Sandbox Package Acceptance

Date: 2026-08-02

Scope: internal Tool Broker execution primitive only. This acceptance does not
register a provider `model_program` skill, route source through `design_part` or
`WorkOrchestrator`, publish a reviewable result, change acceptance, or complete
M2.

## Host and runtime identity

- Host: Windows 10 build 26200.8875.
- WSL: 2.6.3.0; kernel 6.6.87.2-1.
- Dedicated distro: `CadFlow-Sandbox-CQ-v1`.
- Profile: `wsl2_cadquery_v1`.
- Profile digest:
  `0116438c5854c9a38d8bf7bf396fdc770c30f6cc2802ba62629ad4ed2b80fca4`.
- Toolchain digest:
  `26d9a74b393b25f1d2a5a25f9a4fecda873b790b42c1b27840b229e064a19b1f`.
- Acceptance probe attestation digest:
  `4f91ad473b251b3fa9e8c563ae8fcef6202757bd0b7b8a5f95b4c10d037b43d0`.
- Toolchain: Python 3.10.12, CadQuery 2.7.0, cadquery-ocp
  7.8.1.1.post1.

The repository manifest validator recomputed and matched both profile and
toolchain digests. Provisioning downloaded only during its explicit build
phase, finalized `/etc/wsl.conf` with DrvFs automount and Windows interop off,
sealed the runtime, and wrote the `ATTESTED` marker only after all active probes
passed.

## Isolation and attack probes

Every recorded probe returned `true`:

- candidate directory writable;
- directory escape denied;
- symlink write escape denied;
- root filesystem read-only;
- Windows drive and `/run/WSL` integration hidden;
- environment restricted to controlled names and values;
- private network and socket creation denied;
- subprocess, shell, pip/dynamic install, and fork denied;
- `NoNewPrivileges` active;
- CPU, memory, zero-swap, task-count, and output limits active;
- exported STEP re-import and corrupt-STEP rejection active.

The seccomp profile returns `ENOSYS` for `clone3`, allowing glibc pthreads to
fall back to `clone`; the fallback permits only `CLONE_THREAD`. Process-style
clone, fork, vfork, exec, socket, mount, namespace, ptrace, keyring, BPF, and
related authority remain denied. The targeted integration suite separately
proved CPU and memory exhaustion terminate within the configured bounds and
produce typed timeout/resource-limit failures without `model.step`.

## STEP execution evidence

The acceptance program created a non-template hexagonal solid with a central
bore through the fixed CadQuery worker.

- Source SHA-256:
  `026f4e352a0c3c127a01aaa5f7320819419b2638054b5c16114663eabecc566d`.
- Parameter SHA-256:
  `227358f00734174439954a0d785e0207c402450c0e750a9621b64f9074b8fb28`.
- STEP SHA-256:
  `c89513ea967c3d5ac5ba2828753b7f53fdbfaa940c4e9038d9704d9cd14a6bcb`.
- STEP size: 28,033 bytes.
- Geometry: valid, one solid, 9 faces, one cylindrical face, volume
  8657.074863772952 mm3, bounding box 42.0 x 36.37306695894643 x 8.0.
- The worker re-imported the exported STEP and matched solid count, bounding
  box within 0.01 mm, and volume within the declared absolute/relative limits.

The Broker evidence bound:

- Work `work_acceptance`;
- Run `run_acceptance`;
- Part Job `part_acceptance`;
- Episode `episode_acceptance`;
- candidate `acceptance_hex_bore`.

The acceptance used a temporary CadFlow-owned evidence root and removed it
after hashing. No host path was supplied by candidate source.

## Trust postconditions

- `reviewable=false`;
- `accepted=false`;
- `deliverable=false`;
- the pre-existing accepted-result pointer was byte-identical after execution;
- the pre-existing Deliverable Package was byte-identical after execution;
- failed and resource-limited executions contained no STEP product;
- no provider Episode or product orchestrator invoked the primitive.

## Verification commands

```powershell
F:\Tools\PowerShell\7\pwsh.exe -NoProfile -Command `
  '.venv-cadflow\Scripts\python.exe sandbox\wsl2\verify_manifest.py'

F:\Tools\PowerShell\7\pwsh.exe -NoProfile -Command `
  '$env:CADFLOW_MODEL_PROGRAM_SANDBOX="1"; `
  .venv-cadflow\Scripts\python.exe -m pytest `
  tests\test_wsl_sandbox_integration.py tests\test_wsl_sandbox.py `
  tests\test_tool_broker_wsl_integration.py `
  tests\test_model_program_runtime.py tests\test_tool_broker.py `
  tests\test_model_program_policy.py -q'

F:\Tools\PowerShell\7\pwsh.exe -NoProfile -Command `
  '$env:PYTHONPATH="src"; $env:CADFLOW_MODEL_PROGRAM_SANDBOX="1"; `
  .venv-cadflow\Scripts\python.exe sandbox\wsl2\acceptance.py'
```

Targeted result: `53 passed in 46.76s`.

Post-export re-import profile upgrade: `32 passed in 40.49s` targeted,
including live execution, active probes, resource limits, Broker protocol
checks, and STEP re-import evidence.

Full regression with the live sandbox explicitly enabled after the re-import
upgrade: `621 passed, 2 skipped in 519.80s`.

## Capability statement

- Implemented: dedicated pinned worker, active attestation, enforced execution
  controls, fixed protocol, STEP export/re-import comparison, and Broker
  candidate/diagnostic observations.
- Automated verified: manifest/tamper tests, contract/unit tests, live attack
  probes, real STEP execution, resource exhaustion, archive/evidence checks,
  and targeted regression.
- Manually verified: the current Windows/WSL2 host acceptance recorded above.
- Production usable: only as an explicitly enabled, attestation-constrained
  internal execution primitive. Agentic product design remains unavailable.
