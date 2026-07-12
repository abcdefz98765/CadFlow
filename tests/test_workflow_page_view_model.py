"""Contract tests for Work lineage and immutable Workflow page modes."""

from __future__ import annotations

import json

from ai_native_cad.workflow_console import WorkflowConsoleBackend
from ai_native_cad.workflow_console.workflow_page_view_model import build_workflow_page_view_model


def _work_with_failed_latest_attempt(tmp_path):
    workspace = tmp_path / "workspace"
    backend = WorkflowConsoleBackend(project_root=tmp_path, workspace_root=workspace)
    backend.create_workspace(name="test")
    backend.create_work("Lineage work", work_id="lineage_work")
    backend.create_work_requirement_run("lineage_work", "Create a spacer.", run_id="accepted_root")
    runs_root = backend._work_runs_root("lineage_work")
    backend.run_stage_by_id("accepted_root", "requirement", root=runs_root)
    backend.create_run_by_id("failed_attempt", "Create a failed alternative.", root=runs_root)
    (runs_root / "failed_attempt" / "report.json").write_text(json.dumps({"status": "failed", "success": False}) + "\n", encoding="utf-8")
    manifest = backend._read_work_manifest("lineage_work")
    manifest["run_ids"] = ["accepted_root", "failed_attempt"]
    manifest["current_run_id"] = "failed_attempt"  # Legacy field must not control the Work graph.
    manifest["active_lineage"] = {
        "active_root_run_id": "accepted_root",
        "active_leaf_run_id": "accepted_root",
        "accepted_run_ids": ["accepted_root"],
        "superseded_run_ids": [],
        "latest_attempt_run_id": "failed_attempt",
    }
    backend._write_work_manifest("lineage_work", manifest)
    backend.invalidate_work_index()
    return backend


def test_current_work_uses_explicit_active_lineage_not_latest_attempt(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)

    page = build_workflow_page_view_model(backend, "lineage_work", view_mode="current_work")

    assert page["view_mode"] == "current_work"
    assert page["active_lineage"]["active_root_run_id"] == "accepted_root"
    assert page["active_lineage"]["latest_attempt_run_id"] == "failed_attempt"
    assert page["source"]["projection"]["root_run_id"] == "accepted_root"
    assert {item["run_id"]: item["lineage_state"] for item in page["run_strip"]}["failed_attempt"] == "failed_branch"


def test_run_snapshot_is_read_only_and_uses_only_selected_run(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)

    page = build_workflow_page_view_model(
        backend,
        "lineage_work",
        view_mode="run_snapshot",
        selected_run_id="failed_attempt",
    )

    assert page["read_only"] is True
    assert page["viewed_run_id"] == "failed_attempt"
    assert page["selected_stage"]["user_input"]["source_run_id"] == "failed_attempt"
    assert all(action["target_run_id"] == "failed_attempt" for action in page["available_actions"]["disabled_actions"])
    assert all("read-only" in str(action.get("disabled_reason", "")).lower() for action in page["available_actions"]["disabled_actions"] if action.get("backend_action") != "run_rework")


def test_graph_nodes_have_required_contract_and_selected_is_not_status(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)
    page = build_workflow_page_view_model(backend, "lineage_work", view_mode="current_work")
    nodes = [*page["workflow_graph"]["stage_spine"], *page["workflow_graph"]["selected_part_pipeline"], *page["workflow_graph"]["review_tail"]]

    assert nodes
    for node in nodes:
        assert node["stage_id"]
        assert node["label"]
        assert node["status"]
        assert node["short_summary"]
        assert node["kind"] in {"stage", "review", "rework"}
        assert isinstance(node["selected"], bool)
        assert node["status"] != "selected"


def test_current_work_actions_have_one_primary_and_an_explicit_target(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)

    page = build_workflow_page_view_model(backend, "lineage_work", view_mode="current_work")
    primary = page["available_actions"]["primary_action"]

    assert primary is not None
    assert primary["scope"] == "current_work"
    assert primary["target_work_id"] == "lineage_work"
    assert primary["target_run_id"] == "accepted_root"
    assert primary["next_stage_on_success"] == "workflow_review"
    assert page["selected_stage"]["primary_action"] == primary
