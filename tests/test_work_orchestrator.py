from __future__ import annotations

from copy import deepcopy

from ai_native_cad.domain.records import create_artifact_reference
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.routes import dispatch_route


def _step_reference(
    *,
    work_id: str,
    part_job_id: str,
    run_id: str,
    suffix: str,
) -> dict:
    return create_artifact_reference(
        artifact_id=f"artifact:{part_job_id}:{suffix}",
        work_id=work_id,
        run_id=run_id,
        part_job_id=part_job_id,
        relative_path="model.step",
        phase="build_evaluate",
        checkpoint="reviewable_result",
        trust_role="reviewable_result",
        validation_status="passed",
        created_at=f"2026-07-27T00:0{suffix}:00+00:00",
    )


def test_work_orchestrator_keeps_two_attempts_and_can_accept_either(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    created = backend.create_work("Clamp", work_id="clamp_work")
    intent = backend.create_work_requirement_run(
        "clamp_work",
        "Create a clamp.",
        run_id="clamp_intent",
    )
    lineage_before = deepcopy(
        backend._read_work_manifest("clamp_work")["active_lineage"]
    )

    first = backend.create_work_part_attempt(
        "clamp_work",
        "clamp",
        run_id="clamp_attempt_1",
    )
    second_response = dispatch_route(
        backend,
        "create_work_part_attempt",
        path_params={"work_id": "clamp_work", "part_job_id": "clamp"},
        body={"run_id": "clamp_attempt_2"},
    )
    first_prompt = (
        backend._work_runs_root("clamp_work")
        / "clamp_attempt_1"
        / "prompt.txt"
    ).read_bytes()
    lineage_after_attempts = deepcopy(
        backend._read_work_manifest("clamp_work")["active_lineage"]
    )

    orchestrator = backend._work_orchestrator()
    accepted_first = orchestrator.accept_part_result(
        "clamp_work",
        part_job_id="clamp",
        result_id="part_result:clamp:first",
        attempt_run_id="clamp_attempt_1",
        result_run_id="clamp_attempt_1",
        review_id="review_001",
        artifact_references=[
            _step_reference(
                work_id="clamp_work",
                part_job_id="clamp",
                run_id="clamp_attempt_1",
                suffix="1",
            )
        ],
    )
    accepted_second = orchestrator.accept_part_result(
        "clamp_work",
        part_job_id="clamp",
        result_id="part_result:clamp:second",
        attempt_run_id="clamp_attempt_2",
        result_run_id="clamp_attempt_2",
        review_id="review_002",
        artifact_references=[
            _step_reference(
                work_id="clamp_work",
                part_job_id="clamp",
                run_id="clamp_attempt_2",
                suffix="2",
            )
        ],
    )
    manifest = backend._read_work_manifest("clamp_work")
    job = manifest["part_jobs"][0]

    assert created["orchestration"]["orchestrator"] == "work_orchestrator"
    assert intent["orchestration"]["checkpoint"] == "intent_snapshot"
    assert first["orchestration"]["checkpoint"] == "part_job_attempt"
    assert second_response["ok"] is True
    assert (
        second_response["data"]["orchestration"]["orchestrator"]
        == "work_orchestrator"
    )
    assert [attempt["run_id"] for attempt in job["attempts"]] == [
        "clamp_attempt_1",
        "clamp_attempt_2",
    ]
    assert accepted_first["accepted_part_result"]["attempt_run_id"] == "clamp_attempt_1"
    assert accepted_second["accepted_part_result"]["attempt_run_id"] == "clamp_attempt_2"
    assert (
        accepted_second["product_state"]["state_source"]
        == "work_manifest_artifact_references"
    )
    assert manifest["accepted_part_results"]["clamp"]["result_id"] == (
        "part_result:clamp:second"
    )
    assert manifest["active_lineage"] == lineage_after_attempts
    assert manifest["active_lineage"]["active_root_run_id"] == (
        lineage_before["active_root_run_id"]
    )
    assert manifest["active_lineage"]["active_leaf_run_id"] == (
        lineage_before["active_leaf_run_id"]
    )
    assert (
        backend._work_runs_root("clamp_work")
        / "clamp_attempt_1"
        / "prompt.txt"
    ).read_bytes() == first_prompt


def test_artifact_registration_retry_preserves_first_identity_timestamp(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work("Clamp", work_id="clamp_work")
    backend.create_work_part_attempt(
        "clamp_work",
        "clamp",
        run_id="clamp_attempt_1",
    )
    orchestrator = backend._work_orchestrator()
    reference = _step_reference(
        work_id="clamp_work",
        part_job_id="clamp",
        run_id="clamp_attempt_1",
        suffix="1",
    )
    orchestrator.accept_part_result(
        "clamp_work",
        part_job_id="clamp",
        result_id="part_result:clamp:first",
        attempt_run_id="clamp_attempt_1",
        result_run_id="clamp_attempt_1",
        review_id="review_001",
        artifact_references=[reference],
    )
    retry = {**reference, "created_at": "2026-07-27T12:00:00+00:00"}
    orchestrator.accept_part_result(
        "clamp_work",
        part_job_id="clamp",
        result_id="part_result:clamp:first",
        attempt_run_id="clamp_attempt_1",
        result_run_id="clamp_attempt_1",
        review_id="review_001",
        artifact_references=[retry],
    )

    manifest = backend._read_work_manifest("clamp_work")
    assert len(manifest["artifact_references"]) == 1
    assert manifest["artifact_references"][0]["created_at"] == reference["created_at"]


def test_auto_advance_failure_persists_blocked_intent_without_part_attempts(
    tmp_path,
    monkeypatch,
):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    config = dispatch_route(
        backend,
        "write_workspace_config",
        body={"advancement_mode": "auto_advance"},
    )
    assert config["ok"] is True
    backend.create_work("Blocked", work_id="blocked_work")

    def fail_stage(*args, **kwargs):
        raise RuntimeError("deterministic stage failed")

    monkeypatch.setattr(backend, "run_stage_by_id", fail_stage)
    result = backend.create_work_requirement_run(
        "blocked_work",
        "Create a blocked test fixture.",
        run_id="blocked_intent",
    )
    manifest = backend._read_work_manifest("blocked_work")

    assert result["orchestration"]["status"] == "blocked"
    assert result["part_runs"]["created_runs"] == []
    assert manifest["requirement"]["status"] == "blocked"
    assert manifest["root_run_id"] == "blocked_intent"
    assert manifest["part_jobs"] == []
    assert (
        backend._work_runs_root("blocked_work")
        / "blocked_intent"
        / "prompt.txt"
    ).exists()
