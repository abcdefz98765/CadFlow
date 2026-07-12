import json
import os

import pytest

import ai_native_cad.examples as examples_service
from ai_native_cad.cadquery import executor as cadquery_executor
from ai_native_cad.pipeline import runner as pipeline_runner
from ai_native_cad.workflow_console import WorkflowConsoleBackend, dispatch_route
from ai_native_cad.workflow_console.nicegui_app import (
    _create_golden_example_ui,
    build_console_page_data,
)


def _backend(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path, workspace_root=tmp_path / "workspace")
    backend.create_workspace(name="Product Golden Test")
    return backend


def test_web_route_creates_contract_example_with_product_status(tmp_path, monkeypatch):
    backend = _backend(tmp_path, monkeypatch)

    response = dispatch_route(backend, "create_golden_example", body={"mode": "contract"})

    assert response["ok"] is True
    result = response["data"]
    assert result["execution"] == {
        "status": "contract_complete",
        "execution_skipped": True,
        "cad_ir_validated": True,
        "input_ir_created": True,
        "step_stl_expected": False,
        "assembly_generated": False,
        "result_scope": "single_generic_concept_part",
    }
    assert not any(event["status"] == "blocked" for event in result["progress"])
    assert any(event["stage"] == "cadquery_generation" and event["status"] == "skipped" for event in result["progress"])
    summary = backend.get_golden_example_summary(result["work_id"])
    assert summary["comparison"]["passed"] is True
    assert summary["comparison"]["matched_stage_count"] == summary["comparison"]["stage_count"]
    data = build_console_page_data(
        backend,
        result["run_id"],
        selected_work_id=result["work_id"],
        active_page="workflow",
        selected_stage_id="part_modeling",
    )
    stages = {stage["key"]: stage for stage in data["workflow_review_surface"]["stages"]}
    assert stages["part_modeling"]["status"] == "completed"
    assert stages["part_modeling"]["status"] != "blocked"


def test_web_backend_calls_shared_service_for_full_mode(tmp_path, monkeypatch):
    backend = _backend(tmp_path, monkeypatch)
    calls = []

    def fake_service(workspace, *, mode, project_root, progress_callback, backend):
        calls.append({"workspace": workspace, "mode": mode, "project_root": project_root, "backend": backend})
        return {"work_id": "golden_attempt", "run_id": "golden_attempt_root", "mode": mode, "progress": [], "comparison": {"passed": True}}

    monkeypatch.setattr(examples_service, "run_golden_desktop_robot_arm", fake_service)
    response = dispatch_route(backend, "create_golden_example", body={"mode": "full"})

    assert response["ok"] is True
    assert calls == [{"workspace": backend.workspace_root, "mode": "full", "project_root": backend.project_root, "backend": backend}]


def test_golden_attempts_are_append_only(tmp_path, monkeypatch):
    backend = _backend(tmp_path, monkeypatch)

    first = backend.create_golden_example("contract")
    second = backend.create_golden_example("contract")

    assert first["work_id"] == "golden_desktop_robot_arm"
    assert second["work_id"] == "golden_desktop_robot_arm_attempt_2"
    assert backend.get_work_detail(first["work_id"])["summary"]["work_id"] == first["work_id"]
    assert backend.get_work_detail(second["work_id"])["summary"]["work_id"] == second["work_id"]


def test_example_completion_navigates_to_workflow_and_selects_work(monkeypatch):
    result = {
        "work_id": "golden_desktop_robot_arm_attempt_2",
        "run_id": "golden_desktop_robot_arm_attempt_2_root",
        "progress": [{"stage": "comparison", "status": "completed", "message": "Golden comparison passed"}],
    }
    class Backend:
        def create_golden_example(self, mode, progress_callback=None):
            if progress_callback:
                progress_callback(result["progress"][0])
            return result

    state = {"_backend": Backend(), "active_page": "workspace"}
    refreshed = []

    _create_golden_example_ui("contract", state, lambda: refreshed.append(True))

    assert state["selected_work_id"] == result["work_id"]
    assert state["selected_run_id"] == result["run_id"]
    assert state["active_page"] == "workflow"
    assert state["selected_stage_id"] == "workflow_review"
    assert refreshed == [True, True]


@pytest.mark.skipif(os.environ.get("CADFLOW_RUN_SLOW_GOLDEN") != "1", reason="slow full Web golden smoke is opt-in")
def test_full_example_workflow_view_aggregates_child_outputs(tmp_path, monkeypatch):
    backend = _backend(tmp_path, monkeypatch)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)

    result = backend.create_golden_example("full")
    data = build_console_page_data(
        backend,
        result["run_id"],
        selected_work_id=result["work_id"],
        active_page="workflow",
        selected_stage_id="part_modeling",
    )

    surface = data["workflow_review_surface"]
    stages = {stage["key"]: stage for stage in surface["stages"]}
    assert stages["part_modeling"]["status"] == "completed"
    assert stages["part_result_review"]["status"] == "completed"
    assert stages["workflow_review"]["status"] == "completed"
    evidence = {item["artifact"] for item in surface["evidence_chain"]}
    assert {"cad_ir_draft.json", "input_ir.json", "model.step", "model.stl"} <= evidence
    golden = data["selected_work"]["golden_example"]
    assert golden["comparison"]["passed"] is True
    assert golden["execution"]["assembly_generated"] is False
    assert golden["execution"]["result_scope"] == "single_generic_concept_part"
