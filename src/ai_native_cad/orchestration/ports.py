"""Typed ports owned by the product Work orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol


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
        if self.trust_role not in {"candidate", "observation", "diagnostic"}:
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
        if not self.artifacts:
            raise ValueError("Design Episode outcome requires durable evidence")

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
            idempotent_replay=idempotent_replay,
            schema_version=value.get("schema_version", 1),
        )

    def as_idempotent_replay(self) -> "DesignPartEpisodeOutcome":
        return replace(self, idempotent_replay=True)


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
    """Append one provider-selected, validation-only Episode to a Run."""

    def run_part_design_episode(
        self,
        request: DesignPartEpisodeRequest,
    ) -> DesignPartEpisodeOutcome: ...
