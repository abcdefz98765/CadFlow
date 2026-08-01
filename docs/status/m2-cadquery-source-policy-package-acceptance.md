# M2 CadQuery Source-Policy Package Acceptance

Status date: 2026-08-01.

Scope: select `cadquery_v1` as the first model-program API, define its versioned
source contract, and route pure AST static validation through the CadFlow Tool
Broker without enabling model-program execution.

## Automated verification

Targeted command:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe -m pytest tests/test_model_program_policy.py tests/test_tool_broker.py tests/test_agent_registry.py tests/test_agent_episode.py tests/test_work_design_episode.py tests/test_workflow_console.py -q
```

Result:

```text
175 passed in 35.64s
```

Full command:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe -m pytest tests/ -q
```

Result:

```text
596 passed, 2 skipped in 379.72s (0:06:19)
```

The two skips remain opt-in/environment-gated existing tests.

## Manual file-level acceptance

Command:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe examples\provider_smoke\model_program_policy_eval.py
```

Observed summary:

```json
{
  "acceptance": "m2_cadquery_v1_static_source_policy",
  "execution_gate": {
    "candidate_directory_created": false,
    "observation_type": "sandbox_unavailable",
    "side_effect_started": false
  },
  "passed": true,
  "static_validation": {
    "api_id": "cadquery_v1",
    "entrypoint": "build_model(parameters)",
    "forbidden_source_codes": [
      "dangerous_call_not_allowed",
      "import_not_allowed"
    ],
    "side_effect_started": false,
    "source_retained": false,
    "valid_source_accepted": true
  }
}
```

## Capability judgment

- Implemented: selected CadQuery v1 API, fixed entrypoint contract, versioned
  imports/calls/prohibitions/limits, pure AST validator, Broker authorization,
  source hashing, sanitized typed violations, and static/execution gate
  separation.
- Automated verified: allowlisted source, import/call/module/private/dynamic/
  top-level/signature/return/syntax/size rejection, source redaction, skill and
  input authorization, internal-exception redaction, manifest declarations, and
  no execution bypass after a static pass.
- Manually verified: allowlisted source passed, `socket` and `open` were safely
  rejected without source retention, execution remained `sandbox_unavailable`,
  and no candidate directory was created.
- Production usable: the local pure static source-policy validator only. It is
  an internal validation service, not a provider Episode action or CAD runtime.

This acceptance does not verify a real external provider, source persistence,
bytecode compilation, CadQuery import, CAD execution, an enforceable Windows
sandbox, resource isolation, geometry correctness, STEP generation, reviewable
publication, acceptance, non-template benchmark success, or the complete M2
vertical slice.
