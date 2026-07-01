# Model Intake

Model Intake classifies a model source before CadFlow chooses a create,
reference, or revision workflow.

It is a product and architecture concept for staged implementation. Full intake
logic is not required in the current deterministic baseline.

## Intake Output

Suggested contract:

```json
{
  "source_type": "cadflow_run | cadflow_ir | step | mesh | unknown",
  "editability": "high | medium | low | unsupported",
  "recommended_strategy": "...",
  "available_artifacts": [],
  "warnings": []
}
```

## Source Types

### CadFlow Run

`source_type`: `cadflow_run`

Editability: high.

Detected from an artifact-backed parent run containing files such as
`requirement.json`, `planning_artifact.json`, `input_ir.json`, `model.py`,
`model.step`, `report.json`, and `agent_trace.json`.

Recommended strategy: structured revision workflow with a new child run,
change-intent parsing, patch target selection, CAD IR patch when possible,
validation, comparison, and lineage.

### CadFlow IR + model.py

`source_type`: `cadflow_ir`

Editability: high when both files validate as CadFlow-compatible.

Recommended strategy: treat as a native editable source, normalize artifacts
into a run directory, then use patch-based revision.

### STEP

`source_type`: `step`

Editability: medium.

Recommended strategy: use as reference geometry or a base for limited derived
operations. CadFlow may measure bounding box, inspect simple geometry, and
detect some planes, holes, or cylinders when reliable.

Warnings should state that STEP usually does not contain full modeling history
and CadFlow does not promise robust parametric feature recovery.

### STL / OBJ / Mesh

`source_type`: `mesh`

Editability: low.

Recommended strategy: use as visual or dimensional reference. CadFlow may
measure bounding box and later attempt simple approximation, but should not
promise reliable CAD feature editing.

Warnings should state that STL/OBJ are mesh references, not dependable
parametric CAD sources.

### Unknown

`source_type`: `unknown`

Editability: unsupported until classified.

Recommended strategy: ask the user for a CadFlow run, IR, STEP, or mesh file;
otherwise route to new-model creation from prompt.

## UI Use

The Web Workflow Console should use Model Intake to explain what CadFlow can and
cannot edit before a revision run begins. Intake warnings should be visible in
the review panel and written into artifacts when a revision proceeds.
