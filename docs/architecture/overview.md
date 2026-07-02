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
  -> user feedback / revision request
  -> child run and old/new comparison
```

The user-facing interaction is natural language. The internal pipeline remains structured and deterministic. LLM output must be converted into validated JSON contracts before it can affect execution. The execution layer must not rely on unconstrained free-form LLM behavior.

CadFlow is evolving from one-shot Text-to-CAD into an iterative natural-language
CAD workflow. The system should support incomplete initial intent, explicit
assumptions, focused clarification, exploratory drafts, user feedback, revision
planning, patch-based regeneration, and parent/child comparison.

## Layers

### User Interaction Layer

- Web Chat / Prompt UI
- Confirmation UI
- Artifact Viewer

This layer accepts natural-language intent, asks focused confirmation questions, and displays workflow status and artifacts. It should not expose CAD IR authoring as the default user path.

The user may start from a blank prompt, a previous CadFlow run, CadFlow IR plus
`model.py`, a STEP reference, or a mesh reference. The UI should route those
inputs through Model Intake before choosing a create or revise workflow.

### Agent Layer

- `AgentAdapter`
- stage agents such as `RequirementAgent`, `PlanningAgent`,
  `RepairAgent`, `ReviewAgent`, `RevisionIntentAgent`, and
  `RevisionPlanAgent`
- `DeterministicFallbackAgent`

This layer turns user language and workflow context into structured JSON. Agent output is advisory until it passes schema and workflow validation.

For iterative CAD, the agent layer also parses revision requests, proposes
change intent, drafts revision plans, proposes assumptions, and explains old/new
differences. CadFlow validates and normalizes these proposals before execution.

Provider-backed agents should be narrow and stage-specific. Each stage agent
uses a CadFlow-owned skill guide plus selected knowledge and an operation
contract guide before it calls an external provider. See
`docs/architecture/agent-skill-knowledge.md`.

### Workflow Layer

- Requirement
- Planning
- CAD IR
- Part Modeling
- Assembly
- Review
- Outputs

This layer defines stage boundaries and handoff gates. Users should not need to manually operate these stages, but the artifacts remain available for transparency and review.

Workflow gates should support more than proceed/return. They should allow
`proceed`, `proceed_with_assumptions`, `ask_user`,
`return_to_requirement`, `return_to_planning`, and
`revise_existing_model`, depending on check level, risk, and available model
context.

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

Revision workflows add child-run artifacts such as `revision_request.json`,
`change_intent.json`, `revision_plan.json`, `patch.json`,
`comparison.json`, `revision_report.md`, and `lineage.json`. Parent runs must
not be overwritten.

## Responsibility Boundary

- LLM/Agent: understanding, planning, repair suggestions, and review explanation.
- CadFlow Python API: deterministic workflow execution.
- Web UI: workflow operation, visualization, and review.
- CadQuery/STEP: CAD generation backend and primary artifact output.

These responsibilities should not collapse into each other. The Web Console should run and inspect the workflow, not become a CAD kernel. The agent should produce validated contracts, not arbitrary runtime code.

## Related Architecture Docs

- `docs/architecture/workflow-decisions.md`
- `docs/architecture/revision-workflow.md`
- `docs/architecture/model-intake.md`
- `docs/architecture/workflow-contract.md`
- `docs/architecture/agent-adapter.md`
- `docs/architecture/agent-skill-knowledge.md`
- `docs/architecture/web-workflow-console.md`
