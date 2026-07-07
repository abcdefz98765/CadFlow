# Desktop 2DOF Robot Arm Smoke Test

## Purpose

This smoke test verifies CadFlow's workflow-first handling of an incomplete
assembly-level CAD request. It is not a test for generating a complete robot arm
assembly.

The validated goal is to confirm that CadFlow can:

- recognize incomplete assembly-level natural-language requirements
- ask structured clarification questions
- block Planning before unresolved Requirement clarification is applied
- save structured user answers
- generate `requirement_v2.json`
- continue Planning from `requirement_v2.json`
- produce `assembly_plan.json`
- create a reviewed part request for one candidate part
- create a reviewed handoff
- call `AgentAdapter.create_part_ir(...)` for the reviewed part
- either validate a child `input_ir.json` and attempt STEP/STL, or safely block
  at `cad_ir_validation` when the generated CAD IR is unsupported

## Tested workflow

```text
Requirement
-> blocked Planning gate
-> requirement_clarification.json
-> requirement_v2.json
-> Planning
-> planning_artifact.json
-> assembly_plan.json
-> action_part_request
-> 02_part_request/part_create_request.json
-> action_part_review
-> 03_review/part_request_review.json
-> action_reviewed_handoff
-> 04_handoff/reviewed_part_handoff.json
-> action_reviewed_part_create
-> AgentAdapter.create_part_ir
-> cad_ir_validation blocked or child run attempted
```

## Test prompt

"帮我设计一个可以 3D 打印的桌面小机械臂，大概有两个关节，可以夹起小物体，结构简单一点，后续希望能装舵机。"

## Clarification answers used

- `arm_reach_mm`: `220`
- `degrees_of_freedom`: `2`
- `payload_target_g`: `100`
- `servo_reference_size_mm`: `40 x 20 x 40`
- `gripper_opening_mm`: `30`
- `actuator_type`: `standard 20kg hobby servo`
- `manufacturing_method`: `FDM 3D printing`
- `material`: `PLA or PETG`
- `gripper_type`: `simple parallel gripper or gripper mounting plate`
- `primary_generated_part`: `upper_link`
- `safety_note`: `desktop demonstration only, not production or safety critical`

## Expected artifacts

Expected to appear:

- `prompt.txt`
- `requirement.json`
- `logs/runtime.json`
- `requirement_clarification.json`
- `requirement_v2.json`
- `planning_artifact.json`
- `assembly_plan.json`
- `02_part_request/part_create_request.json`
- `03_review/part_request_review.json`
- `04_handoff/reviewed_part_handoff.json`
- `05_single_create/part_execution_request.json`
- `05_single_create/agent_trace.json`
- `05_single_create/report.json`

Expected if local/mock or provider returns supported CAD IR:

- `05_single_create/single_part_upper_link/input_ir.json`
- `05_single_create/single_part_upper_link/model.step`
- `05_single_create/single_part_upper_link/model.stl`

Expected if the generated IR is unsupported:

- `05_single_create/cad_ir_draft.json`
- `05_single_create/report.json` with `blocked_stage: cad_ir_validation`
- no child `input_ir.json`
- no child STEP/STL

Not expected in the current MVP:

- full robot arm assembly STEP
- automatic generation of all parts
- motion simulation results
- strength validation results
- real servo fit validation
- automatic batch run
- cloud collaboration state

## Expected current block

The current local/mock smoke path may block at `cad_ir_validation` for
`upper_link`, because robotic-arm link geometry is not yet a supported Part
Modeling backend family. This is expected MVP behavior when the trace clearly
shows that the reviewed-part workflow reached `AgentAdapter.create_part_ir(...)`
and the block is caused by invalid or unsupported agent-generated CAD IR.

Current checkpoint result:

- selected part: `upper_link`
- handoff: `ready_for_single_part_planning`
- reviewed create: `blocked_cad_ir_validation`
- blocked reason: `unsupported_part_type`
- `05_single_create/cad_ir_draft.json` exists
- draft `part_type`: `upper_link`
- child `input_ir.json` is not created
- `model.step` / `model.stl` are not created
- no fallback to `mounting_plate`

The smoke test should not be considered failed if CadFlow clearly blocks there,
as long as it does not fabricate robot arm CAD, does not fall back to
`mounting_plate`, and does not bypass workflow gates.

## Expected Web Console Review Surface

In the NiceGUI Workflow page, the primary user-facing surface should be
`Workflow Stage Review`, not a raw OpenNode/debug graph. The debug graph may
remain below the cards as `Debug / Raw Workflow Graph`.

Expected visible state for this smoke target:

- Requirement is completed or blocked-for-clarification with the original
  prompt, recognized robotic-arm intent, assumptions, missing information,
  follow-up questions, requirement flow decision, and raw `requirement.json`.
- Clarification shows `requirement_clarification.json` and
  `requirement_v2.json` after the structured answers are applied.
- Planning shows that it used `requirement_v2.json`, plus
  `planning_artifact.json`, flow gate status, blocked reasons, candidate parts,
  reference components, and raw planning artifact access.
- Assembly Plan shows `assembly_plan.json` with `upper_link` selected as a
  supported candidate and other parts/reference components visible.
- Part Request shows `02_part_request/part_create_request.json`.
- Part Review shows `03_review/part_request_review.json` when generated.
- Reviewed Handoff shows `04_handoff/reviewed_part_handoff.json`.
- Reviewed Part Create / CAD IR Draft shows
  `05_single_create/part_execution_request.json`,
  `05_single_create/cad_ir_draft.json`, and
  `blocked_cad_ir_validation` when validation blocks.
- Child `input_ir.json` is absent and explained when CAD IR validation blocks.
- Child `model.step` and `model.stl` are absent and explained when no child run
  is created.
- Review buttons are visible with disabled prerequisite reasons when upstream
  artifacts are missing.
- `Create / Refresh Workflow Review` can produce `workflow_review.json` and
  `workflow_review.md`.
- The raw artifact viewer may show editable override controls for allowlisted
  JSON artifacts such as `requirement_v2.json`, `assembly_plan.json`,
  `reviewed_part_handoff.json`, and `cad_ir_draft.json`. Saving an override
  must preserve the original artifact, write a versioned edit under `edits/`,
  validate the content, and mark affected downstream stages as user-modified or
  needing rerun.
- A `cad_ir_draft.json` override is still blocked unless it passes CAD IR
  validation. This does not add an `upper_link` template or a robot-arm CAD
  generator.

## Security expectations

- Default host remains `127.0.0.1`.
- Tailnet/LAN access is only an explicit configuration scenario.
- API keys must not be written to workspace artifacts.
- Public route responses must not expose provider raw payloads, chat
  transcripts, environment variables, or arbitrary local paths.
- The download whitelist must not be expanded for this smoke path.

## Current limitations

- no full robot arm assembly CAD
- no automatic all-part generation
- no motion simulation
- no strength validation
- no real servo/mechanical fit validation
- no free-form chat UI
- no multi-turn agent conversation
- no cloud/database/account system

## Next recommended capability

Implement a generic link-like / elongated-plate CAD IR family through the
CadIrAgent and Part Modeling backend. This should be a reusable part family for
simple links, tabs, and elongated plates, not a robot-arm-specific `upper_link`
template.

The next capability should move the workflow from:

```text
assembly_plan.json
-> part_create_request.json
```

to:

```text
reviewed_part_handoff.json
-> AgentAdapter.create_part_ir
-> validated input_ir.json
-> single part STEP/STL
```

It should not attempt full robot arm assembly generation.
