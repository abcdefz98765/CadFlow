import importlib.util
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
    build_stage_review_data,
    build_workflow_review_data,
    build_artifacts_page_data,
    read_artifact_page_content,
)
from ai_native_cad.workflow_console.routes import dispatch_route


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
            "clarification_questions": ["Should the lid snap on?"],
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


def test_nicegui_console_builds_page_data_from_fake_run_summaries(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend, "nicegui_run")

    assert data["selected_run_id"] == "nicegui_run"
    assert [run["run_id"] for run in data["runs"]] == ["nicegui_run"]
    assert data["requirement_review"]["original_prompt"].startswith("Make a desktop enclosure")
    assert data["assembly_plan"]["candidate_part_ids"] == ["base"]
    assert data["assembly_plan"]["interface_count"] == 1
    assert data["part_workflow"]["actions"][0]["available"] is True


def test_nicegui_console_uses_paginated_run_list_and_lazy_detail(tmp_path, monkeypatch):
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

    data = build_console_page_data(backend, limit=25, offset=0)

    assert len(data["runs"]) == 25
    assert data["pagination"]["limit"] == 25
    assert data["pagination"]["total"] == DEFAULT_RUN_PAGE_SIZE + 3
    assert data["pagination"]["has_next"] is True
    assert loaded_details == [data["selected_run_id"]]


def test_nicegui_console_search_filters_run_names(tmp_path):
    for name in ("alpha_console", "beta_console"):
        run_dir = tmp_path / "outputs" / name
        run_dir.mkdir(parents=True)
        (run_dir / "prompt.txt").write_text(f"Make {name}.\n", encoding="utf-8")
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend, search="alpha")

    assert [run["run_id"] for run in data["runs"]] == ["alpha_console"]
    assert data["run_filters"] == {"search": "alpha"}


def test_nicegui_run_selection_data_excludes_absolute_paths(tmp_path):
    _sample_run(tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    data = build_console_page_data(backend, "nicegui_run")

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

    assert artifact_names <= set(ARTIFACT_PAGE_ARTIFACTS) | {"planning_artifact.json", "input_ir.json"}
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
