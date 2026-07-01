# Architecture Overview

CadFlow follows a layered workflow:

```text
User natural language
  -> LLM / Agent Adapter
  -> structured requirement
  -> planning artifact
  -> CAD IR
  -> CadFlow Python API execution layer
  -> CAD Agent Loop
  -> STEP-first outputs
  -> Web Workflow Console display
```

The user-facing interaction is natural language. The internal pipeline remains structured and deterministic. LLM output must be converted into validated JSON contracts before it can affect execution. The execution layer must not rely on unconstrained free-form LLM behavior.

## Layers

### User Interaction Layer

- Web Chat / Prompt UI
- Confirmation UI
- Artifact Viewer

This layer accepts natural-language intent, asks focused confirmation questions, and displays workflow status and artifacts. It should not expose CAD IR authoring as the default user path.

### Agent Layer

- `AgentAdapter`
- `LLMRequirementAgent`
- `LLMPlanningAgent`
- `RepairAdvisorAgent`
- `ReviewExplainerAgent`
- `DeterministicFallbackAgent`

This layer turns user language and workflow context into structured JSON. Agent output is advisory until it passes schema and workflow validation.

### Workflow Layer

- Requirement
- Planning
- CAD IR
- Part Modeling
- Assembly
- Review
- Outputs

This layer defines stage boundaries and handoff gates. Users should not need to manually operate these stages, but the artifacts remain available for transparency and review.

### Execution Layer

- CadFlow Python API
- CAD Agent Loop
- CadQuery Generator
- Executor
- Validator
- Failure Analyzer
- IR Repair

This layer is deterministic. It consumes validated contracts, generates CadQuery code from CAD IR, executes the model, validates outputs, analyzes failures, and applies constrained IR repair.

### Artifact Layer

```text
requirement.json
planning_artifact.json
input_ir.json
model.py
model.step
model.stl
report.json
report.md
agent_trace.json
logs/runtime.json
```

Artifacts are the stable record of a run. `model.step` is the primary CAD artifact. `model.stl` is derived mesh output. `input_ir.json` is the internal structured design contract.

## Responsibility Boundary

- LLM/Agent: understanding, planning, repair suggestions, and review explanation.
- CadFlow Python API: deterministic workflow execution.
- Web UI: workflow operation, visualization, and review.
- CadQuery/STEP: CAD generation backend and primary artifact output.

These responsibilities should not collapse into each other. The Web Console should run and inspect the workflow, not become a CAD kernel. The agent should produce validated contracts, not arbitrary runtime code.
