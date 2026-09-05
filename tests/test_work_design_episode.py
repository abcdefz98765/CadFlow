from __future__ import annotations

import json
import threading
from copy import deepcopy

import pytest

from ai_native_cad.agents import JsonContractAgentAdapter
from ai_native_cad.domain.records import create_artifact_reference
from ai_native_cad.orchestration import (
    DesignEpisodeArtifact,
    DesignPartEpisodeOutcome,
    WorkOrchestrator,
)
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.orchestrator_adapters import (
    WorkflowConsoleDeterministicCompatibility,
    WorkflowConsoleWorkStore,
)
from ai_native_cad.workflow_console.routes import dispatch_route


class SequencedDesignClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    @property
    def provider_identity(self):
        return {"provider": "scripted-product-design", "model": "fixture"}

    def generate_json_contract(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


class ForgedDesignPort:
    def __init__(self, *, request_id: str, relative_path: str) -> None:
        self.request_id = request_id
        self.relative_path = relative_path

    def run_part_design_episode(self, request):
        return DesignPartEpisodeOutcome(
            request_id=self.request_id,
            episode_id="forged_episode",
            status="safely_blocked",
            stop_reason="policy_blocked",
            capability_mode="test_forged_port",
            validated=False,
            artifacts=(
                DesignEpisodeArtifact(
                    artifact_id="episode:forged_episode:route",
                    relative_path=self.relative_path,
                    checkpoint="product_design_routing",
                    trust_role="diagnostic",
                    validation_status="blocked",
                ),
            ),
        )


class ConcurrentDesignPort:
    """Controlled Design port used to prove provider work happens outside commits."""

    def __init__(self, outcomes: dict[str, DesignPartEpisodeOutcome]) -> None:
        self.outcomes = outcomes
        self.started = threading.Event()
        self.releases = {
            request_id: threading.Event() for request_id in outcomes
        }
        self._lock = threading.Lock()
        self.requests = []

    def run_part_design_episode(self, request):
        with self._lock:
            self.requests.append(request)
            if len(self.requests) == len(self.outcomes):
                self.started.set()
        if not self.releases[request.request_id].wait(timeout=5):
            raise RuntimeError("test Design port was not released")
        return self.outcomes[request.request_id]


def _episode_outcome(
    request_id: str,
    *,
    stop_reason: str,
    validated: bool,
) -> DesignPartEpisodeOutcome:
    status = "completed" if validated else "safely_blocked"
    return DesignPartEpisodeOutcome(
        request_id=request_id,
        episode_id=f"episode_{request_id}",
        status=status,
        stop_reason=stop_reason,
        capability_mode="concurrency_fixture",
        validated=validated,
        artifacts=(
            DesignEpisodeArtifact(
                artifact_id=f"episode:{request_id}:route",
                relative_path=(
                    f"episodes/design_part/{request_id}/product_route_result.json"
                ),
                checkpoint="product_design_routing",
                trust_role="candidate" if validated else "diagnostic",
                validation_status="passed" if validated else stop_reason,
            ),
        ),
    )


def _valid_contract() -> dict:
    return {
        "part_type": "simple_bracket",
        "part_name": "product_routed_clamp",
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


def _provider_adapter() -> tuple[JsonContractAgentAdapter, SequencedDesignClient]:
    client = SequencedDesignClient(
        [
            {"action": "request_context", "context_key": "part_job"},
            {
                "action": "create_contract",
                "contract_type": "cad_ir_draft",
                "contract": _valid_contract(),
                "summary": "Create a compact clamp bracket candidate.",
            },
            {"action": "request_validation"},
        ]
    )
    return (
        JsonContractAgentAdapter(
            client,
            provider="scripted",
            model="fixture",
        ),
        client,
    )


def _prepared_backend(tmp_path) -> WorkflowConsoleBackend:
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work(
        "Clamp",
        description="Design a compact printable clamp jaw.",
        work_id="clamp_work",
    )
    backend.create_work_part_attempt(
        "clamp_work",
        "clamp",
        role="moving jaw",
        run_id="clamp_attempt_1",
    )
    return backend


def test_work_orchestrator_routes_validation_only_episode_without_trust_mutation(
    tmp_path,
) -> None:
    backend = _prepared_backend(tmp_path)
    adapter, client = _provider_adapter()
    backend.stage_runner.agent_adapter = adapter
    manifest_before = backend._read_work_manifest("clamp_work")
    protected_before = deepcopy(
        {
            "active_lineage": manifest_before["active_lineage"],
            "accepted_part_results": manifest_before["accepted_part_results"],
            "part_jobs": manifest_before["part_jobs"],
            "deliverable_packages": manifest_before["deliverable_packages"],
        }
    )
    run_dir = (
        backend._work_runs_root("clamp_work") / "clamp_attempt_1"
    )
    prompt_before = (run_dir / "prompt.txt").read_bytes()

    response = dispatch_route(
        backend,
        "run_work_part_design_episode",
        path_params={"work_id": "clamp_work", "part_job_id": "clamp"},
        body={"request_id": "design_request_001"},
    )

    assert response["ok"] is True
    data = response["data"]
    assert data["episode"]["validated"] is True
    assert data["episode"]["idempotent_replay"] is False
    assert data["orchestration"] == {
        "orchestrator": "work_orchestrator",
        "status": "completed",
        "command": "run_part_design_episode",
        "phase": "design",
        "checkpoint": "contract_validation",
        "postcondition": (
            "A validated contract candidate for clamp was appended to Run "
            "clamp_attempt_1; no acceptance mutation occurred."
        ),
        "next_action": "Review the validated contract candidate",
    }
    assert len(client.requests) == 3
    assert {item["trust_role"] for item in data["artifact_references"]} == {
        "candidate",
        "observation",
    }
    assert data["product_state"]["accepted_artifacts"] == []
    assert data["product_state"]["deliverable_artifacts"] == []

    manifest_after = backend._read_work_manifest("clamp_work")
    protected_after = {
        "active_lineage": manifest_after["active_lineage"],
        "accepted_part_results": manifest_after["accepted_part_results"],
        "part_jobs": manifest_after["part_jobs"],
        "deliverable_packages": manifest_after["deliverable_packages"],
    }
    assert protected_after == protected_before
    assert len(manifest_after["artifact_references"]) == 6
    assert {item["checkpoint"] for item in manifest_after["artifact_references"]} >= {
        "agent_output",
        "agent_activity",
        "contract_validation",
        "product_design_routing",
    }
    assert (run_dir / "prompt.txt").read_bytes() == prompt_before
    assert not any(
        (run_dir / name).exists()
        for name in ("model.py", "model.step", "model.stl", "preview.png")
    )

    episode_dir = run_dir / "episodes" / "design_part" / "design_request_001"
    route_result = json.loads(
        (episode_dir / "product_route_result.json").read_text(encoding="utf-8")
    )
    agent_episode = json.loads(
        (episode_dir / "agent_episode.json").read_text(encoding="utf-8")
    )
    assert route_result["authority"] == {
        "orchestrator": "work_orchestrator",
        "execution_enabled": False,
        "publication_enabled": False,
        "acceptance_mutation_enabled": False,
    }
    assert agent_episode["lineage"]["run_id"] == "clamp_attempt_1"
    assert agent_episode["lineage"]["work_id"] == "clamp_work"
    assert agent_episode["lineage"]["part_id"] == "clamp"


def test_design_episode_request_is_idempotent_without_second_provider_call(
    tmp_path,
) -> None:
    backend = _prepared_backend(tmp_path)
    adapter, client = _provider_adapter()
    backend.stage_runner.agent_adapter = adapter

    first = backend.run_work_part_design_episode(
        "clamp_work",
        "clamp",
        request_id="design_request_001",
    )
    manifest_path = backend._work_manifest_path("clamp_work")
    manifest_after_first = manifest_path.read_bytes()
    second = backend.run_work_part_design_episode(
        "clamp_work",
        "clamp",
        request_id="design_request_001",
    )

    assert first["episode"]["idempotent_replay"] is False
    assert second["episode"]["idempotent_replay"] is True
    assert first["episode"]["episode_id"] == second["episode"]["episode_id"]
    assert len(client.requests) == 3
    assert manifest_path.read_bytes() == manifest_after_first
    episodes = list(
        (
            backend._work_runs_root("clamp_work")
            / "clamp_attempt_1"
            / "episodes"
            / "design_part"
        ).iterdir()
    )
    assert [item.name for item in episodes] == ["design_request_001"]


def test_request_id_cannot_be_reused_for_different_design_content(tmp_path) -> None:
    backend = _prepared_backend(tmp_path)
    adapter, _ = _provider_adapter()
    backend.stage_runner.agent_adapter = adapter
    backend.run_work_part_design_episode(
        "clamp_work",
        "clamp",
        request_id="design_request_001",
    )

    with pytest.raises(ValueError, match="already bound"):
        backend.run_work_part_design_episode(
            "clamp_work",
            "clamp",
            request_id="design_request_001",
            objective="A different objective must not reuse the request id.",
        )


def test_design_episode_rejects_unowned_attempt_before_provider_or_evidence(
    tmp_path,
) -> None:
    backend = _prepared_backend(tmp_path)
    backend.create_work_part_attempt(
        "clamp_work",
        "base",
        run_id="base_attempt_1",
    )
    adapter, client = _provider_adapter()
    backend.stage_runner.agent_adapter = adapter

    with pytest.raises(ValueError, match="owned Part Job attempt"):
        backend.run_work_part_design_episode(
            "clamp_work",
            "clamp",
            request_id="wrong_attempt_request",
            attempt_run_id="base_attempt_1",
        )

    assert client.requests == []
    assert not (
        backend._work_runs_root("clamp_work")
        / "base_attempt_1"
        / "episodes"
    ).exists()


def test_local_adapter_safely_blocks_without_cad_or_acceptance(tmp_path) -> None:
    backend = _prepared_backend(tmp_path)
    before = backend._read_work_manifest("clamp_work")

    result = backend.run_work_part_design_episode(
        "clamp_work",
        "clamp",
        request_id="local_adapter_request",
    )

    after = backend._read_work_manifest("clamp_work")
    assert result["episode"]["validated"] is False
    assert result["episode"]["stop_reason"] == "unsupported_capability"
    assert result["orchestration"]["status"] == "blocked"
    assert len(result["artifact_references"]) == 1
    assert result["artifact_references"][0]["trust_role"] == "diagnostic"
    assert after["accepted_part_results"] == before["accepted_part_results"]
    assert after["active_lineage"] == before["active_lineage"]
    run_dir = backend._work_runs_root("clamp_work") / "clamp_attempt_1"
    assert not any(run_dir.rglob("model.step"))
    assert not any(run_dir.rglob("model.py"))


def test_provider_execution_field_is_product_routed_to_policy_block(tmp_path) -> None:
    backend = _prepared_backend(tmp_path)
    forbidden_source = "open('../escape.txt', 'w').write('bad')"
    client = SequencedDesignClient(
        [
            {
                "action": "create_contract",
                "contract_type": "cad_ir_draft",
                "contract": {
                    **_valid_contract(),
                    "python_code": forbidden_source,
                },
            }
        ]
    )
    backend.stage_runner.agent_adapter = JsonContractAgentAdapter(
        client,
        provider="scripted",
        model="fixture",
    )

    result = backend.run_work_part_design_episode(
        "clamp_work",
        "clamp",
        request_id="policy_block_request",
    )

    assert result["episode"]["stop_reason"] == "policy_blocked"
    assert result["episode"]["validated"] is False
    diagnostic = result["episode"]["failure_diagnostic"]
    assert diagnostic == {
        "schema_version": 1,
        "rejection_stage": "action_contract_validation",
        "rejected_action": "create_contract",
        "reason_code": "structured_contract_execution_field",
        "requested_capability_or_context": "python_code",
        "human_safe_detail": (
            "The Agent placed an executable-source field inside a structured geometry action."
        ),
        "side_effect_started": False,
    }
    assert result["artifact_references"][0]["trust_role"] == "diagnostic"
    episode_dir = (
        backend._work_runs_root("clamp_work")
        / "clamp_attempt_1"
        / "episodes"
        / "design_part"
        / "policy_block_request"
    )
    persisted = "".join(
        path.read_text(encoding="utf-8")
        for path in episode_dir.rglob("*")
        if path.is_file()
    )
    assert forbidden_source not in persisted
    assert (episode_dir / "failure_diagnostic.json").is_file()
    assert not any(episode_dir.rglob("model.py"))


def test_idempotent_replay_revalidates_cached_artifact_contract(tmp_path) -> None:
    backend = _prepared_backend(tmp_path)
    adapter, _ = _provider_adapter()
    backend.stage_runner.agent_adapter = adapter
    backend.run_work_part_design_episode(
        "clamp_work",
        "clamp",
        request_id="tamper_check_request",
    )
    route_result_path = (
        backend._work_runs_root("clamp_work")
        / "clamp_attempt_1"
        / "episodes"
        / "design_part"
        / "tamper_check_request"
        / "product_route_result.json"
    )
    route_result = json.loads(route_result_path.read_text(encoding="utf-8"))
    route_result["episode"]["artifacts"][0]["relative_path"] = "../escape.json"
    route_result_path.write_text(
        json.dumps(route_result) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="controlled and relative"):
        backend.run_work_part_design_episode(
            "clamp_work",
            "clamp",
            request_id="tamper_check_request",
        )


@pytest.mark.parametrize(
    ("returned_request_id", "relative_path", "message"),
    [
        (
            "different_request",
            "episodes/design_part/port_boundary_request/product_route_result.json",
            "mismatched request id",
        ),
        (
            "port_boundary_request",
            "episodes/design_part/another_request/product_route_result.json",
            "request directory",
        ),
    ],
)
def test_work_orchestrator_rejects_forged_design_port_identity(
    tmp_path,
    returned_request_id,
    relative_path,
    message,
) -> None:
    backend = _prepared_backend(tmp_path)
    manifest_before = backend._work_manifest_path("clamp_work").read_bytes()
    orchestrator = WorkOrchestrator(
        WorkflowConsoleWorkStore(backend),
        WorkflowConsoleDeterministicCompatibility(backend),
        ForgedDesignPort(
            request_id=returned_request_id,
            relative_path=relative_path,
        ),
    )

    with pytest.raises(RuntimeError, match=message):
        orchestrator.run_part_design_episode(
            "clamp_work",
            "clamp",
            request_id="port_boundary_request",
        )

    assert backend._work_manifest_path("clamp_work").read_bytes() == manifest_before


def _concurrent_orchestrator(tmp_path, port):
    backend = _prepared_backend(tmp_path)
    backend.create_work_part_attempt(
        "clamp_work",
        "base",
        run_id="base_attempt_1",
    )
    orchestrator = WorkOrchestrator(
        WorkflowConsoleWorkStore(backend),
        WorkflowConsoleDeterministicCompatibility(backend),
        port,
    )
    accepted = orchestrator.accept_part_result(
        "clamp_work",
        part_job_id="base",
        result_id="part_result:base:accepted",
        attempt_run_id="base_attempt_1",
        result_run_id="base_attempt_1",
        review_id="review_base_001",
        artifact_references=[
            create_artifact_reference(
                artifact_id="artifact:base:accepted",
                work_id="clamp_work",
                run_id="base_attempt_1",
                part_job_id="base",
                relative_path="accepted_model.step",
                phase="build_evaluate",
                checkpoint="reviewable_result",
                trust_role="reviewable_result",
                validation_status="passed",
            )
        ],
    )
    return backend, orchestrator, deepcopy(accepted["accepted_part_result"])


@pytest.mark.parametrize(
    ("first_request", "second_request"),
    [("budget_request", "success_request"), ("success_request", "budget_request")],
)
def test_concurrent_part_design_commits_keep_sibling_evidence_and_acceptance(
    tmp_path,
    first_request,
    second_request,
) -> None:
    port = ConcurrentDesignPort(
        {
            "success_request": _episode_outcome(
                "success_request",
                stop_reason="completed",
                validated=True,
            ),
            "budget_request": _episode_outcome(
                "budget_request",
                stop_reason="budget_exhausted",
                validated=False,
            ),
        }
    )
    backend, orchestrator, accepted_before = _concurrent_orchestrator(tmp_path, port)
    results = {}
    errors = []

    def run_episode(request_id, part_job_id):
        try:
            results[request_id] = orchestrator.run_part_design_episode(
                "clamp_work",
                part_job_id,
                request_id=request_id,
            )
        except BaseException as error:  # pragma: no cover - test assertion below
            errors.append(error)

    threads = {
        "success_request": threading.Thread(
            target=run_episode,
            args=("success_request", "clamp"),
        ),
        "budget_request": threading.Thread(
            target=run_episode,
            args=("budget_request", "base"),
        ),
    }
    for thread in threads.values():
        thread.start()
    assert port.started.wait(timeout=5)

    port.releases[first_request].set()
    threads[first_request].join(timeout=5)
    assert not threads[first_request].is_alive()
    port.releases[second_request].set()
    for thread in threads.values():
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert errors == []
    assert results["success_request"]["orchestration"]["status"] == "completed"
    assert results["budget_request"]["orchestration"]["status"] == "blocked"
    manifest = backend._read_work_manifest("clamp_work")
    assert manifest["accepted_part_results"]["base"] == accepted_before
    assert {
        item["artifact_id"]
        for item in manifest["artifact_references"]
        if item["artifact_id"] in {
            "episode:success_request:route",
            "episode:budget_request:route",
        }
    } == {
        "episode:success_request:route",
        "episode:budget_request:route",
    }


def test_acceptance_and_sibling_episode_merge_share_one_work_commit_guard(
    tmp_path,
    monkeypatch,
) -> None:
    port = ConcurrentDesignPort({
        "success_request": _episode_outcome(
            "success_request",
            stop_reason="completed",
            validated=True,
        ),
    })
    backend, orchestrator, _accepted_before = _concurrent_orchestrator(tmp_path, port)
    acceptance_at_write = threading.Event()
    release_acceptance = threading.Event()
    episode_done = threading.Event()
    errors = []
    original_write = orchestrator.store.write_work

    def controlled_write(work_id, value):
        if threading.current_thread().name == "accept-thread":
            acceptance_at_write.set()
            if not release_acceptance.wait(timeout=5):
                raise RuntimeError("test acceptance write was not released")
        original_write(work_id, value)

    monkeypatch.setattr(orchestrator.store, "write_work", controlled_write)

    def run_episode():
        try:
            orchestrator.run_part_design_episode(
                "clamp_work",
                "clamp",
                request_id="success_request",
            )
        except BaseException as error:  # pragma: no cover - asserted below
            errors.append(error)
        finally:
            episode_done.set()

    def accept_new_result():
        try:
            orchestrator.accept_part_result(
                "clamp_work",
                part_job_id="base",
                result_id="part_result:base:second",
                attempt_run_id="base_attempt_1",
                result_run_id="base_attempt_1",
                review_id="review_base_002",
                artifact_references=[create_artifact_reference(
                    artifact_id="artifact:base:second",
                    work_id="clamp_work",
                    run_id="base_attempt_1",
                    part_job_id="base",
                    relative_path="second_model.step",
                    phase="build_evaluate",
                    checkpoint="reviewable_result",
                    trust_role="reviewable_result",
                    validation_status="passed",
                )],
            )
        except BaseException as error:  # pragma: no cover - asserted below
            errors.append(error)

    episode_thread = threading.Thread(target=run_episode, name="episode-thread")
    acceptance_thread = threading.Thread(target=accept_new_result, name="accept-thread")
    episode_thread.start()
    assert port.started.wait(timeout=5)
    acceptance_thread.start()
    assert acceptance_at_write.wait(timeout=5)
    port.releases["success_request"].set()
    assert not episode_done.wait(timeout=0.1)
    release_acceptance.set()
    acceptance_thread.join(timeout=5)
    episode_thread.join(timeout=5)

    assert errors == []
    assert not acceptance_thread.is_alive()
    assert not episode_thread.is_alive()
    manifest = backend._read_work_manifest("clamp_work")
    assert manifest["accepted_part_results"]["base"]["result_id"] == (
        "part_result:base:second"
    )
    assert {
        item["artifact_id"] for item in manifest["artifact_references"]
    } >= {"artifact:base:second", "episode:success_request:route"}


def test_user_input_block_commit_is_isolated_from_sibling_success(tmp_path) -> None:
    port = ConcurrentDesignPort(
        {
            "success_request": _episode_outcome(
                "success_request",
                stop_reason="completed",
                validated=True,
            ),
            "question_request": _episode_outcome(
                "question_request",
                stop_reason="user_input_required",
                validated=False,
            ),
        }
    )
    backend, orchestrator, accepted_before = _concurrent_orchestrator(tmp_path, port)
    results = {}
    errors = []

    def run_episode(request_id, part_job_id):
        try:
            results[request_id] = orchestrator.run_part_design_episode(
                "clamp_work",
                part_job_id,
                request_id=request_id,
            )
        except BaseException as error:  # pragma: no cover - test assertion below
            errors.append(error)

    success = threading.Thread(
        target=run_episode,
        args=("success_request", "clamp"),
    )
    question = threading.Thread(
        target=run_episode,
        args=("question_request", "base"),
    )
    success.start()
    question.start()
    assert port.started.wait(timeout=5)

    port.releases["question_request"].set()
    question.join(timeout=5)
    assert not question.is_alive()
    port.releases["success_request"].set()
    success.join(timeout=5)
    assert not success.is_alive()

    assert errors == []
    assert results["question_request"]["orchestration"]["status"] == "blocked"
    assert (
        results["question_request"]["orchestration"]["next_action"]
        == "Answer the focused question, then start a new Design Episode request"
    )
    manifest = backend._read_work_manifest("clamp_work")
    assert manifest["accepted_part_results"]["base"] == accepted_before
    assert {
        item["artifact_id"]
        for item in manifest["artifact_references"]
        if item["artifact_id"] in {
            "episode:success_request:route",
            "episode:question_request:route",
        }
    } == {
        "episode:success_request:route",
        "episode:question_request:route",
    }


def test_concurrent_attempt_creation_allocates_distinct_owned_child_runs(tmp_path) -> None:
    backend = _prepared_backend(tmp_path)
    orchestrator = backend._work_orchestrator()
    results = []
    errors = []
    start = threading.Barrier(3)

    def create_attempt():
        try:
            start.wait(timeout=5)
            results.append(
                orchestrator.create_part_attempt("clamp_work", "clamp")
            )
        except BaseException as error:  # pragma: no cover - test assertion below
            errors.append(error)

    threads = [threading.Thread(target=create_attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert errors == []
    new_run_ids = [item["run"]["run_id"] for item in results]
    assert len(new_run_ids) == 2
    assert len(set(new_run_ids)) == 2
    manifest = backend._read_work_manifest("clamp_work")
    attempts = manifest["part_jobs"][0]["attempts"]
    assert {item["run_id"] for item in attempts} == {
        "clamp_attempt_1",
        *new_run_ids,
    }
