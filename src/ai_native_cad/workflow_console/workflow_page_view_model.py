"""Single, mode-safe view model for the Workflow cockpit page.

This module is intentionally the only place where Work lineage, immutable Run
snapshots, graph nodes, selected-stage detail, and action targets are assembled
for the NiceGUI Workflow page.  It reads backend projections only; it never
writes artifacts or infers lineage from browser state.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from ai_native_cad.workflow_console.review_surface import build_workflow_review_surface
from ai_native_cad.workflow_console.work_stage_projection import (
    build_work_stage_projection,
    unavailable_work_stage_projection,
)


ViewMode = Literal["current_work", "run_snapshot"]
_ATTENTION = {"blocked": "required", "needs_review": "required", "running": "in_progress", "stale": "required"}
_SELECTION_PRIORITY = ("blocked", "needs_review", "running", "stale")
_READ_ONLY_REASON = "Historical Run Snapshots are read-only. Return to Current Work or create a new Rework attempt."


def build_workflow_page_view_model(
    backend: Any,
    work_id: str,
    *,
    view_mode: ViewMode = "current_work",
    selected_run_id: str | None = None,
    selected_stage_id: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Build one coherent Workflow page for a Work or immutable Run snapshot."""
    if view_mode not in {"current_work", "run_snapshot"}:
        raise ValueError("workflow view mode must be current_work or run_snapshot")
    work = backend.get_work_detail(work_id)
    summary = work.get("summary") if isinstance(work.get("summary"), dict) else {}
    lineage = summary.get("active_lineage") if isinstance(summary.get("active_lineage"), dict) else {}
    active_root = lineage.get("active_root_run_id") or summary.get("root_run_id")
    if view_mode == "run_snapshot":
        if not selected_run_id:
            raise ValueError("a Run Snapshot requires selected_run_id")
        run = backend.read_run_metadata_by_id(selected_run_id, root=backend._work_runs_root(work_id))
        projection = None
        surface = build_workflow_review_surface(
            backend, selected_run_id, run, selected_stage_id=selected_stage_id, language=language,
        )
        source_run_id = selected_run_id
    else:
        try:
            projection = build_work_stage_projection(backend, work_id)
        except (FileNotFoundError, ValueError) as exc:
            projection = unavailable_work_stage_projection(work_id, type(exc).__name__)
        root_run = projection.get("root_run") if isinstance(projection.get("root_run"), dict) else {}
        surface = build_workflow_review_surface(
            backend, active_root if isinstance(active_root, str) else None, root_run,
            selected_stage_id=selected_stage_id, language=language, projection=projection,
        )
        source_run_id = active_root if isinstance(active_root, str) else None

    stages = [dict(stage) for stage in surface.get("stages", []) if isinstance(stage, dict)]
    selected = _select_stage(stages, selected_stage_id, view_mode)
    selected_id = selected.get("stage_id") if selected else None
    if selected is not None:
        selected = _stage_detail(selected, source_run_id, view_mode)
    graph = _workflow_graph(surface.get("workflow_graph"), stages, selected_id, projection, source_run_id)
    action_target = source_run_id
    actions = _scoped_actions(selected, view_mode, work_id, action_target)
    if selected is not None:
        selected["primary_action"] = actions["primary_action"]
        selected["secondary_actions"] = actions["secondary_actions"]
        selected["disabled_actions"] = actions["disabled_actions"]
    conclusion = _conclusion(surface, selected, summary, view_mode)
    return {
        "view_mode": view_mode,
        "read_only": view_mode == "run_snapshot",
        "read_only_reason": _READ_ONLY_REASON if view_mode == "run_snapshot" else None,
        "work": {"work_id": work_id, "title": summary.get("title") or work_id, "overall_status": summary.get("overall_status"), "summary": summary.get("next_action")},
        "active_lineage": lineage,
        "lineage_inferred": bool(lineage.get("lineage_inferred")),
        "viewed_run_id": selected_run_id if view_mode == "run_snapshot" else None,
        "run_strip": _run_strip(work.get("run_history"), lineage, view_mode, selected_run_id),
        "current_conclusion": conclusion,
        "recommended_next_action": actions["primary_action"],
        "workflow_graph": graph,
        "selected_stage": selected,
        "available_actions": actions,
        "empty_state": None if stages else {"title": "No workflow has started yet.", "summary": "Add a requirement to begin."},
        "error_state": None,
        # Compatibility/debug consumers can inspect the provenance without using
        # it to assemble another UI surface.
        "source": {"projection": projection, "surface": surface},
    }


def _select_stage(stages: list[dict[str, Any]], requested: str | None, view_mode: ViewMode) -> dict[str, Any] | None:
    if requested:
        found = next((stage for stage in stages if stage.get("stage_id") == requested or stage.get("key") == requested), None)
        if found:
            return found
    if view_mode == "run_snapshot":
        terminal = [stage for stage in stages if stage.get("status") in {"failed", "blocked"}]
        return terminal[0] if terminal else next((stage for stage in reversed(stages) if stage.get("status") != "not_started"), stages[0] if stages else None)
    for status in _SELECTION_PRIORITY:
        found = next((stage for stage in stages if stage.get("status") == status), None)
        if found:
            return found
    meaningful = [stage for stage in stages if stage.get("status") in {"completed", "completed_with_assumptions", "contract_complete", "execution_skipped"} and _first_enabled(stage)]
    if meaningful:
        return meaningful[-1]
    return next((stage for stage in stages if stage.get("status") in {"ready", "not_started"}), stages[-1] if stages else None)


def _workflow_graph(raw: Any, stages: list[dict[str, Any]], selected_id: str | None, projection: Any, fallback_source: str | None) -> dict[str, Any]:
    graph = deepcopy(raw) if isinstance(raw, dict) else {}
    by_id = {str(stage.get("stage_id") or stage.get("key")): stage for stage in stages}
    unavailable = isinstance(projection, dict) and bool(projection.get("diagnostics"))
    for section in ("stage_spine", "selected_part_pipeline", "review_tail"):
        nodes = graph.get(section) if isinstance(graph.get(section), list) else []
        graph[section] = [_stage_node(node, by_id.get(str(node.get("stage_id"))), selected_id, fallback_source, unavailable) for node in nodes if isinstance(node, dict)]
    candidates = graph.get("part_candidates") if isinstance(graph.get("part_candidates"), list) else []
    graph["part_candidates"] = [_part_node(item, "candidate_part") for item in candidates if isinstance(item, dict)]
    references = graph.get("reference_lane") if isinstance(graph.get("reference_lane"), list) else []
    graph["reference_lane"] = [_part_node(item, "reference_component") for item in references if isinstance(item, dict)]
    return graph


def _stage_node(node: dict[str, Any], stage: dict[str, Any] | None, selected_id: str | None, fallback_source: str | None, unavailable: bool) -> dict[str, Any]:
    stage = stage or {}
    stage_id = str(node.get("stage_id") or stage.get("stage_id") or stage.get("key") or "unavailable_stage")
    status = "unavailable" if unavailable else str(node.get("status") or stage.get("status") or "unavailable")
    label = str(node.get("label") or stage.get("stage_name") or stage_id.replace("_", " ").title())
    summary = str(node.get("short_summary") or stage.get("short_summary") or "Stage data unavailable")
    result = {
        **node,
        "stage_id": stage_id,
        "label": label,
        "kind": "review" if stage_id == "workflow_review" else ("rework" if stage_id == "rework" else "stage"),
        "status": status,
        "selected": stage_id == selected_id,
        "attention": _ATTENTION.get(status, "none"),
        "clickable": True,
        "source_run_id": stage.get("source_run_id") or fallback_source,
        "source_artifact_count": int(node.get("source_artifact_count") or len(stage.get("raw_artifacts") or [])),
        "short_summary": summary,
    }
    _validate_node(result)
    return result


def _part_node(item: dict[str, Any], kind: str) -> dict[str, Any]:
    status = str(item.get("status") or ("reference_only" if kind == "reference_component" else "ready"))
    selected = bool(item.get("selected"))
    if status == "selected":
        status = "ready"
    return {**item, "kind": kind, "status": status, "selected": selected, "attention": "required" if status == "blocked" else "none", "clickable": kind == "candidate_part"}


def _validate_node(node: dict[str, Any]) -> None:
    for field in ("stage_id", "label", "status", "short_summary"):
        assert node.get(field), f"workflow graph node requires {field}"


def _stage_detail(stage: dict[str, Any], fallback_source: str | None, view_mode: ViewMode) -> dict[str, Any]:
    detail = dict(stage)
    inputs = [item for item in detail.get("input_artifacts", []) if isinstance(item, dict) and item.get("present")]
    outputs = [item for item in detail.get("output_artifacts", []) if isinstance(item, dict) and item.get("present")]
    source_input = inputs[0] if inputs else {}
    source_output = outputs[0] if outputs else {}
    source_run = detail.get("source_run_id") or source_input.get("source_run_id") or fallback_source
    detail.update({
        "stage_id": detail.get("stage_id") or detail.get("key"),
        "conclusion": {"title": _nested(detail, "status_banner", "title") or detail.get("stage_name"), "summary": _nested(detail, "status_banner", "summary") or detail.get("human_summary") or detail.get("short_summary")},
        "user_input": {
            "summary": source_input.get("summary") or ("Inherited from an accepted upstream stage." if not inputs else "Accepted upstream workflow input."),
            "source_run_id": source_input.get("source_run_id") or source_run,
            "source_stage_id": _input_stage(detail.get("stage_id")),
            "source_type": "active_override" if detail.get("override_present") else "accepted_upstream_output",
            "editable": view_mode == "current_work" and bool(detail.get("override_present")),
            "stale_downstream": bool(detail.get("override_present")),
            "artifacts": inputs,
        },
        "agent_decision": {
            "summary": detail.get("human_summary") or detail.get("short_summary"),
            "decisions": detail.get("key_decisions_human") or [],
            "assumptions": detail.get("limitations_summary") or [],
            "interventions": [],
        },
        "agent_output": {
            "summary": source_output.get("summary") or ("No stage output is available yet." if not outputs else detail.get("short_summary")),
            "source_run_id": source_output.get("source_run_id") or detail.get("source_run_id") or fallback_source,
            "source_stage_id": detail.get("stage_id"),
            "validation_status": "passed" if detail.get("status") in {"completed", "contract_complete", "execution_skipped"} else detail.get("status"),
            "artifacts": outputs,
            "products": [item for item in outputs if item.get("name") in {"model.step", "model.stl"}],
        },
        "evidence": detail.get("important_artifacts") or [],
    })
    return detail


def _scoped_actions(stage: dict[str, Any] | None, view_mode: ViewMode, work_id: str, target_run_id: str | None) -> dict[str, Any]:
    groups = stage.get("action_groups") if isinstance(stage, dict) and isinstance(stage.get("action_groups"), dict) else {}
    actions = [dict(item) for group in groups.values() if isinstance(group, list) for item in group if isinstance(item, dict)]
    prepared = []
    for action in actions:
        backend_action = action.get("backend_action") or ("save_stage_review" if action.get("key") == "save_stage_review" else None)
        if backend_action:
            action["backend_action"] = backend_action
        creates_new_run = backend_action == "run_rework"
        enabled = bool(action.get("enabled"))
        if enabled and not backend_action and not action.get("presentation_action"):
            enabled = False
            action["disabled_reason"] = "This intervention requires structured input and is not available from this compact action yet."
        if view_mode == "run_snapshot" and backend_action and not creates_new_run:
            enabled = False
            action["disabled_reason"] = _READ_ONLY_REASON
        action.update({
            "enabled": enabled,
            "scope": "run_snapshot" if view_mode == "run_snapshot" else "current_work",
            "target_work_id": work_id,
            "target_run_id": target_run_id,
            "creates_new_run": creates_new_run,
            "updates_active_lineage": creates_new_run,
            "next_stage_on_success": _next_stage_for_action(backend_action or action.get("key"), stage.get("stage_id") if isinstance(stage, dict) else None),
        })
        prepared.append(action)
    enabled = [action for action in prepared if action.get("enabled")]
    primary = enabled[0] if enabled else None
    secondary = [action for action in enabled if action is not primary]
    return {"primary_action": primary, "secondary_actions": secondary, "disabled_actions": [action for action in prepared if not action.get("enabled")], "advanced_actions": []}


def _run_strip(history: Any, lineage: dict[str, Any], view_mode: ViewMode, viewed_run_id: str | None) -> list[dict[str, Any]]:
    result = []
    for index, item in enumerate(history if isinstance(history, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        run_id = item.get("run_id")
        result.append({
            **item,
            "display_label": f"Run {index}",
            "lineage_state": item.get("lineage_state") or "historical",
            "is_current": item.get("lineage_state") == "active",
            "read_only": view_mode == "run_snapshot" and run_id == viewed_run_id,
        })
    return result


def _conclusion(surface: dict[str, Any], stage: dict[str, Any] | None, summary: dict[str, Any], view_mode: ViewMode) -> dict[str, Any]:
    if view_mode == "run_snapshot":
        return {"title": "Historical Run Snapshot", "summary": "Read-only. This Run does not represent the complete current Work."}
    decision = surface.get("decision_panel") if isinstance(surface.get("decision_panel"), dict) else {}
    return {"title": "Current result", "summary": decision.get("decision") or (stage or {}).get("human_summary") or summary.get("next_action") or "Inspect the active Work lineage."}


def _first_enabled(stage: dict[str, Any]) -> bool:
    groups = stage.get("action_groups") if isinstance(stage.get("action_groups"), dict) else {}
    return any(item.get("enabled") for group in groups.values() if isinstance(group, list) for item in group if isinstance(item, dict))


def _input_stage(stage_id: Any) -> str | None:
    mapping = {"clarification": "requirement", "planning": "requirement", "assembly_plan": "planning", "part_request": "assembly_plan", "part_review": "part_request", "reviewed_handoff": "part_review", "cad_ir_draft": "reviewed_handoff", "part_modeling": "cad_ir_draft", "part_result_review": "part_modeling", "workflow_review": "part_result_review", "rework": "workflow_review"}
    return mapping.get(str(stage_id))


def _next_stage_for_action(backend_action: Any, stage_id: Any) -> str | None:
    targets = {
        "part_request": "part_review",
        "part_review": "reviewed_handoff",
        "reviewed_handoff": "cad_ir_draft",
        "reviewed_part_create": "part_result_review",
        "part_result_review": "workflow_review",
        "create_workflow_review": "rework",
        "run_rework": "workflow_review",
        "save_stage_review": "workflow_review",
    }
    return targets.get(str(backend_action)) or ("workflow_review" if stage_id == "workflow_review" else None)


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
