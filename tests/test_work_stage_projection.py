"""Regression coverage for Work-level Workflow graph lineage aggregation."""

from __future__ import annotations

import json

from ai_native_cad.examples import golden_desktop_robot_arm as golden_service
from ai_native_cad.pipeline import runner as pipeline_runner
from ai_native_cad.workflow_console import WorkflowConsoleBackend
from ai_native_cad.workflow_console.nicegui_app import build_console_page_data
from ai_native_cad.workflow_console.work_stage_projection import build_work_stage_projection


def _golden_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    workspace = tmp_path / "workspace"
    result = golden_service.run_golden_workflow(workspace, mode="contract", project_root=tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path, workspace_root=workspace)
    run = workspace / "works" / result["work_id"] / "runs" / result["run_id"]
    return backend, result, run


def test_golden_work_projection_discovers_nested_lineage_and_contract_statuses(tmp_path, monkeypatch):
    backend, result, _ = _golden_contract(tmp_path, monkeypatch)

    projection = build_work_stage_projection(backend, result["work_id"])
    stages = projection["stages"]

    assert all(stages[key]["status"] == "completed" for key in (
        "requirement", "clarification", "planning", "assembly_plan", "part_request",
        "part_review", "reviewed_handoff", "cad_ir_draft", "workflow_review",
    ))
    assert stages["part_modeling"]["status"] == "execution_skipped"
    assert stages["part_modeling"]["status"] != "blocked"
    assert stages["part_modeling"]["input_status"] == "accepted_upstream"
    assert stages["part_modeling"]["execution_status"] == "skipped"
    assert stages["part_modeling"]["result_status"] == "contract_complete"
    assert stages["part_modeling"]["user_review_status"] == "not_reviewed"
    assert stages["part_modeling"]["capability_mode"] == "contract"
    assert stages["part_result_review"]["status"] == "skipped"
    assert stages["rework"]["status"] == "not_started"
    assert stages["part_request"]["output_artifacts"][0]["source_relative_path"] == "02_part_request/part_create_request.json"
    assert stages["part_review"]["output_artifacts"][0]["source_relative_path"] == "03_review/part_request_review.json"
    assert stages["reviewed_handoff"]["output_artifacts"][0]["source_relative_path"] == "04_handoff/reviewed_part_handoff.json"
    modeling_outputs = {item["name"]: item for item in stages["part_modeling"]["output_artifacts"] if item["present"]}
    assert modeling_outputs["input_ir.json"]["source_relative_path"].endswith("single_part_upper_link/input_ir.json")
    assert stages["workflow_review"]["source_relative_path"] == "workflow_review.json"


def test_golden_full_projection_completes_modeling_and_result_review(tmp_path, monkeypatch):
    backend, result, run = _golden_contract(tmp_path, monkeypatch)
    child = run / "05_single_create" / "single_part_upper_link"
    (child / "model.step").write_text("STEP", encoding="utf-8")
    (child / "model.stl").write_text("solid model\nendsolid model\n", encoding="utf-8")
    review_dir = run / "06_part_result_review"
    review_dir.mkdir()
    (review_dir / "part_result_review.json").write_text(json.dumps({"status": "accepted", "part_id": "upper_link"}), encoding="utf-8")
    golden_path = run / "golden_example.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    golden["mode"] = "full"
    golden["execution"]["execution_skipped"] = False
    golden_path.write_text(json.dumps(golden), encoding="utf-8")
    backend.invalidate_work_index()

    stages = build_work_stage_projection(backend, result["work_id"])["stages"]
    assert stages["part_modeling"]["status"] == "completed"
    assert stages["part_modeling"]["execution_status"] == "completed"
    assert stages["part_modeling"]["result_status"] == "generated"
    assert stages["part_modeling"]["user_review_status"] == "not_reviewed"
    assert stages["part_result_review"]["status"] == "completed"
    assert stages["part_result_review"]["agent_review_status"] == "accepted"
    assert stages["part_result_review"]["user_review_status"] == "not_reviewed"
    outputs = {item["name"]: item for item in stages["part_modeling"]["output_artifacts"] if item["present"]}
    assert outputs["model.step"]["source_relative_path"].endswith("single_part_upper_link/model.step")
    assert outputs["model.stl"]["source_relative_path"].endswith("single_part_upper_link/model.stl")


def test_work_graph_and_detail_share_projection_when_latest_run_is_child(tmp_path, monkeypatch):
    backend, result, run = _golden_contract(tmp_path, monkeypatch)
    child = run.parent / "workflow_review_child"
    child.mkdir()
    (child / "workflow_review.json").write_text(json.dumps({"status": "completed"}), encoding="utf-8")
    manifest_path = run.parent.parent / "work_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["current_run_id"] = child.name
    manifest["run_ids"].append(child.name)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    backend.invalidate_work_index()

    data = build_console_page_data(
        backend,
        child.name,
        selected_work_id=result["work_id"],
        active_page="workflow",
        selected_stage_id="part_modeling",
    )
    surface = data["workflow_review_surface"]
    nodes = surface["graph_nodes"]

    assert data["selected_run_id"] == child.name  # history/default audit selection is still independent
    assert {node["stage_id"]: node["status"] for node in nodes}["requirement"] == "completed"
    assert surface["selected_stage"]["status"] == "execution_skipped"
    assert {stage["key"]: stage["status"] for stage in surface["stages"]}["part_modeling"] == surface["selected_stage"]["status"]
    for node in nodes:
        assert node["stage_id"]
        assert node["label"]
        assert node["status"]
        assert node["short_summary"]
        assert isinstance(node["source_artifact_count"], int)
