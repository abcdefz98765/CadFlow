import json

import pytest

from ai_native_cad.agents.episode import (
    AgentAction,
    AgentCapabilities,
    AgentObjective,
    ContextBroker,
    ContextEnvelope,
    ContextItem,
    EpisodeBudget,
    EpisodeOrchestrator,
    StopReason,
    UnknownAgentActionError,
    build_create_part_ir_context,
    run_create_part_ir_episode,
)
from ai_native_cad.agents.deterministic import DeterministicAgentAdapter


def _orchestrator(tmp_path, *, budget=EpisodeBudget(), valid=True):
    objective = AgentObjective("create_part_ir", "Create a CAD IR draft for spacer")
    item = ContextItem(
        "reviewed_part_handoff", "active-run", "reviewed_part_handoff",
        "accepted_active_lineage", {"part_id": "spacer"}, {"part_id": "spacer"},
    )
    envelope = ContextEnvelope(objective, {"active_leaf_run_id": "active-run"}, (), {"part_id": "spacer"}, (), (), ("reviewed_part_handoff",))
    return EpisodeOrchestrator(
        objective, envelope, ContextBroker([item]), AgentCapabilities(), budget,
        lambda contract: {"valid": valid, "errors": [] if valid else [{"code": "invalid_ir"}]},
        tmp_path,
    )


def _valid_spacer_contract():
    return {
        "part_type": "spacer", "part_name": "episode_spacer", "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 5, "thickness": 10},
        "features": {}, "outputs": ["step", "stl"], "check_level": "L0",
    }


def test_unknown_action_is_rejected(tmp_path):
    with pytest.raises(UnknownAgentActionError):
        _orchestrator(tmp_path).run(lambda state: {"action": "run_shell"})


def test_step_context_and_submission_budgets_are_enforced(tmp_path):
    result = _orchestrator(tmp_path / "steps", budget=EpisodeBudget(max_steps=1)).run(
        lambda state: AgentAction(action="request_context", context_key="reviewed_part_handoff")
    )
    assert result.stop_reason == StopReason.BUDGET_EXHAUSTED

    result = _orchestrator(tmp_path / "context", budget=EpisodeBudget(max_context_requests=0)).run(
        lambda state: AgentAction(action="request_context", context_key="reviewed_part_handoff")
    )
    assert result.context_request_count == 0
    assert result.stop_reason == StopReason.BUDGET_EXHAUSTED

    result = _orchestrator(tmp_path / "submission", budget=EpisodeBudget(max_contract_submissions=0)).run(
        lambda state: AgentAction(action="submit_contract", contract_type="cad_ir_draft", contract=_valid_spacer_contract())
    )
    assert result.contract_submission_count == 0
    assert result.stop_reason == StopReason.BUDGET_EXHAUSTED


def test_context_broker_rejects_paths_and_superseded_items():
    broker = ContextBroker([
        ContextItem("reviewed_part_handoff", "active", "reviewed_part_handoff", "accepted_active_lineage", {}, {}, active=True),
        ContextItem("assembly_plan", "old", "assembly_plan", "superseded", {}, {}, active=False),
    ])
    with pytest.raises(ValueError):
        broker.resolve("C:/arbitrary/artifact.json")
    with pytest.raises(ValueError):
        broker.resolve("assembly_plan")


def test_unvalidated_contract_stops_before_execution_boundary(tmp_path):
    phases = iter([
        AgentAction(action="submit_contract", contract_type="cad_ir_draft", contract=_valid_spacer_contract()),
        AgentAction(action="request_validation"),
        AgentAction(action="stop", stop_reason=StopReason.VALIDATION_EXHAUSTED),
    ])
    result = _orchestrator(tmp_path, valid=False).run(lambda state: next(phases))
    assert result.validated is False
    assert result.final_contract == _valid_spacer_contract()
    assert result.stop_reason == StopReason.VALIDATION_EXHAUSTED


def test_deterministic_episode_artifacts_and_output_are_stable(tmp_path):
    handoff = {
        "part_id": "spacer", "status": "ready_for_single_part_planning",
        "part_brief": "Printable spacer", "interface_constraints": [{"kind": "through_hole", "related_part_id": "base"}],
        "preserved_assembly_context": {"assembly_scope": "multi_part", "related_parts": ["base"]},
    }
    execution_request = {"child_run_id": "single_part_spacer", "prompt": "Create spacer"}
    adapter = DeterministicAgentAdapter()
    expected = adapter.create_part_ir(handoff, context={"prompt": "Create spacer"})
    result = run_create_part_ir_episode(
        adapter=adapter, handoff=handoff, execution_request=execution_request,
        adapter_context={"prompt": "Create spacer"}, artifact_dir=tmp_path,
    )

    assert result.validated is True
    assert result.final_contract == expected
    for name in ("agent_episode.json", "context_manifest.json", "agent_events.jsonl", "agent_result.json"):
        assert (tmp_path / name).exists()
    assert (tmp_path / "contract_submissions" / "submission_001.json").exists()
    assert (tmp_path / "validation_feedback" / "validation_001.json").exists()
    result_artifact = json.loads((tmp_path / "agent_result.json").read_text(encoding="utf-8"))
    assert result_artifact["capability_mode"] == "deterministic_fallback"
    assert all("chain" not in path.name.lower() for path in tmp_path.rglob("*"))
    assert "raw" not in (tmp_path / "agent_events.jsonl").read_text(encoding="utf-8").lower()


def test_create_part_context_contains_only_active_lineage_items():
    envelope, broker = build_create_part_ir_context(
        {"part_id": "upper_link", "status": "ready_for_single_part_planning", "preserved_assembly_context": {}},
        run_id="active-run", execution_request={},
    )
    assert "reviewed_part_handoff" in envelope.available_context
    assert broker.resolve("reviewed_part_handoff").source_run_id == "active-run"


def test_scripted_repair_loop_uses_context_and_validation_observation(tmp_path):
    seen = []

    def validator(contract):
        return {"valid": contract["part_name"] == "repaired_spacer", "errors": [] if contract["part_name"] == "repaired_spacer" else [{"code": "needs_repair"}]}

    def proposer(state):
        seen.append(state)
        if state["state"] == "created":
            return AgentAction(action="request_context", context_key="reviewed_part_handoff")
        if state["state"] == "gathering_context":
            assert state["supplied_context"][0]["content"]["part_id"] == "spacer"
            return AgentAction(action="submit_contract", contract_type="cad_ir_draft", contract=_valid_spacer_contract())
        if state["state"] == "proposing":
            return AgentAction(action="request_validation")
        if state["state"] == "awaiting_validation":
            assert state["validation_feedback"]["errors"][0]["code"] == "needs_repair"
            repaired = {**_valid_spacer_contract(), "part_name": "repaired_spacer"}
            return AgentAction(action="repair_contract", contract_type="cad_ir_draft", contract=repaired, summary="Adjusted spacer after validator feedback.")
        return AgentAction(action="request_validation")

    result = _orchestrator(tmp_path, budget=EpisodeBudget(max_steps=8, max_repair_attempts=1), valid=True)
    result.validate_contract = validator
    outcome = result.run(proposer)
    assert outcome.validated is True
    assert outcome.contract_submission_count == 2
    assert outcome.repair_attempt_count == 1
    events = (tmp_path / "agent_events.jsonl").read_text(encoding="utf-8")
    assert '"event_type": "system_observation"' in events
    assert '"codes": ["needs_repair"]' in events
    episode = json.loads((tmp_path / "agent_episode.json").read_text(encoding="utf-8"))
    assert episode["lineage"]["accepted_submission_id"] == "submission_002"


def test_scripted_user_input_and_context_exhaustion_are_typed(tmp_path):
    outcome = _orchestrator(tmp_path / "user").run(lambda state: AgentAction(
        action="ask_user", questions=({"field": "diameter", "question": "Specify diameter", "reason": "Missing interface"},),
    ))
    assert outcome.stop_reason == StopReason.USER_INPUT_REQUIRED

    outcome = _orchestrator(tmp_path / "context", budget=EpisodeBudget(max_context_requests=1)).run(
        lambda state: AgentAction(action="request_context", context_key="reviewed_part_handoff")
    )
    assert outcome.stop_reason == StopReason.BUDGET_EXHAUSTED
