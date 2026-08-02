"""Workflow Console adapters for the single M1 Work orchestrator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ai_native_cad.agents import run_design_part_episode
from ai_native_cad.agents.episode import (
    EpisodeContractError,
    UnknownAgentActionError,
)
from ai_native_cad.orchestration.ports import (
    DesignEpisodeArtifact,
    DesignPartEpisodeOutcome,
    DesignPartEpisodeRequest,
)
from ai_native_cad.workflow_console.work_index import create_work_manifest

if TYPE_CHECKING:
    from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend


class WorkflowConsoleWorkStore:
    """File-backed Work store using safe backend path boundaries."""

    def __init__(self, backend: WorkflowConsoleBackend) -> None:
        self.backend = backend

    def create_work(
        self,
        *,
        title: str,
        description: str | None,
        work_id: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return create_work_manifest(
            self.backend,
            title=title,
            description=description,
            work_id=work_id,
            metadata=metadata,
        )

    def read_work(self, work_id: str) -> dict[str, Any]:
        return self.backend._read_work_manifest(work_id)

    def write_work(self, work_id: str, work: dict[str, Any]) -> None:
        self.backend._write_work_manifest(work_id, work)

    def work_detail(self, work_id: str) -> dict[str, Any]:
        return self.backend.get_work_detail(work_id)

    def next_run_id(self, work_id: str, base: str) -> str:
        return self.backend._next_workspace_run_id(work_id, base)

    def invalidate_projection(self) -> None:
        self.backend.invalidate_work_index()


class WorkflowConsoleDeterministicCompatibility:
    """The sole product adapter to current deterministic Run behavior."""

    def __init__(self, backend: WorkflowConsoleBackend) -> None:
        self.backend = backend

    def workspace_config(self) -> dict[str, Any]:
        return self.backend.read_workspace_config()

    def create_run(
        self,
        *,
        work_id: str,
        run_id: str,
        prompt: str,
    ) -> dict[str, Any]:
        return self.backend.create_run_by_id(
            run_id,
            prompt,
            root=self.backend._work_runs_root(work_id),
        )

    def run_stage(
        self,
        *,
        work_id: str,
        run_id: str,
        stage: str,
    ) -> dict[str, Any]:
        return self.backend.run_stage_by_id(
            run_id,
            stage,
            root=self.backend._work_runs_root(work_id),
        )

    def planned_parts(
        self,
        *,
        work_id: str,
        root_run_id: str,
    ) -> list[dict[str, Any]]:
        root_run = self.backend.read_run_metadata_by_id(
            root_run_id,
            root=self.backend._work_runs_root(work_id),
        )
        return self.backend._planned_parts_from_run(root_run)

    def run_exists(self, *, work_id: str, run_id: str) -> bool:
        try:
            self.backend.resolve_run(
                run_id,
                root=self.backend._work_runs_root(work_id),
            )
        except FileNotFoundError:
            return False
        return True


class WorkflowConsoleAgentDesign:
    """Append validation-only provider Episodes under the owning Part Job Run."""

    def __init__(self, backend: WorkflowConsoleBackend) -> None:
        self.backend = backend

    def run_part_design_episode(
        self,
        request: DesignPartEpisodeRequest,
    ) -> DesignPartEpisodeOutcome:
        run_path = self.backend.resolve_run(
            request.run_id,
            root=self.backend._work_runs_root(request.work_id),
        )
        relative_root = f"episodes/design_part/{request.request_id}"
        episode_dir = self.backend._require_child_path(run_path, relative_root)
        route_result_path = self.backend._require_child_path(
            episode_dir,
            "product_route_result.json",
        )
        request_fingerprint = _request_fingerprint(request)
        if episode_dir.exists():
            return _read_idempotent_outcome(
                route_result_path,
                request_fingerprint=request_fingerprint,
            )
        episode_dir.mkdir(parents=True, exist_ok=False)

        adapter = self.backend.stage_runner.agent_adapter
        if not callable(getattr(adapter, "choose_design_action", None)):
            outcome = _blocked_design_outcome(
                request,
                relative_root=relative_root,
                stop_reason="unsupported_capability",
            )
        else:
            try:
                result = run_design_part_episode(
                    adapter=adapter,
                    handoff=_design_handoff(request),
                    artifact_dir=episode_dir,
                    run_id=request.run_id,
                    objective_summary=request.objective,
                )
            except (EpisodeContractError, UnknownAgentActionError):
                outcome = _blocked_design_outcome(
                    request,
                    relative_root=relative_root,
                    stop_reason="policy_blocked",
                )
            except Exception:
                outcome = _blocked_design_outcome(
                    request,
                    relative_root=relative_root,
                    stop_reason="provider_failure",
                )
            else:
                outcome = _episode_outcome(
                    request,
                    result,
                    relative_root=relative_root,
                )

        _write_json(
            route_result_path,
            {
                "schema_version": 1,
                "request_fingerprint": request_fingerprint,
                "request_identity": {
                    "request_id": request.request_id,
                    "work_id": request.work_id,
                    "run_id": request.run_id,
                    "part_job_id": request.part_job_id,
                },
                "episode": outcome.as_dict(),
                "authority": {
                    "orchestrator": "work_orchestrator",
                    "execution_enabled": outcome.result_kind == "model_program",
                    "publication_enabled": False,
                    "acceptance_mutation_enabled": False,
                },
            },
        )
        return outcome


def _design_handoff(request: DesignPartEpisodeRequest) -> dict[str, Any]:
    interfaces = request.interface_context.get("interfaces")
    if not isinstance(interfaces, list):
        interfaces = request.interface_context.get("interface_constraints")
    if not isinstance(interfaces, list):
        interfaces = []
    return {
        "work_id": request.work_id,
        "part_id": request.part_job_id,
        "role": request.role,
        "status": "active_part_job_attempt",
        "part_brief": request.objective,
        "interface_constraints": interfaces,
        "preserved_assembly_context": {
            "source": "work_manifest_v2",
            "interface_context": request.interface_context,
            "accepted_result_id": request.accepted_result_id,
        },
    }


def _episode_outcome(
    request: DesignPartEpisodeRequest,
    result: Any,
    *,
    relative_root: str,
) -> DesignPartEpisodeOutcome:
    artifacts: list[DesignEpisodeArtifact] = []
    candidate_id = None
    if result.final_contract is not None and result.contract_submission_count:
        candidate_id = f"episode:{result.episode_id}:contract"
        artifacts.append(
            DesignEpisodeArtifact(
                artifact_id=candidate_id,
                relative_path=(
                    f"{relative_root}/contract_submissions/"
                    f"submission_{result.contract_submission_count:03d}.json"
                ),
                checkpoint="geometry_candidate",
                trust_role="candidate",
                validation_status=(
                    "passed"
                    if result.validated
                    else "failed"
                    if result.validation_feedback is not None
                    else "not_validated"
                ),
            )
        )
    feedback_id = None
    if result.validation_feedback is not None:
        feedback_id = f"episode:{result.episode_id}:validation"
        artifacts.append(
            DesignEpisodeArtifact(
                artifact_id=feedback_id,
                relative_path=(
                    f"{relative_root}/validation_feedback/"
                    f"validation_{result.contract_submission_count:03d}.json"
                ),
                checkpoint="contract_validation",
                trust_role="observation",
                validation_status="passed" if result.validated else "failed",
                source_artifact_ids=(candidate_id,) if candidate_id else (),
            )
        )
    execution_observation_id = None
    if result.result_kind == "model_program" and result.final_candidate_id:
        candidate_id = f"episode:{result.episode_id}:model_program_candidate"
        artifacts.append(
            DesignEpisodeArtifact(
                artifact_id=candidate_id,
                relative_path=(
                    f"{relative_root}/model_program_submissions/"
                    f"submission_{result.source_submission_count:03d}.json"
                ),
                checkpoint="model_program_candidate",
                trust_role="candidate",
                validation_status=(
                    "passed" if result.execution_succeeded else "not_validated"
                ),
            )
        )
    if result.result_kind == "model_program" and result.final_observation_id:
        execution_observation_id = (
            f"episode:{result.episode_id}:execution_observation"
        )
        artifacts.append(
            DesignEpisodeArtifact(
                artifact_id=execution_observation_id,
                relative_path=(
                    f"{relative_root}/execution_observations/"
                    f"observation_{result.execution_count:03d}.json"
                ),
                checkpoint="execution_observation",
                trust_role=(
                    "observation" if result.execution_succeeded else "diagnostic"
                ),
                validation_status=(
                    "passed" if result.execution_succeeded else "failed"
                ),
                source_artifact_ids=(candidate_id,) if candidate_id else (),
            )
        )
    agent_result_id = f"episode:{result.episode_id}:result"
    artifacts.append(
        DesignEpisodeArtifact(
            artifact_id=agent_result_id,
            relative_path=f"{relative_root}/agent_result.json",
            checkpoint=(
                "execution_observation"
                if result.result_kind == "model_program"
                else "contract_validation"
            ),
            trust_role=(
                "observation"
                if result.status == "completed"
                else "diagnostic"
            ),
            validation_status=(
                "passed"
                if result.status == "completed"
                else "blocked"
            ),
            source_artifact_ids=tuple(
                item
                for item in (
                    candidate_id,
                    feedback_id,
                    execution_observation_id,
                )
                if item is not None
            ),
        )
    )
    route_id = f"episode:{result.episode_id}:product_route"
    artifacts.append(
        DesignEpisodeArtifact(
            artifact_id=route_id,
            relative_path=f"{relative_root}/product_route_result.json",
            checkpoint="product_design_routing",
            trust_role=(
                "observation"
                if result.status == "completed"
                else "diagnostic"
            ),
            validation_status=(
                "passed"
                if result.status == "completed"
                else "blocked"
            ),
            source_artifact_ids=(agent_result_id,),
        )
    )
    return DesignPartEpisodeOutcome(
        request_id=request.request_id,
        episode_id=result.episode_id,
        status=result.status,
        stop_reason=result.stop_reason.value,
        capability_mode=result.capability_mode,
        validated=result.validated,
        artifacts=tuple(artifacts),
        result_kind=result.result_kind,
        output_validated=result.output_validated,
        candidate_id=result.final_candidate_id,
        observation_id=result.final_observation_id,
        execution_succeeded=result.execution_succeeded,
    )


def _blocked_design_outcome(
    request: DesignPartEpisodeRequest,
    *,
    relative_root: str,
    stop_reason: str,
) -> DesignPartEpisodeOutcome:
    episode_id = uuid4().hex
    return DesignPartEpisodeOutcome(
        request_id=request.request_id,
        episode_id=episode_id,
        status="safely_blocked",
        stop_reason=stop_reason,
        capability_mode="provider_selected_design_with_attested_model_program",
        validated=False,
        artifacts=(
            DesignEpisodeArtifact(
                artifact_id=f"episode:{episode_id}:product_route",
                relative_path=f"{relative_root}/product_route_result.json",
                checkpoint="product_design_routing",
                trust_role="diagnostic",
                validation_status="blocked",
            ),
        ),
    )


def _request_fingerprint(request: DesignPartEpisodeRequest) -> str:
    encoded = json.dumps(
        request.manifest(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_idempotent_outcome(
    route_result_path: Path,
    *,
    request_fingerprint: str,
) -> DesignPartEpisodeOutcome:
    if not route_result_path.is_file():
        raise RuntimeError(
            "design episode request has incomplete evidence; use a new request id"
        )
    try:
        payload = json.loads(route_result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("design episode request evidence is unreadable") from exc
    if payload.get("request_fingerprint") != request_fingerprint:
        raise ValueError("request_id is already bound to a different design request")
    episode = payload.get("episode")
    if not isinstance(episode, dict):
        raise RuntimeError("design episode request evidence is incomplete")
    return DesignPartEpisodeOutcome.from_dict(
        episode,
        idempotent_replay=True,
    )


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
