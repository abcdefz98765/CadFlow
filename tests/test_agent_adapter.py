import json
import os
from pathlib import Path

import pytest

from ai_native_cad.agents import (
    AgentAdapter,
    DesignPlannerFakeAgentAdapter,
    DeterministicAgentAdapter,
    JsonContractAgentAdapter,
    JsonProviderEndpoint,
    JsonContractProviderConfig,
    JsonContractProviderError,
    OpenAICompatibleJsonContractClient,
    OpenAIResponsesJsonContractClient,
    make_json_contract_adapter_from_env,
)
from ai_native_cad.agents.provider_context import knowledge_summary_for, provider_messages_for
from ai_native_cad.agents.validation import validate_adapter_result, validate_requirement_draft
import ai_native_cad.cadquery.executor as cadquery_executor
from ai_native_cad.pipeline import (
    create_reviewed_part_handoff,
    review_part_result,
    review_part_create_request,
    run_assembly_part_request_pipeline,
    run_part_request_review_pipeline,
    run_part_result_review_pipeline,
    run_reviewed_part_agent_ir_create_pipeline,
    run_reviewed_part_handoff_pipeline,
    run_reviewed_part_single_create_pipeline,
    run_provider_create_pipeline,
    run_provider_normalized_create_pipeline,
    run_provider_normalized_design_create_pipeline,
)
import ai_native_cad.pipeline.runner as pipeline_runner
from ai_native_cad.workflow_console.stage_runner import StageRunner


class InvalidRequirementAdapter(DeterministicAgentAdapter):
    def parse_requirement(self, prompt, context=None):
        return {"part_type": "", "dimensions": []}


class InvalidPlanningAdapter(DeterministicAgentAdapter):
    def create_plan(self, requirement, context=None):
        return {
            "artifact_type": "plan",
            "route": {},
            "selected_parts": [],
            "flow_gate_status": {},
        }


class SecretiveAdapter(DeterministicAgentAdapter):
    @property
    def provider_identity(self):
        return {
            "provider": "local/mock",
            "adapter": "secretive-test",
            "api_key": "should-not-be-recorded",
            "token": "should-not-be-recorded",
        }


class FakeJsonContractClient:
    def __init__(self, response, provider_identity=None):
        self.response = response
        self.requests = []
        self.provider_identity = provider_identity or {
            "provider": "fake/json",
            "model": "fake-requirement-v1",
        }

    def generate_json_contract(self, request):
        self.requests.append(request)
        return self.response


class OperationFakeJsonContractClient:
    def __init__(self, responses, provider_identity=None):
        self.responses = responses
        self.requests = []
        self.provider_identity = provider_identity or {
            "provider": "fake/json",
            "model": "fake-contract-v1",
        }

    def generate_json_contract(self, request):
        self.requests.append(request)
        return self.responses[request["operation"]]


class FailingJsonContractClient:
    provider_identity = {"provider": "fake/json", "api_key": "secret"}

    def __init__(self, exc):
        self.exc = exc
        self.requests = []

    def generate_json_contract(self, request):
        self.requests.append(request)
        raise self.exc


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class RecordingUrlOpen:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, http_request, timeout=None):
        self.calls.append({
            "url": http_request.full_url,
            "timeout": timeout,
            "method": http_request.get_method(),
            "headers": dict(http_request.header_items()),
            "body": json.loads(http_request.data.decode("utf-8")),
        })
        return FakeHTTPResponse(self.payload)


def _valid_requirement_json():
    return json.dumps({
        "part_type": "spacer",
        "dimensions": {
            "outer_diameter": 12,
            "inner_diameter": 6.5,
            "thickness": 20,
        },
        "features": {},
        "assumptions": [],
        "missing_information": [],
        "follow_up_questions": [],
        "follow_up_requests": [],
        "requirement_status": {
            "complete_for_generation": True,
            "needs_user_input": False,
            "blocking_fields": [],
            "missing_count": 0,
            "follow_up_count": 0,
            "flow_decision": {
                "action": "proceed",
                "from_stage": "requirement",
                "to_stage": "planning",
                "reasons": [],
            },
        },
    })


def _valid_requirement():
    return json.loads(_valid_requirement_json())


def _valid_planning_json():
    return json.dumps(DeterministicAgentAdapter().create_plan(_valid_requirement()))


def _valid_ir():
    return {
        "part_type": "mounting_plate",
        "part_name": "repairable_plate",
        "unit": "mm",
        "dimensions": {"length": 30, "width": 20, "thickness": 4},
        "features": {"holes": {"diameter": 5, "positions": "corner_4", "offset_from_edge": 1}},
        "outputs": ["step", "stl"],
    }


def _valid_repair_json():
    return json.dumps({
        "analysis": {"affected_feature": "holes", "root_cause": "holes too close to edge"},
        "repair": {
            "strategy": "increase_spacing",
            "repaired_ir": {
                "part_type": "mounting_plate",
                "part_name": "repairable_plate",
                "unit": "mm",
                "dimensions": {"length": 30, "width": 20, "thickness": 4},
                "features": {"holes": {"diameter": 5, "positions": "corner_4", "offset_from_edge": 4}},
                "outputs": ["step", "stl"],
            },
        },
        "mode": "json_contract",
    })


def _valid_review_json():
    return json.dumps({
        "status": "success",
        "summary": "spacer generated successfully with STEP as the primary CAD artifact.",
        "errors": [],
        "warnings": [],
        "mode": "json_contract",
    })


def _valid_revision_intent():
    return {
        "artifact_type": "revision_intent",
        "version": "revision-intent-v0.1",
        "requested_change": "Increase the thickness to 8 mm.",
        "changes": [
            {
                "op": "replace",
                "path": "dimensions.thickness",
                "value": 8,
                "reason": "User requested thickness change.",
            }
        ],
        "confidence": "high",
    }


def _valid_revision_plan():
    return {
        "artifact_type": "revision_plan",
        "version": "revision-plan-v0.1",
        "status": "ready_for_patch",
        "planned_operations": [
            {
                "op": "replace",
                "path": "dimensions.thickness",
                "value": 8,
                "reason": "User requested thickness change.",
            }
        ],
        "notes": [],
    }


def _request_user_payload(request):
    return json.loads(_request_user_message(request)["content"])


def _request_user_message(request):
    return next(message for message in request["messages"] if message["role"] == "user")


def _request_system_text(request):
    return "\n".join(message["content"] for message in request["messages"] if message["role"] == "system")


def test_deterministic_agent_adapter_satisfies_contract_without_provider_config():
    adapter = DeterministicAgentAdapter()

    assert isinstance(adapter, AgentAdapter)
    assert adapter.provider_identity == {
        "provider": "local/mock",
        "adapter": "deterministic",
        "network": "disabled",
        "api_key_required": False,
    }


def test_deterministic_agent_adapter_outputs_are_repeatable():
    adapter = DeterministicAgentAdapter()
    prompt = "Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm."

    first = adapter.parse_requirement(prompt)
    second = adapter.parse_requirement(prompt)
    plan = adapter.create_plan(first)

    assert first == second
    assert first["part_type"] == "spacer"
    assert plan["artifact_type"] == "planning"
    assert plan["selected_parts"][0]["resolved_decisions"]["part_type"] == "spacer"


def test_json_contract_agent_adapter_accepts_valid_fake_requirement_output():
    fake_client = FakeJsonContractClient(_valid_requirement_json())
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement("Make a spacer washer.")

    assert requirement["part_type"] == "spacer"
    assert fake_client.requests[0]["operation"] == "parse_requirement"
    assert fake_client.requests[0]["response_format"] == {"type": "json_object"}
    assert fake_client.requests[0]["provider_options"] == {"timeout_seconds": 30, "max_retries": 0}
    assert fake_client.requests[0]["messages"][0]["role"] == "system"
    assert "Return JSON only" in fake_client.requests[0]["messages"][0]["content"]
    assert "requirement.json" in _request_system_text(fake_client.requests[0])


def test_parse_requirement_provider_request_is_requirement_scoped():
    fake_client = FakeJsonContractClient(_valid_requirement_json())
    adapter = JsonContractAgentAdapter(fake_client)

    adapter.parse_requirement("Make a spacer washer.")

    request = fake_client.requests[0]
    system_text = _request_system_text(request)

    assert "Stage skill: requirement" in system_text
    assert "requirement_check_level_missing_information" in system_text
    assert "features MUST be a JSON object" in system_text
    assert "requirement_status MUST be a JSON object" in system_text
    assert "revision_supported_changes" not in system_text
    assert "revision_patch_contract" not in system_text
    assert "assembly" not in system_text.lower()


def test_provider_messages_include_selected_knowledge_in_messages_not_only_context():
    fake_client = FakeJsonContractClient(_valid_requirement_json())
    adapter = JsonContractAgentAdapter(fake_client)

    adapter.parse_requirement("Make a spacer washer.", context={"workflow_stage": "requirement"})

    request = fake_client.requests[0]
    messages_text = json.dumps(request["messages"], sort_keys=True)
    context_text = json.dumps(request["context"], sort_keys=True)

    assert "Selected compact knowledge" in messages_text
    assert "requirement_check_level_missing_information" in messages_text
    assert "requirement_check_level_missing_information" not in context_text


def test_provider_context_messages_use_only_system_and_user_roles():
    messages = provider_messages_for(
        operation="create_plan",
        contract_instruction="Return planning JSON.",
        user_payload=_valid_requirement(),
    )

    assert [message["role"] for message in messages] == ["system", "system", "system", "user"]
    assert {message["role"] for message in messages} == {"system", "user"}


def test_provider_context_unknown_operation_fails_closed():
    with pytest.raises(ValueError, match="unsupported provider context operation"):
        knowledge_summary_for("interpret_user_intent")

    with pytest.raises(ValueError, match="unsupported provider context operation"):
        provider_messages_for(
            operation="interpret_user_intent",
            contract_instruction="Return JSON.",
            user_payload={},
        )


@pytest.mark.parametrize("response", [
    {"content": _valid_requirement_json()},
    {"output_text": _valid_requirement_json()},
    {"choices": [{"message": {"content": _valid_requirement_json()}}]},
    {"choices": [{"text": _valid_requirement_json()}]},
    {"output": [{"content": [{"text": _valid_requirement_json()}]}]},
    {"output": [{"content": [{"json": json.loads(_valid_requirement_json())}]}]},
])
def test_json_contract_agent_adapter_accepts_provider_response_wrappers(response):
    adapter = JsonContractAgentAdapter(FakeJsonContractClient(response))

    requirement = adapter.parse_requirement("Make a spacer washer.")

    assert requirement["part_type"] == "spacer"


def test_json_contract_agent_adapter_validates_provider_wrapper_content():
    adapter = JsonContractAgentAdapter(FakeJsonContractClient({
        "choices": [{
            "message": {
                "content": json.dumps({
                    "part_type": "spacer",
                    "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
                    "python_code": "print('bypass')",
                })
            }
        }]
    }))

    with pytest.raises(ValueError, match="python_code"):
        adapter.parse_requirement("Make a spacer washer.")


def test_json_contract_agent_adapter_accepts_valid_fake_planning_output():
    fake_client = FakeJsonContractClient(_valid_planning_json())
    adapter = JsonContractAgentAdapter(fake_client)

    planning = adapter.create_plan(_valid_requirement())

    assert planning["artifact_type"] == "planning"
    assert planning["selected_parts"][0]["resolved_decisions"]["part_type"] == "spacer"
    assert fake_client.requests[0]["operation"] == "create_plan"
    assert fake_client.requests[0]["response_format"] == {"type": "json_object"}
    assert fake_client.requests[0]["messages"][0]["role"] == "system"
    assert "planning_artifact.json" in _request_system_text(fake_client.requests[0])


def test_json_contract_agent_adapter_accepts_valid_fake_part_ir_output():
    fake_client = FakeJsonContractClient(json.dumps({
        "part_type": "spacer",
        "part_name": "single_part_spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 5, "thickness": 8},
        "features": {},
        "outputs": ["step", "stl"],
    }))
    adapter = JsonContractAgentAdapter(fake_client)

    ir = adapter.create_part_ir(
        {"artifact_type": "reviewed_part_handoff", "part_id": "spacer", "status": "ready_for_single_part_planning"},
        context={"part_execution_request": {"child_run_id": "single_part_spacer", "prompt": "Create spacer."}},
    )

    assert ir["part_type"] == "spacer"
    assert fake_client.requests[0]["operation"] == "create_part_ir"
    assert "Stage skill: cad_ir" in _request_system_text(fake_client.requests[0])
    assert "input_ir.json" in _request_system_text(fake_client.requests[0])


def test_json_contract_agent_adapter_rejects_part_ir_bypass_fields():
    adapter = JsonContractAgentAdapter(FakeJsonContractClient({
        "part_type": "spacer",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 5, "thickness": 8},
        "python_code": "print('bypass')",
    }))

    with pytest.raises(ValueError, match="python_code"):
        adapter.create_part_ir({"part_id": "spacer"})


def test_json_contract_agent_adapter_accepts_revision_contract_outputs():
    fake_client = OperationFakeJsonContractClient({
        "parse_revision_request": _valid_revision_intent(),
        "create_revision_plan": _valid_revision_plan(),
    })
    adapter = JsonContractAgentAdapter(fake_client)
    model_context = {"current_ir": _valid_ir(), "parent_run_id": "parent_run"}

    change_intent = adapter.parse_revision_request("Increase the thickness to 8 mm.", model_context)
    revision_plan = adapter.create_revision_plan(change_intent, model_context)

    assert change_intent["changes"][0]["path"] == "dimensions.thickness"
    assert revision_plan["status"] == "ready_for_patch"
    assert [request["operation"] for request in fake_client.requests] == [
        "parse_revision_request",
        "create_revision_plan",
    ]
    assert fake_client.requests[0]["response_format"] == {"type": "json_object"}
    assert "revision_intent" in _request_system_text(fake_client.requests[0])
    assert "revision_plan.json" in _request_system_text(fake_client.requests[1])


def test_create_revision_plan_provider_request_includes_revision_patch_guidance():
    fake_client = OperationFakeJsonContractClient({
        "create_revision_plan": _valid_revision_plan(),
    })
    adapter = JsonContractAgentAdapter(fake_client)

    adapter.create_revision_plan(_valid_revision_intent(), {"current_ir": _valid_ir()})

    request = fake_client.requests[0]
    system_text = _request_system_text(request)

    assert request["operation"] == "create_revision_plan"
    assert "Stage skill: revision" in system_text
    assert "revision_patch_contract" in system_text
    assert "patch operations" in system_text
    assert "blocked/no_structured_changes" in system_text


@pytest.mark.parametrize("operation,response", [
    ("parse_revision_request", {"artifact_type": "revision_intent", "python_code": "print('bypass')"}),
    ("create_revision_plan", {"artifact_type": "revision_plan", "shell_command": "python model.py"}),
])
def test_json_contract_agent_adapter_rejects_revision_bypass_fields(operation, response):
    fake_client = OperationFakeJsonContractClient({
        "parse_revision_request": response if operation == "parse_revision_request" else _valid_revision_intent(),
        "create_revision_plan": response if operation == "create_revision_plan" else _valid_revision_plan(),
    })
    adapter = JsonContractAgentAdapter(fake_client)
    model_context = {"current_ir": _valid_ir(), "parent_run_id": "parent_run"}

    with pytest.raises(ValueError):
        change_intent = adapter.parse_revision_request("Increase the thickness to 8 mm.", model_context)
        adapter.create_revision_plan(change_intent, model_context)


@pytest.mark.parametrize("response", [
    "[]",
    {"artifact_type": "plan", "route": {}, "selected_parts": [], "flow_gate_status": {}},
    {
        "artifact_type": "planning",
        "route": {},
        "selected_parts": [{"shell_command": "python model.py"}],
        "flow_gate_status": {},
    },
])
def test_json_contract_agent_adapter_rejects_invalid_planning_output(response):
    adapter = JsonContractAgentAdapter(FakeJsonContractClient(response))

    with pytest.raises(ValueError):
        adapter.create_plan(_valid_requirement())


def test_json_contract_agent_adapter_accepts_valid_fake_repair_output():
    fake_client = FakeJsonContractClient(_valid_repair_json())
    adapter = JsonContractAgentAdapter(fake_client)

    repair = adapter.suggest_repair(
        {"affected_feature": "holes", "suggested_ir_fix": {"strategy": "increase_spacing"}},
        _valid_ir(),
    )

    assert repair["analysis"]["affected_feature"] == "holes"
    assert repair["repair"]["repaired_ir"]["features"]["holes"]["offset_from_edge"] == 4
    assert fake_client.requests[0]["operation"] == "suggest_repair"
    assert fake_client.requests[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("response", [
    "[]",
    {"analysis": [], "repair": {}},
    {"analysis": {}, "repair": {"repaired_ir": {"part_type": "mounting_plate"}}},
    {"analysis": {}, "repair": {"python_code": "print('bypass')"}},
])
def test_json_contract_agent_adapter_rejects_invalid_repair_output(response):
    adapter = JsonContractAgentAdapter(FakeJsonContractClient(response))

    with pytest.raises(ValueError):
        adapter.suggest_repair({"affected_feature": "holes"}, _valid_ir())


def test_json_contract_agent_adapter_accepts_valid_fake_review_output():
    fake_client = FakeJsonContractClient(_valid_review_json())
    adapter = JsonContractAgentAdapter(fake_client)

    review = adapter.explain_review(
        {"status": "success", "success": True, "part_name": "spacer"},
        {"total_attempts": 1},
    )

    assert review["status"] == "success"
    assert "STEP" in review["summary"]
    assert fake_client.requests[0]["operation"] == "explain_review"
    assert fake_client.requests[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("response", [
    "[]",
    {"status": "", "summary": "missing status"},
    {"status": "failed", "summary": ""},
    {"status": "failed", "summary": "bad", "warnings": {}},
    {"status": "failed", "summary": "bad", "shell_command": "python model.py"},
])
def test_json_contract_agent_adapter_rejects_invalid_review_output(response):
    adapter = JsonContractAgentAdapter(FakeJsonContractClient(response))

    with pytest.raises(ValueError):
        adapter.explain_review({"status": "failed"}, {"total_attempts": 1})


@pytest.mark.parametrize("response", ["[]", "not json", {"part_type": "spacer", "dimensions": []}])
def test_json_contract_agent_adapter_rejects_invalid_or_non_object_output(response):
    adapter = JsonContractAgentAdapter(FakeJsonContractClient(response))

    with pytest.raises(ValueError):
        adapter.parse_requirement("Make a spacer washer.")


def test_json_contract_agent_adapter_provider_identity_is_sanitized():
    adapter = JsonContractAgentAdapter(
        FakeJsonContractClient(
            _valid_requirement_json(),
            provider_identity={
                "provider": "fake/json",
                "model": "fake-requirement-v1",
                "api_key": "secret",
                "token_count": 123,
                "prompt_path": "D:/private/prompt.txt",
                "transcript": "private chat",
            },
        )
    )

    assert adapter.provider_identity == {
        "provider": "fake/json",
        "adapter": "json_contract",
        "network": "client_injected",
        "enabled": False,
        "timeout_seconds": 30,
        "max_retries": 0,
        "api_key_required": False,
        "api_key_config": "not_configured",
        "model": "fake-requirement-v1",
    }


def test_json_contract_provider_config_is_secret_free_and_request_scoped():
    config = JsonContractProviderConfig(
        provider="fake/json",
        model="fake-revision-v1",
        enabled=True,
        timeout_seconds=12,
        max_retries=2,
        api_key_env_var="CADFLOW_FAKE_API_KEY",
    )
    fake_client = FakeJsonContractClient(_valid_requirement_json(), provider_identity={"provider": "fake/json"})
    adapter = JsonContractAgentAdapter(fake_client, config=config)

    adapter.parse_requirement("Make a spacer washer.")

    assert adapter.provider_identity == {
        "provider": "fake/json",
        "adapter": "json_contract",
        "network": "client_injected",
        "enabled": True,
        "timeout_seconds": 12,
        "max_retries": 2,
        "api_key_required": True,
        "api_key_config": "env_var_name_configured",
        "model": "fake-revision-v1",
    }
    assert "CADFLOW_FAKE_API_KEY" not in json.dumps(adapter.provider_identity)
    assert fake_client.requests[0]["provider_options"] == {"timeout_seconds": 12, "max_retries": 2}


def test_json_contract_agent_adapter_records_provider_request_trace_summary():
    fake_client = FakeJsonContractClient(
        _valid_requirement_json(),
        provider_identity={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key_env_var": "DEEPSEEK_API_KEY",
            "prompt": "private prompt",
            "local_path": r"D:\private\prompt.txt",
        },
    )
    adapter = JsonContractAgentAdapter(fake_client)

    adapter.parse_requirement("Make a spacer washer.")

    trace = adapter.last_provider_request_trace
    assert trace == fake_client.requests[0]["request_trace_summary"]
    assert trace["operation"] == "parse_requirement"
    assert trace["stage"] == "requirement"
    assert trace["provider_identity"] == {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "adapter": "json_contract",
        "network": "client_injected",
        "enabled": False,
        "timeout_seconds": 30,
        "max_retries": 0,
    }
    assert trace["message_count"] == 4
    assert trace["context_shape"] == {
        "has_global_rules": True,
        "has_stage_skill": True,
        "has_contract_guide": True,
        "selected_knowledge_count": 1,
    }
    assert trace["knowledge_ids"] == ["requirement_check_level_missing_information"]
    assert trace["payload_shape"] == {"kind": "prompt_payload", "top_level_keys": ["prompt"]}


def test_provider_request_trace_summary_excludes_sensitive_content():
    fake_client = FakeJsonContractClient(
        _valid_requirement_json(),
        provider_identity={
            "provider": "fake/json",
            "model": "fake-requirement-v1",
            "api_key": "fake-secret-value-123456",
            "api_key_env_var": "CADFLOW_FAKE_API_KEY",
            "provider_response": {"content": "raw provider body"},
            "transcript": "raw chat transcript",
            "workspace_path": r"D:\MyCode\llm2cad\secret",
        },
    )
    adapter = JsonContractAgentAdapter(fake_client)

    adapter.parse_requirement(
        r"Make a spacer at D:\private\prompt.txt using CADFLOW_FAKE_API_KEY and fake-secret-value-123456.",
        context={
            "workflow_stage": "requirement",
            "overrides": {
                "runtime_logs": ["raw runtime log"],
                "provider_response": "raw provider body",
                "api_key_env_var": "CADFLOW_FAKE_API_KEY",
                "output_dir": r"D:\private\outputs",
            },
        },
    )

    serialized = json.dumps(adapter.last_provider_request_trace, sort_keys=True)
    assert "Make a spacer" not in serialized
    assert "messages" not in serialized
    assert "raw provider body" not in serialized
    assert "raw runtime log" not in serialized
    assert "raw chat transcript" not in serialized
    assert "fake-secret-value-123456" not in serialized
    assert "CADFLOW_FAKE_API_KEY" not in serialized
    assert "D:\\private" not in serialized
    assert "D:\\MyCode" not in serialized
    assert "api_key" not in serialized
    assert "api_key_env_var" not in serialized


def test_json_contract_agent_adapter_sanitizes_context_before_provider_request():
    fake_client = FakeJsonContractClient(_valid_requirement_json())
    adapter = JsonContractAgentAdapter(fake_client)

    adapter.parse_requirement(
        "Make a spacer at D:/private/prompt.txt using sk-test-secret123456.",
        context={
            "workflow_stage": "requirement",
            "target_contract": "requirement_v0",
            "output_dir": r"D:\private\outputs\run",
            "root_run_id": "root_run",
            "overrides": {
                "dimensions": {"thickness": 8},
                "geometry_authority": "selected_parts.resolved_decisions",
                "api_key": "sk-test-secret123456",
                "api_key_env_var": "CADFLOW_FAKE_API_KEY",
                "local_path": r"D:\private\part.step",
                "runtime_logs": ["raw provider log"],
                "chat_log": "raw chat",
            },
        },
    )

    request = fake_client.requests[0]
    serialized = json.dumps(request, sort_keys=True)

    assert request["context"] == {
        "overrides": {
            "dimensions": {"thickness": 8},
            "geometry_authority": "selected_parts.resolved_decisions",
        },
        "workflow_stage": "requirement",
        "target_contract": "requirement_v0",
    }
    assert "[redacted-local-path]" in _request_user_message(request)["content"]
    assert "[redacted-secret]" in _request_user_message(request)["content"]
    assert "D:/private" not in serialized
    assert "D:\\private" not in serialized
    assert "sk-test-secret123456" not in serialized
    assert "CADFLOW_FAKE_API_KEY" not in serialized
    assert "api_key" not in serialized
    assert "output_dir" not in serialized
    assert "runtime_logs" not in serialized
    assert "chat_log" not in serialized


def test_json_contract_agent_adapter_sanitizes_requirement_payload_before_planning_request():
    fake_client = FakeJsonContractClient(_valid_planning_json())
    adapter = JsonContractAgentAdapter(fake_client)
    requirement = _valid_requirement()
    requirement.update({
        "api_token": "sk-test-secret123456",
        "source_path": r"D:\private\requirement.json",
        "notes": ["review CADFLOW_FAKE_API_KEY later", "keep the spacer thickness"],
    })

    adapter.create_plan(requirement)

    payload = _request_user_payload(fake_client.requests[0])
    serialized = json.dumps(fake_client.requests[0], sort_keys=True)

    assert payload["part_type"] == "spacer"
    assert payload["dimensions"]["thickness"] == 20
    assert payload["notes"] == ["review [redacted-api-env-var] later", "keep the spacer thickness"]
    assert "api_token" not in payload
    assert "source_path" not in payload
    assert "sk-test-secret123456" not in serialized
    assert "D:\\private" not in serialized
    assert "CADFLOW_FAKE_API_KEY" not in serialized


def test_json_contract_agent_adapter_removes_sensitive_payload_fields_from_provider_messages():
    fake_client = FakeJsonContractClient(_valid_planning_json())
    adapter = JsonContractAgentAdapter(fake_client)
    requirement = _valid_requirement()
    requirement.update({
        "password": "not-for-provider",
        "api_key": "sk-test-secret123456",
        "token": "private-token",
        "provider_response": {"output_text": "raw provider text"},
        "chat_logs": ["raw chat"],
    })

    adapter.create_plan(requirement)

    messages_text = json.dumps(fake_client.requests[0]["messages"], sort_keys=True)

    assert "password" not in messages_text
    assert "api_key" not in messages_text
    assert "token" not in messages_text
    assert "provider_response" not in messages_text
    assert "chat_logs" not in messages_text
    assert "not-for-provider" not in messages_text
    assert "sk-test-secret123456" not in messages_text
    assert "raw provider text" not in messages_text


def test_json_contract_agent_adapter_removes_api_env_names_and_local_paths_from_provider_messages():
    fake_client = FakeJsonContractClient(_valid_requirement_json())
    adapter = JsonContractAgentAdapter(fake_client)

    adapter.parse_requirement(
        r"Use CADFLOW_FAKE_API_KEY with D:\MyCode\llm2cad\outputs\secret.step and /home/admin/private/file.step"
    )

    messages_text = json.dumps(fake_client.requests[0]["messages"], sort_keys=True)

    assert "CADFLOW_FAKE_API_KEY" not in messages_text
    assert r"D:\MyCode" not in messages_text
    assert "/home/admin" not in messages_text
    assert "[redacted-api-env-var]" in messages_text
    assert "[redacted-local-path]" in messages_text


def test_json_contract_agent_adapter_sanitizes_revision_model_context_before_provider_request():
    fake_client = OperationFakeJsonContractClient({
        "parse_revision_request": _valid_revision_intent(),
        "create_revision_plan": _valid_revision_plan(),
    })
    adapter = JsonContractAgentAdapter(fake_client)
    model_context = {
        "parent_run_id": "parent_run",
        "parent_run_dir": r"D:\MyCode\llm2cad\outputs\parent_run",
        "input_ir": _valid_ir(),
        "report": {
            "status": "success",
            "files": {"step": r"D:\MyCode\llm2cad\outputs\parent_run\part.step"},
        },
        "agent_trace": {"raw_transcript": "private chat"},
        "runtime_logs": ["raw runtime log"],
        "password": "not-for-provider",
    }
    context = {
        "workflow_stage": "agent_revision",
        "target_contract": "cadflow_native_revision_v0.6",
        "output_dir": r"D:\MyCode\llm2cad\outputs\child_run",
        "overrides": {"features": {"holes": {"diameter": 5}}, "token": "secret-token"},
    }

    change_intent = adapter.parse_revision_request(
        "Increase thickness. See D:/private/revision.txt and CADFLOW_FAKE_API_KEY.",
        model_context,
        context=context,
    )
    adapter.create_revision_plan(change_intent, model_context, context=context)

    intent_payload = _request_user_payload(fake_client.requests[0])
    plan_payload = _request_user_payload(fake_client.requests[1])
    serialized = json.dumps(fake_client.requests, sort_keys=True)

    assert intent_payload["model_context"]["input_ir"]["part_type"] == "mounting_plate"
    assert intent_payload["model_context"]["report"]["status"] == "success"
    assert intent_payload["model_context"]["report"]["files"]["step"] == "[redacted-local-path]"
    assert plan_payload["change_intent"]["changes"][0]["path"] == "dimensions.thickness"
    assert fake_client.requests[0]["context"] == {
        "overrides": {"features": {"holes": {"diameter": 5}}},
        "workflow_stage": "agent_revision",
        "target_contract": "cadflow_native_revision_v0.6",
    }
    assert "parent_run_dir" not in serialized
    assert "output_dir" not in serialized
    assert "agent_trace" not in serialized
    assert "runtime_logs" not in serialized
    assert "raw_transcript" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized
    assert "D:/private" not in serialized
    assert "D:\\MyCode" not in serialized
    assert "CADFLOW_FAKE_API_KEY" not in serialized


@pytest.mark.parametrize("config", [
    {"provider": ""},
    {"timeout_seconds": 0},
    {"timeout_seconds": 301},
    {"max_retries": -1},
    {"max_retries": 6},
    {"api_key_env_var": r"C:\secret\key.txt"},
    {"unknown": True},
])
def test_json_contract_provider_config_rejects_unsafe_values(config):
    with pytest.raises(ValueError):
        JsonContractProviderConfig.from_mapping(config)


@pytest.mark.parametrize("exc,category,retryable", [
    (TimeoutError("request timed out for sk-test-secret at D:/private/prompt.txt"), "timeout", True),
    (RuntimeError("429 rate limit for CADFLOW_FAKE_API_KEY"), "rate_limited", True),
    (RuntimeError("401 auth failed with key sk-test-secret"), "auth_failed", False),
    (RuntimeError("provider crashed with transcript and D:/private/run"), "client_error", False),
])
def test_json_contract_provider_failures_are_wrapped_without_leaking_private_details(exc, category, retryable):
    adapter = JsonContractAgentAdapter(FailingJsonContractClient(exc))

    with pytest.raises(JsonContractProviderError) as raised:
        adapter.parse_requirement("Make a spacer washer.")

    error = raised.value
    serialized = json.dumps(error.to_dict()) + str(error)
    assert error.operation == "parse_requirement"
    assert error.category == category
    assert error.retryable is retryable
    assert "sk-test-secret" not in serialized
    assert "CADFLOW_FAKE_API_KEY" not in serialized
    assert "D:/private" not in serialized
    assert "transcript" not in serialized


def test_json_contract_provider_error_shape_is_public_and_stable():
    error = JsonContractProviderError("create_revision_plan", "timeout", retryable=True)

    assert str(error) == "JSON contract provider failed during create_revision_plan: timeout"
    assert error.to_dict() == {
        "type": "json_contract_provider_error",
        "operation": "create_revision_plan",
        "category": "timeout",
        "retryable": True,
    }


def test_provider_smoke_env_file_parser_loads_simple_pairs_and_ignores_comments():
    from examples.provider_smoke.env_file import parse_env_file

    values = parse_env_file(
        """
        # local provider credentials
        \ufeffDEEPSEEK_API_KEY=from-file

        export CADFLOW_DEEPSEEK_MODEL=deepseek-chat
        INVALID LINE
        QUOTED_VALUE="quoted"
        """
    )

    assert values == {
        "DEEPSEEK_API_KEY": "from-file",
        "CADFLOW_DEEPSEEK_MODEL": "deepseek-chat",
        "QUOTED_VALUE": "quoted",
    }


def test_provider_smoke_env_file_loader_preserves_process_env_precedence(tmp_path, monkeypatch):
    from examples.provider_smoke.env_file import load_env_file

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEEPSEEK_API_KEY=from-file\nCADFLOW_DEEPSEEK_MODEL=file-model\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-process")
    monkeypatch.delenv("CADFLOW_DEEPSEEK_MODEL", raising=False)

    loaded = load_env_file(env_file)

    assert "DEEPSEEK_API_KEY" not in loaded
    assert loaded == {"CADFLOW_DEEPSEEK_MODEL": "file-model"}
    assert os.environ["DEEPSEEK_API_KEY"] == "from-process"
    assert os.environ["CADFLOW_DEEPSEEK_MODEL"] == "file-model"


def test_provider_smoke_env_file_cli_uses_fake_adapter_without_leaking_secret(
    tmp_path,
    monkeypatch,
    capsys,
):
    from examples.provider_smoke import parse_requirement_smoke

    secret = "env-file-secret-value-123"
    env_file = tmp_path / ".env"
    env_file.write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    calls = []

    class FakeAdapter:
        provider_identity = {"provider": "deepseek", "model": "fake-model", "api_key": secret}

        @property
        def last_provider_request_trace(self):
            return {
                "operation": "parse_requirement",
                "provider_identity": {"provider": "deepseek", "model": "fake-model"},
                "knowledge_ids": ["requirement_check_level_missing_information"],
                "message_count": 4,
            }

        def parse_requirement(self, prompt, context=None):
            calls.append({"prompt": prompt, "context": context})
            return {"part_type": "mounting_plate"}

    def fake_make_adapter(provider, model=None):
        assert provider == "deepseek"
        assert os.environ["DEEPSEEK_API_KEY"] == secret
        return FakeAdapter()

    monkeypatch.setattr(parse_requirement_smoke, "make_json_contract_adapter_from_env", fake_make_adapter)

    exit_code = parse_requirement_smoke.main([
        "--provider",
        "deepseek",
        "--env-file",
        str(env_file),
    ])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert len(calls) == 1
    assert secret not in output
    assert "DEEPSEEK_API_KEY" not in output
    assert "Authorization" not in output
    assert "Make an 80x40x5" not in output


def test_provider_smoke_script_handles_missing_credentials_without_leaking_env_names(monkeypatch, capsys):
    from examples.provider_smoke import parse_requirement_smoke

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    exit_code = parse_requirement_smoke.main(["--provider", "deepseek"])

    output = capsys.readouterr().out
    status = json.loads(output)
    assert exit_code == 2
    assert status["provider"] == "deepseek"
    assert status["operation"] == "parse_requirement"
    assert status["validation_status"] == "not_run"
    assert status["status"] == "missing_provider_credentials"
    assert status["selected_knowledge_ids"] == ["requirement_check_level_missing_information"]
    assert status["message_count"] == 4
    assert "DEEPSEEK_API_KEY" not in output
    assert "Authorization" not in output
    assert "Make an 80x40x5" not in output
    assert "messages" not in output


def test_provider_create_smoke_script_handles_missing_credentials_without_leaking_env_names(
    tmp_path,
    monkeypatch,
    capsys,
):
    from examples.provider_smoke import create_workflow_smoke

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)

    exit_code = create_workflow_smoke.main([
        "--provider",
        "deepseek",
        "--output-dir",
        str(tmp_path / "outputs" / "provider_create_smoke_missing_credentials"),
    ])

    output = capsys.readouterr().out
    status = json.loads(output)
    assert exit_code == 2
    assert status["provider"] == "deepseek"
    assert status["requirement_status"] == "failed"
    assert status["planning_status"] == "not_run"
    assert status["ir_validation_status"] == "not_run"
    assert status["pipeline_status"] == "not_run"
    assert status["error_category"] == "auth_failed"
    assert "DEEPSEEK_API_KEY" not in output
    assert "Authorization" not in output
    assert "Make an 80x40x5" not in output
    assert "messages" not in output


def test_reviewed_part_single_create_smoke_runs_one_sanitized_fake_flow(tmp_path, monkeypatch, capsys):
    from examples.provider_smoke import reviewed_part_single_create_smoke as smoke

    secret = "env-file-secret-value-456"
    env_file = tmp_path / ".env"
    env_file.write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    class FakeAdapter:
        provider_identity = {"provider": "deepseek", "model": "fake-model", "api_key": secret}

    def fake_make_adapter(provider, model=None):
        assert provider == "deepseek"
        assert os.environ["DEEPSEEK_API_KEY"] == secret
        return FakeAdapter()

    def fake_design(prompt, adapter, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "assembly_plan.json").write_text(json.dumps({
            "artifact_type": "assembly_plan",
            "scope": "multi_part",
            "parts": [
                {
                    "part_id": "base",
                    "supported_candidate": True,
                    "part_status": "candidate_for_single_part_generation",
                    "generation_strategy": "single_part",
                },
                {
                    "part_id": "lid",
                    "supported_candidate": True,
                    "part_status": "candidate_for_single_part_generation",
                    "generation_strategy": "single_part",
                },
                {"part_id": "screws", "part_status": "reference_only"},
            ],
            "interfaces": [],
        }), encoding="utf-8")
        return {"status": "blocked_multi_part_generation_not_supported", "diagnostic_codes": ["assembly.plan_created"]}

    def fake_part_request(assembly_plan, output_dir=None, part_id=None, **kwargs):
        assert part_id == "base"
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "part_create_request.json").write_text(json.dumps({"part_id": part_id}), encoding="utf-8")
        return {"status": "ready_for_review", "diagnostic_codes": ["part_request.created"]}

    def fake_review(part_create_request, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "part_request_review.json").write_text(json.dumps({"status": "approved"}), encoding="utf-8")
        return {"status": "approved", "diagnostic_codes": ["part_request.approved_for_single_part_planning"]}

    def fake_handoff(part_create_request, part_request_review, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "reviewed_part_handoff.json").write_text(json.dumps({
            "part_id": "base",
            "status": "ready_for_single_part_planning",
        }), encoding="utf-8")
        return {"status": "ready_for_single_part_planning", "diagnostic_codes": ["part_handoff.ready_for_single_part_planning"]}

    def fake_bridge(reviewed_part_handoff, adapter, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        child_dir = output_path / "single_part_base"
        child_dir.mkdir(parents=True)
        (child_dir / "model.step").write_text("STEP", encoding="utf-8")
        (child_dir / "model.stl").write_text("STL", encoding="utf-8")
        (output_path / "lineage.json").write_text(json.dumps({
            "reviewed_part_handoff_artifact": "reviewed_part_handoff.json",
            "child_run_id": "single_part_base",
        }), encoding="utf-8")
        return {
            "status": "success",
            "child_output_dir": str(child_dir),
            "diagnostic_codes": ["reviewed_part_single_create.started"],
        }

    def fake_part_result_review(reviewed_part_handoff, child_run, output_dir=None, **kwargs):
        assert Path(child_run).name == "single_part_base"
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        review = {
            "artifact_type": "part_result_review",
            "schema_version": "0.1",
            "source_handoff": "reviewed_part_handoff.json",
            "child_run": "single_part_base",
            "part_id": "base",
            "status": "accepted_for_preview",
            "checks": {
                "step_created": True,
                "stl_created": True,
                "single_part_only": True,
                "no_batch_generation": True,
                "no_assembly_generation": True,
                "lineage_preserved": True,
                "interface_constraints_preserved_in_metadata": True,
            },
            "diagnostic_codes": [
                "part_result.review_created",
                "part_result.step_created",
                "part_result.single_part_scope_preserved",
            ],
            "revision_notes": [],
        }
        (output_path / "part_result_review.json").write_text(json.dumps(review), encoding="utf-8")
        return {"status": "accepted_for_preview", "part_result_review": review}

    monkeypatch.setattr(smoke, "make_json_contract_adapter_from_env", fake_make_adapter)
    monkeypatch.setattr(smoke, "run_provider_normalized_design_create_pipeline", fake_design)
    monkeypatch.setattr(smoke, "run_assembly_part_request_pipeline", fake_part_request)
    monkeypatch.setattr(smoke, "run_part_request_review_pipeline", fake_review)
    monkeypatch.setattr(smoke, "run_reviewed_part_handoff_pipeline", fake_handoff)
    monkeypatch.setattr(smoke, "run_reviewed_part_single_create_pipeline", fake_bridge)
    monkeypatch.setattr(smoke, "run_part_result_review_pipeline", fake_part_result_review)

    exit_code = smoke.main([
        "--provider",
        "deepseek",
        "--env-file",
        str(env_file),
        "--output-dir",
        str(tmp_path / "outputs" / "manual_smoke"),
    ])

    output = capsys.readouterr().out
    status = json.loads(output)
    assert exit_code == 0
    assert status["provider"] == "deepseek"
    assert status["model"] == "fake-model"
    assert status["source_prompt_case"] == "electronics_enclosure_base_lid"
    assert status["assembly_plan_created"] is True
    assert status["requested_part_id"] is None
    assert status["selected_part_id"] == "base"
    assert status["part_selection_status"] == "selected"
    assert status["part_selection_diagnostic_codes"] == ["part_selection.default_candidate_selected"]
    assert status["candidate_part_ids"] == ["base", "lid"]
    assert status["reference_only_part_ids"] == ["screws"]
    assert status["blocked_part_ids"] == []
    assert status["part_request_status"] == "ready_for_review"
    assert status["review_status"] == "approved"
    assert status["handoff_status"] == "ready_for_single_part_planning"
    assert status["bridge_status"] == "success"
    assert status["child_run_created"] is True
    assert status["child_run_name"] == "single_part_base"
    assert status["child_diagnostic_codes"] == []
    assert status["part_result_review_created"] is True
    assert status["part_result_review_status"] == "accepted_for_preview"
    assert status["part_result_diagnostic_codes"] == [
        "part_result.review_created",
        "part_result.single_part_scope_preserved",
        "part_result.step_created",
    ]
    assert status["part_result_step_check"] is True
    assert status["part_result_stl_check"] is True
    assert status["part_result_single_part_scope_check"] is True
    assert status["part_result_lineage_check"] is True
    assert status["part_result_interface_metadata_check"] is True
    assert status["step_created"] is True
    assert status["stl_created"] is True
    assert status["no_batch_generation"] is True
    assert status["no_assembly_generation"] is True
    assert status["no_assembly_constraints_solved"] is True
    assert "reviewed_part_single_create.started" in status["diagnostic_codes"]
    assert secret not in output
    assert str(tmp_path) not in output
    assert "DEEPSEEK_API_KEY" not in output
    assert "messages" not in output
    assert "raw_response" not in output
    assert "transcript" not in output
    assert "part_result_review.json" not in output


def test_reviewed_part_single_create_smoke_surfaces_blocked_child_diagnostics(tmp_path, monkeypatch):
    from examples.provider_smoke import reviewed_part_single_create_smoke as smoke

    class FakeAdapter:
        provider_identity = {"provider": "fake/json", "model": "fake-model", "api_key": "secret-value"}

    def fake_design(prompt, adapter, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "assembly_plan.json").write_text(json.dumps({
            "artifact_type": "assembly_plan",
            "scope": "multi_part",
            "parts": [
                {
                    "part_id": "base",
                    "supported_candidate": True,
                    "part_status": "candidate_for_single_part_generation",
                    "generation_strategy": "single_part",
                },
                {"part_id": "screws", "part_status": "reference_only"},
            ],
            "interfaces": [],
        }), encoding="utf-8")
        return {"status": "blocked_multi_part_generation_not_supported", "diagnostic_codes": ["assembly.plan_created"]}

    def fake_part_request(assembly_plan, output_dir=None, part_id=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "part_create_request.json").write_text(json.dumps({"part_id": part_id}), encoding="utf-8")
        return {"status": "ready_for_review", "diagnostic_codes": ["part_request.created"]}

    def fake_review(part_create_request, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "part_request_review.json").write_text(json.dumps({"status": "approved"}), encoding="utf-8")
        return {"status": "approved", "diagnostic_codes": ["part_request.approved_for_single_part_planning"]}

    def fake_handoff(part_create_request, part_request_review, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "reviewed_part_handoff.json").write_text(json.dumps({
            "part_id": "base",
            "status": "ready_for_single_part_planning",
        }), encoding="utf-8")
        return {"status": "ready_for_single_part_planning", "diagnostic_codes": ["part_handoff.ready_for_single_part_planning"]}

    def fake_bridge(reviewed_part_handoff, adapter, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        child_dir = output_path / "single_part_base"
        child_dir.mkdir(parents=True)
        (child_dir / "report.json").write_text(json.dumps({
            "status": "blocked_provider_requirement",
            "diagnostic_codes": ["compiler.assembly_requires_assembly_planning"],
            "provider_create": {
                "diagnostic_codes": ["compiler.assembly_requires_assembly_planning"],
                "requirement_status": {
                    "diagnostic_codes": ["compiler.scope_blocked"],
                    "raw_response": "do not print",
                },
            },
        }), encoding="utf-8")
        return {
            "status": "blocked_provider_requirement",
            "child_output_dir": str(child_dir),
            "diagnostic_codes": ["reviewed_part_single_create.started"],
            "child_result": {
                "diagnostic_codes": ["compiler.assembly_requires_assembly_planning"],
            },
        }

    def fake_part_result_review(reviewed_part_handoff, child_run, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        review = {
            "artifact_type": "part_result_review",
            "schema_version": "0.1",
            "source_handoff": "reviewed_part_handoff.json",
            "child_run": "single_part_base",
            "part_id": "base",
            "status": "blocked_missing_step",
            "checks": {
                "step_created": False,
                "stl_created": False,
                "single_part_only": True,
                "no_batch_generation": True,
                "no_assembly_generation": True,
                "lineage_preserved": False,
                "interface_constraints_preserved_in_metadata": False,
            },
            "diagnostic_codes": [
                "part_result.review_created",
                "part_result.blocked_missing_step",
            ],
            "revision_notes": [{"code": "part_result.blocked_missing_step", "message": "sanitized"}],
            "raw_response": "do not print",
        }
        return {"status": "blocked_missing_step", "part_result_review": review}

    monkeypatch.setattr(smoke, "run_provider_normalized_design_create_pipeline", fake_design)
    monkeypatch.setattr(smoke, "run_assembly_part_request_pipeline", fake_part_request)
    monkeypatch.setattr(smoke, "run_part_request_review_pipeline", fake_review)
    monkeypatch.setattr(smoke, "run_reviewed_part_handoff_pipeline", fake_handoff)
    monkeypatch.setattr(smoke, "run_reviewed_part_single_create_pipeline", fake_bridge)
    monkeypatch.setattr(smoke, "run_part_result_review_pipeline", fake_part_result_review)

    summary = smoke.run_reviewed_part_single_create_smoke(
        FakeAdapter(),
        "fake",
        tmp_path / "outputs" / "manual_smoke",
    )

    serialized = json.dumps(summary, sort_keys=True)
    assert summary["selected_part_id"] == "base"
    assert summary["child_run_created"] is True
    assert summary["bridge_status"] == "blocked_provider_requirement"
    assert summary["child_diagnostic_codes"] == [
        "compiler.assembly_requires_assembly_planning",
        "compiler.scope_blocked",
    ]
    assert summary["part_result_review_created"] is True
    assert summary["part_result_review_status"] == "blocked_missing_step"
    assert summary["part_result_diagnostic_codes"] == [
        "part_result.blocked_missing_step",
        "part_result.review_created",
    ]
    assert summary["part_result_step_check"] is False
    assert summary["part_result_stl_check"] is False
    assert summary["part_result_single_part_scope_check"] is True
    assert summary["part_result_lineage_check"] is False
    assert summary["part_result_interface_metadata_check"] is False
    assert summary["part_result_review_status"] != "accepted_for_preview"
    assert "compiler.assembly_requires_assembly_planning" in summary["diagnostic_codes"]
    assert summary["step_created"] is False
    assert summary["stl_created"] is False
    assert summary["no_batch_generation"] is True
    assert summary["no_assembly_generation"] is True
    assert "secret-value" not in serialized
    assert str(tmp_path) not in serialized
    assert "raw_response" not in serialized
    assert "do not print" not in serialized
    assert str(tmp_path) not in serialized


def test_reviewed_part_single_create_smoke_selects_one_candidate_only():
    from examples.provider_smoke.reviewed_part_single_create_smoke import (
        select_candidate_part,
        select_one_candidate_part_id,
        selection_diagnostics,
    )

    assembly_plan = {
        "parts": [
            {
                "part_id": "base",
                "supported_candidate": True,
                "part_status": "candidate_for_single_part_generation",
            },
            {
                "part_id": "lid",
                "supported_candidate": True,
                "part_status": "candidate_for_single_part_generation",
            },
            {"part_id": "screws", "part_status": "reference_only"},
        ]
    }

    assert select_one_candidate_part_id(assembly_plan) == "base"
    explicit = select_candidate_part(assembly_plan, requested_part_id="lid")
    assert explicit["selected_part_id"] == "lid"
    assert explicit["status"] == "selected"
    assert explicit["diagnostic_codes"] == ["part_selection.requested_part_selected"]
    reference_only = select_candidate_part(assembly_plan, requested_part_id="screws")
    assert reference_only["selected_part_id"] is None
    assert reference_only["status"] == "blocked_reference_only_part"
    assert reference_only["diagnostic_codes"] == ["part_selection.reference_only_not_selectable"]
    missing = select_candidate_part(assembly_plan, requested_part_id="missing")
    assert missing["status"] == "blocked_requested_part_not_found"
    diagnostics = selection_diagnostics(assembly_plan)
    assert diagnostics["part_count"] == 3
    assert diagnostics["candidate_part_count"] == 2
    assert diagnostics["reference_only_count"] == 1
    assert diagnostics["blocked_part_count"] == 0
    assert diagnostics["candidate_part_ids"] == ["base", "lid"]
    assert diagnostics["part_status_counts"] == {
        "candidate_for_single_part_generation": 2,
        "reference_only": 1,
    }


def test_reviewed_part_single_create_smoke_explicit_part_id_selects_requested_candidate(tmp_path, monkeypatch):
    from examples.provider_smoke import reviewed_part_single_create_smoke as smoke

    class FakeAdapter:
        provider_identity = {"provider": "fake/json", "model": "fake-model", "api_key": "secret-value"}

    def fake_design(prompt, adapter, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "assembly_plan.json").write_text(json.dumps({
            "parts": [
                {
                    "part_id": "base",
                    "supported_candidate": True,
                    "part_status": "candidate_for_single_part_generation",
                    "generation_strategy": "single_part",
                },
                {
                    "part_id": "lid",
                    "supported_candidate": True,
                    "part_status": "candidate_for_single_part_generation",
                    "generation_strategy": "single_part",
                },
                {"part_id": "screws", "part_status": "reference_only"},
            ],
            "interfaces": [],
        }), encoding="utf-8")
        return {"status": "blocked_multi_part_generation_not_supported", "diagnostic_codes": ["assembly.plan_created"]}

    def fake_part_request(assembly_plan, output_dir=None, part_id=None, **kwargs):
        assert part_id == "lid"
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "part_create_request.json").write_text(json.dumps({"part_id": part_id}), encoding="utf-8")
        return {"status": "ready_for_review", "diagnostic_codes": ["part_request.created"]}

    def fake_review(part_create_request, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "part_request_review.json").write_text(json.dumps({"status": "approved"}), encoding="utf-8")
        return {"status": "approved", "diagnostic_codes": ["part_request.approved_for_single_part_planning"]}

    def fake_handoff(part_create_request, part_request_review, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "reviewed_part_handoff.json").write_text(json.dumps({
            "part_id": "lid",
            "status": "ready_for_single_part_planning",
        }), encoding="utf-8")
        return {"status": "ready_for_single_part_planning", "diagnostic_codes": ["part_handoff.ready_for_single_part_planning"]}

    def fake_bridge(reviewed_part_handoff, adapter, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        child_dir = output_path / "single_part_lid"
        child_dir.mkdir(parents=True)
        (child_dir / "model.step").write_text("STEP", encoding="utf-8")
        (child_dir / "model.stl").write_text("STL", encoding="utf-8")
        return {
            "status": "success",
            "child_output_dir": str(child_dir),
            "diagnostic_codes": ["reviewed_part_single_create.started"],
        }

    def fake_part_result_review(reviewed_part_handoff, child_run, output_dir=None, **kwargs):
        review = {
            "status": "accepted_for_preview",
            "checks": {
                "step_created": True,
                "stl_created": True,
                "single_part_only": True,
                "no_batch_generation": True,
                "no_assembly_generation": True,
                "lineage_preserved": True,
                "interface_constraints_preserved_in_metadata": True,
            },
            "diagnostic_codes": ["part_result.review_created"],
        }
        return {"status": "accepted_for_preview", "part_result_review": review}

    monkeypatch.setattr(smoke, "run_provider_normalized_design_create_pipeline", fake_design)
    monkeypatch.setattr(smoke, "run_assembly_part_request_pipeline", fake_part_request)
    monkeypatch.setattr(smoke, "run_part_request_review_pipeline", fake_review)
    monkeypatch.setattr(smoke, "run_reviewed_part_handoff_pipeline", fake_handoff)
    monkeypatch.setattr(smoke, "run_reviewed_part_single_create_pipeline", fake_bridge)
    monkeypatch.setattr(smoke, "run_part_result_review_pipeline", fake_part_result_review)

    summary = smoke.run_reviewed_part_single_create_smoke(
        FakeAdapter(),
        "fake",
        tmp_path / "outputs" / "manual_smoke",
        requested_part_id="lid",
    )

    serialized = json.dumps(summary, sort_keys=True)
    assert summary["requested_part_id"] == "lid"
    assert summary["selected_part_id"] == "lid"
    assert summary["part_selection_status"] == "selected"
    assert summary["part_selection_diagnostic_codes"] == ["part_selection.requested_part_selected"]
    assert summary["child_run_name"] == "single_part_lid"
    assert summary["child_run_created"] is True
    assert summary["no_batch_generation"] is True
    assert summary["no_assembly_generation"] is True
    assert "secret-value" not in serialized
    assert str(tmp_path) not in serialized


@pytest.mark.parametrize(
    ("requested_part_id", "expected_status", "expected_code"),
    [
        ("screws", "blocked_reference_only_part", "part_selection.reference_only_not_selectable"),
        ("gear", "blocked_part_not_selectable", "part_selection.blocked_part_not_selectable"),
        ("missing", "blocked_requested_part_not_found", "part_selection.requested_part_not_found"),
    ],
)
def test_reviewed_part_single_create_smoke_blocks_unsafe_requested_parts(
    tmp_path,
    monkeypatch,
    requested_part_id,
    expected_status,
    expected_code,
):
    from examples.provider_smoke import reviewed_part_single_create_smoke as smoke

    class FakeAdapter:
        provider_identity = {"provider": "fake/json", "model": "fake-model", "api_key": "secret-value"}

    def fake_design(prompt, adapter, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "assembly_plan.json").write_text(json.dumps({
            "parts": [
                {
                    "part_id": "base",
                    "supported_candidate": True,
                    "part_status": "candidate_for_single_part_generation",
                    "generation_strategy": "single_part",
                },
                {"part_id": "screws", "part_status": "reference_only", "generation_strategy": "reference_only"},
                {"part_id": "gear", "part_status": "blocked", "generation_strategy": "blocked"},
            ],
        }), encoding="utf-8")
        return {"status": "blocked_multi_part_generation_not_supported", "diagnostic_codes": ["assembly.plan_created"]}

    def fail_if_called(*args, **kwargs):
        raise AssertionError("blocked requested part must stop before downstream stages")

    monkeypatch.setattr(smoke, "run_provider_normalized_design_create_pipeline", fake_design)
    monkeypatch.setattr(smoke, "run_assembly_part_request_pipeline", fail_if_called)
    monkeypatch.setattr(smoke, "run_part_request_review_pipeline", fail_if_called)
    monkeypatch.setattr(smoke, "run_reviewed_part_handoff_pipeline", fail_if_called)
    monkeypatch.setattr(smoke, "run_reviewed_part_single_create_pipeline", fail_if_called)
    monkeypatch.setattr(smoke, "run_part_result_review_pipeline", fail_if_called)

    summary = smoke.run_reviewed_part_single_create_smoke(
        FakeAdapter(),
        "fake",
        tmp_path / "outputs" / "manual_smoke",
        requested_part_id=requested_part_id,
    )

    serialized = json.dumps(summary, sort_keys=True)
    assert summary["requested_part_id"] == requested_part_id
    assert summary["selected_part_id"] is None
    assert summary["part_selection_status"] == expected_status
    assert summary["part_selection_diagnostic_codes"] == [expected_code]
    assert summary["candidate_part_ids"] == ["base"]
    assert summary["reference_only_part_ids"] == ["screws"]
    assert summary["blocked_part_ids"] == ["gear"]
    assert summary["child_run_created"] is False
    assert summary["no_batch_generation"] is True
    assert summary["no_assembly_generation"] is True
    assert "secret-value" not in serialized
    assert str(tmp_path) not in serialized


def test_reviewed_part_single_create_smoke_no_candidate_summary_includes_sanitized_selection_diagnostics(tmp_path, monkeypatch):
    from examples.provider_smoke import reviewed_part_single_create_smoke as smoke

    class FakeAdapter:
        provider_identity = {"provider": "fake/json", "model": "fake-model", "api_key": "secret-value"}

    def fake_design(prompt, adapter, output_dir=None, **kwargs):
        output_path = Path(output_dir)
        output_path.mkdir(parents=True)
        (output_path / "assembly_plan.json").write_text(json.dumps({
            "artifact_type": "assembly_plan",
            "scope": "multi_part",
            "parts": [
                {
                    "part_id": "base",
                    "part_status": "planned_only",
                    "generation_strategy": "future_part_pipeline",
                    "supported_candidate": False,
                    "blocked_reasons": [{"code": "needs_review"}],
                    "raw_response": "do not print",
                },
                {
                    "part_id": "screws",
                    "part_status": "reference_only",
                    "generation_strategy": "reference_only",
                    "supported_candidate": False,
                    "blocked_reasons": [],
                },
                {
                    "part_id": "gear",
                    "part_status": "blocked",
                    "generation_strategy": "blocked",
                    "supported_candidate": False,
                    "blocked_reasons": [{"code": "unsupported_part_family"}],
                },
            ],
            "quality": {"blocked_reason_codes": ["assembly_generation_not_supported_yet"]},
            "provider_response": {"transcript": "do not print"},
        }), encoding="utf-8")
        return {
            "status": "blocked_multi_part_generation_not_supported",
            "diagnostic_codes": ["assembly.plan_created"],
        }

    def fail_if_called(*args, **kwargs):
        raise AssertionError("no candidate should stop before part request/review/handoff/bridge")

    monkeypatch.setattr(smoke, "run_provider_normalized_design_create_pipeline", fake_design)
    monkeypatch.setattr(smoke, "run_assembly_part_request_pipeline", fail_if_called)
    monkeypatch.setattr(smoke, "run_part_request_review_pipeline", fail_if_called)
    monkeypatch.setattr(smoke, "run_reviewed_part_handoff_pipeline", fail_if_called)
    monkeypatch.setattr(smoke, "run_reviewed_part_single_create_pipeline", fail_if_called)
    monkeypatch.setattr(smoke, "run_part_result_review_pipeline", fail_if_called)

    summary = smoke.run_reviewed_part_single_create_smoke(
        FakeAdapter(),
        "fake",
        tmp_path / "outputs" / "manual_smoke",
    )

    output = json.dumps(summary, sort_keys=True)
    assert summary["assembly_plan_created"] is True
    assert summary["selected_part_id"] is None
    assert summary["no_batch_generation"] is True
    assert summary["no_assembly_generation"] is True
    assert summary["no_assembly_constraints_solved"] is True
    assert summary["selection_diagnostics"] == {
        "part_count": 3,
        "candidate_part_count": 0,
        "reference_only_count": 1,
        "blocked_part_count": 1,
        "part_status_counts": {"blocked": 1, "planned_only": 1, "reference_only": 1},
        "generation_strategy_counts": {"blocked": 1, "future_part_pipeline": 1, "reference_only": 1},
        "candidate_part_ids": [],
        "blocked_reason_codes": [
            "assembly_generation_not_supported_yet",
            "needs_review",
            "unsupported_part_family",
        ],
    }
    assert "secret-value" not in output
    assert str(tmp_path) not in output
    assert "raw_response" not in output
    assert "transcript" not in output
    assert "do not print" not in output


def test_reviewed_part_single_create_smoke_missing_credentials_are_sanitized(monkeypatch, capsys):
    from examples.provider_smoke import reviewed_part_single_create_smoke as smoke

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def fake_make_adapter(provider, model=None):
        raise JsonContractProviderError("parse_requirement", "auth_failed")

    monkeypatch.setattr(smoke, "make_json_contract_adapter_from_env", fake_make_adapter)

    exit_code = smoke.main(["--provider", "deepseek"])

    output = capsys.readouterr().out
    status = json.loads(output)
    assert exit_code == 2
    assert status["provider"] == "deepseek"
    assert status["bridge_status"] == "provider_error"
    assert status["error_category"] == "auth_failed"
    assert status["message"] == "Provider credentials are missing or not accepted."
    assert "DEEPSEEK_API_KEY" not in output
    assert "Authorization" not in output
    assert "messages" not in output
    assert "raw_response" not in output


def test_provider_create_eval_aggregates_successful_and_blocked_cases(tmp_path):
    from examples.provider_smoke import provider_create_eval

    class FakeAdapter:
        provider_identity = {"provider": "fake/json", "model": "fake-model"}

    cases = [
        {"case_id": "success_case", "prompt": "Make a spacer washer."},
        {"case_id": "blocked_case", "prompt": "Make a mounting plate without dimensions."},
    ]

    def fake_runner(prompt, adapter, output_dir=None, provider_contract_mode="strict"):
        if "without dimensions" in prompt:
            return {
                "status": "blocked_provider_requirement",
                "blocked_stage": "requirement",
                "error_category": "requirement_gate_blocked",
                "output_dir": str(output_dir),
                "provider_create": {
                    "status": "blocked_provider_requirement",
                    "requirement_status": "failed",
                    "planning_status": "not_run",
                    "ir_validation_status": "not_run",
                    "pipeline_status": "not_run",
                    "blocked_stage": "requirement",
                    "error_category": "requirement_gate_blocked",
                    "provider_request_traces": [{
                        "operation": "parse_requirement",
                        "message_count": 4,
                        "knowledge_ids": ["requirement_check_level_missing_information"],
                    }],
                },
            }
        return {
            "status": "success",
            "output_dir": str(output_dir),
            "provider_create": {
                "status": "success",
                "requirement_status": "passed",
                "planning_status": "passed",
                "ir_validation_status": "passed",
                "pipeline_status": "success",
                "provider_request_traces": [
                    {"operation": "parse_requirement", "message_count": 4, "knowledge_ids": ["requirement_check_level_missing_information"]},
                    {"operation": "create_plan", "message_count": 4, "knowledge_ids": ["planning_design_analysis"]},
                ],
            },
        }

    result = provider_create_eval.run_provider_create_eval(
        adapter=FakeAdapter(),
        provider="fake/json",
        output_dir=tmp_path / "eval",
        cases=cases,
        runner=fake_runner,
    )

    summary = result["summary"]
    assert summary["case_count"] == 2
    assert summary["requirement_valid_count"] == 1
    assert summary["planning_valid_count"] == 1
    assert summary["ir_conversion_success_count"] == 1
    assert summary["pipeline_success_count"] == 1
    assert summary["blocked_count"] == 1
    assert summary["expected_blocked_count"] == 0
    assert summary["unexpected_blocked_count"] == 1
    assert summary["failed_count"] == 0
    assert result["cases"][1]["outcome"] == "unexpected_blocked"
    assert result["cases"][1]["blocked_stage"] == "requirement"
    assert result["cases"][0]["provider_trace_summary"]["operations"] == ["parse_requirement", "create_plan"]


def test_provider_create_eval_writes_artifacts_without_private_details(tmp_path):
    from examples.provider_smoke import provider_create_eval

    class FakeAdapter:
        provider_identity = {
            "provider": "fake/json",
            "model": "fake-model",
            "api_key": "fake-secret-value-123456",
        }

    def fake_runner(prompt, adapter, output_dir=None, provider_contract_mode="strict"):
        return {
            "status": "blocked_provider_validation",
            "blocked_stage": "cad_ir",
            "error_category": "cad_ir_validation_failed",
            "output_dir": r"D:\private\provider\run",
            "provider_response": "raw provider response",
            "runtime_logs": ["raw runtime log"],
            "transcript": "raw chat transcript",
            "provider_create": {
                "status": "blocked_provider_validation",
                "requirement_status": "passed",
                "planning_status": "passed",
                "ir_validation_status": "failed",
                "pipeline_status": "not_run",
                "blocked_stage": "cad_ir",
                "error_category": "cad_ir_validation_failed",
                "provider_request_traces": [{
                    "operation": "parse_requirement",
                    "message_count": 4,
                    "knowledge_ids": [
                        "requirement_check_level_missing_information",
                        "CADFLOW_FAKE_API_KEY",
                    ],
                    "messages": ["raw provider message"],
                    "provider_response": "raw provider response",
                }],
            },
        }

    eval_dir = tmp_path / "eval"
    result = provider_create_eval.run_provider_create_eval(
        adapter=FakeAdapter(),
        provider="fake/json",
        output_dir=eval_dir,
        cases=[{"case_id": "privacy_case", "prompt": "Make a spacer washer."}],
        runner=fake_runner,
    )

    for artifact in ("eval_cases.json", "eval_summary.json", "eval_report.md"):
        assert (eval_dir / artifact).exists()
    serialized = "\n".join(
        (eval_dir / artifact).read_text(encoding="utf-8")
        for artifact in ("eval_cases.json", "eval_summary.json", "eval_report.md")
    )
    assert result["cases"][0]["output_dir"] == "[redacted-path]"
    assert "fake-secret-value-123456" not in serialized
    assert "CADFLOW_FAKE_API_KEY" not in serialized
    assert "D:\\private" not in serialized
    assert "D:" not in serialized
    assert "raw provider message" not in serialized
    assert "raw provider response" not in serialized
    assert "raw runtime log" not in serialized
    assert "raw chat transcript" not in serialized
    assert "transcript" not in serialized


def test_provider_create_eval_labels_modes_and_expected_blocked_cases(tmp_path):
    from examples.provider_smoke import provider_create_eval

    class FakeAdapter:
        provider_identity = {"provider": "fake/json", "model": "fake-model"}

    def fake_runner(prompt, adapter, output_dir=None, provider_contract_mode="strict"):
        if "gear" in prompt:
            return {
                "status": "blocked_provider_validation",
                "blocked_stage": "requirement",
                "error_category": "local_validation_failed",
                "output_dir": str(output_dir),
                "provider_create": {
                    "requirement_status": "failed",
                    "planning_status": "not_run",
                    "ir_validation_status": "not_run",
                    "pipeline_status": "not_run",
                    "blocked_stage": "requirement",
                    "error_category": "local_validation_failed",
                    "provider_request_traces": [],
                },
            }
        return {
            "status": "blocked_provider_validation",
            "blocked_stage": "cad_ir",
            "error_category": "cad_ir_validation_failed",
            "output_dir": str(output_dir),
            "provider_create": {
                "requirement_status": "passed",
                "planning_status": "passed",
                "ir_validation_status": "failed",
                "pipeline_status": "not_run",
                "blocked_stage": "cad_ir",
                "error_category": "cad_ir_validation_failed",
                "provider_request_traces": [],
            },
        }

    eval_dir = tmp_path / "eval"
    result = provider_create_eval.run_provider_create_eval(
        adapter=FakeAdapter(),
        provider="fake/json",
        output_dir=eval_dir,
        provider_contract_mode="extract_then_compile",
        cases=[
            {"case_id": "gear_24_teeth", "prompt": "Make a gear with 24 teeth."},
            {"case_id": "button_battery_enclosure_base", "prompt": "Make a small enclosure base for a button and battery."},
        ],
        runner=fake_runner,
    )

    cases = {case["case_id"]: case for case in result["cases"]}
    report = (eval_dir / "eval_report.md").read_text(encoding="utf-8")
    assert result["summary"]["provider_contract_mode"] == "extract_then_compile"
    assert result["summary"]["expected_blocked_count"] == 1
    assert result["summary"]["unexpected_blocked_count"] == 1
    assert cases["gear_24_teeth"]["outcome"] == "expected_blocked"
    assert "unsupported_part_type.gear" in cases["gear_24_teeth"]["validation_error_codes"]
    assert cases["button_battery_enclosure_base"]["outcome"] == "unexpected_blocked"
    assert "cad_ir_validation.failed" in cases["button_battery_enclosure_base"]["validation_error_codes"]
    assert "product-oriented normalized workflow mode" in report
    assert "Strict failures do not automatically imply product workflow failure" in report


def test_provider_create_eval_script_handles_missing_credentials_without_network_or_secret_leak(
    tmp_path,
    monkeypatch,
    capsys,
):
    from examples.provider_smoke import provider_create_eval

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)

    exit_code = provider_create_eval.main([
        "--provider",
        "deepseek",
        "--output-dir",
        str(tmp_path / "eval_missing_credentials"),
    ])

    output = capsys.readouterr().out
    status = json.loads(output)
    assert exit_code == 2
    assert status["provider"] == "deepseek"
    assert status["case_count"] == len(provider_create_eval.DEFAULT_CASES)
    assert status["blocked_count"] == len(provider_create_eval.DEFAULT_CASES)
    assert status["failed_count"] == 0
    assert "DEEPSEEK_API_KEY" not in output
    assert "Authorization" not in output
    assert "Make an 80x40x5" not in output
    assert "messages" not in output


def test_normalized_design_eval_script_handles_missing_credentials_without_secret_leak(
    tmp_path,
    monkeypatch,
    capsys,
):
    from examples.provider_smoke import normalized_design_eval

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)

    exit_code = normalized_design_eval.main([
        "--provider",
        "deepseek",
        "--output-dir",
        str(tmp_path / "normalized_design_eval_missing_credentials"),
    ])

    output = capsys.readouterr().out
    status = json.loads(output)
    assert exit_code == 2
    assert status["provider"] == "deepseek"
    assert status["case_count"] == len(normalized_design_eval.DEFAULT_CASES)
    assert status["blocked_count"] == len(normalized_design_eval.DEFAULT_CASES)
    assert status["failed_count"] == 0
    assert "provider_error.auth_failed" in json.dumps(status)
    assert "DEEPSEEK_API_KEY" not in output
    assert "Authorization" not in output
    assert "messages" not in output


def test_normalized_design_eval_aggregates_classifications(tmp_path):
    from examples.provider_smoke import normalized_design_eval

    class FakeAdapter:
        provider_identity = {"provider": "fake/json", "model": "fake-model"}

    cases = [
        {"case_id": "success_case", "category": "complex_single_part", "prompt": "Make a camera mounting plate."},
        {
            "case_id": "hinge_case",
            "category": "multi_part_assembly_intent",
            "prompt": "Design a simple hinge bracket assembly with two leaves and a pin.",
        },
        {"case_id": "odd_block", "category": "complex_single_part", "prompt": "Make an odd unsupported plate."},
        {"case_id": "runner_failure", "category": "complex_single_part", "prompt": "Make a part that raises."},
    ]

    def fake_runner(prompt, adapter, output_dir=None):
        if "raises" in prompt:
            raise RuntimeError("raw provider response should not be recorded")
        if "hinge" in prompt:
            return {
                "status": "blocked_assembly_generation_not_supported",
                "blocked_stage": "assembly_planning",
                "error_category": "assembly_generation_not_supported_yet",
                "design_brief": {"design_goal": {"scope": "assembly"}},
            }
        if "unsupported plate" in prompt:
            return {
                "status": "blocked_provider_validation",
                "blocked_stage": "cad_ir",
                "error_category": "cad_ir_validation_failed",
                "design_brief": {"design_goal": {"scope": "single_part"}},
            }
        return {
            "status": "success",
            "success": True,
            "design_brief": {"design_goal": {"scope": "single_part"}},
            "candidate_plans": [{"candidate_id": "A"}],
            "selected_plan": {"candidate_id": "A"},
        }

    result = normalized_design_eval.run_normalized_design_eval(
        adapter=FakeAdapter(),
        provider="fake/json",
        output_dir=tmp_path / "eval",
        cases=cases,
        runner=fake_runner,
    )

    summary = result["summary"]
    records = {case["case_id"]: case for case in result["cases"]}
    assert summary["success_count"] == 1
    assert summary["expected_blocked_count"] == 1
    assert summary["unexpected_blocked_count"] == 1
    assert summary["failed_count"] == 1
    assert records["success_case"]["classification"] == "success"
    assert records["hinge_case"]["classification"] == "expected_blocked"
    assert records["odd_block"]["classification"] == "unexpected_blocked"
    assert records["runner_failure"]["classification"] == "failed"


def test_normalized_design_eval_records_assembly_metadata_from_compiled_artifacts(tmp_path):
    from examples.provider_smoke import normalized_design_eval

    class FakeAdapter:
        provider_identity = {"provider": "fake/json", "model": "fake-model"}

    def fake_runner(prompt, adapter, output_dir=None):
        return {
            "status": "blocked_provider_planning",
            "blocked_stage": "planning",
            "error_category": "planning_gate_blocked",
            "intent": {"scope": "assembly"},
            "design_brief": {
                "design_goal": {"scope": "assembly"},
                "parts": [{"name": "leaf_a"}, {"name": "leaf_b"}, {"name": "pin"}],
                "interfaces": [{"kind": "pin_joint"}],
                "risk_notes": [{"kind": "unsupported_scope"}],
            },
            "candidate_plans": [{"candidate_id": "A"}, {"candidate_id": "B"}],
            "selected_plan": {
                "candidate_id": "B",
                "resolved_decisions": {
                    "fasteners": [{"kind": "pin"}],
                    "clearance_notes": ["Leave rotational fit clearance."],
                },
            },
            "planning_artifact": {
                "selected_parts": [{"name": "leaf_a"}, {"name": "leaf_b"}, {"name": "pin"}],
                "fit_interfaces": [{"kind": "pin_joint"}],
            },
            "assembly_plan": {
                "artifact_type": "assembly_plan",
                "parts": [
                    {
                        "part_id": "leaf_a",
                        "role": "hinge leaf",
                        "generation_strategy": "future_part_pipeline",
                        "part_status": "candidate_for_single_part_generation",
                        "supported_candidate": True,
                        "part_brief": "Hinge leaf component with pin interface preserved for future single-part generation.",
                        "blocked_reasons": [],
                    },
                    {
                        "part_id": "leaf_b",
                        "role": "hinge leaf",
                        "generation_strategy": "future_part_pipeline",
                        "part_status": "candidate_for_single_part_generation",
                        "supported_candidate": True,
                        "part_brief": "Hinge leaf component with pin interface preserved for future single-part generation.",
                        "blocked_reasons": [],
                    },
                    {
                        "part_id": "pin",
                        "role": "hinge pin",
                        "generation_strategy": "reference_only",
                        "part_status": "reference_only",
                        "supported_candidate": False,
                        "part_brief": "Hinge pin is recorded as reference hardware, not a primary generated CAD part.",
                        "blocked_reasons": [],
                    },
                ],
                "interfaces": [
                    {"from": "leaf_a", "to": "pin", "kind": "pinned_joint", "notes": "rotating hinge interface"},
                    {"from": "leaf_b", "to": "pin", "kind": "pinned_joint", "notes": "rotating hinge interface"},
                ],
                "fasteners": [],
                "risk_notes": [{"kind": "capability_boundary"}],
                "blocked_reasons": [{"code": "assembly_generation_not_supported_yet"}],
                "quality": {
                    "assembly_plan_count": 1,
                    "part_count": 3,
                    "interface_count": 2,
                    "fastener_count": 0,
                    "risk_note_count": 1,
                    "part_candidate_count": 2,
                    "part_reference_only_count": 1,
                    "part_blocked_count": 0,
                    "part_generation_strategy_counts": {"future_part_pipeline": 2, "reference_only": 1},
                    "part_status_counts": {"candidate_for_single_part_generation": 2, "reference_only": 1},
                    "blocked_reason_codes": ["assembly_generation_not_supported_yet"],
                },
            },
        }

    result = normalized_design_eval.run_normalized_design_eval(
        adapter=FakeAdapter(),
        provider="fake/json",
        output_dir=tmp_path / "eval",
        cases=[{
            "case_id": "hinge_bracket_assembly",
            "category": "multi_part_assembly_intent",
            "prompt": "Design a simple hinge bracket assembly with two leaves and a pin.",
        }],
        runner=fake_runner,
    )

    case = result["cases"][0]
    assert case["detected_scope"] == "assembly"
    assert case["part_count_estimate"] == 3
    assert case["part_list_present"] is True
    assert case["interfaces_present"] is True
    assert case["fasteners_present"] is True
    assert case["clearance_or_fit_notes_present"] is True
    assert case["risk_notes_present"] is True
    assert case["candidate_plan_count"] == 2
    assert case["selected_candidate"] == "B"
    assert case["assembly_plan_count"] == 1
    assert case["part_count"] == 3
    assert case["interface_count"] == 2
    assert case["fastener_count"] == 0
    assert case["risk_note_count"] == 1
    assert case["part_candidate_count"] == 2
    assert case["part_reference_only_count"] == 1
    assert case["part_blocked_count"] == 0
    assert case["part_generation_strategy_counts"] == {"future_part_pipeline": 2, "reference_only": 1}
    assert case["part_status_counts"] == {"candidate_for_single_part_generation": 2, "reference_only": 1}
    assert case["blocked_reason_codes"] == ["assembly_generation_not_supported_yet"]
    assert result["summary"]["assembly_plan_count"] == 1
    assert result["summary"]["part_count"] == 3
    assert result["summary"]["interface_count"] == 2
    assert result["summary"]["risk_note_count"] == 1
    assert result["summary"]["part_candidate_count"] == 2
    assert result["summary"]["part_reference_only_count"] == 1
    assert result["summary"]["part_generation_strategy_counts"] == {"future_part_pipeline": 2, "reference_only": 1}


@pytest.mark.parametrize(
    ("prompt", "expected_scope"),
    [
        (
            "Make a phone stand with a back support, cable slot, and rounded front lip.",
            "single_part_with_features",
        ),
        (
            "Make a small electronics enclosure base with PCB standoffs, battery pocket, and lid screw bosses.",
            "single_part_with_features",
        ),
        (
            "Make a camera mounting plate with tripod hole, four corner holes, and chamfered edges.",
            "single_part_with_features",
        ),
        (
            "Design a two-part electronics enclosure with base and lid, four screws, and PCB standoffs.",
            "multi_part",
        ),
        (
            "Design a simple hinge bracket assembly with two leaves and a pin.",
            "assembly",
        ),
        (
            "Design a small adjustable phone holder made of a base, vertical support, and clamp.",
            "multi_part",
        ),
        (
            "Design a load-bearing drone arm assembly for production.",
            "safety_critical",
        ),
        (
            "Design a gearbox with two gears and exact tooth profiles.",
            "unsupported",
        ),
    ],
)
def test_normalized_design_eval_scope_detection_refines_feature_rich_single_parts(prompt, expected_scope):
    from examples.provider_smoke import normalized_design_eval

    assert normalized_design_eval._detected_scope(prompt, {}) == expected_scope


def test_normalized_design_eval_diagnostic_text_does_not_turn_feature_part_into_assembly():
    from examples.provider_smoke import normalized_design_eval

    artifacts = {
        "requirement": {
            "requirement_status": {
                "diagnostic_codes": [
                    "blocked_policy.requirement_gate_blocked",
                    "compiler.multi_part_requires_assembly_planning",
                ]
            }
        }
    }

    scope = normalized_design_eval._detected_scope(
        "Make a camera mounting plate with tripod hole, four corner holes, and chamfered edges.",
        artifacts,
    )

    assert scope == "single_part_with_features"


def test_normalized_design_eval_classifies_expected_blocked_cases(tmp_path):
    from examples.provider_smoke import normalized_design_eval

    class FakeAdapter:
        provider_identity = {"provider": "fake/json", "model": "fake-model"}

    def fake_runner(prompt, adapter, output_dir=None):
        return {
            "status": "blocked_provider_validation",
            "blocked_stage": "requirement",
            "error_category": "local_validation_failed",
        }

    result = normalized_design_eval.run_normalized_design_eval(
        adapter=FakeAdapter(),
        provider="fake/json",
        output_dir=tmp_path / "eval",
        cases=[
            {
                "case_id": "gearbox_exact_teeth",
                "category": "expected_blocked_over_scoped",
                "prompt": "Design a gearbox with two gears and exact tooth profiles.",
            },
            {
                "case_id": "medical_implant_bracket",
                "category": "expected_blocked_over_scoped",
                "prompt": "Design a medical implant bracket.",
            },
        ],
        runner=fake_runner,
    )

    cases = {case["case_id"]: case for case in result["cases"]}
    assert result["summary"]["expected_blocked_count"] == 2
    assert cases["gearbox_exact_teeth"]["detected_scope"] == "unsupported"
    assert "unsupported.exact_gear_tooth_profiles" in cases["gearbox_exact_teeth"]["diagnostic_codes"]
    assert cases["medical_implant_bracket"]["detected_scope"] == "safety_critical"
    assert "blocked_policy.safety_critical" in cases["medical_implant_bracket"]["diagnostic_codes"]


def test_normalized_design_eval_writes_privacy_safe_reports(tmp_path):
    from examples.provider_smoke import normalized_design_eval

    class FakeAdapter:
        provider_identity = {
            "provider": "fake/json",
            "model": "fake-model",
            "api_key": "fake-secret-value-123456",
        }

    def fake_runner(prompt, adapter, output_dir=None):
        return {
            "status": "blocked_provider_validation",
            "blocked_stage": "cad_ir",
            "error_category": "cad_ir_validation_failed",
            "output_dir": r"D:\private\provider\run",
            "provider_response": "raw provider response",
            "runtime_logs": ["raw runtime log"],
            "transcript": "raw chat transcript",
            "provider_normalized_design_create": {
                "provider_request_traces": [{
                    "messages": ["raw provider message"],
                    "provider_response": "raw provider response",
                }],
            },
            "design_brief": {
                "risk_notes": [{"kind": "missing_information"}],
                "provider_response": "raw provider response",
            },
            "candidate_plans": [{"candidate_id": "A", "cad_ir": {"part_type": "gear"}}],
            "selected_plan": {"candidate_id": "A", "python_code": "print('do not record')"},
            "input_ir": {"part_type": "mounting_plate"},
        }

    eval_dir = tmp_path / "eval"
    normalized_design_eval.run_normalized_design_eval(
        adapter=FakeAdapter(),
        provider="fake/json",
        output_dir=eval_dir,
        cases=[{
            "case_id": "privacy_case",
            "category": "complex_single_part",
            "prompt": "Make a camera mounting plate with four holes.",
        }],
        runner=fake_runner,
    )

    serialized = "\n".join(
        (eval_dir / artifact).read_text(encoding="utf-8")
        for artifact in ("eval_cases.json", "eval_summary.json", "eval_report.md")
    )
    assert "fake-secret-value-123456" not in serialized
    assert "D:\\private" not in serialized
    assert "D:" not in serialized
    assert "raw provider message" not in serialized
    assert "raw provider response" not in serialized
    assert "raw runtime log" not in serialized
    assert "raw chat transcript" not in serialized
    assert "transcript" not in serialized
    assert "python_code" not in serialized
    assert "\"cad_ir\":" not in serialized
    assert "\"part_type\": \"gear\"" not in serialized


def test_provider_create_flow_calls_requirement_and_planning_and_writes_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": _valid_requirement_json(),
        "create_plan": _valid_planning_json(),
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_create_success"

    result = run_provider_create_pipeline("Make a spacer washer.", adapter, output_dir=output_dir)

    assert result["status"] == "success"
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement", "create_plan"]
    assert result["input_ir"]["part_type"] == "spacer"
    for artifact in ("prompt.txt", "requirement.json", "planning_artifact.json", "input_ir.json", "report.json", "agent_trace.json"):
        assert (output_dir / artifact).exists()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))
    runtime = json.loads((output_dir / "logs" / "runtime.json").read_text(encoding="utf-8"))
    provider_traces = trace["provider_create"]["provider_request_traces"]
    assert report["provider_create"]["requirement_status"] == "passed"
    assert report["provider_create"]["planning_status"] == "passed"
    assert report["provider_create"]["ir_validation_status"] == "passed"
    assert [item["operation"] for item in provider_traces] == ["parse_requirement", "create_plan"]
    assert provider_traces[0]["validation_status"] == "passed"
    assert provider_traces[1]["validation_status"] == "passed"
    assert runtime["provider_create"]["provider_request_traces"][0]["message_count"] == 4


def test_provider_create_invalid_requirement_blocks_before_planning(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": {"part_type": "", "dimensions": {}},
        "create_plan": _valid_planning_json(),
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_create_invalid_requirement"

    result = run_provider_create_pipeline("Make a spacer washer.", adapter, output_dir=output_dir)

    assert result["status"] == "blocked_provider_validation"
    assert result["blocked_stage"] == "requirement"
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement"]
    assert not (output_dir / "requirement.json").exists()
    assert not (output_dir / "planning_artifact.json").exists()
    assert not (output_dir / "input_ir.json").exists()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["error_category"] == "local_validation_failed"
    assert report["part_modeling_started"] is False


def test_provider_create_invalid_planning_blocks_in_strict_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": _valid_requirement_json(),
        "create_plan": {
            "artifact_type": "plan",
            "route": {},
            "selected_parts": [],
            "flow_gate_status": {},
        },
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_create_invalid_planning"

    result = run_provider_create_pipeline("Make a spacer washer.", adapter, output_dir=output_dir)

    assert result["status"] == "blocked_provider_validation"
    assert result["blocked_stage"] == "planning"
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement", "create_plan"]
    assert (output_dir / "requirement.json").exists()
    assert not (output_dir / "planning_artifact.json").exists()
    assert not (output_dir / "input_ir.json").exists()


def test_provider_create_compiles_provider_requirement_and_explicitly_falls_back_to_local_planning(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": {
            "part_type": "mounting_plate",
            "unit": "mm",
            "dimensions": {"length": 80, "width": 40, "thickness": 5},
            "features": [
                {"kind": "holes", "count": 4, "diameter_mm": 4.5, "pattern": "corner"},
            ],
            "requirement_status": "ready",
        },
        "create_plan": {
            "artifact_type": "plan",
            "route": {},
            "selected_parts": [],
            "flow_gate_status": {},
        },
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_create_compiled"

    result = run_provider_create_pipeline(
        "Make an 80x40x5 mm mounting plate with four M4 holes.",
        adapter,
        output_dir=output_dir,
        provider_contract_mode="extract_then_compile",
    )

    assert result["status"] == "success"
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement", "create_plan"]
    assert result["requirement"]["features"]["holes"]["count"] == 4
    assert result["requirement"]["requirement_status"]["complete_for_generation"] is True
    assert (output_dir / "requirement.json").exists()
    assert (output_dir / "planning_artifact.json").exists()
    assert (output_dir / "input_ir.json").exists()


def test_provider_normalized_create_pipeline_is_explicit_and_records_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": {
            "part_type": "mounting_plate",
            "unit": "mm",
            "dimensions": {"length": 80, "width": 40, "thickness": 5},
            "features": {"holes": {"count": 4, "diameter": 4.5, "positions": "corner_4"}},
        },
        "create_plan": {
            "artifact_type": "plan",
            "route": {},
            "selected_parts": [],
            "flow_gate_status": {},
        },
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_normalized_create"

    result = run_provider_normalized_create_pipeline(
        "Make an 80x40x5 mm mounting plate with four M4 holes.",
        adapter,
        output_dir=output_dir,
    )

    assert result["status"] == "success"
    assert fake_client.requests[0]["context"]["provider_contract_mode"] == "extract_then_compile"
    assert fake_client.requests[1]["context"]["provider_contract_mode"] == "extract_then_compile"
    provider_create = result["provider_create"]
    assert provider_create["provider_contract_mode"] == "extract_then_compile"
    assert provider_create["workflow_mode"] == "normalized_provider_create"
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    runtime = json.loads((output_dir / "logs" / "runtime.json").read_text(encoding="utf-8"))
    assert report["provider_create"]["provider_contract_mode"] == "extract_then_compile"
    assert runtime["provider_create"]["workflow_mode"] == "normalized_provider_create"


def test_provider_normalized_design_create_pipeline_writes_local_design_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": {
            "part_type": "mounting_plate",
            "unit": "mm",
            "dimensions": {"length": 80, "width": 40, "thickness": 5},
            "features": {"holes": {"count": 4, "diameter": 4.5, "positions": "corner_4"}},
            "assumptions": ["Use standard clearance for M4 holes."],
        },
        "create_plan": {
            "artifact_type": "planning",
            "route": {},
            "selected_parts": [],
            "flow_gate_status": {},
        },
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_normalized_design_create"

    result = run_provider_normalized_design_create_pipeline(
        "Make an 80x40x5 mm mounting plate with four M4 holes.",
        adapter,
        output_dir=output_dir,
    )

    assert result["status"] == "success"
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement"]
    assert fake_client.requests[0]["context"]["workflow_stage"] == "provider_normalized_design_create"
    assert fake_client.requests[0]["context"]["provider_contract_mode"] == "extract_then_compile"
    assert result["intent"]["artifact_type"] == "intent"
    assert result["design_brief"]["artifact_type"] == "design_brief"
    assert result["candidate_plans"][0]["candidate_id"] == "A"
    assert result["selected_plan"]["candidate_id"] == "A"
    assert result["requirement"]["part_type"] == "mounting_plate"
    assert result["planning_artifact"]["artifact_type"] == "planning"
    assert result["input_ir"]["part_type"] == "mounting_plate"
    assert result["provider_normalized_design_create"]["workflow_mode"] == "normalized_design_create"
    for artifact in (
        "prompt.txt",
        "intent.json",
        "design_brief.json",
        "candidate_plans.json",
        "selected_plan.json",
        "requirement.json",
        "planning_artifact.json",
        "input_ir.json",
        "report.json",
        "report.md",
        "agent_trace.json",
    ):
        assert (output_dir / artifact).exists()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    report_md = (output_dir / "report.md").read_text(encoding="utf-8")
    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))
    assert report["provider_normalized_design_create"]["selected_candidate"] == "A"
    assert str(output_dir) not in json.dumps(report, sort_keys=True)
    assert str(output_dir) not in report_md
    assert trace["provider_normalized_design_create"]["provider_role"] == "extract_design_signals_only"


def test_provider_normalized_design_create_ignores_provider_ir_code_and_arbitrary_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": {
            "part_type": "mounting_plate",
            "unit": "mm",
            "dimensions": {"length": 80, "width": 40, "thickness": 5, "unsafe_extra": 999},
            "features": {
                "holes": {"count": 4, "diameter": 4.5, "positions": "corner_4"},
                "laser": {"power": 1000},
            },
            "intent_json": {"artifact_type": "intent", "recognized_part_type": "gear"},
            "design_brief": {"part_type": "gear"},
            "candidate_plans": [{"cad_ir": {"part_type": "gear"}}],
            "input_ir": {"part_type": "gear", "dimensions": {"teeth": 24}},
            "cadquery_code": "import cadquery as cq",
            "python_code": "print('provider code must not run')",
        },
        "create_plan": {
            "artifact_type": "planning",
            "selected_parts": [],
            "cadquery_code": "import cadquery as cq",
        },
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_normalized_design_no_ir"

    result = run_provider_normalized_design_create_pipeline(
        "Make an 80x40x5 mm mounting plate with four M4 holes.",
        adapter,
        output_dir=output_dir,
    )

    assert result["status"] == "success"
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement"]
    assert result["intent"]["recognized_part_type"] == "mounting_plate"
    assert result["design_brief"]["part_type"] == "mounting_plate"
    assert result["input_ir"]["dimensions"] == {"length": 80, "thickness": 5, "width": 40}
    assert all("cad_ir" not in candidate for candidate in result["candidate_plans"])
    serialized = json.dumps({
        "intent": result["intent"],
        "design_brief": result["design_brief"],
        "candidate_plans": result["candidate_plans"],
        "selected_plan": result["selected_plan"],
        "requirement": result["requirement"],
        "planning_artifact": result["planning_artifact"],
        "input_ir": result["input_ir"],
    }, sort_keys=True)
    assert "unsafe_extra" not in serialized
    assert "laser" not in serialized
    assert "cadquery_code" not in serialized
    assert "python_code" not in serialized
    assert "\"part_type\": \"gear\"" not in serialized


@pytest.mark.parametrize(
    ("prompt", "provider_requirement", "expected_status", "expected_scope", "expected_code"),
    [
        (
            "Design a two-part electronics enclosure with base and lid, four screws, and PCB standoffs.",
            {
                "part_type": "electronics_enclosure",
                "scope": "single_part",
                "dimensions": {"length": 100, "width": 60, "height": 30},
                "features": {"standoffs": {"count": 4}, "screws": {"count": 4}},
                "input_ir": {"part_type": "gear"},
                "cadquery_code": "import cadquery as cq",
                "unsafe_extra": {"secret": "provider value"},
            },
            "blocked_multi_part_generation_not_supported",
            "multi_part",
            "compiler.multi_part_requires_assembly_planning",
        ),
        (
            "Design a simple hinge bracket assembly with two leaves and a pin.",
            {
                "part_type": "hinge_bracket",
                "scope": "single_part",
                "dimensions": {"length": 60, "width": 30, "height": 10},
                "features": {"pin": {"diameter": 4}},
                "python_code": "print('provider code must not run')",
            },
            "blocked_assembly_generation_not_supported",
            "assembly",
            "compiler.assembly_requires_assembly_planning",
        ),
    ],
)
def test_provider_normalized_design_create_writes_assembly_plan_without_cad_execution(
    prompt,
    provider_requirement,
    expected_status,
    expected_scope,
    expected_code,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    called = {"run_ir_pipeline": False}

    def fake_run_ir_pipeline(*args, **kwargs):
        called["run_ir_pipeline"] = True
        raise AssertionError("assembly planning MVP must not run CAD execution")

    monkeypatch.setattr(pipeline_runner, "run_ir_pipeline", fake_run_ir_pipeline)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": provider_requirement,
        "create_plan": _valid_planning_json(),
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_normalized_design_assembly_plan"

    result = run_provider_normalized_design_create_pipeline(prompt, adapter, output_dir=output_dir)

    assert result["status"] == expected_status
    assert result["blocked_stage"] == "assembly_planning"
    assert result["assembly_plan"]["artifact_type"] == "assembly_plan"
    assert result["assembly_plan"]["scope"] == expected_scope
    assert result["assembly_plan"]["status"] == "blocked_before_part_generation"
    assert expected_code in result["assembly_plan"]["diagnostic_codes"]
    assert "assembly.plan_created" in result["assembly_plan"]["diagnostic_codes"]
    assert "assembly.parts_detected" in result["assembly_plan"]["diagnostic_codes"]
    assert "assembly.interfaces_detected" in result["assembly_plan"]["diagnostic_codes"]
    assert "assembly.generation_not_supported_yet" in result["diagnostic_codes"]
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement"]
    assert called["run_ir_pipeline"] is False
    assert (output_dir / "assembly_plan.json").exists()
    assert (output_dir / "intent.json").exists()
    assert (output_dir / "design_brief.json").exists()
    assert (output_dir / "candidate_plans.json").exists()
    assert (output_dir / "selected_plan.json").exists()
    assert (output_dir / "requirement.json").exists()
    assert (output_dir / "report.json").exists()
    assert (output_dir / "report.md").exists()
    assert (output_dir / "agent_trace.json").exists()
    assert not (output_dir / "input_ir.json").exists()
    assert not (output_dir / "planning_artifact.json").exists()

    assembly_plan = json.loads((output_dir / "assembly_plan.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))
    serialized = json.dumps({"assembly_plan": assembly_plan, "report": report, "trace": trace}, sort_keys=True)
    assert assembly_plan["parts"]
    expected_part_keys = {
        "part_id",
        "role",
        "generation_strategy",
        "part_status",
        "supported_candidate",
        "part_brief",
        "blocked_reasons",
    }
    assert all(set(part) == expected_part_keys for part in assembly_plan["parts"])
    assert all(part["generation_strategy"] in {"future_part_pipeline", "reference_only", "blocked"} for part in assembly_plan["parts"])
    assert all(part["part_status"] in {"planned_only", "candidate_for_single_part_generation", "reference_only", "blocked"} for part in assembly_plan["parts"])
    assert all(part["part_id"] == pipeline_runner._safe_artifact_id(part["part_id"]) for part in assembly_plan["parts"])
    assert all(isinstance(part["supported_candidate"], bool) for part in assembly_plan["parts"])
    assert all(isinstance(part["part_brief"], str) and part["part_brief"] for part in assembly_plan["parts"])
    assert all(isinstance(part["blocked_reasons"], list) for part in assembly_plan["parts"])
    assert all(set(interface) == {"from", "to", "kind", "notes"} for interface in assembly_plan["interfaces"])
    assert all(
        interface["kind"] in {"screw_fastened", "pinned_joint", "sliding_fit", "snap_fit", "stacked", "unknown"}
        for interface in assembly_plan["interfaces"]
    )
    assert assembly_plan["quality"]["assembly_plan_count"] == 1
    assert assembly_plan["quality"]["part_count"] == len(assembly_plan["parts"])
    assert assembly_plan["quality"]["interface_count"] == len(assembly_plan["interfaces"])
    assert assembly_plan["quality"]["fastener_count"] == len(assembly_plan["fasteners"])
    assert assembly_plan["quality"]["risk_note_count"] == len(assembly_plan["risk_notes"])
    assert assembly_plan["quality"]["part_candidate_count"] == sum(1 for part in assembly_plan["parts"] if part["supported_candidate"])
    assert assembly_plan["quality"]["part_reference_only_count"] == sum(1 for part in assembly_plan["parts"] if part["part_status"] == "reference_only")
    assert assembly_plan["quality"]["part_blocked_count"] == sum(1 for part in assembly_plan["parts"] if part["part_status"] == "blocked")
    assert assembly_plan["blocked_reasons"][0]["code"] == "assembly_generation_not_supported_yet"
    assert report["cad_ir_created"] is False
    assert report["part_modeling_started"] is False
    assert report["assembly_plan_count"] == 1
    assert report["part_count"] == len(assembly_plan["parts"])
    assert report["interface_count"] == len(assembly_plan["interfaces"])
    assert report["fastener_count"] == len(assembly_plan["fasteners"])
    assert report["risk_note_count"] == len(assembly_plan["risk_notes"])
    assert report["part_candidate_count"] == assembly_plan["quality"]["part_candidate_count"]
    assert report["part_reference_only_count"] == assembly_plan["quality"]["part_reference_only_count"]
    assert report["part_blocked_count"] == assembly_plan["quality"]["part_blocked_count"]
    assert report["part_generation_strategy_counts"] == assembly_plan["quality"]["part_generation_strategy_counts"]
    assert report["part_status_counts"] == assembly_plan["quality"]["part_status_counts"]
    assert report["blocked_reason_codes"] == ["assembly_generation_not_supported_yet"]
    assert trace["provider_normalized_design_create"]["assembly_plan_created"] is True
    assert trace["provider_normalized_design_create"]["assembly_plan_quality"]["part_count"] == len(assembly_plan["parts"])
    assert "input_ir" not in trace["provider_normalized_design_create"]["artifacts"]
    assert "run_ir_pipeline" not in trace["provider_normalized_design_create"]["stages"]
    assert "input_ir" not in serialized
    assert "cadquery_code" not in serialized
    assert "python_code" not in serialized
    assert "unsafe_extra" not in serialized
    assert "provider value" not in serialized
    if "two-part electronics enclosure" in prompt:
        parts_by_id = {part["part_id"]: part for part in assembly_plan["parts"]}
        assert parts_by_id["base"]["part_status"] == "candidate_for_single_part_generation"
        assert parts_by_id["base"]["supported_candidate"] is True
        assert parts_by_id["lid"]["part_status"] == "candidate_for_single_part_generation"
        assert parts_by_id["lid"]["supported_candidate"] is True
        assert all(part["part_id"] != "screws" for part in assembly_plan["parts"])
        assert assembly_plan["fasteners"] == [{"kind": "screw", "quantity": 4}]
        assert assembly_plan["quality"]["part_candidate_count"] == 2
        assert assembly_plan["quality"]["part_reference_only_count"] == 0


def test_assembly_plan_normalization_is_stable_sanitized_and_non_executable():
    raw_parts = [
        {"part_id": "Base Plate!", "role": "main base\nwith extra detail", "generation_strategy": "provider_code"},
        {"part_id": "Base Plate!", "role": "duplicate base"},
        {"part_id": "Pin #1", "role": "hinge pin"},
    ]
    raw_interfaces = [
        {"from": "Base Plate!", "to": "Pin #1", "kind": "pin_joint", "notes": "rotates\nwithout solving motion"},
        {"from": "external part", "to": "Base Plate!", "kind": "provider_custom_kind", "notes": "unsafe <script> note"},
    ]

    first_parts = pipeline_runner._normalize_assembly_plan_parts(raw_parts, prompt="Design a hinge with a base plate and pin.")
    second_parts = pipeline_runner._normalize_assembly_plan_parts(raw_parts, prompt="Design a hinge with a base plate and pin.")
    interfaces = pipeline_runner._normalize_assembly_plan_interfaces(raw_interfaces, first_parts)

    assert first_parts == second_parts
    assert [part["part_id"] for part in first_parts] == ["base_plate", "base_plate_2", "pin_1"]
    assert [part["generation_strategy"] for part in first_parts] == ["future_part_pipeline", "future_part_pipeline", "reference_only"]
    assert [part["part_status"] for part in first_parts] == [
        "candidate_for_single_part_generation",
        "candidate_for_single_part_generation",
        "reference_only",
    ]
    assert interfaces[0]["kind"] == "pinned_joint"
    assert interfaces[1]["kind"] == "unknown"
    assert all("\n" not in interface["notes"] for interface in interfaces)
    serialized = json.dumps({"parts": first_parts, "interfaces": interfaces}, sort_keys=True)
    assert "provider_code" not in serialized
    assert "provider_custom_kind" not in serialized
    assert "<script>" not in serialized


def test_assembly_plan_part_decomposition_blocks_unsupported_parts_without_generation():
    parts = pipeline_runner._normalize_assembly_plan_parts(
        [
            {"part_id": "gear", "role": "drive gear"},
            {"part_id": "medical_bracket", "role": "medical implant bracket"},
            {"part_id": "lid", "role": "cover component"},
        ],
        prompt="Design an assembly with a gear and medical implant bracket.",
    )

    by_id = {part["part_id"]: part for part in parts}
    assert by_id["gear"]["generation_strategy"] == "blocked"
    assert by_id["gear"]["part_status"] == "blocked"
    assert by_id["gear"]["supported_candidate"] is False
    assert by_id["medical_bracket"]["generation_strategy"] == "blocked"
    assert by_id["medical_bracket"]["blocked_reasons"]
    assert by_id["lid"]["generation_strategy"] == "blocked"
    serialized = json.dumps(parts, sort_keys=True)
    assert "cadquery_code" not in serialized
    assert "python_code" not in serialized
    assert "input_ir" not in serialized


def _part_request_assembly_plan():
    return {
        "artifact_type": "assembly_plan",
        "schema_version": "0.1",
        "scope": "multi_part",
        "status": "blocked_before_part_generation",
        "parts": [
            {
                "part_id": "base",
                "role": "main housing base",
                "generation_strategy": "future_part_pipeline",
                "part_status": "candidate_for_single_part_generation",
                "supported_candidate": True,
                "part_brief": "Base component with PCB standoffs and screw bosses.",
                "blocked_reasons": [],
                "provider_extra": "must not pass through",
                "cad_ir": {"part_type": "enclosure_base"},
                "python_code": "import cadquery as cq",
            },
            {
                "part_id": "lid",
                "role": "cover component",
                "generation_strategy": "future_part_pipeline",
                "part_status": "candidate_for_single_part_generation",
                "supported_candidate": True,
                "part_brief": "Lid component.",
                "blocked_reasons": [],
            },
            {
                "part_id": "screws",
                "role": "reference screws",
                "generation_strategy": "reference_only",
                "part_status": "reference_only",
                "supported_candidate": False,
                "part_brief": "Reference hardware.",
                "blocked_reasons": [],
            },
            {
                "part_id": "gear",
                "role": "drive gear",
                "generation_strategy": "blocked",
                "part_status": "blocked",
                "supported_candidate": False,
                "part_brief": "Unsupported gear.",
                "blocked_reasons": [{"code": "unsupported_part_family"}],
            },
        ],
        "interfaces": [
            {"from": "base", "to": "lid", "kind": "screw_fastened", "notes": "Screw holes should align with lid."},
            {"from": "screws", "to": "base", "kind": "unknown", "notes": "Reference screw envelope only."},
            {"from": "lid", "to": "gear", "kind": "provider_kind", "notes": "provider-only detail"},
        ],
        "fasteners": [{"kind": "screw", "quantity": 4, "raw_provider_notes": "secret"}],
        "provider_response": {"raw": "must not pass through"},
    }


def test_part_create_request_pipeline_writes_candidate_request_without_cad_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    called = {"run_ir_pipeline": False}

    def fake_run_ir_pipeline(*args, **kwargs):
        called["run_ir_pipeline"] = True
        raise AssertionError("part request MVP must not run CAD execution")

    monkeypatch.setattr(pipeline_runner, "run_ir_pipeline", fake_run_ir_pipeline)
    output_dir = tmp_path / "outputs" / "part_request"
    assembly_path = output_dir / "assembly_plan.json"
    output_dir.mkdir(parents=True)
    assembly_path.write_text(json.dumps(_part_request_assembly_plan()), encoding="utf-8")

    result = run_assembly_part_request_pipeline(assembly_path, output_dir=output_dir)

    assert result["status"] == "ready_for_review"
    assert called["run_ir_pipeline"] is False
    assert (output_dir / "part_create_request.json").exists()
    assert (output_dir / "report.json").exists()
    assert (output_dir / "report.md").exists()
    assert (output_dir / "agent_trace.json").exists()
    assert not (output_dir / "input_ir.json").exists()
    assert not (output_dir / "base" / "input_ir.json").exists()
    assert not (output_dir / "model.step").exists()
    assert not (output_dir / "model.stl").exists()

    request = json.loads((output_dir / "part_create_request.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))
    assert request == result["part_create_request"]
    assert request["artifact_type"] == "part_create_request"
    assert request["schema_version"] == "0.1"
    assert request["source_artifact"] == "assembly_plan.json"
    assert request["part_id"] == "base"
    assert request["part_role"] == "main housing base"
    assert request["generation_mode"] == "single_part_candidate"
    assert request["status"] == "ready_for_review"
    assert request["blocked_reasons"] == []
    assert "part_request.created" in request["diagnostic_codes"]
    assert "part_request.interface_constraints_preserved" in request["diagnostic_codes"]
    assert {
        "kind": "screw_alignment",
        "related_part_id": "lid",
        "notes": "Screw holes should align with lid.",
    } in request["interface_constraints"]
    assert request["preserved_assembly_context"]["assembly_scope"] == "multi_part"
    assert request["preserved_assembly_context"]["related_parts"] == ["lid", "screws", "gear"]
    assert report["cad_ir_created"] is False
    assert report["part_modeling_started"] is False
    assert trace["assembly_part_request"]["cad_ir_created"] is False
    assert "run_ir_pipeline" not in json.dumps(trace, sort_keys=True)


@pytest.mark.parametrize(
    ("part_id", "expected_code"),
    [
        ("screws", "part_request.reference_only_not_selectable"),
        ("gear", "part_request.blocked_part_not_selectable"),
    ],
)
def test_part_create_request_rejects_reference_only_and_blocked_parts(tmp_path, monkeypatch, part_id, expected_code):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    output_dir = tmp_path / "outputs" / f"part_request_{part_id}"

    result = run_assembly_part_request_pipeline(_part_request_assembly_plan(), output_dir=output_dir, part_id=part_id)

    request = result["part_create_request"]
    assert result["status"] == "blocked_no_candidate_part"
    assert request["status"] == "blocked_no_candidate_part"
    assert request["part_id"] == part_id
    assert request["blocked_reasons"] == [{"code": expected_code}]
    assert request["diagnostic_codes"] == [expected_code]
    assert not (output_dir / "input_ir.json").exists()


def test_part_create_request_no_candidate_produces_blocked_request(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    plan = _part_request_assembly_plan()
    plan["parts"] = [part for part in plan["parts"] if part["part_status"] != "candidate_for_single_part_generation"]
    output_dir = tmp_path / "outputs" / "part_request_no_candidate"

    result = run_assembly_part_request_pipeline(plan, output_dir=output_dir)

    request = result["part_create_request"]
    assert result["status"] == "blocked_no_candidate_part"
    assert request["part_id"] is None
    assert request["blocked_reasons"] == [{"code": "part_request.no_candidate_part"}]
    assert request["interface_constraints"] == []
    assert not (output_dir / "input_ir.json").exists()


def test_part_create_request_is_sanitized_and_contains_no_provider_cad_or_private_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    output_dir = tmp_path / "outputs" / "part_request_privacy"

    result = run_assembly_part_request_pipeline(_part_request_assembly_plan(), output_dir=output_dir)

    request = json.loads((output_dir / "part_create_request.json").read_text(encoding="utf-8"))
    serialized = json.dumps({
        "result": result,
        "request": request,
        "report": json.loads((output_dir / "report.json").read_text(encoding="utf-8")),
        "trace": json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8")),
    }, sort_keys=True)
    request_serialized = json.dumps(request, sort_keys=True)
    assert "provider_extra" not in serialized
    assert "provider_response" not in serialized
    assert "raw_provider_notes" not in serialized
    assert "must not pass through" not in serialized
    assert "cad_ir" not in request_serialized
    assert "python_code" not in request_serialized
    assert "cadquery" not in request_serialized.lower()
    assert "D:\\" not in serialized
    assert "api_key" not in serialized
    assert "transcript" not in serialized


def _valid_part_create_request():
    return pipeline_runner.create_part_request_from_assembly_plan(_part_request_assembly_plan())


def test_part_request_review_pipeline_approves_valid_candidate_request(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    called = {"run_ir_pipeline": False}

    def fake_run_ir_pipeline(*args, **kwargs):
        called["run_ir_pipeline"] = True
        raise AssertionError("part request review MVP must not run CAD execution")

    monkeypatch.setattr(pipeline_runner, "run_ir_pipeline", fake_run_ir_pipeline)
    output_dir = tmp_path / "outputs" / "part_request_review"
    request_path = output_dir / "part_create_request.json"
    output_dir.mkdir(parents=True)
    request_path.write_text(json.dumps(_valid_part_create_request()), encoding="utf-8")

    result = run_part_request_review_pipeline(request_path, output_dir=output_dir)

    assert result["status"] == "approved"
    assert result["success"] is True
    assert called["run_ir_pipeline"] is False
    assert (output_dir / "part_request_review.json").exists()
    assert (output_dir / "report.json").exists()
    assert (output_dir / "report.md").exists()
    assert (output_dir / "agent_trace.json").exists()
    assert not (output_dir / "input_ir.json").exists()
    assert not (output_dir / "model.step").exists()
    assert not (output_dir / "model.stl").exists()

    review = json.loads((output_dir / "part_request_review.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))
    assert review == result["part_request_review"]
    assert review["artifact_type"] == "part_request_review"
    assert review["schema_version"] == "0.1"
    assert review["source_artifact"] == "part_create_request.json"
    assert review["part_id"] == "base"
    assert review["status"] == "approved"
    assert review["review_result"] == "approved_for_single_part_planning"
    assert review["checks"] == {
        "has_part_brief": True,
        "has_interface_constraints": True,
        "is_reference_only": False,
        "is_blocked": False,
        "has_provider_generated_code": False,
        "has_provider_generated_cad_ir": False,
        "has_arbitrary_provider_fields": False,
        "has_clear_related_parts": True,
    }
    assert "part_request.review_created" in review["diagnostic_codes"]
    assert "part_request.approved_for_single_part_planning" in review["diagnostic_codes"]
    assert review["blocked_reasons"] == []
    assert review["revision_notes"] == []
    assert report["cad_ir_created"] is False
    assert report["part_modeling_started"] is False
    assert trace["part_request_review"]["cad_ir_created"] is False
    assert "run_ir_pipeline" not in json.dumps(trace, sort_keys=True)


def test_part_request_review_missing_part_brief_needs_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    request = _valid_part_create_request()
    request["part_brief"] = "part"

    result = run_part_request_review_pipeline(request, output_dir=tmp_path / "outputs" / "review_missing_brief")

    review = result["part_request_review"]
    assert result["status"] == "needs_revision"
    assert review["review_result"] == "needs_revision_missing_part_brief"
    assert review["checks"]["has_part_brief"] is False
    assert "part_request.needs_revision_missing_part_brief" in review["diagnostic_codes"]
    assert review["revision_notes"]


def test_part_request_review_missing_assembly_interfaces_needs_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    request = _valid_part_create_request()
    request["interface_constraints"] = []

    result = run_part_request_review_pipeline(request, output_dir=tmp_path / "outputs" / "review_missing_interfaces")

    review = result["part_request_review"]
    assert result["status"] == "needs_revision"
    assert review["review_result"] == "needs_revision_missing_interface_constraints"
    assert review["checks"]["has_interface_constraints"] is False
    assert "part_request.needs_revision_missing_interface_constraints" in review["diagnostic_codes"]


@pytest.mark.parametrize(
    ("part_request_payload", "expected_code", "expected_result"),
    [
        (
            {
                **_valid_part_create_request(),
                "part_id": "screws",
                "status": "blocked_no_candidate_part",
                "blocked_reasons": [{"code": "part_request.reference_only_not_selectable"}],
                "diagnostic_codes": ["part_request.reference_only_not_selectable"],
            },
            "part_request.blocked_reference_only",
            "blocked_reference_only",
        ),
        (
            {
                **_valid_part_create_request(),
                "part_id": "gear",
                "status": "blocked_no_candidate_part",
                "blocked_reasons": [{"code": "part_request.blocked_part_not_selectable"}],
                "diagnostic_codes": ["part_request.blocked_part_not_selectable"],
            },
            "part_request.blocked_unsupported_part",
            "blocked_unsupported_part",
        ),
    ],
)
def test_part_request_review_blocks_reference_only_and_unsupported_requests(
    tmp_path,
    monkeypatch,
    part_request_payload,
    expected_code,
    expected_result,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)

    result = run_part_request_review_pipeline(part_request_payload, output_dir=tmp_path / "outputs" / expected_result)

    review = result["part_request_review"]
    assert result["status"] == "blocked"
    assert review["review_result"] == expected_result
    assert expected_code in review["diagnostic_codes"]
    assert {"code": expected_code} in review["blocked_reasons"]
    assert not (Path(result["output_dir"]) / "input_ir.json").exists()


@pytest.mark.parametrize(
    ("extra", "expected_code", "check_name"),
    [
        ({"python_code": "import cadquery as cq"}, "part_request.blocked_provider_generated_code", "has_provider_generated_code"),
        ({"cad_ir": {"part_type": "spacer"}}, "part_request.blocked_provider_generated_cad_ir", "has_provider_generated_cad_ir"),
        ({"provider_response": {"raw": "secret provider payload"}}, "part_request.blocked_provider_generated_code", "has_arbitrary_provider_fields"),
    ],
)
def test_part_request_review_blocks_provider_generated_or_arbitrary_provider_fields(
    tmp_path,
    monkeypatch,
    extra,
    expected_code,
    check_name,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    request = {**_valid_part_create_request(), **extra}

    result = run_part_request_review_pipeline(request, output_dir=tmp_path / "outputs" / f"review_{check_name}")

    review = result["part_request_review"]
    assert result["status"] == "blocked"
    assert review["checks"][check_name] is True
    assert expected_code in review["diagnostic_codes"]
    assert {"code": expected_code} in review["blocked_reasons"]


def test_part_request_review_artifact_is_sanitized(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    request = {
        **_valid_part_create_request(),
        "provider_response": {"raw": "secret provider payload"},
        "raw_transcript": "private transcript",
        "api_key": "secret",
        "local_path": r"D:\private\run",
        "python_code": "import cadquery as cq",
        "cad_ir": {"part_type": "spacer"},
    }
    output_dir = tmp_path / "outputs" / "review_privacy"

    result = run_part_request_review_pipeline(request, output_dir=output_dir)

    review = json.loads((output_dir / "part_request_review.json").read_text(encoding="utf-8"))
    serialized = json.dumps({
        "result": result,
        "review": review,
        "report": json.loads((output_dir / "report.json").read_text(encoding="utf-8")),
        "trace": json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8")),
    }, sort_keys=True)
    review_serialized = json.dumps(review, sort_keys=True)
    assert "secret provider payload" not in serialized
    assert "private transcript" not in serialized
    assert "api_key" not in serialized
    assert "D:\\private" not in serialized
    assert "python_code" not in review_serialized
    assert "\"cad_ir\": {" not in review_serialized
    assert "import cadquery" not in serialized.lower()


def test_part_request_review_exports_are_available():
    import ai_native_cad.pipeline as pipeline

    assert pipeline.review_part_create_request is review_part_create_request
    assert pipeline.run_part_request_review_pipeline is run_part_request_review_pipeline
    assert "review_part_create_request" in pipeline.__all__
    assert "run_part_request_review_pipeline" in pipeline.__all__


def test_reviewed_part_handoff_pipeline_writes_ready_handoff_without_cad_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    called = {"run_ir_pipeline": False}

    def fake_run_ir_pipeline(*args, **kwargs):
        called["run_ir_pipeline"] = True
        raise AssertionError("reviewed part handoff MVP must not run CAD execution")

    monkeypatch.setattr(pipeline_runner, "run_ir_pipeline", fake_run_ir_pipeline)
    output_dir = tmp_path / "outputs" / "reviewed_part_handoff"
    output_dir.mkdir(parents=True)
    request = _valid_part_create_request()
    review = review_part_create_request(request)
    request_path = output_dir / "part_create_request.json"
    review_path = output_dir / "part_request_review.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    review_path.write_text(json.dumps(review), encoding="utf-8")

    result = run_reviewed_part_handoff_pipeline(request_path, review_path, output_dir=output_dir)

    assert result["status"] == "ready_for_single_part_planning"
    assert result["success"] is True
    assert called["run_ir_pipeline"] is False
    assert (output_dir / "reviewed_part_handoff.json").exists()
    assert (output_dir / "report.json").exists()
    assert (output_dir / "report.md").exists()
    assert (output_dir / "agent_trace.json").exists()
    assert not (output_dir / "input_ir.json").exists()
    assert not (output_dir / "model.step").exists()
    assert not (output_dir / "model.stl").exists()

    handoff = json.loads((output_dir / "reviewed_part_handoff.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))
    assert handoff == result["reviewed_part_handoff"]
    assert handoff["artifact_type"] == "reviewed_part_handoff"
    assert handoff["schema_version"] == "0.1"
    assert handoff["source_part_request"] == "part_create_request.json"
    assert handoff["source_review"] == "part_request_review.json"
    assert handoff["part_id"] == "base"
    assert handoff["status"] == "ready_for_single_part_planning"
    assert "Create the base component as a single CAD part." in handoff["single_part_prompt"]
    assert handoff["part_brief"] == "Base component with PCB standoffs and screw bosses."
    assert {
        "kind": "screw_alignment",
        "related_part_id": "lid",
        "notes": "fastener clearance/alignment features",
    } in handoff["interface_constraints"]
    assert handoff["preserved_assembly_context"]["assembly_scope"] == "multi_part"
    assert handoff["preserved_assembly_context"]["related_parts"] == ["lid", "screws", "gear"]
    assert "part_handoff.created" in handoff["diagnostic_codes"]
    assert "part_handoff.ready_for_single_part_planning" in handoff["diagnostic_codes"]
    assert handoff["blocked_reasons"] == []
    assert report["cad_ir_created"] is False
    assert report["part_modeling_started"] is False
    assert trace["reviewed_part_handoff"]["cad_ir_created"] is False
    assert "run_ir_pipeline" not in json.dumps(trace, sort_keys=True)


@pytest.mark.parametrize(
    ("review_status", "review_result", "expected_status", "expected_code"),
    [
        ("needs_revision", "needs_revision_missing_part_brief", "blocked_review_not_approved", "part_handoff.blocked_review_not_approved"),
        (
            "needs_revision",
            "needs_revision_missing_interface_constraints",
            "needs_revision_missing_interface_constraints",
            "part_handoff.needs_revision_missing_interface_constraints",
        ),
        ("blocked", "blocked_unsupported_part", "blocked_review_not_approved", "part_handoff.blocked_review_not_approved"),
    ],
)
def test_reviewed_part_handoff_non_approved_review_blocks_or_needs_revision(
    tmp_path,
    monkeypatch,
    review_status,
    review_result,
    expected_status,
    expected_code,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    request = _valid_part_create_request()
    review = {
        **review_part_create_request(request),
        "status": review_status,
        "review_result": review_result,
    }

    result = run_reviewed_part_handoff_pipeline(
        request,
        review,
        output_dir=tmp_path / "outputs" / f"handoff_{expected_status}",
    )

    handoff = result["reviewed_part_handoff"]
    assert result["status"] == expected_status
    assert result["success"] is False
    assert expected_code in handoff["diagnostic_codes"]
    assert {"code": expected_code} in handoff["blocked_reasons"]
    assert not (Path(result["output_dir"]) / "input_ir.json").exists()


@pytest.mark.parametrize(
    ("request_update", "expected_status", "expected_code"),
    [
        (
            {
                "part_id": "screws",
                "status": "blocked_no_candidate_part",
                "blocked_reasons": [{"code": "part_request.reference_only_not_selectable"}],
                "diagnostic_codes": ["part_request.reference_only_not_selectable"],
            },
            "blocked_reference_only_part",
            "part_handoff.blocked_reference_only_part",
        ),
        (
            {
                "part_id": "gear",
                "status": "blocked_no_candidate_part",
                "blocked_reasons": [{"code": "part_request.blocked_part_not_selectable"}],
                "diagnostic_codes": ["part_request.blocked_part_not_selectable"],
            },
            "blocked_unsupported_part",
            "part_handoff.blocked_unsupported_part",
        ),
    ],
)
def test_reviewed_part_handoff_rejects_reference_only_and_unsupported_parts(
    tmp_path,
    monkeypatch,
    request_update,
    expected_status,
    expected_code,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    request = {**_valid_part_create_request(), **request_update}
    review = {
        **review_part_create_request(_valid_part_create_request()),
        "status": "approved",
        "review_result": "approved_for_single_part_planning",
    }

    result = run_reviewed_part_handoff_pipeline(request, review, output_dir=tmp_path / "outputs" / expected_status)

    handoff = result["reviewed_part_handoff"]
    assert result["status"] == expected_status
    assert handoff["part_id"] == request_update["part_id"]
    assert expected_code in handoff["diagnostic_codes"]
    assert {"code": expected_code} in handoff["blocked_reasons"]


@pytest.mark.parametrize(
    ("extra", "expected_code"),
    [
        ({"python_code": "import cadquery as cq"}, "part_handoff.provider_code_rejected"),
        ({"cad_ir": {"part_type": "spacer"}}, "part_handoff.provider_cad_ir_rejected"),
        ({"provider_response": {"raw": "secret provider payload"}}, "part_handoff.provider_code_rejected"),
    ],
)
def test_reviewed_part_handoff_rejects_provider_cad_code_ir_and_arbitrary_fields(
    tmp_path,
    monkeypatch,
    extra,
    expected_code,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    request = {**_valid_part_create_request(), **extra}
    review = {
        **review_part_create_request(_valid_part_create_request()),
        "status": "approved",
        "review_result": "approved_for_single_part_planning",
    }
    output_dir = tmp_path / "outputs" / "handoff_provider_rejected"

    result = run_reviewed_part_handoff_pipeline(request, review, output_dir=output_dir)

    handoff = result["reviewed_part_handoff"]
    serialized = json.dumps({
        "result": result,
        "handoff": json.loads((output_dir / "reviewed_part_handoff.json").read_text(encoding="utf-8")),
        "report": json.loads((output_dir / "report.json").read_text(encoding="utf-8")),
        "trace": json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8")),
    }, sort_keys=True)
    assert result["status"] == "blocked_unsupported_part"
    assert expected_code in handoff["diagnostic_codes"]
    assert "secret provider payload" not in serialized
    assert "python_code" not in serialized
    assert "\"cad_ir\": {" not in serialized
    assert "import cadquery" not in serialized.lower()


def test_reviewed_part_handoff_approved_review_with_missing_interfaces_needs_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    request = _valid_part_create_request()
    request["interface_constraints"] = []
    review = {
        **review_part_create_request(_valid_part_create_request()),
        "status": "approved",
        "review_result": "approved_for_single_part_planning",
    }

    result = run_reviewed_part_handoff_pipeline(
        request,
        review,
        output_dir=tmp_path / "outputs" / "handoff_missing_interfaces",
    )

    handoff = result["reviewed_part_handoff"]
    assert result["status"] == "needs_revision_missing_interface_constraints"
    assert "part_handoff.needs_revision_missing_interface_constraints" in handoff["diagnostic_codes"]
    assert not (Path(result["output_dir"]) / "input_ir.json").exists()


def _valid_reviewed_part_handoff():
    request = _valid_part_create_request()
    return pipeline_runner.create_reviewed_part_handoff(request, review_part_create_request(request))


def test_reviewed_part_single_create_ready_handoff_invokes_agent_part_ir(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "create_part_ir": {
            "part_type": "enclosure_base",
            "part_name": "single_part_base",
            "unit": "mm",
            "dimensions": {"outer_length": 80, "outer_width": 50, "outer_height": 18, "wall_thickness": 2},
            "features": {},
            "outputs": ["step", "stl"],
        },
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "reviewed_part_single_create"

    result = run_reviewed_part_single_create_pipeline(
        _valid_reviewed_part_handoff(),
        adapter,
        output_dir=output_dir,
    )

    child_dir = output_dir / "single_part_base"
    assert result["status"] == "success"
    assert result["success"] is True
    assert [request["operation"] for request in fake_client.requests] == ["create_part_ir"]
    assert (output_dir / "reviewed_part_handoff.json").exists()
    assert (output_dir / "part_execution_request.json").exists()
    assert (output_dir / "cad_ir_draft.json").exists()
    assert (output_dir / "lineage.json").exists()
    assert (output_dir / "report.json").exists()
    assert (output_dir / "agent_trace.json").exists()
    assert (child_dir / "input_ir.json").exists()
    assert (child_dir / "model.step").exists()
    assert (child_dir / "model.stl").exists()
    assert not (output_dir / "input_ir.json").exists()
    assert not (output_dir / "model.step").exists()
    assert not (output_dir / "model.stl").exists()

    execution_request = json.loads((output_dir / "part_execution_request.json").read_text(encoding="utf-8"))
    prompt = execution_request["prompt"]
    assert execution_request["execution_mode"] == "single_part_only"
    assert execution_request["child_run_id"] == "single_part_base"
    assert 'part_id "base"' in prompt
    assert "Generate only this one part." in prompt
    assert "Base component with PCB standoffs and screw bosses." in prompt
    assert "fastener clearance/alignment features" in prompt
    assert "Do not generate a lid, screws, other parts, batch output, or a combined model." in prompt
    assert "lid component" not in prompt.lower()
    assert "reference screw envelope" not in prompt.lower()
    assert "generate all parts" not in prompt.lower()
    assert "batch generate" not in prompt.lower()
    assert "step assembly" not in prompt.lower()
    assert "assembly" not in prompt.lower()
    request_payload = _request_user_payload(fake_client.requests[0])
    assert request_payload["part_execution_request"]["prompt"] == prompt
    assert request_payload["reviewed_part_handoff"]["part_id"] == "base"

    lineage = json.loads((output_dir / "lineage.json").read_text(encoding="utf-8"))
    assert lineage["relationship"] == "reviewed_part_single_create_child"
    assert lineage["assembly_plan_artifact"] == "assembly_plan.json"
    assert lineage["part_create_request_artifact"] == "part_create_request.json"
    assert lineage["part_request_review_artifact"] == "part_request_review.json"
    assert lineage["reviewed_part_handoff_artifact"] == "reviewed_part_handoff.json"
    assert lineage["child_run_id"] == "single_part_base"
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))
    assert report["reviewed_part_single_create"]["stages"] == [
        "load_reviewed_part_handoff",
        "validate_review_gate",
        "compile_single_part_execution_request",
        "create_part_ir",
        "validate_agent_generated_cad_ir",
        "run_ir_pipeline",
        "record_lineage",
    ]
    assert report["reviewed_part_single_create"]["workflow_mode"] == "agent_ir_synthesis"
    assert trace["reviewed_part_single_create"]["part_id"] == "base"


def test_reviewed_part_single_create_non_ready_handoff_does_not_execute(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    handoff = _valid_reviewed_part_handoff()
    handoff["status"] = "blocked_review_not_approved"
    adapter = JsonContractAgentAdapter(OperationFakeJsonContractClient({}))
    output_dir = tmp_path / "outputs" / "blocked_single_create"

    result = run_reviewed_part_single_create_pipeline(handoff, adapter, output_dir=output_dir)

    assert result["status"] == "blocked_handoff_not_ready"
    assert adapter.last_provider_request_trace is None
    assert (output_dir / "reviewed_part_handoff.json").exists()
    assert (output_dir / "report.json").exists()
    assert (output_dir / "agent_trace.json").exists()
    assert not (output_dir / "part_execution_request.json").exists()
    assert not (output_dir / "input_ir.json").exists()
    assert not (output_dir / "model.step").exists()
    assert not (output_dir / "model.stl").exists()


@pytest.mark.parametrize(
    ("handoff_update", "expected_status", "expected_code"),
    [
        (
            {"part_id": "screws"},
            "blocked_reference_only_part",
            "reviewed_part_single_create.blocked_reference_only_part",
        ),
        (
            {"blocked_reasons": [{"code": "part_handoff.blocked_unsupported_part"}]},
            "blocked_unsupported_part",
            "reviewed_part_single_create.blocked_unsupported_part",
        ),
        (
            {"part_brief": "part"},
            "blocked_missing_part_brief",
            "reviewed_part_single_create.blocked_missing_part_brief",
        ),
        (
            {"interface_constraints": []},
            "needs_revision_missing_interface_constraints",
            "reviewed_part_single_create.needs_revision_missing_interface_constraints",
        ),
    ],
)
def test_reviewed_part_single_create_rejects_reference_blocked_and_incomplete_handoffs(
    tmp_path,
    monkeypatch,
    handoff_update,
    expected_status,
    expected_code,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    handoff = {**_valid_reviewed_part_handoff(), **handoff_update}
    adapter = JsonContractAgentAdapter(OperationFakeJsonContractClient({}))

    result = run_reviewed_part_single_create_pipeline(
        handoff,
        adapter,
        output_dir=tmp_path / "outputs" / expected_status,
    )

    assert result["status"] == expected_status
    assert adapter.last_provider_request_trace is None
    assert expected_code in result["diagnostic_codes"]
    assert not (Path(result["output_dir"]) / "part_execution_request.json").exists()
    assert not (Path(result["output_dir"]) / "input_ir.json").exists()


@pytest.mark.parametrize(
    ("extra", "expected_status", "expected_code"),
    [
        ({"python_code": "import cadquery as cq"}, "blocked_provider_generated_code", "reviewed_part_single_create.provider_code_rejected"),
        ({"cad_ir": {"part_type": "spacer"}}, "blocked_provider_generated_cad_ir", "reviewed_part_single_create.provider_cad_ir_rejected"),
        ({"provider_response": {"raw": "secret provider payload"}}, "blocked_arbitrary_provider_fields", "reviewed_part_single_create.provider_code_rejected"),
        ({"part_brief": "Generate an assembly with all assembly parts."}, "blocked_multi_part_or_assembly_request", "reviewed_part_single_create.blocked_multi_part_or_assembly_request"),
    ],
)
def test_reviewed_part_single_create_rejects_provider_fields_and_assembly_requests(
    tmp_path,
    monkeypatch,
    extra,
    expected_status,
    expected_code,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    handoff = {**_valid_reviewed_part_handoff(), **extra}
    adapter = JsonContractAgentAdapter(OperationFakeJsonContractClient({}))
    output_dir = tmp_path / "outputs" / expected_status

    result = run_reviewed_part_single_create_pipeline(handoff, adapter, output_dir=output_dir)

    serialized_outputs = json.dumps({
        "handoff": json.loads((output_dir / "reviewed_part_handoff.json").read_text(encoding="utf-8")),
        "report": json.loads((output_dir / "report.json").read_text(encoding="utf-8")),
        "trace": json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8")),
    }, sort_keys=True)
    assert result["status"] == expected_status
    assert adapter.last_provider_request_trace is None
    assert expected_code in result["diagnostic_codes"]
    assert "secret provider payload" not in serialized_outputs
    assert "python_code" not in serialized_outputs
    assert "\"cad_ir\": {" not in serialized_outputs
    assert "import cadquery" not in serialized_outputs.lower()


def test_reviewed_part_single_create_outputs_do_not_leak_paths_secrets_or_provider_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "create_part_ir": {
            "part_type": "enclosure_base",
            "part_name": "single_part_base",
            "unit": "mm",
            "dimensions": {"outer_length": 80, "outer_width": 50, "outer_height": 18, "wall_thickness": 2},
            "features": {},
            "outputs": ["step", "stl"],
        },
    }, provider_identity={"provider": "fake/json", "api_key": "secret"})
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "single_create_privacy"

    run_reviewed_part_single_create_pipeline(_valid_reviewed_part_handoff(), adapter, output_dir=output_dir)

    serialized_outputs = json.dumps({
        "execution_request": json.loads((output_dir / "part_execution_request.json").read_text(encoding="utf-8")),
        "lineage": json.loads((output_dir / "lineage.json").read_text(encoding="utf-8")),
        "report": json.loads((output_dir / "report.json").read_text(encoding="utf-8")),
        "trace": json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8")),
    }, sort_keys=True)
    assert str(tmp_path) not in serialized_outputs
    assert "D:\\" not in serialized_outputs
    assert "api_key" not in serialized_outputs
    assert "secret" not in serialized_outputs
    assert "messages" not in serialized_outputs
    assert "raw_response" not in serialized_outputs


def test_reviewed_part_agent_ir_normalizes_upper_link_to_generic_family_without_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)
    handoff = {
        **_valid_reviewed_part_handoff(),
        "part_id": "upper_link",
        "part_brief": "Second printable robotic arm link; recommended single-part smoke target.",
        "interface_constraints": [{"kind": "pin_joint", "related_part_id": "lower_link"}],
        "preserved_assembly_context": {"related_parts": ["lower_link", "gripper_mount"], "arm_reach_mm": 220},
    }
    output_dir = tmp_path / "outputs" / "upper_link_agent_ir"

    class RecordingAdapter(DeterministicAgentAdapter):
        calls = 0

        def create_part_ir(self, reviewed_part_handoff, context=None):
            self.calls += 1
            return super().create_part_ir(reviewed_part_handoff, context=context)

    adapter = RecordingAdapter()
    result = run_reviewed_part_agent_ir_create_pipeline(
        handoff,
        adapter,
        output_dir=output_dir,
    )

    assert adapter.calls == 1
    assert result["status"] == "success"
    draft = json.loads((output_dir / "cad_ir_draft.json").read_text(encoding="utf-8"))
    input_ir = json.loads((output_dir / "single_part_upper_link" / "input_ir.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))
    assert draft["source_part_id"] == "upper_link"
    assert draft["source_intent"] == "upper_link"
    assert draft["part_type"] == "link_like_part"
    assert draft["geometry_family"] == "elongated_plate_with_end_holes"
    assert input_ir["part_type"] == "link_like_part"
    assert input_ir["geometry_family"] == "elongated_plate_with_end_holes"
    assert draft["dimensions"]["hole_diameter"] < draft["dimensions"]["width"]
    assert draft["dimensions"]["hole_center_distance"] < draft["dimensions"]["length"]
    assert draft["source"]["normalization"]["reason"]
    assert draft["validation_metadata"]["strength_validated"] is False
    assert "mounting_plate" not in json.dumps({"draft": draft, "report": report, "trace": trace})
    assert (output_dir / "single_part_upper_link" / "model.step").exists()
    assert (output_dir / "single_part_upper_link" / "model.stl").exists()
    assert report["concept_scope"] == "single_generic_concept_part"
    assert report["assembly_generated"] is False
    assert report["strength_validated"] is False
    assert report["lineage"]["part_id"] == "upper_link"
    assert report["lineage"]["assembly_plan_artifact"] == "assembly_plan.json"
    lower_link_ir = DeterministicAgentAdapter().create_part_ir({**handoff, "part_id": "lower_link"})
    assert lower_link_ir["part_type"] == draft["part_type"]
    assert lower_link_ir["geometry_family"] == draft["geometry_family"]
    assert lower_link_ir["source_part_id"] == "lower_link"
    assert trace["reviewed_part_single_create"]["stages"] == [
        "load_reviewed_part_handoff",
        "validate_review_gate",
        "compile_single_part_execution_request",
        "create_part_ir",
        "validate_agent_generated_cad_ir",
        "run_ir_pipeline",
        "record_lineage",
    ]


def test_reviewed_part_agent_ir_bypass_output_blocks_without_writing_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)

    class BypassPartIrAdapter(DeterministicAgentAdapter):
        def create_part_ir(self, reviewed_part_handoff, context=None):
            return {
                "part_type": "spacer",
                "dimensions": {"outer_diameter": 12, "inner_diameter": 5, "thickness": 8},
                "python_code": "print('bypass')",
            }

    output_dir = tmp_path / "outputs" / "bypass_part_ir"
    result = run_reviewed_part_single_create_pipeline(
        _valid_reviewed_part_handoff(),
        BypassPartIrAdapter(),
        output_dir=output_dir,
    )

    serialized = json.dumps({
        "result": result,
        "report": json.loads((output_dir / "report.json").read_text(encoding="utf-8")),
        "trace": json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8")),
    }, sort_keys=True)
    assert result["status"] == "blocked_cad_ir_validation"
    assert result["error_category"] == "adapter_bypass_rejected"
    assert not (output_dir / "cad_ir_draft.json").exists()
    assert "python_code" not in serialized
    assert "print('bypass')" not in serialized


def _write_part_result_child_run(
    tmp_path,
    *,
    include_step=True,
    include_stl=True,
    include_lineage=True,
    prompt_text=None,
    execution_mode="single_part_only",
    requirement_scope="single_part",
    report_part_id="base",
):
    bridge_dir = tmp_path / "outputs" / "reviewed_part_single_create"
    child_dir = bridge_dir / "single_part_base"
    child_dir.mkdir(parents=True)
    (child_dir / "input_ir.json").write_text(json.dumps({"part_type": "mounting_plate"}), encoding="utf-8")
    (child_dir / "requirement.json").write_text(json.dumps({
        "intent": {"scope": requirement_scope},
        "part_type": "mounting_plate",
    }), encoding="utf-8")
    (child_dir / "report.json").write_text(json.dumps({
        "status": "success",
        "part_id": report_part_id,
        "provider_response": {"raw_response": "secret provider payload"},
        "messages": ["do not leak"],
    }), encoding="utf-8")
    (child_dir / "prompt.txt").write_text(
        prompt_text or "Create base. Preserve fastener clearance/alignment features and reference fastener clearance envelope.",
        encoding="utf-8",
    )
    if include_step:
        (child_dir / "model.step").write_text("STEP", encoding="utf-8")
    if include_stl:
        (child_dir / "model.stl").write_text("STL", encoding="utf-8")
    (bridge_dir / "part_execution_request.json").write_text(json.dumps({
        "child_run_id": "single_part_base",
        "execution_mode": execution_mode,
        "part_id": "base",
        "prompt": prompt_text or "Preserve fastener clearance/alignment features and reference fastener clearance envelope.",
        "api_key": "secret",
    }), encoding="utf-8")
    (bridge_dir / "reviewed_part_handoff.json").write_text(json.dumps(_valid_reviewed_part_handoff()), encoding="utf-8")
    if include_lineage:
        (bridge_dir / "lineage.json").write_text(json.dumps({
            "relationship": "reviewed_part_single_create_child",
            "part_id": "base",
            "assembly_plan_artifact": "assembly_plan.json",
            "part_create_request_artifact": "part_create_request.json",
            "part_request_review_artifact": "part_request_review.json",
            "reviewed_part_handoff_artifact": "reviewed_part_handoff.json",
            "child_run_id": "single_part_base",
        }), encoding="utf-8")
    return bridge_dir, child_dir


def test_part_result_review_accepts_successful_single_part_child_run(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    called = {"run_ir_pipeline": False}

    def fake_run_ir_pipeline(*args, **kwargs):
        called["run_ir_pipeline"] = True
        raise AssertionError("part result review must not run CAD execution")

    monkeypatch.setattr(pipeline_runner, "run_ir_pipeline", fake_run_ir_pipeline)
    bridge_dir, child_dir = _write_part_result_child_run(tmp_path)
    output_dir = tmp_path / "outputs" / "part_result_review"

    result = run_part_result_review_pipeline(
        _valid_reviewed_part_handoff(),
        child_dir,
        output_dir=output_dir,
    )

    review = json.loads((output_dir / "part_result_review.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))
    assert result["status"] == "accepted_for_preview"
    assert result["success"] is True
    assert called["run_ir_pipeline"] is False
    assert review["artifact_type"] == "part_result_review"
    assert review["source_handoff"] == "reviewed_part_handoff.json"
    assert review["child_run"] == "single_part_base"
    assert review["part_id"] == "base"
    assert review["checks"] == {
        "child_run_created": True,
        "step_created": True,
        "stl_created": True,
        "input_ir_created": True,
        "report_created": True,
        "child_scope": "single_part",
        "single_part_only": True,
        "no_batch_generation": True,
        "no_assembly_generation": True,
        "selected_part_id_preserved": True,
        "lineage_preserved": True,
        "interface_constraints_preserved_in_metadata": True,
    }
    assert "part_result.review_created" in review["diagnostic_codes"]
    assert "part_result.child_run_found" in review["diagnostic_codes"]
    assert "part_result.step_created" in review["diagnostic_codes"]
    assert "part_result.stl_created" in review["diagnostic_codes"]
    assert "part_result.input_ir_found" in review["diagnostic_codes"]
    assert "part_result.single_part_scope_preserved" in review["diagnostic_codes"]
    assert "part_result.selected_part_id_preserved" in review["diagnostic_codes"]
    assert "part_result.lineage_preserved" in review["diagnostic_codes"]
    assert "part_result.interface_constraints_preserved_in_metadata" in review["diagnostic_codes"]
    assert review["revision_notes"] == []
    assert report["cad_ir_created"] is False
    assert report["part_modeling_started"] is False
    assert trace["part_result_review"]["cad_ir_created"] is False
    assert (bridge_dir / "assembly.step").exists() is False


def test_part_result_review_missing_child_run_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    child_dir = tmp_path / "outputs" / "reviewed_part_single_create" / "single_part_base"

    result = run_part_result_review_pipeline(
        _valid_reviewed_part_handoff(),
        child_dir,
        output_dir=tmp_path / "outputs" / "part_result_missing_child",
    )

    review = result["part_result_review"]
    assert result["status"] == "blocked_missing_child_run"
    assert review["checks"]["child_run_created"] is False
    assert "part_result.blocked_missing_child_run" in review["diagnostic_codes"]


def test_part_result_review_missing_step_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    _, child_dir = _write_part_result_child_run(tmp_path, include_step=False)

    result = run_part_result_review_pipeline(
        _valid_reviewed_part_handoff(),
        child_dir,
        output_dir=tmp_path / "outputs" / "part_result_missing_step",
    )

    review = result["part_result_review"]
    assert result["status"] == "blocked_missing_step"
    assert review["checks"]["step_created"] is False
    assert "part_result.blocked_missing_step" in review["diagnostic_codes"]


def test_part_result_review_scope_violation_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    bridge_dir, child_dir = _write_part_result_child_run(
        tmp_path,
        execution_mode="assembly",
        requirement_scope="assembly",
    )
    (bridge_dir / "single_part_lid").mkdir()
    (bridge_dir / "assembly.step").write_text("ASSEMBLY", encoding="utf-8")

    result = run_part_result_review_pipeline(
        _valid_reviewed_part_handoff(),
        child_dir,
        output_dir=tmp_path / "outputs" / "part_result_scope_violation",
    )

    review = result["part_result_review"]
    assert result["status"] == "blocked_scope_violation"
    assert review["checks"]["child_scope"] == "assembly_or_multi_part"
    assert review["checks"]["single_part_only"] is False
    assert review["checks"]["no_batch_generation"] is False
    assert review["checks"]["no_assembly_generation"] is False
    assert "part_result.blocked_scope_violation" in review["diagnostic_codes"]


def test_part_result_review_missing_lineage_blocks_with_diagnostic(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    _, child_dir = _write_part_result_child_run(tmp_path, include_lineage=False)

    result = run_part_result_review_pipeline(
        _valid_reviewed_part_handoff(),
        child_dir,
        output_dir=tmp_path / "outputs" / "part_result_missing_lineage",
    )

    review = result["part_result_review"]
    assert result["status"] == "blocked_lineage_missing"
    assert review["checks"]["lineage_preserved"] is False
    assert "part_result.blocked_lineage_missing" in review["diagnostic_codes"]


def test_part_result_review_interface_metadata_missing_needs_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    _, child_dir = _write_part_result_child_run(tmp_path, prompt_text="Create base only.")

    result = run_part_result_review_pipeline(
        _valid_reviewed_part_handoff(),
        child_dir,
        output_dir=tmp_path / "outputs" / "part_result_missing_interface_metadata",
    )

    review = result["part_result_review"]
    assert result["status"] == "needs_revision"
    assert review["checks"]["interface_constraints_preserved_in_metadata"] is False
    assert "part_result.needs_revision_missing_interface_metadata" in review["diagnostic_codes"]


def test_part_result_review_outputs_do_not_leak_paths_secrets_or_provider_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    _, child_dir = _write_part_result_child_run(tmp_path)
    output_dir = tmp_path / "outputs" / "part_result_privacy"

    result = run_part_result_review_pipeline(
        _valid_reviewed_part_handoff(),
        child_dir,
        output_dir=output_dir,
    )

    serialized_outputs = json.dumps({
        "result": result,
        "review": json.loads((output_dir / "part_result_review.json").read_text(encoding="utf-8")),
        "report": json.loads((output_dir / "report.json").read_text(encoding="utf-8")),
        "trace": json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8")),
    }, sort_keys=True)
    assert str(tmp_path) not in serialized_outputs
    assert "D:\\" not in serialized_outputs
    assert "api_key" not in serialized_outputs
    assert "secret" not in serialized_outputs
    assert "messages" not in serialized_outputs
    assert "raw_response" not in serialized_outputs
    assert "provider payload" not in serialized_outputs


def test_reviewed_part_handoff_exports_are_available():
    import ai_native_cad.pipeline as pipeline

    assert pipeline.create_reviewed_part_handoff is create_reviewed_part_handoff
    assert pipeline.review_part_result is review_part_result
    assert pipeline.run_reviewed_part_handoff_pipeline is run_reviewed_part_handoff_pipeline
    assert pipeline.run_reviewed_part_single_create_pipeline is run_reviewed_part_single_create_pipeline
    assert pipeline.run_reviewed_part_agent_ir_create_pipeline is run_reviewed_part_agent_ir_create_pipeline
    assert pipeline.run_part_result_review_pipeline is run_part_result_review_pipeline
    assert "create_reviewed_part_handoff" in pipeline.__all__
    assert "review_part_result" in pipeline.__all__
    assert "run_reviewed_part_handoff_pipeline" in pipeline.__all__
    assert "run_reviewed_part_single_create_pipeline" in pipeline.__all__
    assert "run_reviewed_part_agent_ir_create_pipeline" in pipeline.__all__
    assert "run_part_result_review_pipeline" in pipeline.__all__


@pytest.mark.parametrize(
    ("prompt", "provider_requirement", "expected_code"),
    [
        ("Make a 24 tooth gear.", {"part_type": "gear", "dimensions": {"teeth": 24}}, "unsupported_part_type.gear"),
        (
            "Make a production-ready load-bearing aerospace bracket.",
            {"part_type": "bracket", "dimensions": {"length": 80, "width": 40, "height": 30}},
            "blocked_policy.safety_scope_blocked",
        ),
    ],
)
def test_provider_normalized_design_create_keeps_expected_unsupported_or_unsafe_cases_blocked(
    prompt,
    provider_requirement,
    expected_code,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": provider_requirement,
        "create_plan": _valid_planning_json(),
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_normalized_design_blocked"

    result = run_provider_normalized_design_create_pipeline(prompt, adapter, output_dir=output_dir)

    assert result["status"] == "blocked_provider_requirement"
    assert result["blocked_stage"] == "requirement"
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement"]
    assert (output_dir / "requirement.json").exists()
    assert not (output_dir / "intent.json").exists()
    assert not (output_dir / "assembly_plan.json").exists()
    assert not (output_dir / "input_ir.json").exists()
    requirement = json.loads((output_dir / "requirement.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert requirement["requirement_status"]["complete_for_generation"] is False
    assert expected_code in requirement["requirement_status"]["diagnostic_codes"]
    assert expected_code in report["diagnostic_codes"]


def test_normalized_create_uses_local_compiler_and_rejects_provider_ir_or_code(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": {
            "part_type": "mounting_plate",
            "unit": "mm",
            "dimensions": {"length": 80, "width": 40, "thickness": 5, "unsafe_extra": 999},
            "features": {
                "holes": {"count": 4, "diameter": 4.5, "positions": "corner_4"},
                "laser": {"power": 1000},
            },
            "input_ir": {"part_type": "gear", "dimensions": {"teeth": 24}},
            "cadquery_code": "import cadquery as cq",
            "python_code": "print('provider code must not run')",
        },
        "create_plan": {
            "artifact_type": "plan",
            "selected_parts": [],
            "input_ir": {"part_type": "gear", "dimensions": {"teeth": 24}},
            "cadquery_code": "import cadquery as cq",
        },
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_normalized_no_ir"

    result = run_provider_normalized_create_pipeline(
        "Make an 80x40x5 mm mounting plate with four M4 holes.",
        adapter,
        output_dir=output_dir,
    )

    assert result["status"] == "success"
    assert result["input_ir"]["part_type"] == "mounting_plate"
    assert result["input_ir"]["dimensions"] == {"length": 80, "thickness": 5, "width": 40}
    assert "unsafe_extra" not in result["input_ir"]["dimensions"]
    assert "laser" not in result["input_ir"]["features"]
    serialized = json.dumps({
        "requirement": result["requirement"],
        "planning_artifact": result["planning_artifact"],
        "input_ir": result["input_ir"],
    }, sort_keys=True)
    assert "cadquery_code" not in serialized
    assert "python_code" not in serialized
    assert "\"part_type\": \"gear\"" not in serialized


def test_strict_provider_create_records_compliance_mode_and_does_not_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": _valid_requirement_json(),
        "create_plan": {
            "artifact_type": "plan",
            "selected_parts": [],
            "input_ir": {"part_type": "spacer"},
            "cadquery_code": "import cadquery as cq",
        },
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_strict_no_fallback"

    result = run_provider_create_pipeline("Make a spacer washer.", adapter, output_dir=output_dir)

    assert result["status"] == "blocked_provider_validation"
    assert result["blocked_stage"] == "planning"
    assert not (output_dir / "planning_artifact.json").exists()
    assert not (output_dir / "input_ir.json").exists()
    assert result["provider_create"]["provider_contract_mode"] == "strict"
    assert result["provider_create"]["workflow_mode"] == "provider_contract_compliance"


@pytest.mark.parametrize(
    ("prompt", "provider_requirement", "expected_code"),
    [
        (
            "Make a 24 tooth gear.",
            {"part_type": "gear", "dimensions": {"teeth": 24}},
            "unsupported_part_type.gear",
        ),
        (
            "Make a production-ready load-bearing aerospace bracket.",
            {"part_type": "bracket", "dimensions": {"length": 80, "width": 40, "height": 30}},
            "blocked_policy.safety_scope_blocked",
        ),
    ],
)
def test_provider_normalized_create_keeps_expected_unsupported_or_unsafe_cases_blocked(
    prompt,
    provider_requirement,
    expected_code,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": provider_requirement,
        "create_plan": _valid_planning_json(),
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_normalized_blocked"

    result = run_provider_normalized_create_pipeline(prompt, adapter, output_dir=output_dir)

    assert result["status"] == "blocked_provider_requirement"
    assert result["blocked_stage"] == "requirement"
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement"]
    assert result["provider_create"]["provider_contract_mode"] == "extract_then_compile"
    assert (output_dir / "requirement.json").exists()
    assert not (output_dir / "input_ir.json").exists()
    requirement = json.loads((output_dir / "requirement.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert requirement["requirement_status"]["complete_for_generation"] is False
    assert expected_code in requirement["requirement_status"]["diagnostic_codes"]
    assert expected_code in report["diagnostic_codes"]


def test_provider_requirement_compiler_maps_prompt_scoped_bracket_alias():
    fake_client = FakeJsonContractClient({
        "part_type": "bracket",
        "dimensions": {"length": 40, "width": 20, "height": 30, "thickness": 4},
        "features": {"holes": {"count": 2, "diameter": 4}},
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement(
        "Make a simple right-angle bracket with two mounting holes.",
        context={"provider_contract_mode": "extract_then_compile"},
    )

    assert requirement["part_type"] == "simple_bracket"
    assert requirement["dimensions"]["base_length"] == 40
    assert requirement["features"]["base_holes"]["count"] == 2


def test_provider_requirement_compiler_does_not_treat_single_part_features_as_assembly():
    fake_client = FakeJsonContractClient({
        "part_type": "camera_mounting_plate",
        "scope": "assembly",
        "dimensions": {"length": 90, "width": 55, "thickness": 5},
        "features": {
            "mounting_holes": {"count": 4, "diameter": 4, "offset_from_edge": 8},
            "tripod_hole": {"diameter": 6.35},
        },
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement(
        "Make a camera mounting plate with tripod hole, four corner holes, and chamfered edges.",
        context={"provider_contract_mode": "extract_then_compile"},
    )

    assert requirement["part_type"] == "mounting_plate"
    assert requirement["requirement_status"]["complete_for_generation"] is True
    assert "compiler.assembly_requires_assembly_planning" not in requirement["requirement_status"]["diagnostic_codes"]


def test_provider_requirement_compiler_blocks_two_part_enclosure_as_multi_part():
    fake_client = FakeJsonContractClient({
        "part_type": "electronics_enclosure",
        "scope": "single_part",
        "dimensions": {"length": 100, "width": 60, "height": 30},
        "features": {"standoffs": {"count": 4}, "screws": {"count": 4}},
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement(
        "Design a two-part electronics enclosure with base and lid, four screws, and PCB standoffs.",
        context={"provider_contract_mode": "extract_then_compile"},
    )

    assert requirement["intent"]["scope"] == "multi_part"
    assert requirement["requirement_status"]["complete_for_generation"] is False
    assert "compiler.multi_part_requires_assembly_planning" in requirement["requirement_status"]["diagnostic_codes"]


def test_provider_requirement_compiler_blocks_hinge_as_assembly():
    fake_client = FakeJsonContractClient({
        "part_type": "hinge_bracket",
        "scope": "single_part",
        "dimensions": {"length": 60, "width": 30, "height": 10},
        "features": {"pin": {"diameter": 4}},
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement(
        "Design a simple hinge bracket assembly with two leaves and a pin.",
        context={"provider_contract_mode": "extract_then_compile"},
    )

    assert requirement["intent"]["scope"] == "assembly"
    assert requirement["requirement_status"]["complete_for_generation"] is False
    assert "compiler.assembly_requires_assembly_planning" in requirement["requirement_status"]["diagnostic_codes"]


def test_provider_requirement_compiler_does_not_map_unsafe_generic_bracket():
    fake_client = FakeJsonContractClient({
        "part_type": "bracket",
        "dimensions": {},
        "features": {},
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement(
        "Make a production-ready load-bearing aerospace bracket.",
        context={"provider_contract_mode": "extract_then_compile"},
    )

    assert requirement["requirement_status"]["complete_for_generation"] is False
    assert "blocked_policy.safety_scope_blocked" in requirement["requirement_status"]["diagnostic_codes"]


def test_provider_requirement_compiler_blocks_assembly_without_single_part_cad():
    fake_client = FakeJsonContractClient({
        "part_type": "phone_holder",
        "scope": "assembly",
        "dimensions": {},
        "features": {},
        "input_ir": {"part_type": "mounting_plate"},
        "cadquery_code": "import cadquery as cq",
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement(
        "Design a small adjustable phone holder made of a base, vertical support, and clamp.",
        context={"provider_contract_mode": "extract_then_compile"},
    )

    assert requirement["part_type"] == "phone_holder"
    assert requirement["intent"]["scope"] == "multi_part"
    assert requirement["requirement_status"]["complete_for_generation"] is False
    assert "compiler.multi_part_requires_assembly_planning" in requirement["requirement_status"]["diagnostic_codes"]
    serialized = json.dumps(requirement, sort_keys=True)
    assert "input_ir" not in serialized
    assert "cadquery_code" not in serialized
    assert "import cadquery" not in serialized


def test_provider_requirement_compiler_reports_specific_invalid_dimension_diagnostic():
    from ai_native_cad.agents.json_contract import ProviderRequirementCompilerError

    fake_client = FakeJsonContractClient({
        "part_type": "mounting_plate",
        "dimensions": ["length", 80],
        "features": {},
    })
    adapter = JsonContractAgentAdapter(fake_client)

    with pytest.raises(ProviderRequirementCompilerError) as raised:
        adapter.parse_requirement(
            "Make a mounting plate.",
            context={"provider_contract_mode": "extract_then_compile"},
        )

    assert raised.value.diagnostic_codes == ["requirement_validation.invalid_dimensions"]


def test_provider_normalized_design_create_reports_specific_compiler_diagnostic_for_invalid_dimensions(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": {
            "part_type": "mounting_plate",
            "dimensions": ["length", 80],
            "features": {},
        },
        "create_plan": _valid_planning_json(),
    })
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_normalized_design_invalid_dimensions"

    result = run_provider_normalized_design_create_pipeline(
        "Make a mounting plate.",
        adapter,
        output_dir=output_dir,
    )

    assert result["status"] == "blocked_provider_validation"
    assert result["blocked_stage"] == "requirement"
    assert "requirement_validation.invalid_dimensions" in result["diagnostic_codes"]
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert "requirement_validation.invalid_dimensions" in report["diagnostic_codes"]


def test_provider_requirement_blocked_artifact_does_not_record_provider_private_fields():
    fake_client = FakeJsonContractClient({
        "part_type": "gear",
        "dimensions": {"teeth": 24},
        "api_key": "secret-value",
        "provider_response": "raw response",
        "transcript": "raw transcript",
        "local_path": r"D:\private\file.step",
        "python_code": "print('no')",
        "cad_ir": {"part_type": "gear"},
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement(
        "Make a 24 tooth gear.",
        context={"provider_contract_mode": "extract_then_compile"},
    )

    serialized = json.dumps(requirement, sort_keys=True)
    assert "unsupported_part_type.gear" in serialized
    assert "secret-value" not in serialized
    assert "raw response" not in serialized
    assert "raw transcript" not in serialized
    assert "D:\\private" not in serialized
    assert "python_code" not in serialized
    assert "cad_ir" not in serialized


def test_provider_requirement_compiler_enriches_mounting_plate_hole_diameter_from_template():
    fake_client = FakeJsonContractClient({
        "part_type": "mounting_plate",
        "dimensions": {"length": 100, "width": 80, "thickness": 5},
        "features": {"holes": {"count": 4, "positions": "corner_4"}},
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement(
        "Make a camera mounting plate with tripod hole, four corner holes, and chamfered edges.",
        context={"provider_contract_mode": "extract_then_compile"},
    )

    assert requirement["features"]["holes"]["diameter"] == 4.5
    assert requirement["features"]["holes"]["type"] == "through_hole"
    assert requirement["requirement_status"]["complete_for_generation"] is True


def test_provider_requirement_compiler_keeps_circular_button_diameter_consistent():
    fake_client = FakeJsonContractClient({
        "part_type": "circular_button",
        "dimensions": {"diameter": 18, "height": 4},
        "features": {},
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement(
        "Make a circular button 18 mm diameter and 4 mm tall.",
        context={"provider_contract_mode": "extract_then_compile"},
    )

    assert requirement["dimensions"]["body_diameter"] == 18
    assert requirement["dimensions"]["button_diameter"] == 18


def test_provider_requirement_compiler_filters_unsupported_enclosure_fields():
    fake_client = FakeJsonContractClient({
        "part_type": "enclosure_base",
        "dimensions": {"length": 100, "width": 50, "depth": 50, "height": 20, "wall_thickness": 2},
        "features": {
            "battery_compartment": {"width": 30, "height": 10, "depth": 20},
            "button_hole": {"diameter": 12, "depth": 5},
            "bosses": {"diameter": 6, "height": 5},
        },
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement(
        "Make a small enclosure base for a button and battery.",
        context={"provider_contract_mode": "extract_then_compile"},
    )

    assert requirement["dimensions"]["outer_length"] == 100
    assert requirement["dimensions"]["outer_width"] == 50
    assert "depth" not in requirement["dimensions"]
    assert "battery_compartment" not in requirement["features"]
    assert "button_hole" not in requirement["features"]
    assert "bosses" in requirement["features"]


def test_provider_create_provider_failure_is_categorized_without_raw_exception_leak(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    fake_client = FailingJsonContractClient(
        RuntimeError(r"credential failed for CADFLOW_FAKE_API_KEY fake-secret-value-123456 at D:\private\run")
    )
    adapter = JsonContractAgentAdapter(fake_client)
    output_dir = tmp_path / "outputs" / "provider_create_provider_failure"

    result = run_provider_create_pipeline("Make a spacer washer.", adapter, output_dir=output_dir)

    assert result["status"] == "blocked_provider_requirement"
    assert result["error_category"] == "auth_failed"
    serialized = json.dumps({
        "result": result,
        "report": json.loads((output_dir / "report.json").read_text(encoding="utf-8")),
        "trace": json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8")),
        "runtime": json.loads((output_dir / "logs" / "runtime.json").read_text(encoding="utf-8")),
    }, sort_keys=True)
    assert "credential failed" not in serialized
    assert "CADFLOW_FAKE_API_KEY" not in serialized
    assert "fake-secret-value-123456" not in serialized
    assert "D:\\private" not in serialized
    assert "messages" not in serialized
    assert "Make a spacer" not in serialized


def test_json_contract_agent_adapter_requires_no_provider_sdk_or_network():
    fake_client = FakeJsonContractClient(_valid_requirement_json())
    adapter = JsonContractAgentAdapter(fake_client)

    adapter.parse_requirement("Make a spacer washer.")

    assert len(fake_client.requests) == 1
    assert "openai" not in JsonContractAgentAdapter.__module__


def test_openai_compatible_client_builds_deepseek_chat_request_without_leaking_identity(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    urlopen = RecordingUrlOpen({"choices": [{"message": {"content": _valid_requirement_json()}}]})
    endpoint = JsonProviderEndpoint(
        provider="deepseek",
        model="deepseek-chat",
        api_key_env_var="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        endpoint="/v1/chat/completions",
        api_shape="chat_completions",
        timeout_seconds=9,
        max_retries=1,
    )
    client = OpenAICompatibleJsonContractClient(endpoint, urlopen=urlopen)
    adapter = JsonContractAgentAdapter(
        client,
        config=JsonContractProviderConfig(
            provider="deepseek",
            model="deepseek-chat",
            enabled=True,
            timeout_seconds=9,
            max_retries=1,
            api_key_env_var="DEEPSEEK_API_KEY",
        ),
    )

    requirement = adapter.parse_requirement("Make a spacer washer.")

    call = urlopen.calls[0]
    assert requirement["part_type"] == "spacer"
    assert call["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert call["timeout"] == 9
    assert call["method"] == "POST"
    assert call["headers"]["Authorization"] == "Bearer deepseek-secret"
    assert call["body"]["model"] == "deepseek-chat"
    assert call["body"]["response_format"] == {"type": "json_object"}
    assert call["body"]["messages"][0]["role"] == "system"
    assert "DEEPSEEK_API_KEY" not in json.dumps(adapter.provider_identity)
    assert "deepseek-secret" not in json.dumps(adapter.provider_identity)


def test_openai_responses_client_builds_codex_request_without_leaking_identity(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    urlopen = RecordingUrlOpen({"output_text": _valid_requirement_json()})
    endpoint = JsonProviderEndpoint(
        provider="openai",
        model="gpt-5.1-codex",
        api_key_env_var="OPENAI_API_KEY",
        base_url="https://api.openai.com",
        endpoint="/v1/responses",
        api_shape="responses",
    )
    client = OpenAIResponsesJsonContractClient(endpoint, urlopen=urlopen)
    adapter = JsonContractAgentAdapter(
        client,
        config=JsonContractProviderConfig(
            provider="openai",
            model="gpt-5.1-codex",
            enabled=True,
            api_key_env_var="OPENAI_API_KEY",
        ),
    )

    requirement = adapter.parse_requirement("Make a spacer washer.")

    call = urlopen.calls[0]
    assert requirement["part_type"] == "spacer"
    assert call["url"] == "https://api.openai.com/v1/responses"
    assert call["headers"]["Authorization"] == "Bearer openai-secret"
    assert call["body"]["model"] == "gpt-5.1-codex"
    assert call["body"]["text"]["format"] == {"type": "json_object"}
    assert call["body"]["input"][0]["role"] == "system"
    assert "OPENAI_API_KEY" not in json.dumps(adapter.provider_identity)
    assert "openai-secret" not in json.dumps(adapter.provider_identity)


def test_json_contract_provider_factory_selects_deepseek_from_environment(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("CADFLOW_DEEPSEEK_MODEL", "deepseek-reasoner")
    monkeypatch.setenv("CADFLOW_PROVIDER_TIMEOUT_SECONDS", "11")
    urlopen = RecordingUrlOpen({"choices": [{"message": {"content": _valid_requirement_json()}}]})

    adapter = make_json_contract_adapter_from_env("deepseek", urlopen=urlopen)
    adapter.parse_requirement("Make a spacer washer.")

    assert adapter.provider_identity["provider"] == "deepseek"
    assert adapter.provider_identity["model"] == "deepseek-reasoner"
    assert adapter.provider_identity["enabled"] is True
    assert adapter.provider_identity["timeout_seconds"] == 11
    assert "DEEPSEEK_API_KEY" not in json.dumps(adapter.provider_identity)
    assert urlopen.calls[0]["body"]["model"] == "deepseek-reasoner"


def test_json_contract_provider_factory_selects_openai_codex_from_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("CADFLOW_OPENAI_MODEL", "gpt-5.1-codex")
    urlopen = RecordingUrlOpen({"output_text": _valid_requirement_json()})

    adapter = make_json_contract_adapter_from_env("openai", urlopen=urlopen)
    adapter.parse_requirement("Make a spacer washer.")

    assert adapter.provider_identity["provider"] == "openai"
    assert adapter.provider_identity["model"] == "gpt-5.1-codex"
    assert adapter.provider_identity["api_shape"] == "responses"
    assert urlopen.calls[0]["body"]["model"] == "gpt-5.1-codex"


def test_provider_client_missing_api_key_is_wrapped_without_env_name(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    endpoint = JsonProviderEndpoint(
        provider="deepseek",
        model="deepseek-chat",
        api_key_env_var="DEEPSEEK_API_KEY",
        base_url="https://api.deepseek.com",
        endpoint="/v1/chat/completions",
        api_shape="chat_completions",
    )
    adapter = JsonContractAgentAdapter(OpenAICompatibleJsonContractClient(endpoint))

    with pytest.raises(JsonContractProviderError) as raised:
        adapter.parse_requirement("Make a spacer washer.")

    serialized = str(raised.value) + json.dumps(raised.value.to_dict())
    assert raised.value.category == "auth_failed"
    assert "DEEPSEEK_API_KEY" not in serialized


def test_stage_runner_can_use_json_contract_adapter_when_explicitly_injected(tmp_path):
    fake_client = FakeJsonContractClient(_valid_requirement_json())
    runner = StageRunner(project_root=tmp_path, agent_adapter=JsonContractAgentAdapter(fake_client))
    output_dir = tmp_path / "outputs" / "json_contract_requirement"

    result = runner.run_requirement("Make a spacer washer.", {"output_dir": output_dir})
    runtime = json.loads((output_dir / "logs" / "runtime.json").read_text(encoding="utf-8"))
    activity = runtime["workflow_console"]["latest_stage"]["adapter_activity"]

    assert result["requirement"]["part_type"] == "spacer"
    assert json.loads((output_dir / "requirement.json").read_text(encoding="utf-8")) == result["requirement"]
    assert activity["provider_identity"]["adapter"] == "json_contract"
    assert activity["provider_identity"]["provider"] == "fake/json"
    assert activity["request_trace_summary"]["operation"] == "parse_requirement"
    assert activity["request_trace_summary"]["payload_shape"] == {
        "kind": "prompt_payload",
        "top_level_keys": ["prompt"],
    }


def test_stage_runner_can_use_json_contract_adapter_for_planning_when_explicitly_injected(tmp_path):
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": _valid_requirement_json(),
        "create_plan": _valid_planning_json(),
    })
    runner = StageRunner(project_root=tmp_path, agent_adapter=JsonContractAgentAdapter(fake_client))
    output_dir = tmp_path / "outputs" / "json_contract_planning"

    requirement = runner.run_requirement("Make a spacer washer.", {"output_dir": output_dir})["requirement"]
    result = runner.run_planning(requirement, {"output_dir": output_dir})
    runtime = json.loads((output_dir / "logs" / "runtime.json").read_text(encoding="utf-8"))
    activity = runtime["workflow_console"]["latest_stage"]["adapter_activity"]

    assert result["planning_artifact"]["artifact_type"] == "planning"
    assert result["planning_artifact"]["selected_parts"][0]["resolved_decisions"]["part_type"] == "spacer"
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement", "create_plan"]
    assert activity["operation"] == "create_plan"
    assert activity["provider_identity"]["provider"] == "fake/json"


def test_json_contract_agent_adapter_supports_all_contract_operations_with_fake_client():
    fake_client = OperationFakeJsonContractClient({
        "parse_requirement": _valid_requirement_json(),
        "create_plan": _valid_planning_json(),
        "create_part_ir": {
            "part_type": "spacer",
            "part_name": "single_part_spacer",
            "unit": "mm",
            "dimensions": {"outer_diameter": 12, "inner_diameter": 6, "thickness": 4},
            "features": {},
            "outputs": ["step", "stl"],
        },
        "parse_revision_request": _valid_revision_intent(),
        "create_revision_plan": _valid_revision_plan(),
        "suggest_repair": _valid_repair_json(),
        "explain_review": _valid_review_json(),
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement("Make a spacer washer.")
    planning = adapter.create_plan(requirement)
    part_ir = adapter.create_part_ir({"part_id": "spacer", "status": "ready_for_single_part_planning"})
    change_intent = adapter.parse_revision_request("Increase the thickness to 8 mm.", {"current_ir": _valid_ir()})
    revision_plan = adapter.create_revision_plan(change_intent, {"current_ir": _valid_ir()})
    repair = adapter.suggest_repair({"affected_feature": "holes"}, _valid_ir())
    review = adapter.explain_review({"status": "success"}, {"total_attempts": 1})

    assert planning["artifact_type"] == "planning"
    assert part_ir["part_type"] == "spacer"
    assert revision_plan["artifact_type"] == "revision_plan"
    assert repair["repair"]["strategy"] == "increase_spacing"
    assert review["status"] == "success"
    assert [request["operation"] for request in fake_client.requests] == [
        "parse_requirement",
        "create_plan",
        "create_part_ir",
        "parse_revision_request",
        "create_revision_plan",
        "suggest_repair",
        "explain_review",
    ]


def test_stage_runner_keeps_deterministic_agent_adapter_as_default(tmp_path):
    runner = StageRunner(project_root=tmp_path)

    assert isinstance(runner.agent_adapter, DeterministicAgentAdapter)


def test_stage_runner_rejects_invalid_requirement_adapter_output(tmp_path):
    runner = StageRunner(project_root=tmp_path, agent_adapter=InvalidRequirementAdapter())
    output_dir = tmp_path / "outputs" / "invalid_requirement"

    with pytest.raises(ValueError, match="part_type"):
        runner.run_requirement("Make a spacer.", {"output_dir": output_dir})

    assert not (output_dir / "requirement.json").exists()


def test_stage_runner_rejects_invalid_planning_adapter_output(tmp_path):
    runner = StageRunner(project_root=tmp_path, agent_adapter=InvalidPlanningAdapter())
    output_dir = tmp_path / "outputs" / "invalid_planning"
    requirement = runner.run_requirement(
        "Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.",
        {"output_dir": output_dir},
    )["requirement"]

    with pytest.raises(ValueError, match="artifact_type"):
        runner.run_planning(requirement, {"output_dir": output_dir})

    assert not (output_dir / "planning_artifact.json").exists()


def test_stage_runner_records_sanitized_local_mock_adapter_activity(tmp_path):
    runner = StageRunner(project_root=tmp_path, agent_adapter=SecretiveAdapter())
    output_dir = tmp_path / "outputs" / "adapter_activity"

    runner.run_requirement(
        "Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.",
        {"output_dir": output_dir},
    )
    runtime = json.loads((output_dir / "logs" / "runtime.json").read_text(encoding="utf-8"))
    activity = runtime["workflow_console"]["latest_stage"]["adapter_activity"]

    assert activity["operation"] == "parse_requirement"
    assert activity["provider_identity"] == {
        "provider": "local/mock",
        "adapter": "secretive-test",
    }


def test_agent_adapter_exposes_llm_shaped_planning_without_direct_execution_surface():
    public_methods = {
        name
        for name in dir(DeterministicAgentAdapter())
        if not name.startswith("_") and callable(getattr(DeterministicAgentAdapter(), name))
    }

    assert "generate_cad_code" not in public_methods
    assert "run_shell" not in public_methods
    assert "parse_requirement" in public_methods
    assert "create_plan" in public_methods
    assert "interpret_user_intent" in public_methods
    assert "propose_design_brief" in public_methods
    assert "generate_candidate_plans" in public_methods
    assert "convert_plan_to_ir" in public_methods
    assert "create_part_ir" in public_methods
    assert "parse_revision_request" in public_methods
    assert "create_revision_plan" in public_methods


def test_design_planner_fake_adapter_creates_llm_shaped_artifacts():
    adapter = DesignPlannerFakeAgentAdapter()

    intent = adapter.interpret_user_intent("Make an 80 x 40 x 5 mm mounting plate with four M4 corner holes.")
    design_brief = adapter.propose_design_brief(intent)
    candidates = adapter.generate_candidate_plans(design_brief)
    ir = adapter.convert_plan_to_ir(candidates[0])

    assert intent["artifact_type"] == "intent"
    assert intent["recognized_part_type"] == "mounting_plate"
    assert design_brief["artifact_type"] == "design_brief"
    assert design_brief["geometry_constraints"]["dimensions"]["length"] == 80.0
    assert [candidate["candidate_id"] for candidate in candidates] == ["A", "B"]
    assert candidates[0]["cad_ir"]["part_type"] == "mounting_plate"
    assert ir["part_type"] == "mounting_plate"
    assert ir["source"]["agent_create_workflow"]["selected_candidate"] == "A"


def test_adapter_validation_dispatch_accepts_all_deterministic_operations():
    adapter = DeterministicAgentAdapter()
    requirement = adapter.parse_requirement("Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.")
    planning = adapter.create_plan(requirement)
    repair = adapter.suggest_repair(
        {"affected_feature": "holes", "suggested_ir_fix": {"strategy": "increase_spacing"}},
        {
            "part_type": "mounting_plate",
            "part_name": "repairable_plate",
            "unit": "mm",
            "dimensions": {"length": 30, "width": 20, "thickness": 4},
            "features": {"holes": {"diameter": 5, "positions": "corner_4", "offset_from_edge": 1}},
            "outputs": ["step", "stl"],
        },
    )
    review = adapter.explain_review({"status": "success", "success": True, "part_name": "spacer"}, {"total_attempts": 1})
    part_ir = {
        "part_type": "spacer",
        "part_name": "single_part_spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6, "thickness": 4},
        "features": {},
        "outputs": ["step", "stl"],
    }

    validate_adapter_result("parse_requirement", requirement)
    validate_adapter_result("create_plan", planning)
    validate_adapter_result("create_part_ir", part_ir)
    validate_adapter_result("suggest_repair", repair)
    validate_adapter_result("explain_review", review)


def test_adapter_validation_rejects_direct_cad_and_shell_bypass_fields():
    with pytest.raises(ValueError, match="cadquery_code"):
        validate_requirement_draft({
            "part_type": "spacer",
            "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
            "cadquery_code": "import cadquery as cq",
        })

    with pytest.raises(ValueError, match="shell_command"):
        validate_adapter_result("create_plan", {
            "artifact_type": "planning",
            "route": {},
            "selected_parts": [{"shell_command": "python model.py"}],
            "flow_gate_status": {},
        })
