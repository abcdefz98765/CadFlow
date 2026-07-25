import importlib.util
import asyncio
import json
from pathlib import Path

import pytest

from ai_native_cad.workflow_console import WorkflowConsoleBackend
from ai_native_cad.workflow_console.nicegui_app import (
    ARTIFACT_PAGE_ARTIFACTS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_RUN_PAGE_SIZE,
    REVIEWED_PART_ACTIONS,
    build_assembly_plan_data,
    build_console_page_data,
    build_part_workflow_data,
    build_requirement_review_data,
    build_workflow_review_surface,
    build_stage_review_data,
    build_workflow_review_data,
    build_artifacts_page_data,
    read_artifact_page_content,
    WORK_USER_PAGES,
    PAGE_IDS,
    _page_selection_callback,
    _select_console_page,
    _select_console_run,
    _select_console_work,
    _select_current_console_work,
    _part_viewer_url,
    _run_workflow_page_action,
    _execute_action_lifecycle,
    _save_artifact_override_ui,
)
from ai_native_cad.workflow_console.routes import dispatch_route
from ai_native_cad.workflow_console.review_surface import REVIEW_SURFACE_ARTIFACTS
from ai_native_cad.workflow_console.stage_runner import READABLE_ARTIFACTS
from ai_native_cad.workflow_console.actions import WorkflowConsoleActions


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _does_not_contain_absolute_paths(value, root: Path):
    if isinstance(value, dict):
        return all(_does_not_contain_absolute_paths(item, root) for item in value.values())
    if isinstance(value, list):
        return all(_does_not_contain_absolute_paths(item, root) for item in value)
    if isinstance(value, str):
        return str(root.resolve()) not in value and not Path(value).is_absolute()
    return True


def test_console_page_navigation_contract_preserves_work_and_reaches_workflow_view_model(tmp_path):
    _sample_work(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    refreshes = []
    state = {
        "selected_work_id": "enclosure_work",
        "selected_node_id": "legacy-node",
        "selected_stage_id": "planning",
        "view_mode": "current_work",
    }

    _select_console_work(state, "enclosure_work", lambda: refreshes.append("work"))
    assert state["active_page"] == "overview"
    assert state["selected_work_id"] == "enclosure_work"

    _select_console_page(state, "workflow", lambda: refreshes.append("workflow"))
    assert state["active_page"] == "workflow"
    assert state["selected_work_id"] == "enclosure_work"
    assert state["selected_node_id"] is None
    assert state["selected_stage_id"] is None
    workflow = build_console_page_data(backend, selected_work_id=state["selected_work_id"], active_page=state["active_page"])
    assert workflow["active_page"] == state["active_page"]
    assert isinstance(workflow["workflow_page"], dict)

    _select_console_page(state, "parts", lambda: refreshes.append("parts"))
    assert state["active_page"] == "parts"
    _select_console_page(state, "history", lambda: refreshes.append("history"))
    assert state["active_page"] == "history"
    assert refreshes == ["work", "workflow", "parts", "history"]


def test_console_navigation_callbacks_consume_events_and_snapshot_boundaries():
    selected_pages = []
    callback = _page_selection_callback(selected_pages.append, "workflow")
    callback(object())
    assert selected_pages == ["workflow"]
    assert all(page in PAGE_IDS for page in selected_pages)

    state = {"selected_work_id": "work-1", "selected_node_id": "node-1", "selected_stage_id": "part_modeling"}
    refreshes = []
    _select_console_run(state, "run-1", lambda: refreshes.append("run"))
    assert state["active_page"] == "workflow"
    assert state["view_mode"] == "run_snapshot"
    assert state["selected_run_id"] == "run-1"

    _select_current_console_work(state, lambda: refreshes.append("current"))
    assert state["active_page"] == "workflow"
    assert state["view_mode"] == "current_work"
    assert state["selected_run_id"] is None
    assert refreshes == ["run", "current"]

    with pytest.raises(ValueError):
        _select_console_page(state, object(), lambda: None)
    with pytest.raises(ValueError):
        _select_console_page(state, "not-a-page", lambda: None)


def test_workflow_action_refreshes_without_touching_the_deleted_button_slot():
    class NoNotifyUi:
        def notify(self, *_args, **_kwargs):
            raise AssertionError("workflow action must not notify after refresh")

    class FakeActions:
        def create_part_request(self, run_id):
            assert run_id == "active_run"
            return {"ok": True, "artifact": "part_create_request.json"}

    state = {}
    refreshes = []
    _run_workflow_page_action(
        NoNotifyUi(),
        FakeActions(),
        {
            "enabled": True,
            "target_run_id": "active_run",
            "backend_action": "part_request",
            "next_stage_on_success": "part_review",
        },
        state,
        lambda: refreshes.append(True),
    )

    assert len(refreshes) >= 2  # pending is rendered before the backend completes
    assert state["selected_stage_id"] == "part_review"
    assert state["action_execution"]["status"] == "succeeded"
    assert state["action_execution"]["postcondition_verified"] is True


def test_action_lifecycle_reports_failed_postcondition_and_rejects_duplicate_click():
    state = {}
    refreshes = []
    action = {"key": "select_candidate_part", "label": "Use This Part Next", "target_work_id": "work", "target_run_id": "run", "target_stage_id": "assembly_plan", "part_id": "lower_link"}
    calls = []

    async def exercise():
        async def first():
            return await _execute_action_lifecycle(
                action, state, lambda: refreshes.append(True), lambda: calls.append("run") or {"ok": True},
                language="zh", verify=lambda _result: (False, "postcondition mismatch"),
            )
        task = asyncio.create_task(first())
        await asyncio.sleep(0)
        duplicate = await _execute_action_lifecycle(
            action, state, lambda: refreshes.append(True), lambda: calls.append("duplicate") or {"ok": True}, language="zh"
        )
        await task
        return duplicate

    assert asyncio.run(exercise()) is None
    assert calls == ["run"]
    assert state["action_execution"]["status"] == "failed"
    assert state["action_execution"]["postcondition_verified"] is False
    assert "postcondition mismatch" in state["action_execution"]["error_detail"]


def _does_not_contain_text(value, blocked):
    if isinstance(value, dict):
        return all(_does_not_contain_text(key, blocked) and _does_not_contain_text(item, blocked) for key, item in value.items())
    if isinstance(value, list):
        return all(_does_not_contain_text(item, blocked) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return all(item.lower() not in lowered for item in blocked)
    return True


def _sample_run(tmp_path):
    run_dir = tmp_path / "outputs" / "nicegui_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a desktop enclosure with a base and lid.\n", encoding="utf-8")
    _write_json(
        run_dir / "requirement.json",
        {
            "part_type": "enclosure",
            "part_family": "housing",
            "product_family": "desktop accessory",
            "scope": "multi_part",
            "dimensions": {},
            "assumptions": ["Use millimeters."],
            "missing_information": [{"field": "mounting", "message": "Mounting style not specified."}],
            "follow_up_questions": ["Should the lid snap on?"],
            "requirement_status": {
                "flow_decision": {"action": "ask_user", "to_stage": "requirement"},
            },
            "diagnostic_codes": ["requirement.needs_mounting"],
        },
    )
    _write_json(
        run_dir / "requirement_v2.json",
        {
            "part_type": "enclosure",
            "part_family": "housing",
            "intent": {"scope": "multi_part", "object_goal": "desktop enclosure"},
            "assumptions": ["Use millimeters."],
            "missing_information": [],
            "follow_up_questions": [],
            "requirement_status": {
                "flow_decision": {"action": "proceed_with_assumptions", "to_stage": "planning"},
            },
            "clarification_applied": True,
        },
    )
    _write_json(
        run_dir / "planning_artifact.json",
        {
            "artifact_type": "planning",
            "route": {"selected": "assembly_split"},
            "flow_gate_status": {
                "status": "ready_for_review",
                "blocking_reasons": [{"code": "assembly_requires_review"}],
                "rework_decision": {"action": "return_to_requirement"},
            },
        },
    )
    _write_json(
        run_dir / "01_design" / "assembly_plan.json",
        {
            "artifact_type": "assembly_plan",
            "scope": "multi_part",
            "status": "blocked_before_part_generation",
            "parts": [
                {
                    "part_id": "base",
                    "role": "main housing",
                    "generation_strategy": "future_part_pipeline",
                    "part_status": "candidate_for_single_part_generation",
                    "supported_candidate": True,
                },
                {
                    "part_id": "lid",
                    "role": "cover",
                    "generation_strategy": "future_part_pipeline",
                    "part_status": "blocked",
                    "supported_candidate": False,
                    "blocked_reasons": [{"code": "missing_lid_interface"}],
                },
                {
                    "part_id": "screws",
                    "role": "fasteners",
                    "generation_strategy": "reference_only",
                    "part_status": "reference_only",
                    "supported_candidate": False,
                },
            ],
            "interfaces": [{"from": "base", "to": "lid"}],
            "blocked_reasons": [{"code": "assembly_requires_review"}],
        },
    )
    _write_json(run_dir / "02_part_request" / "part_create_request.json", {"part_id": "base", "status": "ready_for_review"})
    _write_json(run_dir / "03_review" / "part_request_review.json", {"status": "approved"})
    _write_json(run_dir / "04_handoff" / "reviewed_part_handoff.json", {"part_id": "base", "status": "ready_for_single_part_planning"})
    _write_json(run_dir / "05_single_create" / "part_execution_request.json", {"part_id": "base", "status": "ready"})
    _write_json(run_dir / "05_single_create" / "cad_ir_draft.json", {"part_type": "upper_link", "diagnostic_codes": ["cad_ir.unsupported_part_type"]})
    _write_json(
        run_dir / "05_single_create" / "report.json",
        {"status": "blocked_cad_ir_validation", "blocked_stage": "cad_ir_validation", "errors": [{"code": "unsupported_part_type"}]},
    )
    _write_json(run_dir / "agent_trace.json", {"raw_provider_response": "SECRET_TOKEN", "safe": "ok", "path": str(tmp_path)})
    (run_dir / "model.step").write_text("STEP\n", encoding="utf-8")
    return run_dir


def _add_workflow_review(run_dir: Path):
    _write_json(
        run_dir / "workflow_review.json",
        {
            "schema_version": 1,
            "overall_status": "accepted_for_preview",
            "readiness_score": 88,
            "confidence": {"cad_result": "high"},
            "risk_level": "medium",
            "summary": ["Base was selected and generated as a single part."],
            "key_diagnostics": ["part_result.step_created"],
            "risks": ["No geometric fit validation with lid."],
            "recommended_next_actions": ["Review the generated STEP/STL."],
            "scoring_explanation": ["STEP availability adds readiness."],
        },
    )
    (run_dir / "workflow_review.md").write_text("# Workflow Review\n", encoding="utf-8")


def _sample_work(tmp_path):
    work_dir = tmp_path / "workspace" / "works" / "enclosure_work"
    root = work_dir / "runs" / "enclosure_work_root"
    child = root / "05_single_create" / "single_part_base"
    child.mkdir(parents=True)
    _write_json(
        work_dir / "work_manifest.json",
        {
            "schema_version": 1,
            "work_id": "enclosure_work",
            "title": "Enclosure Work",
            "description": "Two-part enclosure fixture.",
            "status": "active",
            "root_run_id": "enclosure_work_root",
            "current_run_id": "enclosure_work_root",
            "run_ids": ["enclosure_work_root", "rework_workflow_review_1"],
            "part_jobs": [],
            "requirement": {"status": "confirmed", "root_run_id": "enclosure_work_root"},
            "advancement_mode": "manual_confirm",
            "metadata": {},
        },
    )
    (root / "prompt.txt").write_text("Two-part electronics enclosure with base, lid, and screws.\n", encoding="utf-8")
    _write_json(root / "requirement.json", {"product_family": "electronics enclosure", "scope": "multi_part"})
    _write_json(
        root / "01_design" / "assembly_plan.json",
        {
            "scope": "multi_part",
            "status": "blocked_before_part_generation",
            "parts": [
                {
                    "part_id": "base",
                    "role": "base",
                    "generation_strategy": "future_part_pipeline",
                    "part_status": "candidate_for_single_part_generation",
                    "supported_candidate": True,
                },
                {
                    "part_id": "lid",
                    "role": "lid",
                    "generation_strategy": "future_part_pipeline",
                    "part_status": "blocked",
                    "supported_candidate": False,
                    "blocked_reasons": [{"code": "unsupported_part_type.lid"}],
                },
                {
                    "part_id": "screws",
                    "role": "fastener",
                    "generation_strategy": "reference_only",
                    "part_status": "reference_only",
                    "supported_candidate": False,
                },
            ],
            "interfaces": [{"from": "base", "to": "lid"}],
        },
    )
    _write_json(root / "05_single_create" / "lineage.json", {"relationship": "reviewed_part_single_create_child", "part_id": "base", "child_run_id": "single_part_base"})
    _write_json(
        root / "06_part_result_review" / "part_result_review.json",
        {
            "part_id": "base",
            "child_run": "single_part_base",
            "status": "accepted_for_preview",
            "checks": {"step_created": True, "stl_created": True},
            "diagnostic_codes": ["part_result.step_created"],
        },
    )
    _write_json(root / "workflow_review.json", {"overall_status": "needs_revision", "readiness_score": 68, "risk_level": "medium", "summary": ["Base accepted; lid blocked."]})
    (root / "workflow_review.md").write_text("# Workflow Review\n", encoding="utf-8")
    _write_json(root / "stage_review.json", {"stage": "assembly_plan", "review_status": "needs_revision", "target_rework_stage": "workflow_review"})
    _write_json(root / "rework_decision.json", {"execution_status": "completed", "target_rework_stage": "workflow_review", "child_run_id": "rework_workflow_review_1"})
    rework = work_dir / "runs" / "rework_workflow_review_1"
    rework.mkdir(parents=True)
    _write_json(rework / "workflow_review.json", {"overall_status": "needs_revision", "risk_level": "medium"})
    (child / "model.step").write_text("STEP\n", encoding="utf-8")
    (child / "model.stl").write_text("STL\n", encoding="utf-8")
    _write_json(child / "report.json", {"status": "success", "success": True})
    debug = tmp_path / "outputs" / "debug_probe"
    debug.mkdir(parents=True)
    (debug / "prompt.txt").write_text("Tiny debug run.\n", encoding="utf-8")
    return root


def test_nicegui_console_builds_page_data_from_fake_run_summaries(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend, "nicegui_run")

    assert data["selected_run_id"] == "nicegui_run"
    assert data["runs"] == []
    assert data["requirement_review"]["original_prompt"].startswith("Make a desktop enclosure")
    assert data["assembly_plan"]["candidate_part_ids"] == ["base"]
    assert data["assembly_plan"]["interface_count"] == 1
    assert data["part_workflow"]["actions"][0]["available"] is True


def test_nicegui_defaults_to_workspace_page_without_selecting_first_work(tmp_path):
    _sample_work(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend)

    assert data["active_page"] == "workspace"
    assert data["selected_work_id"] is None
    assert data["selected_work"]["summary"] is None
    assert data["workspace"]["display_path"] == "workspace"
    assert not Path(data["workspace"]["display_path"]).is_absolute()
    assert data["workspace"]["work_count"] == 1


def test_nicegui_work_dashboard_infers_work_and_hides_debug_by_default(tmp_path):
    _sample_work(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend, selected_work_id="enclosure_work", active_page="overview")
    works = data["works"]
    detail = data["selected_work"]

    assert [work["work_id"] for work in works] == ["enclosure_work"]
    assert works[0]["overall_status"] == "needs_review"
    assert works[0]["part_counts"] == {
        "total": 3,
        "accepted": 0,
        "blocked": 1,
        "needs_review": 1,
        "reference_only": 1,
        "incomplete": 0,
    }
    assert works[0]["readiness_score"] == 68
    assert detail["current_state"]["current_run_id"] in {"enclosure_work_root", "rework_workflow_review_1"}
    assert detail["history_semantics"]["runs_are_immutable"] is True
    assert {row["run_id"] for row in detail["run_history"]} == {"enclosure_work_root", "rework_workflow_review_1"}


def test_nicegui_work_detail_separates_current_state_parts_nodes_and_products(tmp_path):
    _sample_work(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    detail = build_console_page_data(backend, selected_work_id="enclosure_work")["selected_work"]
    parts = {part["part_id"]: part for part in detail["parts"]}
    node_status = {node["id"]: node["status"] for node in detail["nodes"]}
    products = detail["products"]

    assert parts["base"]["status"] == "needs_review"
    assert parts["base"]["user_review_status"] == "not_reviewed"
    assert parts["base"]["agent_review_status"] == "accepted_for_preview"
    assert parts["base"]["deliverable_available"] is False
    assert parts["base"]["has_step"] is True
    assert parts["lid"]["status"] == "blocked"
    assert parts["screws"]["status"] == "reference_only"
    assert node_status["assembly_plan"] == "completed"
    assert node_status["part:base"] == "needs_review"
    assert node_status["part:lid"] == "blocked"
    assert products["human_facing"] == []
    assert "workflow_review.md" in {item["name"] for item in products["supporting_artifacts"]}
    assert products["downloadables"] == []
    assert {item["name"] for item in products["reviewable_outputs"]} == {"model.step", "model.stl"}
    assert products["artifact_state"] == {
        "accepted_deliverable_count": 0,
        "reviewable_output_count": 2,
        "failed_attempt_output_count": 0,
        "untrusted_output_count": 0,
    }
    directory_map = detail["directory_map"]
    assert [item["label"] for item in directory_map["inputs"]["items"]] == ["Original request", "Reviewed requirement"]
    assert {item["label"] for item in directory_map["parts"]["items"]} == {"base", "lid", "screws"}
    assert {item["label"] for item in directory_map["history"]["items"]} == {"enclosure_work_root", "rework_workflow_review_1"}
    assert products["artifacts_secondary_by_default"] is True
    assert _does_not_contain_absolute_paths(detail, tmp_path)


def test_nicegui_deliverables_require_explicit_accepted_result_pointer(tmp_path):
    _sample_work(tmp_path)
    manifest_path = tmp_path / "workspace" / "works" / "enclosure_work" / "work_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["accepted_part_results"] = {
        "base": {
            "child_run_id": "single_part_base",
            "review_id": "review_001",
            "status": "approved",
        }
    }
    _write_json(manifest_path, manifest)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    detail = build_console_page_data(backend, selected_work_id="enclosure_work")["selected_work"]
    base = next(part for part in detail["parts"] if part["part_id"] == "base")
    products = detail["products"]

    assert base["status"] == "accepted"
    assert base["user_review_status"] == "approved"
    assert base["deliverable_available"] is True
    assert {item["name"] for item in products["accepted_deliverables"]} == {"model.step", "model.stl"}
    assert {item["name"] for item in products["downloadables"]} == {"model.step", "model.stl"}
    assert products["reviewable_outputs"] == []


def test_nicegui_product_projection_does_not_trust_file_presence_without_success_state(tmp_path):
    _sample_work(tmp_path)
    child_report = (
        tmp_path
        / "workspace"
        / "works"
        / "enclosure_work"
        / "runs"
        / "enclosure_work_root"
        / "05_single_create"
        / "single_part_base"
        / "report.json"
    )
    _write_json(child_report, {"status": "unknown", "success": None})
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    products = build_console_page_data(backend, selected_work_id="enclosure_work")["selected_work"]["products"]

    assert products["accepted_deliverables"] == []
    assert products["reviewable_outputs"] == []
    assert products["artifact_state"]["untrusted_output_count"] == 2


def test_nicegui_work_dashboard_does_not_mix_debug_group_into_work_list(tmp_path):
    _sample_work(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    hidden = build_console_page_data(backend)
    shown = build_console_page_data(backend, show_debug_works=True)

    assert "__debug_runs__" not in {work["work_id"] for work in hidden["works"]}
    assert "__debug_runs__" not in {work["work_id"] for work in shown["works"]}


def test_nicegui_real_work_entity_can_be_created_without_runs_or_cad(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    response = dispatch_route(
        backend,
        "create_work",
        body={"work_id": "electronics_enclosure", "title": "Electronics Enclosure", "description": "Base and lid project."},
    )
    data = build_console_page_data(backend, selected_work_id="electronics_enclosure")
    manifest = json.loads((tmp_path / "workspace" / "works" / "electronics_enclosure" / "work_manifest.json").read_text(encoding="utf-8"))

    assert response["ok"] is True
    assert response["status_code"] == 201
    assert response["data"]["work"]["work_id"] == "electronics_enclosure"
    assert manifest["run_ids"] == []
    assert data["selected_work"]["entity_state"]["present"] is True
    assert data["selected_work"]["summary"]["overall_status"] == "incomplete"
    assert data["selected_work"]["run_history"] == []
    assert not (tmp_path / "outputs" / "electronics_enclosure").exists()
    assert not (tmp_path / "outputs" / "_works" / "electronics_enclosure").exists()


def test_nicegui_workspace_config_and_requirement_run_are_work_scoped(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_workspace", body={"path": "workspace", "advancement_mode": "manual_confirm"})
    dispatch_route(backend, "write_workspace_config", body={"provider": "local", "advancement_mode": "manual_confirm"})
    dispatch_route(backend, "create_work", body={"work_id": "fixture", "title": "Fixture"})
    dispatch_route(
        backend,
        "create_work_requirement_run",
        path_params={"work_id": "fixture"},
        body={"prompt": "Create a fixture with two clamp blocks."},
    )

    data = build_console_page_data(backend, selected_work_id="fixture", active_page="overview")

    assert data["workspace"]["relative_path"] == "workspace"
    assert data["workspace_config"]["advancement_mode"] == "manual_confirm"
    assert data["selected_work"]["entity_state"]["requirement"]["root_run_id"] == "fixture_root"
    assert data["selected_work"]["entity_state"]["requirement"]["confirmation_required"] is True
    assert {row["run_id"] for row in data["selected_work"]["run_history"]} == {"fixture_root"}
    assert data["runs"] == []


def test_nicegui_workspace_examples_are_visible_as_workspace_works(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    response = dispatch_route(backend, "create_workspace", body={"path": "workspace", "include_examples": True})

    workspace_data = build_console_page_data(backend, active_page="workspace")
    planning_data = build_console_page_data(
        backend,
        selected_work_id="multi_part_enclosure_planning",
        active_page="parts",
    )
    reviewed_data = build_console_page_data(
        backend,
        selected_work_id="reviewed_one_part_enclosure_base",
        active_page="products",
    )

    assert response["ok"] is True
    assert workspace_data["workspace"]["work_count"] == 3
    assert {work["work_id"] for work in workspace_data["works"]} == {
        "single_part_mounting_plate",
        "multi_part_enclosure_planning",
        "reviewed_one_part_enclosure_base",
    }
    assert {part["part_id"] for part in planning_data["selected_work"]["parts"]} >= {"base", "lid", "screws"}
    assert not any(
        item["name"] == "model.step"
        for item in reviewed_data["selected_work"]["products"]["downloadables"]
    )
    assert any(
        item["name"] == "model.step"
        for item in reviewed_data["selected_work"]["products"]["reviewable_outputs"]
    )
    assert _does_not_contain_text(reviewed_data["selected_work"], ["api_key", "secret", "bearer"])


def test_nicegui_workflow_graph_groups_examples_by_stage_parts_and_review(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_workspace", body={"path": "workspace", "include_examples": True})

    single = build_console_page_data(
        backend,
        selected_work_id="single_part_mounting_plate",
        active_page="workflow",
    )["selected_work"]["workflow_graph"]
    planning = build_console_page_data(
        backend,
        selected_work_id="multi_part_enclosure_planning",
        active_page="workflow",
    )["selected_work"]["workflow_graph"]
    reviewed = build_console_page_data(
        backend,
        selected_work_id="reviewed_one_part_enclosure_base",
        active_page="workflow",
    )["selected_work"]["workflow_graph"]
    reviewed_detail = build_console_page_data(
        backend,
        selected_work_id="reviewed_one_part_enclosure_base",
        active_page="parts",
    )["selected_work"]

    assert [node["id"] for node in single["stage_nodes"]] == ["requirement", "planning"]
    assert [node["status"] for node in single["stage_nodes"]] == ["completed", "completed"]
    assert single["layout"] == "single_part"
    assert single["part_nodes"][0]["label"] == "Single Part"
    assert single["part_nodes"][0]["synthetic"] is True
    assert set(single["part_nodes"][0]["artifacts"]) == {"model.step", "model.stl"}
    assert {node["part_id"] for node in planning["part_nodes"]} >= {"base", "lid", "screws"}
    assert planning["layout"] == "multi_part"
    reviewed_parts = {node["part_id"]: node for node in reviewed["part_nodes"]}
    assert reviewed_parts["base"]["status"] == "needs_review"
    assert set(reviewed_parts) == {"base"}
    assert [node["id"] for node in reviewed["review_nodes"]] == ["result"]
    assert reviewed_parts["base"]["review_status"] == "accepted_for_preview"
    assert reviewed_parts["base"]["download_run_id"] == "single_part_enclosure_base_result"
    detail_parts = {part["part_id"]: part for part in reviewed_detail["parts"]}
    assert detail_parts["lid"]["download_run_id"] is None
    assert detail_parts["lid"]["has_stl"] is False
    assert detail_parts["screws"]["download_run_id"] is None
    assert detail_parts["screws"]["has_step"] is False
    assert _part_viewer_url(reviewed_parts["base"], reviewed_parts["base"]["download_run_id"]) == (
        "/web-viewer/index.html?file=%2Fapi%2Fdownloads%2Fsingle_part_enclosure_base_result%2Fmodel.stl"
    )


def test_nicegui_user_pages_hide_review_and_products_from_work_nav_contract():
    user_pages = [page for page, _icon, _text in WORK_USER_PAGES]

    assert "review" not in user_pages
    assert "products" not in user_pages
    assert user_pages == ["overview", "workflow", "parts", "history"]


def test_nicegui_legacy_work_manifest_under_outputs_is_not_indexed(tmp_path):
    legacy_manifest = tmp_path / "outputs" / "_works" / "legacy_work" / "work_manifest.json"
    _write_json(
        legacy_manifest,
        {
            "schema_version": 1,
            "work_id": "legacy_work",
            "title": "Legacy Work",
            "description": "Created before workspace storage.",
            "status": "incomplete",
            "run_ids": [],
            "metadata": {},
        },
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend, selected_work_id="legacy_work")

    assert data["works"] == []
    assert data["selected_work"]["error"]["type"] == "not_found"


def test_nicegui_workspace_work_manifest_wins_over_legacy_manifest(tmp_path):
    _write_json(
        tmp_path / "workspace" / "works" / "same_work" / "work_manifest.json",
        {
            "schema_version": 1,
            "work_id": "same_work",
            "title": "Workspace Work",
            "status": "incomplete",
            "run_ids": [],
            "metadata": {},
        },
    )
    _write_json(
        tmp_path / "outputs" / "_works" / "same_work" / "work_manifest.json",
        {
            "schema_version": 1,
            "work_id": "same_work",
            "title": "Legacy Work",
            "status": "incomplete",
            "run_ids": [],
            "metadata": {},
        },
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend, selected_work_id="same_work")

    assert data["selected_work"]["summary"]["title"] == "Workspace Work"


def test_nicegui_real_work_entity_rejects_unsafe_ids_and_secrets(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    bad_path = dispatch_route(backend, "create_work", body={"work_id": "../bad", "title": "Bad"})
    secret = dispatch_route(backend, "create_work", body={"work_id": "bad_secret", "title": "api_key secret"})

    assert bad_path["ok"] is False
    assert bad_path["status_code"] == 400
    assert secret["ok"] is False
    assert secret["status_code"] == 400


def test_nicegui_work_switch_does_not_load_runs_debug_page(tmp_path, monkeypatch):
    _sample_work(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    calls = []

    def fail_run_page(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("Runs / Debug should be lazy-loaded only when active.")

    monkeypatch.setattr(backend, "list_runs_page", fail_run_page)

    data = build_console_page_data(backend, selected_work_id="enclosure_work", active_page="overview")

    assert data["selected_work_id"] == "enclosure_work"
    assert data["runs"] == []
    assert calls == []


def test_nicegui_workflow_node_detail_points_to_selected_work_node(tmp_path):
    _sample_work(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(
        backend,
        selected_work_id="enclosure_work",
        active_page="node",
        selected_node_id="part:lid",
    )

    assert data["selected_node"]["id"] == "part:lid"
    assert data["selected_node"]["status"] == "blocked"


def test_nicegui_console_does_not_index_project_level_runs(tmp_path, monkeypatch):
    for index in range(DEFAULT_RUN_PAGE_SIZE + 3):
        run_dir = tmp_path / "outputs" / f"page_run_{index:02d}"
        run_dir.mkdir(parents=True)
        (run_dir / "prompt.txt").write_text(f"Make run {index}.\n", encoding="utf-8")
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    loaded_details = []
    original = backend.read_run_metadata

    def track_detail(run_dir):
        loaded_details.append(Path(run_dir).name)
        return original(run_dir)

    monkeypatch.setattr(backend, "read_run_metadata", track_detail)

    data = build_console_page_data(backend, active_page="runs", show_unclassified_runs=True, limit=25, offset=0)

    assert data["runs"] == []
    assert loaded_details == []


def test_nicegui_console_search_does_not_expose_project_level_runs(tmp_path):
    for name in ("alpha_console", "beta_console"):
        run_dir = tmp_path / "outputs" / name
        run_dir.mkdir(parents=True)
        (run_dir / "prompt.txt").write_text(f"Make {name}.\n", encoding="utf-8")
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend, active_page="runs", show_unclassified_runs=True, search="alpha")

    assert data["runs"] == []
    assert data["run_filters"] == {}


def test_nicegui_run_selection_data_excludes_absolute_paths(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend, "nicegui_run")
    data["workspace"]["display_path"] = "workspace"

    assert _does_not_contain_absolute_paths(data, tmp_path)


def test_nicegui_requirement_review_handles_missing_fields_gracefully(tmp_path):
    run_dir = tmp_path / "outputs" / "missing_negotiation"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a bracket.\n", encoding="utf-8")
    _write_json(run_dir / "requirement.json", {"part_type": "bracket", "dimensions": {}})
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run = build_console_page_data(backend, "missing_negotiation")["selected_run"]

    review = build_requirement_review_data(backend, "missing_negotiation", run)

    assert review["assumptions"] == []
    assert review["missing_information"] == []
    assert review["clarification_questions"] == []
    assert review["blocked_reason"] is None


def test_nicegui_requirement_review_exposes_clarification_state(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("arm_ui", "Design a desktop 2 DOF robotic arm with a gripper and servo.")
    backend.run_stage_by_id("arm_ui", "requirement")

    before = build_console_page_data(backend, "arm_ui")["requirement_review"]

    assert before["requirement_v2_present"] is False
    assert before["can_run_planning"] is False
    assert {item["field"] for item in before["clarification_requests"]} >= {"arm_reach_mm", "payload_mass_g"}

    backend.apply_requirement_clarification_by_id(
        "arm_ui",
        answers=[
            {"field": "arm_reach_mm", "question": "Reach?", "answer": "220 mm"},
            {"field": "payload_mass_g", "question": "Payload?", "answer": "80 g"},
            {"field": "servo_envelope", "question": "Servo?", "answer": "SG90"},
            {"field": "gripper_opening_mm", "question": "Opening?", "answer": "35 mm"},
        ],
    )
    after = build_console_page_data(backend, "arm_ui")["requirement_review"]

    assert after["requirement_v2_present"] is True
    assert after["clarification_applied"] is True
    assert after["can_run_planning"] is True
    assert after["clarification_requests"] == []


def test_nicegui_stage_review_view_model_handles_empty_and_saved_states(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    empty = build_console_page_data(backend, "nicegui_run")

    assert empty["stage_review"]["saved"] is None
    assert "requirement" in empty["stage_review"]["stage_options"]
    assert "needs_revision" in empty["stage_review"]["review_status_options"]
    assert "assembly_plan" in empty["stage_review"]["target_rework_stage_options"]

    saved = dispatch_route(
        backend,
        "action_save_stage_review",
        body={
            "run_id": "nicegui_run",
            "stage": "assembly_plan",
            "review_status": "needs_revision",
            "target_rework_stage": "requirement",
            "user_notes": "Treat lid as flat cover.",
            "requested_changes": ["Keep screws reference_only"],
        },
    )
    data = build_console_page_data(backend, "nicegui_run")

    assert saved["ok"] is True
    assert data["stage_review"]["saved"]["stage"] == "assembly_plan"
    assert data["stage_review"]["saved"]["review_status"] == "needs_revision"
    assert data["stage_review"]["saved"]["target_rework_stage"] == "requirement"
    assert data["stage_review"]["saved"]["requested_changes_count"] == 1
    assert build_stage_review_data(data["selected_run"])["saved"]["user_notes_preview"] == "Treat lid as flat cover."
    assert data["stage_review"]["rework_available"] is False
    assert "workflow_review" in data["stage_review"]["target_rework_stage_options"]


def test_nicegui_rework_view_model_handles_unsupported_and_completed_states(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    no_review = build_console_page_data(backend, "nicegui_run")

    assert no_review["stage_review"]["saved"] is None
    assert no_review["stage_review"]["rework_decision"] is None
    assert no_review["stage_review"]["rework_available"] is False

    dispatch_route(
        backend,
        "action_save_stage_review",
        body={
            "run_id": "nicegui_run",
            "stage": "assembly_plan",
            "review_status": "needs_revision",
            "target_rework_stage": "assembly_plan",
            "requested_changes": ["Treat lid as flat cover."],
        },
    )
    unsupported = build_console_page_data(backend, "nicegui_run")

    assert unsupported["stage_review"]["rework_available"] is True
    assert unsupported["stage_review"]["rework_supported"] is False
    assert "not supported" in unsupported["stage_review"]["rework_blocked_reason"]

    dispatch_route(
        backend,
        "action_save_stage_review",
        body={
            "run_id": "nicegui_run",
            "stage": "assembly_plan",
            "review_status": "needs_revision",
            "target_rework_stage": "workflow_review",
            "requested_changes": ["Refresh workflow review."],
        },
    )
    rework = dispatch_route(backend, "action_run_rework", body={"run_id": "nicegui_run"})
    completed = build_console_page_data(backend, "nicegui_run")

    assert rework["ok"] is True
    assert completed["stage_review"]["rework_available"] is True
    assert completed["stage_review"]["rework_supported"] is True
    assert completed["stage_review"]["rework_decision"]["execution_status"] == "completed"
    assert completed["stage_review"]["rework_decision"]["child_run_id"] == "rework_workflow_review_1"


def test_nicegui_workflow_review_view_model_handles_empty_and_saved_states(tmp_path):
    run_dir = _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    empty = build_console_page_data(backend, "nicegui_run")

    assert empty["workflow_review"]["present"] is False
    assert empty["workflow_review"]["summary_preview"] == []

    _add_workflow_review(run_dir)
    data = build_console_page_data(backend, "nicegui_run")
    review = build_workflow_review_data(data["selected_run"])

    assert review["present"] is True
    assert review["overall_status"] == "accepted_for_preview"
    assert review["readiness_score"] == 88
    assert review["risk_level"] == "medium"
    assert review["summary_preview"] == ["Base was selected and generated as a single part."]


def test_nicegui_assembly_plan_table_data_is_sanitized(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run = build_console_page_data(backend, "nicegui_run")["selected_run"]

    assembly = build_assembly_plan_data(run)
    serialized = json.dumps(assembly, sort_keys=True)

    assert assembly["reference_only_part_ids"] == ["screws"]
    assert assembly["blocked_part_ids"] == ["lid"]
    assert assembly["parts"][0] == {
        "part_id": "base",
        "role": "main housing",
        "status": "candidate_for_single_part_generation",
        "generation_strategy": "future_part_pipeline",
        "supported_candidate": True,
        "reason": "",
        "reference_only": False,
    }
    assert str(tmp_path) not in serialized


def test_nicegui_part_workflow_actions_are_gated_by_upstream_artifacts(tmp_path):
    run_dir = tmp_path / "outputs" / "gated_run"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "assembly_plan.json", {"parts": [{"part_id": "base"}]})
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run = build_console_page_data(backend, "gated_run")["selected_run"]

    workflow = build_part_workflow_data(run)
    availability = {item["key"]: item["available"] for item in workflow["actions"]}

    assert availability == {
        "part_request": True,
        "part_review": False,
        "reviewed_handoff": False,
        "reviewed_part_create": False,
        "part_result_review": False,
    }
    assert workflow["actions"][1]["missing_upstream_artifacts"] == ["part_create_request.json"]


def test_nicegui_workflow_review_surface_summarizes_requirement_planning_and_reviewed_part(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    data = build_console_page_data(backend, "nicegui_run", active_page="workflow")

    surface = data["workflow_review_surface"]
    stages = {stage["key"]: stage for stage in surface["stages"]}
    graph_nodes = {node["stage_id"]: node for node in surface["graph_nodes"]}
    requirement = stages["requirement"]["report_summary"]
    planning = stages["planning"]["report_summary"]
    part_modeling = stages["part_modeling"]["report_summary"]

    assert surface["primary_concept"] == "Workflow / Stage / Review"
    assert surface["layout"] == "workflow_graph_v2_selected_stage_detail"
    assert surface["selected_stage"]["key"] == "part_modeling"
    assert surface["debug_graph_label"] == "Debug / Raw Workflow Graph"
    assert "OpenNode" not in json.dumps(surface)
    assert graph_nodes["requirement"]["label"] == "Requirement"
    assert graph_nodes["part_modeling"]["status"] == "blocked"
    assert graph_nodes["part_modeling"]["has_debug"] is True
    assert graph_nodes["part_modeling"]["hover"] == {
        "title": "Blocked at CAD IR validation",
        "summary": graph_nodes["part_modeling"]["short_summary"],
        "reason": "The draft uses a part type the backend cannot execute yet. This is a capability limit, not a corrupted run.",
        "consequence": "No child input_ir.json, STEP, or STL was created.",
        "recommended_action": "Review the part definition and record the required revision; the current backend cannot continue with this draft.",
    }
    assert "CAD IR validation" in surface["selected_stage"]["human_summary"]
    assert surface["selected_stage"]["debug"]["diagnostic_codes"]
    banner = surface["selected_stage"]["status_banner"]
    assert banner["title"] == "Blocked at CAD IR validation"
    assert "not supported" in banner["summary"]
    assert banner["consequence"] == "No child input_ir.json, STEP, or STL was created."
    badge_values = {badge["label"]: badge["value"] for badge in banner["badges"]}
    assert badge_values["Part"] == "base"
    assert badge_values["Draft"] == "present"
    assert badge_values["CAD output"] == "none"
    assert badge_values["Fallback"] == "none"
    detail_cards = {card["title"]: card for card in surface["selected_stage"]["detail_cards"]}
    assert {"What happened", "Why it stopped", "Recommended next step", "Artifact status", "Review state"} <= set(detail_cards)
    assert detail_cards["Artifact status"]["items"] == [
        {"label": "cad_ir_draft.json", "value": "present", "status": "completed"},
        {"label": "child input_ir.json", "value": "not created", "status": "not_started"},
        {"label": "model.step", "value": "not created", "status": "not_started"},
        {"label": "model.stl", "value": "not created", "status": "not_started"},
    ]
    action_groups = surface["selected_stage"]["action_groups"]
    assert [action["key"] for action in action_groups["primary"]] == ["view_cad_ir_draft", "save_stage_review"]
    assert {action["key"] for action in action_groups["secondary"]} >= {"mark_blocked", "create_workflow_review"}
    disabled_actions = {action["key"]: action for action in action_groups["disabled"]}
    assert disabled_actions["approve_stage"]["disabled_reason"] == "No STEP/STL was generated, so there is no part result to approve."
    assert disabled_actions["reviewed_part_create"]["disabled_reason"] == "This reviewed-part create already ran and blocked at CAD IR validation."
    prompt = surface["workflow_context"]["prompt"]
    assert prompt["display_name"] == "Original request"
    assert prompt["purpose"] == "Original user request"
    assert prompt["status_label"] == "available"
    assert prompt["preview"]["title"] == "Original request"
    stage_artifacts = {item["name"]: item for item in surface["workflow_context"]["stage_artifacts"]}
    assert stage_artifacts["cad_ir_draft.json"]["direction"] == "output"
    assert stage_artifacts["cad_ir_draft.json"]["previewable"] is True
    assert stage_artifacts["model.step"]["status_label"] == "not created"
    assert stage_artifacts["model.step"]["downloadable"] is False
    graph = surface["workflow_graph"]
    assert [node["stage_id"] for node in graph["stage_spine"]] == ["requirement", "clarification", "planning", "assembly_plan"]
    assert graph["selected_part_id"] == "base"
    candidates = {candidate["part_id"]: candidate for candidate in graph["part_candidates"]}
    assert candidates["base"] == {
        "part_id": "base",
        "role": "main housing",
            "brief": "main housing",
            "generation_strategy": "future_part_pipeline",
            "status": "selected",
        "supported_candidate": True,
        "selected": True,
        "current": True,
        "reference_only": False,
        "short_summary": "Selected for the reviewed-part pipeline as main housing.",
    }
    assert candidates["lid"]["status"] == "blocked"
    assert candidates["lid"]["supported_candidate"] is False
    assert graph["reference_lane"][0]["part_id"] == "screws"
    assert graph["reference_lane"][0]["status"] == "reference_only"
    assert [node["stage_id"] for node in graph["selected_part_pipeline"]] == [
        "part_request", "part_review", "reviewed_handoff", "cad_ir_draft", "part_modeling", "part_result_review",
    ]
    assert requirement["requirement_source"] == "requirement_v2.json"
    assert requirement["part_type"] == "enclosure"
    assert requirement["part_family"] == "housing"
    assert requirement["intent_scope"] == "multi_part"
    assert requirement["object_goal"] == "desktop enclosure"
    assert requirement["assumptions"] == ["Use millimeters."]
    assert requirement["missing_information"] == []
    assert requirement["flow_decision"]["action"] == "proceed_with_assumptions"
    assert planning["requirement_source"] == "requirement_v2.json"
    assert planning["route"] == "assembly_split"
    assert planning["candidate_parts"] == ["base"]
    assert planning["reference_components"] == ["screws"]
    assert planning["supported_candidate"] is True
    assert part_modeling["blocked_cad_ir_validation"]["blocked_stage"] == "cad_ir_validation"
    assert part_modeling["child_input_ir_status"] == "absent"
    assert part_modeling["model_step_status"] == "absent"
    assert part_modeling["model_stl_status"] == "absent"


def test_nicegui_workflow_review_surface_selects_one_stage_detail(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(
        backend,
        "nicegui_run",
        active_page="workflow",
        selected_stage_id="planning",
    )

    surface = data["workflow_review_surface"]
    selected = surface["selected_stage"]

    assert surface["selected_stage_id"] == "planning"
    assert selected["key"] == "planning"
    assert selected["stage_name"] == "Planning"
    assert "broken into 1 part candidate" in selected["human_summary"]
    assert selected["why_it_matters"]
    assert selected["current_block"] is None
    assert selected["next_recommended_action"].startswith("Review base")
    assert any("Route: assembly decomposition" in item for item in selected["key_decisions_human"])
    assert selected["progress_summary"]
    assert selected["limitations_summary"]
    assert selected["safety_summary"] == []
    banner = selected["status_banner"]
    assert banner["title"] == "Assembly plan completed"
    assert banner["consequence"].startswith("Full assembly CAD is not supported")
    assert {badge["label"]: badge["value"] for badge in banner["badges"]}["Selected"] == "base"
    detail_cards = {card["title"]: card for card in selected["detail_cards"]}
    assert detail_cards["Candidate parts"]["kind"] == "chips"
    assert detail_cards["Candidate parts"]["items"] == [{"label": "base", "status": "selected"}]
    assert detail_cards["Reference lane"]["items"] == [{"label": "screws", "status": "reference_only"}]
    assert selected["advanced"]["summary_data"] == selected["report_summary"]
    assert selected["debug"]["blocked_reasons"] == selected["blocked_reasons"]


def test_nicegui_workflow_selected_stage_detail_supports_chinese_display_copy(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend, "nicegui_run", active_page="workflow", language="zh")
    selected = data["workflow_review_surface"]["selected_stage"]

    assert selected["display_language"] == "zh"
    assert selected["stage_name"] == "零件建模 / 已评审零件创建"
    assert selected["status_banner"]["title"] == "CAD IR 验证已阻断"
    assert "当前 CAD 后端尚不支持" in selected["status_banner"]["summary"]
    cards = {card["title"]: card for card in selected["detail_cards"]}
    assert cards["为什么停止"]["items"] == ["草稿使用了当前后端尚不能执行的零件类型。", "这是能力限制，不是运行损坏。"]
    assert cards["产物状态"]["items"][1]["value"] == "未创建"
    groups = selected["action_groups"]
    assert [action["label"] for action in groups["primary"]] == ["查看 CAD IR 草稿", "保存阶段评审"]
    disabled = {action["key"]: action for action in groups["disabled"]}
    assert disabled["approve_stage"]["disabled_reason"] == "未生成 STEP/STL，因此没有可批准的零件结果。"
    context = data["workflow_review_surface"]["workflow_context"]
    assert context["title"] == "工作流输入与输出"
    assert context["table_columns"] == ["资料", "用途", "方向", "状态", "操作"]
    assert context["prompt"]["purpose"] == "原始用户需求"


def test_nicegui_workflow_review_surface_actions_and_artifacts_are_allowlisted(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    data = build_console_page_data(backend, "nicegui_run", active_page="workflow")

    surface = build_workflow_review_surface(backend, "nicegui_run", data["selected_run"])
    stages = {stage["key"]: stage for stage in surface["stages"]}
    planning_actions = {action["key"]: action for action in stages["planning"]["available_actions"]}
    requirement_actions = {action["key"]: action for action in stages["requirement"]["available_actions"]}
    artifacts = {artifact["name"] for artifact in surface["artifact_viewer"]["artifacts"]}

    assert planning_actions["create_part_request"]["enabled"] is True
    assert requirement_actions["mark_needs_revision"]["enabled"] is False
    assert "target rework stage" in requirement_actions["mark_needs_revision"]["disabled_reason"]
    assert "cad_ir_draft.json" in artifacts
    assert "logs/runtime.json" not in artifacts
    assert surface["artifact_viewer"]["arbitrary_browsing"] is False
    assert set(surface["artifact_viewer"]["allowlist"]) <= READABLE_ARTIFACTS


def test_nicegui_workflow_review_surface_shows_artifact_edit_availability_and_override(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run_dir = tmp_path / "outputs" / "nicegui_run"
    assembly_override = {
        "artifact_type": "assembly_plan",
        "scope": "multi_part",
        "parts": [{"part_id": "override_base", "supported_candidate": True}],
    }
    backend.write_artifact_by_id("nicegui_run", "assembly_plan.json", assembly_override)

    data = build_console_page_data(backend, "nicegui_run", active_page="workflow")
    artifacts = {item["name"]: item for item in data["workflow_review_surface"]["artifact_viewer"]["artifacts"]}
    stages = {stage["key"]: stage for stage in data["workflow_review_surface"]["stages"]}

    assert (run_dir / "01_design" / "assembly_plan.json").exists()
    assert (run_dir / "edits" / "assembly_plan.edit_001.json").exists()
    assert artifacts["assembly_plan.json"]["editable"] is True
    assert artifacts["assembly_plan.json"]["source"] == "user_override"
    assert artifacts["assembly_plan.json"]["override_present"] is True
    assert artifacts["assembly_plan.json"]["validation_status"] == "valid"
    assert "part_request" in artifacts["assembly_plan.json"]["downstream_stages_affected"]
    assert artifacts["report.json"]["editable"] is False
    assert "report" in artifacts["report.json"]["edit_disabled_reason"].lower()
    assert stages["assembly_plan"]["status"] == "user_modified"


def test_nicegui_artifact_override_editor_rejects_invalid_json_before_backend(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    actions = WorkflowConsoleActions(backend)
    state = {}
    calls = []

    _save_artifact_override_ui(
        actions,
        "nicegui_run",
        "assembly_plan.json",
        "{not-json",
        "bad edit",
        state,
        "result",
        lambda: calls.append("refresh"),
    )

    assert state["result"]["ok"] is False
    assert state["result"]["diagnostic_code"] == "artifact_override.invalid_json"
    assert len(calls) >= 2  # the failed lifecycle also renders pending first
    assert state["action_execution"]["status"] == "failed"
    assert not (tmp_path / "outputs" / "nicegui_run" / "edits").exists()


def test_nicegui_exposes_no_batch_all_part_or_assembly_action():
    action_text = json.dumps(REVIEWED_PART_ACTIONS, sort_keys=True)

    assert {item["method"] for item in REVIEWED_PART_ACTIONS} == {
        "create_part_request",
        "review_part_request",
        "create_reviewed_handoff",
        "create_reviewed_part",
        "review_part_result",
    }
    assert "batch" not in action_text
    assert "all_part" not in action_text
    assert "assembly_generation" not in action_text


def test_nicegui_artifact_page_uses_existing_allowlist_and_sanitization(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    data = build_console_page_data(backend, "nicegui_run")

    artifact_names = {item["name"] for item in data["artifacts_page"]["artifacts"]}
    debug_names = {item["name"] for item in build_artifacts_page_data(data["selected_run"], show_debug=True)["artifacts"]}
    content = read_artifact_page_content(backend, "nicegui_run", "agent_trace.json")

    assert artifact_names <= set(ARTIFACT_PAGE_ARTIFACTS) | set(REVIEW_SURFACE_ARTIFACTS)
    assert "agent_trace.json" not in artifact_names
    assert "agent_trace.json" in debug_names
    assert content["content"] == {"safe": "ok"}
    assert _does_not_contain_text(content, ["SECRET_TOKEN", "raw_provider_response", str(tmp_path)])
    with pytest.raises(ValueError, match="not readable"):
        read_artifact_page_content(backend, "nicegui_run", "not_allowed.json")


def test_nicegui_artifact_page_defaults_to_human_facing_and_filters_debug(tmp_path):
    run_dir = _sample_run(tmp_path)
    _add_workflow_review(run_dir)
    _write_json(run_dir / "input_ir.json", {"kind": "internal"})
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run = build_console_page_data(backend, "nicegui_run")["selected_run"]

    default = build_artifacts_page_data(run)
    debug = build_artifacts_page_data(run, show_debug=True)
    internal = build_artifacts_page_data(run, show_internal=True)

    assert "workflow_review.md" in {item["name"] for item in default["artifacts"]}
    assert "workflow_review.json" in {item["name"] for item in default["artifacts"]}
    assert "requirement.json" not in {item["name"] for item in default["artifacts"]}
    assert "input_ir.json" not in {item["name"] for item in default["artifacts"]}
    assert "requirement.json" in {item["name"] for item in debug["artifacts"]}
    assert "input_ir.json" not in {item["name"] for item in debug["artifacts"]}
    assert "input_ir.json" in {item["name"] for item in internal["artifacts"]}


def test_nicegui_artifact_page_includes_stage_review_debug_access(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(
        backend,
        "action_save_stage_review",
        body={"run_id": "nicegui_run", "stage": "requirement", "review_status": "approved"},
    )

    data = build_console_page_data(backend, "nicegui_run")
    artifact_names = {item["name"] for item in data["artifacts_page"]["artifacts"]}
    content = read_artifact_page_content(backend, "nicegui_run", "stage_review.json")

    assert "stage_review.json" in artifact_names
    assert content["content"]["stage"] == "requirement"
    assert content["content"]["review_status"] == "approved"


def test_nicegui_defaults_are_local_and_optional_import_can_be_skipped():
    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 8780
    if importlib.util.find_spec("nicegui") is None:
        pytest.skip("NiceGUI optional dependency is not installed")
