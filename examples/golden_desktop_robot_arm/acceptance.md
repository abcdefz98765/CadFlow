# Golden Workflow Acceptance

## Artifact acceptance

- Every expected-summary JSON file parses successfully.
- Requirement starts as assembly scope, records missing information, and
  proceeds from a clarified `requirement_v2`.
- Planning uses assembly decomposition and identifies six candidate parts plus
  two reference components.
- `upper_link` is the selected candidate entering the reviewed-part pipeline.
- The reviewed handoff reaches `AgentAdapter.create_part_ir(...)` with assembly
  context preserved.
- The CAD IR preserves `source_part_id: upper_link` while using
  `part_type: link_like_part` and
  `geometry_family: elongated_plate_with_end_holes`.
- When CadQuery is available, the selected-part run produces `input_ir.json`,
  STEP, and STL evidence.
- The report scope is `single_generic_concept_part`, with
  `assembly_generated: false`.

## Web UI acceptance

- The Workflow graph shows the stage spine, candidate parts, reference lane,
  selected part pipeline, and review tail.
- The Requirement node provides a human summary of the requested object,
  assembly scope, manufacturing intent, and clarification state.
- The Assembly Plan node shows 6 candidates, 2 references, and selected
  `upper_link`.
- Candidate detail for `upper_link` shows its source intent and the generic
  family normalization to
  `link_like_part / elongated_plate_with_end_holes`.
- The Part Modeling node shows STEP/STL present when they were generated.
- The Evidence chain shows `cad_ir_draft.json`, `input_ir.json`, `model.step`,
  and `model.stl`.
- The Decision panel says the result is one single generic concept part, not a
  complete assembly.
- Raw diagnostics remain available for investigation but are not required for
  normal understanding of the workflow.

## Rejection conditions

Reject the example or implementation if it uses a dedicated `upper_link`
template, falls back to `mounting_plate`, bypasses CAD IR with provider code,
or claims that a full robot-arm assembly has been generated.
