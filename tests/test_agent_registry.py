from __future__ import annotations

import json

import pytest

from ai_native_cad.agents import (
    DESIGN_PART_SKILL,
    MODEL_PROGRAM_SKILL,
    RUNTIME_SKILL_REGISTRY,
    ContextBroker,
    EpisodeBudget,
    JsonContractAgentAdapter,
    StopReason,
    run_design_part_episode,
)
from ai_native_cad.agents.episode import ContextItem, EpisodeContractError


class SequencedActionClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    @property
    def provider_identity(self):
        return {"provider": "scripted-action-provider", "model": "fixture"}

    def generate_json_contract(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _handoff():
    return {
        "work_id": "fixture_work",
        "part_id": "clamp",
        "role": "moving jaw",
        "status": "ready_for_single_part_planning",
        "part_brief": "Compact printable clamp jaw",
        "interface_constraints": [
            {"kind": "through_hole", "diameter_mm": 5.0}
        ],
        "preserved_assembly_context": {"assembly_scope": "single_part"},
    }


def _valid_contract(*, part_name="provider_clamp"):
    return {
        "part_type": "simple_bracket",
        "part_name": part_name,
        "unit": "mm",
        "dimensions": {
            "base_length": 50,
            "base_width": 30,
            "height": 35,
            "thickness": 5,
        },
        "features": {},
        "outputs": ["step", "stl"],
        "check_level": "L0",
    }


def _adapter(responses):
    return JsonContractAgentAdapter(
        SequencedActionClient(responses),
        provider="scripted",
        model="fixture",
    )


def test_v1_runtime_authority_is_exactly_the_three_registered_operations():
    expected = {"work_design", "design_part", "model_program"}

    assert set(RUNTIME_SKILL_REGISTRY._by_operation) == expected
    assert set(RUNTIME_SKILL_REGISTRY._by_id) == expected
    assert {
        RUNTIME_SKILL_REGISTRY.for_operation(operation).skill_id
        for operation in expected
    } == expected


def test_design_part_registry_delegates_only_to_cadflow_model_program_skill():
    skill = RUNTIME_SKILL_REGISTRY.for_operation("design_part")

    assert skill is DESIGN_PART_SKILL
    assert skill.version == "0.2.0"
    assert skill.allowed_tools == frozenset({"validate_structured_contract"})
    assert "create_contract" in skill.allowed_actions
    assert "request_execution" in skill.allowed_actions
    assert "model_program_candidate" in skill.output_contract_types
    assert skill.delegated_skill_ids == ("model_program",)
    assert "part_job" in skill.allowed_context_keys
    assert "reviewed_part_handoff" not in skill.allowed_context_keys
    knowledge = RUNTIME_SKILL_REGISTRY.knowledge_for_skill("design_part")
    assert [item.knowledge_id for item in knowledge] == [
        "verification_state_vocabulary",
        "design_part_structured_contract_strategy",
    ]
    with pytest.raises(ValueError, match="not declared"):
        RUNTIME_SKILL_REGISTRY.knowledge_for_skill(
            "design_part",
            "model_program_api_patterns",
        )
    delegated = RUNTIME_SKILL_REGISTRY.skill("model_program")
    assert delegated is MODEL_PROGRAM_SKILL
    assert delegated.allowed_tools == frozenset(
        {"validate_model_program_source", "execute_model_program"}
    )
    assert delegated.allowed_context_keys == frozenset()
    assert delegated.stop_reasons == frozenset()


def test_provider_selects_context_contract_and_validation_actions(tmp_path, monkeypatch):
    monkeypatch.delenv("CADFLOW_MODEL_PROGRAM_SANDBOX", raising=False)
    adapter = _adapter(
        [
            {"action": "request_context", "context_key": "part_job"},
            {
                "action": "create_contract",
                "contract_type": "cad_ir_draft",
                "contract": _valid_contract(),
                "summary": "Create a compact bracket candidate.",
            },
            {"action": "request_validation"},
        ]
    )

    result = run_design_part_episode(
        adapter=adapter,
        handoff=_handoff(),
        artifact_dir=tmp_path,
    )
    client = adapter.client

    assert result.validated is True
    assert result.operation == "design_part"
    assert result.skill_id == "design_part"
    assert result.skill_version == "0.2.0"
    assert result.capability_mode == (
        "provider_selected_design_with_attested_model_program"
    )
    assert [request["operation"] for request in client.requests] == [
        "design_part_action",
        "design_part_action",
        "design_part_action",
    ]
    assert all(
        request["skill"]["allowed_tools"]
        == ["validate_structured_contract"]
        for request in client.requests
    )
    assert client.requests[0]["skill"]["delegated_skills"] == [
        {
            "skill_id": "model_program",
            "version": "0.1.0",
            "allowed_actions": [
                "create_model_program",
                "inspect_observation",
                "patch_model_program",
                "request_execution",
            ],
            "allowed_tools": [
                "execute_model_program",
                "validate_model_program_source",
            ],
            "output_contract_types": ["model_program_candidate"],
            "prohibited_side_effects": list(
                MODEL_PROGRAM_SKILL.prohibited_side_effects
            ),
        }
    ]
    action_contract = client.requests[0]["skill"]["agent_action_contract"]
    assert {
        variant["fields"]["action"]["const"]
        for variant in action_contract["variants"]
    } == DESIGN_PART_SKILL.allowed_actions
    assert [
        item["id"] for item in client.requests[0]["skill"]["knowledge"]
    ] == [
        "verification_state_vocabulary",
        "design_part_structured_contract_strategy",
    ]
    assert "Choose the next action" in client.requests[0]["messages"][0]["content"]
    result_artifact = json.loads(
        (tmp_path / "agent_result.json").read_text(encoding="utf-8")
    )
    assert result_artifact["skill"] == {
        "id": "design_part",
        "version": "0.2.0",
    }
    context_manifest = json.loads(
        (tmp_path / "context_manifest.json").read_text(encoding="utf-8")
    )
    assert [item["context_key"] for item in context_manifest["items"]] == [
        "part_job"
    ]
    assert context_manifest["items"][0]["work_id"] == "fixture_work"
    assert context_manifest["items"][0]["part_job_id"] == "clamp"
    assert context_manifest["items"][0]["trust_role"] == "accepted_input"
    tool_manifest = json.loads(
        (tmp_path / "tool_broker_manifest.json").read_text(encoding="utf-8")
    )
    assert tool_manifest["broker"] == "cadflow_tool_broker"
    assert {item["tool_id"] for item in tool_manifest["allowed_tools"]} == {
        "validate_structured_contract",
        "validate_model_program_source",
        "execute_model_program",
    }
    assert tool_manifest["delegated_skill_ids"] == ["model_program"]
    assert tool_manifest["model_program_capability"]["available"] is False
    events = [
        json.loads(line)
        for line in (tmp_path / "agent_events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    validation_event = next(
        event for event in events if event.get("observation") == "validation_passed"
    )
    assert validation_event["owner"] == "cadflow_tool_broker"
    assert validation_event["tool_id"] == "validate_structured_contract"
    assert validation_event["side_effect_started"] is False


def test_provider_repairs_after_observation_and_receives_feedback(tmp_path):
    invalid = {**_valid_contract(part_name="invalid_clamp"), "dimensions": {}}
    adapter = _adapter(
        [
            {
                "action": "create_contract",
                "contract_type": "cad_ir_draft",
                "contract": invalid,
            },
            {"action": "request_validation"},
            {
                "action": "patch_contract",
                "contract_type": "cad_ir_draft",
                "contract": _valid_contract(part_name="repaired_clamp"),
                "summary": "Restore required bracket dimensions.",
            },
            {"action": "request_validation"},
        ]
    )

    result = run_design_part_episode(
        adapter=adapter,
        handoff=_handoff(),
        artifact_dir=tmp_path,
    )

    assert result.validated is True
    assert result.contract_submission_count == 2
    assert result.repair_attempt_count == 1
    repair_request = adapter.client.requests[2]
    assert repair_request["state"]["validation_feedback"]["valid"] is False
    events = (tmp_path / "agent_events.jsonl").read_text(encoding="utf-8")
    assert '"observation": "validation_failed"' in events
    assert '"action": "patch_contract"' in events


def test_provider_can_ask_user_instead_of_guessing(tmp_path):
    adapter = _adapter(
        [
            {"action": "request_context", "context_key": "part_interfaces"},
            {
                "action": "ask_user",
                "reason": "The mating clearance is material to the design.",
                "questions": [
                    {
                        "field": "clearance_mm",
                        "question": "What radial clearance is required?",
                        "reason": "The interface context does not define it.",
                    }
                ],
            },
        ]
    )

    result = run_design_part_episode(
        adapter=adapter,
        handoff=_handoff(),
        artifact_dir=tmp_path,
    )

    assert result.validated is False
    assert result.stop_reason == StopReason.USER_INPUT_REQUIRED
    assert result.context_request_count == 1

    unfocused = _adapter([
        {"action": "ask_user", "questions": []},
        {
            "action": "ask_user",
            "questions": [{
                "field": "clearance_mm",
                "question": "What radial clearance is required?",
            }],
        },
    ])
    corrected = run_design_part_episode(
        adapter=unfocused,
        handoff=_handoff(),
        artifact_dir=tmp_path / "unfocused",
    )
    feedback = unfocused.client.requests[1]["state"]["action_contract_feedback"]
    assert feedback["kind"] == "action_contract_feedback"
    assert feedback["reason_code"] == "invalid_question_contract"
    assert feedback["rejected_action"] == "ask_user"
    assert corrected.stop_reason == StopReason.USER_INPUT_REQUIRED
    assert corrected.step_count == 2
    assert corrected.contract_repair_turn_count == 1


def test_skill_rejects_legacy_context_and_executable_contract_fields(tmp_path):
    legacy_context_adapter = _adapter(
        [{"action": "request_context", "context_key": "reviewed_part_handoff"}]
    )
    with pytest.raises(EpisodeContractError, match="active skill"):
        run_design_part_episode(
            adapter=legacy_context_adapter,
            handoff=_handoff(),
            artifact_dir=tmp_path / "legacy_context",
        )

    code_adapter = _adapter(
        [
            {
                "action": "create_contract",
                "contract_type": "cad_ir_draft",
                "contract": {**_valid_contract(), "python_code": "open('x','w')"},
            }
        ]
    )
    with pytest.raises(EpisodeContractError, match="forbidden execution field"):
        run_design_part_episode(
            adapter=code_adapter,
            handoff=_handoff(),
            artifact_dir=tmp_path / "code",
        )


def test_provider_failure_is_typed_and_does_not_persist_error_text(tmp_path):
    adapter = _adapter([RuntimeError("secret provider response")])

    result = run_design_part_episode(
        adapter=adapter,
        handoff=_handoff(),
        artifact_dir=tmp_path,
        budget=EpisodeBudget(max_steps=2),
    )

    assert result.stop_reason == StopReason.PROVIDER_FAILURE
    events = (tmp_path / "agent_events.jsonl").read_text(encoding="utf-8")
    assert "secret provider response" not in events
    assert '"observation": "provider_failure"' in events


def test_context_byte_budget_and_work_provenance_fail_closed(tmp_path):
    adapter = _adapter(
        [{"action": "request_context", "context_key": "part_job"}]
    )
    result = run_design_part_episode(
        adapter=adapter,
        handoff=_handoff(),
        artifact_dir=tmp_path,
        budget=EpisodeBudget(max_context_bytes=1),
    )
    assert result.stop_reason == StopReason.BUDGET_EXHAUSTED
    assert result.context_request_count == 0
    assert result.context_byte_count == 0

    broker = ContextBroker(
        [
            ContextItem(
                "part_job",
                "other_run",
                "part_job",
                "accepted_active_lineage",
                {},
                {"part_id": "other"},
                work_id="other_work",
                part_job_id="other",
            )
        ]
    )
    with pytest.raises(EpisodeContractError, match="unrelated Work"):
        broker.resolve(
            "part_job",
            allowed_keys=DESIGN_PART_SKILL.allowed_context_keys,
            expected_work_id="fixture_work",
        )


def test_provider_action_state_redacts_secrets_and_local_paths(tmp_path):
    handoff = {
        **_handoff(),
        "preserved_assembly_context": {
            "api_key": "sk-super-secret-value",
            "notes": r"Inspect D:\MyCode\private\fixture.step",
        },
    }
    adapter = _adapter(
        [
            {"action": "request_context", "context_key": "part_job"},
            {
                "action": "stop",
                "stop_reason": "insufficient_context",
                "reason": "No safe candidate yet.",
            },
        ]
    )

    result = run_design_part_episode(
        adapter=adapter,
        handoff=handoff,
        artifact_dir=tmp_path,
    )
    serialized = json.dumps(adapter.client.requests)

    assert result.stop_reason == StopReason.INSUFFICIENT_CONTEXT
    assert "sk-super-secret-value" not in serialized
    assert "D:\\\\MyCode" not in serialized
    assert "[redacted-local-path]" in serialized
