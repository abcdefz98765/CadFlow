"""Single product orchestrator for Work mutations and controlled publication.

This runtime coordinates deterministic compatibility and the bounded Agent
Design port. Untrusted model programs can execute only behind that port's
CadFlow-owned Tool Broker and publication gate.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ai_native_cad.domain.records import (
    accept_part_result,
    advance_active_lineage,
    append_part_attempt,
    begin_work_intent,
    create_artifact_reference,
    project_product_state,
    record_candidate_selection,
    register_artifact_references,
)
from ai_native_cad.orchestration.ports import (
    AgentDesignPort,
    DesignPartEpisodeOutcome,
    DesignPartEpisodeRequest,
    DeterministicCompatibilityPort,
    WorkStorePort,
)


class WorkOrchestrator:
    """Sole target-product coordinator for the four user phases in M1."""

    def __init__(
        self,
        store: WorkStorePort,
        deterministic: DeterministicCompatibilityPort,
        design: AgentDesignPort | None = None,
    ) -> None:
        self.store = store
        self.deterministic = deterministic
        self.design = design

    def create_work(
        self,
        *,
        title: str,
        description: str | None = None,
        work_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.store.create_work(
            title=title,
            description=description,
            work_id=work_id,
            metadata=metadata,
        )
        self.store.invalidate_projection()
        return {
            **result,
            "orchestration": _completion(
                command="create_work",
                phase="intent",
                checkpoint="work_definition",
                postcondition="Work manifest v2 was persisted without creating a Run.",
                next_action="Begin Intent",
            ),
        }

    def begin_intent(
        self,
        work_id: str,
        prompt: str,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        prompt_text = _require_prompt(prompt)
        work = self.store.read_work(work_id)
        config = self.deterministic.workspace_config()
        advancement_mode = config.get("advancement_mode", "manual_confirm")
        if run_id is None:
            run_id = self.store.next_run_id(work_id, f"{work_id}_root")
        candidate = begin_work_intent(
            work,
            run_id=run_id,
            advancement_mode=advancement_mode,
            confirmation_required=advancement_mode == "manual_confirm",
            updated_at=_now(),
        )

        created = self.deterministic.create_run(
            work_id=work_id,
            run_id=run_id,
            prompt=prompt_text,
        )
        stages: list[dict[str, Any]] = []
        auto_blocked = False
        if advancement_mode == "auto_advance":
            for stage in ("requirement", "planning"):
                try:
                    stage_result = self.deterministic.run_stage(
                        work_id=work_id,
                        run_id=run_id,
                        stage=stage,
                    )
                except Exception as exc:
                    stages.append(
                        {
                            "stage": stage,
                            "status": "blocked",
                            "error": type(exc).__name__,
                        }
                    )
                    auto_blocked = True
                    break
                stage_status = stage_result["result"].get("stage_status")
                stages.append(
                    {
                        "stage": stage,
                        "status": stage_status,
                    }
                )
                if not _stage_succeeded(stage_status):
                    auto_blocked = True
                    break
            candidate["requirement"]["status"] = (
                "blocked" if auto_blocked or len(stages) != 2 else "confirmed"
            )
            candidate["requirement"]["confirmation_required"] = False

        self.store.write_work(work_id, candidate)
        if advancement_mode == "auto_advance" and not auto_blocked and len(stages) == 2:
            try:
                part_runs = self.create_planned_part_attempts(
                    work_id,
                    auto_only=True,
                )
            except ValueError as exc:
                auto_blocked = True
                candidate = self.store.read_work(work_id)
                candidate["requirement"]["status"] = "blocked"
                self.store.write_work(work_id, candidate)
                part_runs = {
                    "part_jobs": candidate.get("part_jobs") or [],
                    "created_runs": [],
                    "status": "blocked",
                    "error": type(exc).__name__,
                }
        else:
            part_runs = {
                "part_jobs": candidate.get("part_jobs") or [],
                "created_runs": [],
                **({"status": "blocked"} if auto_blocked else {}),
            }
        self.store.invalidate_projection()
        return {
            "work": self.store.work_detail(work_id),
            "run": created["run"],
            "stages": stages,
            "part_runs": part_runs,
            "orchestration": _completion(
                command="begin_intent",
                phase="intent",
                checkpoint="intent_snapshot",
                status="blocked" if auto_blocked else "completed",
                postcondition=f"Intent Run {run_id} is referenced by Work {work_id}.",
                next_action=(
                    "Confirm requirement"
                    if advancement_mode == "manual_confirm"
                    else (
                        "Inspect deterministic stage diagnostics and retry"
                        if auto_blocked
                        else "Review deterministic planning result"
                    )
                ),
            ),
        }

    def create_planned_part_attempts(
        self,
        work_id: str,
        *,
        auto_only: bool = False,
    ) -> dict[str, Any]:
        config = self.deterministic.workspace_config()
        if auto_only and config.get("advancement_mode") != "auto_advance":
            return {
                "part_jobs": [],
                "created_runs": [],
                "orchestration": _completion(
                    command="create_planned_part_attempts",
                    phase="design",
                    checkpoint="part_job_definition",
                    postcondition="No attempts were created in manual-confirm mode.",
                    next_action="Confirm the split before creating Part Job attempts",
                ),
            }
        work = self.store.read_work(work_id)
        root_run_id = work.get("root_run_id")
        if not isinstance(root_run_id, str) or not root_run_id:
            raise ValueError("Work must have a root Intent Run before creating Part Job attempts")
        planned_parts = self.deterministic.planned_parts(
            work_id=work_id,
            root_run_id=root_run_id,
        )
        if not planned_parts:
            raise ValueError("Work has no planned parts to create attempts for")

        existing = {
            item["part_job_id"]: item
            for item in work.get("part_jobs", [])
            if isinstance(item, dict) and isinstance(item.get("part_job_id"), str)
        }
        created_runs = []
        for part in planned_parts:
            part_job_id = part["part_id"]
            job = existing.get(part_job_id)
            if job and job.get("active_attempt_run_id"):
                continue
            created = self.create_part_attempt(
                work_id,
                part_job_id,
                role=part.get("role"),
                source="assembly_plan",
                prompt=f"Create part '{part_job_id}' for Work '{work_id}'.",
            )
            created_runs.append(created["run"])
            work = self.store.read_work(work_id)
            existing = {
                item["part_job_id"]: item
                for item in work.get("part_jobs", [])
                if isinstance(item, dict)
                and isinstance(item.get("part_job_id"), str)
            }
        self.store.invalidate_projection()
        latest = self.store.read_work(work_id)
        return {
            "part_jobs": latest["part_jobs"],
            "created_runs": created_runs,
            "orchestration": _completion(
                command="create_planned_part_attempts",
                phase="design",
                checkpoint="part_job_definition",
                postcondition=f"Created {len(created_runs)} initial Part Job attempt(s).",
                next_action=(
                    "Open a Part Job attempt"
                    if created_runs
                    else "All planned Part Jobs already have an attempt"
                ),
            ),
        }

    def create_part_attempt(
        self,
        work_id: str,
        part_job_id: str,
        *,
        prompt: str | None = None,
        role: str | None = None,
        source: str = "user_revision",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        work = self.store.read_work(work_id)
        if run_id is None:
            run_id = self.store.next_run_id(
                work_id, f"{work_id}_{part_job_id}"
            )
        prompt_text = _require_prompt(
            prompt or f"Create another attempt for part '{part_job_id}' in Work '{work_id}'."
        )
        candidate = append_part_attempt(
            work,
            part_job_id=part_job_id,
            run_id=run_id,
            role=role,
            source=source,
            status="incomplete",
            created_at=_now(),
        )
        lineage = candidate.get("active_lineage")
        if isinstance(lineage, dict):
            lineage["latest_attempt_run_id"] = run_id

        created = self.deterministic.create_run(
            work_id=work_id,
            run_id=run_id,
            prompt=prompt_text,
        )
        self.store.write_work(work_id, candidate)
        self.store.invalidate_projection()
        job = next(
            item
            for item in candidate["part_jobs"]
            if item["part_job_id"] == part_job_id
        )
        return {
            "part_job": job,
            "run": created["run"],
            "orchestration": _completion(
                command="create_part_attempt",
                phase="design",
                checkpoint="part_job_attempt",
                postcondition=(
                    f"Attempt {run_id} was appended to Part Job {part_job_id}; "
                    "the accepted result was unchanged."
                ),
                next_action="Build and evaluate this attempt",
            ),
        }

    def run_part_design_episode(
        self,
        work_id: str,
        part_job_id: str,
        *,
        request_id: str,
        attempt_run_id: str | None = None,
        objective: str | None = None,
    ) -> dict[str, Any]:
        """Append one Design Episode and register only controlled evidence."""

        if self.design is None:
            raise ValueError("Agent Design port is unavailable")
        work = self.store.read_work(work_id)
        job = next(
            (
                item
                for item in work.get("part_jobs", [])
                if isinstance(item, dict)
                and item.get("part_job_id") == part_job_id
            ),
            None,
        )
        if job is None:
            raise ValueError(f"Work has no Part Job: {part_job_id}")
        run_id = attempt_run_id or job.get("active_attempt_run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("Part Job has no active attempt Run")
        attempt_run_ids = {
            item.get("run_id")
            for item in job.get("attempts", [])
            if isinstance(item, dict)
        }
        if run_id not in attempt_run_ids:
            raise ValueError("Design Episode must target an owned Part Job attempt")
        design_objective = objective or work.get("description") or (
            f"Design Part Job '{part_job_id}' for Work '{work_id}'."
        )
        request = DesignPartEpisodeRequest(
            request_id=request_id,
            work_id=work_id,
            run_id=run_id,
            part_job_id=part_job_id,
            objective=design_objective,
            role=job.get("role") if isinstance(job.get("role"), str) else None,
            interface_context=deepcopy(
                job.get("interface_context")
                if isinstance(job.get("interface_context"), dict)
                else {}
            ),
            accepted_result_id=(
                job.get("accepted_result_id")
                if isinstance(job.get("accepted_result_id"), str)
                else None
            ),
        )
        protected_before = _protected_work_state(work)
        outcome = self.design.run_part_design_episode(request)
        if not outcome.artifacts:
            raise RuntimeError("Agent Design port returned no durable Run evidence")
        _validate_design_outcome(request, outcome, work)

        timestamp = _now()
        references = [
            create_artifact_reference(
                artifact_id=artifact.artifact_id,
                work_id=work_id,
                run_id=run_id,
                part_job_id=part_job_id,
                relative_path=artifact.relative_path,
                phase=_design_artifact_phase(artifact),
                checkpoint=artifact.checkpoint,
                trust_role=artifact.trust_role,
                source_artifact_ids=list(artifact.source_artifact_ids),
                validation_status=artifact.validation_status,
                created_at=timestamp,
            )
            for artifact in outcome.artifacts
        ]
        registered = register_artifact_references(
            work,
            references,
            updated_at=timestamp,
        )
        if _protected_work_state(registered) != protected_before:
            raise RuntimeError(
                "Design Episode routing attempted to mutate protected Work state"
            )
        existing_ids = {
            item.get("artifact_id")
            for item in work.get("artifact_references", [])
            if isinstance(item, dict)
        }
        new_ids = {
            reference["artifact_id"]
            for reference in references
            if reference["artifact_id"] not in existing_ids
        }
        persisted = registered if new_ids else work
        if new_ids:
            self.store.write_work(work_id, persisted)
            self.store.invalidate_projection()
        persisted_by_id = {
            item["artifact_id"]: item
            for item in persisted.get("artifact_references", [])
            if isinstance(item, dict) and isinstance(item.get("artifact_id"), str)
        }
        persisted_references = [
            persisted_by_id[reference["artifact_id"]]
            for reference in references
        ]
        status = "completed" if outcome.status == "completed" else "blocked"
        if outcome.idempotent_replay:
            postcondition = (
                f"Design Episode request {request_id} returned its existing "
                "append-only evidence without another provider call or Work mutation."
            )
        elif outcome.reviewable_result_id:
            postcondition = (
                f"Reviewable STEP {outcome.reviewable_result_id} for "
                f"{part_job_id} was published from locally validated evidence "
                f"in Run {run_id}; acceptance and deliverables were unchanged."
            )
        elif outcome.validated:
            postcondition = (
                f"A validated contract candidate for {part_job_id} was appended "
                f"to Run {run_id}; no acceptance mutation occurred."
            )
        else:
            postcondition = (
                f"A typed Design Episode block for {part_job_id} was appended "
                f"to Run {run_id}; no acceptance mutation occurred."
            )
        return {
            "episode": outcome.as_dict(),
            "reviewable_result": outcome.reviewable_summary,
            "artifact_references": persisted_references,
            "product_state": project_product_state(persisted),
            "orchestration": _completion(
                command="run_part_design_episode",
                phase=(
                    "build_evaluate"
                    if outcome.reviewable_result_id
                    else "design"
                ),
                checkpoint=(
                    "reviewable_result"
                    if outcome.reviewable_result_id
                    else "contract_validation"
                ),
                status=status,
                postcondition=postcondition,
                next_action=_design_episode_next_action(outcome),
            ),
        }

    def accept_part_result(
        self,
        work_id: str,
        *,
        part_job_id: str,
        result_id: str,
        attempt_run_id: str,
        result_run_id: str,
        review_id: str,
        artifact_references: list[dict[str, Any]],
    ) -> dict[str, Any]:
        work = self.store.read_work(work_id)
        timestamp = _now()
        with_references = register_artifact_references(
            work,
            artifact_references,
            updated_at=timestamp,
        )
        artifact_ids = [item["artifact_id"] for item in artifact_references]
        accepted = accept_part_result(
            with_references,
            part_job_id=part_job_id,
            result_id=result_id,
            attempt_run_id=attempt_run_id,
            result_run_id=result_run_id,
            review_id=review_id,
            artifact_ids=artifact_ids,
            accepted_at=timestamp,
        )
        self.store.write_work(work_id, accepted)
        self.store.invalidate_projection()
        return {
            "accepted_part_result": accepted["accepted_part_results"][part_job_id],
            "product_state": project_product_state(accepted),
            "orchestration": _completion(
                command="accept_part_result",
                phase="accept_deliver",
                checkpoint="acceptance_decision",
                postcondition=(
                    f"Accepted-result pointer for {part_job_id} now references "
                    f"{result_id}; active design lineage was unchanged."
                ),
                next_action="View accepted deliverables or start another attempt",
            ),
        }

    def accept_reviewable_part_result(
        self,
        work_id: str,
        *,
        part_job_id: str,
        reviewable_result_id: str,
        review_id: str | None = None,
    ) -> dict[str, Any]:
        """Explicit user authority for one registered reviewable result."""

        work = self.store.read_work(work_id)
        result_reference, step_reference = _registered_reviewable_result(
            work,
            work_id=work_id,
            part_job_id=part_job_id,
            reviewable_result_id=reviewable_result_id,
        )
        self.store.verify_reviewable_evidence(
            work_id,
            result_reference,
            step_reference,
        )
        timestamp = _now()
        accepted = accept_part_result(
            work,
            part_job_id=part_job_id,
            result_id=reviewable_result_id,
            attempt_run_id=result_reference["run_id"],
            result_run_id=result_reference["run_id"],
            review_id=review_id or f"accept_{uuid4().hex}",
            artifact_ids=[
                result_reference["artifact_id"],
                step_reference["artifact_id"],
            ],
            accepted_at=timestamp,
        )
        self.store.write_work(work_id, accepted)
        self.store.invalidate_projection()
        return {
            "accepted_part_result": accepted["accepted_part_results"][
                part_job_id
            ],
            "reviewable_result_id": reviewable_result_id,
            "product_state": project_product_state(accepted),
            "orchestration": _completion(
                command="accept_reviewable_part_result",
                phase="accept_deliver",
                checkpoint="acceptance_decision",
                postcondition=(
                    f"Explicit user acceptance moved only the {part_job_id} "
                    f"accepted-result pointer to {reviewable_result_id}; "
                    "active design lineage and Run evidence were unchanged."
                ),
                next_action="View accepted STEP or continue another Part Job",
            ),
        }

    def revise_reviewable_part_result(
        self,
        work_id: str,
        *,
        part_job_id: str,
        reviewable_result_id: str,
        revision_prompt: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new immutable attempt from a registered reviewable result."""

        before = self.store.read_work(work_id)
        result_reference, step_reference = _registered_reviewable_result(
            before,
            work_id=work_id,
            part_job_id=part_job_id,
            reviewable_result_id=reviewable_result_id,
        )
        self.store.verify_reviewable_evidence(
            work_id,
            result_reference,
            step_reference,
        )
        accepted_before = deepcopy(before.get("accepted_part_results"))
        result = self.create_part_attempt(
            work_id,
            part_job_id,
            prompt=(
                f"Revise reviewable result {reviewable_result_id}: "
                f"{_require_prompt(revision_prompt)}"
            ),
            source="reviewable_result_revision",
            run_id=run_id,
        )
        after = self.store.read_work(work_id)
        if after.get("accepted_part_results") != accepted_before:
            raise RuntimeError(
                "starting a reviewable-result revision changed acceptance"
            )
        return {
            **result,
            "revision_of": {
                "reviewable_result_id": reviewable_result_id,
                "part_job_id": part_job_id,
            },
            "orchestration": _completion(
                command="revise_reviewable_part_result",
                phase="design",
                checkpoint="part_job_attempt",
                postcondition=(
                    f"A new attempt Run was created from {reviewable_result_id}; "
                    "the prior reviewable evidence and accepted pointer were preserved."
                ),
                next_action="Run a new Design Episode for the revision attempt",
            ),
        }

    def select_candidate(
        self,
        work_id: str,
        *,
        selection: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist one validated Work candidate-selection pointer."""
        work = self.store.read_work(work_id)
        selected = record_candidate_selection(
            work,
            selection,
            updated_at=selection.get("created_at"),
        )
        self.store.write_work(work_id, selected)
        self.store.invalidate_projection()
        return {
            "candidate_selection": selected["candidate_selection"],
            "orchestration": _completion(
                command="select_candidate",
                phase="design",
                checkpoint="candidate_selection",
                postcondition=(
                    f"Work {work_id} now selects candidate "
                    f"{selection['selected_candidate']}; accepted results were unchanged."
                ),
                next_action="Create Part Request",
            ),
        }

    def register_existing_part_attempt(
        self,
        work_id: str,
        part_job_id: str,
        *,
        run_id: str,
        role: str | None = None,
    ) -> dict[str, Any]:
        """Adopt an existing legacy Run reference without recreating the Run."""
        if not self.deterministic.run_exists(work_id=work_id, run_id=run_id):
            raise FileNotFoundError(
                f"legacy Part Job attempt Run does not exist: {run_id}"
            )
        work = self.store.read_work(work_id)
        updated = append_part_attempt(
            work,
            part_job_id=part_job_id,
            run_id=run_id,
            role=role,
            source="legacy_reviewed_part",
            status="reviewable",
            created_at=_now(),
        )
        self.store.write_work(work_id, updated)
        self.store.invalidate_projection()
        return {
            "part_job": next(
                item
                for item in updated["part_jobs"]
                if item["part_job_id"] == part_job_id
            ),
            "orchestration": _completion(
                command="register_existing_part_attempt",
                phase="design",
                checkpoint="part_job_attempt",
                postcondition=(
                    f"Existing Run {run_id} is now referenced by Part Job "
                    f"{part_job_id}; Run evidence was not modified."
                ),
                next_action="Accept or revise the reviewable result",
            ),
        }

    def advance_lineage(
        self,
        work_id: str,
        *,
        parent_run_id: str,
        child_run_id: str | None = None,
    ) -> dict[str, Any]:
        work = self.store.read_work(work_id)
        advanced = advance_active_lineage(
            work,
            parent_run_id=parent_run_id,
            child_run_id=child_run_id,
            updated_at=_now(),
        )
        self.store.write_work(work_id, advanced)
        self.store.invalidate_projection()
        return {
            "active_lineage": advanced["active_lineage"],
            "orchestration": _completion(
                command="advance_lineage",
                phase="design",
                checkpoint="active_design_lineage",
                postcondition="Active design lineage advanced without changing acceptance.",
                next_action="Continue the active revision attempt",
            ),
        }


def _require_prompt(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("prompt must be a non-empty string")
    return value.strip()


def _completion(
    *,
    command: str,
    phase: str,
    checkpoint: str,
    status: str = "completed",
    postcondition: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "orchestrator": "work_orchestrator",
        "status": status,
        "command": command,
        "phase": phase,
        "checkpoint": checkpoint,
        "postcondition": postcondition,
        "next_action": next_action,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _protected_work_state(work: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(
        {
            "active_lineage": work.get("active_lineage"),
            "accepted_part_results": work.get("accepted_part_results"),
            "assembly_job": work.get("assembly_job"),
            "deliverable_packages": work.get("deliverable_packages"),
            "part_jobs": work.get("part_jobs"),
            "run_ids": work.get("run_ids"),
        }
    )


def _registered_reviewable_result(
    work: dict[str, Any],
    *,
    work_id: str,
    part_job_id: str,
    reviewable_result_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    references = [
        item
        for item in work.get("artifact_references", [])
        if isinstance(item, dict)
    ]
    matches = [
        item
        for item in references
        if item.get("artifact_id") == reviewable_result_id
    ]
    if len(matches) != 1:
        raise ValueError(
            "acceptance or revision requires one registered reviewable result"
        )
    result = matches[0]
    if not (
        result.get("work_id") == work_id
        and result.get("part_job_id") == part_job_id
        and result.get("phase") == "build_evaluate"
        and result.get("trust_role") == "reviewable_result"
        and result.get("checkpoint") == "reviewable_result"
        and result.get("validation_status") == "passed"
        and isinstance(result.get("run_id"), str)
        and isinstance(result.get("relative_path"), str)
        and result["relative_path"].endswith("/reviewable_result.json")
    ):
        raise ValueError("registered reviewable result identity is invalid")
    prefix = result["relative_path"].removesuffix("/reviewable_result.json")
    step_matches = [
        item
        for item in references
        if item.get("work_id") == work_id
        and item.get("part_job_id") == part_job_id
        and item.get("run_id") == result["run_id"]
        and item.get("phase") == "build_evaluate"
        and item.get("trust_role") == "reviewable_result"
        and item.get("checkpoint") == "reviewable_result"
        and item.get("validation_status") == "passed"
        and result["artifact_id"] in (item.get("source_artifact_ids") or [])
        and isinstance(item.get("relative_path"), str)
        and item["relative_path"].startswith(f"{prefix}/candidates/")
        and item["relative_path"].endswith("/model.step")
    ]
    if len(step_matches) != 1:
        raise ValueError(
            "registered reviewable result requires one validated STEP artifact"
        )
    job = next(
        (
            item
            for item in work.get("part_jobs", [])
            if isinstance(item, dict)
            and item.get("part_job_id") == part_job_id
        ),
        None,
    )
    attempts = {
        item.get("run_id")
        for item in (job.get("attempts", []) if isinstance(job, dict) else [])
        if isinstance(item, dict)
    }
    if result["run_id"] not in attempts:
        raise ValueError(
            "registered reviewable result does not belong to a Part Job attempt"
        )
    return result, step_matches[0]


def _validate_design_outcome(
    request: DesignPartEpisodeRequest,
    outcome: DesignPartEpisodeOutcome,
    work: dict[str, Any],
) -> None:
    if outcome.request_id != request.request_id:
        raise RuntimeError("Agent Design port returned a mismatched request id")
    expected_prefix = f"episodes/design_part/{request.request_id}/"
    artifact_ids = [artifact.artifact_id for artifact in outcome.artifacts]
    if len(set(artifact_ids)) != len(artifact_ids):
        raise RuntimeError("Agent Design port returned duplicate artifact ids")
    existing_ids = {
        item.get("artifact_id")
        for item in work.get("artifact_references", [])
        if isinstance(item, dict) and isinstance(item.get("artifact_id"), str)
    }
    allowed_source_ids = existing_ids | set(artifact_ids)
    reviewable = [
        artifact
        for artifact in outcome.artifacts
        if artifact.trust_role == "reviewable_result"
    ]
    if outcome.reviewable_result_id is None:
        if reviewable:
            raise RuntimeError(
                "Agent Design port returned reviewable artifacts without a reviewable identity"
            )
    else:
        if len(reviewable) != 2:
            raise RuntimeError(
                "reviewable publication requires exactly a result and STEP artifact"
            )
        by_id = {artifact.artifact_id: artifact for artifact in reviewable}
        result_artifact = by_id.get(outcome.reviewable_result_id)
        step_artifact = by_id.get(outcome.reviewable_step_artifact_id)
        if not (
            result_artifact is not None
            and step_artifact is not None
            and result_artifact.checkpoint == "reviewable_result"
            and result_artifact.relative_path.endswith(
                "/reviewable_result.json"
            )
            and step_artifact.checkpoint == "reviewable_result"
            and step_artifact.relative_path.endswith("/model.step")
            and step_artifact.source_artifact_ids
            == (result_artifact.artifact_id,)
        ):
            raise RuntimeError(
                "Agent Design port returned an invalid reviewable publication identity"
            )
    for artifact in outcome.artifacts:
        if not artifact.relative_path.startswith(expected_prefix):
            raise RuntimeError(
                "Agent Design port evidence must stay under the request directory"
            )
        if any(
            source_id not in allowed_source_ids
            for source_id in artifact.source_artifact_ids
        ):
            raise RuntimeError(
                "Agent Design port returned an unknown source artifact id"
            )


def _design_episode_next_action(outcome: DesignPartEpisodeOutcome) -> str:
    if outcome.reviewable_result_id:
        return "Accept or revise"
    if outcome.stop_reason == "completed":
        return "Review the validated contract candidate"
    if outcome.stop_reason == "user_input_required":
        return "Answer the focused question, then start a new Design Episode request"
    if outcome.stop_reason == "unsupported_capability":
        return "Configure a provider that supports design_part actions"
    return "Inspect the typed Episode diagnostic, then retry with a new request id"


def _design_artifact_phase(artifact: DesignEpisodeArtifact) -> str:
    if artifact.checkpoint in {
        "execution_observation",
        "reviewable_publication",
        "reviewable_result",
    }:
        return "build_evaluate"
    return "design"


def _stage_succeeded(value: Any) -> bool:
    return value in {
        "success",
        "completed",
        "completed_with_assumptions",
        "ready_for_review",
    }
