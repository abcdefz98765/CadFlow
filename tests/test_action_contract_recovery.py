from __future__ import annotations

import json
from copy import deepcopy

import pytest

from ai_native_cad.agents import (
    AgentCapabilities,
    AgentObjective,
    ContextBroker,
    ContextEnvelope,
    EpisodeBudget,
    EpisodeContractError,
    EpisodeOrchestrator,
    JsonContractAgentAdapter,
    StopReason,
    ToolObservation,
    run_design_part_episode,
    run_work_design_episode,
)
from ai_native_cad.agents.registry import RUNTIME_SKILL_REGISTRY
from ai_native_cad.agents.provider_sanitization import sanitize_provider_payload
from ai_native_cad.agents.work_design_contract import (
    work_design_contract_description,
    work_design_fields,
)
from ai_native_cad.workflow_console.agent_activity import significant_activity


class SequencedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    @property
    def provider_identity(self):
        return {"provider": "scripted", "model": "contract-recovery"}

    def generate_json_contract(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def _adapter(responses):
    client = SequencedClient(responses)
    return JsonContractAgentAdapter(
        client, provider="scripted", model="contract-recovery"
    ), client


def _proposal():
    return {
        "objective": "Place a compact robot arm on a stable desktop base.",
        "concept_summary": "Use one generated mounting base for the arm.",
        "generated_parts": [{
            "key": "mounting_base",
            "name": "Mounting base",
            "role": "Support the robot arm",
            "interfaces": ["Robot arm bolt pattern"],
            "dependencies": [],
        }],
        "reference_components": [{
            "name": "Robot arm",
            "role": "Existing mechanism",
            "interfaces": ["Base bolt pattern"],
        }],
        "interfaces": [],
        "dependencies": [],
        "assumptions": ["Desktop prototype loads"],
        "unresolved_questions": [],
        "assembly_expected": False,
        "recommendation": "Create the mounting base Part.",
    }


def _work_context():
    return {
        "work_id": "robot_arm_work",
        "title": "Desktop robot arm",
        "description": "Design a stable mounting base for a desktop robot arm.",
        "accepted_part_count": 0,
        "clarification_answers": [],
    }


def _run_work_design(tmp_path, responses, *, budget=None):
    adapter, client = _adapter(responses)
    work_context = _work_context()
    before = deepcopy(work_context)
    result = run_work_design_episode(
        adapter=adapter,
        work_context=work_context,
        artifact_dir=tmp_path,
        run_id="work_design_run",
        budget=budget,
    )
    assert work_context == before
    assert not list(tmp_path.rglob("*.step"))
    assert not list(tmp_path.rglob("*.stl"))
    return result, client


def test_work_design_repairs_case_a_request_context_extra_parameters_in_same_episode(
    tmp_path,
):
    result, client = _run_work_design(
        tmp_path,
        [
            {
                "action": "request_context",
                "context_key": "work_request",
                "parameters": {"detail": "full"},
            },
            {"action": "request_context", "context_key": "work_request"},
            {"action": "propose_work_design", "work_design": _proposal()},
            {"action": "create_part_jobs"},
        ],
    )

    assert result.status == "completed"
    assert result.step_count == 4
    assert result.contract_repair_turn_count == 1
    feedback = client.requests[1]["state"]["action_contract_feedback"]
    assert feedback == {
        "kind": "action_contract_feedback",
        "rejected_action": "request_context",
        "reason_code": "action_contract_extra_fields",
        "message": "Return the action again using only its allowed fields.",
        "allowed_fields": ["action", "context_key", "reason"],
        "required_fields": ["action", "context_key"],
        "invalid_field": "parameters",
    }
    assert client.requests[2]["state"]["action_contract_feedback"] is None
    events = [
        json.loads(line)
        for line in (tmp_path / "agent_events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    correction = [item for item in events if item.get("observation") == "action_contract_feedback"]
    assert len(correction) == 1
    assert "workflow_node" not in correction[0]
    assert "parameters" not in json.dumps(correction[0].get("allowed_fields"))


@pytest.mark.parametrize("nested", [False, True])
def test_work_design_repairs_case_b_acceptance_criteria_contract_mistake(
    tmp_path, nested
):
    invalid = _proposal()
    if nested:
        invalid["generated_parts"][0]["acceptance_criteria"] = ["Does not wobble"]
        bad_action = {"action": "propose_work_design", "work_design": invalid}
    else:
        bad_action = {
            "action": "propose_work_design",
            "work_design": invalid,
            "acceptance_criteria": ["Does not wobble"],
        }
    result, client = _run_work_design(
        tmp_path,
        [
            bad_action,
            {"action": "propose_work_design", "work_design": _proposal()},
            {"action": "create_part_jobs"},
        ],
    )

    assert result.status == "completed"
    assert result.step_count == 3
    feedback = client.requests[1]["state"]["action_contract_feedback"]
    assert feedback["invalid_field"] == "acceptance_criteria"
    assert feedback["reason_code"] == (
        "invalid_work_design_contract" if nested else "action_contract_extra_fields"
    )
    assert feedback["expected_work_design_fields"] == sorted(_proposal())
    assert "Does not wobble" not in json.dumps(feedback)


def test_first_work_design_provider_request_discloses_complete_canonical_contract(
    tmp_path,
):
    _, client = _run_work_design(
        tmp_path,
        [{"action": "stop", "stop_reason": "insufficient_context"}],
    )

    disclosed = client.requests[0]["skill"]["work_design_contract"]
    assert disclosed == work_design_contract_description()
    assert disclosed["additional_fields"] is False
    assert tuple(disclosed["required_fields"]) == work_design_fields()
    generated = disclosed["fields"]["generated_parts"]
    assert (generated["type"], generated["min_items"], generated["max_items"]) == (
        "list", 1, 12,
    )
    assert generated["unique_by"] == "key"
    assert generated["items"]["additional_fields"] is False
    assert tuple(generated["items"]["required_fields"]) == work_design_fields(
        "generated_parts[]"
    )
    assert generated["items"]["fields"]["key"] == {
        "type": "text", "non_empty": True, "max_length": 120,
    }
    references = disclosed["fields"]["reference_components"]
    assert references["max_items"] == 24
    assert references["items"]["additional_fields"] is False
    assert tuple(references["items"]["required_fields"]) == work_design_fields(
        "reference_components[]"
    )
    for relation_name, maximum in (("interfaces", 48), ("dependencies", 24)):
        relation = disclosed["fields"][relation_name]
        assert relation["max_items"] == maximum
        assert relation["items"]["additional_fields"] is False
        assert tuple(relation["items"]["required_fields"]) == work_design_fields(
            f"{relation_name}[]"
        )
    assert disclosed["fields"]["assembly_expected"] == {"type": "boolean"}
    assert disclosed["fields"]["recommendation"]["max_length"] == 1_000


def test_provider_sanitizer_preserves_only_safe_contract_field_paths():
    assert sanitize_provider_payload(
        {"field_path": "generated_parts[].key"}
    ) == {"field_path": "generated_parts[].key"}
    assert sanitize_provider_payload({"field_path": "C:/private/work.json"}) == {}
    assert sanitize_provider_payload({"field_path": "../private"}) == {}


@pytest.mark.parametrize(
    ("scope", "unsafe_key", "expected_parent_path"),
    [
        ("top", "api_key", "work_design"),
        ("generated_part", "targetWorkId", "generated_parts[]"),
    ],
)
def test_unsafe_extra_field_names_never_enter_diagnostics_or_evidence(
    tmp_path,
    scope,
    unsafe_key,
    expected_parent_path,
):
    raw_marker = "RAW_UNSAFE_FIELD_VALUE_MUST_NOT_PERSIST"
    invalid = _proposal()
    if scope == "top":
        invalid[unsafe_key] = raw_marker
    else:
        invalid["generated_parts"][0][unsafe_key] = raw_marker
    adapter, client = _adapter([
        {"action": "propose_work_design", "work_design": invalid}
    ])

    with pytest.raises(EpisodeContractError) as caught:
        run_work_design_episode(
            adapter=adapter,
            work_context=_work_context(),
            artifact_dir=tmp_path,
            run_id="work_design_run",
        )

    diagnostic = caught.value.failure_diagnostic
    assert diagnostic["field_issue"] == "extra"
    assert diagnostic["field_path"] == expected_parent_path
    assert diagnostic["requested_capability_or_context"] is None
    assert diagnostic["expected_fields"] == sorted(
        work_design_fields(
            "generated_parts[]" if scope == "generated_part" else ""
        )
    )
    assert unsafe_key not in json.dumps(diagnostic)
    assert raw_marker not in json.dumps(diagnostic)
    assert len(client.requests) == 1
    persisted_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    assert unsafe_key not in persisted_text
    assert raw_marker not in persisted_text
    assert "action_contract_feedback" not in persisted_text
    assert not (tmp_path / "agent_events.jsonl").exists()
    assert not (tmp_path / "agent_result.json").exists()


@pytest.mark.parametrize(
    ("case", "field_issue", "field_path", "object_path"),
    [
        ("top_extra", "extra", "acceptance_criteria", ""),
        ("top_missing", "missing", "recommendation", ""),
        ("missing_and_extra", "missing", "recommendation", ""),
        (
            "generated_extra",
            "extra",
            "generated_parts[].acceptance_criteria",
            "generated_parts[]",
        ),
        ("generated_missing", "missing", "generated_parts[].key", "generated_parts[]"),
        (
            "reference_shape",
            "invalid_shape",
            "reference_components[]",
            "reference_components[]",
        ),
        ("interface_missing", "missing", "interfaces[].from", "interfaces[]"),
        ("dependency_shape", "invalid_shape", "dependencies[]", "dependencies[]"),
        ("wrong_type", "invalid_type", "assembly_expected", ""),
        ("invalid_value", "invalid_value", "recommendation", ""),
    ],
)
def test_work_design_mismatch_feedback_is_precise_local_and_value_free(
    tmp_path,
    case,
    field_issue,
    field_path,
    object_path,
):
    invalid = _proposal()
    invalid["concept_summary"] = "RAW_PAYLOAD_VALUE_MUST_NOT_LEAK"
    if case == "top_extra":
        invalid["acceptance_criteria"] = ["RAW acceptance"]
    elif case == "top_missing":
        del invalid["recommendation"]
    elif case == "missing_and_extra":
        del invalid["recommendation"]
        invalid["acceptance_criteria"] = ["RAW acceptance"]
    elif case == "generated_extra":
        invalid["generated_parts"][0]["acceptance_criteria"] = ["RAW acceptance"]
    elif case == "generated_missing":
        del invalid["generated_parts"][0]["key"]
    elif case == "reference_shape":
        invalid["reference_components"] = ["RAW reference component"]
    elif case == "interface_missing":
        invalid["interfaces"] = [{"to": "target", "description": "RAW relation"}]
    elif case == "dependency_shape":
        invalid["dependencies"] = ["RAW dependency"]
    elif case == "wrong_type":
        invalid["assembly_expected"] = "RAW boolean"
    elif case == "invalid_value":
        invalid["recommendation"] = ""

    result, client = _run_work_design(
        tmp_path,
        [
            {"action": "propose_work_design", "work_design": invalid},
            {"action": "propose_work_design", "work_design": _proposal()},
            {"action": "create_part_jobs"},
        ],
    )

    assert result.status == "completed"
    feedback = client.requests[1]["state"]["action_contract_feedback"]
    assert feedback["field_issue"] == field_issue
    assert feedback["field_path"] == field_path
    assert feedback["expected_fields"] == sorted(work_design_fields(object_path))
    assert feedback["expected_work_design_fields"] == sorted(work_design_fields())
    assert "RAW" not in json.dumps(feedback)


def test_exhausted_work_design_repair_preserves_precise_terminal_diagnostic(tmp_path):
    invalid = _proposal()
    invalid["acceptance_criteria"] = ["RAW_PAYLOAD_VALUE_MUST_NOT_LEAK"]
    action = {"action": "propose_work_design", "work_design": invalid}

    result, client = _run_work_design(tmp_path, [action, action, action])

    assert result.contract_repair_exhausted is True
    assert result.failure_diagnostic["field_issue"] == "extra"
    assert result.failure_diagnostic["field_path"] == "acceptance_criteria"
    assert result.failure_diagnostic["expected_fields"] == sorted(work_design_fields())
    assert "RAW_PAYLOAD_VALUE_MUST_NOT_LEAK" not in json.dumps(
        result.failure_diagnostic
    )
    assert len(client.requests) == 3


def test_contract_repair_budget_exhausts_once_after_two_corrections(tmp_path):
    bad = {"action": "request_context", "parameters": {}}
    result, client = _run_work_design(tmp_path, [bad, bad, bad])

    assert result.status == "safely_blocked"
    assert result.stop_reason == StopReason.POLICY_BLOCKED
    assert result.step_count == 3
    assert result.contract_repair_turn_count == 2
    assert result.contract_repair_exhausted is True
    assert result.failure_diagnostic["contract_repair_exhausted"] is True
    assert result.failure_diagnostic["contract_repair_turn_count"] == 2
    assert len(client.requests) == 3
    events = (tmp_path / "agent_events.jsonl").read_text(encoding="utf-8")
    assert events.count('"observation": "action_contract_feedback"') == 3
    assert events.count('"contract_repair_exhausted": true') == 1


@pytest.mark.parametrize(
    "bad_action",
    [
        {"action": "unknown_action", "parameters": {}},
        {"action": "request_context", "context_key": "work_request", "path": "C:/private"},
        {"action": "request_context", "context_key": "work_request", "work_id": "other"},
        {"action": "create_contract"},
    ],
)
def test_unknown_authority_and_forbidden_boundaries_never_retry(tmp_path, bad_action):
    adapter, client = _adapter(
        [bad_action, {"action": "propose_work_design", "work_design": _proposal()}]
    )
    with pytest.raises((EpisodeContractError, ValueError)):
        run_work_design_episode(
            adapter=adapter,
            work_context=_work_context(),
            artifact_dir=tmp_path,
            run_id="work_design_run",
        )
    assert len(client.requests) == 1


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "target_work_id",
        "source_run_id",
        "workspace_id",
        "targetWorkId",
        "sourceRunId",
        "workspaceId",
        "authorization",
        "authentication",
        "permission",
        "bypass",
        "identity",
        "capability",
        "access",
        "toolAuthorization",
    ],
)
def test_identity_and_authority_aliases_never_enter_contract_repair(
    tmp_path, forbidden_field
):
    adapter, client = _adapter([
        {
            "action": "request_context",
            "context_key": "work_request",
            forbidden_field: "must-not-be-reflected",
        },
        {"action": "request_context", "context_key": "work_request"},
    ])
    with pytest.raises(EpisodeContractError):
        run_work_design_episode(
            adapter=adapter,
            work_context=_work_context(),
            artifact_dir=tmp_path,
            run_id="work_design_run",
        )
    assert len(client.requests) == 1


def test_generic_episode_repairs_parse_contract_mistake_and_counts_bad_step(tmp_path):
    envelope = ContextEnvelope(
        objective=AgentObjective("create_part_ir", "Create a contract"),
        workflow={"active_leaf_run_id": "run_1"},
        accepted_decisions=(),
        selected_part={},
        constraints=(),
        previous_attempts=(),
        available_context=(),
    )
    orchestrator = EpisodeOrchestrator(
        objective=envelope.objective,
        context_envelope=envelope,
        context_broker=ContextBroker([]),
        capabilities=AgentCapabilities(),
        budget=EpisodeBudget(),
        validate_contract=lambda contract: {"valid": True, "errors": []},
        artifact_dir=tmp_path,
    )
    actions = iter([
        {"action": "request_validation", "parameters": {}},
        {"action": "submit_contract", "contract_type": "cad_ir_draft", "contract": {"shape": "box"}},
        {"action": "request_validation"},
    ])
    seen = []

    def supplier(state):
        seen.append(deepcopy(state))
        return next(actions)

    result = orchestrator.run(supplier)
    assert result.status == "completed"
    assert result.step_count == 3
    assert result.contract_repair_turn_count == 1
    assert seen[1]["action_contract_feedback"]["rejected_action"] == "request_validation"
    assert seen[2]["action_contract_feedback"] is None


class SideEffectBroker:
    def __init__(self):
        self.calls = []

    def manifest(self, *, active_skill_id, delegated_skill_ids=()):
        return {
            "schema_version": 1,
            "active_skill_id": active_skill_id,
            "delegated_skill_ids": list(delegated_skill_ids),
            "allowed_tools": [],
        }

    def invoke(self, tool_id, *, skill_id, payload, context=None):
        self.calls.append(tool_id)
        return ToolObservation(
            tool_id=tool_id,
            success=False,
            observation_type="model_program_execution_failed",
            codes=("runtime_error",),
            output={"reviewable": False, "accepted": False, "deliverable": False},
            execution_profile="test",
            side_effect_started=True,
            execution_id="exec_1",
            exit_state="failed",
        )


def test_accumulated_side_effect_started_blocks_later_contract_auto_repair(tmp_path):
    program = {
        "api_id": "cadquery_v1",
        "source": "def build_model(parameters):\n    return None\n",
        "parameters": {},
        "requested_outputs": ["step"],
    }
    adapter, client = _adapter([
        {"action": "create_model_program", "model_program": program},
        {"action": "request_execution"},
        {"action": "inspect_observation", "parameters": {}},
        {"action": "inspect_observation"},
    ])
    broker = SideEffectBroker()
    with pytest.raises(EpisodeContractError, match="strict action contract") as caught:
        run_design_part_episode(
            adapter=adapter,
            handoff={
                "work_id": "work_1",
                "part_id": "part_1",
                "status": "ready_for_single_part_planning",
                "part_brief": "A test Part",
                "interface_constraints": [],
                "preserved_assembly_context": {},
            },
            artifact_dir=tmp_path,
            tool_broker=broker,
            run_id="run_1",
        )
    diagnostic = caught.value.failure_diagnostic
    assert diagnostic["reason_code"] == "action_contract_extra_fields"
    assert diagnostic["rejected_action"] == "inspect_observation"
    assert diagnostic["requested_capability_or_context"] == "parameters"
    assert diagnostic["human_safe_detail"] == (
        "The Agent returned fields that the inspect_observation action does not allow."
    )
    assert diagnostic["side_effect_started"] is True
    assert len(client.requests) == 3
    assert len(broker.calls) == 1
    assert len(list((tmp_path / "model_program_submissions").glob("*.json"))) == 1
    assert len(list((tmp_path / "execution_observations").glob("*.json"))) == 1


def test_runtime_skill_manifests_authorize_two_contract_repair_turns():
    manifests = [
        RUNTIME_SKILL_REGISTRY.skill(skill_id).manifest()
        for skill_id in ("work_design", "design_part", "model_program")
    ]
    assert [item["budget"]["max_contract_repair_turns"] for item in manifests] == [2, 2, 2]
    assert EpisodeBudget(8, 4, 65536, 3, 2, 4, 3, 3, 180.0).max_contract_repair_turns == 2


def test_action_contract_feedback_collapses_to_one_activity_row():
    rows = significant_activity(
        [
            {"kind": "system_observation", "summary": "action contract feedback"},
            {"kind": "action_contract_feedback"},
        ],
        language="en",
    )
    assert rows == [{
        "key": "action_contract_feedback",
        "label": "Corrected the action format",
        "summary": None,
        "count": 1,
    }]
