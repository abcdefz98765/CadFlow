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
from ai_native_cad.workflow_console.i18n import action_labels, action_label
from ai_native_cad.workflow_console.work_stage_projection import (
    build_work_stage_projection,
    unavailable_work_stage_projection,
)


ViewMode = Literal["current_work", "run_snapshot"]
_ATTENTION = {"blocked": "required", "needs_review": "required", "running": "in_progress", "stale": "required"}
_SELECTION_PRIORITY = ("blocked", "needs_review", "running", "stale")
_READ_ONLY_REASON = "Historical Run Snapshots are read-only. Return to Current Work or create a new Rework attempt."
_REVIEW_DECISION_ACTIONS = {"save_stage_review", "approve_stage", "mark_needs_revision", "mark_blocked"}
_AGENT_REVIEW_ACTIONS = {"part_review", "part_result_review", "create_workflow_review"}


def _artifact_kind(name: str) -> str:
    """Return the UI kind used by the single artifact-viewer contract."""
    if name.endswith(".json"):
        return "json"
    if name.endswith(".md"):
        return "markdown"
    if name.endswith(".step"):
        return "step"
    if name.endswith(".stl"):
        return "stl"
    return "text"


def _artifact_display_name(name: str) -> str:
    names = {
        "workflow_review.json": "Workflow review",
        "workflow_review.md": "Workflow review summary",
        "stage_review.json": "Stage review decision",
        "part_result_review.json": "Part result report",
        "report.json": "Run report",
        "report.md": "Run report summary",
        "model.step": "STEP model",
        "model.stl": "STL model",
    }
    return names.get(name, name)


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
    graph = _workflow_graph(surface.get("workflow_graph"), stages, selected_id, projection, source_run_id, work_id, view_mode, language)
    action_target = source_run_id
    actions = _scoped_actions(selected, view_mode, work_id, action_target, language)
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
        "action_inventory": _action_inventory(actions, graph),
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


def _workflow_graph(
    raw: Any,
    stages: list[dict[str, Any]],
    selected_id: str | None,
    projection: Any,
    fallback_source: str | None,
    work_id: str,
    view_mode: ViewMode,
    language: str,
) -> dict[str, Any]:
    graph = deepcopy(raw) if isinstance(raw, dict) else {}
    active_plan = (
        projection.get("artifact_contents", {}).get("assembly_plan.json")
        if isinstance(projection, dict) and isinstance(projection.get("artifact_contents"), dict)
        else None
    )
    if isinstance(active_plan, dict) and isinstance(active_plan.get("selected_part_id"), str):
        graph["selected_part_id"] = active_plan["selected_part_id"]
    by_id = {str(stage.get("stage_id") or stage.get("key")): stage for stage in stages}
    unavailable = isinstance(projection, dict) and bool(projection.get("diagnostics"))
    for section in ("stage_spine", "selected_part_pipeline", "review_tail"):
        nodes = graph.get(section) if isinstance(graph.get(section), list) else []
        graph[section] = [_stage_node(node, by_id.get(str(node.get("stage_id"))), selected_id, fallback_source, unavailable) for node in nodes if isinstance(node, dict)]
    candidates = graph.get("part_candidates") if isinstance(graph.get("part_candidates"), list) else []
    selected_candidate = graph.get("selected_part_id")
    candidates = [
        {**item, "selected": item.get("part_id") == selected_candidate, "current": item.get("part_id") == selected_candidate}
        for item in candidates if isinstance(item, dict)
    ]
    graph["part_candidates"] = [_part_node(item, "candidate_part", work_id, fallback_source, view_mode, language) for item in candidates if isinstance(item, dict)]
    references = graph.get("reference_lane") if isinstance(graph.get("reference_lane"), list) else []
    graph["reference_lane"] = [_part_node(item, "reference_component", work_id, fallback_source, view_mode, language) for item in references if isinstance(item, dict)]
    for lane in ("part_candidates", "reference_lane"):
        for candidate in graph.get(lane, []):
            candidate["source_run_id"] = fallback_source
            candidate["current_selected_part_id"] = graph.get("selected_part_id")
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


def _part_node(item: dict[str, Any], kind: str, work_id: str, target_run_id: str | None, view_mode: ViewMode, language: str) -> dict[str, Any]:
    status = str(item.get("status") or ("reference_only" if kind == "reference_component" else "ready"))
    selected = bool(item.get("selected"))
    if status == "selected":
        status = "ready"
    part_id = str(item.get("part_id") or "")
    reference = bool(item.get("reference_only")) or kind == "reference_component"
    selectable = view_mode == "current_work" and bool(item.get("supported_candidate")) and not reference and not selected
    target = f"当前 Work · Run {target_run_id or '不可用'} · 装配计划" if language == "zh" else f"Current Work · Run {target_run_id or 'unavailable'} · Assembly Plan"
    actions = [
        {
            "key": "open_candidate_detail",
            "label": action_label(language, "Open Candidate Detail"),
            "label_i18n": action_labels("Open Candidate Detail"),
            "enabled": bool(part_id),
            "category": "navigation",
            "scope": "run_snapshot" if view_mode == "run_snapshot" else "current_work",
            "target_work_id": work_id,
            "target_run_id": target_run_id,
            "target_stage_id": "assembly_plan",
            "tooltip": (f"打开 {part_id} 的候选零件详情。\n\n目标: {target}\n\n结果：只读查看；不会改变 Work 指针、候选选择或 Run。" if language == "zh" else f"Open Candidate Detail for {part_id}.\n\nTarget: {target}\n\nResult: read-only inspection; no Work pointer, candidate selection, or Run changes."),
        },
        {
            "key": "select_candidate_part",
            "label": action_label(language, "Use This Part Next"),
            "label_i18n": action_labels("Use This Part Next"),
            "enabled": selectable,
            "category": "structured_input",
            "scope": "run_snapshot" if view_mode == "run_snapshot" else "current_work",
            "target_work_id": work_id,
            "target_run_id": target_run_id,
            "target_stage_id": "assembly_plan",
            "part_id": part_id,
            "requires_confirmation": True,
            "creates_new_run": False,
            "updates_active_lineage": False,
            "disabled_reason": (
                ("历史 Run 快照只读；请返回当前 Work。" if language == "zh" else _READ_ONLY_REASON) if view_mode == "run_snapshot" else
                ("参考组件不能用于生成。" if language == "zh" else "Reference components cannot be selected for generation.") if reference else
                ("该候选零件已被选择，无需重复覆盖。" if language == "zh" else "This candidate is already selected; no duplicate override is needed.") if selected else
                ("当前单零件流程不支持该候选零件。" if language == "zh" else "This candidate is not supported by the current single-part workflow.")
            ) if not selectable else None,
            "tooltip": (f"确认后将 {part_id} 用于下一次零件请求。\n\n目标: {target}\n\n结果：写入经过验证的版本化装配计划覆盖版本，保留旧 Run，并标记下游阶段为过期。\n会改变 active lineage：否\n创建新 Run：否" if language == "zh" else f"Select {part_id} for the next Part Request with confirmation.\n\nTarget: {target}\n\nResult: writes a validated versioned Assembly Plan override, preserves old Runs, and marks downstream stages stale.\nActive lineage changes: no\nNew Run: no"),
        },
    ]
    return {**item, "kind": kind, "status": status, "selected": selected, "attention": "required" if status == "blocked" else "none", "clickable": True, "actions": actions}


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
    stage_id = str(detail.get("stage_id") or detail.get("key") or "")
    input_contracts = [_artifact_contract(item, detail, "input", fallback_source) for item in inputs]
    output_contracts = [_artifact_contract(item, detail, "output", fallback_source) for item in outputs]
    detail.update({
        "stage_id": stage_id,
        "conclusion": {"title": _nested(detail, "status_banner", "title") or detail.get("stage_name"), "summary": _nested(detail, "status_banner", "summary") or detail.get("human_summary") or detail.get("short_summary")},
        "user_input": {
            "summary": _human_input_summary(detail, input_contracts),
            "source_run_id": source_input.get("source_run_id") or source_run,
            "source_stage_id": _input_stage(detail.get("stage_id")),
            "source_type": "active_override" if detail.get("override_present") else "accepted_upstream_output",
            "editable": view_mode == "current_work" and bool(detail.get("override_present")),
            "stale_downstream": bool(detail.get("override_present")),
            "artifacts": input_contracts,
        },
        "agent_decision": {
            "summary": _human_decision_summary(detail),
            "decisions": _human_decisions(detail),
            "assumptions": detail.get("limitations_summary") or [],
            "interventions": [],
        },
        "agent_output": {
            "summary": _human_output_summary(detail, output_contracts),
            "source_run_id": source_output.get("source_run_id") or detail.get("source_run_id") or fallback_source,
            "source_stage_id": detail.get("stage_id"),
            "validation_status": "passed" if detail.get("status") in {"completed", "contract_complete", "execution_skipped"} else detail.get("status"),
            "artifacts": output_contracts,
            "products": [item for item in output_contracts if item.get("name") in {"model.step", "model.stl"}],
            "step_stl_expectation": "not_expected" if detail.get("status") in {"contract_complete", "execution_skipped"} else "expected",
        },
        "evidence": _evidence_contracts(input_contracts, output_contracts),
    })
    return detail


def _artifact_contract(item: dict[str, Any], detail: dict[str, Any], direction: str, fallback_source: str | None) -> dict[str, Any]:
    """Keep every visible artifact self-describing and directly openable."""
    name = str(item.get("name") or "artifact")
    status = "passed" if direction == "output" and detail.get("status") in {"completed", "contract_complete", "execution_skipped"} else "available"
    return {
        "name": name,
        "display_name": _artifact_display_name(name),
        "kind": _artifact_kind(name),
        "summary": item.get("summary") or ("Stage output" if direction == "output" else "Stage input"),
        "source_run_id": item.get("source_run_id") or detail.get("source_run_id") or fallback_source,
        "source_stage_id": detail.get("stage_id") or detail.get("key"),
        "relative_path": item.get("source_relative_path") or name,
        "modified_at": item.get("modified_at"),
        "validation_status": status,
        "source_type": item.get("source_type") or "original",
        "previewable": _artifact_kind(name) in {"json", "markdown", "text", "stl", "step"},
        "downloadable": _artifact_kind(name) in {"step", "stl"},
        "editable": False,
        "open_action": {"type": "artifact_dialog"},
        "content": item.get("content"),
        "direction": direction,
    }


def _human_input_summary(detail: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    if detail.get("stage_id") == "workflow_review":
        part = detail.get("selected_part_id") or _nested(detail.get("report_summary"), "selected_candidate")
        if not part:
            part = next((
                item.get("content", {}).get("part_id")
                for item in artifacts
                if isinstance(item.get("content"), dict) and isinstance(item["content"].get("part_id"), str)
            ), None)
        part = part or "result"
        return f"The selected {part} result was ready for work-level review."
    if not artifacts:
        return "No accepted upstream input is available for this stage yet."
    names = ", ".join(item["display_name"] for item in artifacts[:2])
    return f"This stage used accepted upstream records: {names}."


def _human_decision_summary(detail: dict[str, Any]) -> str:
    if detail.get("stage_id") == "workflow_review":
        return "CadFlow assessed the available Work lineage and prepared a work-level review conclusion."
    return str(detail.get("human_summary") or detail.get("short_summary") or "No agent interpretation is available.")


def _human_decisions(detail: dict[str, Any]) -> list[Any]:
    if detail.get("stage_id") == "workflow_review":
        decisions = ["The current result is ready for user review."]
        limitations = detail.get("limitations_summary") if isinstance(detail.get("limitations_summary"), list) else []
        decisions.extend(limitations[:2])
        return decisions
    return detail.get("key_decisions_human") or []


def _human_output_summary(detail: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    if detail.get("stage_id") == "workflow_review" and artifacts:
        return "Workflow review created successfully. This is the stage output, not an inherited upstream block."
    if not artifacts:
        return "No stage output is available yet."
    return str(detail.get("short_summary") or "Stage output is available.")


def _evidence_contracts(inputs: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group same-named lineage files without erasing their distinct origins."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in [*outputs, *inputs]:
        grouped.setdefault(str(item.get("name")), []).append(item)
    evidence = []
    for name, items in grouped.items():
        primary = items[0]
        related = items[1:]
        evidence.append({**primary, "related": related, "related_count": len(related)})
    return evidence


def _scoped_actions(stage: dict[str, Any] | None, view_mode: ViewMode, work_id: str, target_run_id: str | None, language: str) -> dict[str, Any]:
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
            "category": "workflow_command" if backend_action else ("navigation" if action.get("presentation_action") else "disabled_future"),
            "scope": "run_snapshot" if view_mode == "run_snapshot" else "current_work",
            "target_work_id": work_id,
            "target_run_id": target_run_id,
            "target_stage_id": stage.get("stage_id") if isinstance(stage, dict) else None,
            "creates_new_run": creates_new_run,
            "updates_active_lineage": creates_new_run,
            "next_stage_on_success": _next_stage_for_action(backend_action or action.get("key"), stage.get("stage_id") if isinstance(stage, dict) else None),
            "expected_postcondition": {
                "next_stage": _next_stage_for_action(backend_action or action.get("key"), stage.get("stage_id") if isinstance(stage, dict) else None),
                "updates_active_lineage": creates_new_run,
            },
        })
        action["label_i18n"] = action_labels(action.get("label"), action.get("key"))
        action["label"] = action["label_i18n"]["zh" if language == "zh" else "en"]
        action["tooltip"] = _action_tooltip(action, stage, language)
        prepared.append(action)
    agent_review = next((action for action in prepared if action.get("enabled") and action.get("key") in _AGENT_REVIEW_ACTIONS), None)
    if agent_review is None and stage is not None:
        agent_review = {
            "key": "create_workflow_review",
            "label": "Refresh agent workflow review",
            "enabled": view_mode == "current_work" and bool(target_run_id),
            "disabled_reason": _READ_ONLY_REASON if view_mode == "run_snapshot" else "Select an active Run first.",
            "backend_action": "create_workflow_review",
            "scope": "run_snapshot" if view_mode == "run_snapshot" else "current_work",
            "target_work_id": work_id,
            "target_run_id": target_run_id,
            "target_stage_id": stage.get("stage_id") if isinstance(stage, dict) else None,
            "category": "workflow_command",
            "creates_new_run": False,
            "updates_active_lineage": False,
            "next_stage_on_success": "workflow_review",
        }
        agent_review["tooltip"] = _action_tooltip(agent_review, stage, language)
    if agent_review is not None:
        agent_review["label"] = _agent_review_label(agent_review, stage)
        agent_review["label_i18n"] = action_labels(agent_review["label"], agent_review.get("key"))
        agent_review["label"] = agent_review["label_i18n"]["zh" if language == "zh" else "en"]
        agent_review["tooltip"] = _action_tooltip(agent_review, stage, language)
    enabled = [action for action in prepared if action.get("enabled") and action.get("key") not in _REVIEW_DECISION_ACTIONS]
    secondary = [action for action in enabled if action is not agent_review]
    disabled = [action for action in prepared if not action.get("enabled")]
    if agent_review is not None and not agent_review.get("enabled"):
        disabled.insert(0, agent_review)
    return {
        "primary_action": agent_review,
        "secondary_actions": secondary,
        "disabled_actions": disabled,
        "advanced_actions": [],
        "review_actions": [action for action in prepared if action.get("key") in _REVIEW_DECISION_ACTIONS],
}


def _agent_review_label(action: dict[str, Any], stage: dict[str, Any] | None) -> str:
    key = str(action.get("key") or "")
    if key == "create_workflow_review":
        return "Refresh agent workflow review"
    if key == "part_result_review":
        return "Request agent result review"
    return "Request agent review"


def _action_tooltip(action: dict[str, Any], stage: dict[str, Any] | None, language: str = "en") -> str:
    """Explain action, target, and effect; disabled actions keep their reason."""
    key = str(action.get("key") or "")
    stage_name = str((stage or {}).get("stage_name") or (stage or {}).get("stage_id") or ("所选阶段" if language == "zh" else "selected stage"))
    run_id = action.get("target_run_id") or ("当前 Run" if language == "zh" else "active Run")
    target = f"当前 Work · {stage_name} · Run {run_id}" if language == "zh" else f"Current Work · {stage_name} · Run {run_id}"
    copy = {
        "save_stage_review": ("Save the selected review decision and notes.", "Writes a traceable stage_review record; does not rerun the agent or modify existing output."),
        "approve_stage": ("Quick approve this stage without notes.", "Records Approved, keeps all artifacts, and updates the Work review state. It does not create CAD."),
        "mark_blocked": ("Record that this stage cannot continue.", "The review form requires a reason and suggested return stage. Existing results are preserved."),
        "mark_needs_revision": ("Request a revision through the stage-review form.", "The saved review records requested changes and can enable a rework run."),
        "create_workflow_review": ("Refresh the work-level review from the current lineage.", "Writes workflow_review artifacts; it does not generate a CAD model."),
        "view_cad_ir_draft": ("Open the selected CAD IR artifact.", "Read-only inspection; no workflow state changes."),
        "edit_assembly_plan": ("Open the assembly plan and its validated override editor.", "Saving an override preserves the original artifact and may mark downstream stages stale."),
        "view_diagnostics": ("Open raw validation and trace diagnostics.", "Read-only troubleshooting; no workflow state changes."),
    }


    action_text, result_text = copy.get(key, ("Run this workflow action.", "The result is recorded against the selected Work and Run."))
    disabled = action.get("disabled_reason")
    if language == "zh":
        action_text = f"执行“{action_label('zh', action.get('label'), key)}”。"
        result_text = "结果会记录到指定的 Work、Run 和阶段。"
        lines = [action_text, "", f"目标: {target}", "", f"结果: {result_text}", "", f"会改变 active lineage：{'是' if action.get('updates_active_lineage') else '否'}", f"创建新 Run：{'是' if action.get('creates_new_run') else '否'}"]
        if disabled:
            lines.extend(["", f"当前不可用：{disabled}"])
        return "\n".join(lines)
    lines = [action_text, "", f"Target: {target}", "", f"Result: {result_text}", "", f"Active lineage changes: {'yes' if action.get('updates_active_lineage') else 'no'}", f"New Run: {'yes' if action.get('creates_new_run') else 'no'}"]
    if disabled:
        lines.extend(["", f"Currently unavailable: {disabled}"])
    return "\n".join(lines)


def _action_inventory(actions: dict[str, Any], graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Machine-readable, target-complete inventory for manual cockpit checks."""
    inventory: list[dict[str, Any]] = []
    for group in ("primary_action", "secondary_actions", "disabled_actions"):
        entries = actions.get(group)
        entries = entries if isinstance(entries, list) else [entries]
        for item in entries:
            if isinstance(item, dict):
                inventory.append(dict(item))
    for lane in ("part_candidates", "reference_lane"):
        for candidate in graph.get(lane, []) if isinstance(graph.get(lane), list) else []:
            if isinstance(candidate, dict):
                inventory.extend(dict(item) for item in candidate.get("actions", []) if isinstance(item, dict))
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in inventory:
        key = (item.get("key"), item.get("target_work_id"), item.get("target_run_id"), item.get("target_stage_id"), item.get("part_id"))
        unique[key] = item
    return list(unique.values())


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
            "status": _nested(item, "status", "status") or item.get("status") or "unknown",
            "summary": item.get("summary") or "Immutable workflow attempt.",
            "is_current": item.get("lineage_state") == "active",
            "read_only": view_mode == "run_snapshot" and run_id == viewed_run_id,
        })
    return result


def _conclusion(surface: dict[str, Any], stage: dict[str, Any] | None, summary: dict[str, Any], view_mode: ViewMode) -> dict[str, Any]:
    if view_mode == "run_snapshot":
        return {"title": "Historical Run Snapshot", "summary": "Read-only. This Run does not represent the complete current Work."}
    decision = surface.get("decision_panel") if isinstance(surface.get("decision_panel"), dict) else {}
    status = (stage or {}).get("status")
    if status in {"contract_complete", "execution_skipped"}:
        return {
            "title": "CAD IR contract validated",
            "summary": "input_ir.json was created. CAD execution was intentionally skipped, so STEP/STL are not expected.",
            "rationale": "This is a contract-complete workflow, not a missing-model failure.",
        }
    if decision.get("scope") == "single_generic_concept_part":
        return {
            "title": "Single generic concept part generated",
            "summary": "CadFlow generated and validated upper_link as link_like_part / elongated_plate_with_end_holes. This is not a complete robot-arm assembly.",
            "rationale": "assembly_generated=false · result scope: single_generic_concept_part",
        }
    return {"title": "Current result", "summary": decision.get("decision") or (stage or {}).get("human_summary") or summary.get("next_action") or "Inspect the active Work lineage.", "rationale": decision.get("rationale") or None}


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
