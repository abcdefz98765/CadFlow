# M2 Work Design Episode Package Acceptance

Status date: 2026-08-01.

Scope: validation-only routing of an existing owned Part Job attempt through
`WorkOrchestrator` and `AgentDesignPort`, with append-only Run evidence,
idempotent request identity, and typed Work artifact references.

## Automated verification

Targeted command:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe -m pytest tests/test_work_design_episode.py tests/test_work_orchestrator.py tests/test_agent_registry.py tests/test_agent_episode.py tests/test_tool_broker.py tests/test_workflow_console.py -q
```

Result:

```text
156 passed in 35.15s
```

Full command:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe -m pytest tests/ -q
```

Result:

```text
574 passed, 2 skipped in 374.51s (0:06:14)
```

The two skips remain opt-in/environment-gated existing tests.

## Manual file-level acceptance

Command:

```powershell
$env:PYTHONPATH = "src"
.venv-cadflow\Scripts\python.exe examples\provider_smoke\work_design_episode_eval.py
```

Observed summary:

```json
{
  "acceptance": "m2_work_orchestrator_design_episode",
  "episode": {
    "artifact_reference_count": 4,
    "provider_call_count": 3,
    "stop_reason": "completed",
    "validated": true
  },
  "idempotency": {
    "replay": true,
    "work_manifest_unchanged_on_replay": true
  },
  "passed": true,
  "trust_boundary": {
    "accepted_artifact_count": 0,
    "deliverable_artifact_count": 0,
    "model_products": [],
    "original_run_prompt_unchanged": true,
    "protected_work_state_unchanged": true
  }
}
```

## Capability judgment

- Implemented: typed request/outcome/artifact contracts, one
  `AgentDesignPort`, Part Job attempt ownership checks, append-only episode
  evidence, idempotent replay, typed Work artifact registration, and protected
  state postcondition checks.
- Automated verified: successful and safely blocked routing, ownership rejection,
  conflicting request-id rejection, tampered evidence rejection, provider-policy
  failure redaction, mismatched port request/path identity rejection, no duplicate
  provider call, no model products, and unchanged lineage/acceptance/deliverable
  state.
- Manually verified: scripted-provider product routing, persisted evidence,
  idempotent replay, unchanged Work/Run evidence, and zero accepted,
  deliverable, STEP, STL, or model-program products.
- Production usable: only the local validation/evidence-registration boundary is
  usable. Provider-backed CAD execution and reviewable publication are
  unavailable.

This acceptance does not verify a real external provider, an enforceable
Windows sandbox, provider CAD source execution, STEP generation, reviewable
publication, explicit acceptance UI, non-template benchmark success, or the
complete M2 vertical slice.
