import json
from urllib import error

import pytest

import ai_native_cad.agents.episode as episode_module
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
    run_design_part_episode,
    run_work_design_episode,
)
from ai_native_cad.agents.json_contract import (
    JsonContractAgentAdapter,
    JsonContractProviderConfig,
)
from ai_native_cad.agents.provider_clients import (
    JsonProviderEndpoint,
    OpenAICompatibleJsonContractClient,
)
from ai_native_cad.agents.tool_broker import ToolObservation


def _contract():
    return {
        "part_type": "spacer",
        "part_name": "accounting_spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 5, "thickness": 4},
        "features": {},
        "outputs": ["step", "stl"],
        "check_level": "L0",
    }


def _episode(tmp_path, budget):
    objective = AgentObjective("create_part_ir", "Create a CAD IR draft")
    item = ContextItem(
        "reviewed_part_handoff",
        "run_1",
        "reviewed_part_handoff",
        "accepted_active_lineage",
        {"part_id": "part_1"},
        {"part_id": "part_1"},
    )
    envelope = ContextEnvelope(
        objective,
        {"active_leaf_run_id": "run_1"},
        (),
        {"part_id": "part_1"},
        (),
        (),
        ("reviewed_part_handoff",),
    )
    return EpisodeOrchestrator(
        objective,
        envelope,
        ContextBroker([item]),
        AgentCapabilities(),
        budget,
        lambda contract: {"valid": True, "errors": []},
        tmp_path,
    )


def _assert_budget(result, kind):
    assert result.stop_reason == StopReason.BUDGET_EXHAUSTED
    assert result.failure_diagnostic == {
        "reason_code": f"budget_exhausted.{kind}",
        "budget_kind": kind,
        "used": result.failure_diagnostic["used"],
        "limit": result.failure_diagnostic["limit"],
        "agent_steps": result.step_count,
    }


@pytest.mark.parametrize(
    ("budget", "action", "kind"),
    [
        (EpisodeBudget(timeout_seconds=0), None, "wall_clock_seconds"),
        (EpisodeBudget(max_steps=0), None, "agent_steps"),
        (EpisodeBudget(max_context_requests=0), AgentAction("request_context", context_key="reviewed_part_handoff"), "context_requests"),
        (EpisodeBudget(max_context_bytes=0), AgentAction("request_context", context_key="reviewed_part_handoff"), "context_bytes"),
        (EpisodeBudget(max_contract_submissions=0), AgentAction("submit_contract", contract_type="cad_ir_draft", contract=_contract()), "contract_submissions"),
        (EpisodeBudget(max_repair_attempts=0), AgentAction("repair_contract", contract_type="cad_ir_draft", contract=_contract()), "repair_attempts"),
    ],
)
def test_episode_persists_exact_budget_diagnostics(tmp_path, budget, action, kind):
    result = _episode(tmp_path, budget).run(
        (lambda state: action) if action is not None else (lambda state: pytest.fail("supplier must not run"))
    )
    _assert_budget(result, kind)


class _ProgramBroker:
    def manifest(self, *, active_skill_id, delegated_skill_ids=()):
        return {"schema_version": 1, "active_skill_id": active_skill_id, "allowed_tools": []}

    def invoke(self, tool_id, *, skill_id, payload, context=None):
        return ToolObservation(
            tool_id=tool_id,
            success=False,
            observation_type="model_program_execution_failed",
            codes=("test_failure",),
            output={},
            execution_profile="test",
            cad_execution_ms=70,
        )


def _model_program():
    return {
        "api_id": "cadquery_v1",
        "source": "def build_model(parameters):\n    return None\n",
        "parameters": {},
        "requested_outputs": ["step"],
    }


def _program_episode(tmp_path, budget, actions):
    iterator = iter(actions)
    return run_design_part_episode(
        adapter=type("Adapter", (), {"provider_identity": {}, "choose_design_action": lambda self, **kwargs: next(iterator)})(),
        handoff={
            "work_id": "work_1",
            "part_id": "part_1",
            "status": "ready_for_single_part_planning",
            "part_brief": "Accounted test part",
            "interface_constraints": [],
            "preserved_assembly_context": {},
        },
        artifact_dir=tmp_path,
        budget=budget,
        tool_broker=_ProgramBroker(),
        run_id="run_1",
    )


@pytest.mark.parametrize(
    ("budget", "actions", "kind"),
    [
        (EpisodeBudget(max_source_submissions=0), [{"action": "create_model_program", "model_program": _model_program()}], "source_submissions"),
        (EpisodeBudget(max_executions=0), [{"action": "create_model_program", "model_program": _model_program()}, {"action": "request_execution"}], "cad_executions"),
        (EpisodeBudget(max_observation_inspections=0), [{"action": "create_model_program", "model_program": _model_program()}, {"action": "request_execution"}, {"action": "inspect_observation"}], "observation_inspections"),
    ],
)
def test_model_program_budget_diagnostics_cover_each_boundary(tmp_path, budget, actions, kind):
    result = _program_episode(tmp_path, budget, actions)
    _assert_budget(result, kind)


def test_part_episode_rechecks_wall_clock_after_provider_returns(tmp_path, monkeypatch):
    elapsed = iter([0.0, 0.0, 1.0, 1.0])
    monkeypatch.setattr(
        episode_module,
        "_elapsed_seconds",
        lambda started: next(elapsed),
    )

    result = _program_episode(
        tmp_path,
        EpisodeBudget(timeout_seconds=0.5),
        [{"action": "create_model_program", "model_program": _model_program()}],
    )

    assert result.step_count == 1
    _assert_budget(result, "wall_clock_seconds")
    events = [json.loads(line) for line in (tmp_path / "agent_events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(event.get("boundary") == "post_provider_return" for event in events)


def test_contract_repair_turn_budget_is_a_budget_exhaustion(tmp_path):
    result = _episode(tmp_path, EpisodeBudget(max_contract_repair_turns=0)).run(
        lambda state: {"action": "request_context", "context_key": "reviewed_part_handoff", "extra": "ignored"}
    )
    _assert_budget(result, "contract_repair_turns")


def test_two_replies_protocol_repair_then_wall_timeout_is_durable(tmp_path, monkeypatch):
    answers = iter([
        {"action": "request_context", "context_key": "work_request", "extra": "repairable"},
        {"action": "request_context", "context_key": "work_request"},
    ])
    adapter = type(
        "Adapter",
        (),
        {"provider_identity": {}, "choose_design_action": lambda self, **kwargs: next(answers)},
    )()
    elapsed = iter([0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0])
    monkeypatch.setattr(episode_module, "_elapsed_seconds", lambda started: next(elapsed))

    result = run_work_design_episode(
        adapter=adapter,
        work_context={"work_id": "work_1", "title": "Test", "description": "Design a test part"},
        artifact_dir=tmp_path,
        run_id="run_1",
        budget=EpisodeBudget(timeout_seconds=0.5, max_contract_repair_turns=1),
    )

    assert result.step_count == 2
    assert result.contract_repair_turn_count == 1
    _assert_budget(result, "wall_clock_seconds")


def test_provider_and_tool_timing_are_durable_and_cad_is_a_tool_subset(tmp_path, monkeypatch):
    elapsed_ms = iter([40, 50, 20, 120])
    monkeypatch.setattr(episode_module, "_elapsed_ms", lambda started: next(elapsed_ms))
    result = _program_episode(
        tmp_path,
        EpisodeBudget(max_steps=2),
        [
            {"action": "create_model_program", "model_program": _model_program()},
            {"action": "request_execution"},
        ],
    )

    assert result.provider_ms == 90
    assert result.tool_ms == 20
    assert result.cad_execution_ms == 20
    assert result.cad_execution_ms <= result.tool_ms
    assert result.elapsed_total_ms == 120
    assert result.provider_logical_request_count == 2
    assert result.provider_transport_attempt_count is None


def test_budget_evidence_redacts_model_source_and_secret_like_text(tmp_path):
    source_marker = "RAW_MODEL_SOURCE_MUST_NOT_PERSIST"
    secret_marker = "sk-accounting-must-not-persist"
    program = {
        **_model_program(),
        "source": f"# {source_marker} {secret_marker}\ndef build_model(parameters):\n    return None\n",
    }

    result = _program_episode(
        tmp_path,
        EpisodeBudget(max_source_submissions=0),
        [{"action": "create_model_program", "model_program": program}],
    )

    _assert_budget(result, "source_submissions")
    evidence = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.rglob("*") if path.is_file())
    assert source_marker not in evidence
    assert secret_marker not in evidence


class _HTTPResponse:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._body


def test_http_transport_retries_are_accounted_without_secret_or_source_retention(tmp_path):
    attempts = []

    def urlopen(http_request, timeout):
        attempts.append(http_request)
        if len(attempts) < 3:
            raise error.URLError("retryable transport failure")
        return _HTTPResponse(json.dumps({
            "choices": [{"message": {"content": json.dumps({
                "action": "stop", "stop_reason": "insufficient_context"
            })}}]
        }).encode("utf-8"))

    client = OpenAICompatibleJsonContractClient(
        JsonProviderEndpoint(
            provider="test",
            model="test-model",
            api_key_env_var="TEST_API_KEY",
            base_url="https://transport-secret.invalid",
            endpoint="/v1/chat/completions",
            api_shape="chat_completions",
            max_retries=2,
        ),
        urlopen=urlopen,
        api_key="api-secret-value",
    )
    adapter = JsonContractAgentAdapter(
        client,
        config=JsonContractProviderConfig(
            provider="test", model="test-model", enabled=True, max_retries=2
        ),
    )

    result = run_design_part_episode(
        adapter=adapter,
        handoff={"work_id": "work_1", "part_id": "part_1", "status": "ready", "part_brief": "Never retain source", "interface_constraints": [], "preserved_assembly_context": {}},
        artifact_dir=tmp_path,
        run_id="run_1",
    )

    assert result.step_count == 1
    assert result.provider_logical_request_count == 1
    assert result.provider_transport_attempt_count == 3
    evidence = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.rglob("*") if path.is_file())
    assert "api-secret-value" not in evidence
    assert "transport-secret.invalid" not in evidence
    assert "Never retain source" not in evidence
