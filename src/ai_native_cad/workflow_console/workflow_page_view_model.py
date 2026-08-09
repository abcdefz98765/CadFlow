"""Single, mode-safe view model for the Workflow cockpit page.

This module is intentionally the only place where Work lineage, immutable Run
snapshots, graph nodes, selected-stage detail, and action targets are assembled
for the NiceGUI Workflow page.  It reads backend projections only; it never
writes artifacts or infers lineage from browser state.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from ai_native_cad.workflow_console.review_surface import build_workflow_review_surface
from ai_native_cad.workflow_console.product_usability import (
    build_agent_output_projection,
    build_agent_first_workflow_projection,
    build_recovery_projection,
)
from ai_native_cad.workflow_console.i18n import (
    action_labels,
    action_label,
    copy as i18n_copy,
    stage_label,
    status_label,
)
from ai_native_cad.workflow_console.work_stage_projection import (
    build_work_stage_projection,
    unavailable_work_stage_projection,
)


ViewMode = Literal["current_work", "run_snapshot"]
_ATTENTION = {"blocked": "required", "needs_review": "required", "running": "in_progress", "stale": "required"}
_SELECTION_PRIORITY = ("blocked", "needs_review", "running", "stale")
_READ_ONLY_REASON = "Historical Run Snapshots are read-only. Return to Current Work or create a new Rework attempt."
_REVIEW_DECISION_ACTIONS = {"save_stage_review", "approve_stage", "mark_needs_revision", "mark_blocked"}
_AGENT_REVIEW_ACTIONS = {"part_review", "part_result_review", "create_workflow_review"}

_PHASE_KEYS = (
    "intent",
    "design",
    "build_evaluate",
    "accept_deliver",
)


def build_workbench_overview_view_model(
    backend: Any,
    work_id: str,
    *,
    language: str = "en",
) -> dict[str, Any]:
    """Project the existing Current Work surface into the Agent-first Overview.

    This is a presentation projection over the same manifest, Part Jobs,
    artifact references, actions, and history already used by the console.  It
    adds no browser-owned domain state and never infers trust from a filename.
    """

    language = "zh" if language == "zh" else "en"
    work = backend.get_work_detail(work_id)
    summary = _dict_value(work.get("summary"))
    entity = _dict_value(work.get("entity_state"))
    references = [
        dict(item)
        for item in entity.get("artifact_references", [])
        if isinstance(item, dict)
    ]
    accepted = _dict_value(entity.get("accepted_part_results"))
    result_records = _reviewable_records(
        backend,
        work_id,
        references,
    )
    jobs = _workbench_part_jobs(
        entity,
        accepted,
        references,
        result_records,
        [item for item in work.get("parts", []) if isinstance(item, dict)],
        language,
    )
    active_job = _active_workbench_part(jobs)
    active_record = (
        result_records.get(active_job.get("reviewable_result_id"))
        if isinstance(active_job, dict)
        else None
    )
    design_evidence = _workbench_design_evidence(
        backend,
        work_id,
        active_job,
        references,
        language,
    )
    user_input = _workbench_user_input(
        backend,
        work_id,
        entity,
        active_job,
        references,
        design_evidence,
        language,
    )
    agent_design = _workbench_agent_design(
        design_evidence,
        active_record,
        language,
    )
    phase_key = _workbench_phase(entity, jobs, active_job)
    metadata = _dict_value(entity.get("metadata"))
    if metadata.get("example_classification") == "product_golden":
        capability_key = "reproducible_product_golden"
    elif metadata.get("example_classification") == "live_agent_example":
        capability_key = "agentic_experimental"
    elif (
        isinstance(active_record, dict)
        and active_record.get("capability_mode")
        == "provider_selected_design_with_attested_model_program"
    ):
        capability_key = "agentic_experimental"
    else:
        capability_key = "deterministic_compatibility"
    preview = _workbench_preview(work_id, active_job, active_record, references, language)
    agent_output = build_agent_output_projection(
        backend,
        work_id,
        references,
        language=language,
    )
    recovery = build_recovery_projection(
        backend,
        work_id,
        entity,
        references,
        language=language,
        agent_output=agent_output,
    )
    activity = _workbench_agent_activity(
        active_job,
        active_record,
        references,
        language,
        recovery=recovery,
    )
    recommendation = _workbench_recommendation(
        entity,
        active_job,
        active_record,
        language,
    )
    current_result = _workbench_result(
        active_job,
        active_record,
        language,
        design_evidence=design_evidence,
    )
    transformation = _workbench_transformation(
        user_input,
        agent_design,
        active_job,
        active_record,
        references,
        language,
    )
    objective = str(
        entity.get("description")
        or summary.get("title")
        or i18n_copy(language, "no_candidate")
    )
    phase_items = [
        {
            "key": key,
            "label": i18n_copy(language, f"phase_{key}"),
            "current": key == phase_key,
        }
        for key in _PHASE_KEYS
    ]
    accepted_count = sum(
        1
        for pointer in accepted.values()
        if isinstance(pointer, dict) and pointer.get("status") == "approved"
    )
    return {
        "work": {
            "title": summary.get("title") or work_id,
            "status": summary.get("overall_status") or "incomplete",
            "active_part": active_job.get("part_job_id") if active_job else None,
            "accepted_part_count": accepted_count,
            "part_count": len(jobs),
        },
        "phase": {
            "key": phase_key,
            "label": i18n_copy(language, f"phase_{phase_key}"),
            "items": phase_items,
            "orientation_only": True,
        },
        "objective": {
            "title": i18n_copy(language, "current_objective"),
            "summary": objective,
        },
        "user_input": user_input,
        "agent_design": agent_design,
        "transformation": transformation,
        "recommendation": recommendation,
        "recovery": recovery,
        "agent_output": agent_output,
        "capability": {
            "key": capability_key,
            "label": i18n_copy(language, capability_key),
            "experimental": capability_key in {
                "agentic_experimental",
                "reproducible_product_golden",
            },
        },
        "agent_activity": activity,
        "preview": preview,
        "current_result": current_result,
        "part_jobs": jobs,
        "history": {
            "reachable": True,
            "run_snapshot_read_only": True,
            "run_count": len(work.get("run_history", [])),
        },
        "workflow": {
            "reachable": True,
            "label": i18n_copy(language, "detailed_workflow"),
            "current_phase": phase_key,
            "part_job_state": active_job.get("state") if active_job else "not_started",
            "progression": transformation.get("events", []),
        },
        "advanced": {
            "label": i18n_copy(language, "advanced_evidence"),
            "collapsed": True,
            "work_id": work_id,
            "run_ids": list(entity.get("run_ids", [])),
            "artifact_references": references,
                "reviewable_evidence": _advanced_reviewable_evidence(active_record),
                "input_evidence": {
                    "durable": user_input.get("durable") is True,
                    "source_type": user_input.get("source_type"),
                },
                "design_evidence": {
                    "present": design_evidence.get("present") is True,
                    "checkpoint": "design_brief" if design_evidence.get("present") else None,
                },
            },
        }


def _reviewable_records(
    backend: Any,
    work_id: str,
    references: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for reference in references:
        if not (
            reference.get("checkpoint") == "reviewable_result"
            and reference.get("trust_role") == "reviewable_result"
            and reference.get("validation_status") == "passed"
            and str(reference.get("relative_path") or "").endswith(
                "/reviewable_result.json"
            )
        ):
            continue
        artifact_id = reference.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        try:
            payload = backend.read_work_artifact_reference(work_id, artifact_id)
        except (FileNotFoundError, ValueError):
            continue
        content = payload.get("content") if isinstance(payload, dict) else None
        if not (
            isinstance(content, dict)
            and content.get("reviewable_result_id") == artifact_id
            and content.get("reviewable") is True
        ):
            continue
        records[artifact_id] = content
    return records


def _workbench_design_evidence(
    backend: Any,
    work_id: str,
    job: dict[str, Any] | None,
    references: list[dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    if not job:
        return {"present": False}
    run_id = job.get("latest_attempt_run_id")
    reference = next(
        (
            item
            for item in reversed(references)
            if item.get("checkpoint") == "design_brief"
            and item.get("trust_role") == "candidate"
            and item.get("part_job_id") == job.get("part_job_id")
            and item.get("run_id") == run_id
        ),
        None,
    )
    if not isinstance(reference, dict) or not isinstance(reference.get("artifact_id"), str):
        return {"present": False}
    try:
        payload = backend.read_work_artifact_reference(work_id, reference["artifact_id"])
    except (FileNotFoundError, ValueError):
        return {"present": False}
    envelope = payload.get("content") if isinstance(payload, dict) else None
    content = envelope.get("content") if isinstance(envelope, dict) else None
    if not isinstance(content, dict):
        return {"present": False}
    localized = _dict_value(_dict_value(content.get("translations")).get(language))
    allowed = {
        "concept": localized.get("concept") or content.get("concept"),
        "geometry_strategy": localized.get("geometry_strategy") or content.get("geometry_strategy"),
        "important_parameters": localized.get("important_parameters") or content.get("important_parameters"),
        "functional_features": localized.get("functional_features") or content.get("functional_features"),
        "interfaces": localized.get("interfaces") or content.get("interfaces"),
        "user_constraints": localized.get("user_constraints") or content.get("user_constraints"),
        "assumptions": localized.get("assumptions") or content.get("assumptions"),
        "tradeoffs": localized.get("tradeoffs") or content.get("tradeoffs"),
        "changes_after_repair": localized.get("changes_after_repair") or content.get("changes_after_repair"),
        "repair_count": content.get("repair_count"),
        "source_capability_mode": localized.get("source_capability_mode") or content.get("source_capability_mode"),
        "external_provider_quality_proof": content.get("external_provider_quality_proof") is True,
    }
    return {"present": True, **allowed}


def _workbench_user_input(
    backend: Any,
    work_id: str,
    entity: dict[str, Any],
    job: dict[str, Any] | None,
    references: list[dict[str, Any]],
    design_evidence: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    raw_job = next(
        (
            item
            for item in entity.get("part_jobs", [])
            if isinstance(item, dict)
            and isinstance(job, dict)
            and item.get("part_job_id") == job.get("part_job_id")
        ),
        {},
    )
    attempts = [item for item in raw_job.get("attempts", []) if isinstance(item, dict)]
    first_run_id = attempts[0].get("run_id") if attempts else entity.get("root_run_id")
    active_run_id = job.get("latest_attempt_run_id") if isinstance(job, dict) else first_run_id
    original = _read_work_prompt(backend, work_id, first_run_id)
    if not original:
        original = str(entity.get("description") or "").strip() or None
    active_prompt = _read_work_prompt(backend, work_id, active_run_id)
    active_attempt = attempts[-1] if attempts else {}
    is_revision = bool(
        attempts
        and (
            active_attempt.get("source") == "reviewable_result_revision"
            or (active_run_id and first_run_id and active_run_id != first_run_id)
        )
    )
    revision = _revision_request_text(active_prompt) if is_revision else None

    constraints = design_evidence.get("user_constraints")
    if not isinstance(constraints, list):
        constraints = _first_design_constraints(
            backend,
            work_id,
            job,
            references,
            language,
        )
    return {
        "title": i18n_copy(language, "your_request"),
        "original_request": original,
        "revision_request": revision,
        "visible_constraints": [str(item) for item in constraints if str(item).strip()][:8],
        "source_type": "revision" if is_revision else "initial_request",
        "source_label": i18n_copy(
            language,
            "request_source_revision" if is_revision else "request_source_initial",
        ),
        "durable": bool(original or revision),
        "generated_summary_used": False,
    }


def _read_work_prompt(backend: Any, work_id: str, run_id: Any) -> str | None:
    if not isinstance(run_id, str) or not run_id:
        return None
    try:
        return backend.read_work_run_prompt(work_id, run_id)
    except (FileNotFoundError, ValueError):
        return None


def _revision_request_text(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "Revise reviewable result "
    if value.startswith(prefix) and ": " in value:
        return value.split(": ", 1)[1].strip() or None
    return value


def _first_design_constraints(
    backend: Any,
    work_id: str,
    job: dict[str, Any] | None,
    references: list[dict[str, Any]],
    language: str,
) -> list[Any]:
    if not job:
        return []
    run_ids = [
        item.get("run_id")
        for item in references
        if isinstance(item, dict)
        and item.get("checkpoint") == "design_brief"
        and item.get("part_job_id") == job.get("part_job_id")
    ]
    for run_id in run_ids:
        evidence = _workbench_design_evidence(
            backend,
            work_id,
            {**job, "latest_attempt_run_id": run_id},
            references,
            language,
        )
        if isinstance(evidence.get("user_constraints"), list):
            return evidence["user_constraints"]
    return []


def _workbench_agent_design(
    evidence: dict[str, Any],
    record: dict[str, Any] | None,
    language: str,
) -> dict[str, Any]:
    if not evidence.get("present"):
        return {
            "title": i18n_copy(language, "agent_design"),
            "evidence_status": "insufficient",
            "summary": i18n_copy(language, "agent_design_evidence_gap"),
            "concept": None,
            "geometry_strategy": None,
            "important_parameters": [],
            "functional_features": [],
            "interfaces": [],
            "assumptions": list(record.get("assumptions") or []) if isinstance(record, dict) else [],
            "tradeoffs": [],
            "changes_after_repair": [],
            "source_capability_mode": record.get("capability_mode") if isinstance(record, dict) else None,
            "private_reasoning_exposed": False,
        }
    return {
        "title": i18n_copy(language, "agent_design"),
        "evidence_status": "persisted_summary",
        "summary": evidence.get("concept"),
        "concept": evidence.get("concept"),
        "geometry_strategy": evidence.get("geometry_strategy"),
        "important_parameters": list(evidence.get("important_parameters") or [])[:10],
        "functional_features": list(evidence.get("functional_features") or [])[:10],
        "interfaces": list(evidence.get("interfaces") or [])[:8],
        "assumptions": list(evidence.get("assumptions") or [])[:8],
        "tradeoffs": list(evidence.get("tradeoffs") or [])[:6],
        "changes_after_repair": list(evidence.get("changes_after_repair") or [])[:6],
        "repair_count": evidence.get("repair_count"),
        "source_capability_mode": evidence.get("source_capability_mode"),
        "external_provider_quality_proof": evidence.get("external_provider_quality_proof") is True,
        "private_reasoning_exposed": False,
    }


def _workbench_transformation(
    user_input: dict[str, Any],
    agent_design: dict[str, Any],
    job: dict[str, Any] | None,
    record: dict[str, Any] | None,
    references: list[dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    roles = {
        str(item.get("trust_role"))
        for item in references
        if isinstance(item, dict)
    }
    successful_observation = any(
        item.get("checkpoint") == "execution_observation"
        and item.get("trust_role") == "observation"
        and item.get("validation_status") in {"passed", "completed", "valid"}
        for item in references
        if isinstance(item, dict)
    )
    events = [
        {
            "key": "request_received",
            "label": i18n_copy(language, "timeline_request_received"),
            "status": "completed" if user_input.get("durable") else "pending",
        },
        {
            "key": "design_candidate",
            "label": i18n_copy(language, "timeline_design_candidate"),
            "status": "completed" if agent_design.get("evidence_status") == "persisted_summary" or "candidate" in roles else "pending",
        },
        {
            "key": "geometry_built",
            "label": i18n_copy(language, "timeline_geometry_built"),
            "status": "completed" if record or successful_observation else "pending",
        },
        {
            "key": "step_inspected",
            "label": i18n_copy(language, "timeline_step_inspected"),
            "status": "completed" if isinstance(record, dict) and _dict_value(record.get("validation")).get("step_reimport_valid") is True else "pending",
        },
        {
            "key": "ready_review",
            "label": i18n_copy(language, "timeline_ready_review"),
            "status": "completed" if job and job.get("has_reviewable_result") else "pending",
        },
    ]
    if int(agent_design.get("repair_count") or 0) > 0:
        events.insert(
            4,
            {
                "key": "candidate_repaired",
                "label": i18n_copy(language, "repairing_candidate"),
                "status": "completed",
            },
        )
    return {
        "title": i18n_copy(language, "what_happened"),
        "chain": ["user_request", "agent_design", "build_evaluate", "result"],
        "events": events,
    }


def _workbench_part_jobs(
    entity: dict[str, Any],
    accepted: dict[str, Any],
    references: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    legacy_parts: list[dict[str, Any]],
    language: str,
) -> list[dict[str, Any]]:
    jobs = []
    for raw in entity.get("part_jobs", []):
        if not isinstance(raw, dict):
            continue
        part_id = raw.get("part_job_id") or raw.get("part_id")
        if not isinstance(part_id, str):
            continue
        attempts = [item for item in raw.get("attempts", []) if isinstance(item, dict)]
        latest_run_id = (
            raw.get("active_attempt_run_id")
            or (attempts[-1].get("run_id") if attempts else None)
        )
        pointer = _dict_value(accepted.get(part_id))
        compatibility = next(
            (item for item in legacy_parts if item.get("part_id") == part_id),
            {},
        )
        result_ids = [
            artifact_id
            for artifact_id, record in records.items()
            if record.get("part_job_id") == part_id
        ]
        latest_result_id = next(
            (
                artifact_id
                for attempt in reversed(attempts)
                for artifact_id in reversed(result_ids)
                if records[artifact_id].get("run_id") == attempt.get("run_id")
            ),
            result_ids[-1] if result_ids else None,
        )
        accepted_result_id = pointer.get("result_id")
        has_new_attempt = bool(
            latest_run_id
            and accepted_result_id
            and latest_run_id
            not in {pointer.get("attempt_run_id"), pointer.get("run_id")}
        )
        if has_new_attempt:
            state = "design"
        elif latest_result_id and latest_result_id == accepted_result_id:
            state = "accepted"
        elif latest_result_id:
            state = "reviewable"
        elif accepted_result_id:
            state = "accepted"
        elif attempts:
            state = "design"
        else:
            state = "not_started"
        jobs.append(
            {
                "part_job_id": part_id,
                "name": part_id.replace("_", " ").title(),
                "role": raw.get("role") or ("零件" if language == "zh" else "Part"),
                "attempt_count": len(attempts),
                "latest_attempt_run_id": latest_run_id,
                "latest_attempt_source": attempts[-1].get("source") if attempts else None,
                "state": state,
                "state_label": status_label(language, state),
                "reviewable_result_id": latest_result_id,
                "accepted_result_id": accepted_result_id,
                "has_reviewable_result": bool(latest_result_id),
                "has_accepted_result": bool(accepted_result_id),
                "legacy_download_run_id": compatibility.get("download_run_id"),
                "legacy_has_stl": bool(compatibility.get("has_stl")),
                "legacy_has_step": bool(compatibility.get("has_step")),
                "recommended_action": _part_recommendation(state, language),
            }
        )
    if jobs:
        return jobs

    # Deterministic compatibility Works may predate first-class Part Jobs.  The
    # existing Work projector remains the authority for these rows.
    return [
        {
            "part_job_id": item.get("part_id"),
            "name": str(item.get("part_id") or "Part").replace("_", " ").title(),
            "role": item.get("role") or ("零件" if language == "zh" else "Part"),
            "attempt_count": int(item.get("attempt_count") or 0),
            "latest_attempt_run_id": item.get("latest_run_id"),
            "legacy_download_run_id": item.get("download_run_id"),
            "legacy_has_stl": bool(item.get("has_stl")),
            "legacy_has_step": bool(item.get("has_step")),
            "state": "accepted" if item.get("status") == "accepted" else (
                "reviewable" if item.get("status") == "needs_review" else "design"
            ),
            "state_label": status_label(
                language,
                "accepted" if item.get("status") == "accepted" else (
                    "reviewable" if item.get("status") == "needs_review" else "design"
                ),
            ),
            "reviewable_result_id": None,
            "accepted_result_id": "legacy_accepted" if item.get("status") == "accepted" else None,
            "has_reviewable_result": item.get("status") == "needs_review",
            "has_accepted_result": item.get("status") == "accepted",
            "recommended_action": _part_recommendation(
                "accepted" if item.get("status") == "accepted" else "design",
                language,
            ),
        }
        for item in legacy_parts
    ]


def _active_workbench_part(jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for state in ("reviewable", "design", "accepted", "not_started"):
        match = next((item for item in jobs if item.get("state") == state), None)
        if match:
            return match
    return jobs[0] if jobs else None


def _workbench_phase(
    entity: dict[str, Any],
    jobs: list[dict[str, Any]],
    active_job: dict[str, Any] | None,
) -> str:
    if not entity.get("root_run_id") and not jobs:
        return "intent"
    state = active_job.get("state") if active_job else None
    if state in {"reviewable", "accepted"}:
        return "accept_deliver"
    if state == "design":
        return "design"
    if any(
        item.get("trust_role") == "observation"
        for item in entity.get("artifact_references", [])
        if isinstance(item, dict)
    ):
        return "build_evaluate"
    return "design"


def _workbench_preview(
    work_id: str,
    job: dict[str, Any] | None,
    record: dict[str, Any] | None,
    references: list[dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    if job and record:
        result_id = record.get("reviewable_result_id")
        accepted_reference = result_id == job.get("accepted_result_id")
        step = next(
            (
                item
                for item in references
                if isinstance(item, dict)
                and item.get("checkpoint") == "reviewable_result"
                and item.get("trust_role") == "reviewable_result"
                and item.get("validation_status") == "passed"
                and item.get("part_job_id") == job.get("part_job_id")
                and result_id in (item.get("source_artifact_ids") or [])
            ),
            None,
        )
        if step:
            artifact_id = step.get("artifact_id")
            return {
                "status": "accepted" if accepted_reference else "reviewable",
                "label": i18n_copy(
                    language,
                    "accepted_result_retained"
                    if accepted_reference and job.get("state") == "design"
                    else ("result_accepted" if accepted_reference else "result_ready_review"),
                ),
                "kind": "registered_step",
                "viewer_url": (
                    f"/web-viewer/index.html?file="
                    f"%2Fapi%2Fwork-artifacts%2F{work_id}%2F{artifact_id}%2Fpreview.stl"
                ),
                "download_url": f"/api/work-artifacts/{work_id}/{artifact_id}/download",
                "geometry": _dict_value(record.get("geometry")),
            }
    if job and job.get("legacy_has_stl") and job.get("legacy_download_run_id"):
        run_id = job["legacy_download_run_id"]
        return {
            "status": job.get("state"),
            "label": i18n_copy(language, "model_ready"),
            "kind": "legacy_stl",
            "viewer_url": f"/web-viewer/index.html?file=%2Fapi%2Fdownloads%2F{run_id}%2Fmodel.stl",
            "download_url": (
                f"/api/downloads/{run_id}/model.step"
                if job.get("legacy_has_step")
                else None
            ),
            "geometry": {},
        }
    return {
        "status": "no_candidate",
        "label": i18n_copy(language, "no_candidate"),
        "kind": "empty",
        "viewer_url": None,
        "download_url": None,
        "geometry": {},
    }


def _workbench_agent_activity(
    job: dict[str, Any] | None,
    record: dict[str, Any] | None,
    references: list[dict[str, Any]],
    language: str,
    *,
    recovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    answered_question_ids = {
        source
        for item in references
        if item.get("trust_role") == "accepted_input"
        for source in item.get("source_artifact_ids", [])
        if isinstance(source, str)
    }
    waiting_for_user = any(
        item.get("checkpoint") == "clarification_decision"
        and item.get("validation_status") == "user_input_required"
        and item.get("artifact_id") not in answered_question_ids
        for item in references
    )
    recovery_category = str((recovery or {}).get("category") or "")
    safely_stopped = recovery_category in {
        "provider_auth_failed",
        "provider_failure",
        "policy_blocked",
        "unsupported_capability",
        "budget_exhausted",
    }
    if waiting_for_user:
        key = "waiting_user"
    elif safely_stopped:
        key = "safely_stopped"
    elif record and job and job.get("state") in {"reviewable", "accepted"}:
        key = "accepted_state" if job.get("state") == "accepted" else "ready_review"
    elif any(
        item.get("checkpoint") == "execution_observation"
        and item.get("trust_role") == "observation"
        and item.get("validation_status") == "passed"
        for item in references
    ):
        key = "inspecting_step"
    elif any(item.get("trust_role") == "candidate" for item in references):
        key = "building_geometry"
    elif any(
        item.get("checkpoint") == "contract_validation"
        and item.get("trust_role") == "diagnostic"
        for item in references
    ):
        key = "repairing_candidate"
    elif job and job.get("attempt_count"):
        key = "preparing_candidate"
    else:
        key = "understanding_interfaces"
    details = []
    detail_keys = {
        "candidate": "preparing_candidate",
        "observation": "inspecting_step",
        "reviewable_result": "ready_review",
        "diagnostic": "safely_stopped" if safely_stopped else "repairing_candidate",
    }
    for reference in references[-12:]:
        detail_key = detail_keys.get(str(reference.get("trust_role")))
        if detail_key and i18n_copy(language, detail_key) not in details:
            details.append(i18n_copy(language, detail_key))
    return {
        "key": key,
        "label": i18n_copy(language, key),
        "summary": i18n_copy(language, key),
        "details": details,
        "raw_provider_payload_exposed": False,
        "private_reasoning_exposed": False,
    }


def _workbench_recommendation(
    entity: dict[str, Any],
    job: dict[str, Any] | None,
    record: dict[str, Any] | None,
    language: str,
) -> dict[str, Any]:
    if not entity.get("root_run_id") and not job:
        return {
            "key": "start_design",
            "label": i18n_copy(language, "start_design"),
            "summary": (
                "描述目标并开始第一个设计尝试。"
                if language == "zh"
                else "Describe the objective and start the first design attempt."
            ),
        }
    if job and record and job.get("state") == "reviewable":
        return {
            "key": "accept_or_revise",
            "label": i18n_copy(language, "accept_result"),
            "summary": i18n_copy(language, "result_ready_review"),
        }
    if job and job.get("state") == "accepted":
        return {
            "key": "revise",
            "label": i18n_copy(language, "revise"),
            "summary": i18n_copy(language, "accept_success_detail"),
        }
    return {
        "key": "continue_agent",
        "label": i18n_copy(language, "continue_agent"),
        "summary": (
            "让 Agent 准备、生成并检查下一候选设计。"
            if language == "zh"
            else "Let the Agent prepare, build, and inspect the next candidate."
        ),
    }


def _workbench_result(
    job: dict[str, Any] | None,
    record: dict[str, Any] | None,
    language: str,
    *,
    design_evidence: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not job:
        return None
    if not record:
        if job.get("legacy_has_step") or job.get("has_accepted_result"):
            return {
                "status": job.get("state"),
                "title": i18n_copy(
                    language,
                    "result_accepted" if job.get("state") == "accepted" else "model_ready",
                ),
                "part": job.get("name"),
                "role": job.get("role"),
                "geometry": {},
                "verified": [],
                "assumptions": [],
                "limitations": [],
                "unverified": [],
                "unsupported": [],
                "not_requested": [],
            }
        return None
    geometry = _dict_value(record.get("geometry"))
    validation = _dict_value(record.get("validation"))
    accepted_reference = record.get("reviewable_result_id") == job.get("accepted_result_id")
    revision_in_progress = job.get("state") == "design" and accepted_reference
    verified = []
    if geometry.get("valid") is True:
        verified.append("有效实体" if language == "zh" else "Valid solid")
    if isinstance(record.get("step"), dict):
        verified.append("STEP 导出成功" if language == "zh" else "STEP export passed")
    if validation.get("step_reimport_valid") is True:
        verified.append(
            "STEP 重新导入验证通过"
            if language == "zh"
            else "STEP re-import passed"
        )
    return {
        "status": job.get("state"),
        "title": i18n_copy(
            language,
            "accepted_result_retained"
            if revision_in_progress
            else ("result_accepted" if accepted_reference else "result_ready_review"),
        ),
        "part": job.get("name"),
        "role": job.get("role"),
        "geometry": geometry,
        "verified": verified,
        "assumptions": list(
            _dict_value(design_evidence).get("assumptions")
            or record.get("assumptions")
            or []
        ),
        "limitations": list(
            _dict_value(design_evidence).get("limitations")
            or record.get("limitations")
            or []
        )[:3],
        "unverified": (
            ["与指定制造商舵机模型的装配配合"]
            if language == "zh"
            else ["Fit against a specified manufacturer servo model"]
        ),
        "unsupported": (
            ["工程发布验证"]
            if language == "zh"
            else ["Engineering release validation"]
        ),
        "not_requested": (
            ["强度分析", "公差分析", "运动分析"]
            if language == "zh"
            else ["Strength analysis", "Tolerance analysis", "Motion analysis"]
        ),
        "reviewable_result_id": record.get("reviewable_result_id"),
        "accepted": accepted_reference,
        "revision_in_progress": revision_in_progress,
    }


def _advanced_reviewable_evidence(record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    keys = (
        "run_id",
        "episode_id",
        "candidate_id",
        "observation_id",
        "execution_id",
        "api_id",
        "source_hash",
        "parameters_hash",
        "attestation_digest",
        "profile_digest",
        "toolchain_digest",
        "limits",
    )
    return {key: deepcopy(record.get(key)) for key in keys if record.get(key) is not None}


def _part_recommendation(state: str, language: str) -> str:
    if state == "reviewable":
        return i18n_copy(language, "accept_result")
    if state == "accepted":
        return i18n_copy(language, "revise")
    return i18n_copy(language, "continue_agent")


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}

# Canonical checkpoints stay owned by the architecture.  This catalog only
# explains their established responsibility in the user's language.
_GUIDANCE: dict[str, dict[str, tuple[str, str]]] = {
    "requirement": {
        "purpose": ("Turn the request into an engineering requirement with assumptions and missing information.", "将需求转为包含假设和缺失信息的工程需求。"),
        "decision": ("No decision is needed unless an assumption or missing detail is wrong.", "除非假设或缺失信息有误，否则当前无需决定。"),
        "next": ("Continue to planning.", "继续进入规划。"),
        "expected": ("A design approach will be prepared; no CAD model will be created.", "将形成设计路径，不会创建 CAD 模型。"),
        "recovery": ("Clarify or correct the requirement.", "补充或更正需求。"),
    },
    "clarification": {
        "purpose": ("Resolve only the information that materially affects the requirement.", "仅解决会实质影响需求的信息。"),
        "decision": ("Answer the focused questions or accept the stated assumptions.", "回答聚焦问题，或接受已说明的假设。"),
        "next": ("Update the active requirement, then continue to planning.", "更新当前需求后继续规划。"),
        "expected": ("A new requirement version will record the clarification.", "新的需求版本将记录这些澄清。"),
        "recovery": ("Return to the requirement when the scope itself is wrong.", "如范围本身不正确，请返回需求阶段。"),
    },
    "planning": {
        "purpose": ("Choose an engineering approach and define its scope and capability boundaries.", "确定工程路线，并界定范围和能力边界。"),
        "decision": ("No decision is needed unless the proposed approach is unsuitable.", "除非建议的路线不合适，否则当前无需决定。"),
        "next": ("Review the assembly plan.", "查看装配计划。"),
        "expected": ("CadFlow will describe candidate strategies; it will not generate CAD yet.", "CadFlow 将说明候选路线；此时不会生成 CAD。"),
        "recovery": ("Revise the requirement or planning approach.", "修改需求或规划路线。"),
    },
    "assembly_plan": {
        "purpose": ("Split the confirmed request into candidate parts, reference components, and their interface context.", "将已确认需求拆分为候选零件、参考组件及其接口上下文。"),
        "decision": ("No decision is needed unless you want a different next part.", "除非希望更换下一步零件，否则当前无需决定。"),
        "next": ("Create a Part Request for the selected part.", "为已选零件创建零件请求。"),
        "expected": ("A scoped single-part task will be prepared; CAD will not run yet.", "将准备单零件任务；不会立即执行 CAD。"),
        "recovery": ("Inspect candidates or return to planning if the split is wrong.", "检查候选零件；若拆分有误则返回规划。"),
    },
    "part_request": {
        "purpose": ("Define the scoped contract for exactly one selected part.", "为一个已选零件定义范围明确的任务合同。"),
        "decision": ("Confirm the part scope is right before modeling review.", "在建模评审前确认零件范围正确。"),
        "next": ("Review whether this part request is ready for modeling.", "评审该零件请求是否可建模。"),
        "expected": ("A reviewable task contract will be created, not a CAD result.", "将创建可评审的任务合同，而非 CAD 结果。"),
        "recovery": ("Return to the assembly plan when the selected part is wrong.", "如所选零件有误，请返回装配计划。"),
    },
    "part_review": {
        "purpose": ("Check whether the part request is coherent and ready for modeling.", "检查零件请求是否连贯且可进入建模。"),
        "decision": ("Review the request before it becomes the CAD input.", "在其成为 CAD 输入前评审该请求。"),
        "next": ("Create the reviewed handoff.", "创建已评审交接。"),
        "expected": ("CadFlow will record a readiness conclusion; it will not create CAD.", "CadFlow 将记录就绪结论；不会创建 CAD。"),
        "recovery": ("Request changes to the part request.", "请求修改零件请求。"),
    },
    "reviewed_handoff": {
        "purpose": ("Freeze the approved modeling brief and assembly context for the CAD IR proposal.", "冻结已批准的建模简报和装配上下文，供 CAD IR 提案使用。"),
        "decision": ("No decision is needed unless the modeling brief is incorrect.", "除非建模简报有误，否则当前无需决定。"),
        "next": ("Create a CAD IR draft.", "创建 CAD IR 草稿。"),
        "expected": ("A structured geometry proposal can be prepared from this handoff.", "可基于此交接准备结构化几何提案。"),
        "recovery": ("Return to Part Review to correct the brief.", "返回零件评审以更正简报。"),
    },
    "cad_ir_draft": {
        "purpose": ("Present a structured, reviewable geometry proposal before deterministic execution.", "在确定性执行前呈现结构化、可评审的几何提案。"),
        "decision": ("Inspect the proposal when a limitation or validation issue needs attention.", "当限制或验证问题需要关注时检查该提案。"),
        "next": ("Validate the CAD IR and proceed to part modeling when valid.", "验证 CAD IR；有效后进入零件建模。"),
        "expected": ("A validated CAD IR can be passed to deterministic modeling.", "已验证的 CAD IR 可交给确定性建模。"),
        "recovery": ("Correct the reviewed handoff or record a rework request.", "更正已评审交接，或记录返工请求。"),
    },
    "part_modeling": {
        "purpose": ("Validate CAD IR and execute deterministic modeling only when it is valid.", "验证 CAD IR，并且仅在有效时执行确定性建模。"),
        "decision": ("Review the result when it is ready; Contract mode intentionally needs no export decision.", "结果就绪时进行检查；Contract 模式的跳过执行不需要导出决策。"),
        "next": ("Review the single-part result.", "评审单零件结果。"),
        "expected": ("Full mode may create STEP/STL. Contract mode records validated input only and intentionally skips execution.", "Full 模式可能生成 STEP/STL；Contract 模式只记录已验证输入，并有意跳过执行。"),
        "recovery": ("Inspect the CAD IR or return upstream with a rework request.", "检查 CAD IR，或带着返工请求返回上游。"),
    },
    "part_result_review": {
        "purpose": ("Assess one child part result against its reviewed handoff.", "根据已评审交接评估一个子零件结果。"),
        "decision": ("Decide whether to approve this part result, request revision, or leave it unaccepted.", "决定批准该零件结果、请求修改，或暂不接受。"),
        "next": ("Approve the result only when it is acceptable for this part.", "仅在该零件结果可接受时批准它。"),
        "expected": ("Approval updates the accepted result for this part only; it does not claim a complete assembly.", "批准只更新此零件的已接受结果；不会宣称完整装配已完成。"),
        "recovery": ("Request revision or leave the result unaccepted.", "请求修改，或保持该结果未接受。"),
    },
    "workflow_review": {
        "purpose": ("Summarize the current Work, accepted results, limitations, and valid next action.", "总结当前 Work、已接受结果、限制及有效的下一步。"),
        "decision": ("Choose whether to continue with another part, request rework, or inspect deliverables.", "选择继续下一个零件、请求返工，或检查交付物。"),
        "next": ("Continue with the recommended Work-level action.", "继续执行推荐的 Work 级操作。"),
        "expected": ("The Work conclusion will be refreshed; this does not generate a complete assembly.", "将刷新 Work 结论；不会生成完整装配。"),
        "recovery": ("Request rework when the current scope is not acceptable.", "若当前范围不可接受，请请求返工。"),
    },
    "rework": {
        "purpose": ("Create a traceable new attempt from an explicit review decision.", "根据明确的评审决定创建可追溯的新尝试。"),
        "decision": ("Confirm the requested changes and target checkpoint.", "确认请求的修改和目标检查点。"),
        "next": ("Create a new rework Run.", "创建新的返工 Run。"),
        "expected": ("A child Run will preserve the older attempt and advance the requested rework path.", "将创建子 Run，保留旧尝试并推进请求的返工路径。"),
        "recovery": ("Save a Needs Revision review with requested changes first.", "请先保存包含请求修改的“需要修改”评审。"),
    },
}


def _artifact_kind(name: str) -> str:
    """Return the UI kind used by the single artifact-viewer contract."""
    if name.endswith(".json"):
        return "json"
    if name.endswith(".md"):
        return "markdown"
    if name.endswith(".step"):
        return "step"
    if name.endswith(".stl"):
        return "stl"
    return "text"


def _artifact_display_name(name: str) -> str:
    names = {
        "workflow_review.json": "Workflow review",
        "workflow_review.md": "Workflow review summary",
        "stage_review.json": "Stage review decision",
        "part_result_review.json": "Part result report",
        "report.json": "Run report",
        "report.md": "Run report summary",
        "model.step": "STEP model",
        "model.stl": "STL model",
    }
    return names.get(name, name)


def build_workflow_page_view_model(
    backend: Any,
    work_id: str,
    *,
    view_mode: ViewMode = "current_work",
    selected_run_id: str | None = None,
    selected_stage_id: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Build one coherent Workflow page for a Work or immutable Run snapshot."""
    if view_mode not in {"current_work", "run_snapshot"}:
        raise ValueError("workflow view mode must be current_work or run_snapshot")
    work = backend.get_work_detail(work_id)
    summary = work.get("summary") if isinstance(work.get("summary"), dict) else {}
    entity = work.get("entity_state") if isinstance(work.get("entity_state"), dict) else {}
    lineage = summary.get("active_lineage") if isinstance(summary.get("active_lineage"), dict) else {}
    active_root = lineage.get("active_root_run_id") or summary.get("root_run_id")
    if view_mode == "current_work":
        overview = build_workbench_overview_view_model(backend, work_id, language=language)
        agent_page = build_agent_first_workflow_projection(
            backend,
            work_id,
            work,
            overview,
            selected_node_id=selected_stage_id,
            language=language,
        )
        selected_node = _dict_value(agent_page.get("selected_node"))
        interaction = _dict_value(selected_node.get("interaction"))
        primary_action = interaction.get("primary_action") if isinstance(interaction.get("primary_action"), dict) else None
        secondary_actions = [
            dict(item)
            for item in interaction.get("secondary_actions", [])
            if isinstance(item, dict)
        ]
        available_actions = {
            "primary_action": primary_action,
            "secondary_actions": secondary_actions,
            "disabled_actions": [],
            "advanced_actions": [],
        }
        agent_page.update({
            "view_mode": "current_work",
            "read_only": False,
            "read_only_reason": None,
            "work": {
                "work_id": work_id,
                "title": summary.get("title") or work_id,
                "overall_status": summary.get("overall_status"),
                "summary": summary.get("next_action"),
            },
            "active_lineage": lineage,
            "lineage_inferred": bool(lineage.get("lineage_inferred")),
            "viewed_run_id": None,
            "run_strip": _run_strip(work.get("run_history"), lineage, view_mode, None),
            "recommended_next_action": primary_action,
            "available_actions": available_actions,
            "action_inventory": _action_inventory(available_actions, agent_page.get("workflow_graph") or {}),
            "empty_state": None,
            "error_state": None,
            "source": {"projection": "agent_first", "overview": overview},
        })
        return agent_page
    if view_mode == "run_snapshot":
        if not selected_run_id:
            raise ValueError("a Run Snapshot requires selected_run_id")
        run = backend.read_run_metadata_by_id(selected_run_id, root=backend._work_runs_root(work_id))
        projection = None
        surface = build_workflow_review_surface(
            backend, selected_run_id, run, selected_stage_id=selected_stage_id, language=language,
        )
        source_run_id = selected_run_id
    else:
        try:
            projection = build_work_stage_projection(backend, work_id)
        except (FileNotFoundError, ValueError) as exc:
            projection = unavailable_work_stage_projection(work_id, type(exc).__name__)
        root_run = projection.get("root_run") if isinstance(projection.get("root_run"), dict) else {}
        surface = build_workflow_review_surface(
            backend, active_root if isinstance(active_root, str) else None, root_run,
            selected_stage_id=selected_stage_id, language=language, projection=projection,
        )
        source_run_id = active_root if isinstance(active_root, str) else None

    stages = [dict(stage) for stage in surface.get("stages", []) if isinstance(stage, dict)]
    stages = [_with_guidance(stage, language, view_mode) for stage in stages]
    selected = _select_stage(stages, selected_stage_id, view_mode)
    selected_id = selected.get("stage_id") if selected else None
    if selected is not None:
        selected = _stage_detail(selected, source_run_id, view_mode)
    graph = _workflow_graph(surface.get("workflow_graph"), stages, selected_id, projection, source_run_id, work_id, view_mode, language)
    action_target = source_run_id
    actions = _scoped_actions(selected, view_mode, work_id, action_target, language)
    if selected is not None:
        selected["primary_action"] = actions["primary_action"]
        selected["secondary_actions"] = actions["secondary_actions"]
        selected["disabled_actions"] = actions["disabled_actions"]
        selected["guidance"] = _with_action_guidance(selected["guidance"], actions, language)
    conclusion = _conclusion(surface, selected, summary, view_mode)
    if language == "zh" and selected is not None:
        guidance = selected.get("guidance") if isinstance(selected.get("guidance"), dict) else {}
        conclusion["title"] = stage_label(language, selected.get("stage_id"), "当前工作流")
        conclusion["summary"] = guidance.get("current_conclusion") or conclusion.get("summary")
        conclusion["rationale"] = " · ".join(str(item) for item in guidance.get("limitations", [])[:2])
    return {
        "view_mode": view_mode,
        "read_only": view_mode == "run_snapshot",
        "read_only_reason": _READ_ONLY_REASON if view_mode == "run_snapshot" else None,
        "work": {"work_id": work_id, "title": summary.get("title") or work_id, "overall_status": summary.get("overall_status"), "summary": summary.get("next_action")},
        "active_lineage": lineage,
        "lineage_inferred": bool(lineage.get("lineage_inferred")),
        "viewed_run_id": selected_run_id if view_mode == "run_snapshot" else None,
        "run_strip": _run_strip(work.get("run_history"), lineage, view_mode, selected_run_id),
        "current_conclusion": conclusion,
        "recommended_next_action": actions["primary_action"],
        "workflow_graph": graph,
        "stages": stages,
        "selected_stage": selected,
        "available_actions": actions,
        "action_inventory": _action_inventory(actions, graph),
        "historical_run_summary": _historical_run_summary(
            backend,
            work_id,
            run,
            surface,
            selected_run_id,
            language,
        ) if view_mode == "run_snapshot" else None,
        "empty_state": None if stages else {"title": "No workflow has started yet.", "summary": "Add a requirement to begin."},
        "error_state": None,
        # Compatibility/debug consumers can inspect the provenance without using
        # it to assemble another UI surface.
        "source": {"projection": projection, "surface": surface},
    }


def _historical_run_summary(
    backend: Any,
    work_id: str,
    run: dict[str, Any],
    surface: dict[str, Any],
    run_id: str | None,
    language: str,
) -> dict[str, Any]:
    """Project a task-oriented read-only summary ahead of legacy stage evidence."""

    stages = [item for item in surface.get("stages", []) if isinstance(item, dict)]
    meaningful = [
        item
        for item in stages
        if item.get("status") not in {None, "not_started", "unavailable"}
    ]
    latest = meaningful[-1] if meaningful else (stages[0] if stages else {})
    blocked = next(
        (item for item in reversed(meaningful) if item.get("status") in {"blocked", "failed"}),
        None,
    )
    agent_stage = next(
        (item for item in reversed(meaningful) if _dict_value(item.get("agent_output"))),
        None,
    )
    context = _dict_value(surface.get("workflow_context"))
    prompt = _dict_value(context.get("prompt"))
    preview = _dict_value(prompt.get("preview"))
    prompt_text = preview.get("content") or prompt.get("content") or _read_work_prompt(backend, work_id, run_id)
    if isinstance(prompt_text, dict):
        prompt_text = prompt_text.get("text") or prompt_text.get("prompt")
    raw_status = run.get("status")
    status_value = (
        raw_status.get("status")
        if isinstance(raw_status, dict)
        else raw_status
    )
    artifacts = [
        item
        for item in _dict_value(surface.get("artifact_viewer")).get("artifacts", [])
        if isinstance(item, dict) and item.get("present")
    ]
    model_artifacts = [
        item for item in artifacts
        if item.get("name") in {"model.step", "model.stl", "preview.png", "input_ir.json"}
    ]
    banner = _dict_value((blocked or latest).get("status_banner"))
    return {
        "run_id": run_id,
        "status": status_value or latest.get("status") or "unknown",
        "request": prompt_text,
        "summary": latest.get("human_summary") or latest.get("short_summary") or run.get("summary"),
        "latest_evidence": latest.get("stage_name") or latest.get("label"),
        "agent_output": _dict_value((agent_stage or latest).get("agent_output")),
        "validation": {
            "title": banner.get("title"),
            "summary": banner.get("summary") or latest.get("human_summary"),
            "consequence": banner.get("consequence"),
            "blocked": blocked is not None,
        },
        "model_artifacts": model_artifacts,
        "geometry_viewer_url": (
            f"/web-viewer/index.html?file=%2Fapi%2Fdownloads%2F{run_id}%2Fmodel.stl"
            if run_id and any(item.get("name") == "model.stl" for item in model_artifacts)
            else None
        ),
        "compatibility_evidence_available": bool(stages),
        "read_only": True,
        "legacy_workflow_is_primary": False,
        "title": "历史 Run 摘要" if language == "zh" else "Historical Run summary",
    }


def _with_guidance(stage: dict[str, Any], language: str, view_mode: ViewMode) -> dict[str, Any]:
    """Attach the complete, localized user-guidance contract to every stage."""
    result = dict(stage)
    key = str(result.get("stage_id") or result.get("key") or "")
    catalog = _GUIDANCE.get(key, _GUIDANCE["workflow_review"])
    text = lambda name: catalog[name][1 if language == "zh" else 0]
    status = str(result.get("status") or "not_started")
    blocked = str(result.get("current_block") or "")
    is_snapshot = view_mode == "run_snapshot"
    required = status in {"blocked", "needs_review", "stale"} or key in {"clarification", "part_result_review", "rework"}
    if is_snapshot:
        decision = "此历史 Run 仅供查看；请返回当前 Work 后再做决定。" if language == "zh" else "This historical Run is read-only; return to Current Work before making a decision."
        recovery = "返回当前 Work，或从评审决定创建返工尝试。" if language == "zh" else "Return to Current Work, or create a rework attempt from a review decision."
    else:
        decision, recovery = text("decision"), text("recovery")
    if status in {"contract_complete", "execution_skipped"} and key == "part_modeling":
        conclusion = "CAD IR 已验证；已按 Contract 模式有意跳过 CAD 执行。" if language == "zh" else "CAD IR is validated; CAD execution was intentionally skipped in Contract mode."
        limitations = ["不预期 STEP/STL；这不是错误或阻断。" if language == "zh" else "STEP/STL are not expected; this is not an error or a block."]
    else:
        conclusion = _localized_stage_conclusion(key, status, str(result.get("human_summary") or result.get("short_summary") or ""), language)
        limitations = list(result.get("limitations_summary") or [])
    result["guidance"] = {
        "stage_purpose": text("purpose"),
        "current_conclusion": conclusion,
        "why_this_matters": str(result.get("why_it_matters") or text("purpose")),
        "user_decision_required": required,
        "user_decision_summary": decision,
        "recommended_next_action": text("next"),
        "expected_result": text("expected"),
        "normal_next_stage": _normal_next_stage(key, language),
        "blocked_reason": blocked or None,
        "recovery_action": recovery,
        "limitations": limitations,
    }
    return result


def _localized_stage_conclusion(stage_id: str, status: str, fallback: str, language: str) -> str:
    if language != "zh":
        return fallback
    if status in {"not_started", "ready"}:
        return "此阶段尚未完成，等待满足前置条件后继续。"
    if status == "stale":
        return "上游决定已改变；此阶段的旧结果需要重新检查或生成。"
    if status == "blocked":
        return "此阶段暂时无法继续；请查看阻断原因和恢复操作。"
    conclusions = {
        "requirement": "需求已整理为可供后续工程决策使用的内容。",
        "clarification": "澄清内容已记录到当前需求版本。",
        "planning": "设计路线已确定，可进入装配级拆分。",
        "assembly_plan": "候选零件、参考组件和当前选定零件已明确。",
        "part_request": "已为选定零件建立范围明确的建模任务。",
        "part_review": "零件请求已得到可建模性结论。",
        "reviewed_handoff": "已评审的建模简报已准备好作为 CAD IR 输入。",
        "cad_ir_draft": "结构化几何提案已准备好进行验证。",
        "part_modeling": "已完成当前零件的 CAD IR 验证和建模结果投影。",
        "part_result_review": "单零件结果已具备评审依据，但尚未自动批准。",
        "workflow_review": "当前 Work 的结果、限制和可行下一步已汇总。",
        "rework": "返工将以新的 Run 保存，旧尝试保持不变。",
    }
    return conclusions.get(stage_id, fallback)


def _with_action_guidance(guidance: dict[str, Any], actions: dict[str, Any], language: str) -> dict[str, Any]:
    result = dict(guidance)
    primary = actions.get("primary_action") if isinstance(actions.get("primary_action"), dict) else None
    if primary and primary.get("enabled"):
        result["recommended_next_action"] = primary.get("label") or result["recommended_next_action"]
    elif not primary or not primary.get("enabled"):
        result["recommended_next_action"] = (
            "当前无需执行操作；请按正常工作流继续，或检查可用的恢复操作。"
            if language == "zh" else "No action is available here yet; continue with the normal workflow or inspect the available recovery action."
        )
    return result


def _normal_next_stage(stage_id: str, language: str) -> str:
    names = {
        "requirement": ("Planning", "规划"), "clarification": ("Planning", "规划"), "planning": ("Assembly Plan", "装配计划"),
        "assembly_plan": ("Part Request", "零件请求"), "part_request": ("Part Review", "零件评审"),
        "part_review": ("Reviewed Handoff", "已评审交接"), "reviewed_handoff": ("CAD IR Draft", "CAD IR 草稿"),
        "cad_ir_draft": ("Part Modeling", "零件建模"), "part_modeling": ("Part Result Review", "零件结果评审"),
        "part_result_review": ("Workflow Review", "工作流评审"), "workflow_review": ("Rework or next Part Job", "返工或下一个零件任务"),
        "rework": ("New rework Run", "新的返工 Run"),
    }
    pair = names.get(stage_id, ("Next workflow stage", "下一工作流阶段"))
    return pair[1 if language == "zh" else 0]


def _select_stage(stages: list[dict[str, Any]], requested: str | None, view_mode: ViewMode) -> dict[str, Any] | None:
    if requested:
        found = next((stage for stage in stages if stage.get("stage_id") == requested or stage.get("key") == requested), None)
        if found:
            return found
    if view_mode == "run_snapshot":
        terminal = [stage for stage in stages if stage.get("status") in {"failed", "blocked"}]
        return terminal[0] if terminal else next((stage for stage in reversed(stages) if stage.get("status") != "not_started"), stages[0] if stages else None)
    for status in _SELECTION_PRIORITY:
        found = next((stage for stage in stages if stage.get("status") == status), None)
        if found:
            return found
    meaningful = [stage for stage in stages if stage.get("status") in {"completed", "completed_with_assumptions", "contract_complete", "execution_skipped"} and _first_enabled(stage)]
    if meaningful:
        return meaningful[-1]
    return next((stage for stage in stages if stage.get("status") in {"ready", "not_started"}), stages[-1] if stages else None)


def _workflow_graph(
    raw: Any,
    stages: list[dict[str, Any]],
    selected_id: str | None,
    projection: Any,
    fallback_source: str | None,
    work_id: str,
    view_mode: ViewMode,
    language: str,
) -> dict[str, Any]:
    graph = deepcopy(raw) if isinstance(raw, dict) else {}
    active_plan = (
        projection.get("artifact_contents", {}).get("assembly_plan.json")
        if isinstance(projection, dict) and isinstance(projection.get("artifact_contents"), dict)
        else None
    )
    if isinstance(active_plan, dict) and isinstance(active_plan.get("selected_part_id"), str):
        graph["selected_part_id"] = active_plan["selected_part_id"]
    by_id = {str(stage.get("stage_id") or stage.get("key")): stage for stage in stages}
    unavailable = isinstance(projection, dict) and bool(projection.get("diagnostics"))
    for section in ("stage_spine", "selected_part_pipeline", "review_tail"):
        nodes = graph.get(section) if isinstance(graph.get(section), list) else []
        graph[section] = [_stage_node(node, by_id.get(str(node.get("stage_id"))), selected_id, fallback_source, unavailable) for node in nodes if isinstance(node, dict)]
    candidates = graph.get("part_candidates") if isinstance(graph.get("part_candidates"), list) else []
    selected_candidate = graph.get("selected_part_id")
    candidates = [
        {**item, "selected": item.get("part_id") == selected_candidate, "current": item.get("part_id") == selected_candidate}
        for item in candidates if isinstance(item, dict)
    ]
    graph["part_candidates"] = [_part_node(item, "candidate_part", work_id, fallback_source, view_mode, language) for item in candidates if isinstance(item, dict)]
    references = graph.get("reference_lane") if isinstance(graph.get("reference_lane"), list) else []
    graph["reference_lane"] = [_part_node(item, "reference_component", work_id, fallback_source, view_mode, language) for item in references if isinstance(item, dict)]
    for lane in ("part_candidates", "reference_lane"):
        for candidate in graph.get(lane, []):
            candidate["source_run_id"] = fallback_source
            candidate["current_selected_part_id"] = graph.get("selected_part_id")
    return graph


def _stage_node(node: dict[str, Any], stage: dict[str, Any] | None, selected_id: str | None, fallback_source: str | None, unavailable: bool) -> dict[str, Any]:
    stage = stage or {}
    stage_id = str(node.get("stage_id") or stage.get("stage_id") or stage.get("key") or "unavailable_stage")
    status = "unavailable" if unavailable else str(node.get("status") or stage.get("status") or "unavailable")
    label = str(node.get("label") or stage.get("stage_name") or stage_id.replace("_", " ").title())
    summary = str(node.get("short_summary") or stage.get("short_summary") or "Stage data unavailable")
    result = {
        **node,
        "stage_id": stage_id,
        "label": label,
        "kind": "review" if stage_id == "workflow_review" else ("rework" if stage_id == "rework" else "stage"),
        "status": status,
        "selected": stage_id == selected_id,
        "attention": _ATTENTION.get(status, "none"),
        "clickable": True,
        "source_run_id": stage.get("source_run_id") or fallback_source,
        "source_artifact_count": int(node.get("source_artifact_count") or len(stage.get("raw_artifacts") or [])),
        "short_summary": summary,
    }
    _validate_node(result)
    return result


def _part_node(item: dict[str, Any], kind: str, work_id: str, target_run_id: str | None, view_mode: ViewMode, language: str) -> dict[str, Any]:
    status = str(item.get("status") or ("reference_only" if kind == "reference_component" else "ready"))
    selected = bool(item.get("selected"))
    if status == "selected":
        status = "ready"
    part_id = str(item.get("part_id") or "")
    reference = bool(item.get("reference_only")) or kind == "reference_component"
    selectable = view_mode == "current_work" and bool(item.get("supported_candidate")) and not reference and not selected
    actions = [
        {
            "key": "open_candidate_detail",
            "label": action_label(language, "Open Candidate Detail"),
            "label_i18n": action_labels("Open Candidate Detail"),
            "enabled": bool(part_id),
            "category": "navigation",
            "scope": "run_snapshot" if view_mode == "run_snapshot" else "current_work",
            "target_work_id": work_id,
            "target_run_id": target_run_id,
            "target_stage_id": "assembly_plan",
            "tooltip": (f"查看 {part_id} 的职责、接口和支持状态。\n不会改变当前选择或 Work。" if language == "zh" else f"Inspect {part_id}'s role, interfaces, and support status.\nIt does not change the selected part or Current Work."),
        },
        {
            "key": "select_candidate_part",
            "label": action_label(language, "Use This Part Next"),
            "label_i18n": action_labels("Use This Part Next"),
            "enabled": selectable,
            "category": "structured_input",
            "scope": "run_snapshot" if view_mode == "run_snapshot" else "current_work",
            "target_work_id": work_id,
            "target_run_id": target_run_id,
            "target_stage_id": "assembly_plan",
            "part_id": part_id,
            "requires_confirmation": True,
            "creates_new_run": False,
            "updates_active_lineage": False,
            "disabled_reason": (
                ("历史 Run 快照只读；请返回当前 Work。" if language == "zh" else _READ_ONLY_REASON) if view_mode == "run_snapshot" else
                ("参考组件不能用于生成。" if language == "zh" else "Reference components cannot be selected for generation.") if reference else
                ("该候选零件已被选择，无需重复覆盖。" if language == "zh" else "This candidate is already selected; no duplicate override is needed.") if selected else
                ("当前单零件流程不支持该候选零件。" if language == "zh" else "This candidate is not supported by the current single-part workflow.")
            ) if not selectable else None,
            "tooltip": (f"把 {part_id} 设为接下来的建模对象。\n系统会保存新的装配计划覆盖版本，并将旧的下游结果标记为过期；已有 Run 和已批准结果不会被删除。" if language == "zh" else f"Use {part_id} as the next modeling target.\nCadFlow saves a new Assembly Plan override and marks older downstream results stale; existing Runs and accepted results remain."),
        },
    ]
    return {**item, "kind": kind, "status": status, "selected": selected, "attention": "required" if status == "blocked" else "none", "clickable": True, "actions": actions}


def _validate_node(node: dict[str, Any]) -> None:
    for field in ("stage_id", "label", "status", "short_summary"):
        assert node.get(field), f"workflow graph node requires {field}"


def _stage_detail(stage: dict[str, Any], fallback_source: str | None, view_mode: ViewMode) -> dict[str, Any]:
    detail = dict(stage)
    inputs = [item for item in detail.get("input_artifacts", []) if isinstance(item, dict) and item.get("present")]
    outputs = [item for item in detail.get("output_artifacts", []) if isinstance(item, dict) and item.get("present")]
    source_input = inputs[0] if inputs else {}
    source_output = outputs[0] if outputs else {}
    source_run = detail.get("source_run_id") or source_input.get("source_run_id") or fallback_source
    stage_id = str(detail.get("stage_id") or detail.get("key") or "")
    legacy_status = str(detail.get("status") or "not_started")
    detail.setdefault("execution_status", "skipped" if legacy_status in {"execution_skipped", "skipped"} else legacy_status)
    detail.setdefault(
        "result_status",
        "contract_complete"
        if legacy_status in {"execution_skipped", "contract_complete"}
        else "no_trusted_result"
        if legacy_status in {"failed", "blocked"}
        else "available"
        if legacy_status in {"completed", "completed_with_assumptions"}
        else "not_created",
    )
    detail.setdefault("user_review_status", "not_reviewed")
    input_contracts = [_artifact_contract(item, detail, "input", fallback_source) for item in inputs]
    output_contracts = [_artifact_contract(item, detail, "output", fallback_source) for item in outputs]
    detail.update({
        "stage_id": stage_id,
        "conclusion": {"title": _nested(detail, "status_banner", "title") or detail.get("stage_name"), "summary": _nested(detail, "status_banner", "summary") or detail.get("human_summary") or detail.get("short_summary")},
        "user_input": {
            "summary": _human_input_summary(detail, input_contracts),
            "input_status": detail.get("input_status") or ("accepted_upstream" if input_contracts else "missing"),
            "source_run_id": source_input.get("source_run_id") or source_run,
            "source_stage_id": _input_stage(detail.get("stage_id")),
            "source_type": "active_override" if detail.get("override_present") else "accepted_upstream_output",
            "editable": view_mode == "current_work" and bool(detail.get("override_present")),
            "stale_downstream": bool(detail.get("override_present")),
            "artifacts": input_contracts,
        },
        "agent_decision": {
            "summary": _human_decision_summary(detail),
            "decisions": _human_decisions(detail),
            "assumptions": detail.get("limitations_summary") or [],
            "interventions": [],
        },
        "agent_output": {
            "summary": _human_output_summary(detail, output_contracts),
            "source_run_id": source_output.get("source_run_id") or detail.get("source_run_id") or fallback_source,
            "source_stage_id": detail.get("stage_id"),
            "execution_status": detail.get("execution_status") or detail.get("status"),
            "result_status": detail.get("result_status"),
            "agent_review_status": detail.get("agent_review_status"),
            "user_review_status": detail.get("user_review_status"),
            "validation_status": "passed" if detail.get("result_status") in {"available", "generated", "accepted", "ready_for_review", "contract_complete"} else detail.get("result_status") or detail.get("status"),
            "artifacts": output_contracts,
            "products": [
                item for item in output_contracts
                if item.get("name") in {"model.step", "model.stl"} and item.get("trust_status") in {"reviewable", "accepted"}
            ],
            "step_stl_expectation": "not_expected" if detail.get("status") in {"contract_complete", "execution_skipped"} else "expected",
        },
        "evidence": _evidence_contracts(input_contracts, output_contracts),
    })
    return detail


def _artifact_contract(item: dict[str, Any], detail: dict[str, Any], direction: str, fallback_source: str | None) -> dict[str, Any]:
    """Keep every visible artifact self-describing and directly openable."""
    name = str(item.get("name") or "artifact")
    result_status = str(detail.get("result_status") or "")
    if direction == "input":
        trust_status = str(detail.get("input_status") or "available_unverified")
        artifact_role = (
            "accepted_input"
            if trust_status == "accepted_upstream"
            else "stale_input"
            if trust_status == "stale"
            else "unverified_input"
        )
        validation_status = "passed" if trust_status == "accepted_upstream" else trust_status
    elif name in {"model.step", "model.stl", "preview.png", "model.py"}:
        artifact_role = (
            "final_output"
            if result_status == "accepted"
            else "attempt_output"
            if result_status == "generated"
            else "diagnostic_evidence"
        )
        trust_status = (
            "accepted"
            if result_status == "accepted"
            else "reviewable"
            if result_status == "generated"
            else "untrusted"
        )
        validation_status = "passed" if trust_status in {"accepted", "reviewable"} else result_status or "failed"
    else:
        artifact_role = "diagnostic_evidence" if result_status in {"no_trusted_result", "blocked"} else "stage_output"
        trust_status = "diagnostic" if artifact_role == "diagnostic_evidence" else "validated"
        validation_status = "passed" if trust_status == "validated" else result_status or "available"
    return {
        "name": name,
        "display_name": _artifact_display_name(name),
        "kind": _artifact_kind(name),
        "summary": item.get("summary") or ("Stage output" if direction == "output" else "Stage input"),
        "source_run_id": item.get("source_run_id") or detail.get("source_run_id") or fallback_source,
        "source_stage_id": detail.get("stage_id") or detail.get("key"),
        "relative_path": item.get("source_relative_path") or name,
        "modified_at": item.get("modified_at"),
        "artifact_role": artifact_role,
        "trust_status": trust_status,
        "validation_status": validation_status,
        "source_type": item.get("source_type") or "original",
        "previewable": _artifact_kind(name) in {"json", "markdown", "text", "stl", "step"},
        "downloadable": _artifact_kind(name) in {"step", "stl"} and trust_status in {"reviewable", "accepted"},
        "editable": False,
        "open_action": {"type": "artifact_dialog"},
        "content": item.get("content"),
        "direction": direction,
    }


def _human_input_summary(detail: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    if detail.get("stage_id") == "workflow_review":
        part = detail.get("selected_part_id") or _nested(detail.get("report_summary"), "selected_candidate")
        if not part:
            part = next((
                item.get("content", {}).get("part_id")
                for item in artifacts
                if isinstance(item.get("content"), dict) and isinstance(item["content"].get("part_id"), str)
            ), None)
        part = part or "result"
        return f"The selected {part} result was ready for work-level review."
    if not artifacts:
        return "No accepted upstream input is available for this stage yet."
    names = ", ".join(item["display_name"] for item in artifacts[:2])
    return f"This stage used accepted upstream records: {names}."


def _human_decision_summary(detail: dict[str, Any]) -> str:
    if detail.get("stage_id") == "workflow_review":
        return "CadFlow assessed the available Work lineage and prepared a work-level review conclusion."
    return str(detail.get("human_summary") or detail.get("short_summary") or "No agent interpretation is available.")


def _human_decisions(detail: dict[str, Any]) -> list[Any]:
    if detail.get("stage_id") == "workflow_review":
        decisions = ["The current result is ready for user review."]
        limitations = detail.get("limitations_summary") if isinstance(detail.get("limitations_summary"), list) else []
        decisions.extend(limitations[:2])
        return decisions
    return detail.get("key_decisions_human") or []


def _human_output_summary(detail: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    if detail.get("stage_id") == "workflow_review" and artifacts:
        return "Workflow review created successfully. This is the stage output, not an inherited upstream block."
    if not artifacts:
        return "No stage output is available yet."
    return str(detail.get("short_summary") or "Stage output is available.")


def _evidence_contracts(inputs: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group same-named lineage files without erasing their distinct origins."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in [*outputs, *inputs]:
        grouped.setdefault(str(item.get("name")), []).append(item)
    evidence = []
    for name, items in grouped.items():
        primary = items[0]
        related = items[1:]
        evidence.append({**primary, "related": related, "related_count": len(related)})
    return evidence


def _scoped_actions(stage: dict[str, Any] | None, view_mode: ViewMode, work_id: str, target_run_id: str | None, language: str) -> dict[str, Any]:
    groups = stage.get("action_groups") if isinstance(stage, dict) and isinstance(stage.get("action_groups"), dict) else {}
    actions = [dict(item) for group in groups.values() if isinstance(group, list) for item in group if isinstance(item, dict)]
    prepared = []
    for action in actions:
        backend_action = action.get("backend_action") or ("save_stage_review" if action.get("key") == "save_stage_review" else None)
        if backend_action:
            action["backend_action"] = backend_action
        creates_new_run = backend_action == "run_rework"
        enabled = bool(action.get("enabled"))
        if enabled and not backend_action and not action.get("presentation_action"):
            enabled = False
            action["disabled_reason"] = "This intervention requires structured input and is not available from this compact action yet."
        if view_mode == "run_snapshot" and backend_action and not creates_new_run:
            enabled = False
            action["disabled_reason"] = _READ_ONLY_REASON
        action.update({
            "enabled": enabled,
            "category": "workflow_command" if backend_action else ("navigation" if action.get("presentation_action") else "disabled_future"),
            "scope": "run_snapshot" if view_mode == "run_snapshot" else "current_work",
            "target_work_id": work_id,
            "target_run_id": target_run_id,
            "target_stage_id": stage.get("stage_id") if isinstance(stage, dict) else None,
            "creates_new_run": creates_new_run,
            "updates_active_lineage": creates_new_run,
            "next_stage_on_success": _next_stage_for_action(backend_action or action.get("key"), stage.get("stage_id") if isinstance(stage, dict) else None),
            "expected_postcondition": {
                "next_stage": _next_stage_for_action(backend_action or action.get("key"), stage.get("stage_id") if isinstance(stage, dict) else None),
                "updates_active_lineage": creates_new_run,
            },
        })
        action["label_i18n"] = action_labels(action.get("label"), action.get("key"))
        action["label"] = action["label_i18n"]["zh" if language == "zh" else "en"]
        action["tooltip"] = _action_tooltip(action, stage, language)
        prepared.append(action)
    agent_review = next((action for action in prepared if action.get("enabled") and action.get("key") in _AGENT_REVIEW_ACTIONS), None)
    if agent_review is None and stage is not None:
        agent_review = {
            "key": "create_workflow_review",
            "label": "Refresh agent workflow review",
            "enabled": view_mode == "current_work" and bool(target_run_id),
            "disabled_reason": _READ_ONLY_REASON if view_mode == "run_snapshot" else "Select an active Run first.",
            "backend_action": "create_workflow_review",
            "scope": "run_snapshot" if view_mode == "run_snapshot" else "current_work",
            "target_work_id": work_id,
            "target_run_id": target_run_id,
            "target_stage_id": stage.get("stage_id") if isinstance(stage, dict) else None,
            "category": "workflow_command",
            "creates_new_run": False,
            "updates_active_lineage": False,
            "next_stage_on_success": "workflow_review",
        }
        agent_review["tooltip"] = _action_tooltip(agent_review, stage, language)
    if agent_review is not None:
        agent_review["label"] = _agent_review_label(agent_review, stage)
        agent_review["label_i18n"] = action_labels(agent_review["label"], agent_review.get("key"))
        agent_review["label"] = agent_review["label_i18n"]["zh" if language == "zh" else "en"]
        agent_review["tooltip"] = _action_tooltip(agent_review, stage, language)
    enabled = [action for action in prepared if action.get("enabled") and action.get("key") not in _REVIEW_DECISION_ACTIONS]
    secondary = [action for action in enabled if action is not agent_review]
    disabled = [action for action in prepared if not action.get("enabled")]
    if agent_review is not None and not agent_review.get("enabled"):
        disabled.insert(0, agent_review)
    return {
        "primary_action": agent_review,
        "secondary_actions": secondary,
        "disabled_actions": disabled,
        "advanced_actions": [],
        "review_actions": [action for action in prepared if action.get("key") in _REVIEW_DECISION_ACTIONS],
}


def _agent_review_label(action: dict[str, Any], stage: dict[str, Any] | None) -> str:
    key = str(action.get("key") or "")
    if key == "create_workflow_review":
        return "Refresh agent workflow review"
    if key == "part_result_review":
        return "Request agent result review"
    return "Request agent review"


def _action_tooltip(action: dict[str, Any], stage: dict[str, Any] | None, language: str = "en") -> str:
    """Keep default Hover focused on action, important result, and availability."""
    key = str(action.get("key") or "")
    copy = {
        "save_stage_review": ("Save the selected review decision and notes.", "Writes a traceable stage_review record; does not rerun the agent or modify existing output."),
        "approve_stage": ("Quick approve this stage without notes.", "Records Approved, keeps all artifacts, and updates the Work review state. It does not create CAD."),
        "mark_blocked": ("Record that this stage cannot continue.", "The review form requires a reason and suggested return stage. Existing results are preserved."),
        "mark_needs_revision": ("Request a revision through the stage-review form.", "The saved review records requested changes and can enable a rework run."),
        "create_workflow_review": ("Refresh the work-level review from the current lineage.", "Writes workflow_review artifacts; it does not generate a CAD model."),
        "view_cad_ir_draft": ("Open the selected CAD IR artifact.", "Read-only inspection; no workflow state changes."),
        "edit_assembly_plan": ("Open the assembly plan and its validated override editor.", "Saving an override preserves the original artifact and may mark downstream stages stale."),
        "view_diagnostics": ("Open raw validation and trace diagnostics.", "Read-only troubleshooting; no workflow state changes."),
    }


    action_text, result_text = copy.get(key, ("Run this workflow action.", "The result is recorded against the selected Work and Run."))
    disabled = action.get("disabled_reason")
    if language == "zh":
        action_text = f"执行“{action_label('zh', action.get('label'), key)}”。"
        result_text = "结果会更新当前工作流状态。"
        lines = [action_text, result_text]
        if action.get("creates_new_run"):
            lines.append("这会创建新的 Run。")
        elif action.get("updates_active_lineage"):
            lines.append("这会改变当前 Work。")
        if disabled:
            lines.append(f"当前不可用：{disabled}")
        return "\n".join(lines)
    lines = [action_text, result_text]
    if action.get("creates_new_run"):
        lines.append("This creates a new Run.")
    elif action.get("updates_active_lineage"):
        lines.append("This changes the Current Work.")
    if disabled:
        lines.append(f"Unavailable: {disabled}")
    return "\n".join(lines)


def _action_inventory(actions: dict[str, Any], graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Machine-readable, target-complete inventory for manual cockpit checks."""
    inventory: list[dict[str, Any]] = []
    for group in ("primary_action", "secondary_actions", "disabled_actions"):
        entries = actions.get(group)
        entries = entries if isinstance(entries, list) else [entries]
        for item in entries:
            if isinstance(item, dict):
                inventory.append(dict(item))
    for lane in ("part_candidates", "reference_lane"):
        for candidate in graph.get(lane, []) if isinstance(graph.get(lane), list) else []:
            if isinstance(candidate, dict):
                inventory.extend(dict(item) for item in candidate.get("actions", []) if isinstance(item, dict))
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in inventory:
        key = (item.get("key"), item.get("target_work_id"), item.get("target_run_id"), item.get("target_stage_id"), item.get("part_id"))
        unique[key] = item
    return list(unique.values())


def _run_strip(history: Any, lineage: dict[str, Any], view_mode: ViewMode, viewed_run_id: str | None) -> list[dict[str, Any]]:
    result = []
    for index, item in enumerate(history if isinstance(history, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        run_id = item.get("run_id")
        result.append({
            **item,
            "display_label": f"Run {index}",
            "lineage_state": item.get("lineage_state") or "historical",
            "status": _nested(item, "status", "status") or item.get("status") or "unknown",
            "summary": item.get("summary") or "Immutable workflow attempt.",
            "is_current": item.get("lineage_state") == "active",
            "read_only": view_mode == "run_snapshot" and run_id == viewed_run_id,
        })
    return result


def _conclusion(surface: dict[str, Any], stage: dict[str, Any] | None, summary: dict[str, Any], view_mode: ViewMode) -> dict[str, Any]:
    if view_mode == "run_snapshot":
        return {"title": "Historical Run Snapshot", "summary": "Read-only. This Run does not represent the complete current Work."}
    decision = surface.get("decision_panel") if isinstance(surface.get("decision_panel"), dict) else {}
    status = (stage or {}).get("status")
    if status in {"contract_complete", "execution_skipped"}:
        return {
            "title": "CAD IR contract validated",
            "summary": "input_ir.json was created. CAD execution was intentionally skipped, so STEP/STL are not expected.",
            "rationale": "This is a contract-complete workflow, not a missing-model failure.",
        }
    if decision.get("scope") == "single_generic_concept_part":
        return {
            "title": "Single generic concept part generated",
            "summary": "CadFlow generated and validated upper_link as link_like_part / elongated_plate_with_end_holes. This is not a complete robot-arm assembly.",
            "rationale": "assembly_generated=false · result scope: single_generic_concept_part",
        }
    return {"title": "Current result", "summary": decision.get("decision") or (stage or {}).get("human_summary") or summary.get("next_action") or "Inspect the active Work lineage.", "rationale": decision.get("rationale") or None}


def _first_enabled(stage: dict[str, Any]) -> bool:
    groups = stage.get("action_groups") if isinstance(stage.get("action_groups"), dict) else {}
    return any(item.get("enabled") for group in groups.values() if isinstance(group, list) for item in group if isinstance(item, dict))


def _input_stage(stage_id: Any) -> str | None:
    mapping = {"clarification": "requirement", "planning": "requirement", "assembly_plan": "planning", "part_request": "assembly_plan", "part_review": "part_request", "reviewed_handoff": "part_review", "cad_ir_draft": "reviewed_handoff", "part_modeling": "cad_ir_draft", "part_result_review": "part_modeling", "workflow_review": "part_result_review", "rework": "workflow_review"}
    return mapping.get(str(stage_id))


def _next_stage_for_action(backend_action: Any, stage_id: Any) -> str | None:
    targets = {
        "part_request": "part_review",
        "part_review": "reviewed_handoff",
        "reviewed_handoff": "cad_ir_draft",
        "reviewed_part_create": "part_result_review",
        "part_result_review": "workflow_review",
        "create_workflow_review": "rework",
        "run_rework": "workflow_review",
        "save_stage_review": "workflow_review",
    }
    return targets.get(str(backend_action)) or ("workflow_review" if stage_id == "workflow_review" else None)


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
