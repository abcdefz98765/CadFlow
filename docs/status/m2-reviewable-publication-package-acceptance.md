# M2 Reviewable Publication Package Acceptance

Date: 2026-08-08
Host: current Windows/WSL2 development host
Runtime: dedicated `CadFlow-Sandbox-CQ-v1` only

## Scope

This acceptance covers the product-routed Work → provider-selected Episode →
Tool Broker → attested WSL2 worker → STEP re-import → CadFlow publication gate,
plus explicit accept and revise authority in a temporary test Work. It does not
cover a real external provider, the five-part benchmark, or user acceptance of
a benchmark reviewable result. M2 remains incomplete.

## Reproduction

```powershell
$env:PYTHONPATH = "src"
$env:CADFLOW_MODEL_PROGRAM_SANDBOX = "1"
.venv-cadflow\Scripts\python.exe examples\provider_smoke\reviewable_product_route_eval.py
```

The process used a credential-free scripted provider and a temporary
Workspace. Provider source ran only in the dedicated attested sandbox.

## Verified result

- status: passed;
- capability mode:
  `provider_selected_design_with_attested_model_program`;
- profile digest:
  `0116438c5854c9a38d8bf7bf396fdc770c30f6cc2802ba62629ad4ed2b80fca4`;
- toolchain digest:
  `26d9a74b393b25f1d2a5a25f9a4fecda873b790b42c1b27840b229e064a19b1f`;
- attestation digest:
  `abb1b0a0e25a792fa523a82c0d64097991a27a4741248ef0434f775a899a525a`;
- source hash:
  `026f4e352a0c3c127a01aaa5f7320819419b2638054b5c16114663eabecc566d`;
- parameter hash:
  `227358f00734174439954a0d785e0207c402450c0e750a9621b64f9074b8fb28`;
- STEP hash:
  `3dfc3bed636bb8995f9325b61bbe22eb72a03097fabfe0fec8891d4cf909826c`;
- STEP size: 28,033 bytes;
- source geometry: one valid solid, nine faces, one cylindrical face, volume
  8,657.074863772952 mm³, bounding box
  42.0 × 36.37306695894643 × 8.0 mm;
- STEP re-import geometry: one valid solid, volume
  8,657.074863771755 mm³, bounding box
  42.000000000006494 × 36.373066958943014 × 8.0 mm;
- publication response exposed capability mode, validation and geometry
  summaries, limitations, the assumption `Dimensions are in millimetres.`, and
  the single recommended action `Accept or revise`.

Before explicit acceptance, the acceptance record verified that active lineage,
accepted-result pointers, and Deliverable Packages were unchanged. Exact replay
made no second provider call and did not rewrite the Work. In the same temporary
test Work, the explicit acceptance route changed the accepted-result pointer;
the revision route then created a new attempt while preserving that pointer and
creating no Deliverable Package. These temporary mutations are route tests, not
the final user's M2 acceptance.

Automated verification passed `160` targeted Package 3 tests and the complete
suite at `644 passed, 2 skipped` in 576.21 seconds with live WSL2 enabled. The
dedicated WSL2 integration file passed `6` live tests, including the product
route and attack/resource-limit coverage.

Automated verification passed `160` targeted Package 3 tests and the complete
suite at `644 passed, 2 skipped` in 576.21 seconds with live WSL2 enabled. The
dedicated WSL2 integration file passed `6` live tests, including the product
route and attack/resource-limit coverage.

## Capability statement

- implemented: strict reviewable publication, product response, by-id explicit
  acceptance, and by-id revision;
- automated verified: publication/tamper/identity/route/replay tests and live
  WSL2 product integration;
- manually verified: this current-host scripted-provider acceptance;
- production usable: only as an attestation-constrained internal execution and
  publication primitive. The Agentic product path is not production usable
  until the external-provider benchmark and user acceptance gates pass.
