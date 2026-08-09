"""Visual-contract checks for the declarative NiceGUI cockpit layer.

These tests intentionally avoid pixel snapshots: they protect the rendering
data and the semantic CSS classes that make a workflow legible at any width.
"""

from __future__ import annotations

import inspect

from ai_native_cad.examples import golden_desktop_robot_arm as golden_service
from ai_native_cad.pipeline import runner as pipeline_runner
from ai_native_cad.workflow_console import WorkflowConsoleBackend
from ai_native_cad.workflow_console.nicegui_app import WORKFLOW_UI_CSS, WORK_USER_PAGES
from ai_native_cad.workflow_console.workflow_page_view_model import build_workflow_page_view_model


def _contract_page(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    workspace = tmp_path / "workspace"
    result = golden_service.run_golden_workflow(workspace, mode="contract", project_root=tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path, workspace_root=workspace)
    return build_workflow_page_view_model(backend, result["work_id"])


def test_visual_tokens_keep_status_selection_attention_and_horizontal_graph_separate(tmp_path, monkeypatch):
    page = _contract_page(tmp_path, monkeypatch)
    nodes = page["workflow_graph"]["nodes"]

    assert all(node["label"] and node["summary"] for node in nodes)
    assert all(node["status"] != "selected" and isinstance(node["selected"], bool) for node in nodes)
    assert "overflow-x:auto" in WORKFLOW_UI_CSS
    assert ".dynamic-workflow-canvas{min-width:" in WORKFLOW_UI_CSS
    assert ".dynamic-phase-grid{display:flex" in WORKFLOW_UI_CSS
    assert ".workflow-master-detail{display:grid" in WORKFLOW_UI_CSS
    assert ".dynamic-edge-line" in WORKFLOW_UI_CSS
    assert ".dynamic-node.selected" in WORKFLOW_UI_CSS
    assert ".workflow-dot.status-unavailable" in WORKFLOW_UI_CSS
    assert ".workflow-dot.status-execution_skipped" in WORKFLOW_UI_CSS
    assert ".workflow-dot.status-reviewable" in WORKFLOW_UI_CSS
    assert ".workflow-dot.status-accepted" in WORKFLOW_UI_CSS


def test_current_work_does_not_fabricate_part_branches_or_legacy_graph_nodes(tmp_path, monkeypatch):
    page = _contract_page(tmp_path, monkeypatch)
    graph = page["workflow_graph"]

    assert graph["compatibility_mode"] is False
    assert graph["branches"] == []
    assert {item["kind"] for item in graph["nodes"]} <= {
        "request", "part", "attempt", "decision", "design", "candidate",
        "build", "recovery", "reviewable", "accepted",
    }
    assert "part_candidates" not in graph
    assert "reference_lane" not in graph
    assert graph["edges"] == []


def test_current_and_snapshot_page_structure_are_distinguishable(tmp_path, monkeypatch):
    page = _contract_page(tmp_path, monkeypatch)
    snapshot = build_workflow_page_view_model(
        WorkflowConsoleBackend(project_root=tmp_path, workspace_root=tmp_path / "workspace"),
        page["work"]["work_id"],
        view_mode="run_snapshot",
        selected_run_id=page["active_lineage"]["active_root_run_id"],
    )

    assert page["view_mode"] == "current_work"
    assert page["projection_mode"] == "agent_first"
    assert page["workflow_graph"]["topology"] == "dynamic_work_graph"
    assert snapshot["read_only"] is True
    assert "read-only" in snapshot["read_only_reason"].lower()
    assert "stage_spine" in snapshot["workflow_graph"]
    assert [page for page, _icon, _label in WORK_USER_PAGES] == ["overview", "workflow", "parts", "history"]
    assert "grid-template-columns:repeat(4" in WORKFLOW_UI_CSS
    assert ".workflow-inspector-pane{min-width:0;position:sticky" in WORKFLOW_UI_CSS
    assert "@media(max-width:760px)" in WORKFLOW_UI_CSS


def test_primary_surface_keeps_audit_metadata_in_expanded_action_details():
    from ai_native_cad.workflow_console import nicegui_app

    source = inspect.getsource(nicegui_app._render_selected_stage_detail_v2)
    assert "_render_guidance_contract" in source
    assert "_render_action_details" in source
    assert "source_run_id" not in source
    action_details = inspect.getsource(nicegui_app._render_action_details)
    assert "backend_action" in action_details
    assert "target_run_id" in action_details
