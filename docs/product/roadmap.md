# Roadmap

CadFlow's roadmap keeps the product boundary clear:

- LLM/Agent = understanding, planning, explanation.
- CadFlow Python API = deterministic execution.
- Web UI = operation, visualization, review.
- CadQuery/STEP = CAD backend and artifact output.

## v0.3

- CAD Agent Loop.
- Failure analysis.
- IR repair.
- Candidate scoring.
- Agent trace.

## v0.4

- Web Workflow Console baseline.
- Run existing workflow.
- List runs.
- Show artifacts.
- Show report and trace.

v0.4 is not a Web CAD editor. It is a Web Workflow Console for running and inspecting the existing CadFlow workflow.

## v0.5

Status: released as `v0.5.0` local deterministic, LLM-ready foundation.

- LLM-first UX clarification.
- AgentAdapter design planning.
- Assumptions and `proceed_with_assumptions` workflow.
- Focused confirmation flow documentation.
- Keep provider integration staged behind validated structured contracts.

## v0.6

- Revision Workflow for CadFlow-native runs.
- `revision_request.json`.
- `change_intent.json`.
- `revision_plan.json`.
- CAD IR patch.
- Child run lineage.
- Old/new comparison.

## v0.7

- Web revision UI.
- Select previous run.
- Submit revision prompt.
- Show patch diff.
- Show comparison.
- Show lineage.

## v0.8

- Model Intake for external files.
- STEP as reference geometry.
- STL/OBJ as mesh reference.
- Editability classification.

## v0.9

- Engineering CAD IR v2.
- Manufacturing context.
- Material context.
- Tolerances.
- Constraints.
- Design intent.
- Validation targets.

## v1.0

- Integrated natural-language create-and-revise CAD workflow.
- Web Workflow Console supports create, review, revise, compare, and lineage
  across artifact-backed runs.
- STEP remains the primary CAD artifact; mesh outputs remain derived preview or
  manufacturing aids.
