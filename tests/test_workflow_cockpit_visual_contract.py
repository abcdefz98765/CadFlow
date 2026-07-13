"""Visual-contract checks for the declarative NiceGUI cockpit layer.

These tests intentionally avoid pixel snapshots: they protect the rendering
data and the semantic CSS classes that make a workflow legible at any width.
"""

from __future__ import annotations

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
    return build_workflow_page_view_model(backend, result["work_id"], selected_stage_id="part_modeling")


def test_visual_tokens_keep_status_selection_attention_and_horizontal_graph_separate(tmp_path, monkeypatch):
    page = _contract_page(tmp_path, monkeypatch)
    nodes = [
        *page["workflow_graph"]["stage_spine"],
        *page["workflow_graph"]["selected_part_pipeline"],
        *page["workflow_graph"]["review_tail"],
    ]

    assert all(node["label"] and node["short_summary"] for node in nodes)
    assert all(node["status"] != "selected" and isinstance(node["selected"], bool) for node in nodes)
    assert all(node["attention"] in {"none", "required", "in_progress"} for node in nodes)
    assert "overflow-x:auto" in WORKFLOW_UI_CSS
    assert ".workflow-graph-canvas{min-width:" in WORKFLOW_UI_CSS
    assert ".workflow-step-selected" in WORKFLOW_UI_CSS
    assert ".workflow-attention" in WORKFLOW_UI_CSS
    assert ".workflow-dot.status-unavailable" in WORKFLOW_UI_CSS
    assert ".workflow-dot.status-execution_skipped" in WORKFLOW_UI_CSS


def test_candidate_reference_and_contract_rendering_contracts_are_explicit(tmp_path, monkeypatch):
    page = _contract_page(tmp_path, monkeypatch)
    graph = page["workflow_graph"]

    assert graph["part_candidates"] and graph["reference_lane"]
    assert {item["kind"] for item in graph["part_candidates"]} == {"candidate_part"}
    assert {item["kind"] for item in graph["reference_lane"]} == {"reference_component"}
    assert page["selected_stage"]["status"] == "execution_skipped"
    assert page["selected_stage"]["agent_output"]["step_stl_expectation"] == "not_expected"
    assert "reference-component" in WORKFLOW_UI_CSS


def test_current_and_snapshot_page_structure_are_distinguishable(tmp_path, monkeypatch):
    page = _contract_page(tmp_path, monkeypatch)
    snapshot = build_workflow_page_view_model(
        WorkflowConsoleBackend(project_root=tmp_path, workspace_root=tmp_path / "workspace"),
        page["work"]["work_id"],
        view_mode="run_snapshot",
        selected_run_id=page["active_lineage"]["active_root_run_id"],
    )

    assert page["view_mode"] == "current_work"
    assert page["current_conclusion"]["title"] == "CAD IR contract validated"
    assert snapshot["read_only"] is True
    assert "read-only" in snapshot["read_only_reason"].lower()
    assert [page for page, _icon, _label in WORK_USER_PAGES] == ["overview", "workflow", "parts", "history"]
    assert "grid-template-columns:repeat(3" in WORKFLOW_UI_CSS
    assert "@media(max-width:760px)" in WORKFLOW_UI_CSS
