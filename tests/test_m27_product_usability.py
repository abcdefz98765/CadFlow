from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ai_native_cad.agents.episode import AgentAction, StopReason
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.credential_discovery import resolve_provider_credential
from ai_native_cad.workflow_console.i18n import copy as i18n_copy
from ai_native_cad.workflow_console.nicegui_app import (
    _mark_provider_draft_changed,
    _save_verify_provider_draft_async,
    _test_provider_draft_async,
    build_console_page_data,
)
from ai_native_cad.workflow_console.product_usability import build_recovery_projection
from ai_native_cad.workflow_console.workflow_page_view_model import (
    build_workbench_overview_view_model,
    build_workflow_page_view_model,
)


class HealthyDeepSeekAdapter:
    def __init__(self, *, model: str = "deepseek-chat", api_key: str | None = None, **_: object) -> None:
        self.provider_identity = {
            "provider": "deepseek",
            "model": model,
            "network": "https",
        }
        self.received_api_key = api_key

    def parse_requirement(self, prompt: str, context: dict[str, object]) -> dict[str, object]:
        assert prompt
        assert context["workflow_stage"] == "provider_check"
        return {
            "part_type": "spacer",
            "dimensions": {"outer_diameter": 12, "inner_diameter": 6, "thickness": 4},
        }


class AskThenStopAdapter:
    provider_identity = {"provider": "deepseek", "model": "deepseek-chat", "network": "https"}

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def choose_design_action(self, *, state: dict[str, object], skill_manifest: dict[str, object]) -> AgentAction:
        self.calls.append(state)
        if len(self.calls) == 1:
            return AgentAction(
                action="ask_user",
                questions=({
                    "field": "servo_hole_spacing_mm",
                    "question": "What is the servo mounting-hole spacing?",
                    "reason": "The spacing controls the ear geometry.",
                },),
                reason="One interface dimension is missing.",
            )
        return AgentAction(
            action="stop",
            stop_reason=StopReason.INSUFFICIENT_CONTEXT,
            reason="Controlled resume fixture stop.",
        )


def _backend(tmp_path: Path) -> tuple[WorkflowConsoleBackend, list[HealthyDeepSeekAdapter]]:
    adapters: list[HealthyDeepSeekAdapter] = []

    def factory(provider: str, *, model: str | None = None, api_key: str | None = None, **kwargs: object) -> HealthyDeepSeekAdapter:
        assert provider == "deepseek"
        adapter = HealthyDeepSeekAdapter(model=model or "deepseek-chat", api_key=api_key, **kwargs)
        adapters.append(adapter)
        return adapter

    backend = WorkflowConsoleBackend(project_root=tmp_path, provider_adapter_factory=factory)
    backend.create_workspace()
    return backend, adapters


def test_top_level_product_labels_are_bilingual_and_internal_ids_remain_compatible():
    assert i18n_copy("en", "home") == "Home"
    assert i18n_copy("zh", "home") == "首页"
    assert i18n_copy("en", "works") == "Works"
    assert i18n_copy("zh", "works") == "设计项目"
    assert i18n_copy("en", "settings") == "Settings"
    assert i18n_copy("zh", "settings") == "设置"
    assert i18n_copy("en", "show_developer_content") == "Show developer content"
    assert i18n_copy("zh", "credential_source") == "凭据来源"
    source = Path("src/ai_native_cad/workflow_console/nicegui_app.py").read_text(encoding="utf-8")
    assert '("config", "settings"' in source
    assert "首页" in source and "开始产品示例" in source and "保存并验证" in source


def test_provider_draft_test_is_non_persisting_and_survives_refresh(tmp_path):
    backend, adapters = _backend(tmp_path)
    state = {
        "provider_draft": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "test-session-secret",
            "base_url": "",
            "timeout_seconds": 15,
            "max_retries": 1,
            "advancement_mode": "manual_confirm",
        },
        "provider_draft_status": "not_tested",
    }
    asyncio.run(_test_provider_draft_async(backend, state, lambda: None, "en"))

    assert state["provider_draft_status"] == "connected"
    assert state["provider_draft"]["api_key"] == "test-session-secret"
    assert backend.read_workspace_config()["provider"] == "local/mock"
    assert adapters[-1].received_api_key == "test-session-secret"
    assert _mark_provider_draft_changed(state, "model", "deepseek-chat-next") is True
    assert state["provider_draft_status"] == "changed_since_test"


def test_save_verify_persists_only_safe_settings_and_home_uses_verified_readiness(tmp_path, monkeypatch):
    backend, _ = _backend(tmp_path)
    secret = "never-write-this-secret"
    state = {
        "provider_draft": {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": secret,
            "base_url": "",
            "timeout_seconds": 15,
            "max_retries": 1,
            "advancement_mode": "manual_confirm",
        },
        "provider_draft_status": "not_tested",
    }
    asyncio.run(_save_verify_provider_draft_async(backend, state, lambda: None, "en"))

    assert state["provider_draft_status"] == "connected"
    assert backend.read_provider_readiness()["ready"] is True
    page = build_console_page_data(backend, active_page="workspace", language="en")
    assert page["home"]["environment"]["provider"]["ready"] is True
    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    assert secret not in persisted
    assert "api_key" not in json.dumps(backend.read_workspace_config()).lower()
    assert backend.read_workspace_config()["provider_verification"]["status"] == "connected"

    monkeypatch.setenv("DEEPSEEK_API_KEY", "restart-session-secret")
    restarted = WorkflowConsoleBackend(
        project_root=tmp_path,
        provider_adapter_factory=backend._provider_adapter_factory,
        restore_saved_provider=True,
    )
    assert restarted.read_provider_readiness()["ready"] is True
    assert restarted.read_provider_config()["provider_identity"]["provider"] == "deepseek"


def test_credential_discovery_precedence_and_public_readiness_never_expose_value(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "DEEPSEEK_API_KEY=project-env-secret\nUNRELATED_SECRET=ignore-me\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "process-secret")
    process = resolve_provider_credential("deepseek", project_root=tmp_path)
    session = resolve_provider_credential("deepseek", project_root=tmp_path, session_value="session-secret")
    project = resolve_provider_credential("deepseek", project_root=tmp_path, environ={})
    assert (process.source, process.value) == ("process_environment", "process-secret")
    assert (session.source, session.value) == ("session", "session-secret")
    assert (project.source, project.value) == ("project_env", "project-env-secret")

    backend, _ = _backend(tmp_path)
    backend.create_workspace()
    backend.save_and_verify_provider("deepseek", model="deepseek-chat")
    readiness = backend.read_provider_readiness()
    assert readiness["credential_source"] == "process_environment"
    assert readiness["credential_variable"] == "DEEPSEEK_API_KEY"
    assert readiness["credential_value_exposed"] is False
    assert "process-secret" not in json.dumps(readiness)
    public_source = backend.read_provider_credential_source("deepseek")
    assert public_source == {
        "available": True,
        "source": "process_environment",
        "variable": "DEEPSEEK_API_KEY",
        "secret_exposed": False,
    }
    assert "process-secret" not in json.dumps(public_source)


def test_live_product_example_starts_at_real_beginning_and_uses_agent_projection(tmp_path):
    backend, _ = _backend(tmp_path)
    started = backend.start_live_product_example()
    manifest = backend._read_work_manifest(started["work_id"])

    assert started["preloaded_design"] is False
    assert started["preloaded_geometry"] is False
    assert started["reviewable"] is False
    assert started["accepted"] is False
    assert manifest["artifact_references"] == []
    assert manifest["accepted_part_results"] == {}
    assert manifest["part_jobs"] == []
    overview = build_workbench_overview_view_model(backend, started["work_id"], language="en")
    workflow = build_workflow_page_view_model(backend, started["work_id"], language="en")
    assert overview["user_input"]["original_request"].startswith("Create a compact single-piece")
    assert overview["agent_design"]["evidence_status"] == "insufficient"
    assert overview["current_result"] is None
    assert workflow["projection_mode"] == "agent_first"
    assert [phase["id"] for phase in workflow["phase_groups"]] == [
        "intent", "design", "build_evaluate", "accept_deliver"
    ]
    assert [node["kind"] for node in workflow["nodes"]] == ["request", "work_design"]
    assert workflow["workflow_graph"]["topology"] == "dynamic_work_graph"
    assert workflow["workflow_graph"]["compatibility_mode"] is False
    assert workflow["nodes"][0]["status"] == "completed"
    assert workflow["nodes"][1]["status"] == "not_started"


def test_clarification_is_persisted_and_same_work_can_resume(tmp_path):
    backend, _ = _backend(tmp_path)
    started = backend.start_live_product_example()
    adapter = AskThenStopAdapter()
    backend.stage_runner.agent_adapter = adapter
    first = backend.run_work_design_episode(
        started["work_id"],
        request_id="ask_fixture",
    )
    assert first["episode"]["stop_reason"] == "user_input_required"
    overview = build_workbench_overview_view_model(backend, started["work_id"], language="en")
    recovery = overview["recovery"]
    assert recovery["resolution_owner"] == "user"
    assert recovery["recommended_action"]["key"] == "answer_question"
    question = recovery["questions"][0]
    waiting_workflow = build_workflow_page_view_model(
        backend, started["work_id"], language="en"
    )
    waiting_question = next(
        node
        for node in waiting_workflow["nodes"]
        if node["detail"]["type"] == "clarification"
    )
    assert waiting_question["interaction"]["primary_action"]["key"] == "answer_question"
    assert waiting_question["interaction"]["requires_user_action"] is True
    assert waiting_question["user_state"] == "needs_you"
    assert waiting_workflow["current_attention"][0]["node_id"] == waiting_question["id"]
    assert waiting_workflow["current_attention"][0]["state"] == "needs_you"
    backend.answer_work_design_question(
        started["work_id"],
        run_id=first["work_design"]["run_id"],
        answer_id="spacing_answer",
        question_artifact_id=recovery["question_artifact_id"],
        field=question["field"],
        question=question["question"],
        answer="27.5 mm",
    )
    resumed = backend.run_work_design_episode(
        started["work_id"],
        request_id="resume_fixture",
        objective="Continue with servo_hole_spacing_mm = 27.5 mm",
    )
    assert resumed["episode"]["stop_reason"] == "insufficient_context"
    assert "27.5 mm" in adapter.calls[-1]["context_envelope"]["objective"]["summary"]
    manifest = backend._read_work_manifest(started["work_id"])
    assert any(item["trust_role"] == "accepted_input" for item in manifest["artifact_references"])
    assert manifest["accepted_part_results"] == {}
    overview = build_workbench_overview_view_model(backend, started["work_id"], language="en")
    output = overview["agent_output"]
    assert output["has_external_responses"] is True
    assert any(item["kind"] == "user_answer" and item["summary"] == "27.5 mm" for item in output["items"])
    assert any(item.get("stop_reason") == "insufficient_context" for item in output["items"])
    assert overview["recovery"]["technical_reason"] == "insufficient_context"
    assert overview["recovery"]["last_agent_action"] == "stop"
    assert overview["recovery"]["recommended_action"]["key"] == "modify_request"
    assert overview["recovery"]["summary"] == "Controlled resume fixture stop."
    workflow = build_workflow_page_view_model(
        backend, started["work_id"], language="en"
    )
    nodes = {item["id"]: item for item in workflow["nodes"]}
    edges = workflow["edges"]
    question_id = next(node_id for node_id, node in nodes.items() if node["kind"] == "decision" and node["detail"]["type"] == "clarification")
    answer_id = next(node_id for node_id, node in nodes.items() if node["kind"] == "decision" and node["detail"]["type"] == "answer")
    resumed_id = next(node_id for node_id, node in nodes.items() if node["kind"] == "recovery" and node["detail"]["stop_reason"] == "insufficient_context")
    assert nodes[question_id]["group"] == nodes[answer_id]["group"]
    assert nodes[question_id]["detail"]["answered"] is True
    assert nodes[question_id]["interaction"]["primary_action"] is None
    assert "historical" in nodes[question_id]["interaction"]["unavailable_reason"].lower()
    assert any(edge["source"] == question_id and edge["target"] == answer_id and edge["type"] == "answered" for edge in edges)
    assert any(edge["source"] == answer_id and edge["target"] == resumed_id and edge["type"] == "resumed" for edge in edges)


def test_home_product_examples_are_explicitly_distinct(tmp_path):
    backend, _ = _backend(tmp_path)
    page = build_console_page_data(backend, active_page="workspace", language="en")
    examples = page["home"]["product_examples"]
    assert [item["key"] for item in examples] == ["live_agent", "completed_golden"]
    assert "variable" in examples[0]["badge"].lower()
    assert "no provider" in examples[1]["badge"].lower()
    assert examples[0]["requirements"] != examples[1]["requirements"]


def test_recovery_owner_mappings_do_not_offer_meaningless_retry():
    class FakeBackend:
        def __init__(self, stop_reason: str, codes: list[str] | None = None) -> None:
            self.stop_reason = stop_reason
            self.codes = codes or []

        def read_provider_readiness(self) -> dict[str, object]:
            return {"ready": True}

        def read_work_artifact_reference(self, work_id: str, artifact_id: str) -> dict[str, object]:
            if artifact_id == "route":
                return {"content": {"episode": {"status": "safely_blocked", "stop_reason": self.stop_reason}}}
            return {"content": {"codes": self.codes}}

    entity = {"metadata": {"product_entry": "new_design"}}
    base_refs = [{"artifact_id": "route", "checkpoint": "product_design_routing"}]
    unsupported = build_recovery_projection(FakeBackend("unsupported_capability"), "w", entity, base_refs, language="en")
    transient = build_recovery_projection(FakeBackend("provider_failure"), "w", entity, base_refs, language="en")
    environment = build_recovery_projection(
        FakeBackend("policy_blocked", ["sandbox_unavailable"]),
        "w",
        entity,
        [*base_refs, {"artifact_id": "execution", "checkpoint": "execution_observation"}],
        language="en",
    )
    assert unsupported["resolution_owner"] == "unsupported"
    assert unsupported["recommended_action"]["key"] == "modify_request"
    assert unsupported["retryable"] is False
    assert transient["resolution_owner"] == "cadflow" and transient["retryable"] is True
    assert environment["resolution_owner"] == "environment"
    assert environment["recommended_action"]["key"] == "check_environment"
    assert environment["retryable"] is False
