"""Targeted NiceGUI renderer for the selected Workflow node inspector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ai_native_cad.workflow_console.agent_activity_ui import render_agent_activity
from ai_native_cad.workflow_console.attempt_ui import render_stopped_attempt
from ai_native_cad.workflow_console.technical_evidence_ui import render_lazy_technical_evidence
from ai_native_cad.workflow_console.work_design_ui import render_work_design


@dataclass(frozen=True)
class SelectedInspectorRenderers:
    """Mature composition-root renderers used by the independent inspector."""

    action_feedback: Callable[..., None]
    display_status: Callable[..., str]
    pending_action_matches: Callable[..., bool]
    node_actions: Callable[..., None]
    key_values: Callable[..., None]
    agent_design_summary: Callable[..., None]
    preview: Callable[..., None]
    workbench_result: Callable[..., None]


def _dict_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _work_design_recovery(detail_type: str, detail: dict[str, Any]) -> dict[str, Any]:
    """Return persisted recovery only for the active Work Design node."""

    if detail_type != "work_design":
        return {}
    recovery = detail.get("recovery")
    return recovery if isinstance(recovery, dict) and recovery else {}


def render_selected_node_inspector(
    ui: Any,
    page: dict[str, Any],
    actions: Any,
    state: dict[str, Any],
    refresh: Callable[[], None],
    on_select_run: Callable[[str], None],
    language: str,
    *,
    renderers: SelectedInspectorRenderers,
) -> None:
    """Render only selected-node content over an existing page projection."""

    _render_action_feedback_panel = renderers.action_feedback
    _display_status = renderers.display_status
    _pending_action_matches = renderers.pending_action_matches
    _render_dynamic_node_actions = renderers.node_actions
    _key_values = renderers.key_values
    _render_agent_design_summary = renderers.agent_design_summary
    _render_dynamic_preview = renderers.preview
    _render_workbench_result = renderers.workbench_result
    node = page.get("selected_node") if isinstance(page.get("selected_node"), dict) else None
    if not node:
        return
    detail = node.get("detail") if isinstance(node.get("detail"), dict) else {}
    detail_type = str(detail.get("type") or "evidence")
    interaction = node.get("interaction") if isinstance(node.get("interaction"), dict) else {}
    overview = _dict_get(page.get("source"), "overview") or {}
    node_overview = dict(overview)
    node_work = dict(_dict_get(overview, "work") or {})
    if node.get("part_job_id"):
        node_work["active_part"] = node.get("part_job_id")
    node_overview["work"] = node_work
    with ui.element("section").classes("dynamic-node-detail w-full"):
        _render_action_feedback_panel(ui, state, language)
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label("所选节点" if language == "zh" else "SELECTED NODE").classes("workflow-eyebrow")
                part = detail.get("part") if isinstance(detail.get("part"), dict) else {}
                part_name = str(part.get("name") or node.get("part_job_id") or "")
                title = str(node.get("label") or node.get("id") or "")
                if node.get("part_job_id") and part_name and detail_type == "attempt":
                    title = part_name
                ui.label(title).classes("text-xl font-semibold")
                if detail_type == "attempt":
                    attempt_index = detail.get("attempt_index") or "—"
                    ui.label(
                        f"零件设计 · 尝试 #{attempt_index}"
                        if language == "zh"
                        else f"Part design · Attempt #{attempt_index}"
                    ).classes("text-sm font-medium text-blue-700")
                elif node.get("part_job_id"):
                    ui.label(
                        "零件范围" if language == "zh" else "Part scope"
                    ).classes("text-sm font-medium text-blue-700")
                # A request inspector owns the one visible copy of the request;
                # repeating the node summary above it made the same text appear twice.
                if detail_type != "request":
                    ui.label(str(node.get("summary") or "")).classes("text-sm text-gray-600")
            primary_action = (
                interaction.get("primary_action")
                if isinstance(interaction.get("primary_action"), dict)
                else {}
            )
            action_running = bool(primary_action and _pending_action_matches(state, primary_action))
            user_state = "running" if action_running else str(node.get("user_state") or "ready")
            user_state_label = (
                ("运行中" if language == "zh" else "Running")
                if action_running
                else str(node.get("user_state_label") or _display_status(node.get("status"), language))
            )
            ui.label(user_state_label).classes(
                f"workflow-state-pill {user_state}"
            )
        with ui.row().classes("items-center gap-2 mt-3"):
            needs_action = interaction.get("requires_user_action") is True
            if needs_action:
                action_state_label = "需要你的操作" if language == "zh" else "Your action is required"
            elif interaction.get("primary_action"):
                action_state_label = "准备好后即可继续" if language == "zh" else "Ready when you are"
            else:
                action_state_label = "当前无需操作" if language == "zh" else "No action required"
            ui.label(action_state_label).classes(
                "text-sm font-semibold " + ("text-amber-800" if needs_action else "text-gray-600")
            )

        _render_dynamic_node_actions(
            ui,
            node,
            interaction,
            node_overview,
            actions.backend,
            state,
            refresh,
            on_select_run,
            language,
        )

        if detail_type == "request":
            user_input = detail.get("user_input") if isinstance(detail.get("user_input"), dict) else {}
            ui.label("原始请求" if language == "zh" else "Original request").classes("workflow-eyebrow mt-4")
            ui.label(str(user_input.get("original_request") or _dict_get(detail.get("objective"), "summary") or "—")).classes("text-base font-medium mt-3")
            constraints = [str(item) for item in user_input.get("visible_constraints", [])]
            if constraints:
                ui.label("重要约束" if language == "zh" else "Important constraints").classes("workflow-eyebrow mt-3")
                for constraint in constraints:
                    ui.label(f"• {constraint}").classes("text-sm")
        elif detail_type in {"work_design", "decomposition"}:
            if detail_type == "work_design":
                work_design_recovery = _work_design_recovery(detail_type, detail)
                if work_design_recovery:
                    render_stopped_attempt(ui, work_design_recovery, language)
            work_design = detail.get("work_design") if isinstance(detail.get("work_design"), dict) else {}
            _key_values(ui, {
                "Scope": "Work Design",
                "State": work_design.get("status") or node.get("status"),
                "Generated Parts": work_design.get("part_job_count", len(work_design.get("generated_parts", []))),
                "Reference components": work_design.get("reference_component_count", len(work_design.get("reference_components", []))),
            })
            render_work_design(ui, work_design, language)
            render_agent_activity(ui, _dict_get(detail, "agent_output") or {}, language, backend=actions.backend)
        elif detail_type == "part_job":
            part = detail.get("part") if isinstance(detail.get("part"), dict) else {}
            projected_part = next(
                (item for item in overview.get("part_jobs", []) if isinstance(item, dict) and item.get("part_job_id") == node.get("part_job_id")),
                {},
            )
            _key_values(ui, {
                "Role": part.get("role") or "—",
                "State": part.get("state") or node.get("status"),
                "Attempts": projected_part.get("attempt_count", len(part.get("attempts", []))),
                "Reviewable result": "available" if projected_part.get("has_reviewable_result") else "none",
                "Accepted result": "available" if projected_part.get("has_accepted_result") else "none",
            })
            if detail.get("prompt"):
                ui.label("设计请求" if language == "zh" else "Design request").classes("workflow-eyebrow mt-3")
                ui.label(str(detail["prompt"])).classes("text-sm")
            render_agent_activity(ui, _dict_get(detail, "agent_output") or {}, language, backend=actions.backend)
        elif detail_type == "attempt":
            attempt_recovery = detail.get("recovery") if isinstance(detail.get("recovery"), dict) else {}
            if attempt_recovery:
                render_stopped_attempt(ui, attempt_recovery, language)
            ui.label(
                (
                    "从较早结果开始的新设计版本。"
                    if detail.get("source_result_id") and language == "zh"
                    else "A new design version started from an earlier result."
                    if detail.get("source_result_id")
                    else "当前零件的设计尝试。"
                    if language == "zh"
                    else "A design attempt for the current Part."
                )
            ).classes("text-sm text-gray-700 mt-3")
            part = detail.get("part") if isinstance(detail.get("part"), dict) else {}
            _key_values(ui, {
                "Part": part.get("name") or node.get("part_job_id") or "—",
                "Role": part.get("role") or "—",
            })
            if detail.get("prompt"):
                ui.label("设计请求" if language == "zh" else "Design request").classes("workflow-eyebrow mt-3")
                ui.label(str(detail["prompt"])).classes("text-sm")
            agent_design = _dict_get(detail, "agent_design") or {}
            if agent_design:
                normalized_design = {
                    "title": "Agent 设计" if language == "zh" else "Agent Design",
                    "summary": agent_design.get("concept") or agent_design.get("summary"),
                    "geometry_strategy": agent_design.get("geometry_strategy"),
                    "important_parameters": agent_design.get("important_parameters") or [],
                    "functional_features": agent_design.get("functional_features") or [],
                }
                _render_agent_design_summary(ui, normalized_design, {}, language)
            render_agent_activity(ui, _dict_get(detail, "agent_output") or {}, language, backend=actions.backend)
        elif detail_type == "agent_design":
            agent_design = _dict_get(detail, "agent_design") or {}
            _render_agent_design_summary(
                ui,
                {
                    "title": "Agent 设计" if language == "zh" else "Agent Design",
                    "summary": agent_design.get("concept") or agent_design.get("summary"),
                    "geometry_strategy": agent_design.get("geometry_strategy"),
                    "important_parameters": agent_design.get("important_parameters") or [],
                    "functional_features": agent_design.get("functional_features") or [],
                },
                {},
                language,
            )
            render_agent_activity(ui, _dict_get(detail, "agent_output") or {}, language, backend=actions.backend)
        elif detail_type == "clarification":
            for question in detail.get("questions", []):
                if isinstance(question, dict):
                    ui.label(str(question.get("question") or "")).classes("text-base text-amber-800 mt-2")
                    if question.get("reason"):
                        ui.label(str(question["reason"])).classes("text-sm text-gray-600")
            if detail.get("answered"):
                agent_output = _dict_get(detail, "agent_output") or {}
                answers = [
                    item for item in agent_output.get("items", [])
                    if isinstance(item, dict) and item.get("kind") == "user_answer"
                ]
                for answer in answers[-2:]:
                    ui.label(("你的回答：" if language == "zh" else "Your answer: ") + str(answer.get("summary") or "—")).classes("text-sm font-medium text-green-800")
        elif detail_type == "answer":
            ui.label(str(detail.get("question") or "")).classes("text-sm text-gray-600 mt-2")
            ui.label(str(detail.get("answer") or "—")).classes("text-base font-medium")
        elif detail_type == "recovery":
            recovery = detail.get("recovery") if isinstance(detail.get("recovery"), dict) else {}
            if recovery:
                ui.label(str(recovery.get("why_it_stopped") or recovery.get("summary") or "")).classes("text-sm text-gray-700 mt-3")
                _key_values(ui, {
                    "Last Agent action": recovery.get("last_agent_action") or "Not recorded",
                    "Last observation": recovery.get("last_observation") or "Not recorded",
                })
            else:
                ui.label(
                    "这是历史停止证据；恢复操作只在当前活动停止节点上提供。"
                    if language == "zh"
                    else "This is historical stop evidence; recovery actions are available only for the current active stop."
                ).classes("text-sm text-gray-600 mt-3")
            render_agent_activity(ui, _dict_get(detail, "agent_output") or {}, language, backend=actions.backend)
        elif detail_type in {"reviewable_result", "accepted_result"}:
            result = detail.get("result") if isinstance(detail.get("result"), dict) else {}
            _render_dynamic_preview(ui, _dict_get(detail, "preview") or {}, result, language)
            _render_workbench_result(ui, result, node_overview, actions.backend, state, refresh, language, show_actions=False)
            render_agent_activity(ui, _dict_get(detail, "agent_output") or {}, language, backend=actions.backend)
        else:
            evidence = detail.get("evidence") if isinstance(detail.get("evidence"), dict) else {}
            if evidence:
                ui.label(str(evidence.get("summary") or evidence.get("status") or node.get("summary") or "")).classes("text-sm mt-3")

        evidence = detail.get("evidence") if isinstance(detail.get("evidence"), dict) else {}
        agent_projection = detail.get("agent_output") if isinstance(detail.get("agent_output"), dict) else {}
        agent_references = agent_projection.get("technical_evidence_references")
        if not isinstance(agent_references, list) or not agent_references:
            render_lazy_technical_evidence(
                ui,
                title="技术证据" if language == "zh" else "Technical Evidence",
                language=language,
                metadata={
                    "Domain status": node.get("status") or "—",
                    "Work": node.get("work_id") or "—",
                    "Part Job": node.get("part_job_id") or "—",
                    "Node": node.get("id"),
                    "Run": node.get("run_id") or "—",
                    "Artifact": node.get("artifact_id") or "—",
                    "Source result": detail.get("source_result_id") or "—",
                    "Episode": _dict_get(detail, "episode").get("episode_id") if isinstance(_dict_get(detail, "episode"), dict) else "—",
                },
                evidence=evidence,
            )
