# Domain Record Contracts

Status: implemented and M1-accepted, schema date 2026-07-25; runtime acceptance
2026-07-27.

Authority:

- `cadflow-canonical-product-architecture.md`
- `../workflow_contract.md`
- `decisions/0001-single-product-orchestrator.md`

Implementation:

- `src/ai_native_cad/domain/records.py`
- `src/ai_native_cad/orchestration/work_orchestrator.py`
- `src/ai_native_cad/workflow_console/legacy_product_projector.py`

These records define manifest state only. They do not implement Agentic design,
Assembly generation, drawing generation, or a Workbench UI.

## Versioning

- Work manifest: `record_type: "work"`, `schema_version: 2`.
- Nested domain records and artifact references: `schema_version: 1`.
- Unknown future schema versions must fail closed until an explicit projector
  exists.

## Work v2

```json
{
  "record_type": "work",
  "schema_version": 2,
  "work_id": "fixture",
  "run_ids": ["fixture_root", "clamp_attempt_1"],
  "active_lineage": {
    "active_root_run_id": "fixture_root",
    "active_leaf_run_id": "fixture_root",
    "latest_attempt_run_id": "clamp_attempt_1",
    "superseded_run_ids": [],
    "accepted_run_ids": []
  },
  "part_jobs": [],
  "accepted_part_results": {},
  "assembly_job": null,
  "deliverable_packages": [],
  "artifact_references": []
}
```

`active_lineage.accepted_run_ids` is retained only as a v1 console
compatibility view. New acceptance code does not write it. Canonical accepted
part state exists only in `accepted_part_results`.

## Part Job and attempt

```json
{
  "record_type": "part_job",
  "schema_version": 1,
  "part_job_id": "clamp",
  "part_id": "clamp",
  "role": "moving jaw",
  "status": "incomplete",
  "source": "assembly_plan",
  "interface_context": {},
  "attempts": [
    {
      "record_type": "part_job_attempt",
      "schema_version": 1,
      "attempt_id": "clamp:1",
      "sequence": 1,
      "run_id": "clamp_attempt_1",
      "status": "incomplete",
      "artifact_ids": [],
      "created_at": "..."
    }
  ],
  "active_attempt_run_id": "clamp_attempt_1",
  "accepted_result_id": null,
  "stale_dependencies": []
}
```

Attempt order is append-only and contiguous. `active_attempt_run_id` identifies
the current design attempt. It is not an acceptance pointer.

## Accepted part result

```json
{
  "record_type": "accepted_part_result",
  "schema_version": 1,
  "result_id": "part_result:clamp:1",
  "part_job_id": "clamp",
  "attempt_run_id": "clamp_attempt_1",
  "run_id": "clamp_result_1",
  "review_id": "review_001",
  "artifact_ids": ["artifact:clamp_step"],
  "status": "approved",
  "accepted_at": "..."
}
```

Acceptance requires an existing Part Job attempt and known artifact ids. It
updates the Work pointer and the Part Job's `accepted_result_id`; it does not
change active lineage or rewrite a Run.

The `child_run_id` alias remains in the compatibility projection while the
legacy console consumes that name.

## Artifact reference

```json
{
  "record_type": "artifact_reference",
  "schema_version": 1,
  "artifact_id": "artifact:clamp_step",
  "work_id": "fixture",
  "run_id": "clamp_attempt_1",
  "part_job_id": "clamp",
  "assembly_job_id": null,
  "phase": "build_evaluate",
  "checkpoint": "reviewable_result",
  "trust_role": "reviewable_result",
  "relative_path": "products/clamp.step",
  "source_artifact_ids": [],
  "validation_status": "passed",
  "created_at": "..."
}
```

The relative path is controlled and secondary to `artifact_id`. Filename
presence never assigns trust or product status.

## Assembly Job definition

```json
{
  "record_type": "assembly_job",
  "schema_version": 1,
  "assembly_job_id": "fixture_assembly",
  "intent": {},
  "accepted_part_result_ids": ["part_result:clamp:1"],
  "reference_components": [],
  "attempts": [],
  "active_attempt_run_id": null,
  "accepted_result_id": null,
  "status": "defined"
}
```

This is an M1 schema only. No normal Assembly Job execution or assembly
deliverable is implemented.

## Deliverable Package definition

```json
{
  "record_type": "deliverable_package",
  "schema_version": 1,
  "package_id": "package:fixture:1",
  "source_accepted_result_ids": ["part_result:clamp:1"],
  "artifact_ids": ["artifact:clamp_step"],
  "status": "defined",
  "created_at": "...",
  "accepted_at": null
}
```

This is a versioned definition. M1 does not implement integrated BOM, drawing,
or Assembly package generation.

## Manifest-derived product state

`project_product_state` resolves:

- accepted part-result ids from explicit pointers;
- accepted artifacts from the pointer's artifact ids;
- deliverable artifacts from versioned package artifact ids;
- Assembly status from the Assembly Job record.

It performs no directory walk and receives no filename list. Unreferenced
`model.step`, drawing, or report files remain candidate or diagnostic evidence.

## v1 compatibility projection

The projector:

- maps `part_jobs[].run_id` to one ordered attempt;
- maps legacy `child_run_id` accepted results to stable compatibility result
  ids;
- preserves legacy active-lineage fields for existing console views;
- adds empty Assembly Job, Deliverable Package, and artifact-reference fields;
- does not inspect directories;
- does not write during read;
- never changes files inside a historical Run.

If a later valid Work mutation is persisted, the manifest is written as v2.
Legacy evidence with incomplete attempt ownership remains readable and is not
fabricated into stronger trust.

## Orchestration ownership

`WorkOrchestrator` is the only target-product coordinator that persists Work
mutations. Its current M1 commands own Work creation, Intent Run ownership,
planned and later Part Job attempts, candidate selection, active-lineage
changes, legacy attempt adoption, and accepted-result pointer changes. Its M2
validation-only design command also registers typed evidence produced for an
existing owned Part Job attempt; it is prohibited from changing lineage,
acceptance, Assembly Job, Deliverable Package, Part Job, or Run identity state.

The current deterministic execution service is reached through
`DeterministicCompatibilityPort`. Low-level workflow/evaluation entry points
remain callable for compatibility but do not establish target product state.

The provider-selected validation episode is reached through `AgentDesignPort`.
The concrete file adapter appends evidence under the owned attempt Run and
binds a path-safe request id to a canonical fingerprint. Exact retries replay
persisted evidence; conflicting reuse and incomplete evidence fail closed. The
orchestrator, not the port or provider, owns Work artifact-reference
registration and verifies protected state after every outcome.

The legacy Workflow Console projector may translate already-sanitized Run
metadata into in-memory artifact references for old Runs. It never writes
during read, and it never creates acceptance. Target product state is then
resolved from those references plus explicit manifest pointers.
