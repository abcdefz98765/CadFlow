# CadFlow

CadFlow is becoming an Agent-first CAD design workbench: the user describes an
engineering objective, an Agent explores and revises a design with controlled
CAD tools, and CadFlow turns accepted results into parts, assemblies, drawings,
BOMs, and traceable deliverables.

The repository already contains a useful deterministic CAD and workflow
foundation. The general Agentic design experience described below is the target
architecture, not a claim that every capability is implemented today.

## Product direction

The main user loop is:

```text
Intent
  -> Design
  -> Build & Evaluate
  -> Accept & Deliver
```

The Agent may:

- ask a focused engineering question;
- inspect accepted Work context;
- propose or compare design candidates;
- create or revise parts;
- plan and build an assembly;
- run allowlisted geometry and engineering checks;
- explain assumptions, evidence, and limitations;
- prepare deliverables from accepted results.

CadFlow retains control of:

- filesystem, network, process, and CAD execution authority;
- isolation, budgets, validation, and export policy;
- immutable Run evidence and parent/child lineage;
- accepted-result pointers;
- the distinction between measured, assumed, and unverified claims.

## Geometry strategy

CadFlow will support two complementary candidate paths:

1. a backend-neutral structured feature and assembly graph;
2. a sandboxed model program using an allowlisted CAD API.

Both paths converge on the same trust boundary:

```text
candidate
  -> source or contract validation
  -> isolated execution
  -> geometry inspection
  -> result validation
  -> reviewable result
  -> explicit acceptance
```

Provider output never receives unrestricted host authority. A successful build
does not automatically become an accepted result or deliverable.

## Canonical product objects

- **Workspace** — Works and safe configuration.
- **Work** — one mutable user-facing engineering objective.
- **Run** — one append-only attempt and audit record.
- **Part Job** — one intended part, its attempt Runs, and an accepted-result
  pointer.
- **Assembly Job** — exact accepted part inputs, assembly attempts, and an
  accepted-result pointer.
- **Deliverable Package** — accepted-result-derived models, assembly, BOM,
  drawings, and reports.

Current Work is actionable. Historical Run Snapshots are immutable and
read-only. Active design lineage and accepted results are related but distinct.

## Current implementation status

Implemented and useful today:

- typed Work and Run artifacts with immutable attempt history;
- deterministic CadQuery generation for the currently supported CAD IR;
- geometry validation, reports, STEP/STL export, and regression tests;
- provider adapters and a bounded but fixed-sequence proposal loop;
- a legacy NiceGUI Workflow Console;
- early Part Job, review, revision, and assembly-validation foundations.

Not yet implemented as a general product capability:

- a provider-controlled tool-using design episode;
- an enforceable sandbox for Agent-generated model programs;
- a generalized feature graph beyond the current closed part families;
- first-class Assembly Job execution and accepted assembly lineage;
- industrial drawing and complete deliverable packaging;
- the Agent-first Design Workbench UX.

See [current product readiness](docs/status/current-product-readiness.md) for
the authoritative and deliberately conservative status.

## Documentation authority

Read these before product work:

1. [Final PRD](docs/FINAL-PRD.md)
2. [Canonical product architecture](docs/architecture/cadflow-canonical-product-architecture.md)
3. [Current product readiness](docs/status/current-product-readiness.md)
4. [Design and artifact contract](docs/workflow_contract.md)
5. [Agent, skill, and knowledge architecture](docs/architecture/agent-skill-knowledge.md)
6. [Bounded design episodes and brokers](docs/architecture/bounded-agent-loop-context-broker-and-checkpoints.md)
7. [Roadmap](docs/roadmap/milestones.md)
8. [Task board](docs/tasks/task-board.md)
9. [Agent implementation start](docs/tasks/agent-start-here.md)

The old Workflow Console is a migration surface and diagnostics reference, not
the target product model.

## Repository layout

```text
src/ai_native_cad/
  agents/              provider adapters and episode infrastructure
  cad_ir/              current structured CAD contract
  pipeline/            deterministic build, validation, export, and reports
  workflow/            current Work/Run persistence and projections
  workflow_console/    legacy browser console
skills/                 CadFlow-owned Agent behavior contracts
knowledge/              shared engineering knowledge
policies/               global invariants and assurance policy
docs/                   product, architecture, UX, roadmap, and usage
tests/                  regression and contract tests
```

## Development setup

Python 3.10 or newer is required. CadQuery 2.4 or newer is the current CAD
backend dependency.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,web]"
$env:PYTHONPATH = "src"
python -m pytest tests/ -q
```

For current commands, environment variables, execution modes, and the legacy
console launcher, use [docs/usage.md](docs/usage.md).

## Contribution guardrails

- Do not answer general CAD capability requests by adding another
  product-specific `part_type` template by default.
- Do not turn internal artifact checkpoints into a mandatory user-facing
  wizard.
- Do not let provider-generated source bypass the Tool Broker, sandbox, or
  validators.
- Do not infer product state from filenames alone.
- Do not mutate historical Run evidence.
- Do not publish reviewable output as accepted output.
- Do not claim checks that did not run.

Documentation may describe the target before code exists only when readiness
and the roadmap state the gap explicitly.

## License

Apache-2.0.
