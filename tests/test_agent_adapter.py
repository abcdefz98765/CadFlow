import json
from pathlib import Path

import pytest

from ai_native_cad.agents import AgentAdapter, DeterministicAgentAdapter, JsonContractAgentAdapter
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
        "api_key_required": "provider_dependent",
        "model": "fake-requirement-v1",
    }


def test_json_contract_agent_adapter_requires_no_provider_sdk_or_network():
    fake_client = FakeJsonContractClient(_valid_requirement_json())
    adapter = JsonContractAgentAdapter(fake_client)

    adapter.parse_requirement("Make a spacer washer.")

    assert len(fake_client.requests) == 1
    assert "openai" not in JsonContractAgentAdapter.__module__


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
        "suggest_repair": _valid_repair_json(),
        "explain_review": _valid_review_json(),
    })
    adapter = JsonContractAgentAdapter(fake_client)

    requirement = adapter.parse_requirement("Make a spacer washer.")
    planning = adapter.create_plan(requirement)
    repair = adapter.suggest_repair({"affected_feature": "holes"}, _valid_ir())
    review = adapter.explain_review({"status": "success"}, {"total_attempts": 1})

    assert planning["artifact_type"] == "planning"
    assert repair["repair"]["strategy"] == "increase_spacing"
    assert review["status"] == "success"
    assert [request["operation"] for request in fake_client.requests] == [
        "parse_requirement",
        "create_plan",
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


def test_agent_adapter_has_no_direct_prompt_to_cad_surface():
    public_methods = {
        name
        for name in dir(DeterministicAgentAdapter())
        if not name.startswith("_") and callable(getattr(DeterministicAgentAdapter(), name))
    }

    assert "generate_cad_code" not in public_methods
    assert "run_shell" not in public_methods
    assert "parse_requirement" in public_methods
    assert "create_plan" in public_methods


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
