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
from ai_native_cad.workflow_console.artifact_display import (
    artifact_display_category,
    artifact_visible_by_default,
    filter_artifacts_for_display,
)
from ai_native_cad.workflow_console.review_surface import build_workflow_review_surface
from ai_native_cad.workflow_console.work_index import build_work_index


def _does_not_contain_keys(value, keys):
    if isinstance(value, dict):
        return all(key not in keys and _does_not_contain_keys(item, keys) for key, item in value.items())
    if isinstance(value, list):
        return all(_does_not_contain_keys(item, keys) for item in value)
    return True


def test_canonical_work_never_invokes_legacy_product_inference(tmp_path, monkeypatch):
    backend = WorkflowConsoleBackend(
        project_root=tmp_path, workspace_root=tmp_path / "workspace"
    )
    backend.create_workspace()
    backend.create_work("Canonical", "Design one bracket.", work_id="canonical")
    backend.create_work_requirement_run(
        "canonical", "Design one bracket.", run_id="canonical_root"
    )
    run_dir = backend._work_runs_root("canonical") / "canonical_root"
    (run_dir / "assembly_plan.json").write_text(
        json.dumps({"parts": [{"part_id": "inferred_part"}]}) + "\n",
        encoding="utf-8",
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("canonical read invoked compatibility inference")

    monkeypatch.setattr(
        "ai_native_cad.workflow_console.work_index.project_legacy_product_references",
        forbidden,
    )
    backend.invalidate_work_index()
    detail = backend.get_work_detail("canonical")

    assert detail["entity_state"]["state_authority"] == "canonical"
    assert detail["parts"] == []
    assert detail["available_actions"] == []
    assert detail["summary"]["active_lineage"]["lineage_inferred"] is False
    assert {node["id"] for node in detail["nodes"]} == {"request", "work:design"}


def test_developer_works_use_isolated_storage_and_explicit_catalog_visibility(tmp_path):
    backend = WorkflowConsoleBackend(
        project_root=tmp_path, workspace_root=tmp_path / "workspace"
    )
    backend.create_workspace()
    backend.create_work(
        "Browser fixture",
        work_id="browser_fixture",
        metadata={"work_classification": "developer_fixture"},
    )
    backend.create_work(
        "Product example",
        work_id="product_example",
        metadata={"work_classification": "product_example"},
    )

    isolated = tmp_path / "workspace" / ".internal" / "dev-works" / "browser_fixture"
    assert (isolated / "work_manifest.json").is_file()
    assert not (tmp_path / "workspace" / "works" / "browser_fixture").exists()
    assert (tmp_path / "workspace" / "works" / "product_example" / "work_manifest.json").is_file()
    assert not (tmp_path / "workspace" / ".internal" / "dev-works" / "product_example").exists()
    assert backend.get_work_detail("browser_fixture")["summary"]["work_id"] == "browser_fixture"
    assert [item["summary"]["work_id"] for item in build_work_index(backend)["works"]] == [
        "product_example"
    ]
    debug_index = build_work_index(backend, include_debug=True)
    assert {item["summary"]["work_id"] for item in debug_index["works"]} == {
        "browser_fixture",
        "product_example",
    }


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


def test_workflow_cockpit_shows_successful_generic_upper_link_evidence(tmp_path):
    run_dir = tmp_path / "outputs" / "upper_link_review"
    child_dir = run_dir / "single_part_upper_link"
    child_dir.mkdir(parents=True)
    artifacts = {
        "assembly_plan.json": {
            "artifact_type": "assembly_plan",
            "scope": "multi_part",
            "selected_part_id": "upper_link",
            "parts": [{"part_id": "upper_link", "role": "second arm link", "part_brief": "selected printable link", "part_status": "candidate_for_single_part_generation", "supported_candidate": True}],
        },
        "part_create_request.json": {"part_id": "upper_link", "status": "ready_for_review"},
        "reviewed_part_handoff.json": {"part_id": "upper_link", "status": "ready_for_single_part_planning"},
        "cad_ir_draft.json": {
            "part_type": "link_like_part",
            "geometry_family": "elongated_plate_with_end_holes",
            "source_part_id": "upper_link",
            "source": {"normalization": {"source_part_id": "upper_link", "part_type": "link_like_part", "geometry_family": "elongated_plate_with_end_holes", "reason": "generic family mapping"}},
        },
        "lineage.json": {"relationship": "reviewed_part_single_create_child", "part_id": "upper_link", "child_run_id": "single_part_upper_link", "assembly_plan_artifact": "assembly_plan.json"},
        "report.json": {"status": "success", "success": True, "part_id": "upper_link", "concept_scope": "single_generic_concept_part", "assembly_generated": False},
    }
    for name, value in artifacts.items():
        (run_dir / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
    (child_dir / "input_ir.json").write_text(json.dumps(artifacts["cad_ir_draft.json"]) + "\n", encoding="utf-8")
    (child_dir / "report.json").write_text(json.dumps({"status": "success", "success": True}) + "\n", encoding="utf-8")
    (child_dir / "model.step").write_text("STEP\n", encoding="utf-8")
    (child_dir / "model.stl").write_text("STL\n", encoding="utf-8")

    backend = WorkflowConsoleBackend(project_root=tmp_path)
    run = backend.read_run_metadata_by_id("upper_link_review", root=tmp_path / "outputs")
    surface = build_workflow_review_surface(backend, "upper_link_review", run, root=str(tmp_path / "outputs"), selected_stage_id="part_modeling")

    assert surface["task_state"]["status"] == "completed"
    assert surface["task_state"]["selected_part_id"] == "upper_link"
    assert surface["decision_panel"]["scope"] == "single_generic_concept_part"
    assert surface["decision_panel"]["assembly_generated"] is False
    assert "generic link-like concept part" in surface["decision_panel"]["decision"]
    assert surface["candidate_part_detail"]["part_id"] == "upper_link"
    assert surface["candidate_part_detail"]["part_type"] == "link_like_part"
    assert surface["candidate_part_detail"]["geometry_family"] == "elongated_plate_with_end_holes"
    evidence = {item["artifact"] for item in surface["evidence_chain"]}
    assert {"cad_ir_draft.json", "input_ir.json", "model.step", "model.stl"} <= evidence


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
        "create_workspace",
        "load_workspace",
        "create_work",
        "open_product_golden_example",
        "start_live_product_example",
        "create_product_design",
        "create_golden_example",
        "create_work_requirement_run",
        "create_work_part_runs",
        "create_work_part_attempt",
        "run_work_design_episode",
        "answer_work_design_question",
        "run_work_part_design_episode",
        "answer_work_part_design_question",
        "accept_work_reviewable_result",
        "revise_work_reviewable_result",
        "create_run_by_id",
        "get_work_detail",
        "list_works",
        "list_runs",
        "read_provider_config",
        "read_workspace",
        "read_workspace_config",
        "read_run_metadata_by_id",
        "run_stage_by_id",
        "run_revision_by_id",
        "test_provider_connection",
        "save_and_verify_provider",
        "read_product_readiness",
        "write_workspace_config",
        "list_artifacts_by_id",
        "read_artifact_by_id",
        "write_artifact_by_id",
        "list_downloadables_by_id",
        "record_gate_decision_by_id",
        "apply_requirement_clarification_by_id",
        "WorkflowConsoleActions.create_part_request",
        "WorkflowConsoleActions.review_part_request",
        "WorkflowConsoleActions.create_reviewed_handoff",
        "WorkflowConsoleActions.create_reviewed_part",
        "WorkflowConsoleActions.review_part_result",
        "WorkflowConsoleActions.save_stage_review",
        "WorkflowConsoleActions.create_workflow_review",
        "WorkflowConsoleActions.run_rework",
    }

    assert {spec.backend_operation for spec in ROUTE_SPECS} == expected_operations
    assert all(
        spec.backend_operation.endswith("_by_id")
        or spec.backend_operation in {
            "list_runs",
            "list_works",
            "read_workspace",
            "create_workspace",
            "load_workspace",
                "create_work",
                "open_product_golden_example",
                "start_live_product_example",
                "create_product_design",
                "create_golden_example",
            "create_work_requirement_run",
            "create_work_part_runs",
            "create_work_part_attempt",
            "run_work_design_episode",
            "answer_work_design_question",
            "run_work_part_design_episode",
            "answer_work_part_design_question",
            "accept_work_reviewable_result",
            "revise_work_reviewable_result",
            "get_work_detail",
            "read_workspace_config",
            "write_workspace_config",
            "read_provider_config",
            "configure_provider",
            "test_provider_connection",
            "save_and_verify_provider",
            "read_product_readiness",
            "WorkflowConsoleActions.create_part_request",
            "WorkflowConsoleActions.review_part_request",
            "WorkflowConsoleActions.create_reviewed_handoff",
            "WorkflowConsoleActions.create_reviewed_part",
            "WorkflowConsoleActions.review_part_result",
            "WorkflowConsoleActions.save_stage_review",
            "WorkflowConsoleActions.create_workflow_review",
            "WorkflowConsoleActions.run_rework",
        }
        for spec in ROUTE_SPECS
    )
    assert "run_dir" not in {spec.backend_operation for spec in ROUTE_SPECS}


def test_workspace_create_and_config_are_file_backed_without_secrets(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    workspace = dispatch_route(
        backend,
        "create_workspace",
        body={"path": "workspace_demo", "name": "Demo Workspace", "advancement_mode": "manual_confirm"},
    )
    config = dispatch_route(
        backend,
        "write_workspace_config",
        body={"provider": "local", "model": "mock-model", "timeout_seconds": 30, "max_retries": 2, "advancement_mode": "auto_advance"},
    )
    secret = dispatch_route(backend, "write_workspace_config", body={"provider": "local", "api_key": "secret"})

    assert workspace["ok"] is True
    assert workspace["data"]["workspace"]["relative_path"] == "workspace_demo"
    assert (tmp_path / "workspace_demo" / "workspace.json").exists()
    assert (tmp_path / "workspace_demo" / "config.json").exists()
    assert config["ok"] is True
    assert config["data"]["config"]["advancement_mode"] == "auto_advance"
    assert secret["ok"] is False
    assert workspace["data"]["workspace"]["display_path"] == "workspace_demo"
    assert str(tmp_path.resolve()) not in workspace["data"]["workspace"]["display_path"]
    assert _does_not_contain_text(config["data"], ["api_key", "secret"])


def test_workspace_can_be_external_and_load_requires_initialized_marker(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path / "repo")
    external = tmp_path / "external_workspace"
    uninitialized = tmp_path / "plain_directory"
    uninitialized.mkdir()

    created = dispatch_route(
        backend,
        "create_workspace",
        body={"path": str(external), "name": "External Workspace"},
    )
    loaded = dispatch_route(backend, "load_workspace", body={"path": str(external)})
    plain = dispatch_route(backend, "load_workspace", body={"path": str(uninitialized)})

    assert created["ok"] is True
    assert created["data"]["workspace"]["is_external"] is True
    assert created["data"]["workspace"]["display_path"] == "external_workspace"
    assert str(tmp_path.resolve()) not in created["data"]["workspace"]["display_path"]
    assert (external / "workspace.json").exists()
    assert loaded["ok"] is True
    assert plain["ok"] is False
    assert plain["status_code"] == 404
    assert backend.read_workspace()["display_path"] == "external_workspace"


def test_workspace_can_seed_static_example_works_under_external_root(tmp_path, monkeypatch):
    backend = WorkflowConsoleBackend(project_root=tmp_path / "repo")
    external = tmp_path / "example_workspace"
    monkeypatch.setattr(backend.stage_runner, "create_run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("examples must not create runs")))
    monkeypatch.setattr(backend.stage_runner, "run_stage", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("examples must not run stages")))

    created = dispatch_route(
        backend,
        "create_workspace",
        body={"path": str(external), "name": "Example Workspace", "include_examples": True},
    )
    normal_works = dispatch_route(backend, "list_works")
    works = dispatch_route(backend, "list_works", query={"show_developer": True})
    detail = dispatch_route(backend, "read_work", path_params={"work_id": "reviewed_one_part_enclosure_base"})

    assert created["ok"] is True
    assert created["data"]["examples"]["seeded_work_ids"] == [
        "single_part_mounting_plate",
        "multi_part_enclosure_planning",
        "reviewed_one_part_enclosure_base",
    ]
    assert created["data"]["workspace"]["work_count"] == 0
    assert normal_works["data"]["works"] == []
    developer_works = external / ".internal" / "dev-works"
    assert (developer_works / "single_part_mounting_plate" / "work_manifest.json").exists()
    assert (developer_works / "multi_part_enclosure_planning" / "runs" / "multi_part_enclosure_planning_root" / "01_design" / "assembly_plan.json").exists()
    assert (developer_works / "reviewed_one_part_enclosure_base" / "runs" / "single_part_enclosure_base_result" / "model.step").exists()
    assert "facet normal" in (developer_works / "reviewed_one_part_enclosure_base" / "runs" / "single_part_enclosure_base_result" / "model.stl").read_text(encoding="utf-8")
    assert not (external / "works" / "single_part_mounting_plate").exists()
    assert {work["work_id"] for work in works["data"]["works"]} == {
        "single_part_mounting_plate",
        "multi_part_enclosure_planning",
        "reviewed_one_part_enclosure_base",
    }
    assert {part["part_id"] for part in detail["data"]["parts"]} >= {"base", "lid", "screws"}
    assert not detail["data"]["products"]["downloadables"]
    assert any(item["name"] == "model.step" for item in detail["data"]["products"]["reviewable_outputs"])


def test_workspace_example_seed_rejects_existing_work_without_overwrite(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path / "repo")
    external = tmp_path / "example_workspace"
    first = dispatch_route(backend, "create_workspace", body={"path": str(external), "include_examples": True})
    marker = external / ".internal" / "dev-works" / "single_part_mounting_plate" / "work_manifest.json"
    before = marker.read_text(encoding="utf-8")

    second = dispatch_route(backend, "create_workspace", body={"path": str(external), "include_examples": True})

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["status_code"] == 409
    assert marker.read_text(encoding="utf-8") == before


def test_workspace_example_seed_rejects_same_id_in_normal_storage_without_overwrite(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path / "repo")
    external = tmp_path / "example_workspace"
    dispatch_route(backend, "create_workspace", body={"path": str(external)})
    backend.create_work(
        "Existing product example",
        work_id="single_part_mounting_plate",
        metadata={"work_classification": "product_example"},
    )
    marker = external / "works" / "single_part_mounting_plate" / "work_manifest.json"
    before = marker.read_text(encoding="utf-8")

    seeded = dispatch_route(backend, "create_workspace", body={"path": str(external), "include_examples": True})

    assert seeded["ok"] is False
    assert seeded["status_code"] == 409
    assert marker.read_text(encoding="utf-8") == before
    assert not (external / ".internal" / "dev-works" / "single_part_mounting_plate").exists()


def test_external_workspace_work_and_runs_are_written_outside_repo(tmp_path):
    repo = tmp_path / "repo"
    external = tmp_path / "external_workspace"
    backend = WorkflowConsoleBackend(project_root=repo)
    dispatch_route(backend, "create_workspace", body={"path": str(external)})
    dispatch_route(backend, "create_work", body={"work_id": "fixture", "title": "Fixture"})

    response = dispatch_route(
        backend,
        "create_work_requirement_run",
        path_params={"work_id": "fixture"},
        body={"prompt": "Create a fixture with two clamp blocks."},
    )

    assert response["ok"] is True
    assert (external / "works" / "fixture" / "work_manifest.json").exists()
    assert (external / "works" / "fixture" / "runs" / "fixture_root" / "prompt.txt").exists()
    assert not (repo / "workspace" / "works" / "fixture").exists()


def test_work_requirement_run_is_created_under_workspace_and_bound_to_work(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_workspace", body={"path": "workspace"})
    dispatch_route(backend, "create_work", body={"work_id": "enclosure", "title": "Enclosure"})

    response = dispatch_route(
        backend,
        "create_work_requirement_run",
        path_params={"work_id": "enclosure"},
        body={"prompt": "Design an electronics enclosure with base and lid."},
    )
    manifest = json.loads((tmp_path / "workspace" / "works" / "enclosure" / "work_manifest.json").read_text(encoding="utf-8"))
    detail = dispatch_route(backend, "read_work", path_params={"work_id": "enclosure"})

    assert response["ok"] is True
    assert response["data"]["run"]["run_id"] == "enclosure_root"
    assert (tmp_path / "workspace" / "works" / "enclosure" / "runs" / "enclosure_root" / "prompt.txt").exists()
    assert manifest["root_run_id"] == "enclosure_root"
    assert manifest["requirement"]["confirmation_required"] is True
    assert "enclosure_root" in {row["run_id"] for row in detail["data"]["run_history"]}
    assert _does_not_contain_absolute_paths(response["data"])


def test_work_part_runs_are_created_after_manual_split_confirmation(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_workspace", body={"path": "workspace"})
    dispatch_route(backend, "create_work", body={"work_id": "enclosure", "title": "Enclosure"})
    dispatch_route(
        backend,
        "create_work_requirement_run",
        path_params={"work_id": "enclosure"},
        body={"prompt": "Design an electronics enclosure with base and lid."},
    )
    _write_json = lambda path, value: (path.parent.mkdir(parents=True, exist_ok=True), path.write_text(json.dumps(value) + "\n", encoding="utf-8"))
    _write_json(
            tmp_path / "workspace" / "works" / "enclosure" / "runs" / "enclosure_root" / "01_design" / "assembly_plan.json",
        {
            "parts": [
                {"part_id": "base", "role": "housing", "supported_candidate": True, "part_status": "candidate_for_single_part_generation"},
                {"part_id": "lid", "role": "cover", "supported_candidate": True, "part_status": "candidate_for_single_part_generation"},
                {"part_id": "screws", "role": "fastener", "part_status": "reference_only"},
            ]
        },
    )

    response = dispatch_route(backend, "create_work_part_runs", path_params={"work_id": "enclosure"})
    detail = dispatch_route(backend, "read_work", path_params={"work_id": "enclosure"})

    assert response["ok"] is True
    assert {run["run_id"] for run in response["data"]["created_runs"]} == {"enclosure_base", "enclosure_lid"}
    assert (tmp_path / "workspace" / "works" / "enclosure" / "runs" / "enclosure_base" / "prompt.txt").exists()
    assert {part["part_id"] for part in detail["data"]["parts"]} >= {"base", "lid", "screws"}


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
    assert ROUTE_SPECS_BY_NAME["action_create_workflow_review"].path == "/api/actions/workflow-review"
    assert ROUTE_SPECS_BY_NAME["action_run_rework"].path == "/api/actions/rework"
    assert ROUTE_SPECS_BY_NAME["apply_requirement_clarification"].method == "POST"
    assert ROUTE_SPECS_BY_NAME["apply_requirement_clarification"].path == "/api/actions/requirement-clarification"


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
        "action_create_workflow_review",
        "action_run_rework",
    }
    assert all("batch" not in spec.path for spec in action_specs)
    assert all("assembly-generation" not in spec.path for spec in action_specs)
    assert "batch_generation" not in ACTION_NAMES
    assert "assembly_generation" not in ACTION_NAMES


def test_workflow_console_artifact_display_policy_classifies_known_artifacts():
    assert artifact_display_category("workflow_review.md") == "human_facing"
    assert artifact_display_category("workflow_review.json") == "human_facing"
    assert artifact_display_category("stage_review.json") == "human_facing"
    assert artifact_display_category("requirement.json") == "review_debug"
    assert artifact_display_category("agent_trace.json") == "review_debug"
    assert artifact_display_category("input_ir.json") == "internal_debug"
    assert artifact_visible_by_default("workflow_review.md") is True
    assert artifact_visible_by_default("requirement.json") is False


def test_workflow_console_artifact_display_policy_filters_by_explicit_mode():
    artifacts = [
        {"name": "workflow_review.md"},
        {"name": "requirement.json"},
        {"name": "input_ir.json"},
    ]

    default = filter_artifacts_for_display(artifacts)
    debug = filter_artifacts_for_display(artifacts, show_debug=True)
    internal = filter_artifacts_for_display(artifacts, show_internal=True)

    assert [item["name"] for item in default] == ["workflow_review.md"]
    assert [item["name"] for item in debug] == ["workflow_review.md", "requirement.json"]
    assert [item["name"] for item in internal] == ["workflow_review.md", "requirement.json", "input_ir.json"]
    assert all(".." not in item["name"] for item in internal)


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


def test_workflow_console_rework_rejects_missing_stage_review(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "missing_rework_review"}, body={"prompt": "Make a bracket."})

    response = dispatch_route(backend, "action_run_rework", body={"run_id": "missing_rework_review"})

    assert response["ok"] is False
    assert response["status_code"] == 404
    assert "stage_review.json" in response["error"]["message"]


def test_workflow_console_rework_rejects_approved_stage_review(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "approved_rework"}, body={"prompt": "Make a bracket."})
    dispatch_route(
        backend,
        "action_save_stage_review",
        body={"run_id": "approved_rework", "stage": "assembly_plan", "review_status": "approved"},
    )

    response = dispatch_route(backend, "action_run_rework", body={"run_id": "approved_rework"})

    assert response["ok"] is False
    assert response["status_code"] == 400
    assert "needs_revision" in response["error"]["message"]


def test_workflow_console_rework_rejects_unknown_target_and_traversal(tmp_path):
    run_dir = tmp_path / "outputs" / "unknown_rework"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a bracket.\n", encoding="utf-8")
    (run_dir / "stage_review.json").write_text(
        json.dumps({
            "schema_version": 1,
            "stage": "assembly_plan",
            "review_status": "needs_revision",
            "target_rework_stage": "unknown_target",
        }) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    unknown = dispatch_route(backend, "action_run_rework", body={"run_id": "unknown_rework"})
    traversal = dispatch_route(backend, "action_run_rework", body={"run_id": "../unknown_rework"})

    assert unknown["ok"] is False
    assert unknown["status_code"] == 400
    assert "rework target stage" in unknown["error"]["message"]
    assert traversal["ok"] is False
    assert traversal["status_code"] == 400


def test_workflow_console_rework_unsupported_target_writes_blocked_decision(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "blocked_rework"}, body={"prompt": "Make an enclosure."})
    dispatch_route(
        backend,
        "action_save_stage_review",
        body={
            "run_id": "blocked_rework",
            "stage": "assembly_plan",
            "review_status": "needs_revision",
            "target_rework_stage": "assembly_plan",
            "requested_changes": ["Treat lid as a flat cover candidate"],
        },
    )

    response = dispatch_route(backend, "action_run_rework", body={"run_id": "blocked_rework"})
    decision = json.loads((tmp_path / "outputs" / "blocked_rework" / "rework_decision.json").read_text(encoding="utf-8"))
    metadata = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "blocked_rework"})["data"]

    assert response["ok"] is True
    assert decision["execution_status"] == "blocked_unsupported_target"
    assert decision["child_run_id"] is None
    assert decision["diagnostic_codes"] == ["rework.unsupported_target_stage"]
    assert metadata["rework_decision_summary"]["execution_status"] == "blocked_unsupported_target"
    assert metadata["rework_decision_summary"]["requested_changes_preview"] == ["Treat lid as a flat cover candidate"]


def test_workflow_console_blocked_stage_review_preserves_rework_intent(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "blocked_intent"}, body={"prompt": "Make an enclosure."})

    response = dispatch_route(
        backend,
        "action_save_stage_review",
        body={
            "run_id": "blocked_intent",
            "stage": "assembly_plan",
            "review_status": "blocked",
            "target_rework_stage": "workflow_review",
            "user_notes": "Planning is blocked but review intent should be retained.",
        },
    )
    artifact = json.loads((tmp_path / "outputs" / "blocked_intent" / "stage_review.json").read_text(encoding="utf-8"))

    assert response["ok"] is True
    assert response["data"]["summary"]["review_status"] == "blocked"
    assert response["data"]["summary"]["target_rework_stage"] == "workflow_review"
    assert artifact["target_rework_stage"] == "workflow_review"


def test_workflow_console_rework_workflow_review_creates_child_without_overwriting_parent(tmp_path):
    run_dir = tmp_path / "outputs" / "workflow_review_rework"
    _write_reviewed_part_run(run_dir)
    original_step = (run_dir / "model.step").read_text(encoding="utf-8")
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(
        backend,
        "action_save_stage_review",
        body={
            "run_id": "workflow_review_rework",
            "stage": "assembly_plan",
            "review_status": "needs_revision",
            "target_rework_stage": "workflow_review",
            "requested_changes": ["Refresh the review with user rework notes."],
        },
    )

    response = dispatch_route(backend, "action_run_rework", body={"run_id": "workflow_review_rework"})
    decision = json.loads((run_dir / "rework_decision.json").read_text(encoding="utf-8"))
    child_dir = run_dir / decision["child_run_id"]
    child_review = json.loads((child_dir / "workflow_review.json").read_text(encoding="utf-8"))
    child_decision = json.loads((child_dir / "rework_decision.json").read_text(encoding="utf-8"))

    assert response["ok"] is True
    assert response["data"]["summary"]["execution_status"] == "completed"
    assert decision["execution_status"] == "completed"
    assert decision["child_run_id"] == "rework_workflow_review_1"
    assert (run_dir / "model.step").read_text(encoding="utf-8") == original_step
    assert not (run_dir / "workflow_review.json").exists()
    assert (child_dir / "stage_review.json").exists()
    assert (child_dir / "lineage.json").exists()
    assert child_decision == decision
    assert any("User-triggered rework" in item for item in child_review["summary"])
    assert any("rework_decision.json" in item for item in child_review["recommended_next_actions"])


def test_workflow_console_rework_makes_no_provider_or_cad_pipeline_call(tmp_path, monkeypatch):
    run_dir = tmp_path / "outputs" / "local_rework"
    _write_reviewed_part_run(run_dir)
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(
        backend,
        "action_save_stage_review",
        body={
            "run_id": "local_rework",
                "stage": "assembly_plan",
                "review_status": "needs_revision",
                "target_rework_stage": "workflow_review",
                "requested_changes": ["Review the selected candidate before continuing."],
            },
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("provider or CAD pipeline should not be called by rework MVP")

    monkeypatch.setattr(backend.stage_runner.agent_adapter, "parse_requirement", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_assembly_part_request_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_part_request_review_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_part_result_review_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_reviewed_part_handoff_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_reviewed_part_single_create_pipeline", fail_if_called)

    response = dispatch_route(backend, "action_run_rework", body={"run_id": "local_rework"})

    assert response["ok"] is True
    assert response["data"]["summary"]["execution_status"] == "completed"


def test_workflow_console_rework_summary_is_sanitized(tmp_path):
    run_dir = tmp_path / "outputs" / "rework_privacy"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a bracket.\n", encoding="utf-8")
    (run_dir / "stage_review.json").write_text(
        json.dumps({
            "schema_version": 1,
            "stage": "assembly_plan",
            "review_status": "needs_revision",
            "target_rework_stage": "assembly_plan",
            "requested_changes": [str(tmp_path / "secret_path"), "API_KEY=secret", "Use a flat cover."],
        }) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    response = dispatch_route(backend, "action_run_rework", body={"run_id": "rework_privacy"})
    metadata = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "rework_privacy"})["data"]
    serialized = json.dumps({"response": response, "metadata": metadata}, sort_keys=True)

    assert response["ok"] is True
    assert _does_not_contain_absolute_paths(response)
    assert str(tmp_path) not in serialized
    assert "API_KEY" not in serialized
    assert metadata["rework_decision_summary"]["requested_changes_preview"] == ["Use a flat cover."]


def _write_reviewed_part_run(run_dir: Path, *, accepted: bool = True) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "model.step").write_text("STEP\n", encoding="utf-8")
    if accepted:
        (run_dir / "model.stl").write_text("STL\n", encoding="utf-8")
    (run_dir / "assembly_plan.json").write_text(
        json.dumps({
            "artifact_type": "assembly_plan",
            "scope": "multi_part",
            "status": "blocked_before_part_generation" if accepted else "blocked_before_part_generation",
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
                    "role": "cover",
                    "generation_strategy": "future_part_pipeline",
                    "part_status": "blocked" if not accepted else "candidate_for_single_part_generation",
                    "supported_candidate": accepted,
                    "blocked_reasons": [{"code": "unsupported_lid_cover"}] if not accepted else [],
                },
                {
                    "part_id": "screws",
                    "role": "fasteners",
                    "generation_strategy": "reference_only",
                    "part_status": "reference_only",
                    "supported_candidate": False,
                },
            ],
            "interfaces": [{"from": "base", "to": "lid", "kind": "screw_fastened"}],
            "diagnostic_codes": ["assembly.plan_created"],
        }) + "\n",
        encoding="utf-8",
    )
    (run_dir / "part_result_review.json").write_text(
        json.dumps({
            "artifact_type": "part_result_review",
            "status": "accepted_for_preview" if accepted else "blocked_missing_step",
            "part_id": "base" if accepted else "lid",
            "checks": {
                "step_created": accepted,
                "stl_created": accepted,
                "single_part_only": True,
                "lineage_preserved": True,
                "interface_constraints_preserved_in_metadata": True,
            },
            "diagnostic_codes": (
                ["part_result.step_created", "part_result.single_part_scope_preserved"]
                if accepted
                else ["part_result.blocked_missing_step", "part_request.unsupported_part_family"]
            ),
        }) + "\n",
        encoding="utf-8",
    )


def test_workflow_console_workflow_review_generation_is_deterministic_from_fake_artifacts(tmp_path):
    run_dir = tmp_path / "outputs" / "accepted_review"
    _write_reviewed_part_run(run_dir, accepted=True)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    first = dispatch_route(backend, "action_create_workflow_review", body={"run_id": "accepted_review"})
    first_json = json.loads((run_dir / "workflow_review.json").read_text(encoding="utf-8"))
    second = dispatch_route(backend, "action_create_workflow_review", body={"run_id": "accepted_review"})
    second_json = json.loads((run_dir / "workflow_review.json").read_text(encoding="utf-8"))

    assert first["ok"] is True
    assert second["ok"] is True
    assert first_json == second_json
    assert (run_dir / "workflow_review.md").exists()
    assert first_json["overall_status"] == "accepted_for_preview"
    assert first_json["readiness_score"] >= 80
    assert "No geometric fit validation with related assembly parts." in first_json["risks"]
    assert _does_not_contain_absolute_paths(first)


def test_workflow_console_workflow_review_blocked_run_is_low_readiness(tmp_path):
    run_dir = tmp_path / "outputs" / "blocked_lid"
    _write_reviewed_part_run(run_dir, accepted=False)
    (run_dir / "model.step").unlink()
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    response = dispatch_route(backend, "action_create_workflow_review", body={"run_id": "blocked_lid"})
    review = json.loads((run_dir / "workflow_review.json").read_text(encoding="utf-8"))

    assert response["ok"] is True
    assert review["overall_status"] == "blocked"
    assert review["readiness_score"] < 40
    assert review["risk_level"] == "high"
    assert "part_request.unsupported_part_family" in review["key_diagnostics"]
    assert any("Primary STEP output is missing" in risk for risk in review["risks"])


def test_workflow_console_workflow_review_rejects_invalid_run_ids_and_traversal(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    dispatch_route(backend, "create_run", path_params={"run_id": "safe_workflow_review"}, body={"prompt": "Make a bracket."})

    missing = dispatch_route(backend, "action_create_workflow_review", body={"run_id": "missing_review"})
    traversal = dispatch_route(backend, "action_create_workflow_review", body={"run_id": "../safe_workflow_review"})

    assert missing["ok"] is False
    assert missing["status_code"] == 404
    assert traversal["ok"] is False
    assert traversal["status_code"] == 400


def test_workflow_console_workflow_review_makes_no_provider_or_cad_pipeline_call(tmp_path, monkeypatch):
    run_dir = tmp_path / "outputs" / "local_report"
    _write_reviewed_part_run(run_dir, accepted=True)
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("workflow review must not call provider or CAD pipeline")

    backend.stage_runner.agent_adapter.parse_requirement = fail_if_called
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_assembly_part_request_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_part_request_review_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_part_result_review_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_reviewed_part_handoff_pipeline", fail_if_called)
    monkeypatch.setattr("ai_native_cad.workflow_console.actions.run_reviewed_part_single_create_pipeline", fail_if_called)

    response = dispatch_route(backend, "action_create_workflow_review", body={"run_id": "local_report"})

    assert response["ok"] is True
    assert response["data"]["summary"]["overall_status"] == "accepted_for_preview"


def test_workflow_console_workflow_review_summary_is_sanitized(tmp_path):
    run_dir = tmp_path / "outputs" / "review_privacy"
    _write_reviewed_part_run(run_dir, accepted=True)
    (run_dir / "stage_review.json").write_text(
        json.dumps({"schema_version": 1, "stage": "requirement", "review_status": "approved", "user_notes": "api_key=SECRET"}) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    dispatch_route(backend, "action_create_workflow_review", body={"run_id": "review_privacy"})
    metadata = dispatch_route(backend, "read_run_metadata", path_params={"run_id": "review_privacy"})["data"]
    serialized = json.dumps(metadata, sort_keys=True)

    assert metadata["workflow_review_summary"]["present"] is True
    assert metadata["workflow_review_summary"]["overall_status"] == "accepted_for_preview"
    assert metadata["workflow_review_summary"]["recommended_next_action_count"] >= 1
    assert "workflow_review.json" in {item["name"] for item in metadata["artifacts"]}
    assert "SECRET" not in serialized
    assert str(tmp_path) not in serialized


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
    (tmp_path / "outputs" / "dispatch_edit" / "requirement_v2.json").write_text(
        json.dumps(requirement) + "\n",
        encoding="utf-8",
    )

    written = dispatch_route(
        backend,
        "write_artifact",
        path_params={"run_id": "dispatch_edit", "artifact": "requirement_v2.json"},
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
    parent_dir = Path.cwd() / "workspace" / ".internal" / "runs" / parent_id
    parent_dir.mkdir(parents=True)
    (Path.cwd() / "workspace" / ".internal" / "runs" / f"{parent_id}_revision_1").mkdir()
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
    assert (Path.cwd() / "workspace" / ".internal" / "runs" / f"{parent_id}_revision_2" / "revision_request.json").exists()


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

    assert recorded["ok"] is False
    assert "secret-token" not in json.dumps(runtime["data"])
    private_runtime = backend.read_artifact_by_id("gate_payload", "logs/runtime.json")
    assert "secret-token" not in json.dumps(private_runtime)


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
    (tmp_path / "outputs" / "content_path" / "requirement_v2.json").write_text(
        json.dumps(requirement) + "\n",
        encoding="utf-8",
    )
    backend.write_artifact_by_id("content_path", "requirement_v2.json", requirement)

    response = dispatch_route(
        backend,
        "read_artifact",
        path_params={"run_id": "content_path", "artifact": "requirement_v2.json"},
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


def test_backend_list_runs_respects_default_limit_and_uses_summaries(tmp_path, monkeypatch):
    for index in range(55):
        run_dir = tmp_path / "outputs" / f"run_{index:02d}"
        run_dir.mkdir(parents=True)
        (run_dir / "prompt.txt").write_text(f"Make run {index}.\n", encoding="utf-8")
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    def fail_if_full_metadata_loaded(run_dir):
        raise AssertionError(f"full metadata should be lazy-loaded: {run_dir}")

    monkeypatch.setattr(backend, "read_run_metadata", fail_if_full_metadata_loaded)

    runs = backend.list_runs()

    assert len(runs) == 50
    assert all("run_dir" not in run and "root" not in run for run in runs)


def test_backend_list_runs_respects_explicit_limit_offset_and_pagination(tmp_path):
    for index in range(5):
        run_dir = tmp_path / "outputs" / f"paged_{index}"
        run_dir.mkdir(parents=True)
        (run_dir / "prompt.txt").write_text(f"Make paged {index}.\n", encoding="utf-8")
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    page = backend.list_runs_page(limit=2, offset=2)

    assert len(page["runs"]) == 2
    assert page["pagination"] == {
        "limit": 2,
        "offset": 2,
        "returned": 2,
        "total": 5,
        "has_previous": True,
        "has_next": True,
    }


def test_backend_list_runs_searches_safe_relative_run_names(tmp_path):
    for name in ("alpha_bracket", "beta_spacer", "alpha_mount"):
        run_dir = tmp_path / "outputs" / name
        run_dir.mkdir(parents=True)
        (run_dir / "prompt.txt").write_text(f"Make {name}.\n", encoding="utf-8")
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    page = backend.list_runs_page(limit=10, offset=0, filters={"search": "alpha"})
    serialized = json.dumps(page, sort_keys=True)

    assert {run["run_id"] for run in page["runs"]} == {"alpha_bracket", "alpha_mount"}
    assert str(tmp_path) not in serialized


def test_backend_run_summary_includes_review_and_model_availability(tmp_path):
    run_dir = tmp_path / "outputs" / "summary_run"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text("Make a reviewed part.\n", encoding="utf-8")
    (run_dir / "model.step").write_text("STEP\n", encoding="utf-8")
    (run_dir / "workflow_review.json").write_text(
        json.dumps({
            "overall_status": "accepted_for_preview",
            "readiness_score": 90,
            "summary": ["Ready."],
        }) + "\n",
        encoding="utf-8",
    )
    backend = WorkflowConsoleBackend(project_root=tmp_path)

    summary = backend.get_run_summary("summary_run")

    assert summary["workflow_review_summary"]["present"] is True
    assert summary["workflow_review_summary"]["overall_status"] == "accepted_for_preview"
    assert summary["has_step"] is True
    assert summary["has_stl"] is False


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


def test_requirement_clarification_blocks_then_allows_planning(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    prompt = "Design a desktop 2 DOF robotic arm with a gripper, servo-ready joints, and 3D printable parts."
    backend.create_run_by_id("arm_clarification", prompt)
    requirement_result = backend.run_stage_by_id("arm_clarification", "requirement")

    blocked = backend.run_stage_by_id("arm_clarification", "planning")

    assert requirement_result["result"]["flow_decision"]["action"] == "ask_user"
    assert blocked["result"]["stage_status"] == "blocked"
    assert blocked["result"]["flow_decision"]["to_stage"] == "requirement"

    applied = backend.apply_requirement_clarification_by_id(
        "arm_clarification",
        answers=[
            {"question_id": "q1", "field": "arm_reach_mm", "question": "Reach?", "answer": "220 mm"},
            {"question_id": "q2", "field": "payload_target_g", "question": "Payload?", "answer": "80 g"},
            {"question_id": "q3", "field": "servo_reference_size_mm", "question": "Servo?", "answer": "40 x 20 x 40"},
            {"question_id": "q4", "field": "gripper_opening_mm", "question": "Opening?", "answer": "35 mm"},
        ],
        notes="Desktop demo only.",
    )
    planning = backend.run_stage_by_id("arm_clarification", "planning")
    part_request = dispatch_route(
        backend,
        "action_part_request",
        body={"run_id": "arm_clarification", "part_id": "upper_link"},
    )
    runtime = backend.read_artifact_by_id("arm_clarification", "logs/runtime.json")["content"]["workflow_console"]
    clarification = backend.read_artifact_by_id("arm_clarification", "requirement_clarification.json")["content"]
    requirement_v2 = backend.read_artifact_by_id("arm_clarification", "requirement_v2.json")["content"]
    assembly_plan = backend.read_artifact_by_id("arm_clarification", "assembly_plan.json")["content"]

    assert applied["requirement"]["clarification_applied"] is True
    assert clarification["answers"][0]["field"] == "arm_reach_mm"
    assert requirement_v2["dimensions"]["arm_reach_mm"] == 220.0
    assert requirement_v2["features"]["payload_mass_g"] == 80.0
    assert requirement_v2["features"]["servo_envelope"] == "40 x 20 x 40"
    assert requirement_v2["dimensions"]["gripper_opening_mm"] == 35.0
    assert requirement_v2["missing_information"] == []
    assert requirement_v2["lineage"]["created_by"] == "apply_requirement_clarification"
    assert runtime["clarification_applied_count"] == 1
    assert planning["result"]["stage_status"] == "blocked"
    assert planning["result"]["planning_artifact"]["route"]["selected"] == "assembly_loop"
    assert planning["result"]["planning_artifact"]["source"]["requirement_part_type"] == "robotic_arm"
    assert planning["result"]["planning_artifact"]["assembly_planning"]["primary_candidate_part"] == "upper_link"
    assert {part["part_id"] for part in assembly_plan["parts"]} >= {
        "base",
        "lower_link",
        "upper_link",
        "shoulder_servo_bracket",
        "elbow_servo_bracket",
        "gripper_mount",
        "reference_servo",
        "reference_gripper",
    }
    assert assembly_plan["selected_part_id"] == "upper_link"
    assert assembly_plan["status"] == "blocked_before_part_generation"
    assert part_request["ok"] is True
    assert part_request["data"]["summary"]["status"] == "ready_for_review"
    assert "part_create_request.json" in {item["name"] for item in part_request["data"]["run"]["artifacts"]}


def test_requirement_clarification_route_sanitizes_public_response(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("safe_clarification", "Design a desktop 2 DOF robotic arm with a gripper and servo.")
    dispatch_route(backend, "run_stage", path_params={"run_id": "safe_clarification", "stage": "requirement"})

    rejected = dispatch_route(
        backend,
        "apply_requirement_clarification",
        body={
            "run_id": "safe_clarification",
            "answers": [{"field": "arm_reach_mm", "question": "Reach?", "answer": "220 mm", "api_key": "secret-token"}],
        },
    )
    response = dispatch_route(
        backend,
        "apply_requirement_clarification",
        body={
            "run_id": "safe_clarification",
            "answers": [{"field": "arm_reach_mm", "question": "Reach?", "answer": "220 mm"}],
            "notes": "Use a compact desktop footprint.",
        },
    )

    assert rejected["ok"] is False
    assert "secrets" in rejected["error"]["message"]
    assert response["ok"] is True
    assert _does_not_contain_keys(response["data"], {"path", "run_dir", "root", "output_dir", "payload"})
    assert _does_not_contain_absolute_paths(response["data"])
    assert "secret-token" not in json.dumps(response["data"])


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

    with pytest.raises(ValueError, match="must not include secrets"):
        backend.record_gate_decision_by_id(
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
    runtime = backend.read_artifact_by_id("payload_summary", "logs/runtime.json")
    assert "secret-token" not in json.dumps(runtime)


def test_backend_rejects_invalid_gate_decision_inputs(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("decision_run", "Make a spacer.")

    with pytest.raises(ValueError, match="gate decision stage"):
        backend.record_gate_decision_by_id("decision_run", stage="shell", action="approve")
    with pytest.raises(ValueError, match="gate decision action"):
        backend.record_gate_decision_by_id("decision_run", stage="requirement", action="execute")
    with pytest.raises(ValueError, match="payload must be a dictionary"):
        backend.record_gate_decision_by_id("decision_run", stage="requirement", action="override", payload="bad")


def test_backend_writes_editable_requirement_override_by_id(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")
    requirement = {
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
        "requirement_status": {"complete_for_generation": True},
    }
    run_dir = tmp_path / "workspace" / ".internal" / "runs" / "edit_run"
    (run_dir / "requirement_v2.json").write_text(json.dumps(requirement) + "\n", encoding="utf-8")

    edited = {**requirement, "part_family": "washer"}
    written = backend.write_artifact_by_id("edit_run", "requirement_v2.json", edited, edit_reason="User selected washer family.")
    runtime = backend.read_artifact_by_id("edit_run", "logs/runtime.json")["content"]["workflow_console"]

    assert json.loads((run_dir / "requirement_v2.json").read_text(encoding="utf-8")).get("part_family") is None
    assert written["artifact"]["content"]["part_family"] == "washer"
    assert written["edit"]["artifact"] == "requirement_v2.json"
    assert written["edit"]["source"] == "user_override"
    assert (run_dir / "edits" / "requirement_v2.edit_001.json").exists()
    assert (run_dir / "edits" / "active" / "requirement_v2.json").exists()
    assert written["run"]["status"]["artifact_edit"]["artifact"] == "requirement_v2.json"
    assert runtime["latest_artifact_edit"] == written["edit"]
    assert runtime["artifact_edit_count"] == 1
    assert "requirement_v2.json" in EDITABLE_ARTIFACTS


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
    (tmp_path / "workspace" / ".internal" / "runs" / "edit_run" / "input_ir.json").write_text(json.dumps(input_ir) + "\n", encoding="utf-8")

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

    with pytest.raises(ValueError, match="invalid artifact path|artifact is not editable"):
        backend.write_artifact_by_id("edit_run", "../requirement_v2.json", {"part_type": "spacer"})


def test_backend_rejects_non_object_artifact_write(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")

    with pytest.raises(ValueError, match="must be a JSON object"):
        backend.write_artifact_by_id("edit_run", "requirement_v2.json", ["bad"])


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
    (tmp_path / "workspace" / ".internal" / "runs" / "edit_run" / "input_ir.json").write_text(json.dumps({**invalid_ir, "dimensions": {"outer_diameter": 12, "inner_diameter": 6, "thickness": 2}, "part_name": "valid", "check_level": "L0"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="failed CAD IR validation"):
        backend.write_artifact_by_id("edit_run", "input_ir.json", invalid_ir)


def test_backend_rejects_invalid_planning_artifact_write(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")
    (tmp_path / "workspace" / ".internal" / "runs" / "edit_run" / "planning_artifact.json").write_text(
        json.dumps({"artifact_type": "planning", "route": {}, "selected_parts": [], "flow_gate_status": {}}) + "\n",
        encoding="utf-8",
    )

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


def test_backend_artifact_override_whitelist_rejects_generated_and_debug_artifacts(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")
    editable = {
        "requirement_v2.json",
        "planning_artifact.json",
        "assembly_plan.json",
        "part_create_request.json",
        "02_part_request/part_create_request.json",
        "part_request_review.json",
        "03_review/part_request_review.json",
        "reviewed_part_handoff.json",
        "04_handoff/reviewed_part_handoff.json",
        "cad_ir_draft.json",
        "05_single_create/cad_ir_draft.json",
        "input_ir.json",
        "stage_review.json",
    }

    assert editable <= EDITABLE_ARTIFACTS
    for artifact in ("prompt.txt", "model.py", "model.step", "report.json", "agent_trace.json", "logs/runtime.json"):
        with pytest.raises(ValueError, match="artifact is not editable"):
            backend.write_artifact_by_id("edit_run", artifact, {"status": "bad"})


def test_backend_rejects_secret_and_executable_artifact_overrides(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("edit_run", "Make a spacer.")
    source = {
        "part_type": "spacer",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6, "thickness": 2},
    }
    (tmp_path / "workspace" / ".internal" / "runs" / "edit_run" / "requirement_v2.json").write_text(json.dumps(source) + "\n", encoding="utf-8")

    for payload in (
        {**source, "api_key": "SECRET"},
        {**source, "python_code": "print('no')"},
        {**source, "cadquery_code": "import cadquery"},
        {**source, "shell_command": "del *"},
        {**source, "provider_response": {"raw": "payload"}},
        {**source, "notes": "bearer token should not be here"},
    ):
        with pytest.raises(ValueError, match="forbidden field|must not contain secrets"):
            backend.write_artifact_by_id("edit_run", "requirement_v2.json", payload)

    assert not (tmp_path / "workspace" / ".internal" / "runs" / "edit_run" / "edits").exists()


def test_backend_planning_uses_requirement_override_before_requirement_v2(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("override_plan", "Make a mounting plate.")
    run_dir = tmp_path / "workspace" / ".internal" / "runs" / "override_plan"
    original = {
        "part_type": "mounting_plate",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {},
        "requirement_status": {"flow_decision": {"action": "proceed"}},
    }
    override = {
        "part_type": "spacer",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6, "thickness": 3},
        "features": {},
        "requirement_status": {"flow_decision": {"action": "proceed"}},
    }
    (run_dir / "requirement.json").write_text(json.dumps(original) + "\n", encoding="utf-8")
    (run_dir / "requirement_v2.json").write_text(json.dumps(original) + "\n", encoding="utf-8")
    backend.write_artifact_by_id("override_plan", "requirement_v2.json", override)

    result = backend.run_stage_by_id("override_plan", "planning")
    runtime = backend.read_artifact_by_id("override_plan", "logs/runtime.json")["content"]["workflow_console"]

    selected = result["result"]["planning_artifact"]["selected_parts"][0]
    assert selected["resolved_decisions"]["part_type"] == "spacer"
    assert result["result"]["planning_artifact"]["route"]["selected"] == "single_part"
    assert runtime["latest_override_usage"]["artifact"] == "requirement_v2.json"
    assert runtime["latest_override_usage"]["stage"] == "planning"


def test_actions_create_part_request_uses_assembly_plan_override(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("override_assembly", "Make an assembly.")
    run_dir = tmp_path / "workspace" / ".internal" / "runs" / "override_assembly"
    original = {
        "artifact_type": "assembly_plan",
        "parts": [{"part_id": "base", "supported_candidate": True, "part_status": "candidate_for_single_part_generation"}],
    }
    override = {
        "artifact_type": "assembly_plan",
        "parts": [{"part_id": "lid", "supported_candidate": True, "part_status": "candidate_for_single_part_generation"}],
    }
    (run_dir / "assembly_plan.json").write_text(json.dumps(original) + "\n", encoding="utf-8")
    backend.write_artifact_by_id("override_assembly", "assembly_plan.json", override)

    result = WorkflowConsoleActions(backend).create_part_request("override_assembly")
    request = json.loads((run_dir / "02_part_request" / "part_create_request.json").read_text(encoding="utf-8"))

    assert result["summary"]["status"] == "ready_for_review"
    assert request["part_id"] == "lid"


def test_select_candidate_part_writes_validated_override_and_preserves_work_results(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work("Candidate selection", work_id="candidate_selection")
    backend.create_work_requirement_run("candidate_selection", "Choose one assembly candidate.", run_id="candidate_selection_root")
    run_dir = tmp_path / "workspace" / "works" / "candidate_selection" / "runs" / "candidate_selection_root"
    original = {
        "artifact_type": "assembly_plan",
        "selected_part_id": "upper_link",
        "primary_candidate_part": "upper_link",
        "parts": [
            {"part_id": "upper_link", "supported_candidate": True, "part_status": "candidate_for_single_part_generation"},
            {"part_id": "lower_link", "supported_candidate": True, "part_status": "candidate_for_single_part_generation"},
            {"part_id": "reference_servo", "supported_candidate": False, "part_status": "reference_only", "generation_strategy": "reference_only"},
        ],
        "interfaces": [],
    }
    (run_dir / "assembly_plan.json").write_text(json.dumps(original) + "\n", encoding="utf-8")
    manifest = backend._read_work_manifest("candidate_selection")
    manifest["accepted_part_results"] = {"upper_link": {"child_run_id": "old_child", "review_id": "review_001", "status": "approved"}}
    backend._write_work_manifest("candidate_selection", manifest)

    result = WorkflowConsoleActions(backend).select_candidate_part(
        "candidate_selection_root", work_id="candidate_selection", part_id="lower_link"
    )

    assert result["selected_candidate"] == "lower_link"
    assert result["next_action"] == "Create Part Request"
    assert set(result["downstream_stages_affected"]) >= {"part_request", "part_modeling", "workflow_review"}
    assert json.loads((run_dir / "assembly_plan.json").read_text(encoding="utf-8"))["selected_part_id"] == "upper_link"
    assert backend.read_artifact_by_id("candidate_selection_root", "assembly_plan.json", root=backend._work_runs_root("candidate_selection"))["content"]["selected_part_id"] == "lower_link"
    assert (run_dir / result["metadata_artifact"]).exists()
    manifest = backend._read_work_manifest("candidate_selection")
    assert manifest["accepted_part_results"]["upper_link"]["child_run_id"] == "old_child"
    assert manifest["candidate_selection"]["selected_candidate"] == "lower_link"


def test_select_candidate_part_rejects_reference_and_current_candidate_without_mutation(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work("Candidate selection", work_id="candidate_selection_noop")
    backend.create_work_requirement_run("candidate_selection_noop", "Choose one assembly candidate.", run_id="candidate_selection_noop_root")
    run_dir = tmp_path / "workspace" / "works" / "candidate_selection_noop" / "runs" / "candidate_selection_noop_root"
    (run_dir / "assembly_plan.json").write_text(json.dumps({
        "artifact_type": "assembly_plan", "selected_part_id": "upper_link", "parts": [
            {"part_id": "upper_link", "supported_candidate": True, "part_status": "candidate_for_single_part_generation"},
            {"part_id": "reference_servo", "supported_candidate": False, "part_status": "reference_only", "generation_strategy": "reference_only"},
        ], "interfaces": [],
    }) + "\n", encoding="utf-8")
    actions = WorkflowConsoleActions(backend)

    no_op = actions.select_candidate_part("candidate_selection_noop_root", work_id="candidate_selection_noop", part_id="upper_link")
    assert no_op["no_op"] is True
    assert backend.active_override_path(run_dir, "assembly_plan.json") is None
    with pytest.raises(ValueError, match="reference-only"):
        actions.select_candidate_part("candidate_selection_noop_root", work_id="candidate_selection_noop", part_id="reference_servo")
    assert backend.active_override_path(run_dir, "assembly_plan.json") is None


def test_invalid_cad_ir_draft_override_is_rejected_before_part_modeling(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_run_by_id("bad_cad_ir", "Make one part.")
    run_dir = tmp_path / "workspace" / ".internal" / "runs" / "bad_cad_ir"
    handoff = {"part_id": "upper_link", "status": "ready_for_single_part_planning"}
    valid_ir = {
        "part_type": "spacer",
        "part_name": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6, "thickness": 3},
        "features": {},
        "outputs": ["step"],
        "check_level": "L0",
    }
    invalid_ir = {**valid_ir, "dimensions": {"outer_diameter": 12}}
    (run_dir / "04_handoff").mkdir()
    (run_dir / "04_handoff" / "reviewed_part_handoff.json").write_text(json.dumps(handoff) + "\n", encoding="utf-8")
    (run_dir / "05_single_create").mkdir()
    (run_dir / "05_single_create" / "cad_ir_draft.json").write_text(json.dumps(valid_ir) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="failed CAD IR validation"):
        backend.write_artifact_by_id("bad_cad_ir", "cad_ir_draft.json", invalid_ir)

    assert backend.active_override_path(run_dir, "cad_ir_draft.json") is None
    assert not (run_dir / "edits").exists()


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
    assert [item["run_id"] for item in response["data"]["runs"]] == ["base"]
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

    runs = dispatch_route(backend, "list_runs")["data"]["runs"]
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
