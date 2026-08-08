# Compatibility / Multi-Part Planning Regression: Desktop 2DOF Robot Arm

Classification: **COMPATIBILITY / REGRESSION**.

This is not the canonical current Product Golden. It preserves coverage for the
former Requirement / Planning / reviewed-part / CAD IR / Workflow Cockpit
product and for historical multi-part planning projections.

This is a legacy Golden workflow contract, not a model asset library. It describes the
expected user-visible and artifact-level progression from an incomplete Work
prompt to one reviewed, normalized, generic concept part.

The example validates:

- requirement negotiation and structured clarification
- planning and assembly decomposition
- selection of one candidate part
- the reviewed-part request, review, and handoff gates
- generic-family CAD IR normalization
- generation of one `single_generic_concept_part`
- the expected Workflow Cockpit summary and evidence chain

The selected `upper_link` remains source intent and is normalized to
`link_like_part / elongated_plate_with_end_holes`. This example does not define
an `upper_link` template and never falls back to `mounting_plate`.

## Layout

`expected_workflow/` contains small expected-summary fixtures for seven workflow
stages. These files are not executable workflow artifacts and do not replace
the runtime schemas. They capture stable acceptance facts without committing
generated CAD binaries.

No STEP or STL is stored here. To exercise the real implementation, run the
existing desktop robot-arm manual smoke workflow or the reviewed-part pipeline
tests documented in `docs/smoke-tests/desktop-robot-arm.md`.

## Executable runner

The expected summaries are the specification. The runner below creates a real
Work and invokes the existing backend, actions, AgentAdapter, validation, and
pipeline stages:

```powershell
$env:PYTHONPATH='src'
.venv-cadflow\Scripts\python.exe scripts\run_golden_desktop_robot_arm.py `
  --workspace workspace\golden_demo `
  --mode contract
```

Use `--mode full` to execute CadQuery and require STEP/STL. `contract` mode is
the fast CI path: it reaches `AgentAdapter.create_part_ir`, validates the CAD
IR, writes the real child `input_ir.json`, and stops before CadQuery execution.
Both modes create `golden_comparison.json` and `golden_comparison.md` from
compact stable fields extracted from real artifacts.

The workspace path currently must be inside the project checkout because the
existing local CAD pipeline enforces project-root output containment.

## Load in the Detailed Workflow compatibility view

1. Run the executable example with a workspace path such as
   `workspace\golden_demo`.
2. Start the existing Workflow Console.
3. On the Workspace page, load that initialized workspace path.
4. Open **Golden Desktop Robot Arm**.

The Work manifest and root run are real file-backed workspace entities. The
Workflow graph, candidates, reference lane, reviewed-part stages, and review
tail are derived from their runtime artifacts rather than the expected-summary
fixtures.

Use **Open Product Example** on the Workspace page for the canonical current
Agent-first Workbench journey.

## Scope

A successful result means that one selected generic concept part was generated.
It does not mean the complete robot arm, every candidate part, servo fit,
motion, or strength was generated or validated. It does not create or execute a
canonical Assembly Job.
