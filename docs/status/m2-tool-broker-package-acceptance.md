# M2 Tool Broker Package Acceptance

Status date: 2026-08-01.

Scope: CadFlow-owned Tool Broker catalog, Broker-owned local structured-contract
validation, and the explicit fail-closed Windows model-program capability gate.

## Automated verification

Targeted command:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe -m pytest tests/test_tool_broker.py tests/test_agent_registry.py tests/test_agent_episode.py -q
```

Result:

```text
23 passed in 0.27s
```

Full command:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe -m pytest tests/ -q
```

Result:

```text
565 passed, 2 skipped in 384.44s (0:06:24)
```

The two skips remain opt-in/environment-gated existing tests.

## Manual Windows acceptance

Command:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe examples\provider_smoke\tool_broker_gate_eval.py
```

Observed summary:

```json
{
  "acceptance": "m2_tool_broker_fail_closed",
  "model_program": {
    "available": false,
    "candidate_directory_created": false,
    "codes": ["sandbox_unavailable"],
    "observation_type": "sandbox_unavailable",
    "side_effect_started": false
  },
  "passed": true,
  "platform": "Windows",
  "structured_validation": {
    "execution_profile": "local_pure_validation_v1",
    "observation_type": "contract_validation_passed",
    "success": true
  }
}
```

## Capability judgment

- Implemented: typed Broker catalog, skill/tool authorization, structured
  validator routing, typed observations, episode Broker evidence, and an
  explicit Windows sandbox capability gate.
- Automated verified: authorization and input failures, validator exception
  redaction, Episode integration, mandatory-control completeness, and
  fail-closed model-program behavior.
- Manually verified: the Windows gate blocks before candidate-directory or
  process side effects while Broker-owned structured validation succeeds.
- Production usable: local structured-contract validation only, as part of the
  internal M2 preview. Provider model-program execution is unavailable.

This acceptance does not verify or enable an enforceable sandbox, provider CAD
source execution, STEP generation, reviewable-result publication, product
`WorkOrchestrator` routing, or the M2 benchmark gate.
