from __future__ import annotations

import hashlib
import json

import pytest

from ai_native_cad.agents.episode import AgentEpisodeResult, StopReason
from ai_native_cad.agents.model_program_runtime import (
    MODEL_PROGRAM_LIMITS,
    canonical_json_bytes,
)
from ai_native_cad.orchestration.ports import DesignPartEpisodeRequest
from ai_native_cad.orchestration.reviewable_publication import (
    ReviewablePublicationError,
    publish_reviewable_model_program_result,
)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fixture(tmp_path):
    episode_id = "a" * 32
    execution_id = "exec_001"
    candidate_id = "candidate_001"
    observation_id = "observation_001"
    evidence_dir = tmp_path / "candidates" / candidate_id / execution_id
    evidence_dir.mkdir(parents=True)
    source = "import cadquery as cq\n\ndef build_model(parameters):\n    return cq.Workplane('XY').box(10, 20, 5)\n"
    parameters = {"length": 10, "width": 20, "height": 5}
    step = b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n"
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    parameters_hash = hashlib.sha256(canonical_json_bytes(parameters)).hexdigest()
    step_hash = hashlib.sha256(step).hexdigest()
    geometry = {
        "valid": True,
        "solid_count": 1,
        "face_count": 6,
        "cylindrical_face_count": 0,
        "volume": 1000.0,
        "bounding_box": {"x": 10.0, "y": 20.0, "z": 5.0},
    }
    reimport = {
        "valid": True,
        "geometry": dict(geometry),
        "bbox_tolerance_mm": 0.01,
        "volume_absolute_tolerance_mm3": 0.01,
        "volume_relative_tolerance": 1e-6,
    }
    worker = {
        "schema_version": 1,
        "success": True,
        "observation_type": "model_program_execution_completed",
        "codes": [],
        "exit_state": "completed",
        "geometry": geometry,
        "step_reimport": reimport,
    }
    limits = dict(MODEL_PROGRAM_LIMITS)
    manifest = {
        "schema_version": 1,
        "owner": "cadflow_tool_broker",
        "trust_role": "candidate",
        "reviewable": False,
        "accepted": False,
        "deliverable": False,
        "work_id": "work_1",
        "run_id": "run_1",
        "part_job_id": "part_1",
        "episode_id": episode_id,
        "candidate_id": candidate_id,
        "execution_id": execution_id,
        "api_id": "cadquery_v1",
        "source_hash": source_hash,
        "parameters_hash": parameters_hash,
        "attestation_digest": "1" * 64,
        "profile_digest": "2" * 64,
        "toolchain_digest": "3" * 64,
        "limits": limits,
        "worker_observation": worker,
        "files": [
            {"name": "model.step", "sha256": step_hash, "size": len(step)}
        ],
    }
    (evidence_dir / "source.py").write_bytes(source.encode("utf-8"))
    _write_json(evidence_dir / "parameters.json", parameters)
    (evidence_dir / "model.step").write_bytes(step)
    manifest_relative = (
        f"candidates/{candidate_id}/{execution_id}/evidence_manifest.json"
    )
    _write_json(evidence_dir / "evidence_manifest.json", manifest)
    output = {
        "candidate_id": candidate_id,
        "execution_id": execution_id,
        "source_hash": source_hash,
        "parameters_hash": parameters_hash,
        "profile_digest": manifest["profile_digest"],
        "toolchain_digest": manifest["toolchain_digest"],
        "geometry": geometry,
        "step_reimport": reimport,
        "evidence_manifest": manifest_relative,
        "outputs": [
            {
                "name": "model.step",
                "sha256": step_hash,
                "size": len(step),
                "relative_path": (
                    f"candidates/{candidate_id}/{execution_id}/model.step"
                ),
            }
        ],
        "reviewable": False,
        "accepted": False,
        "deliverable": False,
    }
    observation = {
        "schema_version": 1,
        "observation_id": observation_id,
        "owner": "cadflow_tool_broker",
        "tool_id": "execute_model_program",
        "success": True,
        "observation_type": "model_program_execution_completed",
        "codes": [],
        "execution_profile": "wsl2_cadquery_v1",
        "side_effect_started": True,
        "execution_id": execution_id,
        "attestation_digest": manifest["attestation_digest"],
        "limits": limits,
        "exit_state": "completed",
        "output": output,
        "reviewable": False,
        "accepted": False,
        "deliverable": False,
    }
    _write_json(
        tmp_path / "execution_observations" / "observation_001.json",
        observation,
    )
    (tmp_path / "agent_events.jsonl").write_text(
        json.dumps(
            {
                "event_type": "agent_action",
                "candidate_id": candidate_id,
                "assumptions": ["Dimensions are in millimetres."],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    request = DesignPartEpisodeRequest(
        request_id="request_1",
        work_id="work_1",
        run_id="run_1",
        part_job_id="part_1",
        objective="Create a rectangular solid",
        role=None,
        interface_context={},
        accepted_result_id=None,
    )
    result = AgentEpisodeResult(
        episode_id=episode_id,
        operation="design_part",
        skill_id="design_part",
        skill_version="0.2.0",
        status="completed",
        stop_reason=StopReason.COMPLETED,
        capability_mode="provider_selected_design_with_attested_model_program",
        step_count=4,
        context_request_count=0,
        context_byte_count=0,
        contract_submission_count=0,
        repair_attempt_count=0,
        final_contract=None,
        validation_feedback=None,
        validated=False,
        result_kind="model_program",
        source_submission_count=1,
        execution_count=1,
        observation_inspection_count=1,
        final_candidate_id=candidate_id,
        final_observation_id=observation_id,
        execution_succeeded=True,
        output_validated=True,
    )
    return request, result, evidence_dir, observation


def test_publication_cross_checks_and_writes_immutable_reviewable_result(
    tmp_path,
):
    request, result, evidence_dir, _ = _fixture(tmp_path)

    published = publish_reviewable_model_program_result(
        request=request,
        result=result,
        episode_dir=tmp_path,
        relative_root="episodes/design_part/request_1",
    )

    record = json.loads(
        (tmp_path / "reviewable_result.json").read_text(encoding="utf-8")
    )
    assert record == published.record
    assert record["reviewable"] is True
    assert record["accepted"] is False
    assert record["deliverable"] is False
    assert record["recommended_action"] == "Accept or revise"
    assert record["step"]["sha256"] == hashlib.sha256(
        (evidence_dir / "model.step").read_bytes()
    ).hexdigest()
    assert published.result_artifact.trust_role == "reviewable_result"
    assert published.step_artifact.source_artifact_ids == (
        published.result_artifact.artifact_id,
    )
    with pytest.raises(
        ReviewablePublicationError, match="publication_evidence_conflict"
    ):
        publish_reviewable_model_program_result(
            request=request,
            result=result,
            episode_dir=tmp_path,
            relative_root="episodes/design_part/request_1",
        )


@pytest.mark.parametrize(
    "tamper,code",
    [
        ("step", "publication_step_tampered"),
        ("source", "publication_source_tampered"),
        ("identity", "publication_identity_mismatch"),
        ("profile", "publication_digest_mismatch"),
        ("roundtrip", "publication_geometry_invalid"),
        ("limits", "publication_geometry_invalid"),
    ],
)
def test_publication_tampering_is_diagnostic_only(tmp_path, tamper, code):
    request, result, evidence_dir, observation = _fixture(tmp_path)
    if tamper == "step":
        (evidence_dir / "model.step").write_bytes(b"tampered")
    elif tamper == "source":
        (evidence_dir / "source.py").write_text("tampered", encoding="utf-8")
    elif tamper == "identity":
        manifest_path = evidence_dir / "evidence_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["work_id"] = "other_work"
        _write_json(manifest_path, manifest)
    elif tamper == "profile":
        observation["output"]["profile_digest"] = "4" * 64
        _write_json(
            tmp_path / "execution_observations" / "observation_001.json",
            observation,
        )
    elif tamper == "roundtrip":
        manifest_path = evidence_dir / "evidence_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["worker_observation"]["step_reimport"]["geometry"][
            "volume"
        ] = 999.0
        _write_json(manifest_path, manifest)
        observation["output"]["step_reimport"]["geometry"]["volume"] = 999.0
        _write_json(
            tmp_path / "execution_observations" / "observation_001.json",
            observation,
        )
    else:
        manifest_path = evidence_dir / "evidence_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["limits"]["wall_clock_seconds"] = 300
        _write_json(manifest_path, manifest)
        observation["limits"]["wall_clock_seconds"] = 300
        _write_json(
            tmp_path / "execution_observations" / "observation_001.json",
            observation,
        )

    with pytest.raises(ReviewablePublicationError, match=code):
        publish_reviewable_model_program_result(
            request=request,
            result=result,
            episode_dir=tmp_path,
            relative_root="episodes/design_part/request_1",
        )
    assert not (tmp_path / "reviewable_result.json").exists()
