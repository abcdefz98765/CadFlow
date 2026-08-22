from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from ai_native_cad.agents import JsonContractAgentAdapter
from ai_native_cad.agents.episode import EpisodeContractError, validate_work_design_proposal
from ai_native_cad.agents.registry import RUNTIME_SKILL_REGISTRY
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
    assert recovery["technical_reason"] == "action_not_allowed_for_skill"
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
