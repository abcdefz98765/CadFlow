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
    assert page["source"]["projection"] == "agent_first"
    assert page["workflow_graph"]["state_source"] == "work_manifest_runs_part_jobs_artifact_references"
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
    nodes = page["workflow_graph"]["nodes"]

    assert nodes
    for node in nodes:
        assert node["id"]
        assert node["label"]
        assert node["status"]
        assert node["kind"]
        assert node["group"] in {"intent", "design", "build_evaluate", "accept_deliver"}
        assert isinstance(node["selected"], bool)
        assert node["status"] != "selected"
    assert [item["id"] for item in page["phase_groups"]] == [
        "intent", "design", "build_evaluate", "accept_deliver"
    ]
    assert {item["id"] for item in nodes} != {item["id"] for item in page["phase_groups"]}


def test_selecting_current_work_graph_node_is_presentation_only(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)
    before = backend._read_work_manifest("lineage_work")
    page = build_workflow_page_view_model(
        backend, "lineage_work", view_mode="current_work", selected_stage_id="work:request"
    )

    assert page["selected_node"]["id"] == "work:request"
    assert page["workflow_graph"]["selection_is_presentation_only"] is True
    assert backend._read_work_manifest("lineage_work") == before


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

    page = build_workflow_page_view_model(
        backend,
        "lineage_work",
        view_mode="run_snapshot",
        selected_run_id="accepted_root",
        selected_stage_id="workflow_review",
    )
    stage = page["selected_stage"]

    assert stage["agent_output"]["summary"].startswith("Workflow review created successfully")
    assert stage["agent_output"]["validation_status"] == "passed"
    assert stage["user_input"]["summary"] == "The selected upper_link result was ready for work-level review."
    output = {item["name"]: item for item in stage["agent_output"]["artifacts"]}
    assert output["workflow_review.json"]["open_action"] == {"type": "artifact_dialog"}
    assert output["workflow_review.json"]["source_run_id"] == "accepted_root"
    reports = next(item for item in stage["evidence"] if item["name"] == "report.json")
    assert "token" not in reports["content"]
    assert "raw_provider_response" not in reports["content"]
    assert page["read_only"] is True


def test_dynamic_graph_phase_groups_and_node_labels_are_bilingual(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)

    chinese = build_workflow_page_view_model(backend, "lineage_work", view_mode="current_work", language="zh")
    english = build_workflow_page_view_model(backend, "lineage_work", view_mode="current_work", language="en")

    assert [item["label"] for item in chinese["phase_groups"]] == ["意图", "设计", "构建与评估", "接受与交付"]
    assert [item["label"] for item in english["phase_groups"]] == ["Intent", "Design", "Build & Evaluate", "Accept & Deliver"]
    assert chinese["nodes"][0]["label"] == "用户请求"
    assert english["nodes"][0]["label"] == "User request"


def test_multi_part_current_work_has_one_branch_per_durable_part_job(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work(
        "Two-part fixture",
        "Design a base and a cover as separate parts.",
        work_id="two_part_work",
    )
    backend.create_work_part_attempt(
        "two_part_work", "base", role="base plate", run_id="base_attempt_1"
    )
    backend.create_work_part_attempt(
        "two_part_work", "cover", role="protective cover", run_id="cover_attempt_1"
    )

    page = build_workflow_page_view_model(backend, "two_part_work", language="en")

    assert [item["part_job_id"] for item in page["workflow_graph"]["branches"]] == [
        "base", "cover"
    ]
    assert {
        node["part_job_id"] for node in page["nodes"] if node["kind"] == "part"
    } == {"base", "cover"}
    assert not any(node["kind"] == "assembly" for node in page["nodes"])
    assert page["workflow_graph"]["compatibility_mode"] is False


def test_legacy_part_job_is_badged_as_compatibility_projection(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work("Legacy fixture", "Imported fixture.", work_id="legacy_work")
    backend.create_work_part_attempt(
        "legacy_work", "legacy_part", role="legacy part", run_id="legacy_attempt"
    )
    manifest = backend._read_work_manifest("legacy_work")
    manifest["part_jobs"][0]["source"] = "assembly_plan"
    backend._write_work_manifest("legacy_work", manifest)
    backend.invalidate_work_index()

    page = build_workflow_page_view_model(backend, "legacy_work", language="en")

    assert page["workflow_graph"]["compatibility_mode"] is True
    assert any(edge["type"] == "imported" for edge in page["edges"])


def test_revision_edges_are_not_inferred_from_prompt_or_attempt_order(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work("Fixture", "Design a clamp.", work_id="no_inference_work")
    backend.create_work_part_attempt(
        "no_inference_work", "clamp", prompt="Design the clamp.", run_id="attempt_1"
    )
    backend.create_work_part_attempt(
        "no_inference_work",
        "clamp",
        prompt="Revise the earlier clamp and make it wider.",
        run_id="attempt_2",
    )

    page = build_workflow_page_view_model(backend, "no_inference_work", language="en")
    second_id = "attempt:clamp:attempt_2"

    assert page["nodes"][-1]["detail"]["source_result_id"] is None
    assert any(
        edge["target"] == second_id and edge["type"] == "attempted"
        for edge in page["edges"]
    )
    assert not any(
        edge["target"] == second_id and edge["type"] == "revised"
        for edge in page["edges"]
    )


def test_contract_guidance_and_snapshot_guidance_preserve_user_workflow_semantics(tmp_path):
    backend = _work_with_failed_latest_attempt(tmp_path)
    snapshot = build_workflow_page_view_model(
        backend, "lineage_work", view_mode="run_snapshot", selected_run_id="accepted_root", selected_stage_id="part_modeling",
    )
    assert snapshot["selected_stage"]["guidance"]["user_decision_summary"].startswith("This historical Run is read-only")
    assert snapshot["selected_stage"]["guidance"]["recovery_action"].startswith("Return to Current Work")
