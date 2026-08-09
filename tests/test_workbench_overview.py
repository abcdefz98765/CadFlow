from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from copy import deepcopy

import cadquery as cq

from ai_native_cad.domain.records import (
    accept_part_result,
    create_artifact_reference,
    register_artifact_references,
)
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.i18n import copy as i18n_copy
from ai_native_cad.workflow_console.nicegui_app import (
    WORKFLOW_UI_CSS,
    _accept_reviewable_result_async,
    _revise_reviewable_result_async,
    _select_console_work,
    _step_preview_stl,
)
from ai_native_cad.workflow_console.workflow_page_view_model import (
    build_workbench_overview_view_model,
    build_workflow_page_view_model,
)


def _register_reviewable_result(backend: WorkflowConsoleBackend) -> str:
    work_id = "workbench_work"
    part_id = "mounting_bracket"
    run_id = "mounting_bracket_attempt_1"
    result_id = "reviewable_workbench_candidate_001"
    step_id = "reviewable_step_workbench_candidate_001"
    prefix = "episodes/design_part/workbench_request"
    result_ref = create_artifact_reference(
        artifact_id=result_id,
        work_id=work_id,
        run_id=run_id,
        part_job_id=part_id,
        relative_path=f"{prefix}/reviewable_result.json",
        phase="build_evaluate",
        checkpoint="reviewable_result",
        trust_role="reviewable_result",
        validation_status="passed",
    )
    step_ref = create_artifact_reference(
        artifact_id=step_id,
        work_id=work_id,
        run_id=run_id,
        part_job_id=part_id,
        relative_path=f"{prefix}/candidates/candidate_001/exec_001/model.step",
        phase="build_evaluate",
        checkpoint="reviewable_result",
        trust_role="reviewable_result",
        validation_status="passed",
        source_artifact_ids=[result_id],
    )
    manifest = register_artifact_references(
        backend._read_work_manifest(work_id),
        [result_ref, step_ref],
    )
    backend._write_work_manifest(work_id, manifest)
    episode_dir = backend._work_runs_root(work_id) / run_id / prefix
    step_path = episode_dir / "candidates" / "candidate_001" / "exec_001" / "model.step"
    step_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(cq.Workplane("XY").box(42, 24, 8).faces(">Z").hole(5), str(step_path))
    step_bytes = step_path.read_bytes()
    record = {
        "reviewable_result_id": result_id,
        "work_id": work_id,
        "run_id": run_id,
        "part_job_id": part_id,
        "episode_id": "episode_workbench_001",
        "candidate_id": "candidate_001",
        "observation_id": "observation_001",
        "execution_id": "exec_001",
        "capability_mode": "provider_selected_design_with_attested_model_program",
        "api_id": "cadquery_v1",
        "source_hash": "1" * 64,
        "parameters_hash": "2" * 64,
        "attestation_digest": "3" * 64,
        "profile_digest": "4" * 64,
        "toolchain_digest": "5" * 64,
        "limits": {"wall_seconds": 20},
        "geometry": {
            "valid": True,
            "solid_count": 1,
            "face_count": 7,
            "volume": 7974.3,
            "bounding_box": {"x": 42.0, "y": 24.0, "z": 8.0},
        },
        "validation": {
            "execution_success": True,
            "step_reimport_valid": True,
            "solid_count": 1,
        },
        "step": {
            "artifact_id": step_id,
            "relative_path": "candidates/candidate_001/exec_001/model.step",
            "sha256": hashlib.sha256(step_bytes).hexdigest(),
            "size": len(step_bytes),
        },
        "assumptions": ["Dimensions are in millimetres."],
        "limitations": ["Strength and assembly fit were not validated."],
        "trust_role": "reviewable_result",
        "reviewable": True,
        "accepted": False,
        "deliverable": False,
    }
    episode_dir.mkdir(parents=True, exist_ok=True)
    (episode_dir / "reviewable_result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    backend.invalidate_work_index()
    return result_id


def _backend(tmp_path) -> tuple[WorkflowConsoleBackend, str]:
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work(
        "Servo mounting bracket",
        "Design a compact bracket for a small servo interface.",
        work_id="workbench_work",
    )
    backend.create_work_part_attempt(
        "workbench_work",
        "mounting_bracket",
        role="interface bracket",
        run_id="mounting_bracket_attempt_1",
    )
    return backend, _register_reviewable_result(backend)


def _primary_surface(view_model: dict) -> dict:
    value = deepcopy(view_model)
    value.pop("advanced", None)
    return value


def test_reviewable_overview_uses_canonical_phase_and_hides_evidence_by_default(tmp_path):
    backend, result_id = _backend(tmp_path)

    overview = build_workbench_overview_view_model(
        backend,
        "workbench_work",
        language="zh",
    )

    assert overview["phase"]["key"] == "accept_deliver"
    assert overview["phase"]["orientation_only"] is True
    assert [item["key"] for item in overview["phase"]["items"]] == [
        "intent",
        "design",
        "build_evaluate",
        "accept_deliver",
    ]
    assert overview["capability"] == {
        "key": "agentic_experimental",
        "label": "Agentic 实验模式",
        "experimental": True,
    }
    assert overview["agent_activity"]["label"] == "结果已准备好审查"
    assert overview["preview"]["kind"] == "registered_step"
    assert "%2Fpreview.stl" in overview["preview"]["viewer_url"]
    assert overview["current_result"]["reviewable_result_id"] == result_id
    assert overview["current_result"]["accepted"] is False
    assert "STEP 重新导入验证通过" in overview["current_result"]["verified"]
    assert overview["history"]["run_snapshot_read_only"] is True
    assert overview["workflow"]["reachable"] is True
    primary_json = json.dumps(_primary_surface(overview), ensure_ascii=False)
    assert "source_hash" not in primary_json
    assert "attestation_digest" not in primary_json
    assert "profile_digest" not in primary_json
    assert overview["advanced"]["reviewable_evidence"]["source_hash"] == "1" * 64
    assert overview["advanced"]["reviewable_evidence"]["attestation_digest"] == "3" * 64


def test_accept_and_revise_use_existing_lifecycle_and_preserve_acceptance(tmp_path):
    backend, result_id = _backend(tmp_path)
    review_page = build_workflow_page_view_model(
        backend,
        "workbench_work",
        selected_stage_id=f"result:{result_id}",
        language="en",
    )
    assert review_page["recommended_next_action"]["key"] == "accept_reviewable_result"
    assert review_page["selected_node"]["user_state"] == "review"
    assert review_page["recommended_next_action"]["reviewable_result_id"] == result_id
    assert [item["key"] for item in review_page["available_actions"]["secondary_actions"]] == [
        "revise_reviewable_result"
    ]
    assert review_page["current_attention"][0]["node_id"] == f"result:{result_id}"
    state = {}
    refresh_count = 0

    def refresh():
        nonlocal refresh_count
        refresh_count += 1

    accept_action = {
        "key": "accept_reviewable_result",
        "label": "Accept result",
        "target_work_id": "workbench_work",
        "part_job_id": "mounting_bracket",
        "reviewable_result_id": result_id,
    }
    accepted = asyncio.run(
        _accept_reviewable_result_async(
            backend,
            accept_action,
            state,
            refresh,
            "zh",
        )
    )
    assert accepted["orchestration"]["command"] == "accept_reviewable_part_result"
    pointer = backend._read_work_manifest("workbench_work")["accepted_part_results"]["mounting_bracket"]
    assert pointer["result_id"] == result_id
    assert state["action_execution"]["status"] == "succeeded"
    assert state["action_execution"]["postcondition_verified"] is True
    accepted_page = build_workflow_page_view_model(
        backend,
        "workbench_work",
        selected_stage_id=f"accepted:mounting_bracket:{result_id}",
        language="en",
    )
    assert accepted_page["selected_node"]["status"] == "accepted"
    assert accepted_page["recommended_next_action"] is None
    assert accepted_page["available_actions"]["secondary_actions"][0]["key"] == "revise_reviewable_result"

    revise_action = {
        "key": "revise_reviewable_result",
        "label": "Revise",
        "target_work_id": "workbench_work",
        "part_job_id": "mounting_bracket",
        "reviewable_result_id": result_id,
    }
    revised = asyncio.run(
        _revise_reviewable_result_async(
            backend,
            revise_action,
            "Increase the length by 10 mm and change the bore to 5 mm.",
            state,
            refresh,
            "zh",
        )
    )
    final = backend._read_work_manifest("workbench_work")
    assert revised["orchestration"]["command"] == "revise_reviewable_part_result"
    assert final["accepted_part_results"]["mounting_bracket"] == pointer
    assert len(final["part_jobs"][0]["attempts"]) == 2
    revision_attempt = final["part_jobs"][0]["attempts"][1]
    assert revision_attempt["parent_run_id"] == "mounting_bracket_attempt_1"
    assert revision_attempt["source_result_id"] == result_id
    revised_page = build_workflow_page_view_model(
        backend,
        "workbench_work",
        language="en",
    )
    assert any(node["status"] == "accepted" and node.get("result_id") == result_id for node in revised_page["nodes"])
    assert any(edge["type"] == "revised" for edge in revised_page["edges"])
    assert revised_page["current_attention"][0]["node_id"].startswith("attempt:mounting_bracket:")
    assert revised_page["current_attention"][0]["primary_action"]["key"] == "continue_agent"
    overview = build_workbench_overview_view_model(
        backend,
        "workbench_work",
        language="zh",
    )
    assert overview["phase"]["key"] == "design"
    assert overview["user_input"]["source_type"] == "revision"
    assert overview["user_input"]["revision_request"] == "Increase the length by 10 mm and change the bore to 5 mm."
    assert overview["current_result"]["accepted"] is True
    assert overview["current_result"]["revision_in_progress"] is True
    assert overview["part_jobs"][0]["has_accepted_result"] is True
    assert overview["part_jobs"][0]["attempt_count"] == 2
    workflow = build_workflow_page_view_model(backend, "workbench_work", language="zh")
    graph_nodes = {item["id"]: item for item in workflow["nodes"]}
    revision_node_id = f"attempt:mounting_bracket:{revision_attempt['run_id']}"
    accepted_node_id = f"accepted:mounting_bracket:{result_id}"
    assert graph_nodes[revision_node_id]["detail"]["source_result_id"] == result_id
    assert graph_nodes[accepted_node_id]["status"] == "accepted"
    assert workflow["selected_node"]["id"] == revision_node_id
    assert any(
        edge["target"] == revision_node_id and edge["type"] == "revised"
        for edge in workflow["edges"]
    )
    assert refresh_count >= 4


def test_registered_step_reuses_existing_stl_viewer_with_ephemeral_mesh(tmp_path):
    backend, result_id = _backend(tmp_path)
    manifest = backend._read_work_manifest("workbench_work")
    step_id = next(
        item["artifact_id"]
        for item in manifest["artifact_references"]
        if result_id in item.get("source_artifact_ids", [])
    )
    reference, step_path = backend.resolve_work_artifact_reference(
        "workbench_work",
        step_id,
    )

    preview_path = _step_preview_stl(step_path)
    try:
        assert reference["trust_role"] == "reviewable_result"
        assert preview_path.suffix == ".stl"
        assert preview_path.stat().st_size > 0
    finally:
        preview_path.unlink(missing_ok=True)


def test_deterministic_work_is_honestly_labeled_and_reuses_stl_preview(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work(
        "Deterministic spacer",
        "Create a 20 mm spacer with a 5 mm center bore.",
        work_id="deterministic_work",
    )
    backend.create_work_part_attempt(
        "deterministic_work",
        "spacer",
        role="spacer",
        run_id="spacer_attempt_1",
    )
    run_dir = backend._work_runs_root("deterministic_work") / "spacer_attempt_1"
    model = cq.Workplane("XY").circle(10).circle(2.5).extrude(8)
    cq.exporters.export(model, str(run_dir / "model.step"))
    cq.exporters.export(model, str(run_dir / "model.stl"))
    refs = [
        create_artifact_reference(
            artifact_id=f"deterministic_{suffix}",
            work_id="deterministic_work",
            run_id="spacer_attempt_1",
            part_job_id="spacer",
            relative_path=f"model.{suffix}",
            phase="build_evaluate",
            checkpoint="reviewable_result",
            trust_role="reviewable_result",
            validation_status="passed",
        )
        for suffix in ("step", "stl")
    ]
    manifest = register_artifact_references(
        backend._read_work_manifest("deterministic_work"),
        refs,
    )
    manifest = accept_part_result(
        manifest,
        part_job_id="spacer",
        result_id="deterministic_spacer_result",
        attempt_run_id="spacer_attempt_1",
        result_run_id="spacer_attempt_1",
        review_id="deterministic_review",
        artifact_ids=[item["artifact_id"] for item in refs],
    )
    backend._write_work_manifest("deterministic_work", manifest)
    backend.invalidate_work_index()

    overview = build_workbench_overview_view_model(
        backend,
        "deterministic_work",
        language="zh",
    )

    assert overview["capability"]["key"] == "deterministic_compatibility"
    assert overview["capability"]["label"] == "确定性兼容模式"
    assert overview["preview"]["kind"] == "legacy_stl"
    assert "model.stl" in overview["preview"]["viewer_url"]
    assert overview["part_jobs"][0]["state"] == "accepted"


def test_workbench_keeps_existing_shell_lifecycle_viewer_and_secondary_surfaces():
    source = (
        __import__(
            "ai_native_cad.workflow_console.nicegui_app",
            fromlist=["placeholder"],
        )
        .__loader__
        .get_source("ai_native_cad.workflow_console.nicegui_app")
    )
    assert "create_nicegui_app" in source
    assert "_execute_action_lifecycle" in source
    assert "_show_artifact_contract_dialog" in source
    assert "html_escape(str(preview[\"viewer_url\"]), quote=True)" in source
    assert "sanitize=False" in source
    assert "_render_workflow_page_v2" in source
    assert "_render_runs" in source
    assert "_render_parts_matrix" in source
    assert "WORK_USER_PAGES" in source
    assert "workbench-shell w-full gap-0" in source
    assert ".workbench-shell{display:flex;flex-wrap:nowrap" in WORKFLOW_UI_CSS
    assert ".sidebar{flex:0 0 auto;width:100%" in WORKFLOW_UI_CSS
    assert "workbench-primary-grid" in WORKFLOW_UI_CSS
    assert "@media(max-width:1100px)" in WORKFLOW_UI_CSS
    assert "@media(max-width:760px)" in WORKFLOW_UI_CSS


def test_overview_has_one_dominant_action_owner_and_compact_empty_states():
    from ai_native_cad.workflow_console import nicegui_app

    overview_source = inspect.getsource(nicegui_app._render_work_overview)
    task_source = inspect.getsource(nicegui_app._render_overview_current_task)
    output_source = inspect.getsource(nicegui_app._render_agent_output)
    parts_source = inspect.getsource(nicegui_app._render_workbench_parts_summary)

    assert "_show_continue_agent_confirmation" not in overview_source
    assert task_source.count("_show_continue_agent_confirmation") == 1
    assert "if not has_preview" in overview_source
    assert "if has_preview" in overview_source
    assert "workbench-agent-output-compact" in output_source
    assert "recommended_action" not in parts_source
    assert "View current step in Workflow" in parts_source


def test_chinese_and_english_product_copy_exist():
    assert i18n_copy("en", "result_ready_review") == "Result ready for review"
    assert i18n_copy("zh", "result_ready_review") == "结果已准备好审查"
    assert i18n_copy("en", "deterministic_compatibility") == "Deterministic compatibility"
    assert i18n_copy("zh", "agentic_experimental") == "Agentic 实验模式"


def test_switching_work_clears_action_feedback_owned_by_the_previous_work():
    refresh_count = 0

    def refresh() -> None:
        nonlocal refresh_count
        refresh_count += 1

    state = {
        "selected_work_id": "work_a",
        "action_execution": {
            "status": "succeeded",
            "target_work_id": "work_a",
            "message": "Revision created.",
        },
    }

    _select_console_work(state, "work_b", refresh)

    assert state["selected_work_id"] == "work_b"
    assert state["action_execution"] is None
    assert refresh_count == 1
