"""CadFlow-owned publication gate for attested model-program STEP evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_native_cad.agents.episode import AgentEpisodeResult
from ai_native_cad.agents.model_program_runtime import (
    MODEL_PROGRAM_LIMITS,
    WSL_MODEL_PROGRAM_PROFILE,
    canonical_json_bytes,
)
from ai_native_cad.orchestration.ports import (
    DesignEpisodeArtifact,
    DesignPartEpisodeRequest,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReviewablePublicationError(ValueError):
    """Typed safe block raised before a reviewable artifact is registered."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PublishedReviewable:
    record: dict[str, Any]
    result_artifact: DesignEpisodeArtifact
    step_artifact: DesignEpisodeArtifact


def publish_reviewable_model_program_result(
    *,
    request: DesignPartEpisodeRequest,
    result: AgentEpisodeResult,
    episode_dir: Path,
    relative_root: str,
) -> PublishedReviewable:
    """Validate immutable execution evidence and publish one reviewable STEP."""

    if not (
        result.result_kind == "model_program"
        and result.status == "completed"
        and result.stop_reason.value == "completed"
        and result.execution_succeeded
        and result.output_validated
        and result.final_candidate_id
        and result.final_observation_id
        and result.execution_count > 0
    ):
        raise ReviewablePublicationError("publication_episode_incomplete")

    root = episode_dir.resolve()
    observation_path = _child(
        root,
        Path("execution_observations")
        / f"observation_{result.execution_count:03d}.json",
    )
    observation = _read_json(observation_path)
    output = observation.get("output")
    if not isinstance(output, dict):
        raise ReviewablePublicationError("publication_evidence_missing")
    if not (
        observation.get("observation_id") == result.final_observation_id
        and observation.get("success") is True
        and observation.get("codes") == []
        and observation.get("execution_id")
        and observation.get("attestation_digest")
        and observation.get("execution_profile") == WSL_MODEL_PROGRAM_PROFILE
        and observation.get("side_effect_started") is True
        and observation.get("exit_state") == "completed"
        and observation.get("reviewable") is False
        and observation.get("accepted") is False
        and observation.get("deliverable") is False
    ):
        raise ReviewablePublicationError("publication_observation_invalid")

    manifest_relative = output.get("evidence_manifest")
    if not isinstance(manifest_relative, str):
        raise ReviewablePublicationError("publication_evidence_missing")
    manifest_path = _child(root, Path(manifest_relative))
    manifest = _read_json(manifest_path)
    expected_identity = {
        "work_id": request.work_id,
        "run_id": request.run_id,
        "part_job_id": request.part_job_id,
        "episode_id": result.episode_id,
        "candidate_id": result.final_candidate_id,
        "execution_id": observation["execution_id"],
    }
    if any(manifest.get(key) != value for key, value in expected_identity.items()):
        raise ReviewablePublicationError("publication_identity_mismatch")
    if not (
        output.get("candidate_id") == result.final_candidate_id
        and output.get("execution_id") == observation["execution_id"]
        and output.get("reviewable") is False
        and output.get("accepted") is False
        and output.get("deliverable") is False
    ):
        raise ReviewablePublicationError("publication_identity_mismatch")
    if not (
        manifest.get("owner") == "cadflow_tool_broker"
        and manifest.get("trust_role") == "candidate"
        and manifest.get("reviewable") is False
        and manifest.get("accepted") is False
        and manifest.get("deliverable") is False
        and manifest.get("api_id") == "cadquery_v1"
    ):
        raise ReviewablePublicationError("publication_trust_role_invalid")

    for key in (
        "source_hash",
        "parameters_hash",
        "profile_digest",
        "toolchain_digest",
    ):
        if not _digest(manifest.get(key)) or output.get(key) != manifest.get(key):
            raise ReviewablePublicationError("publication_digest_mismatch")
    if not (
        _digest(manifest.get("attestation_digest"))
        and manifest["attestation_digest"] == observation["attestation_digest"]
    ):
        raise ReviewablePublicationError("publication_attestation_mismatch")

    evidence_dir = manifest_path.parent
    source_path = _child(evidence_dir, Path("source.py"))
    parameters_path = _child(evidence_dir, Path("parameters.json"))
    if _sha256(source_path) != manifest["source_hash"]:
        raise ReviewablePublicationError("publication_source_tampered")
    try:
        parameters = json.loads(parameters_path.read_text(encoding="utf-8"))
        parameter_hash = hashlib.sha256(canonical_json_bytes(parameters)).hexdigest()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise ReviewablePublicationError("publication_parameters_tampered") from None
    if parameter_hash != manifest["parameters_hash"]:
        raise ReviewablePublicationError("publication_parameters_tampered")

    outputs = output.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 1:
        raise ReviewablePublicationError("publication_output_invalid")
    step_summary = outputs[0]
    if not isinstance(step_summary, dict) or step_summary.get("name") != "model.step":
        raise ReviewablePublicationError("publication_output_invalid")
    step_relative = step_summary.get("relative_path")
    if not isinstance(step_relative, str):
        raise ReviewablePublicationError("publication_output_invalid")
    step_path = _child(root, Path(step_relative))
    step_hash = _sha256(step_path)
    step_size = step_path.stat().st_size
    if not (
        _digest(step_summary.get("sha256"))
        and step_summary["sha256"] == step_hash
        and step_summary.get("size") == step_size
        and step_size > 0
    ):
        raise ReviewablePublicationError("publication_step_tampered")
    manifest_step = [
        item
        for item in (manifest.get("files") or [])
        if isinstance(item, dict) and item.get("name") == "model.step"
    ]
    if manifest_step != [
        {"name": "model.step", "sha256": step_hash, "size": step_size}
    ]:
        raise ReviewablePublicationError("publication_step_manifest_mismatch")

    worker = manifest.get("worker_observation")
    geometry = output.get("geometry")
    step_reimport = output.get("step_reimport")
    if not (
        isinstance(worker, dict)
        and worker.get("success") is True
        and worker.get("observation_type")
        == "model_program_execution_completed"
        and worker.get("codes") == []
        and worker.get("exit_state") == "completed"
        and worker.get("geometry") == geometry
        and worker.get("step_reimport") == step_reimport
        and _valid_roundtrip(geometry, step_reimport)
        and observation.get("limits") == manifest.get("limits")
        and manifest.get("limits") == MODEL_PROGRAM_LIMITS
    ):
        raise ReviewablePublicationError("publication_geometry_invalid")

    reviewable_result_id = (
        f"reviewable_{result.episode_id}_{result.final_candidate_id}"
    )
    step_artifact_id = (
        f"reviewable_step_{result.episode_id}_{result.final_candidate_id}"
    )
    assumptions = _final_assumptions(
        root / "agent_events.jsonl", result.final_candidate_id
    )
    normalized_step_relative = step_relative.replace("\\", "/")
    record = {
        "record_type": "reviewable_result",
        "schema_version": 1,
        "reviewable_result_id": reviewable_result_id,
        "work_id": request.work_id,
        "run_id": request.run_id,
        "part_job_id": request.part_job_id,
        "episode_id": result.episode_id,
        "candidate_id": result.final_candidate_id,
        "observation_id": result.final_observation_id,
        "execution_id": observation["execution_id"],
        "capability_mode": result.capability_mode,
        "api_id": manifest["api_id"],
        "source_hash": manifest["source_hash"],
        "parameters_hash": manifest["parameters_hash"],
        "attestation_digest": manifest["attestation_digest"],
        "profile_digest": manifest["profile_digest"],
        "toolchain_digest": manifest["toolchain_digest"],
        "limits": manifest["limits"],
        "geometry": geometry,
        "step_reimport": step_reimport,
        "step": {
            "artifact_id": step_artifact_id,
            "relative_path": normalized_step_relative,
            "sha256": step_hash,
            "size": step_size,
        },
        "assumptions": assumptions,
        "validation": {
            "execution_success": True,
            "step_reimport_valid": True,
            "solid_count": geometry["solid_count"],
        },
        "limitations": [
            "No fit, motion, strength, tolerance, DFM/DFA, GD&T, FEA, or safety validation was performed.",
            "Reviewable is not accepted and cannot enter a Deliverable Package until explicit user acceptance.",
        ],
        "recommended_action": "Accept or revise",
        "trust_role": "reviewable_result",
        "reviewable": True,
        "accepted": False,
        "deliverable": False,
    }
    reviewable_path = root / "reviewable_result.json"
    _write_json_exclusive(reviewable_path, record)
    result_artifact_id = reviewable_result_id
    result_artifact = DesignEpisodeArtifact(
        artifact_id=result_artifact_id,
        relative_path=f"{relative_root}/reviewable_result.json",
        checkpoint="reviewable_result",
        trust_role="reviewable_result",
        validation_status="passed",
        source_artifact_ids=(
            f"episode:{result.episode_id}:model_program_candidate",
            f"episode:{result.episode_id}:execution_observation",
        ),
    )
    step_artifact = DesignEpisodeArtifact(
        artifact_id=step_artifact_id,
        relative_path=f"{relative_root}/{normalized_step_relative}",
        checkpoint="reviewable_result",
        trust_role="reviewable_result",
        validation_status="passed",
        source_artifact_ids=(result_artifact_id,),
    )
    return PublishedReviewable(record, result_artifact, step_artifact)


def write_publication_diagnostic(
    episode_dir: Path,
    *,
    code: str,
) -> None:
    _write_json_exclusive(
        episode_dir / "publication_diagnostic.json",
        {
            "schema_version": 1,
            "owner": "cadflow_reviewable_publication_gate",
            "code": code,
            "trust_role": "diagnostic",
            "reviewable": False,
            "accepted": False,
            "deliverable": False,
        },
    )


def _child(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise ReviewablePublicationError("publication_path_invalid")
    candidate = root / relative
    if candidate.is_symlink():
        raise ReviewablePublicationError("publication_path_invalid")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        raise ReviewablePublicationError("publication_path_invalid") from None
    if not resolved.is_file():
        raise ReviewablePublicationError("publication_evidence_missing")
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ReviewablePublicationError("publication_evidence_unreadable") from None
    if not isinstance(value, dict):
        raise ReviewablePublicationError("publication_evidence_unreadable")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise ReviewablePublicationError("publication_evidence_unreadable") from None


def _digest(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _valid_roundtrip(geometry: Any, reimport: Any) -> bool:
    imported = reimport.get("geometry") if isinstance(reimport, dict) else None
    if not (
        isinstance(geometry, dict)
        and geometry.get("valid") is True
        and isinstance(geometry.get("solid_count"), int)
        and geometry["solid_count"] >= 1
        and isinstance(reimport, dict)
        and reimport.get("valid") is True
        and isinstance(imported, dict)
        and imported.get("valid") is True
        and imported.get("solid_count") == geometry.get("solid_count")
    ):
        return False
    before_box = geometry.get("bounding_box")
    after_box = imported.get("bounding_box")
    bbox_tolerance = reimport.get("bbox_tolerance_mm")
    before_volume = geometry.get("volume")
    after_volume = imported.get("volume")
    absolute_tolerance = reimport.get("volume_absolute_tolerance_mm3")
    relative_tolerance = reimport.get("volume_relative_tolerance")
    if not (
        isinstance(before_box, dict)
        and isinstance(after_box, dict)
        and _number(bbox_tolerance)
        and 0 <= bbox_tolerance <= 0.01
        and _number(before_volume)
        and before_volume > 0
        and _number(after_volume)
        and after_volume > 0
        and _number(absolute_tolerance)
        and absolute_tolerance == 0.01
        and _number(relative_tolerance)
        and relative_tolerance == 1e-6
    ):
        return False
    if any(
        not _number(before_box.get(axis))
        or not _number(after_box.get(axis))
        or abs(before_box[axis] - after_box[axis]) > bbox_tolerance
        for axis in ("x", "y", "z")
    ):
        return False
    return abs(before_volume - after_volume) <= max(
        absolute_tolerance,
        abs(before_volume) * relative_tolerance,
    )


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _final_assumptions(path: Path, candidate_id: str) -> list[str]:
    assumptions: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return assumptions
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("candidate_id") != candidate_id:
            continue
        values = event.get("assumptions")
        if isinstance(values, list):
            assumptions = [item for item in values if isinstance(item, str)][:16]
    return assumptions


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError:
        raise ReviewablePublicationError("publication_evidence_conflict") from None


__all__ = [
    "PublishedReviewable",
    "ReviewablePublicationError",
    "publish_reviewable_model_program_result",
    "write_publication_diagnostic",
]
