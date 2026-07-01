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

The v0.4a Python backend scaffold in `ai_native_cad.workflow_console` already follows this rule: it lists run directories, reads only whitelisted artifact files, derives status from existing report/trace artifacts, and reports downloadable files without creating a second state store.

For future HTTP routes, the backend has path-safe run-id operations that resolve a single directory name only under configured run roots, currently `outputs/` and `runs/`. These operations reject absolute paths, traversal, path separators, and unconfigured roots. Existing artifact files remain the source of truth; no database or separate state store has been introduced.

For runs that stop before `report.json` exists, the backend may derive the latest local stage status from `logs/runtime.json` when `workflow_console.latest_stage` is present.

The Web Console may cache or index metadata, but it should not become the authoritative workflow state store in v0.4.
