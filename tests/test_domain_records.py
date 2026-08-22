from __future__ import annotations

from copy import deepcopy
import json

from ai_native_cad.domain.records import (
    WORK_SCHEMA_VERSION,
    accept_part_result,
    append_part_attempt,
    create_artifact_reference,
    create_assembly_job_record,
    create_deliverable_package_record,
    create_work_record,
    project_product_state,
    project_work_record,
)
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.actions import WorkflowConsoleActions


def _work() -> dict:
    return create_work_record(
        work_id="fixture",
        title="Fixture",
        created_at="2026-07-25T00:00:00+00:00",
    )


def test_part_job_keeps_ordered_attempt_history_and_can_accept_either_attempt():
    work = _work()
    first = append_part_attempt(
        work,
        part_job_id="clamp",
        run_id="clamp_attempt_1",
        created_at="2026-07-25T00:01:00+00:00",
    )
    second = append_part_attempt(
        first,
        part_job_id="clamp",
        run_id="clamp_attempt_2",
        created_at="2026-07-25T00:02:00+00:00",
    )
    lineage_before_acceptance = deepcopy(second["active_lineage"])

    accepted_first = accept_part_result(
        second,
        part_job_id="clamp",
        result_id="part_result:clamp:first",
        attempt_run_id="clamp_attempt_1",
        result_run_id="clamp_attempt_1",
        review_id="review_001",
        accepted_at="2026-07-25T00:03:00+00:00",
    )
    accepted_second = accept_part_result(
        second,
        part_job_id="clamp",
        result_id="part_result:clamp:second",
        attempt_run_id="clamp_attempt_2",
        result_run_id="clamp_attempt_2",
        review_id="review_002",
        accepted_at="2026-07-25T00:04:00+00:00",
    )

    attempts = accepted_first["part_jobs"][0]["attempts"]
    assert [item["run_id"] for item in attempts] == ["clamp_attempt_1", "clamp_attempt_2"]
    assert [item["sequence"] for item in attempts] == [1, 2]
    assert accepted_first["accepted_part_results"]["clamp"]["run_id"] == "clamp_attempt_1"
    assert accepted_second["accepted_part_results"]["clamp"]["run_id"] == "clamp_attempt_2"
    assert accepted_first["active_lineage"] == lineage_before_acceptance
    assert accepted_second["active_lineage"] == lineage_before_acceptance
    assert work["part_jobs"] == []
    assert len(first["part_jobs"][0]["attempts"]) == 1


def test_revision_attempt_provenance_is_optional_durable_and_backward_compatible():
    first = append_part_attempt(
        _work(),
        part_job_id="clamp",
        run_id="clamp_attempt_1",
        created_at="2026-07-25T00:01:00+00:00",
    )
    revised = append_part_attempt(
        first,
        part_job_id="clamp",
        run_id="clamp_attempt_2",
        created_at="2026-07-25T00:02:00+00:00",
        parent_run_id="clamp_attempt_1",
        source_result_id="part_result:clamp:first",
    )

    old_attempt, revision_attempt = revised["part_jobs"][0]["attempts"]
    assert old_attempt["parent_run_id"] is None
    assert old_attempt["source_result_id"] is None
    assert revision_attempt["parent_run_id"] == "clamp_attempt_1"
    assert revision_attempt["source_result_id"] == "part_result:clamp:first"
    assert project_work_record(revised) == revised


def test_legacy_v1_work_projection_preserves_runs_without_rewriting_source():
    legacy = {
        "schema_version": 1,
        "work_id": "legacy_fixture",
        "title": "Legacy fixture",
        "run_ids": ["legacy_root", "legacy_clamp"],
        "root_run_id": "legacy_root",
        "current_run_id": "legacy_root",
        "active_lineage": {
            "active_root_run_id": "legacy_root",
            "active_leaf_run_id": "legacy_root",
            "accepted_run_ids": ["legacy_root"],
            "superseded_run_ids": [],
            "latest_attempt_run_id": "legacy_clamp",
        },
        "part_jobs": [
            {
                "part_id": "clamp",
                "run_id": "legacy_clamp",
                "status": "incomplete",
                "source": "assembly_plan",
            }
        ],
        "accepted_part_results": {
            "clamp": {
                "child_run_id": "legacy_clamp",
                "review_id": "review_001",
                "status": "approved",
            }
        },
    }
    original = deepcopy(legacy)

    projected = project_work_record(legacy)

    assert projected["schema_version"] == WORK_SCHEMA_VERSION
    assert projected["part_jobs"][0]["attempts"][0]["run_id"] == "legacy_clamp"
    assert projected["accepted_part_results"]["clamp"]["run_id"] == "legacy_clamp"
    assert projected["accepted_part_results"]["clamp"]["result_id"].startswith("legacy:")
    assert projected["active_lineage"]["accepted_run_ids"] == ["legacy_root"]
    assert legacy == original


def test_work_mutations_do_not_change_immutable_run_evidence(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work("Fixture", work_id="fixture")
    backend.create_work_requirement_run(
        "fixture",
        "Create a fixture.",
        run_id="fixture_root",
    )
    run_dir = backend._work_runs_root("fixture") / "fixture_root"
    prompt_before = (run_dir / "prompt.txt").read_bytes()

    manifest = backend._read_work_manifest("fixture")
    manifest = append_part_attempt(
        manifest,
        part_job_id="clamp",
        run_id="fixture_root",
        created_at="2026-07-25T00:01:00+00:00",
    )
    manifest = accept_part_result(
        manifest,
        part_job_id="clamp",
        result_id="part_result:clamp:fixture_root",
        attempt_run_id="fixture_root",
        result_run_id="fixture_root",
        review_id="review_001",
        accepted_at="2026-07-25T00:02:00+00:00",
    )
    backend._write_work_manifest("fixture", manifest)

    assert (run_dir / "prompt.txt").read_bytes() == prompt_before
    assert not (run_dir / "work_manifest.json").exists()


def test_console_part_approval_updates_pointer_without_advancing_active_lineage(tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work("Fixture", work_id="fixture")
    backend.create_work_requirement_run(
        "fixture",
        "Create a fixture clamp.",
        run_id="fixture_root",
    )
    run_dir = backend._work_runs_root("fixture") / "fixture_root"
    (run_dir / "part_result_review.json").write_text(
        json.dumps(
            {
                "status": "accepted_for_preview",
                "part_id": "clamp",
                "child_run": "clamp_result_1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "lineage.json").write_text(
        json.dumps(
            {
                "part_id": "clamp",
                "child_run_id": "clamp_result_1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    child_dir = run_dir / "05_single_create" / "clamp_result_1"
    child_dir.mkdir(parents=True)
    (child_dir / "model.step").write_text(
        "ISO-10303-21;\nEND-ISO-10303-21;\n",
        encoding="utf-8",
    )
    (child_dir / "report.json").write_text(
        json.dumps({"status": "success"}) + "\n",
        encoding="utf-8",
    )
    lineage_before = deepcopy(
        backend._read_work_manifest("fixture")["active_lineage"]
    )

    result = WorkflowConsoleActions(backend).approve_part_result(
        "fixture_root",
        work_id="fixture",
        root=backend._work_runs_root("fixture"),
    )
    manifest = backend._read_work_manifest("fixture")
    products = backend.get_work_detail("fixture")["products"]

    assert result["accepted_part_result"]["run_id"] == "clamp_result_1"
    assert manifest["accepted_part_results"]["clamp"]["run_id"] == "clamp_result_1"
    assert manifest["accepted_part_results"]["clamp"]["artifact_ids"]
    assert manifest["artifact_references"][0]["relative_path"] == "model.step"
    assert manifest["active_lineage"] == lineage_before
    assert [item["name"] for item in products["accepted_deliverables"]] == [
        "model.step"
    ]
    assert products["artifact_state"]["untrusted_output_count"] == 0


def test_product_state_uses_manifest_references_not_filename_presence():
    work = append_part_attempt(
        _work(),
        part_job_id="clamp",
        run_id="clamp_attempt_1",
        created_at="2026-07-25T00:01:00+00:00",
    )
    accepted_step = create_artifact_reference(
        artifact_id="artifact:accepted_step",
        work_id="fixture",
        run_id="clamp_attempt_1",
        part_job_id="clamp",
        relative_path="products/clamp.step",
        phase="build_evaluate",
        checkpoint="reviewable_result",
        trust_role="reviewable_result",
        validation_status="passed",
        created_at="2026-07-25T00:02:00+00:00",
    )
    unreferenced_filename = create_artifact_reference(
        artifact_id="artifact:unaccepted_step",
        work_id="fixture",
        run_id="clamp_attempt_1",
        part_job_id="clamp",
        relative_path="model.step",
        phase="build_evaluate",
        checkpoint="geometry_candidate",
        trust_role="candidate",
        validation_status="not_validated",
        created_at="2026-07-25T00:02:00+00:00",
    )
    work["artifact_references"] = [accepted_step, unreferenced_filename]
    work = accept_part_result(
        work,
        part_job_id="clamp",
        result_id="part_result:clamp:accepted",
        attempt_run_id="clamp_attempt_1",
        result_run_id="clamp_attempt_1",
        review_id="review_001",
        artifact_ids=["artifact:accepted_step"],
        accepted_at="2026-07-25T00:03:00+00:00",
    )
    package = create_deliverable_package_record(
        package_id="package:fixture:1",
        source_accepted_result_ids=["part_result:clamp:accepted"],
        artifact_ids=["artifact:accepted_step"],
        status="ready",
        created_at="2026-07-25T00:04:00+00:00",
    )
    work["deliverable_packages"] = [package]

    state = project_product_state(work)

    assert state["state_source"] == "work_manifest_artifact_references"
    assert [item["artifact_id"] for item in state["accepted_artifacts"]] == [
        "artifact:accepted_step"
    ]
    assert [item["artifact_id"] for item in state["deliverable_artifacts"]] == [
        "artifact:accepted_step"
    ]
    assert "artifact:unaccepted_step" not in str(state)


def test_assembly_and_deliverable_records_are_schema_versioned_definitions_only():
    assembly = create_assembly_job_record(
        assembly_job_id="fixture_assembly",
        accepted_part_result_ids=["part_result:clamp:accepted"],
        reference_components=[{"component_id": "bolt_m6", "quantity": 2}],
        intent={"summary": "Hold two plates"},
    )
    package = create_deliverable_package_record(
        package_id="package:fixture:1",
        source_accepted_result_ids=["part_result:clamp:accepted"],
        artifact_ids=[],
    )

    assert assembly["schema_version"] == 1
    assert assembly["attempts"] == []
    assert assembly["accepted_result_id"] is None
    assert package["schema_version"] == 1
    assert package["status"] == "defined"
