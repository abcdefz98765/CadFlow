"""Work-level workflow stage projection.

The Workflow page describes a Work, not the last immutable run selected in its
history.  Golden and reviewed-part workflows deliberately keep their evidence
in staged subdirectories and child runs, so this module projects those files
into one read-only lineage view without changing their on-disk locations.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_native_cad.workflow_console.backend import _sanitize_public_artifact_content
from ai_native_cad.workflow_console.work_index import build_work_index


STAGE_SPECS: tuple[dict[str, Any], ...] = (
    {"key": "requirement", "inputs": ("prompt.txt",), "outputs": ("requirement.json",)},
    {"key": "clarification", "inputs": ("requirement.json",), "outputs": ("requirement_clarification.json", "requirement_v2.json")},
    {"key": "planning", "inputs": ("requirement_v2.json", "requirement.json"), "outputs": ("planning_artifact.json",)},
    {"key": "assembly_plan", "inputs": ("planning_artifact.json",), "outputs": ("assembly_plan.json",)},
    {"key": "part_request", "inputs": ("assembly_plan.json",), "outputs": ("part_create_request.json",)},
    {"key": "part_review", "inputs": ("part_create_request.json",), "outputs": ("part_request_review.json",)},
    {"key": "reviewed_handoff", "inputs": ("part_create_request.json", "part_request_review.json"), "outputs": ("reviewed_part_handoff.json",)},
    {"key": "cad_ir_draft", "inputs": ("part_execution_request.json", "reviewed_part_handoff.json"), "outputs": ("cad_ir_draft.json",)},
    {"key": "part_modeling", "inputs": ("reviewed_part_handoff.json", "cad_ir_draft.json"), "outputs": ("part_execution_request.json", "cad_ir_draft.json", "lineage.json", "input_ir.json", "model.step", "model.stl")},
    {"key": "part_result_review", "inputs": ("reviewed_part_handoff.json", "lineage.json"), "outputs": ("part_result_review.json",)},
    {"key": "workflow_review", "inputs": ("report.json", "stage_review.json"), "outputs": ("workflow_review.json", "workflow_review.md")},
    {"key": "rework", "inputs": ("stage_review.json",), "outputs": ("rework_decision.json",)},
)

_KNOWN_NAMES = {name for spec in STAGE_SPECS for group in (spec["inputs"], spec["outputs"]) for name in group}
_KNOWN_NAMES.update({"golden_example.json", "report.json", "report.md", "stage_review.json"})


def build_work_stage_projection(backend: Any, work_id: str) -> dict[str, Any]:
    """Return a path-referencing stage view of all artifact-backed Work lineage."""
    index = build_work_index(backend)
    work = next((item for item in index["works"] if item["summary"].get("work_id") == work_id), None)
    if work is None:
        raise FileNotFoundError(f"workflow console work not found: {work_id}")

    active_lineage = work["summary"].get("active_lineage") if isinstance(work["summary"].get("active_lineage"), dict) else {}
    root_run_id = active_lineage.get("active_root_run_id") or work["summary"].get("root_run_id")
    runs = work.get("runs_by_id") if isinstance(work.get("runs_by_id"), dict) else {}
    active_run_ids = {
        run_id for run_id in (
            active_lineage.get("active_root_run_id"),
            active_lineage.get("active_leaf_run_id"),
            *(active_lineage.get("accepted_run_ids") or []),
        ) if isinstance(run_id, str) and run_id in runs
    }
    records = _discover_work_artifacts(backend, runs, root_run_id, active_run_ids or ({root_run_id} if root_run_id in runs else set()))
    execution = _execution_metadata(records)
    stages = {
        spec["key"]: _project_stage(spec, records, root_run_id, execution)
        for spec in STAGE_SPECS
    }
    root_run = runs.get(root_run_id) if isinstance(root_run_id, str) else {}
    return {
        "work_id": work_id,
        "root_run_id": root_run_id,
        "active_lineage": active_lineage,
        "stages": stages,
        # Presentation consumers use these sanitized, in-memory values to build
        # the same detail view as the graph. They are not artifact locations.
        "artifact_contents": _preferred_artifact_contents(records),
        "root_run": root_run if isinstance(root_run, dict) else {},
        "execution": execution,
    }


def unavailable_work_stage_projection(work_id: str, reason: str | None = None) -> dict[str, Any]:
    """Return an explicit non-blank fallback when lineage discovery fails."""
    return {
        "work_id": work_id,
        "root_run_id": None,
        "active_lineage": {"lineage_inferred": True},
        "stages": {},
        "artifact_contents": {},
        "root_run": {},
        "execution": {},
        "diagnostics": [reason or "Stage data unavailable"],
    }


def _preferred_artifact_contents(records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Use the same preferred lineage source as the per-stage references."""
    result = {}
    for name, items in records.items():
        item = next((candidate for candidate in items if "content" in candidate), None)
        if item is not None:
            result[name] = item["content"]
    return result


def _discover_work_artifacts(
    backend: Any,
    runs: dict[str, dict[str, Any]],
    root_run_id: str | None,
    active_run_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    records: dict[str, list[dict[str, Any]]] = {name: [] for name in _KNOWN_NAMES}
    for run_id in sorted(active_run_ids, key=lambda value: (value != root_run_id, value)):
        try:
            run_path = backend.resolve_run(run_id)
        except (FileNotFoundError, ValueError):
            continue
        for path in sorted((item for item in run_path.rglob("*") if item.is_file() and item.name in _KNOWN_NAMES), key=lambda item: item.as_posix()):
            relative = path.relative_to(run_path).as_posix()
            source_run_id = _source_run_id(run_id, relative)
            record = {
                "name": path.name,
                "source_run_id": source_run_id,
                "source_relative_path": relative,
                "present": True,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
            content = _read_content(path)
            if content is not None:
                # The projection feeds the interactive artifact viewer directly,
                # so apply the same public-content filter as the backend route.
                record["content"] = _sanitize_public_artifact_content(content)
            records[path.name].append(record)
    for name, items in records.items():
        records[name] = sorted(items, key=lambda item: _record_rank(item, root_run_id))
    return records


def _source_run_id(parent_run_id: str, relative: str) -> str:
    """Name the nested single-part/rework run when the artifact lives in one."""
    parts = Path(relative).parts
    for part in reversed(parts[:-1]):
        if part.startswith(("single_part_", "rework_", "revision_")):
            return part
    return parent_run_id


def _record_rank(item: dict[str, Any], root_run_id: str | None) -> tuple[int, int, str]:
    relative = str(item.get("source_relative_path") or "")
    return (0 if item.get("source_run_id") == root_run_id and "/" not in relative else 1, len(Path(relative).parts), relative)


def _read_content(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if path.suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return text


def _execution_metadata(records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    golden = next((item.get("content") for item in records.get("golden_example.json", []) if isinstance(item.get("content"), dict)), {})
    execution = golden.get("execution") if isinstance(golden, dict) and isinstance(golden.get("execution"), dict) else {}
    mode = golden.get("mode") if isinstance(golden, dict) else None
    skipped = bool(execution.get("execution_skipped")) or mode == "contract"
    return {"mode": mode or execution.get("mode"), "execution_mode": "contract" if skipped else "full", "execution_skipped": skipped}


def _project_stage(spec: dict[str, Any], records: dict[str, list[dict[str, Any]]], root_run_id: str | None, execution: dict[str, Any]) -> dict[str, Any]:
    inputs = _stage_artifacts(spec["inputs"], records)
    outputs = _stage_artifacts(spec["outputs"], records)
    present_outputs = [item for item in outputs if item.get("present")]
    key = spec["key"]
    status = "completed" if present_outputs else "not_started"
    if key == "part_modeling" and execution.get("execution_skipped"):
        status = "execution_skipped"
    elif key == "part_result_review" and execution.get("execution_skipped") and not present_outputs:
        status = "skipped"
    source = present_outputs[0] if present_outputs else (next((item for item in inputs if item.get("present")), None) or {})
    selected_part_id = _selected_part_id([*outputs, *inputs])
    child = next((item for item in outputs if item.get("name") in {"input_ir.json", "model.step", "model.stl"} and item.get("source_run_id") != root_run_id), None)
    if key == "part_modeling" and status == "completed" and not any(item.get("name") in {"model.step", "model.stl"} for item in present_outputs):
        status = "contract_complete" if execution.get("execution_mode") == "contract" else "completed"
    count = len({(item.get("source_run_id"), item.get("source_relative_path")) for item in [*inputs, *outputs] if item.get("present")})
    summary = _summary_for(key, status, count, selected_part_id)
    return {
        "status": status,
        "source_run_id": source.get("source_run_id"),
        "source_relative_path": source.get("source_relative_path"),
        "input_artifacts": inputs,
        "output_artifacts": outputs,
        "selected_part_id": selected_part_id,
        "child_run_id": child.get("source_run_id") if child else None,
        "summary": summary,
        "diagnostics": [],
        "execution_mode": execution.get("execution_mode"),
        "execution_skipped": bool(execution.get("execution_skipped")),
    }


def _stage_artifacts(names: tuple[str, ...], records: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    result = []
    for name in names:
        items = records.get(name) or []
        if items:
            result.extend({**item, "name": name} for item in items)
        else:
            result.append({"name": name, "present": False, "source_run_id": None, "source_relative_path": None})
    return result


def _selected_part_id(items: list[dict[str, Any]]) -> str | None:
    for item in items:
        content = item.get("content")
        if not isinstance(content, dict):
            continue
        for key in ("source_part_id", "selected_part_id", "part_id"):
            value = content.get(key)
            if isinstance(value, str) and value:
                return value
        request = content.get("part_request")
        if isinstance(request, dict) and isinstance(request.get("part_id"), str):
            return request["part_id"]
    return None


def _summary_for(key: str, status: str, count: int, part_id: str | None) -> str:
    if status == "not_started":
        return "Stage data unavailable" if count == 0 else "Stage has no output artifact."
    if status in {"execution_skipped", "contract_complete"}:
        return "CAD execution intentionally skipped after contract validation."
    if status == "skipped":
        return "Not applicable because CAD execution was intentionally skipped."
    suffix = f" for {part_id}" if part_id and key in {"part_request", "part_review", "reviewed_handoff", "cad_ir_draft", "part_modeling", "part_result_review"} else ""
    return f"Completed from {count} lineage artifact{'s' if count != 1 else ''}{suffix}."
