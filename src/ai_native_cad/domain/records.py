"""Schema-versioned M1 domain records.

This module deliberately contains no CAD execution, provider, UI, or filesystem
logic.  It defines the manifest-backed product state that the eventual product
orchestrator will own and supplies the compatibility projection for v1 Work
manifests.  Historical Run evidence is referenced, never rewritten.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

WORK_SCHEMA_VERSION = 2
DOMAIN_RECORD_SCHEMA_VERSION = 1
ARTIFACT_REFERENCE_SCHEMA_VERSION = 1

TRUST_ROLES = {
    "accepted_input",
    "candidate",
    "observation",
    "reviewable_result",
    "accepted_result",
    "deliverable",
    "diagnostic",
}
PHASES = {"intent", "design", "build_evaluate", "accept_deliver"}


def create_work_record(
    *,
    work_id: str,
    title: str,
    description: str = "",
    status: str = "incomplete",
    advancement_mode: str = "manual_confirm",
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create an empty canonical Work record without creating a Run."""
    _require_id(work_id, "work_id")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Work title is required")
    if status not in {"incomplete", "active", "paused", "archived"}:
        raise ValueError(f"unsupported Work status: {status}")
    if advancement_mode not in {"manual_confirm", "auto_advance"}:
        raise ValueError(f"unsupported advancement mode: {advancement_mode}")
    now = created_at or _now()
    record = {
        "record_type": "work",
        "schema_version": WORK_SCHEMA_VERSION,
        "work_id": work_id,
        "title": title,
        "description": description,
        "status": status,
        "created_at": now,
        "updated_at": now,
        "root_run_id": None,
        "current_run_id": None,
        "run_ids": [],
        "active_lineage": _empty_active_lineage(),
        "part_jobs": [],
        "accepted_part_results": {},
        "assembly_job": None,
        "deliverable_packages": [],
        "artifact_references": [],
        "candidate_selection": {},
        "requirement": {"status": "not_started", "root_run_id": None},
        "advancement_mode": advancement_mode,
        "metadata": deepcopy(metadata or {}),
    }
    validate_work_record(record)
    return record


def create_artifact_reference(
    *,
    artifact_id: str,
    work_id: str,
    run_id: str,
    relative_path: str,
    phase: str,
    checkpoint: str,
    trust_role: str,
    part_job_id: str | None = None,
    assembly_job_id: str | None = None,
    source_artifact_ids: list[str] | None = None,
    validation_status: str = "not_validated",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create a controlled, path-relative artifact identity."""
    _require_id(artifact_id, "artifact_id", allow_colon=True)
    _require_id(work_id, "work_id")
    _require_id(run_id, "run_id")
    if part_job_id is not None:
        _require_id(part_job_id, "part_job_id")
    if assembly_job_id is not None:
        _require_id(assembly_job_id, "assembly_job_id")
    if phase not in PHASES:
        raise ValueError(f"unsupported artifact phase: {phase}")
    if trust_role not in TRUST_ROLES:
        raise ValueError(f"unsupported artifact trust role: {trust_role}")
    _require_relative_artifact_path(relative_path)
    sources = _unique_ids(source_artifact_ids or [], "source_artifact_ids", allow_colon=True)
    return {
        "record_type": "artifact_reference",
        "schema_version": ARTIFACT_REFERENCE_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "work_id": work_id,
        "run_id": run_id,
        "part_job_id": part_job_id,
        "assembly_job_id": assembly_job_id,
        "phase": phase,
        "checkpoint": _require_text(checkpoint, "checkpoint"),
        "trust_role": trust_role,
        "relative_path": relative_path.replace("\\", "/"),
        "source_artifact_ids": sources,
        "validation_status": _require_text(validation_status, "validation_status"),
        "created_at": created_at or _now(),
    }


def create_assembly_job_record(
    *,
    assembly_job_id: str,
    accepted_part_result_ids: list[str],
    reference_components: list[dict[str, Any]] | None = None,
    intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Define Assembly Job state only; this does not generate an assembly."""
    _require_id(assembly_job_id, "assembly_job_id")
    return {
        "record_type": "assembly_job",
        "schema_version": DOMAIN_RECORD_SCHEMA_VERSION,
        "assembly_job_id": assembly_job_id,
        "intent": deepcopy(intent or {}),
        "accepted_part_result_ids": _unique_ids(
            accepted_part_result_ids, "accepted_part_result_ids", allow_colon=True
        ),
        "reference_components": deepcopy(reference_components or []),
        "attempts": [],
        "active_attempt_run_id": None,
        "accepted_result_id": None,
        "status": "defined",
    }


def create_deliverable_package_record(
    *,
    package_id: str,
    source_accepted_result_ids: list[str],
    artifact_ids: list[str],
    status: str = "defined",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Define a package manifest; no deliverable generation is performed."""
    _require_id(package_id, "package_id", allow_colon=True)
    return {
        "record_type": "deliverable_package",
        "schema_version": DOMAIN_RECORD_SCHEMA_VERSION,
        "package_id": package_id,
        "source_accepted_result_ids": _unique_ids(
            source_accepted_result_ids, "source_accepted_result_ids", allow_colon=True
        ),
        "artifact_ids": _unique_ids(artifact_ids, "artifact_ids", allow_colon=True),
        "status": _require_text(status, "status"),
        "created_at": created_at or _now(),
        "accepted_at": None,
    }


def append_part_attempt(
    work: dict[str, Any],
    *,
    part_job_id: str,
    run_id: str,
    role: str | None = None,
    source: str = "manifest",
    status: str = "incomplete",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Return a new Work record with one ordered Part Job attempt appended."""
    _require_id(part_job_id, "part_job_id")
    _require_id(run_id, "run_id")
    projected = project_work_record(work)
    jobs = projected["part_jobs"]
    job = next((item for item in jobs if item["part_job_id"] == part_job_id), None)
    if job is None:
        job = _new_part_job(part_job_id, role=role, source=source)
        jobs.append(job)
    if any(item["run_id"] == run_id for item in job["attempts"]):
        raise ValueError(f"Part Job attempt already exists: {part_job_id}/{run_id}")
    timestamp = created_at or _now()
    sequence = len(job["attempts"]) + 1
    job["attempts"].append(
        {
            "record_type": "part_job_attempt",
            "schema_version": DOMAIN_RECORD_SCHEMA_VERSION,
            "attempt_id": f"{part_job_id}:{sequence}",
            "sequence": sequence,
            "run_id": run_id,
            "status": status,
            "artifact_ids": [],
            "created_at": timestamp,
        }
    )
    job["active_attempt_run_id"] = run_id
    job["status"] = status
    if role is not None:
        job["role"] = role
    projected["run_ids"] = list(dict.fromkeys([*projected["run_ids"], run_id]))
    projected["updated_at"] = timestamp
    validate_work_record(projected)
    return projected


def begin_work_intent(
    work: dict[str, Any],
    *,
    run_id: str,
    advancement_mode: str,
    confirmation_required: bool,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Bind the first Intent Run to a Work without creating Run evidence."""
    _require_id(run_id, "run_id")
    if advancement_mode not in {"manual_confirm", "auto_advance"}:
        raise ValueError(f"unsupported advancement mode: {advancement_mode}")
    projected = project_work_record(work)
    if projected.get("root_run_id"):
        raise ValueError("Work already has a root Intent Run")
    timestamp = updated_at or _now()
    projected["root_run_id"] = run_id
    projected["current_run_id"] = run_id
    projected["run_ids"] = list(dict.fromkeys([*projected["run_ids"], run_id]))
    projected["active_lineage"] = {
        "active_root_run_id": run_id,
        "active_leaf_run_id": run_id,
        # Compatibility-only legacy view. Canonical acceptance remains in
        # accepted_part_results.
        "accepted_run_ids": [run_id],
        "superseded_run_ids": [],
        "latest_attempt_run_id": run_id,
    }
    projected["status"] = "active"
    projected["advancement_mode"] = advancement_mode
    projected["requirement"] = {
        "status": "needs_confirmation" if confirmation_required else "draft",
        "root_run_id": run_id,
        "prompt_present": True,
        "confirmation_required": confirmation_required,
    }
    projected["updated_at"] = timestamp
    validate_work_record(projected)
    return projected


def advance_active_lineage(
    work: dict[str, Any],
    *,
    parent_run_id: str,
    child_run_id: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Advance mutable design lineage without changing acceptance pointers."""
    _require_id(parent_run_id, "parent_run_id")
    if child_run_id is not None:
        _require_id(child_run_id, "child_run_id")
    projected = project_work_record(work)
    prior = projected.get("active_lineage")
    prior = prior if isinstance(prior, dict) else {}
    legacy_accepted = [
        item for item in prior.get("accepted_run_ids", []) if isinstance(item, str)
    ]
    superseded = [
        item
        for item in prior.get("superseded_run_ids", [])
        if isinstance(item, str)
    ]
    leaf = child_run_id or parent_run_id
    projected["run_ids"] = list(
        dict.fromkeys([*projected["run_ids"], parent_run_id, leaf])
    )
    projected["active_lineage"] = {
        "active_root_run_id": parent_run_id,
        "active_leaf_run_id": leaf,
        "accepted_run_ids": legacy_accepted,
        "superseded_run_ids": superseded,
        "latest_attempt_run_id": leaf,
    }
    projected["current_run_id"] = parent_run_id
    projected["updated_at"] = updated_at or _now()
    validate_work_record(projected)
    return projected


def register_artifact_references(
    work: dict[str, Any],
    references: list[dict[str, Any]],
    *,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Register explicit artifact identities without assigning acceptance."""
    projected = project_work_record(work)
    existing = {
        item["artifact_id"]: item for item in projected["artifact_references"]
    }
    for reference in references:
        if not isinstance(reference, dict):
            raise ValueError("artifact reference must be an object")
        normalized = _project_artifact_references(
            [reference], projected["work_id"]
        )
        if len(normalized) != 1:
            raise ValueError("artifact reference is invalid")
        item = normalized[0]
        prior = existing.get(item["artifact_id"])
        if prior is not None:
            # Retry timestamps are not provenance.  Preserve the first
            # registration when every identity-bearing field is unchanged.
            comparable_prior = {key: value for key, value in prior.items() if key != "created_at"}
            comparable_item = {key: value for key, value in item.items() if key != "created_at"}
            if comparable_prior != comparable_item:
                raise ValueError(
                    f"artifact id already has different provenance: {item['artifact_id']}"
                )
            item = prior
        existing[item["artifact_id"]] = item
    projected["artifact_references"] = list(existing.values())
    if references:
        projected["updated_at"] = updated_at or _now()
    validate_work_record(projected)
    return projected


def record_candidate_selection(
    work: dict[str, Any],
    selection: dict[str, Any],
    *,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Record the Work-level candidate pointer without rewriting Run evidence."""
    if not isinstance(selection, dict):
        raise ValueError("candidate selection must be an object")
    selected_candidate = selection.get("selected_candidate")
    _require_id(selected_candidate, "selected_candidate")
    projected = project_work_record(work)
    projected["candidate_selection"] = deepcopy(selection)
    projected["updated_at"] = (
        updated_at
        or (
            selection.get("created_at")
            if isinstance(selection.get("created_at"), str)
            else None
        )
        or _now()
    )
    validate_work_record(projected)
    return projected


def accept_part_result(
    work: dict[str, Any],
    *,
    part_job_id: str,
    result_id: str,
    attempt_run_id: str,
    result_run_id: str,
    review_id: str,
    artifact_ids: list[str] | None = None,
    accepted_at: str | None = None,
) -> dict[str, Any]:
    """Update only the explicit accepted-result pointer for one Part Job."""
    _require_id(part_job_id, "part_job_id")
    _require_id(result_id, "result_id", allow_colon=True)
    _require_id(attempt_run_id, "attempt_run_id")
    _require_id(result_run_id, "result_run_id")
    _require_id(review_id, "review_id")
    projected = project_work_record(work)
    job = next(
        (item for item in projected["part_jobs"] if item["part_job_id"] == part_job_id),
        None,
    )
    if job is None or attempt_run_id not in {item["run_id"] for item in job["attempts"]}:
        raise ValueError("accepted result must reference an existing Part Job attempt")
    known_artifacts = {item["artifact_id"] for item in projected["artifact_references"]}
    selected_artifacts = _unique_ids(artifact_ids or [], "artifact_ids", allow_colon=True)
    unknown = [artifact_id for artifact_id in selected_artifacts if artifact_id not in known_artifacts]
    if unknown:
        raise ValueError(f"accepted result references unknown artifacts: {unknown}")
    timestamp = accepted_at or _now()
    pointer = {
        "record_type": "accepted_part_result",
        "schema_version": DOMAIN_RECORD_SCHEMA_VERSION,
        "result_id": result_id,
        "part_job_id": part_job_id,
        "attempt_run_id": attempt_run_id,
        "run_id": result_run_id,
        "child_run_id": result_run_id,
        "review_id": review_id,
        "artifact_ids": selected_artifacts,
        "status": "approved",
        "accepted_at": timestamp,
    }
    projected["accepted_part_results"][part_job_id] = pointer
    job["accepted_result_id"] = result_id
    job["status"] = "accepted"
    projected["updated_at"] = timestamp
    validate_work_record(projected)
    return projected


def project_work_record(value: dict[str, Any]) -> dict[str, Any]:
    """Project v1 or v2 Work data to the canonical v2 in-memory contract.

    The projection is deterministic and does not inspect Run directories or
    artifact filenames.  It may be persisted by a later Work mutation, but the
    legacy Run evidence it references is never modified.
    """
    if not isinstance(value, dict):
        raise ValueError("Work record must be an object")
    source_schema_version = value.get("schema_version")
    if source_schema_version not in {None, 1, WORK_SCHEMA_VERSION}:
        raise ValueError(
            f"unsupported Work schema version: {source_schema_version}"
        )
    work_id = value.get("work_id")
    title = value.get("title")
    _require_id(work_id, "work_id")
    if not isinstance(title, str) or not title:
        raise ValueError("Work title is required")
    projected = deepcopy(value)
    projected["record_type"] = "work"
    projected["schema_version"] = WORK_SCHEMA_VERSION
    projected["run_ids"] = _unique_ids(value.get("run_ids") or [], "run_ids")
    projected["active_lineage"] = _project_active_lineage(value.get("active_lineage"))
    projected["artifact_references"] = _project_artifact_references(
        value.get("artifact_references"), work_id
    )
    projected["part_jobs"] = _project_part_jobs(value.get("part_jobs"))
    projected["accepted_part_results"] = _project_accepted_part_results(
        value.get("accepted_part_results")
    )

    jobs_by_id = {item["part_job_id"]: item for item in projected["part_jobs"]}
    for part_job_id, pointer in projected["accepted_part_results"].items():
        job = jobs_by_id.get(part_job_id)
        if job is None:
            job = _new_part_job(part_job_id, role=None, source="legacy_acceptance")
            projected["part_jobs"].append(job)
            jobs_by_id[part_job_id] = job
        attempt_run_id = pointer["attempt_run_id"]
        if (
            attempt_run_id
            and attempt_run_id in projected["run_ids"]
            and attempt_run_id not in {item["run_id"] for item in job["attempts"]}
        ):
            job["attempts"].append(
                {
                    "record_type": "part_job_attempt",
                    "schema_version": DOMAIN_RECORD_SCHEMA_VERSION,
                    "attempt_id": f"{part_job_id}:{len(job['attempts']) + 1}",
                    "sequence": len(job["attempts"]) + 1,
                    "run_id": attempt_run_id,
                    "status": "legacy",
                    "artifact_ids": [],
                    "created_at": None,
                }
            )
        job["accepted_result_id"] = pointer["result_id"]
        if pointer["status"] == "approved":
            job["status"] = "accepted"

    projected["assembly_job"] = _project_assembly_job(value.get("assembly_job"))
    projected["deliverable_packages"] = _project_deliverable_packages(
        value.get("deliverable_packages")
    )
    projected.setdefault("candidate_selection", {})
    projected.setdefault("requirement", {"status": "not_started", "root_run_id": None})
    projected.setdefault("advancement_mode", "manual_confirm")
    projected.setdefault("metadata", {})
    projected.setdefault("root_run_id", None)
    projected.setdefault("current_run_id", None)
    projected.setdefault("created_at", None)
    projected.setdefault("updated_at", None)
    projected.setdefault("description", "")
    projected.setdefault("status", "incomplete")
    validate_work_record(projected)
    return projected


def project_product_state(work: dict[str, Any]) -> dict[str, Any]:
    """Resolve product state exclusively from manifest ids and references."""
    projected = project_work_record(work)
    artifacts = {item["artifact_id"]: item for item in projected["artifact_references"]}
    accepted_results = list(projected["accepted_part_results"].values())
    accepted_artifact_ids = list(
        dict.fromkeys(
            artifact_id
            for result in accepted_results
            for artifact_id in result.get("artifact_ids", [])
            if artifact_id in artifacts
        )
    )
    packages = projected["deliverable_packages"]
    package_artifact_ids = list(
        dict.fromkeys(
            artifact_id
            for package in packages
            if package.get("status") in {"ready", "accepted"}
            for artifact_id in package.get("artifact_ids", [])
            if artifact_id in artifacts
        )
    )
    return {
        "schema_version": DOMAIN_RECORD_SCHEMA_VERSION,
        "work_id": projected["work_id"],
        "accepted_part_result_ids": [item["result_id"] for item in accepted_results],
        "accepted_artifacts": [artifacts[item] for item in accepted_artifact_ids],
        "deliverable_artifacts": [artifacts[item] for item in package_artifact_ids],
        "assembly_status": (
            projected["assembly_job"].get("status")
            if isinstance(projected.get("assembly_job"), dict)
            else "not_defined"
        ),
        "state_source": "work_manifest_artifact_references",
    }


def validate_work_record(work: dict[str, Any]) -> None:
    """Validate cross-record identity and pointer invariants."""
    if work.get("schema_version") != WORK_SCHEMA_VERSION:
        raise ValueError(f"unsupported Work schema version: {work.get('schema_version')}")
    _require_id(work.get("work_id"), "work_id")
    if work.get("record_type") != "work":
        raise ValueError("Work record_type must be 'work'")
    run_ids = _unique_ids(work.get("run_ids") or [], "run_ids")
    artifact_ids = [item.get("artifact_id") for item in work.get("artifact_references", [])]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("artifact ids must be unique within a Work")
    jobs = work.get("part_jobs")
    if not isinstance(jobs, list):
        raise ValueError("part_jobs must be a list")
    job_ids = [item.get("part_job_id") for item in jobs]
    if len(job_ids) != len(set(job_ids)):
        raise ValueError("Part Job ids must be unique within a Work")
    for job in jobs:
        _validate_part_job(job)
        for attempt in job["attempts"]:
            if attempt["run_id"] not in run_ids:
                raise ValueError("Part Job attempt Run must be present in Work run_ids")
    accepted = work.get("accepted_part_results")
    if not isinstance(accepted, dict):
        raise ValueError("accepted_part_results must be an object")
    known_jobs = set(job_ids)
    accepted_result_ids = set()
    known_artifact_ids = set(artifact_ids)
    for part_job_id, pointer in accepted.items():
        if part_job_id not in known_jobs:
            raise ValueError("accepted part result must reference a Part Job")
        if pointer.get("part_job_id") != part_job_id:
            raise ValueError("accepted part result key and part_job_id must match")
        _require_id(pointer.get("result_id"), "result_id", allow_colon=True)
        accepted_result_ids.add(pointer["result_id"])
        _require_id(pointer.get("attempt_run_id"), "attempt_run_id")
        _require_id(pointer.get("run_id"), "result run_id")
        pointer_artifact_ids = _unique_ids(
            pointer.get("artifact_ids") or [],
            "accepted artifact_ids",
            allow_colon=True,
        )
        if not set(pointer_artifact_ids).issubset(known_artifact_ids):
            raise ValueError("accepted result references unknown artifact ids")
    assembly_job = work.get("assembly_job")
    if isinstance(assembly_job, dict):
        assembly_inputs = _unique_ids(
            assembly_job.get("accepted_part_result_ids") or [],
            "accepted_part_result_ids",
            allow_colon=True,
        )
        if not set(assembly_inputs).issubset(accepted_result_ids):
            raise ValueError("Assembly Job references an unaccepted part result")
    packages = work.get("deliverable_packages")
    if not isinstance(packages, list):
        raise ValueError("deliverable_packages must be a list")
    for package in packages:
        source_results = _unique_ids(
            package.get("source_accepted_result_ids") or [],
            "source_accepted_result_ids",
            allow_colon=True,
        )
        package_artifact_ids = _unique_ids(
            package.get("artifact_ids") or [],
            "package artifact_ids",
            allow_colon=True,
        )
        if not set(source_results).issubset(accepted_result_ids):
            raise ValueError("Deliverable Package references an unaccepted result")
        if not set(package_artifact_ids).issubset(known_artifact_ids):
            raise ValueError("Deliverable Package references unknown artifact ids")
    lineage = work.get("active_lineage")
    if not isinstance(lineage, dict):
        raise ValueError("active_lineage must be an object")
    # Acceptance belongs only to accepted_part_results.  The compatibility key
    # may remain for old views, but new acceptance code never mutates it.
    for key in ("active_root_run_id", "active_leaf_run_id", "latest_attempt_run_id"):
        value = lineage.get(key)
        if value is not None:
            _require_id(value, f"active_lineage.{key}")


def _new_part_job(part_job_id: str, *, role: str | None, source: str) -> dict[str, Any]:
    return {
        "record_type": "part_job",
        "schema_version": DOMAIN_RECORD_SCHEMA_VERSION,
        "part_job_id": part_job_id,
        "part_id": part_job_id,
        "role": role,
        "status": "planned",
        "source": source,
        "interface_context": {},
        "attempts": [],
        "active_attempt_run_id": None,
        "accepted_result_id": None,
        "stale_dependencies": [],
    }


def _project_part_jobs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    jobs: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        part_job_id = raw.get("part_job_id") or raw.get("part_id")
        try:
            _require_id(part_job_id, "part_job_id")
        except ValueError:
            continue
        job = _new_part_job(
            part_job_id,
            role=raw.get("role") if isinstance(raw.get("role"), str) else None,
            source=raw.get("source") if isinstance(raw.get("source"), str) else "manifest",
        )
        job["status"] = raw.get("status") if isinstance(raw.get("status"), str) else "planned"
        job["interface_context"] = deepcopy(
            raw.get("interface_context") if isinstance(raw.get("interface_context"), dict) else {}
        )
        job["stale_dependencies"] = deepcopy(
            raw.get("stale_dependencies") if isinstance(raw.get("stale_dependencies"), list) else []
        )
        attempts = raw.get("attempts") if isinstance(raw.get("attempts"), list) else []
        legacy_run_id = raw.get("run_id")
        if not attempts and isinstance(legacy_run_id, str) and legacy_run_id:
            attempts = [{"run_id": legacy_run_id, "status": raw.get("status") or "legacy"}]
        for index, attempt in enumerate(attempts, start=1):
            if not isinstance(attempt, dict):
                continue
            run_id = attempt.get("run_id")
            try:
                _require_id(run_id, "attempt run_id")
            except ValueError:
                continue
            job["attempts"].append(
                {
                    "record_type": "part_job_attempt",
                    "schema_version": DOMAIN_RECORD_SCHEMA_VERSION,
                    "attempt_id": (
                        attempt.get("attempt_id")
                        if isinstance(attempt.get("attempt_id"), str)
                        else f"{part_job_id}:{index}"
                    ),
                    "sequence": index,
                    "run_id": run_id,
                    "status": (
                        attempt.get("status")
                        if isinstance(attempt.get("status"), str)
                        else "legacy"
                    ),
                    "artifact_ids": _unique_ids(
                        attempt.get("artifact_ids") or [],
                        "attempt artifact_ids",
                        allow_colon=True,
                    ),
                    "created_at": (
                        attempt.get("created_at")
                        if isinstance(attempt.get("created_at"), str)
                        else None
                    ),
                }
            )
        active = raw.get("active_attempt_run_id")
        attempt_ids = [item["run_id"] for item in job["attempts"]]
        job["active_attempt_run_id"] = (
            active if isinstance(active, str) and active in attempt_ids else (attempt_ids[-1] if attempt_ids else None)
        )
        job["accepted_result_id"] = (
            raw.get("accepted_result_id")
            if isinstance(raw.get("accepted_result_id"), str)
            else None
        )
        jobs.append(job)
    return jobs


def _project_accepted_part_results(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    results: dict[str, dict[str, Any]] = {}
    for part_job_id, raw in value.items():
        if not isinstance(raw, dict):
            continue
        try:
            _require_id(part_job_id, "part_job_id")
        except ValueError:
            continue
        result_run_id = raw.get("run_id") or raw.get("child_run_id")
        attempt_run_id = raw.get("attempt_run_id") or raw.get("parent_run_id") or result_run_id
        review_id = raw.get("review_id")
        if not all(isinstance(item, str) and item for item in (result_run_id, attempt_run_id, review_id)):
            continue
        result_id = raw.get("result_id")
        if not isinstance(result_id, str) or not result_id:
            result_id = f"legacy:{part_job_id}:{result_run_id}:{review_id}"
        results[part_job_id] = {
            "record_type": "accepted_part_result",
            "schema_version": DOMAIN_RECORD_SCHEMA_VERSION,
            "result_id": result_id,
            "part_job_id": part_job_id,
            "attempt_run_id": attempt_run_id,
            "run_id": result_run_id,
            "child_run_id": result_run_id,
            "review_id": review_id,
            "artifact_ids": _unique_ids(
                raw.get("artifact_ids") or [], "accepted artifact_ids", allow_colon=True
            ),
            "status": "approved" if raw.get("status") in {"approved", "accepted"} else str(raw.get("status") or "approved"),
            "accepted_at": raw.get("accepted_at") if isinstance(raw.get("accepted_at"), str) else None,
        }
    return results


def _project_artifact_references(value: Any, work_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    references = []
    for raw in value:
        if not isinstance(raw, dict) or raw.get("work_id") not in {None, work_id}:
            continue
        try:
            reference = create_artifact_reference(
                artifact_id=raw["artifact_id"],
                work_id=work_id,
                run_id=raw["run_id"],
                relative_path=raw["relative_path"],
                phase=raw["phase"],
                checkpoint=raw["checkpoint"],
                trust_role=raw["trust_role"],
                part_job_id=raw.get("part_job_id"),
                assembly_job_id=raw.get("assembly_job_id"),
                source_artifact_ids=raw.get("source_artifact_ids") or [],
                validation_status=raw.get("validation_status") or "not_validated",
                created_at=raw.get("created_at"),
            )
        except (KeyError, ValueError):
            continue
        references.append(reference)
    return references


def _project_assembly_job(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    assembly_job_id = value.get("assembly_job_id")
    try:
        _require_id(assembly_job_id, "assembly_job_id")
    except ValueError:
        return None
    projected = create_assembly_job_record(
        assembly_job_id=assembly_job_id,
        accepted_part_result_ids=value.get("accepted_part_result_ids") or [],
        reference_components=value.get("reference_components") or [],
        intent=value.get("intent") or {},
    )
    projected["attempts"] = deepcopy(value.get("attempts") or [])
    projected["active_attempt_run_id"] = value.get("active_attempt_run_id")
    projected["accepted_result_id"] = value.get("accepted_result_id")
    projected["status"] = value.get("status") or "defined"
    return projected


def _project_deliverable_packages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    packages = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        try:
            package = create_deliverable_package_record(
                package_id=raw["package_id"],
                source_accepted_result_ids=raw.get("source_accepted_result_ids") or [],
                artifact_ids=raw.get("artifact_ids") or [],
                status=raw.get("status") or "defined",
                created_at=raw.get("created_at"),
            )
        except (KeyError, ValueError):
            continue
        package["accepted_at"] = raw.get("accepted_at")
        packages.append(package)
    return packages


def _project_active_lineage(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    result = _empty_active_lineage()
    for key in ("active_root_run_id", "active_leaf_run_id", "latest_attempt_run_id"):
        item = raw.get(key)
        result[key] = item if isinstance(item, str) and item else None
    result["superseded_run_ids"] = _unique_ids(
        raw.get("superseded_run_ids") or [], "superseded_run_ids"
    )
    # Read-only compatibility for old views.  This is not an acceptance pointer.
    result["accepted_run_ids"] = _unique_ids(
        raw.get("accepted_run_ids") or [], "legacy accepted_run_ids"
    )
    return result


def _empty_active_lineage() -> dict[str, Any]:
    return {
        "active_root_run_id": None,
        "active_leaf_run_id": None,
        "latest_attempt_run_id": None,
        "superseded_run_ids": [],
        "accepted_run_ids": [],
    }


def _validate_part_job(job: dict[str, Any]) -> None:
    if job.get("record_type") != "part_job":
        raise ValueError("Part Job record_type must be 'part_job'")
    if job.get("schema_version") != DOMAIN_RECORD_SCHEMA_VERSION:
        raise ValueError("unsupported Part Job schema version")
    _require_id(job.get("part_job_id"), "part_job_id")
    attempts = job.get("attempts")
    if not isinstance(attempts, list):
        raise ValueError("Part Job attempts must be a list")
    run_ids = []
    for index, attempt in enumerate(attempts, start=1):
        if attempt.get("record_type") != "part_job_attempt":
            raise ValueError("attempt record_type must be 'part_job_attempt'")
        if attempt.get("sequence") != index:
            raise ValueError("Part Job attempt sequence must be ordered and contiguous")
        _require_id(attempt.get("run_id"), "attempt run_id")
        run_ids.append(attempt["run_id"])
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Part Job attempt Run ids must be unique")
    active = job.get("active_attempt_run_id")
    if active is not None and active not in run_ids:
        raise ValueError("active Part Job attempt must reference attempt history")


def _unique_ids(values: Any, label: str, *, allow_colon: bool = False) -> list[str]:
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list")
    result = []
    for value in values:
        _require_id(value, label, allow_colon=allow_colon)
        if value not in result:
            result.append(value)
    return result


def _require_id(value: Any, label: str, *, allow_colon: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required")
    forbidden = {"/", "\\", "\x00"}
    if not allow_colon:
        forbidden.add(":")
    if value in {".", ".."} or any(marker in value for marker in forbidden):
        raise ValueError(f"{label} must be a safe id")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value


def _require_relative_artifact_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("relative_path is required")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("relative_path must be a controlled relative path")
    return normalized


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
