import json
from uuid import uuid4
from pathlib import Path

import pytest

from ai_native_cad.agents import DeterministicAgentAdapter
from ai_native_cad.workflow_console.stage_runner import READABLE_ARTIFACTS
from ai_native_cad.workflow_console import (
    EDITABLE_ARTIFACTS,
    GATE_DECISION_ACTIONS,
    ROUTE_SPECS,
    ROUTE_SPECS_BY_NAME,
    STATUS_CREATED,
    WORKFLOW_STATUS_VALUES,
    StageRunner,
    WorkflowConsoleBackend,
    dispatch_route,
    error_response,
    status_code_for_exception,
    success_response,
)
from ai_native_cad.workflow_console.server import resolve_downloadable


def _does_not_contain_keys(value, keys):
    if isinstance(value, dict):
        return all(key not in keys and _does_not_contain_keys(item, keys) for key, item in value.items())
    if isinstance(value, list):
        return all(_does_not_contain_keys(item, keys) for item in value)
    return True


def test_stage_runner_runs_requirement_and_planning_to_artifacts(tmp_path):
    runner = StageRunner(project_root=tmp_path)
    output_dir = tmp_path / "outputs" / "console_requirement_planning"

    requirement_result = runner.run_requirement(
        "Generate an 80x40x5 mm mounting plate with four M4 holes in the corners.",
        {"output_dir": output_dir},
    )
    planning_result = runner.run_planning(requirement_result["requirement"], {"output_dir": output_dir})
    artifacts = runner.read_artifacts(output_dir)
    runtime = artifacts["logs/runtime.json"]["workflow_console"]

    assert requirement_result["stage"] == "requirement"
    assert requirement_result["stage_status"] == "completed"
    assert planning_result["stage"] == "planning"
    assert planning_result["stage_status"] == "completed"
    assert (output_dir / "prompt.txt").exists()
    assert artifacts["requirement.json"]["part_type"] == "mounting_plate"
    assert artifacts["planning_artifact.json"]["artifact_type"] == "planning"
    assert [stage["stage"] for stage in runtime["stages"]] == ["requirement", "planning"]
    assert runtime["latest_stage"]["stage"] == "planning"


def test_workflow_console_route_specs_use_safe_by_id_backend_operations():
    expected_operations = {
        "create_run_by_id",
        "list_runs",
        "read_run_metadata_by_id",
        "run_stage_by_id",
        "list_artifacts_by_id",
        "read_artifact_by_id",
        "write_artifact_by_id",
        "list_downloadables_by_id",
        "record_gate_decision_by_id",
    }

    assert {spec.backend_operation for spec in ROUTE_SPECS} == expected_operations
    assert all(
        spec.backend_operation.endswith("_by_id") or spec.backend_operation == "list_runs"
        for spec in ROUTE_SPECS
    )
    assert "run_dir" not in {spec.backend_operation for spec in ROUTE_SPECS}


def test_workflow_console_route_paths_do_not_accept_filesystem_paths():
    forbidden_placeholders = {"{path}", "{file_path}", "{run_dir}", "{local_path}", "{filesystem_path}"}

    for spec in ROUTE_SPECS:
        assert not any(placeholder in spec.path for placeholder in forbidden_placeholders)
        assert "..." not in spec.path
        assert "*" not in spec.path
        assert "\\" not in spec.path


def test_workflow_console_error_mapping_uses_http_like_status_codes():
    assert status_code_for_exception(ValueError("bad stage")) == 400
    assert status_code_for_exception(FileNotFoundError("missing run")) == 404
    assert status_code_for_exception(FileExistsError("duplicate run")) == 409
    assert status_code_for_exception(RuntimeError("unexpected")) == 500


def test_workflow_console_response_envelopes_are_stable():
    assert success_response({"run_id": "console_run"}, status_code=201) == {
        "ok": True,
        "status_code": 201,
        "data": {"run_id": "console_run"},
        "error": None,
    }

    assert error_response(ValueError("unsupported workflow console stage: shell")) == {
        "ok": False,
        "status_code": 400,
        "data": None,
        "error": {
            "type": "bad_request",
            "message": "unsupported workflow console stage: shell",
        },
    }


def test_workflow_console_route_contract_includes_edit_and_gate_routes():
    assert ROUTE_SPECS_BY_NAME["write_artifact"].method == "PUT"
    assert ROUTE_SPECS_BY_NAME["write_artifact"].backend_operation == "write_artifact_by_id"
    assert ROUTE_SPECS_BY_NAME["record_gate_decision"].method == "POST"
    assert ROUTE_SPECS_BY_NAME["record_gate_decision"].backend_operation == "record_gate_decision_by_id"


def test_workflow_console_internal_error_shape_does_not_leak_local_paths():
    response = error_response(RuntimeError(r"failed under D:\MyCode\llm2cad\outputs\secret_run"))

    assert response["status_code"] == 500
    assert response["error"]["type"] == "internal_error"
    assert response["error"]["message"] == "internal workflow console error"
    assert "D:\\MyCode" not in response["error"]["message"]
    assert "secret_run" not in response["error"]["message"]


def test_workflow_console_dispatch_creates_and_reads_run_by_id(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    created = dispatch_route(
        backend,
        "create_run",
        path_params={"run_id": "dispatch_run"},
        body={"prompt": "Make a spacer."},
        query={"root": "runs"},
    )
    read = dispatch_route(
        backend,
        "read_run_metadata",
        path_params={"run_id": "dispatch_run"},
        query={"root": "runs"},
    )

    assert created["ok"] is True
    assert created["status_code"] == 201
    assert created["data"]["run"]["run_id"] == "dispatch_run"
    assert _does_not_contain_keys(created["data"], {"path", "run_dir", "root", "output_dir"})
    assert read["ok"] is True
    assert read["data"]["run_id"] == "dispatch_run"
    assert _does_not_contain_keys(read["data"], {"path", "run_dir", "root", "output_dir"})


def test_workflow_console_dispatch_writes_artifact_and_records_gate_decision(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "dispatch_edit"}, body={"prompt": "Make a spacer."})
    requirement = {
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
    }

    written = dispatch_route(
        backend,
        "write_artifact",
        path_params={"run_id": "dispatch_edit", "artifact": "requirement.json"},
        body={"content": requirement},
    )
    decision = dispatch_route(
        backend,
        "record_gate_decision",
        path_params={"run_id": "dispatch_edit"},
        body={"stage": "requirement", "action": "approve", "reason": "Looks complete."},
    )
    runtime = backend.read_artifact_by_id("dispatch_edit", "logs/runtime.json")["content"]["workflow_console"]

    assert written["ok"] is True
    assert written["data"]["artifact"]["content"]["part_type"] == "spacer"
    assert _does_not_contain_keys(written["data"], {"path", "run_dir", "root", "output_dir"})
    assert decision["ok"] is True
    assert decision["status_code"] == 201
    assert _does_not_contain_keys(decision["data"], {"path", "run_dir", "root", "output_dir"})
    assert runtime["artifact_edit_count"] == 1
    assert runtime["gate_decision_count"] == 1


def test_workflow_console_dispatch_exposes_path_free_stage_history(tmp_path):
    runner = StageRunner(project_root=tmp_path)
    backend = WorkflowConsoleBackend(project_root=tmp_path, stage_runner=runner)
    dispatch_route(
        backend,
        "create_run",
        path_params={"run_id": "stage_history"},
        body={"prompt": "Make a spacer."},
    )
    dispatch_route(backend, "run_stage", path_params={"run_id": "stage_history", "stage": "requirement"})

    response = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "stage_history"})

    assert response["ok"] is True
    assert response["data"]["stage_history"][0]["stage"] == "created"
    assert response["data"]["stage_history"][1]["stage"] == "requirement"
    assert _does_not_contain_keys(response["data"]["stage_history"], {"path", "run_dir", "root", "output_dir"})


def test_workflow_console_dispatch_exposes_path_free_gate_history_summary(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "gate_history"}, body={"prompt": "Make a spacer."})
    dispatch_route(
        backend,
        "record_gate_decision",
        path_params={"run_id": "gate_history"},
        body={
            "stage": "planning",
            "action": "return",
            "reason": "Need a clearer wall thickness.",
            "payload": {"path": r"D:\MyCode\llm2cad\outputs\gate_history"},
        },
    )

    response = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "gate_history"})

    assert response["ok"] is True
    assert response["data"]["gate_history"] == [
        {
            "stage": "planning",
            "action": "return",
            "reason": "Need a clearer wall thickness.",
            "timestamp": response["data"]["gate_history"][0]["timestamp"],
        }
    ]
    assert _does_not_contain_keys(response["data"]["gate_history"], {"path", "run_dir", "root", "output_dir", "payload"})


def test_workflow_console_dispatch_sanitizes_gate_payload_but_preserves_runtime_artifact(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "gate_payload"}, body={"prompt": "Make a spacer."})

    recorded = dispatch_route(
        backend,
        "record_gate_decision",
        path_params={"run_id": "gate_payload"},
        body={
            "stage": "requirement",
            "action": "proceed_with_assumptions",
            "reason": "Proceed with defaults.",
            "payload": {
                "field": "dimensions.length",
                "assumption": "Use selected template defaults.",
                "api_key": "secret-token",
                "path": r"D:\MyCode\llm2cad\outputs\gate_payload",
            },
        },
    )
    runtime = dispatch_route(
        backend,
        "read_artifact",
        path_params={"run_id": "gate_payload", "artifact": "logs/runtime.json"},
    )

    assert recorded["ok"] is True
    assert "payload" not in recorded["data"]["decision"]
    assert recorded["data"]["run"]["status"]["gate_decision"]["payload_summary"]["items"] == [
        {"key": "assumption", "value": "Use selected template defaults."},
        {"key": "field", "value": "dimensions.length"},
    ]
    assert "secret-token" not in json.dumps(recorded["data"])
    assert "D:\\MyCode" not in json.dumps(recorded["data"])
    assert runtime["data"]["content"]["workflow_console"]["latest_gate_decision"]["payload"]["api_key"] == "secret-token"


def test_workflow_console_metadata_includes_compact_report_trace_summary(tmp_path):
    run_dir = tmp_path / "outputs" / "summary_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")
    (run_dir / "report.json").write_text(
        json.dumps({
            "status": "failed",
            "success": False,
            "warnings": [{"code": "thin_wall", "message": "Wall may be thin", "file": str(run_dir / "model.step")}],
            "errors": [{"code": "missing_feature", "message": "Hole missing", "feature": "holes"}],
            "flow_decision": {"action": "return", "to_stage": "planning"},
            "rework_decision": {"action": "return", "to_stage": "planning"},
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "agent_trace.json").write_text(
        json.dumps({"total_attempts": 2, "final_selected_candidate": "B"}) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    metadata = backend.read_run_metadata_by_id("summary_run")

    assert metadata["report_summary"] == {
        "report_present": True,
        "trace_present": True,
        "status": "failed",
        "success": False,
        "warning_count": 1,
        "error_count": 1,
        "warnings": [{"code": "thin_wall", "message": "Wall may be thin"}],
        "errors": [{"code": "missing_feature", "message": "Hole missing", "feature": "holes"}],
        "flow_action": "return",
        "flow_to_stage": "planning",
        "rework_action": "return",
        "rework_to_stage": "planning",
        "attempts": 2,
        "final_selected_candidate": "B",
        "requirement_summary": {
            "present": False,
            "check_level": None,
            "complete_for_generation": None,
            "needs_user_input": None,
            "assumptions": {"count": 0, "items": []},
            "missing_information": {"count": 0, "fields": [], "items": []},
            "follow_up_requests": {"count": 0, "fields": [], "items": []},
            "flow_decision": {
                "action": None,
                "from_stage": None,
                "to_stage": None,
                "owner_stage": None,
                "reason_count": 0,
                "assumption_count": 0,
            },
        },
        "planning_summary": {
            "present": False,
            "route": None,
            "flow_gate": {
                "status": None,
                "blocking_count": 0,
                "blocking_reasons": [],
                "rework_decision": {
                    "action": None,
                    "from_stage": None,
                    "to_stage": None,
                    "owner_stage": None,
                    "reason_count": 0,
                    "assumption_count": 0,
                },
            },
            "risk_notes": {"count": 0, "fields": [], "items": []},
        },
        "requirement_flow_decision": {
            "action": None,
            "from_stage": None,
            "to_stage": None,
            "owner_stage": None,
            "reason_count": 0,
            "assumption_count": 0,
        },
        "planning_flow_gate": {
            "status": None,
            "blocking_count": 0,
            "blocking_reasons": [],
            "rework_decision": {
                "action": None,
                "from_stage": None,
                "to_stage": None,
                "owner_stage": None,
                "reason_count": 0,
                "assumption_count": 0,
            },
        },
    }
    assert _does_not_contain_keys(metadata["report_summary"], {"path", "run_dir", "root", "output_dir", "file"})


def test_workflow_console_metadata_summarizes_assumptions_and_risks_without_paths(tmp_path):
    run_dir = tmp_path / "outputs" / "assumption_summary"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a mounting plate.\n", encoding="utf-8")
    requirement = {
        "part_type": "mounting_plate",
        "unit": "mm",
        "check_level": "L0",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {},
        "assumptions": [
            "Primary dimensions were taken from the selected part template.",
            r"Do not expose D:\MyCode\llm2cad\secret.txt",
            "password copied from prompt",
        ],
        "missing_information": [
            {
                "field": "dimensions.length",
                "category": "primary_dimensions",
                "severity": "important",
                "ask_user": False,
                "default_used": True,
                "question": r"Use D:\MyCode\llm2cad\outputs?",
            },
            {
                "field": "manufacturing_process",
                "category": "manufacturing_context",
                "severity": "important",
                "ask_user": False,
                "default_used": False,
            },
        ],
        "follow_up_requests": [
            {
                "field": "hole_pattern",
                "category": "engineering_constraints",
                "code": "missing_hole_pattern",
                "question": "Confirm the hole pattern?",
            }
        ],
        "requirement_status": {
            "complete_for_generation": True,
            "needs_user_input": False,
            "flow_decision": {
                "action": "proceed_with_assumptions",
                "from_stage": "requirement",
                "to_stage": "planning",
                "owner_stage": "planning",
                "assumptions": ["Primary dimensions were taken from the selected part template."],
                "reasons": [{"field": "dimensions.length"}],
            },
        },
    }
    planning = {
        "artifact_type": "planning",
        "route": {"selected": "single_part"},
        "selected_parts": [],
        "risk_notes": [
            {
                "field": "manufacturing_process",
                "category": "manufacturing",
                "message": r"Local notes in D:\MyCode\llm2cad",
                "blocks_cad_ir": False,
            }
        ],
        "flow_gate_status": {
            "status": "ready_for_cad_ir",
            "blocking_reasons": [],
            "rework_decision": {
                "action": "proceed",
                "from_stage": "planning",
                "to_stage": "cad_ir",
                "owner_stage": "cad_ir",
                "reasons": [],
            },
        },
    }
    (run_dir / "requirement.json").write_text(json.dumps(requirement) + "\n", encoding="utf-8")
    (run_dir / "planning_artifact.json").write_text(json.dumps(planning) + "\n", encoding="utf-8")

    metadata = WorkflowConsoleBackend(project_root=tmp_path).read_run_metadata_by_id("assumption_summary")
    summary = metadata["report_summary"]

    assert summary["requirement_flow_decision"]["action"] == "proceed_with_assumptions"
    assert summary["requirement_flow_decision"]["assumption_count"] == 1
    assert summary["requirement_summary"]["assumptions"] == {
        "count": 3,
        "items": ["Primary dimensions were taken from the selected part template."],
    }
    assert summary["requirement_summary"]["missing_information"]["count"] == 2
    assert summary["requirement_summary"]["missing_information"]["fields"] == [
        "dimensions.length",
        "manufacturing_process",
    ]
    assert summary["requirement_summary"]["follow_up_requests"]["items"] == [
        {"field": "hole_pattern", "category": "engineering_constraints", "code": "missing_hole_pattern"}
    ]
    assert summary["planning_flow_gate"]["status"] == "ready_for_cad_ir"
    assert summary["planning_summary"]["risk_notes"]["items"] == [
        {"field": "manufacturing_process", "category": "manufacturing", "blocks_cad_ir": False}
    ]
    assert metadata["status"]["requirement_summary"]["flow_decision"]["action"] == "proceed_with_assumptions"
    assert _does_not_contain_keys(summary, {"path", "run_dir", "root", "output_dir", "question", "message"})
    assert "D:\\MyCode" not in json.dumps(summary)
    assert "password" not in json.dumps(summary).lower()


def test_workflow_console_dispatch_validation_errors_return_envelopes(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    missing_prompt = dispatch_route(backend, "create_run", path_params={"run_id": "bad_run"}, body={})
    unknown_route = dispatch_route(backend, "delete_run", path_params={"run_id": "bad_run"})
    bad_body = dispatch_route(backend, "create_run", path_params={"run_id": "bad_run"}, body=["not", "a", "dict"])

    assert missing_prompt["status_code"] == 400
    assert missing_prompt["error"]["type"] == "bad_request"
    assert "prompt" in missing_prompt["error"]["message"]
    assert unknown_route["status_code"] == 400
    assert unknown_route["error"]["message"] == "unknown workflow console route: delete_run"
    assert bad_body["status_code"] == 400
    assert "body must be a dictionary" in bad_body["error"]["message"]


def test_workflow_console_dispatch_does_not_expose_unlisted_backend_methods(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    response = dispatch_route(
        backend,
        "read_artifact",
        path_params={"run_id": "../outside", "artifact": "prompt.txt"},
    )

    assert response["status_code"] == 400
    assert response["error"]["type"] == "bad_request"
    assert "run id" in response["error"]["message"]


def test_workflow_console_dispatch_preserves_artifact_content_path_keys(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "content_path"}, body={"prompt": "Make a spacer."})
    requirement = {
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {"path": "not a filesystem path"},
    }
    backend.write_artifact_by_id("content_path", "requirement.json", requirement)

    response = dispatch_route(
        backend,
        "read_artifact",
        path_params={"run_id": "content_path", "artifact": "requirement.json"},
    )

    assert "path" not in response["data"]
    assert response["data"]["content"]["features"]["path"] == "not a filesystem path"


def test_backend_reads_stage_status_from_runtime_without_report(tmp_path):
    runner = StageRunner(project_root=tmp_path)
    output_dir = tmp_path / "outputs" / "console_requirement_only"

    runner.run_requirement("Make a mounting plate.", {"output_dir": output_dir})

    backend = WorkflowConsoleBackend(project_root=tmp_path, stage_runner=runner)
    metadata = backend.read_run_metadata(output_dir)
    runtime = backend.read_artifact(output_dir, "logs/runtime.json")

    assert metadata["status"]["status"] == "completed"
    assert metadata["status"]["stage"] == "requirement"
    assert metadata["stage_history"][0]["stage"] == "requirement"
    assert metadata["stage_history"][0]["status"] == "completed"
    assert metadata["stage_history"][0]["flow_decision"]["action"] == "proceed_with_assumptions"
    assert "timestamp" in metadata["stage_history"][0]
    assert "output_dir" not in metadata["stage_history"][0]
    assert runtime["content"]["workflow_console"]["latest_stage"]["stage"] == "requirement"


def test_backend_creates_run_without_executing_stages(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    created = backend.create_run("Make a mounting plate.", run_name="created_run")
    run_dir = Path(created["run"]["run_dir"])
    listed = backend.list_runs()

    assert created["result"]["status"] == "created"
    assert created["run"]["status"]["status"] == "created"
    assert created["run"]["status"]["stage"] == "created"
    assert [run["run_id"] for run in listed] == ["created_run"]
    assert (run_dir / "prompt.txt").exists()
    assert not (run_dir / "requirement.json").exists()

    requirement = backend.run_stage(run_dir, "requirement")
    assert requirement["result"]["stage"] == "requirement"
    assert (run_dir / "requirement.json").exists()


def test_backend_creates_run_by_safe_id_under_configured_root(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    created = backend.create_run_by_id("created_by_id", "Make a spacer.", root="runs")
    metadata = backend.read_run_metadata_by_id("created_by_id", root="runs")

    assert created["result"]["status"] == STATUS_CREATED
    assert created["run"]["run_id"] == "created_by_id"
    assert created["run"]["status"]["status"] in WORKFLOW_STATUS_VALUES
    assert Path(created["run"]["run_dir"]) == (tmp_path / "runs" / "created_by_id").resolve()
    assert metadata["status"]["stage"] == STATUS_CREATED
    assert (tmp_path / "runs" / "created_by_id" / "prompt.txt").read_text(encoding="utf-8") == "Make a spacer.\n"


def test_backend_create_run_by_id_rejects_unsafe_id(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="run id"):
        backend.create_run_by_id("../outside", "Make a spacer.")


def test_backend_create_run_by_id_rejects_unconfigured_root(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="run root is not configured"):
        backend.create_run_by_id("created_by_id", "Make a spacer.", root="tmp")


def test_backend_create_run_by_id_rejects_existing_run(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("created_by_id", "Make a spacer.")

    with pytest.raises(FileExistsError, match="workflow console run already exists"):
        backend.create_run_by_id("created_by_id", "Make another spacer.")


def test_backend_records_gate_decision_by_id_in_runtime(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("decision_run", "Make a spacer.")

    recorded = backend.record_gate_decision_by_id(
        "decision_run",
        stage="requirement",
        action="approve",
        reason="Requirement is acceptable.",
    )
    runtime = backend.read_artifact_by_id("decision_run", "logs/runtime.json")["content"]["workflow_console"]

    assert recorded["decision"]["action"] == "approve"
    assert recorded["decision"]["stage"] == "requirement"
    assert recorded["run"]["status"]["gate_decision"]["reason"] == "Requirement is acceptable."
    assert runtime["latest_gate_decision"] == recorded["decision"]
    assert runtime["gate_decision_count"] == 1
    assert runtime["gate_decisions"] == [recorded["decision"]]
    assert "approve" in GATE_DECISION_ACTIONS


def test_stage_runner_treats_proceed_with_assumptions_as_completed(tmp_path):
    runner = StageRunner(project_root=tmp_path)
    output_dir = tmp_path / "outputs" / "assumption_run"

    result = runner.run_requirement("Make a mounting plate.", {"output_dir": output_dir})
    runtime = json.loads((output_dir / "logs" / "runtime.json").read_text(encoding="utf-8"))

    assert result["status"] == "proceed_with_assumptions"
    assert result["stage_status"] == "completed"
    assert result["flow_decision"]["assumptions"]
    assert runtime["workflow_console"]["latest_stage"]["status"] == "completed"


def test_backend_records_future_workflow_gate_actions(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("future_decision_run", "Make a mounting plate.")

    recorded = backend.record_gate_decision_by_id(
        "future_decision_run",
        stage="requirement",
        action="proceed_with_assumptions",
        reason="Low-risk L0 draft can continue with visible assumptions.",
    )

    assert recorded["decision"]["action"] == "proceed_with_assumptions"
    assert "proceed_with_assumptions" in GATE_DECISION_ACTIONS


def test_backend_records_gate_decision_payload_without_new_readable_artifact(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("decision_run", "Make a spacer.")

    recorded = backend.record_gate_decision_by_id(
        "decision_run",
        stage="planning",
        action="override",
        payload={"field": "dimensions.outer_diameter_mm", "value": 12},
    )

    assert recorded["decision"]["payload"]["field"] == "dimensions.outer_diameter_mm"
    assert [item["name"] for item in backend.list_artifacts_by_id("decision_run")] == [
        "logs/runtime.json",
        "prompt.txt",
    ]


def test_backend_exposes_safe_gate_payload_summary_only(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("payload_summary", "Make a mounting plate.")

    recorded = backend.record_gate_decision_by_id(
        "payload_summary",
        stage="requirement",
        action="proceed_with_assumptions",
        reason="Proceed with template defaults.",
        payload={
            "field": "dimensions.length",
            "assumption": "Use selected template defaults.",
            "path": r"D:\MyCode\llm2cad\outputs\payload_summary",
            "api_key": "secret-token",
            "count": 3,
            "fields": ["dimensions.length", r"D:\MyCode\llm2cad\secret.txt"],
        },
    )
    metadata = backend.read_run_metadata_by_id("payload_summary")
    runtime = backend.read_artifact_by_id("payload_summary", "logs/runtime.json")["content"]["workflow_console"]

    assert recorded["decision"]["payload"]["path"].startswith("D:\\MyCode")
    assert runtime["latest_gate_decision"]["payload"]["api_key"] == "secret-token"
    assert metadata["status"]["gate_decision"]["payload_summary"] == {
        "count": 6,
        "items": [
            {"key": "assumption", "value": "Use selected template defaults."},
            {"key": "count", "value": 3},
            {"key": "field", "value": "dimensions.length"},
            {"key": "fields", "value": "dimensions.length"},
        ],
    }
    assert metadata["gate_history"][0]["payload_summary"] == metadata["status"]["gate_decision"]["payload_summary"]
    assert "payload" not in metadata["status"]["gate_decision"]
    assert "D:\\MyCode" not in json.dumps(metadata["status"]["gate_decision"])
    assert "secret-token" not in json.dumps(metadata["gate_history"])


def test_backend_rejects_invalid_gate_decision_inputs(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("decision_run", "Make a spacer.")

    with pytest.raises(ValueError, match="gate decision stage"):
        backend.record_gate_decision_by_id("decision_run", stage="shell", action="approve")
    with pytest.raises(ValueError, match="gate decision action"):
        backend.record_gate_decision_by_id("decision_run", stage="requirement", action="execute")
    with pytest.raises(ValueError, match="payload must be a dictionary"):
        backend.record_gate_decision_by_id("decision_run", stage="requirement", action="override", payload="bad")


def test_backend_writes_editable_requirement_artifact_by_id(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")
    requirement = {
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
        "requirement_status": {"complete_for_generation": True},
    }

    written = backend.write_artifact_by_id("edit_run", "requirement.json", requirement)
    runtime = backend.read_artifact_by_id("edit_run", "logs/runtime.json")["content"]["workflow_console"]

    assert written["artifact"]["content"]["part_type"] == "spacer"
    assert written["edit"]["artifact"] == "requirement.json"
    assert written["run"]["status"]["artifact_edit"]["artifact"] == "requirement.json"
    assert runtime["latest_artifact_edit"] == written["edit"]
    assert runtime["artifact_edit_count"] == 1
    assert "requirement.json" in EDITABLE_ARTIFACTS


def test_backend_writes_valid_input_ir_by_id(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")
    input_ir = {
        "part_type": "spacer",
        "part_name": "edited_spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
        "outputs": ["step", "stl"],
        "check_level": "L0",
    }

    written = backend.write_artifact_by_id("edit_run", "input_ir.json", input_ir)

    assert written["artifact"]["content"]["part_name"] == "edited_spacer"


def test_backend_rejects_non_editable_artifact_write(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")

    with pytest.raises(ValueError, match="artifact is not editable"):
        backend.write_artifact_by_id("edit_run", "report.json", {"status": "success"})


def test_backend_rejects_artifact_write_traversal(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")

    with pytest.raises(ValueError, match="artifact is not editable"):
        backend.write_artifact_by_id("edit_run", "../requirement.json", {"part_type": "spacer"})


def test_backend_rejects_non_object_artifact_write(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")

    with pytest.raises(ValueError, match="must be a JSON object"):
        backend.write_artifact_by_id("edit_run", "requirement.json", ["bad"])


def test_backend_rejects_invalid_input_ir_write(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")
    invalid_ir = {
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12},
        "features": {},
        "outputs": ["step"],
    }

    with pytest.raises(ValueError, match="failed CAD IR validation"):
        backend.write_artifact_by_id("edit_run", "input_ir.json", invalid_ir)


def test_backend_rejects_invalid_planning_artifact_write(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")

    with pytest.raises(ValueError, match="artifact_type must be 'planning'"):
        backend.write_artifact_by_id(
            "edit_run",
            "planning_artifact.json",
            {
                "artifact_type": "plan",
                "route": {},
                "selected_parts": [],
                "flow_gate_status": {},
            },
        )


def test_backend_runs_stages_from_existing_run_artifacts(tmp_path):
    runner = StageRunner()
    backend = WorkflowConsoleBackend(stage_runner=runner)
    run_dir = Path.cwd() / "outputs" / f"pytest_console_stage_sequence_{uuid4().hex}"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text(
        "Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.\n",
        encoding="utf-8",
    )

    requirement = backend.run_stage(run_dir, "requirement")
    planning = backend.run_stage(run_dir, "planning")
    modeling = backend.run_stage(run_dir, "part_modeling")
    runtime = backend.read_artifact(run_dir, "logs/runtime.json")["content"]["workflow_console"]

    assert requirement["result"]["stage"] == "requirement"
    assert planning["result"]["stage"] == "planning"
    assert modeling["result"]["status"] == "success"
    assert (run_dir / "input_ir.json").exists()
    assert (run_dir / "model.step").exists()
    assert [stage["stage"] for stage in runtime["stages"]] == ["requirement", "planning", "part_modeling"]


def test_backend_runs_review_and_outputs_from_existing_artifacts(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run_dir = tmp_path / "outputs" / "reviewable_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")
    (run_dir / "model.step").write_text("STEP placeholder\n", encoding="utf-8")
    (run_dir / "model.stl").write_text("STL placeholder\n", encoding="utf-8")
    (run_dir / "report.md").write_text("# Report\n", encoding="utf-8")
    (run_dir / "report.json").write_text(
        json.dumps({
            "status": "success",
            "success": True,
            "errors": [],
            "flow_decision": {"action": "proceed", "from_stage": "review", "proceed_to": "outputs"},
        }) + "\n",
        encoding="utf-8",
    )

    review = backend.run_stage_by_id("reviewable_run", "review")
    outputs = backend.run_stage_by_id("reviewable_run", "outputs")
    runtime = backend.read_artifact_by_id("reviewable_run", "logs/runtime.json")["content"]["workflow_console"]

    assert review["result"]["stage"] == "review"
    assert review["result"]["stage_status"] == "completed"
    assert outputs["result"]["stage"] == "outputs"
    assert outputs["result"]["status"] == "published"
    assert outputs["result"]["files"]["model.step"].endswith("model.step")
    assert [stage["stage"] for stage in runtime["stages"]] == ["review", "outputs"]
    assert runtime["latest_stage"]["stage"] == "outputs"


def test_outputs_stage_blocks_without_primary_step_artifact(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run_dir = tmp_path / "outputs" / "blocked_outputs"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")
    (run_dir / "report.md").write_text("# Report\n", encoding="utf-8")
    (run_dir / "report.json").write_text(
        json.dumps({
            "status": "success",
            "success": True,
            "errors": [],
            "flow_decision": {"action": "proceed", "from_stage": "review", "proceed_to": "outputs"},
        }) + "\n",
        encoding="utf-8",
    )

    outputs = backend.run_stage_by_id("blocked_outputs", "outputs")

    assert outputs["result"]["stage_status"] == "blocked"
    assert outputs["result"]["missing"] == ["model.step"]


def test_workflow_console_backend_lists_status_artifacts_and_downloadables(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")
    (run_dir / "report.json").write_text(
        json.dumps({"status": "success", "success": True, "flow_decision": {"action": "proceed"}}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "agent_trace.json").write_text(
        json.dumps({"total_attempts": 1, "final_selected_candidate": "A"}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "model.step").write_text("STEP placeholder\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    runs = backend.list_runs()
    metadata = backend.read_run_metadata(run_dir)
    report = backend.read_artifact(run_dir, "report.json")

    assert [run["run_id"] for run in runs] == ["console_run"]
    assert metadata["status"]["status"] == "success"
    assert metadata["status"]["attempts"] == 1
    assert [item["name"] for item in metadata["downloadables"]] == ["model.step"]
    assert report["content"]["flow_decision"]["action"] == "proceed"


def test_backend_resolves_metadata_by_safe_run_id(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    metadata = backend.read_run_metadata_by_id("console_run", root="outputs")

    assert metadata["run_id"] == "console_run"
    assert Path(metadata["run_dir"]) == run_dir.resolve()


def test_backend_rejects_path_traversal_run_id(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="run id"):
        backend.read_run_metadata_by_id("../outside")


def test_backend_rejects_absolute_run_id(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="run id"):
        backend.read_run_metadata_by_id(str(tmp_path / "outputs" / "console_run"))


def test_backend_unknown_run_id_raises_clear_error(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(FileNotFoundError, match="workflow console run not found: missing_run"):
        backend.read_run_metadata_by_id("missing_run")


def test_backend_rejects_artifact_path_traversal_by_id(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="artifact is not readable"):
        backend.read_artifact_by_id("console_run", "../report.json")


def test_backend_rejects_unsupported_stage_by_id(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    with pytest.raises(ValueError, match="unsupported workflow console stage"):
        backend.run_stage_by_id("console_run", "shell")


def test_backend_downloadables_by_id_remain_whitelisted(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    for name in ["model.step", "model.stl", "preview.png", "model.py", "notes.txt", "report.md"]:
        (run_dir / name).write_text(f"{name}\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    assert [item["name"] for item in backend.list_downloadables_by_id("console_run")] == [
        "model.step",
        "model.stl",
        "preview.png",
        "model.py",
    ]


def test_workflow_console_server_resolves_only_whitelisted_downloadables(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")
    (run_dir / "model.step").write_text("STEP placeholder\n", encoding="utf-8")
    (run_dir / "notes.txt").write_text("not downloadable\n", encoding="utf-8")
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    resolved = resolve_downloadable(backend, "console_run", "model.step")

    assert resolved == (run_dir / "model.step").resolve()
    with pytest.raises(ValueError, match="downloadable is not allowed"):
        resolve_downloadable(backend, "console_run", "notes.txt")
    with pytest.raises(FileNotFoundError, match="downloadable not found"):
        resolve_downloadable(backend, "console_run", "model.stl")


def test_workflow_console_static_ui_exposes_required_local_workflow_controls():
    console = (Path.cwd() / "web-viewer" / "workflow-console.html").read_text(encoding="utf-8")

    for expected in [
            "Create Run",
            "Stage Timeline",
            "Artifacts",
            "Downloads",
            "Gate",
            "Summary",
        "report_summary",
        "renderReportSummary",
        "summaryIssues",
        "summaryTextList",
        "summaryFields",
        "Requirement Gate",
        "Planning Gate",
        "Assumptions",
        "Missing",
        "Follow-ups",
        "Planning Risks",
        "preferredArtifact",
        "artifactKind",
        "artifact-kind",
        "error-alert",
        "showError",
        "setBusy",
        "withBusy",
        "state.busy",
            "preview-interactive",
            "preview-active",
            "setPreviewInteractive",
            "toggle-preview",
            "Scroll-safe preview",
            "Click the preview",
            "inspector-tab",
        "activeInspectorTab",
        "setInspectorTab",
        "data-inspector-tab",
        "Inspector",
        "STL Preview",
        "stage_history",
        "gate_history",
        "stageHistoryByStage",
        "stageHistorySummary",
        "gateHistoryByStage",
        "gateHistorySummary",
        "payloadSummaryLine",
        "escapeHtml",
        'api("write_artifact"',
        'api("record_gate_decision"',
        'api("run_stage"',
    ]:
        assert expected in console


def test_backend_artifacts_by_id_remain_readable_artifact_whitelist(tmp_path):
    run_dir = tmp_path / "outputs" / "console_run"
    run_dir.mkdir(parents=True)
    (run_dir / "logs").mkdir()
    for name in READABLE_ARTIFACTS:
        artifact_path = run_dir / name
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        content = "{}\n" if artifact_path.suffix == ".json" else f"{name}\n"
        artifact_path.write_text(content, encoding="utf-8")
    (run_dir / "model.step").write_text("STEP placeholder\n", encoding="utf-8")
    (run_dir / "extra.json").write_text("{}\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    assert {item["name"] for item in backend.list_artifacts_by_id("console_run")} == READABLE_ARTIFACTS
    with pytest.raises(ValueError, match="artifact is not readable"):
        backend.read_artifact_by_id("console_run", "extra.json")


def test_stage_runner_text_pipeline_and_deterministic_adapter_smoke():
    adapter = DeterministicAgentAdapter()
    requirement = adapter.parse_requirement("Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.")
    assert requirement["part_type"] == "spacer"

    output_dir = Path.cwd() / "outputs" / "pytest_stage_runner_text_pipeline_smoke"
    result = StageRunner().run_text_pipeline(
        "Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.",
        {"output_dir": output_dir},
    )
    runtime = json.loads((output_dir / "logs" / "runtime.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert (output_dir / "model.step").exists()
    assert (output_dir / "report.json").exists()
    assert runtime["workflow_console"]["latest_stage"]["stage"] == "text_pipeline"
