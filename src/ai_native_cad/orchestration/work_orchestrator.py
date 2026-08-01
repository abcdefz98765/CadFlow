"""Single M1 product orchestrator for Work mutations.

This runtime coordinates the current deterministic compatibility port. It does
not claim provider-selected Agent behavior and does not execute untrusted model
programs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_native_cad.domain.records import (
    accept_part_result,
    advance_active_lineage,
    append_part_attempt,
    begin_work_intent,
    project_product_state,
    record_candidate_selection,
    register_artifact_references,
)
from ai_native_cad.orchestration.ports import (
    DeterministicCompatibilityPort,
    WorkStorePort,
)


class WorkOrchestrator:
    """Sole target-product coordinator for the four user phases in M1."""

    def __init__(
        self,
        store: WorkStorePort,
        deterministic: DeterministicCompatibilityPort,
    ) -> None:
        self.store = store
        self.deterministic = deterministic

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


def _stage_succeeded(value: Any) -> bool:
    return value in {
        "success",
        "completed",
        "completed_with_assumptions",
        "ready_for_review",
    }
