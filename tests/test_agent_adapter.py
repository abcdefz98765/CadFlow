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
from ai_native_cad.agents.validation import validate_adapter_result, validate_requirement_draft
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
    return json.loads(request["messages"][1]["content"])


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
    assert "JSON object" in fake_client.requests[0]["messages"][0]["content"]


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
    assert "planning_artifact.json" in fake_client.requests[0]["messages"][0]["content"]


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
    assert "revision change intent" in fake_client.requests[0]["messages"][0]["content"]
    assert "revision_plan.json" in fake_client.requests[1]["messages"][0]["content"]


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
    assert "[redacted-local-path]" in request["messages"][1]["content"]
    assert "[redacted-secret]" in request["messages"][1]["content"]
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
