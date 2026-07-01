# Workflow Contract

CadFlow runs produce file-based artifacts. Future interfaces, including the Web Workflow Console, should consume these files instead of inventing separate state formats.

## Run Output Contract

Runs may live under either `runs/<run_id>/` or `outputs/<part_name>/`:

```text
runs/<run_id>/ or outputs/<part_name>/
  prompt.txt
  requirement.json
  planning_artifact.json
  input_ir.json
  model.py
  model.step
  model.stl
  preview.png
  report.json
  report.md
  agent_trace.json
  logs/runtime.json
```

Some files may be absent when a workflow gate blocks before CAD IR or model generation. For example, a requirement or planning block should still write `prompt.txt`, `requirement.json`, `report.json`, `report.md`, and `agent_trace.json`, but should not fabricate `input_ir.json`.

Future workflow gates may also produce `proceed_with_assumptions`, `ask_user`,
`return_to_requirement`, `return_to_planning`, or `revise_existing_model`
decisions. When a run proceeds with assumptions, the assumptions must be present
in structured artifacts and visible in reports or UI summaries.

## Artifact Roles

| Artifact | Role | Audience |
| --- | --- | --- |
| `prompt.txt` | Original user request | User-facing |
| `requirement.json` | Structured requirement contract | Developer-facing, advanced user-facing |
| `planning_artifact.json` | Structured planning handoff | Developer-facing, advanced user-facing |
| `input_ir.json` | Internal structured design contract | Developer-facing |
| `model.py` | Generated CadQuery model source | Developer-facing |
| `model.step` | Primary CAD artifact | User-facing, primary CAD output |
| `model.stl` | Derived mesh artifact | User-facing, derived CAD/mesh output |
| `preview.png` | Preview image, currently optional/scaffolded | User-facing |
| `report.json` | Machine-readable review result | Developer-facing |
| `report.md` | Human-readable review output | User-facing |
| `agent_trace.json` | Internal workflow/debug trace | Debug-only, advanced developer-facing |
| `logs/runtime.json` | Runtime details, timings, and local StageRunner status history | Debug-only |

## Revision Run Contract

Revisions create a new child run instead of overwriting the parent run:

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

Some revision artifacts may be absent until the revision workflow is
implemented. Their intended roles are:

| Artifact | Role | Audience |
| --- | --- | --- |
| `parent_run_id.txt` | Parent run pointer | Developer-facing |
| `revision_request.json` | Original revision request and parent context | Developer-facing, advanced user-facing |
| `change_intent.json` | Parsed change intent | Developer-facing |
| `revision_plan.json` | Proposed edit strategy and patch targets | Developer-facing, advanced user-facing |
| `patch.json` | Structured before/after changes | Developer-facing |
| `comparison.json` | Machine-readable old/new comparison | Developer-facing |
| `revision_report.md` | Human-readable revision summary | User-facing |
| `lineage.json` | Parent/child run relationship | Developer-facing, UI-facing |

Patches should record before/after values where possible. Comparison should
summarize old vs new dimensions, features, validation status, and changed
artifacts.

## Required Meaning

- `model.step` = primary CAD artifact.
- `model.stl` = derived mesh artifact.
- `input_ir.json` = internal structured design contract.
- `agent_trace.json` = internal workflow/debug trace.
- `report.md` = human-readable review output.

## Web Console Consumption

The future Web Workflow Console should read this contract directly:

- Run list from run/output directories.
- Status from `report.json` and `agent_trace.json`.
- User review from `report.md`.
- Workflow inspection from `requirement.json`, `planning_artifact.json`, `input_ir.json`, and `agent_trace.json`.
- CAD downloads from `model.step` and derived formats.
- Revision review from `revision_plan.json`, `patch.json`,
  `comparison.json`, `revision_report.md`, and `lineage.json` when present.

The v0.4a Python backend scaffold in `ai_native_cad.workflow_console` already follows this rule: it lists run directories, reads only whitelisted artifact files, derives status from existing report/trace artifacts, and reports downloadable files without creating a second state store.

For future HTTP routes, the backend has path-safe run-id operations that create or resolve a single directory name only under configured run roots, currently `outputs/` and `runs/`. These operations reject absolute paths, traversal, path separators, duplicate create targets, and unconfigured roots. Existing artifact files remain the source of truth; no database or separate state store has been introduced.

The backend also includes a dependency-free future route contract scaffold. It records intended route names, methods, path templates, by-id backend operation mappings, stable success/error envelopes, HTTP-like exception mapping, and an in-process dispatcher for route-name based tests without adding an HTTP server or framework dependency. Future route adapters must wrap only the by-id methods and must not expose direct local path APIs. Public route responses strip local path fields from metadata while preserving artifact JSON/text content.

For runs that stop before `report.json` exists, the backend may derive the latest local stage status from `logs/runtime.json` when `workflow_console.latest_stage` is present.

User gate decisions for future staged UI workflows are recorded in the same runtime artifact under `workflow_console.gate_decisions`. This keeps approve/reject/return/override history file-backed without expanding the public artifact whitelist.

Future UI edits are limited to structured workflow handoff artifacts: `requirement.json`, `planning_artifact.json`, and `input_ir.json`. The backend validates these JSON objects before writing and records edit history in `logs/runtime.json`; generated reports, traces, downloads, and prompts are not editable through this boundary.

The Web Console may cache or index metadata, but it should not become the authoritative workflow state store in v0.4.

## Immutability and Lineage

- Parent runs are immutable workflow records.
- Revisions create child runs.
- Child runs record `parent_run_id.txt` and `lineage.json`.
- Comparison artifacts identify the parent and child artifacts used.
- User-requested changes should be distinguishable from validation repair
  changes.
