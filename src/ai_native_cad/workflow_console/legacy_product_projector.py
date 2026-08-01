"""Explicit compatibility projection from legacy Run summaries.

The target product view consumes Work manifests and artifact references only.
Older deterministic Runs predate those references, so this boundary translates
their already-sanitized metadata into an in-memory v2 Work projection.  It
never writes a Run or a Work manifest and it never turns failed/unknown output
into an accepted result.
"""

from __future__ import annotations

from typing import Any

from ai_native_cad.domain.records import (
    create_artifact_reference,
    project_work_record,
    register_artifact_references,
    validate_work_record,
)

PRODUCT_OUTPUT_NAMES = {"model.step", "model.stl", "preview.png"}
REVIEWABLE_STATUSES = {
    "success",
    "completed",
    "completed_with_assumptions",
    "ready_for_review",
    "accepted_for_preview",
    "generated",
    "accepted",
    "approved",
}
FAILED_STATUSES = {"failed", "blocked", "error"}


def project_legacy_product_references(
    manifest: dict[str, Any],
    run_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a non-persisted compatibility Work with explicit references."""
    projected = project_work_record(manifest)
    existing_ids = {
        item["artifact_id"] for item in projected["artifact_references"]
    }
    existing_by_location = {
        (item["run_id"], item["relative_path"]): item["artifact_id"]
        for item in projected["artifact_references"]
    }
    accepted_by_run: dict[str, tuple[str, dict[str, Any]]] = {}
    for part_job_id, pointer in projected["accepted_part_results"].items():
        if pointer.get("status") == "approved" and isinstance(pointer.get("run_id"), str):
            accepted_by_run[pointer["run_id"]] = (part_job_id, pointer)

    references: list[dict[str, Any]] = []
    reference_ids_by_run: dict[str, list[str]] = {}
    fallback_created_at = (
        projected.get("updated_at")
        or projected.get("created_at")
        or "1970-01-01T00:00:00+00:00"
    )
    for record in run_records:
        run_id = record.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            continue
        status = _status_value(record.get("status"))
        accepted = accepted_by_run.get(run_id)
        part_job_id = accepted[0] if accepted else None
        for relative_path in record.get("artifacts", []):
            if relative_path in PRODUCT_OUTPUT_NAMES:
                continue
            if (run_id, relative_path) in existing_by_location:
                continue
            artifact_id = _legacy_artifact_id(run_id, relative_path)
            if artifact_id in existing_ids:
                continue
            references.append(
                create_artifact_reference(
                    artifact_id=artifact_id,
                    work_id=projected["work_id"],
                    run_id=run_id,
                    part_job_id=part_job_id,
                    relative_path=relative_path,
                    phase="build_evaluate",
                    checkpoint=(
                        "failed_attempt_evidence"
                        if _is_failed(status)
                        else "run_observation"
                    ),
                    trust_role="diagnostic" if _is_failed(status) else "observation",
                    validation_status=(
                        "failed"
                        if _is_failed(status)
                        else (
                            "passed"
                            if accepted is not None or status in REVIEWABLE_STATUSES
                            else "not_validated"
                        )
                    ),
                    created_at=record.get("updated_at") or fallback_created_at,
                )
            )
        for relative_path in record.get("downloadables", []):
            if relative_path not in PRODUCT_OUTPUT_NAMES:
                continue
            artifact_id = existing_by_location.get(
                (run_id, relative_path),
                _legacy_artifact_id(run_id, relative_path),
            )
            reference_ids_by_run.setdefault(run_id, []).append(artifact_id)
            if artifact_id in existing_ids:
                continue
            if accepted is not None:
                trust_role = "accepted_result"
                checkpoint = "accepted_result"
                validation_status = "passed"
            elif _is_failed(status):
                trust_role = "diagnostic"
                checkpoint = "failed_attempt"
                validation_status = "failed"
            elif status in REVIEWABLE_STATUSES:
                trust_role = "reviewable_result"
                checkpoint = "reviewable_result"
                validation_status = "passed"
            else:
                trust_role = "candidate"
                checkpoint = "untrusted_candidate"
                validation_status = "not_validated"
            references.append(
                create_artifact_reference(
                    artifact_id=artifact_id,
                    work_id=projected["work_id"],
                    run_id=run_id,
                    part_job_id=part_job_id,
                    relative_path=relative_path,
                    phase="build_evaluate",
                    checkpoint=checkpoint,
                    trust_role=trust_role,
                    validation_status=validation_status,
                    created_at=record.get("updated_at") or fallback_created_at,
                )
            )

    if references:
        projected = register_artifact_references(
            projected,
            references,
            updated_at=projected.get("updated_at"),
        )

    # Legacy accepted-result records did not carry artifact ids.  Link only
    # explicitly projected product outputs and leave historical evidence intact.
    for pointer in projected["accepted_part_results"].values():
        if pointer.get("status") != "approved":
            continue
        run_id = pointer.get("run_id")
        projected_ids = reference_ids_by_run.get(run_id, [])
        if projected_ids and not pointer.get("artifact_ids"):
            pointer["artifact_ids"] = list(projected_ids)
    validate_work_record(projected)
    return projected


def _legacy_artifact_id(run_id: str, relative_path: str) -> str:
    safe_name = relative_path.replace("\\", "_").replace("/", "_").replace(":", "_")
    return f"legacy:{run_id}:{safe_name}"


def _status_value(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("status")
    return str(value or "unknown")


def _is_failed(value: str) -> bool:
    return value in FAILED_STATUSES or "failed" in value or "blocked" in value
