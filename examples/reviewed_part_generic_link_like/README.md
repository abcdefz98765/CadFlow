# Reviewed Part: Generic Link-Like Family

This example documents how the reviewed-part workflow normalizes the assembly
part intents `upper_link` and `lower_link` to the reusable `link_like_part` CAD
IR family. Both use the `elongated_plate_with_end_holes` geometry family; there
is no part-specific link template.

The input artifact is `reviewed_part_handoff.json`. Runtime artifacts are
produced by the existing reviewed-part pipeline and are intentionally not
committed here:

- `cad_ir_draft.json`
- child `input_ir.json`
- child `model.step`
- child `model.stl`
- `report.json`
- `agent_trace.json`
- `lineage.json`

The committed `*_expected_ir.summary.json` files are lightweight contract
summaries rather than executable CAD inputs or generated model files.

## Expected assertions

- `source_part_id` preserves `upper_link` or `lower_link`.
- `part_type` is `link_like_part`.
- `geometry_family` is `elongated_plate_with_end_holes`.
- The report scope is `single_generic_concept_part`.
- The result is one concept part, not a complete robot-arm assembly.
- There is no fallback to `mounting_plate`.
- There is no `upper_link` template or `lower_link` template.
- `lineage.json` continues to reference the reviewed handoff, selected part,
  part request/review, assembly plan, and child run.

The example makes no claim about strength, motion, servo fit, or production
readiness. Real CAD generation remains covered by the pipeline tests.
