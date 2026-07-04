import json
from uuid import uuid4
from pathlib import Path

import pytest

from ai_native_cad.agents import DeterministicAgentAdapter, JsonContractAgentAdapter, JsonContractProviderError
from ai_native_cad.workflow_console.stage_runner import READABLE_ARTIFACTS
from ai_native_cad.workflow_console import (
    ACTION_NAMES,
    EDITABLE_ARTIFACTS,
    GATE_DECISION_ACTIONS,
    ROUTE_SPECS,
    ROUTE_SPECS_BY_NAME,
    STATUS_CREATED,
    WORKFLOW_STATUS_VALUES,
    StageRunner,
    WorkflowConsoleActions,
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


def _does_not_contain_absolute_paths(value):
    if isinstance(value, dict):
        return all(_does_not_contain_absolute_paths(item) for item in value.values())
    if isinstance(value, list):
        return all(_does_not_contain_absolute_paths(item) for item in value)
    if isinstance(value, str):
        return not Path(value).is_absolute() and str(Path.cwd().resolve()) not in value
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


class ProviderCheckAdapter(DeterministicAgentAdapter):
    provider_identity = {
        "provider": "fake/json",
        "adapter": "json_contract",
        "model": "fake-model",
        "api_key_config": "env_var_name_configured",
    }

    def parse_requirement(self, prompt, context=None):
        return {
            "part_type": "spacer",
            "dimensions": {"outer_diameter": 12, "inner_diameter": 6, "thickness": 4},
        }


class FailingProviderCheckAdapter(ProviderCheckAdapter):
    def parse_requirement(self, prompt, context=None):
        raise JsonContractProviderError("parse_requirement", "auth_failed", retryable=False)


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
        "configure_provider",
        "create_run_by_id",
        "list_runs",
        "read_provider_config",
        "read_run_metadata_by_id",
        "run_stage_by_id",
        "run_revision_by_id",
        "test_provider_connection",
        "list_artifacts_by_id",
        "read_artifact_by_id",
        "write_artifact_by_id",
        "list_downloadables_by_id",
        "record_gate_decision_by_id",
        "WorkflowConsoleActions.create_part_request",
        "WorkflowConsoleActions.review_part_request",
        "WorkflowConsoleActions.create_reviewed_handoff",
        "WorkflowConsoleActions.create_reviewed_part",
        "WorkflowConsoleActions.review_part_result",
        "WorkflowConsoleActions.save_stage_review",
    }

    assert {spec.backend_operation for spec in ROUTE_SPECS} == expected_operations
    assert all(
        spec.backend_operation.endswith("_by_id")
        or spec.backend_operation in {
            "list_runs",
            "read_provider_config",
            "configure_provider",
            "test_provider_connection",
            "WorkflowConsoleActions.create_part_request",
            "WorkflowConsoleActions.review_part_request",
            "WorkflowConsoleActions.create_reviewed_handoff",
            "WorkflowConsoleActions.create_reviewed_part",
            "WorkflowConsoleActions.review_part_result",
            "WorkflowConsoleActions.save_stage_review",
        }
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
    assert ROUTE_SPECS_BY_NAME["run_revision"].method == "POST"
    assert ROUTE_SPECS_BY_NAME["run_revision"].backend_operation == "run_revision_by_id"
    assert ROUTE_SPECS_BY_NAME["read_provider_config"].method == "GET"
    assert ROUTE_SPECS_BY_NAME["read_provider_config"].backend_operation == "read_provider_config"
    assert ROUTE_SPECS_BY_NAME["configure_provider"].method == "POST"
    assert ROUTE_SPECS_BY_NAME["configure_provider"].backend_operation == "configure_provider"
    assert ROUTE_SPECS_BY_NAME["test_provider_connection"].method == "POST"
    assert ROUTE_SPECS_BY_NAME["test_provider_connection"].backend_operation == "test_provider_connection"
    assert ROUTE_SPECS_BY_NAME["action_part_request"].path == "/api/actions/part-request"
    assert ROUTE_SPECS_BY_NAME["action_part_result_review"].path == "/api/actions/part-result-review"
    assert ROUTE_SPECS_BY_NAME["action_save_stage_review"].path == "/api/actions/stage-review"


def test_workflow_console_internal_error_shape_does_not_leak_local_paths():
    response = error_response(RuntimeError(r"failed under D:\MyCode\llm2cad\outputs\secret_run"))

    assert response["status_code"] == 500
    assert response["error"]["type"] == "internal_error"
    assert response["error"]["message"] == "internal workflow console error"
    assert "D:\\MyCode" not in response["error"]["message"]
    assert "secret_run" not in response["error"]["message"]


def test_workflow_console_action_service_rejects_paths_outside_output_root(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    actions = WorkflowConsoleActions(backend)

    with pytest.raises(ValueError, match="run id"):
        actions.create_part_request("../outside")

    with pytest.raises(ValueError, match="run root is not configured"):
        actions.create_part_request("console_run", root=tmp_path / "elsewhere")


def test_workflow_console_action_service_accepts_artifact_relative_run_under_output_root(tmp_path, monkeypatch):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run_dir = tmp_path / "outputs" / "assembly_review"
    run_dir.mkdir(parents=True)
    (run_dir / "assembly_plan.json").write_text(
        json.dumps({"artifact_type": "assembly_plan", "parts": [{"part_id": "base"}]}),
        encoding="utf-8",
    )
    calls = []

    def fake_part_request(assembly_plan, *, output_dir=None, part_id=None, output_root=None):
        calls.append({"assembly_plan": Path(assembly_plan), "output_dir": Path(output_dir), "part_id": part_id})
        Path(output_dir).mkdir(parents=True)
        (Path(output_dir) / "part_create_request.json").write_text(
            json.dumps({"artifact_type": "part_create_request", "part_id": "base", "status": "ready_for_review"}),
            encoding="utf-8",
        )
        return {
            "status": "ready_for_review",
            "success": True,
            "output_dir": str(output_dir),
            "part_create_request": {
                "artifact_type": "part_create_request",
                "part_id": "base",
                "diagnostic_codes": ["part_request.created"],
            },
            "files": {"request": str(Path(output_dir) / "part_create_request.json")},
            "raw_provider_payload": {"api_key": "secret"},
        }

    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_assembly_part_request_pipeline", fake_part_request)

    result = WorkflowConsoleActions(backend).create_part_request("assembly_review", part_id="base")

    assert result["stage_count"] == 1
    assert result["summary"]["status"] == "ready_for_review"
    assert result["summary"]["artifacts"] == ["part_create_request.json"]
    assert calls == [{"assembly_plan": run_dir / "assembly_plan.json", "output_dir": run_dir / "02_part_request", "part_id": "base"}]
    assert _does_not_contain_absolute_paths(result)
    assert _does_not_contain_keys(result, {"raw_provider_payload", "api_key", "secret", "token"})


def test_workflow_console_action_routes_are_one_stage_and_sanitized(tmp_path, monkeypatch):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run_dir = tmp_path / "outputs" / "route_action"
    run_dir.mkdir(parents=True)
    (run_dir / "assembly_plan.json").write_text(json.dumps({"parts": [{"part_id": "base"}]}), encoding="utf-8")

    def fake_part_request(assembly_plan, *, output_dir=None, part_id=None, output_root=None):
        Path(output_dir).mkdir(parents=True)
        return {
            "status": "ready_for_review",
            "success": True,
            "output_dir": str(output_dir),
            "part_create_request": {
                "artifact_type": "part_create_request",
                "part_id": "base",
                "diagnostic_codes": ["part_request.created"],
            },
            "agent_trace": {"provider_response": {"token": "secret"}},
            "files": {"request": str(Path(output_dir) / "part_create_request.json")},
        }

    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_assembly_part_request_pipeline", fake_part_request)

    response = dispatch_route(backend, "action_part_request", body={"run_id": "route_action"})

    assert response["ok"] is True
    assert response["status_code"] == 201
    assert response["data"]["stage_count"] == 1
    assert response["data"]["summary"]["stage_count"] == 1
    assert _does_not_contain_absolute_paths(response["data"])
    assert _does_not_contain_keys(
        response["data"],
        {"raw_provider_payload", "provider_response", "api_key", "token", "secret", "payload"},
    )
    assert _does_not_contain_text(response["data"], ["secret", "api_key", "token", "provider_response"])


def test_workflow_console_action_missing_upstream_artifact_blocks_gracefully(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "missing_upstream"}, body={"prompt": "Make a part."})

    response = dispatch_route(backend, "action_part_review", body={"run_id": "missing_upstream"})

    assert response["ok"] is False
    assert response["status_code"] == 404
    assert response["error"]["type"] == "not_found"
    assert "part_create_request.json" in response["error"]["message"]
    assert _does_not_contain_absolute_paths(response)


def test_workflow_console_reviewed_part_create_action_uses_one_handoff_and_sanitizes_nested_payloads(tmp_path, monkeypatch):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run_dir = tmp_path / "outputs" / "single_handoff"
    run_dir.mkdir(parents=True)
    (run_dir / "reviewed_part_handoff.json").write_text(
        json.dumps({
            "artifact_type": "reviewed_part_handoff",
            "part_id": "base",
            "status": "ready_for_single_part_planning",
        }),
        encoding="utf-8",
    )
    calls = []

    def fake_single_create(reviewed_part_handoff, adapter, *, output_dir=None, output_root=None):
        calls.append({"handoff": Path(reviewed_part_handoff), "output_dir": Path(output_dir)})
        return {
            "status": "success",
            "success": True,
            "output_dir": str(output_dir),
            "child_output_dir": str(Path(output_dir) / "single_part_base"),
            "reviewed_part_handoff": {
                "artifact_type": "reviewed_part_handoff",
                "part_id": "base",
                "diagnostic_codes": ["reviewed_part_single_create.ready"],
            },
            "child_result": {
                "status": "success",
                "provider_messages": [{"role": "assistant", "content": "secret token"}],
                "raw_response": {"env": "OPENAI_API_KEY=secret"},
            },
            "files": {"step": str(Path(output_dir) / "single_part_base" / "model.step")},
        }

    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_reviewed_part_single_create_pipeline", fake_single_create)

    response = dispatch_route(backend, "action_reviewed_part_create", body={"run_id": "single_handoff"})

    assert response["ok"] is True
    assert response["data"]["stage_count"] == 1
    assert response["data"]["summary"]["action"] == "reviewed_part_create"
    assert calls == [{"handoff": run_dir / "reviewed_part_handoff.json", "output_dir": run_dir / "05_single_create"}]
    assert _does_not_contain_absolute_paths(response["data"])
    assert _does_not_contain_keys(response["data"], {"provider_messages", "raw_response", "env", "token", "secret"})
    assert _does_not_contain_text(response["data"], ["OPENAI_API_KEY", "secret token", "provider_messages"])


def test_workflow_console_staged_action_routes_do_not_include_batch_or_assembly_generation():
    action_specs = [spec for spec in ROUTE_SPECS if spec.name.startswith("action_")]

    assert {spec.name for spec in action_specs} == {
        "action_part_request",
        "action_part_review",
        "action_reviewed_handoff",
        "action_reviewed_part_create",
        "action_part_result_review",
        "action_save_stage_review",
    }
    assert all("batch" not in spec.path for spec in action_specs)
    assert all("assembly-generation" not in spec.path for spec in action_specs)
    assert "batch_generation" not in ACTION_NAMES
    assert "assembly_generation" not in ACTION_NAMES


def test_workflow_console_stage_review_can_be_saved_under_selected_run(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "review_target"}, body={"prompt": "Make a bracket."})

    response = dispatch_route(
        backend,
        "action_save_stage_review",
        body={
            "run_id": "review_target",
            "stage": "assembly_plan",
            "review_status": "needs_revision",
            "target_rework_stage": "requirement",
            "user_notes": "The lid should be treated as a flat cover.",
            "requested_changes": ["Keep screws reference_only", "Do not generate full assembly"],
        },
    )
    artifact = json.loads((tmp_path / "outputs" / "review_target" / "stage_review.json").read_text(encoding="utf-8"))

    assert response["ok"] is True
    assert response["status_code"] == 201
    assert response["data"]["summary"]["stage"] == "assembly_plan"
    assert response["data"]["summary"]["review_status"] == "needs_revision"
    assert response["data"]["summary"]["requested_changes_count"] == 2
    assert artifact["created_by"] == "user"
    assert artifact["diagnostic_codes"] == ["stage_review.user_requested_rework"]
    assert not (tmp_path / "outputs" / "review_target" / "model.step").exists()
    assert _does_not_contain_absolute_paths(response["data"])


def test_workflow_console_stage_review_rejects_invalid_run_ids_and_traversal(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "safe_review"}, body={"prompt": "Make a bracket."})

    missing = dispatch_route(
        backend,
        "action_save_stage_review",
        body={"run_id": "missing_review", "stage": "requirement", "review_status": "approved"},
    )
    traversal = dispatch_route(
        backend,
        "action_save_stage_review",
        body={"run_id": "../safe_review", "stage": "requirement", "review_status": "approved"},
    )

    assert missing["ok"] is False
    assert missing["status_code"] == 404
    assert traversal["ok"] is False
    assert traversal["status_code"] == 400
    assert _does_not_contain_absolute_paths(traversal)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"run_id": "enum_review", "stage": "unknown", "review_status": "approved"}, "stage review stage"),
        ({"run_id": "enum_review", "stage": "requirement", "review_status": "maybe"}, "stage review status"),
        (
            {
                "run_id": "enum_review",
                "stage": "assembly_plan",
                "review_status": "needs_revision",
                "target_rework_stage": "unknown",
            },
            "rework target stage",
        ),
    ],
)
def test_workflow_console_stage_review_rejects_unknown_enum_values(tmp_path, body, message):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "enum_review"}, body={"prompt": "Make a bracket."})

    response = dispatch_route(backend, "action_save_stage_review", body=body)

    assert response["ok"] is False
    assert response["status_code"] == 400
    assert message in response["error"]["message"]


def test_workflow_console_stage_review_long_notes_are_truncated_and_sanitized(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "long_review"}, body={"prompt": "Make a bracket."})

    response = dispatch_route(
        backend,
        "action_save_stage_review",
        body={
            "run_id": "long_review",
            "stage": "requirement",
            "review_status": "blocked",
            "user_notes": "A" * 2000,
            "requested_changes": "\n".join([f"change {index}" for index in range(20)]),
        },
    )
    artifact = json.loads((tmp_path / "outputs" / "long_review" / "stage_review.json").read_text(encoding="utf-8"))

    assert response["ok"] is True
    assert len(artifact["user_notes"]) == 1200
    assert len(artifact["requested_changes"]) == 12
    assert response["data"]["summary"]["user_notes_preview"] == "A" * 160


def test_workflow_console_stage_review_summary_is_sanitized_and_in_run_summary(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "summary_review"}, body={"prompt": "Make a bracket."})

    dispatch_route(
        backend,
        "action_save_stage_review",
        body={
            "run_id": "summary_review",
            "stage": "requirement",
            "review_status": "approved",
            "user_notes": "api_key=SECRET_SHOULD_NOT_APPEAR",
            "requested_changes": [str(tmp_path / "secret.txt"), "safe change"],
        },
    )
    response = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "summary_review"})
    summary = response["data"]["stage_review_summary"]
    serialized = json.dumps(response["data"], sort_keys=True)

    assert summary["present"] is True
    assert summary["stage"] == "requirement"
    assert summary["review_status"] == "approved"
    assert summary["requested_changes_count"] == 1
    assert "stage_review.json" in {item["name"] for item in response["data"]["artifacts"]}
    assert "SECRET_SHOULD_NOT_APPEAR" not in serialized
    assert str(tmp_path) not in serialized


def test_workflow_console_stage_review_makes_no_provider_or_cad_pipeline_call(tmp_path, monkeypatch):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "local_only_review"}, body={"prompt": "Make a bracket."})

    def fail_if_called(*args, **kwargs):
        raise AssertionError("stage review must not call provider or CAD pipeline")

    backend.stage_runner.agent_adapter.parse_requirement = fail_if_called
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_assembly_part_request_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_part_request_review_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_part_result_review_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_reviewed_part_handoff_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_reviewed_part_single_create_pipeline", fail_if_called)

    response = dispatch_route(
        backend,
        "action_save_stage_review",
        body={"run_id": "local_only_review", "stage": "requirement", "review_status": "approved"},
    )

    assert response["ok"] is True
    assert response["data"]["summary"]["stage"] == "requirement"


def test_workflow_console_run_summary_includes_negotiation_placeholders(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "negotiation_placeholders"}, body={"prompt": "Make a bracket."})

    response = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "negotiation_placeholders"})
    negotiation = response["data"]["report_summary"]["negotiation"]

    assert negotiation == {
        "assumptions": [],
        "missing_information": [],
        "clarification_questions": [],
        "blocked_reason": None,
        "user_review_status": None,
    }


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


def test_workflow_console_dispatch_configures_provider_without_secret_fields(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    configured = dispatch_route(
        backend,
        "configure_provider",
        body={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "timeout_seconds": 12,
            "max_retries": 2,
        },
    )
    read = dispatch_route(backend, "read_provider_config")

    assert configured["ok"] is True
    assert configured["data"]["provider_identity"]["provider"] == "deepseek"
    assert configured["data"]["provider_identity"]["model"] == "deepseek-chat"
    assert configured["data"]["provider_identity"]["timeout_seconds"] == 12
    assert configured["data"]["provider_identity"]["max_retries"] == 2
    assert "DEEPSEEK_API_KEY" not in json.dumps(configured["data"])
    assert isinstance(backend.stage_runner.agent_adapter, JsonContractAgentAdapter)
    assert read["data"] == configured["data"]


def test_workflow_console_provider_config_rejects_browser_secrets(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    response = dispatch_route(
        backend,
        "configure_provider",
        body={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "secret-token",
        },
    )

    assert response["status_code"] == 400
    assert response["error"]["type"] == "bad_request"
    assert "secret-token" not in json.dumps(response)


def test_backend_can_restore_local_mock_provider(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    backend.configure_provider("openai", model="gpt-5.1", timeout_seconds=20, max_retries=1)
    restored = backend.configure_provider("local")

    assert isinstance(backend.stage_runner.agent_adapter, DeterministicAgentAdapter)
    assert restored["provider_identity"]["provider"] == "local/mock"
    assert restored["provider_identity"]["network"] == "disabled"


def test_workflow_console_provider_connection_test_succeeds_with_configured_adapter(tmp_path):
    backend = WorkflowConsoleBackend(
        project_root=tmp_path,
        provider_adapter_factory=lambda *args, **kwargs: ProviderCheckAdapter(),
    )
    backend.configure_provider("deepseek", model="fake-model")

    response = dispatch_route(backend, "test_provider_connection")

    assert response["ok"] is True
    assert response["data"]["status"] == "ok"
    assert response["data"]["provider_identity"]["provider"] == "fake/json"
    assert response["data"]["contract"] == {
        "part_type": "spacer",
        "dimension_keys": ["inner_diameter", "outer_diameter", "thickness"],
    }
    assert "api_key" not in json.dumps(response["data"])


def test_workflow_console_provider_connection_test_reports_secret_safe_failure(tmp_path):
    backend = WorkflowConsoleBackend(
        project_root=tmp_path,
        provider_adapter_factory=lambda *args, **kwargs: FailingProviderCheckAdapter(),
    )
    backend.configure_provider("deepseek", model="fake-model")

    response = dispatch_route(backend, "test_provider_connection")

    assert response["ok"] is True
    assert response["data"]["status"] == "failed"
    assert response["data"]["error"]["category"] == "auth_failed"
    assert "DEEPSEEK_API_KEY" not in json.dumps(response["data"])


def test_workflow_console_provider_connection_test_accepts_local_mock(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    response = dispatch_route(backend, "test_provider_connection")

    assert response["ok"] is True
    assert response["data"]["status"] == "ok"
    assert response["data"]["operation"] == "local_provider_check"
    assert response["data"]["provider_identity"]["provider"] == "local/mock"


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


def test_workflow_console_dispatch_runs_blocked_revision_by_safe_child_id():
    backend = WorkflowConsoleBackend()
    suffix = uuid4().hex
    parent_id = f"pytest_console_revision_parent_{suffix}"
    child_id = f"pytest_console_revision_child_{suffix}"
    parent_dir = Path.cwd() / "outputs" / parent_id
    parent_dir.mkdir(parents=True, exist_ok=False)
    (parent_dir / "input_ir.json").write_text(
        json.dumps({
            "part_type": "mounting_plate",
            "part_name": parent_id,
            "unit": "mm",
            "dimensions": {"length": 80, "width": 40, "thickness": 5},
            "features": {"holes": {"diameter": 4.5, "positions": "corner_4"}},
            "outputs": ["step", "stl"],
        }) + "\n",
        encoding="utf-8",
    )

    response = dispatch_route(
        backend,
        "run_revision",
        path_params={"run_id": parent_id, "child_run_id": child_id},
        body={"prompt": "Make it more futuristic."},
    )

    assert response["ok"] is True
    assert response["status_code"] == 201
    assert response["data"]["result"]["status"] == "blocked"
    assert response["data"]["run"]["run_id"] == child_id
    assert response["data"]["run"]["report_summary"]["revision_summary"]["relationship"] == "revision_blocked"
    assert response["data"]["run"]["downloadables"] == []
    assert response["data"]["result"]["files"]["revision_request"] == "revision_request.json"
    assert all("/" not in value and "\\" not in value for value in response["data"]["result"]["files"].values())
    assert _does_not_contain_keys(response["data"], {"path", "run_dir", "root", "output_dir"})

    child_dir = Path.cwd() / "outputs" / child_id
    assert (child_dir / "revision_request.json").exists()
    assert (child_dir / "comparison.json").exists()
    assert not (child_dir / "model.step").exists()
    assert not (child_dir / "model.stl").exists()


def test_workflow_console_dispatch_runs_successful_revision_by_safe_child_id():
    backend = WorkflowConsoleBackend()
    suffix = uuid4().hex
    parent_id = f"pytest_console_revision_success_parent_{suffix}"
    child_id = f"pytest_console_revision_success_child_{suffix}"

    create_response = dispatch_route(
        backend,
        "create_run",
        path_params={"run_id": parent_id},
        body={"prompt": "Generate an 80x40x5 mm mounting plate with four M4 holes in the corners."},
    )
    parent_response = dispatch_route(
        backend,
        "run_stage",
        path_params={"run_id": parent_id, "stage": "text_pipeline"},
    )
    response = dispatch_route(
        backend,
        "run_revision",
        path_params={"run_id": parent_id, "child_run_id": child_id},
        body={"prompt": "Increase the thickness to 8 mm."},
    )

    assert create_response["ok"] is True
    assert parent_response["ok"] is True
    assert parent_response["data"]["result"]["status"] == "success"
    assert response["ok"] is True
    assert response["status_code"] == 201
    assert response["data"]["run"]["run_id"] == child_id
    assert response["data"]["result"]["status"] == "success"
    assert _does_not_contain_keys(response["data"], {"path", "run_dir", "root", "output_dir"})
    assert _does_not_contain_absolute_paths(response["data"])
    assert all("/" not in value and "\\" not in value for value in response["data"]["result"]["files"].values())

    child_dir = Path.cwd() / "outputs" / child_id
    expected_artifacts = {
        "revision_request.json",
        "change_intent.json",
        "revision_plan.json",
        "patch.json",
        "comparison.json",
        "revision_report.md",
        "lineage.json",
        "report.json",
        "agent_trace.json",
    }
    for name in expected_artifacts | {"model.step", "model.stl"}:
        assert (child_dir / name).exists()

    comparison = backend.read_artifact_by_id(child_id, "comparison.json")["content"]
    revision_summary = response["data"]["run"]["report_summary"]["revision_summary"]

    assert comparison["requested_changes"]
    assert comparison["actual_ir_changes"]
    assert revision_summary["relationship"] == "revision_child"
    assert revision_summary["requested_change_count"] > 0
    assert revision_summary["actual_ir_change_count"] > 0


def test_backend_uses_next_default_revision_child_id():
    backend = WorkflowConsoleBackend()
    parent_id = f"pytest_default_revision_parent_{uuid4().hex}"
    parent_dir = Path.cwd() / "outputs" / parent_id
    parent_dir.mkdir(parents=True)
    (Path.cwd() / "outputs" / f"{parent_id}_revision_1").mkdir()
    (parent_dir / "input_ir.json").write_text(
        json.dumps({
            "part_type": "mounting_plate",
            "part_name": parent_id,
            "unit": "mm",
            "dimensions": {"length": 80, "width": 40, "thickness": 5},
            "features": {"holes": {"diameter": 4.5, "positions": "corner_4"}},
            "outputs": ["step", "stl"],
        }) + "\n",
        encoding="utf-8",
    )

    result = backend.run_revision_by_id(parent_id, None, "Make it more futuristic.")

    assert result["run"]["run_id"] == f"{parent_id}_revision_2"
    assert result["result"]["status"] == "blocked"
    assert (Path.cwd() / "outputs" / f"{parent_id}_revision_2" / "revision_request.json").exists()


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
    assert "secret-token" not in json.dumps(runtime["data"])
    private_runtime = backend.read_artifact_by_id("gate_payload", "logs/runtime.json")
    assert private_runtime["content"]["workflow_console"]["latest_gate_decision"]["payload"]["api_key"] == "secret-token"


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
        "revision_summary": {
            "present": False,
            "relationship": None,
            "parent_run_id": None,
            "child_run_id": None,
            "revision_index": None,
            "plan_status": None,
            "status": None,
            "blocked_reason": None,
            "requested_change_count": 0,
            "actual_ir_change_count": 0,
            "validation_change_count": 0,
            "system_repair_change_count": 0,
        },
        "negotiation": {
            "assumptions": [],
            "missing_information": [],
            "clarification_questions": [],
            "blocked_reason": None,
            "user_review_status": None,
        },
    }
    assert _does_not_contain_keys(metadata["report_summary"], {"path", "run_dir", "root", "output_dir", "file"})


def test_workflow_console_metadata_summarizes_revision_without_paths(tmp_path):
    run_dir = tmp_path / "outputs" / "revision_summary"
    run_dir.mkdir(parents=True)
    (run_dir / "report.json").write_text('{"status": "blocked", "success": false}\n', encoding="utf-8")
    (run_dir / "revision_plan.json").write_text('{"status": "no_structured_changes"}\n', encoding="utf-8")
    (run_dir / "comparison.json").write_text(
        json.dumps({
            "status": "blocked",
            "blocked_reason": "revision_plan.status=no_structured_changes",
            "parent_run_id": "parent_plate",
            "child_run_id": "revision_summary",
            "summary": {
                "requested_change_count": 0,
                "actual_ir_change_count": 0,
                "validation_change_count": 0,
                "system_repair_change_count": 0,
            },
            "parent_artifacts": {"input_ir": str(run_dir / "parent" / "input_ir.json")},
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "lineage.json").write_text(
        json.dumps({
            "relationship": "revision_blocked",
            "parent_run_id": "parent_plate",
            "child_run_id": "revision_summary",
            "revision_index": 2,
            "parent_run_dir": str(tmp_path / "outputs" / "parent_plate"),
        }) + "\n",
        encoding="utf-8",
    )

    summary = WorkflowConsoleBackend(project_root=tmp_path).read_run_metadata_by_id("revision_summary")[
        "report_summary"
    ]["revision_summary"]

    assert summary == {
        "present": True,
        "relationship": "revision_blocked",
        "parent_run_id": "parent_plate",
        "child_run_id": "revision_summary",
        "revision_index": 2,
        "plan_status": "no_structured_changes",
        "status": "blocked",
        "blocked_reason": "revision_plan.status=no_structured_changes",
        "requested_change_count": 0,
        "actual_ir_change_count": 0,
        "validation_change_count": 0,
        "system_repair_change_count": 0,
    }
    assert _does_not_contain_keys(summary, {"path", "run_dir", "root", "output_dir", "parent_artifacts"})


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


def test_workflow_console_read_artifact_route_redacts_raw_provider_payloads_and_secrets(tmp_path):
    run_dir = tmp_path / "outputs" / "redacted_artifact"
    run_dir.mkdir(parents=True)
    (run_dir / "part_request_review.json").write_text(
        json.dumps({
            "status": "approved",
            "checks": {"has_interface_constraints": True},
            "raw_provider_response": {"message": "SECRET_SHOULD_NOT_APPEAR"},
            "provider_messages": ["SECRET_SHOULD_NOT_APPEAR"],
            "diagnostic_codes": ["part_review.approved"],
            "local_path": str(tmp_path / "outputs" / "redacted_artifact"),
        }) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    response = dispatch_route(
        backend,
        "read_artifact",
        path_params={"run_id": "redacted_artifact", "artifact": "part_request_review.json"},
    )
    serialized = json.dumps(response, sort_keys=True)

    assert response["ok"] is True
    assert response["data"]["content"]["status"] == "approved"
    assert response["data"]["content"]["diagnostic_codes"] == ["part_review.approved"]
    assert "raw_provider_response" not in serialized
    assert "provider_messages" not in serialized
    assert "SECRET_SHOULD_NOT_APPEAR" not in serialized
    assert str(tmp_path) not in serialized


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
    assert metadata["stage_history"][0]["adapter_activity"] == {
        "operation": "parse_requirement",
        "provider_identity": {
            "provider": "local/mock",
            "adapter": "deterministic",
            "network": "disabled",
        },
    }
    assert metadata["status"]["adapter_activity"] == metadata["stage_history"][0]["adapter_activity"]
    assert "timestamp" in metadata["stage_history"][0]
    assert "output_dir" not in metadata["stage_history"][0]
    assert runtime["content"]["workflow_console"]["latest_stage"]["stage"] == "requirement"


def test_backend_sanitizes_adapter_activity_metadata(tmp_path):
    run_dir = tmp_path / "outputs" / "adapter_metadata"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a spacer.\n", encoding="utf-8")
    (run_dir / "logs").mkdir()
    (run_dir / "logs" / "runtime.json").write_text(
        json.dumps({
            "workflow_console": {
                "latest_stage": {
                    "stage": "requirement",
                    "status": "completed",
                    "adapter_activity": {
                        "operation": "parse_requirement",
                        "provider_identity": {
                            "provider": "local/mock",
                            "adapter": "deterministic",
                            "api_key": "secret-token",
                            "endpoint": r"D:\MyCode\llm2cad\provider.log",
                        },
                    },
                },
                "stages": [
                    {
                        "stage": "requirement",
                        "status": "completed",
                        "adapter_activity": {
                            "operation": "parse_requirement",
                            "provider_identity": {
                                "provider": "local/mock",
                                "adapter": "deterministic",
                                "api_key": "secret-token",
                                "endpoint": r"D:\MyCode\llm2cad\provider.log",
                            },
                        },
                    }
                ],
            }
        }) + "\n",
        encoding="utf-8",
    )

    metadata = WorkflowConsoleBackend(project_root=tmp_path).read_run_metadata_by_id("adapter_metadata")

    assert metadata["status"]["adapter_activity"] == {
        "operation": "parse_requirement",
        "provider_identity": {
            "provider": "local/mock",
            "adapter": "deterministic",
        },
    }
    assert metadata["stage_history"][0]["adapter_activity"] == metadata["status"]["adapter_activity"]
    assert "secret-token" not in json.dumps(metadata["status"]["adapter_activity"])
    assert "D:\\MyCode" not in json.dumps(metadata["stage_history"])


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


def test_backend_reads_revision_artifacts_without_making_them_editable(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run_dir = tmp_path / "outputs" / "revision_run"
    run_dir.mkdir(parents=True)
    (run_dir / "revision_request.json").write_text('{"artifact_type": "revision_request"}\n', encoding="utf-8")
    (run_dir / "patch.json").write_text('{"changes": []}\n', encoding="utf-8")
    (run_dir / "comparison.json").write_text('{"status": "blocked"}\n', encoding="utf-8")
    (run_dir / "revision_report.md").write_text("# Revision Report\n", encoding="utf-8")
    (run_dir / "lineage.json").write_text('{"relationship": "revision_blocked"}\n', encoding="utf-8")

    artifact_names = {item["name"] for item in backend.list_artifacts_by_id("revision_run")}

    assert {
        "revision_request.json",
        "patch.json",
        "comparison.json",
        "revision_report.md",
        "lineage.json",
    }.issubset(artifact_names)
    assert backend.read_artifact_by_id("revision_run", "comparison.json")["content"]["status"] == "blocked"
    with pytest.raises(ValueError, match="artifact is not editable"):
        backend.write_artifact_by_id("revision_run", "patch.json", {"changes": []})


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


def test_workflow_console_routes_list_nested_reviewed_part_runs_without_paths(tmp_path):
    run_dir = tmp_path / "outputs" / "provider_smoke" / "reviewed_part_single_create" / "base"
    run_dir.mkdir(parents=True)
    (run_dir / "assembly_plan.json").write_text(
        json.dumps({"artifact_type": "assembly_plan", "scope": "multi_part", "parts": []}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "model.step").write_text("STEP\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)

    response = dispatch_route(backend, "list_runs")
    serialized = json.dumps(response, sort_keys=True)

    assert response["ok"] is True
    assert [item["run_id"] for item in response["data"]] == ["base"]
    assert str(tmp_path) not in serialized
    assert "provider_smoke" not in serialized
    assert "model.step" in serialized


def test_workflow_console_reviewed_part_summary_extracts_assembly_plan_and_part_result(tmp_path):
    run_dir = tmp_path / "outputs" / "provider_smoke" / "reviewed_part_single_create" / "base"
    child_dir = run_dir / "single_part_base"
    child_dir.mkdir(parents=True)
    (child_dir / "model.step").write_text("STEP\n", encoding="utf-8")
    (child_dir / "model.stl").write_text("STL\n", encoding="utf-8")
    (child_dir / "report.json").write_text(json.dumps({"status": "success"}) + "\n", encoding="utf-8")
    (run_dir / "assembly_plan.json").write_text(
        json.dumps({
            "artifact_type": "assembly_plan",
            "scope": "multi_part",
            "status": "blocked_before_part_generation",
            "parts": [
                {
                    "part_id": "base",
                    "role": "main enclosure component",
                    "generation_strategy": "future_part_pipeline",
                    "part_status": "candidate_for_single_part_generation",
                    "supported_candidate": True,
                    "blocked_reasons": [],
                },
                {
                    "part_id": "lid",
                    "role": "cover component",
                    "generation_strategy": "future_part_pipeline",
                    "part_status": "candidate_for_single_part_generation",
                    "supported_candidate": True,
                    "blocked_reasons": [],
                },
                {
                    "part_id": "screws",
                    "role": "fasteners",
                    "generation_strategy": "reference_only",
                    "part_status": "reference_only",
                    "supported_candidate": False,
                    "blocked_reasons": [],
                },
            ],
            "interfaces": [{"from": "lid", "to": "base", "kind": "screw_fastened"}],
            "fasteners": [{"kind": "screw", "quantity": 4}],
            "diagnostic_codes": ["assembly.plan_created"],
            "quality": {
                "part_status_counts": {
                    "candidate_for_single_part_generation": 2,
                    "reference_only": 1,
                },
                "part_generation_strategy_counts": {
                    "future_part_pipeline": 2,
                    "reference_only": 1,
                },
            },
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "part_create_request.json").write_text(
        json.dumps({
            "part_id": "base",
            "status": "ready_for_review",
            "generation_strategy": "future_part_pipeline",
            "interface_constraints": [{"kind": "screw_fastened"}],
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "part_request_review.json").write_text(
        json.dumps({
            "status": "approved",
            "checks": {
                "has_interface_constraints": True,
                "has_provider_generated_code": False,
            },
            "raw_response": "SECRET_SHOULD_NOT_APPEAR",
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "reviewed_part_handoff.json").write_text(
        json.dumps({
            "part_id": "base",
            "status": "ready_for_single_part_planning",
            "source_part_request": "part_create_request.json",
            "source_review": "part_request_review.json",
            "interface_constraints": [{"kind": "screw_fastened"}],
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "lineage.json").write_text(
        json.dumps({
            "relationship": "reviewed_part_single_create_child",
            "part_id": "base",
            "child_run_id": "single_part_base",
            "assembly_plan_artifact": "assembly_plan.json",
            "part_create_request_artifact": "part_create_request.json",
            "part_request_review_artifact": "part_request_review.json",
            "reviewed_part_handoff_artifact": "reviewed_part_handoff.json",
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "part_result_review.json").write_text(
        json.dumps({
            "artifact_type": "part_result_review",
            "child_run": "single_part_base",
            "part_id": "base",
            "status": "accepted_for_preview",
            "checks": {
                "child_run_created": True,
                "step_created": True,
                "stl_created": True,
                "input_ir_created": True,
                "report_created": True,
                "child_scope": "single_part",
                "single_part_only": True,
                "no_batch_generation": True,
                "no_assembly_generation": True,
                "lineage_preserved": True,
                "interface_constraints_preserved_in_metadata": True,
            },
            "diagnostic_codes": ["part_result.review_created", "part_result.step_created"],
            "raw_provider_response": "SECRET_SHOULD_NOT_APPEAR",
        }) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    metadata = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "base"})["data"]
    reviewed = metadata["reviewed_part_summary"]

    assert reviewed["assembly_plan"]["scope"] == "multi_part"
    assert reviewed["assembly_plan"]["candidate_part_count"] == 2
    assert reviewed["assembly_plan"]["reference_only_count"] == 1
    assert reviewed["assembly_plan"]["parts"][0]["part_id"] == "base"
    assert reviewed["assembly_plan"]["parts"][0]["interfaces_count"] == 1
    assert reviewed["part_request"]["interface_constraint_count"] == 1
    assert reviewed["part_request_review"]["checks"]["has_interface_constraints"] is True
    assert reviewed["reviewed_part_handoff"]["status"] == "ready_for_single_part_planning"
    assert reviewed["lineage"]["child_run_id"] == "single_part_base"
    assert reviewed["part_result_review"]["status"] == "accepted_for_preview"
    assert reviewed["part_result_review"]["checks"]["step_created"] is True
    assert reviewed["part_result_review"]["checks"]["stl_created"] is True
    assert reviewed["part_result_review"]["checks"]["single_part_only"] is True
    assert reviewed["part_result_review"]["checks"]["lineage_preserved"] is True
    assert reviewed["part_result_review"]["checks"]["interface_constraints_preserved_in_metadata"] is True
    assert metadata["child_runs"] == [{
        "run_id": "single_part_base",
        "status": "success",
        "stage": None,
        "artifacts": ["report.json"],
        "downloadables": ["model.step", "model.stl"],
    }]
    serialized = json.dumps(metadata, sort_keys=True)
    assert str(tmp_path) not in serialized
    assert "SECRET_SHOULD_NOT_APPEAR" not in serialized


def test_workflow_console_reviewed_part_parent_run_summarizes_staged_child_artifacts(tmp_path):
    run_dir = tmp_path / "outputs" / "provider_smoke" / "reviewed_part_single_create" / "base"
    (run_dir / "01_design").mkdir(parents=True)
    (run_dir / "02_part_request").mkdir()
    (run_dir / "03_review").mkdir()
    (run_dir / "04_handoff").mkdir()
    (run_dir / "05_single_create" / "single_part_base").mkdir(parents=True)
    (run_dir / "06_part_result_review").mkdir()
    (run_dir / "01_design" / "assembly_plan.json").write_text(
        json.dumps({
            "artifact_type": "assembly_plan",
            "scope": "multi_part",
            "status": "blocked_before_part_generation",
            "parts": [
                {
                    "part_id": "base",
                    "role": "main enclosure component",
                    "generation_strategy": "future_part_pipeline",
                    "part_status": "candidate_for_single_part_generation",
                    "supported_candidate": True,
                },
                {
                    "part_id": "screws",
                    "role": "fasteners",
                    "generation_strategy": "reference_only",
                    "part_status": "reference_only",
                    "supported_candidate": False,
                },
            ],
            "interfaces": [{"from": "base", "to": "screws", "kind": "screw_fastened"}],
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "02_part_request" / "part_create_request.json").write_text(
        json.dumps({"part_id": "base", "status": "ready_for_review", "interface_constraints": [{}]}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "03_review" / "part_request_review.json").write_text(
        json.dumps({"status": "approved", "checks": {"has_interface_constraints": True}}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "04_handoff" / "reviewed_part_handoff.json").write_text(
        json.dumps({"part_id": "base", "status": "ready_for_single_part_planning", "interface_constraints": [{}]})
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "05_single_create" / "lineage.json").write_text(
        json.dumps({"relationship": "reviewed_part_single_create_child", "child_run_id": "single_part_base"})
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "05_single_create" / "single_part_base" / "model.step").write_text("STEP\n", encoding="utf-8")
    (run_dir / "05_single_create" / "single_part_base" / "model.stl").write_text("STL\n", encoding="utf-8")
    (run_dir / "05_single_create" / "single_part_base" / "report.json").write_text(
        json.dumps({"status": "success", "success": True}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "06_part_result_review" / "part_result_review.json").write_text(
        json.dumps({
            "status": "accepted_for_preview",
            "part_id": "base",
            "child_run": "single_part_base",
            "checks": {
                "step_created": True,
                "stl_created": True,
                "single_part_only": True,
                "lineage_preserved": True,
                "interface_constraints_preserved_in_metadata": True,
            },
        }) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    runs = dispatch_route(backend, "list_runs")["data"]
    metadata = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "base"})["data"]
    reviewed = metadata["reviewed_part_summary"]

    assert "base" in {run["run_id"] for run in runs}
    assert reviewed["assembly_plan"]["present"] is True
    assert reviewed["assembly_plan"]["candidate_part_count"] == 1
    assert reviewed["assembly_plan"]["reference_only_count"] == 1
    assert reviewed["part_request"]["status"] == "ready_for_review"
    assert reviewed["part_request_review"]["status"] == "approved"
    assert reviewed["reviewed_part_handoff"]["status"] == "ready_for_single_part_planning"
    assert reviewed["lineage"]["child_run_id"] == "single_part_base"
    assert reviewed["part_result_review"]["status"] == "accepted_for_preview"
    assert metadata["child_runs"] == [{
        "run_id": "single_part_base",
        "status": "success",
        "stage": None,
        "artifacts": ["report.json"],
        "downloadables": ["model.step", "model.stl"],
    }]


def test_workflow_console_reviewed_part_parent_run_shows_blocked_child_without_downloads(tmp_path):
    run_dir = tmp_path / "outputs" / "provider_smoke" / "reviewed_part_single_create" / "lid"
    child_dir = run_dir / "05_single_create" / "single_part_lid"
    child_dir.mkdir(parents=True)
    (run_dir / "06_part_result_review").mkdir()
    (child_dir / "report.json").write_text(
        json.dumps({"status": "blocked_provider_requirement", "success": False}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "06_part_result_review" / "part_result_review.json").write_text(
        json.dumps({
            "status": "blocked_missing_step",
            "child_run": "single_part_lid",
            "checks": {"step_created": False, "stl_created": False},
        }) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    metadata = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "lid"})["data"]

    assert metadata["child_runs"] == [{
        "run_id": "single_part_lid",
        "status": "blocked_provider_requirement",
        "stage": None,
        "artifacts": ["report.json"],
        "downloadables": [],
    }]


def test_workflow_console_reviewed_part_missing_artifacts_are_graceful(tmp_path):
    run_dir = tmp_path / "outputs" / "partial_reviewed_part"
    run_dir.mkdir(parents=True)
    (run_dir / "assembly_plan.json").write_text(
        json.dumps({
            "artifact_type": "assembly_plan",
            "scope": "multi_part",
            "status": "blocked_before_part_generation",
            "parts": [{"part_id": "base", "supported_candidate": True}],
        }) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    metadata = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "partial_reviewed_part"})["data"]

    assert metadata["reviewed_part_summary"]["assembly_plan"]["present"] is True
    assert metadata["reviewed_part_summary"]["part_result_review"]["present"] is False
    assert metadata["child_runs"] == []


def test_workflow_console_report_summary_sanitizes_raw_messages_secrets_and_paths(tmp_path):
    run_dir = tmp_path / "outputs" / "privacy_summary"
    run_dir.mkdir(parents=True)
    (run_dir / "report.json").write_text(
        json.dumps({
            "status": "failed",
            "success": False,
            "warnings": [
                {"code": "safe.warning", "message": "api_key=SECRET_SHOULD_NOT_APPEAR"},
                {"code": "path.warning", "message": str(tmp_path / "secret.txt")},
            ],
            "errors": [{"code": "safe.error", "message": "ordinary sanitized message"}],
            "raw_provider_messages": ["SECRET_SHOULD_NOT_APPEAR"],
        }) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    metadata = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "privacy_summary"})["data"]
    serialized = json.dumps(metadata["report_summary"], sort_keys=True)

    assert "safe.warning" in serialized
    assert "safe.error" in serialized
    assert "ordinary sanitized message" in serialized
    assert "SECRET_SHOULD_NOT_APPEAR" not in serialized
    assert str(tmp_path) not in serialized


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
        "Provider",
        "provider-select",
        "provider-model",
        "provider-timeout",
        "provider-retries",
        "test-provider",
        "testProviderConnection",
        "provider-check",
        "configureProvider",
        'api("read_provider_config"',
        'api("configure_provider"',
        'api("test_provider_connection"',
        "stage_history",
        "gate_history",
        "stageHistoryByStage",
        "stageHistorySummary",
        "adapterActivityLine",
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
