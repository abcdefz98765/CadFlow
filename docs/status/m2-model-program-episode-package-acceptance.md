# M2 Model-Program Episode Package Acceptance

Date: 2026-08-02  
Host: current Windows/WSL2 development host  
Runtime: dedicated `CadFlow-Sandbox-CQ-v1` only

## Scope

This acceptance covers the registered `design_part` v0.2 → `model_program`
v0.1 action loop, CadFlow-assigned identities, live Tool Broker execution,
structured observation inspection, and in-sandbox STEP re-import gate. It does
not cover reviewable publication, user acceptance, a real external provider, or
the five-part M2 benchmark.

## Reproduction

```powershell
$env:PYTHONPATH = "src"
$env:CADFLOW_MODEL_PROGRAM_SANDBOX = "1"
.venv-cadflow\Scripts\python.exe examples\provider_smoke\model_program_episode_eval.py
```

The process used a scripted action provider only; it invoked no provider
network and contained no credentials.

## Verified result

- status: passed;
- capability mode:
  `provider_selected_design_with_attested_model_program`;
- CadFlow identities: `candidate_001`, `observation_001`, one execution, one
  inspection;
- attestation digest:
  `72b824f60b5da537209a4caba76f449e29d291e6b272dd8d97dc5fdde289791b`;
- profile digest:
  `0116438c5854c9a38d8bf7bf396fdc770c30f6cc2802ba62629ad4ed2b80fca4`;
- toolchain digest:
  `26d9a74b393b25f1d2a5a25f9a4fecda873b790b42c1b27840b229e064a19b1f`;
- source hash:
  `026f4e352a0c3c127a01aaa5f7320819419b2638054b5c16114663eabecc566d`;
- parameter hash:
  `227358f00734174439954a0d785e0207c402450c0e750a9621b64f9074b8fb28`;
- STEP hash:
  `4cf93de774fec54d2d9b260e2a050bd568fc1da500aa62b36d8d319f57ae9410`;
- STEP size: 28,033 bytes;
- source geometry: one valid solid, nine faces, one cylindrical face, volume
  8,657.074863772952 mm³, bounding box 42.0 × 36.37306695894643 × 8.0 mm;
- re-import geometry: one valid solid, volume 8,657.074863771755 mm³,
  bounding box 42.000000000006494 × 36.373066958943014 × 8.0 mm;
- re-import comparison passed the 0.01 mm bounding-box and fixed
  absolute/relative volume tolerances.

Automated verification on the same host passed `47` targeted Episode/Broker/
product-port tests, `21` live Episode/WSL targeted tests, and the complete suite
at `633 passed, 2 skipped` in 516.74 seconds with live WSL2 enabled.

The acceptance also asserted that full source was absent from concise event
evidence and that no `reviewable_result.json`, accepted-result record, or
Deliverable Package was created. The standalone Episode has no authority to
mutate Work pointers. Existing automated product-route tests separately prove
protected Work/Run state and exact replay behavior.

## Capability statement

- implemented: provider-selected model-program actions, bounded observation
  repair loop, CadFlow identity assignment, execution-aware product evidence;
- automated verified: strict action/ordering/budget/evidence tests and live WSL
  integration tests;
- manually verified: this current-host scripted-provider live execution;
- production usable: no. The internal execution primitive is usable only under
  a valid attestation. Reviewable publication, explicit user acceptance, and
  the external-provider benchmark remain unavailable.
