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
    assert primary["label"] == "Refresh agent workflow review"
    assert primary["backend_action"] == "create_workflow_review"
    assert page["selected_stage"]["primary_action"] == primary


def test_workflow_review_uses_human_stage_output_and_source_aware_artifact_contract(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)
    run_dir = backend._work_runs_root("lineage_work") / "accepted_root"
    (run_dir / "report.json").write_text(json.dumps({
        "status": "ready_for_review",
        "part_id": "upper_link",
        "token": "must-not-reach-the-artifact-dialog",
        "raw_provider_response": "must-not-reach-the-artifact-dialog",
    }) + "\n", encoding="utf-8")
    child = run_dir / "single_part_upper_link"
    child.mkdir()
    (child / "report.json").write_text(json.dumps({"status": "completed", "part_id": "upper_link"}) + "\n", encoding="utf-8")
    (run_dir / "workflow_review.json").write_text(json.dumps({"overall_status": "completed", "summary": ["Single generic concept part available"]}) + "\n", encoding="utf-8")
    (run_dir / "workflow_review.md").write_text("# Workflow Review\n", encoding="utf-8")
    backend.invalidate_work_index()

    page = build_workflow_page_view_model(backend, "lineage_work", view_mode="current_work", selected_stage_id="workflow_review")
    stage = page["selected_stage"]

    assert stage["agent_output"]["summary"].startswith("Workflow review created successfully")
    assert stage["agent_output"]["validation_status"] == "passed"
    assert stage["user_input"]["summary"] == "The selected upper_link result was ready for work-level review."
    output = {item["name"]: item for item in stage["agent_output"]["artifacts"]}
    assert output["workflow_review.json"]["open_action"] == {"type": "artifact_dialog"}
    assert output["workflow_review.json"]["source_run_id"] == "accepted_root"
    reports = next(item for item in stage["evidence"] if item["name"] == "report.json")
    assert reports["related_count"] == 1
    assert reports["related"][0]["source_run_id"] == "single_part_upper_link"
    assert "token" not in reports["content"]
    assert "raw_provider_response" not in reports["content"]
    assert "Target:" not in page["available_actions"]["primary_action"]["tooltip"]
    assert len(page["available_actions"]["primary_action"]["tooltip"].splitlines()) <= 3


def test_enabled_actions_expose_localized_labels_and_tooltips(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)

    chinese = build_workflow_page_view_model(backend, "lineage_work", view_mode="current_work", language="zh")
    english = build_workflow_page_view_model(backend, "lineage_work", view_mode="current_work", language="en")

    for page, language in ((chinese, "zh"), (english, "en")):
        for action in page["action_inventory"]:
            assert action["category"]
            assert action["tooltip"]
            assert action["label_i18n"][language] == action["label"]
            assert "backend_action" not in action["tooltip"]
    assert "Available" not in chinese["available_actions"]["primary_action"]["tooltip"]
    assert "Target:" not in chinese["available_actions"]["primary_action"]["tooltip"]


def test_every_visible_stage_has_a_complete_bilingual_guidance_contract(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)
    english = build_workflow_page_view_model(backend, "lineage_work", language="en")
    chinese = build_workflow_page_view_model(backend, "lineage_work", language="zh")
    fields = {
        "stage_purpose", "current_conclusion", "why_this_matters", "user_decision_required",
        "user_decision_summary", "recommended_next_action", "expected_result", "normal_next_stage",
        "blocked_reason", "recovery_action", "limitations",
    }
    assert {stage["stage_id"] for stage in english["stages"]} == {stage["stage_id"] for stage in chinese["stages"]}
    for english_stage, chinese_stage in zip(english["stages"], chinese["stages"]):
        assert fields <= set(english_stage["guidance"])
        assert fields <= set(chinese_stage["guidance"])
        assert english_stage["guidance"]["stage_purpose"]
        assert chinese_stage["guidance"]["stage_purpose"]
        assert all(ord(char) < 128 or "\u4e00" <= char <= "\u9fff" or char in "，。；：、（）" for char in chinese_stage["guidance"]["current_conclusion"])
        assert isinstance(english_stage["guidance"]["user_decision_required"], bool)


def test_contract_guidance_and_snapshot_guidance_preserve_user_workflow_semantics(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)
    current = build_workflow_page_view_model(backend, "lineage_work", selected_stage_id="part_modeling")
    snapshot = build_workflow_page_view_model(
        backend, "lineage_work", view_mode="run_snapshot", selected_run_id="accepted_root", selected_stage_id="part_modeling",
    )
    assert current["selected_stage"]["guidance"]["normal_next_stage"] == "Part Result Review"
    assert snapshot["selected_stage"]["guidance"]["user_decision_summary"].startswith("This historical Run is read-only")
    assert snapshot["selected_stage"]["guidance"]["recovery_action"].startswith("Return to Current Work")
