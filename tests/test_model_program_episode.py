from __future__ import annotations

import json

import pytest

from ai_native_cad.agents import (
    EpisodeBudget,
    EpisodeContractError,
    JsonContractAgentAdapter,
    StopReason,
    ToolObservation,
    run_design_part_episode,
)


SOURCE = """import cadquery as cq

def build_model(parameters):
    return cq.Workplane("XY").box(
        float(parameters["length"]),
        float(parameters["width"]),
        float(parameters["height"]),
    )
"""


class SequencedClient:
    def __init__(self, actions):
        self.actions = list(actions)
        self.requests = []

    @property
    def provider_identity(self):
        return {"provider": "scripted", "model": "episode-fixture"}

    def generate_json_contract(self, request):
        self.requests.append(request)
        return self.actions.pop(0)


class RecordingBroker:
    def __init__(self, observations):
        self.observations = list(observations)
        self.calls = []

    def manifest(self, *, active_skill_id, delegated_skill_ids=()):
        return {
            "schema_version": 1,
            "broker": "cadflow_tool_broker",
            "active_skill_id": active_skill_id,
            "delegated_skill_ids": list(delegated_skill_ids),
            "allowed_tools": [],
            "model_program_capability": {"available": True},
        }

    def invoke(self, tool_id, *, skill_id, payload, context=None):
        self.calls.append(
            {
                "tool_id": tool_id,
                "skill_id": skill_id,
                "payload": payload,
                "context": context,
            }
        )
        return self.observations.pop(0)


def _handoff():
    return {
        "work_id": "work_1",
        "part_id": "part_1",
        "status": "ready_for_single_part_planning",
        "part_brief": "A parameterized rectangular solid",
        "interface_constraints": [],
        "preserved_assembly_context": {},
    }


def _program(source=SOURCE):
    return {
        "api_id": "cadquery_v1",
        "source": source,
        "parameters": {"length": 30, "width": 20, "height": 10},
        "requested_outputs": ["step"],
    }


def _observation(*, success=True, code=None):
    geometry = {
        "valid": success,
        "solid_count": 1 if success else 0,
        "face_count": 6 if success else 0,
        "cylindrical_face_count": 0,
        "volume": 6000.0 if success else 0.0,
        "bounding_box": {"x": 30.0, "y": 20.0, "z": 10.0},
    }
    return ToolObservation(
        tool_id="execute_model_program",
        success=success,
        observation_type=(
            "model_program_execution_completed"
            if success
            else "model_program_execution_failed"
        ),
        codes=() if success else (code or "model_program_runtime_error",),
        output={
            "candidate_id": "candidate_001",
            "execution_id": "exec_fixture",
            "source_hash": "source-hash",
            "parameters_hash": "parameters-hash",
            "profile_digest": "profile-digest",
            "toolchain_digest": "toolchain-digest",
            "geometry": geometry,
            "step_reimport": {
                "valid": success,
                "geometry": dict(geometry),
            },
            "outputs": [
                {
                    "name": "model.step",
                    "sha256": "a" * 64,
                    "size": 1234,
                    "relative_path": "candidates/private/model.step",
                }
            ] if success else [],
            "reviewable": False,
            "accepted": False,
            "deliverable": False,
        },
        execution_profile="wsl2_cadquery_v1",
        side_effect_started=True,
        execution_id="exec_fixture",
        attestation_digest="attestation-digest",
        exit_state="completed" if success else "failed",
    )


def _adapter(actions):
    client = SequencedClient(actions)
    return JsonContractAgentAdapter(
        client,
        provider="scripted",
        model="episode-fixture",
    )


def test_model_program_episode_assigns_identity_executes_inspects_and_completes(
    tmp_path,
):
    adapter = _adapter(
        [
            {"action": "create_model_program", "model_program": _program()},
            {"action": "request_execution"},
            {"action": "inspect_observation"},
            {"action": "stop", "stop_reason": "completed"},
        ]
    )
    broker = RecordingBroker([_observation()])

    result = run_design_part_episode(
        adapter=adapter,
        handoff=_handoff(),
        artifact_dir=tmp_path,
        tool_broker=broker,
        run_id="run_1",
    )

    assert result.status == "completed"
    assert result.stop_reason == StopReason.COMPLETED
    assert result.result_kind == "model_program"
    assert result.validated is False
    assert result.output_validated is True
    assert result.source_submission_count == 1
    assert result.execution_count == 1
    assert result.observation_inspection_count == 1
    assert result.final_candidate_id == "candidate_001"
    assert result.final_observation_id == "observation_001"
    assert broker.calls[0]["skill_id"] == "model_program"
    assert broker.calls[0]["payload"]["candidate_id"] == "candidate_001"
    context = broker.calls[0]["context"]
    assert (context.work_id, context.run_id, context.part_job_id) == (
        "work_1",
        "run_1",
        "part_1",
    )
    assert context.evidence_root == tmp_path.resolve()
    submission = json.loads(
        (
            tmp_path
            / "model_program_submissions"
            / "submission_001.json"
        ).read_text(encoding="utf-8")
    )
    assert submission["source_retained"] is False
    assert submission["parameters_retained"] is False
    assert not list((tmp_path / "model_program_submissions").glob("*.py"))
    observation = json.loads(
        (
            tmp_path
            / "execution_observations"
            / "observation_001.json"
        ).read_text(encoding="utf-8")
    )
    assert observation["reviewable"] is False
    provider_state = adapter.client.requests[3]["state"]
    inspected = provider_state["supplied_context"][-1]["content"]
    assert inspected["outputs"] == [
        {"name": "model.step", "sha256": "a" * 64, "size": 1234}
    ]
    assert "relative_path" not in json.dumps(inspected)
    events = (tmp_path / "agent_events.jsonl").read_text(encoding="utf-8")
    assert SOURCE not in events


def test_failed_observation_must_be_inspected_before_full_replacement_patch(
    tmp_path,
):
    repaired_source = SOURCE.replace(".box(", ".box(") + "\n"
    adapter = _adapter(
        [
            {"action": "create_model_program", "model_program": _program()},
            {"action": "request_execution"},
            {"action": "inspect_observation"},
            {
                "action": "patch_model_program",
                "model_program": _program(repaired_source),
                "summary": "Replace the complete program after inspecting the runtime observation.",
            },
            {"action": "request_execution"},
            {"action": "inspect_observation"},
            {"action": "stop", "stop_reason": "completed"},
        ]
    )
    broker = RecordingBroker(
        [_observation(success=False), _observation(success=True)]
    )

    result = run_design_part_episode(
        adapter=adapter,
        handoff=_handoff(),
        artifact_dir=tmp_path,
        tool_broker=broker,
        run_id="run_1",
    )

    assert result.output_validated is True
    assert result.source_submission_count == 2
    assert result.execution_count == 2
    assert result.observation_inspection_count == 2
    assert result.repair_attempt_count == 1
    assert [call["payload"]["candidate_id"] for call in broker.calls] == [
        "candidate_001",
        "candidate_002",
    ]


@pytest.mark.parametrize(
    "action,match",
    [
        (
            {
                "action": "request_execution",
                "candidate_id": "provider_chosen",
            },
            "strict action contract",
        ),
        (
            {
                "action": "create_model_program",
                "model_program": {**_program(), "command": "python source.py"},
            },
            "requires exactly",
        ),
        (
            {
                "action": "inspect_observation",
                "observation_id": "provider_chosen",
            },
            "strict action contract",
        ),
    ],
)
def test_model_program_actions_reject_provider_identity_path_and_command_fields(
    tmp_path, action, match
):
    broker = RecordingBroker([_observation()])
    with pytest.raises(EpisodeContractError, match=match):
        run_design_part_episode(
            adapter=_adapter([action]),
            handoff=_handoff(),
            artifact_dir=tmp_path,
            tool_broker=broker,
            run_id="run_1",
        )
    assert broker.calls == []


def test_model_program_cannot_complete_before_inspecting_success_observation(
    tmp_path,
):
    adapter = _adapter(
        [
            {"action": "create_model_program", "model_program": _program()},
            {"action": "request_execution"},
            {"action": "stop", "stop_reason": "completed"},
        ]
    )
    with pytest.raises(EpisodeContractError, match="inspected"):
        run_design_part_episode(
            adapter=adapter,
            handoff=_handoff(),
            artifact_dir=tmp_path,
            tool_broker=RecordingBroker([_observation()]),
            run_id="run_1",
        )


def test_model_program_cannot_complete_without_allowlisted_step_summary(
    tmp_path,
):
    invalid = _observation()
    invalid.output["outputs"].clear()
    adapter = _adapter(
        [
            {"action": "create_model_program", "model_program": _program()},
            {"action": "request_execution"},
            {"action": "inspect_observation"},
            {"action": "stop", "stop_reason": "completed"},
        ]
    )
    with pytest.raises(EpisodeContractError, match="STEP-reimport-validated"):
        run_design_part_episode(
            adapter=adapter,
            handoff=_handoff(),
            artifact_dir=tmp_path,
            tool_broker=RecordingBroker([invalid]),
            run_id="run_1",
        )


def test_unavailable_execution_retains_hashes_but_no_source_file(tmp_path):
    unavailable = ToolObservation(
        tool_id="execute_model_program",
        success=False,
        observation_type="sandbox_unavailable",
        codes=("sandbox_unavailable",),
        output={
            "blocked": True,
            "source_hash": "source-hash",
            "reviewable": False,
            "accepted": False,
            "deliverable": False,
        },
        execution_profile="wsl2_cadquery_v1",
        side_effect_started=False,
    )
    adapter = _adapter(
        [
            {"action": "create_model_program", "model_program": _program()},
            {"action": "request_execution"},
            {"action": "inspect_observation"},
            {
                "action": "stop",
                "stop_reason": "policy_blocked",
                "reason": "The required sandbox is unavailable.",
            },
        ]
    )

    result = run_design_part_episode(
        adapter=adapter,
        handoff=_handoff(),
        artifact_dir=tmp_path,
        tool_broker=RecordingBroker([unavailable]),
        run_id="run_1",
    )

    assert result.stop_reason == StopReason.POLICY_BLOCKED
    assert result.execution_succeeded is False
    assert not list(tmp_path.rglob("source.py"))
    submission = json.loads(
        (
            tmp_path
            / "model_program_submissions"
            / "submission_001.json"
        ).read_text(encoding="utf-8")
    )
    assert submission["source_retained"] is False


@pytest.mark.parametrize(
    "budget,actions,expected_field",
    [
        (
            EpisodeBudget(max_source_submissions=0),
            [{"action": "create_model_program", "model_program": _program()}],
            "source_submission_count",
        ),
        (
            EpisodeBudget(max_executions=0),
            [
                {"action": "create_model_program", "model_program": _program()},
                {"action": "request_execution"},
            ],
            "execution_count",
        ),
        (
            EpisodeBudget(max_observation_inspections=0),
            [
                {"action": "create_model_program", "model_program": _program()},
                {"action": "request_execution"},
                {"action": "inspect_observation"},
            ],
            "observation_inspection_count",
        ),
    ],
)
def test_model_program_budgets_fail_closed(
    tmp_path, budget, actions, expected_field
):
    result = run_design_part_episode(
        adapter=_adapter(actions),
        handoff=_handoff(),
        artifact_dir=tmp_path,
        tool_broker=RecordingBroker([_observation()]),
        run_id="run_1",
        budget=budget,
    )
    assert result.stop_reason == StopReason.BUDGET_EXHAUSTED
    assert getattr(result, expected_field) == 0
