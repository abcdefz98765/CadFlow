import json
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
from ai_native_cad.pipeline import run_provider_create_pipeline, run_provider_normalized_create_pipeline
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
    ("prompt", "provider_requirement"),
    [
        (
            "Make a 24 tooth gear.",
            {"part_type": "gear", "dimensions": {"teeth": 24}},
        ),
        (
            "Make a production-ready load-bearing aerospace bracket.",
            {"part_type": "bracket", "dimensions": {"length": 80, "width": 40, "height": 30}},
        ),
    ],
)
def test_provider_normalized_create_keeps_expected_unsupported_or_unsafe_cases_blocked(
    prompt,
    provider_requirement,
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

    assert result["status"] == "blocked_provider_validation"
    assert result["blocked_stage"] == "requirement"
    assert [request["operation"] for request in fake_client.requests] == ["parse_requirement"]
    assert result["provider_create"]["provider_contract_mode"] == "extract_then_compile"
    assert not (output_dir / "input_ir.json").exists()


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


def test_provider_requirement_compiler_does_not_map_unsafe_generic_bracket():
    fake_client = FakeJsonContractClient({
        "part_type": "bracket",
        "dimensions": {},
        "features": {},
    })
    adapter = JsonContractAgentAdapter(fake_client)

    with pytest.raises(ValueError, match="unsupported provider part_type: bracket"):
        adapter.parse_requirement(
            "Make a production-ready load-bearing aerospace bracket.",
            context={"provider_contract_mode": "extract_then_compile"},
        )


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
        "parse_revision_request": _valid_revision_intent(),
        "create_revision_plan": _valid_revision_plan(),
        "suggest_repair": _valid_repair_json(),
        "explain_review": _valid_review_json(),
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement("Make a spacer washer.")
    planning = adapter.create_plan(requirement)
    change_intent = adapter.parse_revision_request("Increase the thickness to 8 mm.", {"current_ir": _valid_ir()})
    revision_plan = adapter.create_revision_plan(change_intent, {"current_ir": _valid_ir()})
    repair = adapter.suggest_repair({"affected_feature": "holes"}, _valid_ir())
    review = adapter.explain_review({"status": "success"}, {"total_attempts": 1})

    assert planning["artifact_type"] == "planning"
    assert revision_plan["artifact_type"] == "revision_plan"
    assert repair["repair"]["strategy"] == "increase_spacing"
    assert review["status"] == "success"
    assert [request["operation"] for request in fake_client.requests] == [
        "parse_requirement",
        "create_plan",
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

    validate_adapter_result("parse_requirement", requirement)
    validate_adapter_result("create_plan", planning)
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
