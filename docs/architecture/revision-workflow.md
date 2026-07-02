# Model Revision Workflow

CadFlow should support iterative CAD work, not only first-time model creation.

Target flow:

```text
existing run/model + natural-language change request
  -> model intake
  -> editability analysis
  -> change intent parsing
  -> revision plan
  -> patch target selection
  -> regenerate or modify
  -> validate
  -> compare old vs new
  -> revision report
```

This is a staged product direction. The first implementation should focus on
CadFlow-native runs and patch-based revision. Full external STEP feature
recovery and mesh reverse engineering are non-goals for the near term.

## v0.6 MVP

The v0.6 MVP is CadFlow-native and starts from a parent run directory that
already contains `input_ir.json`.

```text
parent run + revision prompt
  -> change_intent.json
  -> revision_plan.json
  -> patch.json
  -> child input_ir.json
  -> run_ir_pipeline(...)
  -> comparison.json
  -> lineage.json
```

The implementation entry point is `run_agent_revision_pipeline(...)`.

The MVP patches CAD IR only. It does not edit external STEP/STL files, does not
integrate a real provider SDK, and does not execute arbitrary LLM-generated
code.

### Fake Revision Parser Scope

`DesignPlannerFakeAgentAdapter` is a deterministic local test adapter, not a
real LLM provider. Its v0.6 revision parser supports only small CadFlow-native
IR edits:

- Named numeric dimension replacement, such as `thickness to 6 mm`.
- Metric fastener hole requests, such as `M5`, mapped to a simple clearance
  diameter of nominal size plus 0.5 mm.
- Explicit hole diameter replacement, such as `hole diameter to 6 mm`.
- Chamfer removal when `features.chamfer` exists.

Current limitations:

- It does not understand arbitrary geometry edits.
- It does not add new topology or new unsupported feature families.
- It does not patch `model.py`.
- It does not edit STEP, STL, OBJ, or mesh files.
- It does not call a real provider SDK.
- It does not execute arbitrary LLM-generated code.

## Source Priority

### 1. CadFlow-Native Run

Highest priority.

If a parent run contains artifacts such as `requirement.json`,
`planning_artifact.json`, `input_ir.json`, `model.py`, `model.step`,
`report.json`, and `agent_trace.json`, CadFlow should revise it through
structured patches.

Preferred path:

```text
parent run
  -> revision request
  -> change intent
  -> requirement/planning/IR patch
  -> new child run
  -> validation
  -> comparison report
```

Example request:

```text
Take the previous mounting plate and make the holes M5, increase thickness to
6 mm, and remove the chamfer.
```

The workflow should produce a structured revision plan and patch before
regenerating the child run.

### 2. CadFlow IR + model.py

Also high priority.

If the user provides CadFlow-compatible `input_ir.json` and `model.py`, CadFlow
may treat the source as an editable native model after validation.

### 3. External STEP File

Medium priority.

STEP can be imported as reference geometry, but it usually lacks full modeling
history. CadFlow may:

- Measure bounding box.
- Inspect simple geometry.
- Detect some holes, planes, and cylinders when reliable.
- Use it as reference geometry.
- Create additive or subtractive operations when feasible.
- Create a new derived model.

Documentation and UI must clearly state that STEP import is limited direct
editing and reference-based editing, not robust parametric feature recovery.

### 4. STL / OBJ / Mesh Files

Low priority.

STL and OBJ should be treated as mesh references, not reliable CAD source files.
CadFlow may:

- Measure bounding box.
- Use the mesh as visual or reference geometry.
- Attempt simple approximation or reconstruction in later versions.

CadFlow must not promise robust parametric editing from STL or OBJ.

## Patch-First Revision

CadFlow should avoid this pattern:

```text
change request -> regenerate everything from scratch with no trace
```

Prefer:

```text
change request
  -> change intent
  -> patch target selection
  -> patch
  -> regenerate
  -> compare
```

Patch targets may include:

- Requirement patch.
- Planning patch.
- CAD IR patch.
- `model.py` patch for trusted CadFlow-compatible sources.
- External geometry operation for reference-based editing.

For CadFlow-native models, prefer CAD IR patch when the requested change maps
cleanly to dimensions or features.

Example patch:

```json
{
  "patch_type": "cad_ir_patch",
  "changes": [
    {
      "path": "dimensions.thickness",
      "before": 5,
      "after": 6,
      "reason": "User requested thicker plate"
    },
    {
      "path": "features.holes.diameter",
      "before": 4.5,
      "after": 5.5,
      "reason": "M5 clearance hole"
    }
  ]
}
```

## Revision Artifacts

Suggested child run structure:

```text
runs/<child_run_id>/
  parent_run_id.txt
  revision_request.json
  change_intent.json
  revision_plan.json
  patch.json
  requirement.json
  planning_artifact.json
  input_ir.json
  model.py
  model.step
  model.stl
  report.json
  report.md
  comparison.json
  revision_report.md
  agent_trace.json
  lineage.json
  logs/runtime.json
```

If the revision prompt cannot be converted into structured CAD IR changes
(`revision_plan.status` is not `ready_for_patch` or `patch.changes` is empty),
the run is recorded as blocked instead of generating a misleading child model.
Blocked revision runs still write `revision_request.json`, `change_intent.json`,
`revision_plan.json`, `patch.json`, `comparison.json`, `lineage.json`,
`report.json`, `report.md`, `revision_report.md`, and `agent_trace.json`.
They do not write child `input_ir.json`, `model.py`, `model.step`, or
`model.stl`.

Revisions should create new child runs. They must not overwrite parent runs.

`revision_request.json` records the user change request and parent context.
`change_intent.json` records parsed change intent. `revision_plan.json` records
the proposed edit strategy and target artifacts. `patch.json` records structured
before/after changes where possible. `comparison.json` summarizes old vs new
dimensions, features, validation status, and changed artifacts.
`revision_report.md` is the human-readable summary of parent, child, requested
changes, actual IR changes, validation status, and system repair changes.
`lineage.json` records parent/child relationships.

## Lineage Rules

- Every revision child run should record its parent run id.
- Parent runs remain immutable workflow records.
- Comparison should identify the parent and child artifacts used.
- Reports should distinguish user-requested changes from validation or repair
  changes.
- Patch records should include before/after values whenever the source artifact
  makes that possible.

## Non-Goals

This stage does not implement:

- Full LLM provider integration.
- Complete revision engine.
- Robust STEP feature recovery.
- STL reverse engineering.
- Arbitrary free-form LLM code execution.
- Full Web revision UI.
