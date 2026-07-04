import importlib.util
import json
from pathlib import Path

import pytest

from ai_native_cad.workflow_console import WorkflowConsoleBackend
from ai_native_cad.workflow_console.nicegui_app import (
    ARTIFACT_PAGE_ARTIFACTS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    REVIEWED_PART_ACTIONS,
    build_assembly_plan_data,
    build_console_page_data,
    build_part_workflow_data,
    build_requirement_review_data,
    read_artifact_page_content,
)


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
    content = read_artifact_page_content(backend, "nicegui_run", "agent_trace.json")

    assert artifact_names <= set(ARTIFACT_PAGE_ARTIFACTS) | {"planning_artifact.json", "input_ir.json"}
    assert "agent_trace.json" in artifact_names
    assert content["content"] == {"safe": "ok"}
    assert _does_not_contain_text(content, ["SECRET_TOKEN", "raw_provider_response", str(tmp_path)])
    with pytest.raises(ValueError, match="not readable"):
        read_artifact_page_content(backend, "nicegui_run", "not_allowed.json")


def test_nicegui_defaults_are_local_and_optional_import_can_be_skipped():
    assert DEFAULT_HOST == "127.0.0.1"
    assert DEFAULT_PORT == 8780
    if importlib.util.find_spec("nicegui") is None:
        pytest.skip("NiceGUI optional dependency is not installed")
