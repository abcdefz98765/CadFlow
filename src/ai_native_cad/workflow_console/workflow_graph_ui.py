"""Workflow graph and Current Attention rendering for canonical Current Work."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from ai_native_cad.workflow_console.i18n import status_label


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def workflow_graph_with_runtime(
    graph: dict[str, Any],
    state: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    """Overlay the honest in-process command state without persisting it."""

    execution = state.get("action_execution")
    if not isinstance(execution, dict) or execution.get("status") != "pending":
        return graph
    target_node_id = execution.get("target_stage_id")
    if not isinstance(target_node_id, str):
        return graph
    projected = deepcopy(graph)
    for node in projected.get("nodes", []):
        if isinstance(node, dict) and node.get("id") == target_node_id:
            node["status"] = "running"
            node["user_state"] = "running"
            node["user_state_label"] = "运行中" if language == "zh" else "Running"
            node["attention"] = "running"
    for item in projected.get("current_attention", []):
        if isinstance(item, dict) and item.get("node_id") == target_node_id:
            item["state"] = "running"
            item["state_label"] = "运行中" if language == "zh" else "Running"
            item["kind"] = "running"
    return projected


def render_current_attention(
    ui: Any,
    graph: dict[str, Any],
    on_select_node: Callable[[str], None],
    language: str,
    *,
    state: dict[str, Any] | None = None,
) -> None:
    items = [item for item in graph.get("current_attention", []) if isinstance(item, dict)]
    execution = (state or {}).get("action_execution")

    def visible_state(item: dict[str, Any]) -> tuple[str, str]:
        running = bool(
            isinstance(execution, dict)
            and execution.get("status") == "pending"
            and execution.get("target_work_id")
            and (
                execution.get("target_run_id") == _dict(item.get("primary_action")).get("target_run_id")
                or execution.get("target_stage_id") == item.get("node_id")
            )
        )
        if running:
            return "running", "运行中" if language == "zh" else "Running"
        return str(item.get("state") or "ready"), str(item.get("state_label") or "")
    if not items:
        return
    if len(items) == 1:
        item = items[0]
        item_state, item_state_label = visible_state(item)
        task = ui.element("section").classes("workflow-current-task w-full")
        task.on("click", lambda _event, node_id=str(item.get("node_id")): on_select_node(node_id))
        with task:
            with ui.column().classes("gap-1"):
                ui.label("当前任务" if language == "zh" else "CURRENT TASK").classes("workflow-eyebrow")
                ui.label(
                    f"{item.get('part_label') or item.get('part_job_id') or ''} · {item.get('label') or ''}"
                ).classes("text-base font-semibold")
            ui.label(item_state_label).classes(
                f"workflow-state-pill {item_state}"
            )
        return
    with ui.element("section").classes("workbench-panel w-full"):
        ui.label("当前任务" if language == "zh" else "CURRENT TASKS").classes("workflow-eyebrow")
        ui.label(
            "每个零件保留自己的下一步。" if language == "zh"
            else "Each Part keeps its own next step."
        ).classes("text-xs text-gray-500")
        with ui.element("div").classes("workflow-attention-grid w-full mt-2"):
            for item in items:
                item_state, item_state_label = visible_state(item)
                row = ui.element("div").classes("workflow-attention-row")
                row.on("click", lambda _event, node_id=str(item.get("node_id")): on_select_node(node_id))
                with row:
                    ui.label(str(item.get("part_label") or item.get("part_job_id") or "")).classes("font-semibold")
                    ui.label(str(item.get("label") or "")).classes("workflow-attention-summary text-sm text-gray-600")
                    ui.label(item_state_label).classes(
                        f"workflow-state-pill {item_state}"
                    )


def render_dynamic_work_graph(
    ui: Any,
    graph: dict[str, Any],
    on_select_node: Callable[[str], None],
    language: str,
) -> None:
    phases = [item for item in graph.get("phase_groups", []) if isinstance(item, dict)]
    nodes = {
        str(item.get("id")): item
        for item in graph.get("nodes", [])
        if isinstance(item, dict) and item.get("id")
    }
    edges = [item for item in graph.get("edges", []) if isinstance(item, dict)]
    phase_labels = {str(item.get("id")): str(item.get("label") or "") for item in phases}
    selected_group = next(
        (str(node.get("group")) for node in nodes.values() if node.get("selected")),
        "",
    )
    phase_counts = {
        phase_id: sum(1 for node in nodes.values() if node.get("group") == phase_id)
        for phase_id in phase_labels
    }

    with ui.element("section").classes("dynamic-workflow-shell w-full"):
        with ui.element("div").classes("dynamic-workflow-canvas"):
            with ui.element("div").classes("dynamic-phase-grid"):
                for phase in phases:
                    phase_id = str(phase.get("id") or "")
                    phase_class = "dynamic-phase-header"
                    if phase_counts.get(phase_id):
                        phase_class += " has-nodes"
                    if phase_id == selected_group:
                        phase_class += " current"
                    ui.label(str(phase.get("label") or phase_id)).classes(phase_class)
            with ui.element("div").classes("dynamic-root-row"):
                for root_id in graph.get("root_node_ids", []):
                    root = nodes.get(str(root_id))
                    if root:
                        _render_dynamic_graph_node(
                            ui, root, phase_labels, on_select_node, language, show_summary=False
                        )
            work_path = [
                nodes[node_id]
                for node_id in graph.get("work_path_node_ids", [])
                if node_id in nodes
            ]
            if work_path:
                with ui.element("div").classes("dynamic-attempt-row active"):
                    _render_dynamic_graph_path(
                        ui,
                        work_path,
                        edges,
                        phase_labels,
                        on_select_node,
                        language,
                    )
            branches = [item for item in graph.get("branches", []) if isinstance(item, dict)]
            if not branches:
                ui.label(
                    "Part Job 尚未创建；图只显示已存在的 Work 状态。"
                    if language == "zh"
                    else "No Part Job exists yet; the graph shows only durable Work state."
                ).classes("text-sm text-gray-500 p-3")
            for branch in branches:
                with ui.element("div").classes("dynamic-branch"):
                    ui.label(
                        f"{('零件' if language == 'zh' else 'PART')} · {branch.get('label') or branch.get('part_job_id')}"
                    ).classes("dynamic-branch-title")
                    part_node = nodes.get(str(branch.get("part_node_id")))
                    with ui.element("div").classes("dynamic-attempt-row branch-origin"):
                        if part_node:
                            _render_dynamic_graph_path(
                                ui,
                                [part_node],
                                edges,
                                phase_labels,
                                on_select_node,
                                language,
                            )
                    attempts = [item for item in branch.get("attempts", []) if isinstance(item, dict)]
                    for attempt in attempts:
                        attempt_nodes = [
                            nodes[node_id]
                            for node_id in attempt.get("node_ids", [])
                            if node_id in nodes
                        ]
                        row_classes = "dynamic-attempt-row"
                        if attempt.get("revision"):
                            row_classes += " revision"
                        if attempt.get("active"):
                            row_classes += " active"
                        with ui.element("div").classes(row_classes):
                            _render_dynamic_graph_path(
                                ui,
                                attempt_nodes,
                                edges,
                                phase_labels,
                                on_select_node,
                                language,
                            )


def _render_dynamic_graph_path(
    ui: Any,
    path_nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    phase_labels: dict[str, str],
    on_select_node: Callable[[str], None],
    language: str,
) -> None:
    if not path_nodes:
        return
    with ui.element("div").classes("dynamic-graph-path"):
        previous_id: str | None = None
        for node in path_nodes:
            node_id = str(node.get("id") or "")
            incoming = next(
                (
                    edge
                    for edge in edges
                    if str(edge.get("target") or "") == node_id
                    and (previous_id is None or str(edge.get("source") or "") == previous_id)
                ),
                None,
            )
            if previous_id is not None:
                with ui.element("div").classes("dynamic-edge"):
                    ui.element("div").classes("dynamic-edge-line")
                    if incoming:
                        ui.label(str(incoming.get("label") or incoming.get("type") or "")).classes("dynamic-edge-label")
            _render_dynamic_graph_node(
                ui, node, phase_labels, on_select_node, language
            )
            previous_id = node_id


def _render_dynamic_graph_node(
    ui: Any,
    node: dict[str, Any],
    phase_labels: dict[str, str],
    on_select_node: Callable[[str], None],
    language: str,
    *,
    show_summary: bool = True,
) -> None:
    status = str(node.get("status") or "not_started")
    attention = str(node.get("attention") or "none")
    classes = f"dynamic-node {status} attention-{attention}" + (" selected" if node.get("selected") else "")
    card = ui.column().classes(classes).props(f'data-node-id="{str(node.get("id") or "")}"')
    card.on("click", lambda _event, node_id=str(node.get("id")): on_select_node(node_id))
    with card:
        ui.label(str(phase_labels.get(str(node.get("group") or ""), ""))).classes("dynamic-node-phase")
        with ui.row().classes("items-center gap-2 no-wrap"):
            ui.element("div").classes(
                f"workflow-dot status-{_dot_status(status)} kind-{node.get('kind') or 'stage'}"
            )
            ui.label(str(node.get("label") or node.get("id") or "")).classes("dynamic-node-title")
        user_state = str(node.get("user_state") or "ready")
        ui.label(str(node.get("user_state_label") or status_label(language, status))).classes("workflow-node-status")
        if attention != "none":
            ui.label(str(node.get("user_state_label") or "")).classes(
                f"dynamic-attention-badge {user_state}"
            )
        if show_summary and node.get("summary"):
            ui.label(str(node["summary"])).classes("dynamic-node-summary")


def _dot_status(status: Any) -> str:
    value = str(status or "unknown")
    if value in {"accepted_for_preview", "success"}:
        return "accepted"
    known = {"completed", "contract_complete", "execution_skipped", "skipped", "unavailable", "user_modified", "stale", "accepted", "reviewable", "available", "ready", "running", "needs_review", "partial_success", "blocked", "reference_only", "not_started", "incomplete", "candidate", "selected", "generated", "failed"}
    if value in known:
        return value
    return "blocked" if "blocked" in value else "unknown"


__all__ = ["workflow_graph_with_runtime", "render_current_attention", "render_dynamic_work_graph"]
