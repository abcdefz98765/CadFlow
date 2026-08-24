from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from ai_native_cad.agents import JsonContractAgentAdapter
from ai_native_cad.agents.episode import EpisodeContractError, validate_work_design_proposal
from ai_native_cad.agents.registry import RUNTIME_SKILL_REGISTRY
from ai_native_cad.agents.work_design_contract import (
    work_design_contract_description,
    work_design_fields,
)
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.action_lifecycle import _continue_work_design_async
from ai_native_cad.workflow_console.product_usability import build_agent_first_workflow_projection
from ai_native_cad.workflow_console.routes import dispatch_route
from ai_native_cad.workflow_console.selected_node_inspector_ui import _work_design_recovery
from ai_native_cad.workflow_console.workflow_page_view_model import (
    build_workbench_overview_view_model,
    build_workflow_page_view_model,
)


class SequencedWorkDesignClient:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    @property
    def provider_identity(self) -> dict[str, str]:
        return {"provider": "scripted", "model": "work-design-fixture"}

    def generate_json_contract(self, request: dict) -> dict:
        self.requests.append(request)
        return self.responses.pop(0)


def _proposal(*, part_count: int = 1, reference_component: bool = False) -> dict:
    parts = [
        {
            "key": f"generated_{index}",
            "name": "Camera cradle" if index == 1 else "Extrusion adapter",
            "role": "Hold the camera" if index == 1 else "Attach the cradle to the rail",
            "interfaces": ["M4 fastener interface"],
            "dependencies": [] if index == 1 else ["generated_1"],
        }
        for index in range(1, part_count + 1)
    ]
    return {
        "objective": "Mount a compact camera to a 2020 extrusion.",
        "concept_summary": "Separate camera support from the rail adapter only when both are needed.",
        "generated_parts": parts,
        "reference_components": (
            [{"name": "2020 extrusion", "role": "Existing installation rail", "interfaces": ["M5 T-nut slot"]}]
            if reference_component
            else []
        ),
        "interfaces": (
            [{"from": "generated_1", "to": "generated_2", "description": "M4 bolted interface"}]
            if part_count > 1
            else []
        ),
        "dependencies": [],
        "assumptions": ["Prototype loads only"],
        "unresolved_questions": [],
        "assembly_expected": part_count > 1,
        "recommendation": "Create the generated Parts and retain existing hardware as references.",
    }


def test_canonical_work_design_sample_normalizes_without_contract_drift() -> None:
    proposal = _proposal(part_count=2, reference_component=True)

    normalized = validate_work_design_proposal(proposal)
    disclosure = work_design_contract_description()

    assert set(proposal) == set(work_design_fields())
    assert set(normalized) - {"schema_version"} == set(work_design_fields())
    assert set(disclosure["fields"]) == set(work_design_fields())
    assert set(disclosure["fields"]["generated_parts"]["items"]["fields"]) == set(
        work_design_fields("generated_parts[]")
    )
    assert set(disclosure["fields"]["reference_components"]["items"]["fields"]) == set(
        work_design_fields("reference_components[]")
    )
    assert set(disclosure["fields"]["interfaces"]["items"]["fields"]) == set(
        work_design_fields("interfaces[]")
    )


def _contract_sample(contract: dict) -> dict:
    return {
        name: _contract_sample_field(field)
        for name, field in contract["fields"].items()
    }


def _contract_sample_field(field: dict):
    if field["type"] == "text":
        return "x"
    if field["type"] == "boolean":
        return False
    if field["type"] == "list":
        return _contract_list_values(field, max(field["min_items"], 1))
    raise AssertionError(f"unsupported canonical test field type: {field['type']}")


def _contract_list_values(field: dict, count: int) -> list:
    items = field["items"]
    if items["type"] == "text":
        return ["x"] * count
    values = [_contract_sample(items) for _ in range(count)]
    unique_by = field.get("unique_by")
    if unique_by is not None:
        for index, item in enumerate(values):
            item[unique_by] = f"key_{index}"
    return values


def _contract_boundary_cases(
    contract: dict,
    *,
    value_path: tuple = (),
    field_prefix: str = "",
):
    for name, field in contract["fields"].items():
        path = value_path + (name,)
        field_path = f"{field_prefix}.{name}" if field_prefix else name
        yield path, field_path, field
        if field["type"] != "list":
            continue
        items = field["items"]
        item_path = path + (0,)
        item_field_path = f"{field_path}[]"
        if items["type"] == "object":
            yield from _contract_boundary_cases(
                items,
                value_path=item_path,
                field_prefix=item_field_path,
            )
        elif items["type"] == "text":
            yield item_path, item_field_path, items


def _set_contract_value(value: dict, path: tuple, replacement) -> None:
    target = value
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = replacement


_CANONICAL_DESCRIPTION = work_design_contract_description()
_CANONICAL_BOUNDARY_CASES = tuple(
    _contract_boundary_cases(_CANONICAL_DESCRIPTION)
)


@pytest.mark.parametrize(
    ("value_path", "field_path", "field"),
    [case for case in _CANONICAL_BOUNDARY_CASES if case[2]["type"] == "text"],
)
def test_all_canonical_text_bounds_drive_validator(
    value_path,
    field_path,
    field,
) -> None:
    exact = _contract_sample(_CANONICAL_DESCRIPTION)
    _set_contract_value(exact, value_path, "x" * field["max_length"])
    validate_work_design_proposal(exact)

    too_long = _contract_sample(_CANONICAL_DESCRIPTION)
    _set_contract_value(too_long, value_path, "x" * (field["max_length"] + 1))
    with pytest.raises(EpisodeContractError) as caught:
        validate_work_design_proposal(too_long)
    assert caught.value.failure_diagnostic["field_issue"] == "invalid_value"
    assert caught.value.failure_diagnostic["field_path"] == field_path


@pytest.mark.parametrize(
    ("value_path", "field_path", "field"),
    [case for case in _CANONICAL_BOUNDARY_CASES if case[2]["type"] == "list"],
)
def test_all_canonical_list_bounds_drive_validator(
    value_path,
    field_path,
    field,
) -> None:
    at_minimum = _contract_sample(_CANONICAL_DESCRIPTION)
    _set_contract_value(
        at_minimum,
        value_path,
        _contract_list_values(field, field["min_items"]),
    )
    validate_work_design_proposal(at_minimum)

    at_maximum = _contract_sample(_CANONICAL_DESCRIPTION)
    _set_contract_value(
        at_maximum,
        value_path,
        _contract_list_values(field, field["max_items"]),
    )
    validate_work_design_proposal(at_maximum)

    above_maximum = _contract_sample(_CANONICAL_DESCRIPTION)
    _set_contract_value(
        above_maximum,
        value_path,
        _contract_list_values(field, field["max_items"] + 1),
    )
    with pytest.raises(EpisodeContractError) as caught:
        validate_work_design_proposal(above_maximum)
    assert caught.value.failure_diagnostic["field_issue"] == "invalid_value"
    assert caught.value.failure_diagnostic["field_path"] == field_path


@pytest.mark.parametrize(
    ("value_path", "field_path", "field"),
    [case for case in _CANONICAL_BOUNDARY_CASES if case[2]["type"] == "boolean"],
)
def test_all_canonical_boolean_types_drive_validator(
    value_path,
    field_path,
    field,
) -> None:
    for valid_value in (False, True):
        valid = _contract_sample(_CANONICAL_DESCRIPTION)
        _set_contract_value(valid, value_path, valid_value)
        validate_work_design_proposal(valid)

    invalid = _contract_sample(_CANONICAL_DESCRIPTION)
    _set_contract_value(invalid, value_path, "false")
    with pytest.raises(EpisodeContractError) as caught:
        validate_work_design_proposal(invalid)
    assert caught.value.failure_diagnostic["field_issue"] == "invalid_type"
    assert caught.value.failure_diagnostic["field_path"] == field_path


@pytest.mark.parametrize(
    ("value_path", "field_path", "field"),
    [case for case in _CANONICAL_BOUNDARY_CASES if case[2].get("unique_by")],
)
def test_all_canonical_unique_keys_drive_validator(
    value_path,
    field_path,
    field,
) -> None:
    invalid = _contract_sample(_CANONICAL_DESCRIPTION)
    duplicates = _contract_list_values(field, 2)
    duplicates[1][field["unique_by"]] = duplicates[0][field["unique_by"]]
    _set_contract_value(invalid, value_path, duplicates)

    with pytest.raises(EpisodeContractError) as caught:
        validate_work_design_proposal(invalid)
    assert caught.value.failure_diagnostic["field_issue"] == "invalid_value"
    assert caught.value.failure_diagnostic["field_path"] == (
        f"{field_path}[].{field['unique_by']}"
    )


def _backend(tmp_path: Path, responses: list[dict]) -> tuple[WorkflowConsoleBackend, SequencedWorkDesignClient]:
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    client = SequencedWorkDesignClient(responses)
    backend.stage_runner.agent_adapter = JsonContractAgentAdapter(
        client, provider="scripted", model="work-design-fixture"
    )
    created = backend.create_product_design(
        "Mount a compact camera to a 2020 extrusion with replaceable adapters.",
        title="Camera Mount",
    )
    assert created["part_job_id"] is None
    return backend, client


@pytest.mark.parametrize("part_count", [1, 2])
def test_normal_entry_runs_real_work_design_before_cad_parts(tmp_path: Path, part_count: int) -> None:
    backend, client = _backend(
        tmp_path,
        [
            {"action": "request_context", "context_key": "work_request"},
            {"action": "propose_work_design", "work_design": _proposal(part_count=part_count), "summary": "Work proposal"},
            {"action": "create_part_jobs"},
        ],
    )
    work_id = backend.list_works(limit=10, offset=0)["works"][0]["work_id"]
    before = backend._read_work_manifest(work_id)
    assert before["part_jobs"] == []

    response = dispatch_route(
        backend,
        "run_work_design_episode",
        path_params={"work_id": work_id},
        body={"request_id": "work_design_001"},
    )

    assert response["ok"] is True
    result = response["data"]
    assert result["episode"]["status"] == "completed"
    assert len(result["part_jobs"]) == part_count
    manifest = backend._read_work_manifest(work_id)
    assert manifest["work_design"]["status"] == "completed"
    assert len(manifest["part_jobs"]) == part_count
    assert all(item["source"] == "work_design" for item in manifest["part_jobs"])
    assert all(item["part_job_id"] != f"generated_{index}" for index, item in enumerate(manifest["part_jobs"], start=1))
    assert manifest["accepted_part_results"] == {}
    assert manifest["assembly_job"] is None
    assert client.requests[0]["operation"] == "work_design_action"
    assert client.requests[0]["skill"]["skill_id"] == "work_design"


def test_contract_repair_exhaustion_routes_through_work_orchestrator(tmp_path: Path) -> None:
    invalid = {"action": "request_context", "parameters": {}}
    backend, client = _backend(tmp_path, [invalid, invalid, invalid])
    work_id = backend.list_works(limit=10, offset=0)["works"][0]["work_id"]

    result = backend.run_work_design_episode(work_id, request_id="repair_exhausted")

    diagnostic = result["episode"]["failure_diagnostic"]
    assert result["episode"]["status"] == "safely_blocked"
    assert diagnostic["contract_repair_exhausted"] is True
    assert diagnostic["contract_repair_turn_count"] == 2
    assert diagnostic["requested_capability_or_context"] == "parameters"
    assert len(client.requests) == 3
    manifest = backend._read_work_manifest(work_id)
    assert manifest["part_jobs"] == []
    assert manifest["work_design"]["status"] == "blocked"


def test_unsafe_extra_field_is_redacted_from_durable_work_design_failure(
    tmp_path: Path,
) -> None:
    unsafe_key = "api_key"
    raw_marker = "RAW_UNSAFE_FIELD_VALUE_MUST_NOT_PERSIST"
    invalid = _proposal()
    invalid[unsafe_key] = raw_marker
    backend, client = _backend(
        tmp_path,
        [{"action": "propose_work_design", "work_design": invalid}],
    )
    work_id = backend.list_works(limit=10, offset=0)["works"][0]["work_id"]

    result = backend.run_work_design_episode(
        work_id,
        request_id="unsafe_extra_field",
    )

    diagnostic = result["episode"]["failure_diagnostic"]
    assert result["episode"]["status"] == "safely_blocked"
    assert diagnostic["field_issue"] == "extra"
    assert diagnostic["field_path"] == "work_design"
    assert diagnostic["requested_capability_or_context"] is None
    assert unsafe_key not in json.dumps(diagnostic)
    assert raw_marker not in json.dumps(diagnostic)
    assert len(client.requests) == 1
    manifest = backend._read_work_manifest(work_id)
    episode_dir = (
        backend._work_runs_root(work_id)
        / manifest["work_design"]["run_id"]
        / "episodes"
        / "work_design"
        / "unsafe_extra_field"
    )
    persisted_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in episode_dir.rglob("*")
        if path.is_file()
    )
    assert (episode_dir / "product_route_result.json").exists()
    assert unsafe_key not in persisted_text
    assert raw_marker not in persisted_text
    assert "action_contract_feedback" not in persisted_text


def test_reference_components_are_not_generated_part_jobs(tmp_path: Path) -> None:
    backend, _ = _backend(
        tmp_path,
        [
            {"action": "propose_work_design", "work_design": _proposal(part_count=2, reference_component=True)},
            {"action": "create_part_jobs"},
        ],
    )
    work_id = backend.list_works(limit=10, offset=0)["works"][0]["work_id"]
    backend.run_work_design_episode(work_id, request_id="reference_case")
    manifest = backend._read_work_manifest(work_id)
    assert len(manifest["part_jobs"]) == 2
    assert manifest["work_design"]["current_design"]["reference_components"][0]["name"] == "2020 extrusion"
    assert all(item["part_job_id"] != "2020_extrusion" for item in manifest["part_jobs"])


def test_ambiguity_pauses_at_work_scope_and_resumes_without_fabricated_part(tmp_path: Path) -> None:
    backend, client = _backend(
        tmp_path,
        [{
            "action": "ask_user",
            "questions": [{"field": "camera_model", "question": "Which camera model must fit?", "reason": "Envelope controls the cradle."}],
            "reason": "A reference envelope is required.",
        }],
    )
    work_id = backend.list_works(limit=10, offset=0)["works"][0]["work_id"]
    first = backend.run_work_design_episode(work_id, request_id="clarify_001")
    assert first["episode"]["stop_reason"] == "user_input_required"
    manifest = backend._read_work_manifest(work_id)
    assert manifest["part_jobs"] == []
    question = next(item for item in manifest["artifact_references"] if item["checkpoint"] == "clarification_decision")
    assert question["part_job_id"] is None

    backend.answer_work_design_question(
        work_id,
        run_id=manifest["work_design"]["run_id"],
        answer_id="camera_answer",
        question_artifact_id=question["artifact_id"],
        field="camera_model",
        question="Which camera model must fit?",
        answer="Raspberry Pi Camera Module 3",
    )
    client.responses.extend([
        {"action": "request_context", "context_key": "work_clarification_answers"},
        {"action": "propose_work_design", "work_design": _proposal()},
        {"action": "create_part_jobs"},
    ])
    resumed = backend.run_work_design_episode(work_id, request_id="clarify_002")
    assert resumed["episode"]["status"] == "completed"
    assert len(backend._read_work_manifest(work_id)["part_jobs"]) == 1


@pytest.mark.parametrize("reason", ["unsupported_capability", "insufficient_context"])
def test_honest_stop_preserves_empty_part_scope(tmp_path: Path, reason: str) -> None:
    backend, _ = _backend(
        tmp_path,
        [{"action": "stop", "stop_reason": reason, "reason": "The request cannot be responsibly decomposed."}],
    )
    work_id = backend.list_works(limit=10, offset=0)["works"][0]["work_id"]
    result = backend.run_work_design_episode(work_id, request_id=f"stop_{reason}")
    assert result["episode"]["status"] == "safely_blocked"
    assert backend._read_work_manifest(work_id)["part_jobs"] == []


def test_local_work_design_rejection_reaches_selected_design_recovery_without_cad(
    tmp_path: Path,
) -> None:
    backend, _ = _backend(
        tmp_path,
        [
            {"action": "create_contract"},
            {"action": "stop", "stop_reason": "insufficient_context", "reason": "Need a dimension."},
        ],
    )
    work_id = backend.list_works(limit=10, offset=0)["works"][0]["work_id"]

    result = backend.run_work_design_episode(work_id, request_id="local_rejection")
    assert result["episode"]["stop_reason"] == "policy_blocked"
    assert result["episode"]["failure_diagnostic"]["rejected_action"] == "create_contract"
    assert backend._read_work_manifest(work_id)["part_jobs"] == []

    page = build_workflow_page_view_model(
        backend, work_id, selected_stage_id="work:design", language="en"
    )
    selected = page["selected_node"]
    assert selected["id"] == "work:design"
    recovery = selected["detail"]["recovery"]
    assert recovery["rejected_action"] == "create_contract"
    assert recovery["technical_reason"] == "invalid_action_payload"
    assert recovery["resolution_owner"] == "agent"
    assert recovery["code_executed"] is False
    assert recovery["geometry_generated"] is False
    assert recovery["result_published"] is False
    assert recovery["retryable"] is True
    assert recovery["next_action"] == "Retry Work Design"
    assert recovery["recommended_action"]["label"] == "Retry Work Design"
    assert recovery["recommended_action"]["key"] == "start_new_attempt"
    assert "same Work Design Run" in recovery["retry_reason"]
    primary = selected["interaction"]["primary_action"]
    assert primary["key"] == "continue_work_design"
    assert primary["label"] == recovery["recommended_action"]["label"]
    assert primary["target_work_id"] == work_id
    assert primary["target_run_id"] == recovery["run_id"]
    before_retry = backend._read_work_manifest(work_id)
    retry_result = asyncio.run(
        _continue_work_design_async(backend, primary, {}, lambda: None, "en")
    )
    after_retry = backend._read_work_manifest(work_id)
    assert retry_result["episode"]["stop_reason"] == "insufficient_context"
    assert after_retry["work_design"]["run_id"] == before_retry["work_design"]["run_id"]
    assert after_retry["run_ids"] == before_retry["run_ids"]
    assert after_retry["part_jobs"] == before_retry["part_jobs"] == []
    assert len(after_retry["artifact_references"]) > len(before_retry["artifact_references"])
    assert _work_design_recovery(selected["detail"]["type"], selected["detail"]) == recovery
    assert _work_design_recovery("decomposition", {"recovery": recovery}) == {}
    assert _work_design_recovery("attempt", {"recovery": recovery}) == {}


def test_agent_reported_work_design_policy_stop_is_distinct_from_local_rejection(
    tmp_path: Path,
) -> None:
    backend, _ = _backend(
        tmp_path,
        [{"action": "stop", "stop_reason": "policy_blocked", "reason": "Agent stopped."}],
    )
    work_id = backend.list_works(limit=10, offset=0)["works"][0]["work_id"]

    backend.run_work_design_episode(work_id, request_id="agent_policy_stop")
    page = build_workflow_page_view_model(
        backend, work_id, selected_stage_id="work:design", language="en"
    )
    recovery = page["selected_node"]["detail"]["recovery"]

    assert recovery["rejected_action"] == "stop"
    assert recovery["technical_reason"] == "agent_reported_policy_block"
    assert recovery["cause_category"] == "agent_reported_policy_block"
    assert recovery["resolution_owner"] == "agent"
    assert recovery["code_executed"] is False
    assert recovery["geometry_generated"] is False
    assert recovery["result_published"] is False
    assert recovery["retryable"] is False
    assert recovery["next_action"] == "Retry Work Design"
    assert recovery["recommended_action"]["label"] == "Retry Work Design"
    primary = page["selected_node"]["interaction"]["primary_action"]
    assert primary["key"] == "continue_work_design"
    assert primary["label"] == recovery["recommended_action"]["label"]
    assert primary["target_work_id"] == work_id
    assert primary["target_run_id"] == recovery["run_id"]


def test_work_design_skill_loads_only_declared_bounded_markdown_knowledge() -> None:
    skill = RUNTIME_SKILL_REGISTRY.skill("work_design")
    knowledge = RUNTIME_SKILL_REGISTRY.knowledge_for_skill("work_design")
    assert skill.operations == ("work_design",)
    assert knowledge
    assert all(item.source.endswith(".md") for item in knowledge)
    assert all(item.load_content().strip() for item in knowledge)
    with pytest.raises(ValueError, match="not declared"):
        RUNTIME_SKILL_REGISTRY.knowledge_for_skill("work_design", "model_program_cadquery_v1")


def test_provider_cannot_assign_identity_or_side_effect_fields() -> None:
    forged = _proposal()
    forged["generated_parts"][0]["part_job_id"] = "provider_owned"
    with pytest.raises(EpisodeContractError, match="fields|identities"):
        validate_work_design_proposal(forged)


def test_overview_and_dynamic_graph_share_work_design_state(tmp_path: Path) -> None:
    backend, _ = _backend(
        tmp_path,
        [
            {"action": "propose_work_design", "work_design": _proposal(part_count=2, reference_component=True)},
            {"action": "create_part_jobs"},
        ],
    )
    work_id = backend.list_works(limit=10, offset=0)["works"][0]["work_id"]
    initial = build_workbench_overview_view_model(backend, work_id)
    assert initial["recommendation"]["key"] == "open_settings"
    assert initial["command_authority"]["work"]["primary_action"]["key"] == "open_settings"
    assert initial["work"]["part_count"] == 0
    backend.run_work_design_episode(work_id, request_id="graph_case")
    overview = build_workbench_overview_view_model(backend, work_id)
    assert overview["user_input"]["original_request"] == (
        "Mount a compact camera to a 2020 extrusion with replaceable adapters."
    )
    assert overview["agent_design"]["evidence_status"] == "persisted_work_design"
    assert overview["capability"]["key"] == "agentic_experimental"
    assert overview["agent_activity"]["key"] == "preparing_candidate"
    work = backend.get_work_detail(work_id)
    graph = build_agent_first_workflow_projection(backend, work_id, work, overview, language="en")
    node_ids = {item["id"] for item in graph["nodes"]}
    assert {"work:request", "work:design"} <= node_ids
    assert "work:decomposition" not in node_ids
    assert graph["workflow_graph"]["work_path_node_ids"] == ["work:design"]
    part_nodes = [item for item in graph["nodes"] if item["kind"] == "part"]
    assert len(part_nodes) == overview["work_design"]["part_job_count"] == 2
    edges = {(item["source"], item["target"]) for item in graph["edges"]}
    assert ("work:request", "work:design") in edges
    assert all(("work:design", item["id"]) in edges for item in part_nodes)


def test_episode_evidence_distinguishes_dynamic_context_from_static_knowledge(tmp_path: Path) -> None:
    backend, _ = _backend(
        tmp_path,
        [
            {"action": "request_context", "context_key": "work_request"},
            {"action": "propose_work_design", "work_design": _proposal()},
            {"action": "create_part_jobs"},
        ],
    )
    work_id = backend.list_works(limit=10, offset=0)["works"][0]["work_id"]
    result = backend.run_work_design_episode(work_id, request_id="evidence_case")
    episode_dir = backend._work_runs_root(work_id) / result["work_design"]["run_id"] / "episodes" / "work_design" / "evidence_case"
    episode = json.loads((episode_dir / "agent_episode.json").read_text(encoding="utf-8"))
    context = json.loads((episode_dir / "context_manifest.json").read_text(encoding="utf-8"))
    assert episode["context_is_work_specific"] is True
    assert episode["knowledge_is_static"] is True
    assert {item["knowledge_id"] for item in episode["knowledge"]}
    assert {item["context_key"] for item in context["items"]} == {"work_request"}
    assert all("source" in item and "sha256" in item for item in episode["knowledge"])
