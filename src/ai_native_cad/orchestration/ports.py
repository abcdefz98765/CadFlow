"""Typed ports owned by the product Work orchestrator."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Any, ContextManager, Protocol


def _require_safe_id(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or any(marker in value for marker in ("/", "\\", ":", "\x00"))
    ):
        raise ValueError(f"{label} must be a safe id")
    return value


def _require_artifact_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or any(marker in value for marker in ("/", "\\", "\x00"))
    ):
        raise ValueError("artifact_id must be a controlled id")
    return value


def _require_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("relative_path is required")
    normalized = value.replace("\\", "/")
    if (
        normalized.startswith("/")
        or ":" in normalized
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
    ):
        raise ValueError("relative_path must be controlled and relative")
    return normalized


_FAILURE_DIAGNOSTIC_REQUIRED_FIELDS = {
    "schema_version",
    "rejection_stage",
    "rejected_action",
    "reason_code",
    "requested_capability_or_context",
    "human_safe_detail",
    "side_effect_started",
}
_FAILURE_DIAGNOSTIC_OPTIONAL_FIELDS = {
    "contract_repair_exhausted",
    "contract_repair_turn_count",
}
_FAILURE_DIAGNOSTIC_WORK_DESIGN_FIELDS = {
    "field_issue",
    "field_path",
    "expected_fields",
}
_BUDGET_FAILURE_DIAGNOSTIC_FIELDS = {
    "reason_code",
    "budget_kind",
    "used",
    "limit",
    "agent_steps",
}
_BUDGET_FAILURE_KINDS = {
    "wall_clock_seconds",
    "agent_steps",
    "context_requests",
    "context_bytes",
    "contract_submissions",
    "repair_attempts",
    "source_submissions",
    "cad_executions",
    "observation_inspections",
    "contract_repair_turns",
}
_SAFE_CONTRACT_FIELD_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,119}")
_SAFE_CONTRACT_FIELD_PATH_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]{0,119}(?:\[\])?"
    r"(?:\.[A-Za-z_][A-Za-z0-9_]{0,119}(?:\[\])?)*"
)


def _require_failure_diagnostic(value: dict[str, Any] | None) -> None:
    """Validate the small, source-free rejection fact carried by route evidence."""

    if value is None:
        return
    if isinstance(value, dict) and set(value) == _BUDGET_FAILURE_DIAGNOSTIC_FIELDS:
        budget_kind = value.get("budget_kind")
        if budget_kind not in _BUDGET_FAILURE_KINDS:
            raise ValueError("failure_diagnostic budget kind is invalid")
        if value.get("reason_code") != f"budget_exhausted.{budget_kind}":
            raise ValueError("failure_diagnostic budget reason code is invalid")
        for field in ("used", "limit"):
            item = value.get(field)
            if (
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(item)
                or item < 0
            ):
                raise ValueError(f"failure_diagnostic budget {field} is invalid")
        steps = value.get("agent_steps")
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0:
            raise ValueError("failure_diagnostic budget agent_steps is invalid")
        return
    fields = set(value) if isinstance(value, dict) else set()
    if (
        not isinstance(value, dict)
        or not _FAILURE_DIAGNOSTIC_REQUIRED_FIELDS <= fields
        or not fields <= (
            _FAILURE_DIAGNOSTIC_REQUIRED_FIELDS
            | _FAILURE_DIAGNOSTIC_OPTIONAL_FIELDS
            | _FAILURE_DIAGNOSTIC_WORK_DESIGN_FIELDS
        )
        or bool(fields & _FAILURE_DIAGNOSTIC_OPTIONAL_FIELDS)
        != (_FAILURE_DIAGNOSTIC_OPTIONAL_FIELDS <= fields)
        or bool(fields & _FAILURE_DIAGNOSTIC_WORK_DESIGN_FIELDS)
        != (_FAILURE_DIAGNOSTIC_WORK_DESIGN_FIELDS <= fields)
    ):
        raise ValueError("failure_diagnostic has an invalid shape")
    if value.get("schema_version") != 1:
        raise ValueError("failure_diagnostic has an unsupported schema version")
    for field in ("rejection_stage", "reason_code"):
        item = value.get(field)
        if not isinstance(item, str) or not item or len(item) > 120:
            raise ValueError(f"failure_diagnostic {field} is invalid")
    for field in ("rejected_action", "requested_capability_or_context"):
        item = value.get(field)
        if item is not None and (not isinstance(item, str) or len(item) > 120):
            raise ValueError(f"failure_diagnostic {field} is invalid")
    detail = value.get("human_safe_detail")
    if not isinstance(detail, str) or not detail or len(detail) > 240:
        raise ValueError("failure_diagnostic human_safe_detail is invalid")
    if not isinstance(value.get("side_effect_started"), bool):
        raise ValueError("failure_diagnostic side_effect_started is invalid")
    if _FAILURE_DIAGNOSTIC_OPTIONAL_FIELDS <= fields:
        if value.get("contract_repair_exhausted") is not True:
            raise ValueError("failure_diagnostic contract repair exhaustion is invalid")
        turn_count = value.get("contract_repair_turn_count")
        if not isinstance(turn_count, int) or isinstance(turn_count, bool) or turn_count < 0:
            raise ValueError("failure_diagnostic contract repair count is invalid")
    if _FAILURE_DIAGNOSTIC_WORK_DESIGN_FIELDS <= fields:
        if value.get("field_issue") not in {
            "missing", "extra", "invalid_type", "invalid_value", "invalid_shape",
        }:
            raise ValueError("failure_diagnostic field_issue is invalid")
        field_path = value.get("field_path")
        if not isinstance(field_path, str) or not _SAFE_CONTRACT_FIELD_PATH_RE.fullmatch(field_path):
            raise ValueError("failure_diagnostic field_path is invalid")
        expected_fields = value.get("expected_fields")
        if (
            not isinstance(expected_fields, list)
            or not 1 <= len(expected_fields) <= 32
            or len(set(expected_fields)) != len(expected_fields)
            or any(
                not isinstance(item, str)
                or not _SAFE_CONTRACT_FIELD_NAME_RE.fullmatch(item)
                for item in expected_fields
            )
        ):
            raise ValueError("failure_diagnostic expected_fields is invalid")


@dataclass(frozen=True)
class DesignPartEpisodeRequest:
    """Work-owned request for one validation-only Part Job Design Episode."""

    request_id: str
    work_id: str
    run_id: str
    part_job_id: str
    objective: str
    role: str | None
    interface_context: dict[str, Any]
    accepted_result_id: str | None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_safe_id(self.request_id, "request_id")
        _require_safe_id(self.work_id, "work_id")
        _require_safe_id(self.run_id, "run_id")
        _require_safe_id(self.part_job_id, "part_job_id")
        if not isinstance(self.objective, str) or not self.objective.strip():
            raise ValueError("design objective must be non-empty")
        if not isinstance(self.interface_context, dict):
            raise ValueError("interface_context must be an object")
        if self.role is not None and not isinstance(self.role, str):
            raise ValueError("design role must be text or null")

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "work_id": self.work_id,
            "run_id": self.run_id,
            "part_job_id": self.part_job_id,
            "objective": self.objective.strip(),
            "role": self.role,
            "interface_context": self.interface_context,
            "accepted_result_id": self.accepted_result_id,
        }


@dataclass(frozen=True)
class WorkDesignEpisodeRequest:
    """Work-owned request for one canonical Work Design Episode."""

    request_id: str
    work_id: str
    run_id: str
    title: str
    objective: str
    previous_work_design: dict[str, Any]
    clarification_answers: tuple[dict[str, Any], ...]
    existing_part_jobs: tuple[dict[str, Any], ...]
    accepted_part_results: dict[str, Any]
    previous_work_design_role: str | None = None
    current_unresolved_status: str = "none"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Work Design request supports schema_version 1 only")
        _require_safe_id(self.request_id, "request_id")
        _require_safe_id(self.work_id, "work_id")
        _require_safe_id(self.run_id, "run_id")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Work Design title must be non-empty")
        if not isinstance(self.objective, str) or not self.objective.strip():
            raise ValueError("Work Design objective must be non-empty")
        if self.previous_work_design_role not in {None, "active_candidate", "materialized"}:
            raise ValueError("Work Design context has an invalid design role")
        if self.current_unresolved_status not in {
            "none",
            "pending_question",
            "answered_pending_proposal",
        }:
            raise ValueError("Work Design context has an invalid unresolved status")

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "work_id": self.work_id,
            "run_id": self.run_id,
            "title": self.title,
            "objective": self.objective,
            "previous_work_design": self.previous_work_design,
            "clarification_answers": list(self.clarification_answers),
            "existing_part_jobs": list(self.existing_part_jobs),
            "accepted_part_results": self.accepted_part_results,
        }


@dataclass(frozen=True)
class DesignEpisodeArtifact:
    """One controlled Run-relative identity emitted by the Design port."""

    artifact_id: str
    relative_path: str
    checkpoint: str
    trust_role: str
    validation_status: str
    source_artifact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_artifact_id(self.artifact_id)
        _require_relative_path(self.relative_path)
        if not isinstance(self.checkpoint, str) or not self.checkpoint:
            raise ValueError("artifact checkpoint is required")
        if self.trust_role not in {
            "accepted_input",
            "candidate",
            "observation",
            "diagnostic",
            "reviewable_result",
        }:
            raise ValueError("Design Episode artifact has an invalid trust role")
        if not isinstance(self.validation_status, str) or not self.validation_status:
            raise ValueError("artifact validation_status is required")
        for source_id in self.source_artifact_ids:
            _require_artifact_id(source_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "relative_path": self.relative_path,
            "checkpoint": self.checkpoint,
            "trust_role": self.trust_role,
            "validation_status": self.validation_status,
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DesignEpisodeArtifact":
        return cls(
            artifact_id=value["artifact_id"],
            relative_path=value["relative_path"],
            checkpoint=value["checkpoint"],
            trust_role=value["trust_role"],
            validation_status=value["validation_status"],
            source_artifact_ids=tuple(value.get("source_artifact_ids") or ()),
        )


@dataclass(frozen=True)
class DesignPartEpisodeOutcome:
    """Path-free result returned from the append-only Run evidence port."""

    request_id: str
    episode_id: str
    status: str
    stop_reason: str
    capability_mode: str
    validated: bool
    artifacts: tuple[DesignEpisodeArtifact, ...]
    result_kind: str = "structured_contract"
    output_validated: bool = False
    candidate_id: str | None = None
    observation_id: str | None = None
    execution_succeeded: bool = False
    reviewable_result_id: str | None = None
    reviewable_step_artifact_id: str | None = None
    reviewable_summary: dict[str, Any] | None = None
    failure_diagnostic: dict[str, Any] | None = None
    idempotent_replay: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_safe_id(self.request_id, "request_id")
        _require_safe_id(self.episode_id, "episode_id")
        if self.schema_version != 1:
            raise ValueError("unsupported Design Episode outcome schema version")
        if self.status not in {"completed", "safely_blocked"}:
            raise ValueError("Design Episode outcome has an invalid status")
        if not isinstance(self.stop_reason, str) or not self.stop_reason:
            raise ValueError("Design Episode stop_reason is required")
        if not isinstance(self.capability_mode, str) or not self.capability_mode:
            raise ValueError("Design Episode capability_mode is required")
        if self.validated and (
            self.status != "completed" or self.stop_reason != "completed"
        ):
            raise ValueError("validated Design Episode outcome must be completed")
        if not self.validated and not self.output_validated and self.status == "completed":
            raise ValueError(
                "completed Design Episode outcome requires a validated contract or output"
            )
        if self.result_kind not in {"structured_contract", "model_program"}:
            raise ValueError("Design Episode outcome has an invalid result kind")
        if self.output_validated and self.result_kind != "model_program":
            raise ValueError("only a model-program outcome may validate output")
        if self.output_validated and not self.execution_succeeded:
            raise ValueError("validated model-program output requires execution success")
        reviewable_values = (
            self.reviewable_result_id,
            self.reviewable_step_artifact_id,
            self.reviewable_summary,
        )
        if any(value is not None for value in reviewable_values):
            if not all(value is not None for value in reviewable_values):
                raise ValueError("reviewable outcome identity must be complete")
            if not (
                self.result_kind == "model_program"
                and self.status == "completed"
                and self.stop_reason == "completed"
                and self.output_validated
                and self.execution_succeeded
            ):
                raise ValueError(
                    "reviewable outcome requires a completed validated model program"
                )
            _require_safe_id(self.reviewable_result_id, "reviewable_result_id")
            _require_artifact_id(self.reviewable_step_artifact_id)
            if not isinstance(self.reviewable_summary, dict):
                raise ValueError("reviewable_summary must be an object")
        if not self.artifacts:
            raise ValueError("Design Episode outcome requires durable evidence")
        _require_failure_diagnostic(self.failure_diagnostic)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "episode_id": self.episode_id,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "capability_mode": self.capability_mode,
            "validated": self.validated,
            "result_kind": self.result_kind,
            "output_validated": self.output_validated,
            "candidate_id": self.candidate_id,
            "observation_id": self.observation_id,
            "execution_succeeded": self.execution_succeeded,
            "reviewable_result_id": self.reviewable_result_id,
            "reviewable_step_artifact_id": self.reviewable_step_artifact_id,
            "reviewable_summary": self.reviewable_summary,
            "failure_diagnostic": (
                dict(self.failure_diagnostic) if self.failure_diagnostic else None
            ),
            "idempotent_replay": self.idempotent_replay,
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
        }

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
        *,
        idempotent_replay: bool = False,
    ) -> "DesignPartEpisodeOutcome":
        return cls(
            request_id=value["request_id"],
            episode_id=value["episode_id"],
            status=value["status"],
            stop_reason=value["stop_reason"],
            capability_mode=value["capability_mode"],
            validated=value["validated"] is True,
            artifacts=tuple(
                DesignEpisodeArtifact.from_dict(item)
                for item in value.get("artifacts") or []
            ),
            result_kind=value.get("result_kind", "structured_contract"),
            output_validated=value.get("output_validated") is True,
            candidate_id=value.get("candidate_id"),
            observation_id=value.get("observation_id"),
            execution_succeeded=value.get("execution_succeeded") is True,
            reviewable_result_id=value.get("reviewable_result_id"),
            reviewable_step_artifact_id=value.get(
                "reviewable_step_artifact_id"
            ),
            reviewable_summary=(
                dict(value["reviewable_summary"])
                if isinstance(value.get("reviewable_summary"), dict)
                else None
            ),
            failure_diagnostic=(
                dict(value["failure_diagnostic"])
                if isinstance(value.get("failure_diagnostic"), dict)
                else None
            ),
            idempotent_replay=idempotent_replay,
            schema_version=value.get("schema_version", 1),
        )

    def as_idempotent_replay(self) -> "DesignPartEpisodeOutcome":
        return replace(self, idempotent_replay=True)


@dataclass(frozen=True)
class WorkDesignEpisodeOutcome:
    """Path-free Work Design proposal returned to CadFlow for mutation."""

    request_id: str
    episode_id: str
    status: str
    stop_reason: str
    work_design: dict[str, Any] | None
    part_job_creation_requested: bool
    knowledge_ids: tuple[str, ...]
    artifacts: tuple[DesignEpisodeArtifact, ...]
    failure_diagnostic: dict[str, Any] | None = None
    idempotent_replay: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        _require_safe_id(self.request_id, "request_id")
        _require_safe_id(self.episode_id, "episode_id")
        if self.status not in {"completed", "safely_blocked"}:
            raise ValueError("Work Design outcome has an invalid status")
        if self.status == "completed" and not (
            isinstance(self.work_design, dict) and self.part_job_creation_requested
        ):
            raise ValueError("completed Work Design requires a decomposition request")
        if not self.artifacts:
            raise ValueError("Work Design outcome requires durable evidence")
        _require_failure_diagnostic(self.failure_diagnostic)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "episode_id": self.episode_id,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "work_design": self.work_design,
            "part_job_creation_requested": self.part_job_creation_requested,
            "knowledge_ids": list(self.knowledge_ids),
            "failure_diagnostic": (
                dict(self.failure_diagnostic) if self.failure_diagnostic else None
            ),
            "idempotent_replay": self.idempotent_replay,
            "artifacts": [item.as_dict() for item in self.artifacts],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any], *, idempotent_replay: bool = False) -> "WorkDesignEpisodeOutcome":
        return cls(
            request_id=value["request_id"],
            episode_id=value["episode_id"],
            status=value["status"],
            stop_reason=value["stop_reason"],
            work_design=dict(value["work_design"]) if isinstance(value.get("work_design"), dict) else None,
            part_job_creation_requested=value.get("part_job_creation_requested") is True,
            knowledge_ids=tuple(value.get("knowledge_ids") or ()),
            artifacts=tuple(DesignEpisodeArtifact.from_dict(item) for item in value.get("artifacts") or []),
            failure_diagnostic=(
                dict(value["failure_diagnostic"])
                if isinstance(value.get("failure_diagnostic"), dict)
                else None
            ),
            idempotent_replay=idempotent_replay,
            schema_version=value.get("schema_version", 1),
        )


class WorkStorePort(Protocol):
    """Mutable Work storage; historical Run contents are outside this port."""

    def create_work(
        self,
        *,
        title: str,
        description: str | None,
        work_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]: ...

    def read_work(self, work_id: str) -> dict[str, Any]: ...

    def write_work(self, work_id: str, work: dict[str, Any]) -> None: ...

    def work_design_answer_guard(self, work_id: str) -> ContextManager[None]: ...

    def verify_reviewable_evidence(
        self,
        work_id: str,
        result_reference: dict[str, Any],
        step_reference: dict[str, Any],
    ) -> None: ...

    def work_detail(self, work_id: str) -> dict[str, Any]: ...

    def next_run_id(self, work_id: str, base: str) -> str: ...

    def invalidate_projection(self) -> None: ...


class DeterministicCompatibilityPort(Protocol):
    """The one M1 port for deterministic legacy Run behavior."""

    def workspace_config(self) -> dict[str, Any]: ...

    def create_run(
        self,
        *,
        work_id: str,
        run_id: str,
        prompt: str,
    ) -> dict[str, Any]: ...

    def run_stage(
        self,
        *,
        work_id: str,
        run_id: str,
        stage: str,
    ) -> dict[str, Any]: ...

    def planned_parts(
        self,
        *,
        work_id: str,
        root_run_id: str,
    ) -> list[dict[str, Any]]: ...

    def run_exists(self, *, work_id: str, run_id: str) -> bool: ...


class AgentDesignPort(Protocol):
    """Append one provider-selected Episode and controlled publication evidence."""

    def run_part_design_episode(
        self,
        request: DesignPartEpisodeRequest,
    ) -> DesignPartEpisodeOutcome: ...

    def run_work_design_episode(
        self,
        request: WorkDesignEpisodeRequest,
    ) -> WorkDesignEpisodeOutcome: ...

    def record_work_design_answer(
        self,
        *,
        work_id: str,
        run_id: str,
        answer_id: str,
        question_artifact_id: str,
        field: str,
        question: str,
        answer: str,
    ) -> DesignEpisodeArtifact: ...

    def record_part_design_answer(
        self,
        *,
        work_id: str,
        run_id: str,
        part_job_id: str,
        answer_id: str,
        question_artifact_id: str,
        field: str,
        question: str,
        answer: str,
    ) -> DesignEpisodeArtifact: ...
