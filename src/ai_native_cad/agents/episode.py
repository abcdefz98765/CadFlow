"""Bounded, provider-independent design episodes.

This module deliberately contains no filesystem browsing, shell execution, or
An adapter may propose actions; the orchestrator owns budgets, identities,
context, validation, attested execution, and the compact audit trail.
"""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4

from ai_native_cad.agents.registry import (
    RUNTIME_SKILL_REGISTRY,
    SkillDefinition,
)
from ai_native_cad.agents.tool_broker import (
    MODEL_PROGRAM_TOOL,
    STRUCTURED_CONTRACT_TOOL,
    CadFlowToolBroker,
)
from ai_native_cad.agents.model_program_runtime import (
    ToolInvocationContext,
    validate_model_program_parameters,
)
from ai_native_cad.agents.provider_context import sanitize_provider_payload


class StopReason(str, Enum):
    """The only terminal outcomes an episode may record."""

    COMPLETED = "completed"
    USER_INPUT_REQUIRED = "user_input_required"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    VALIDATION_EXHAUSTED = "validation_exhausted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROVIDER_FAILURE = "provider_failure"
    POLICY_BLOCKED = "policy_blocked"


class AgentActionRejection(ValueError):
    """Typed, product-safe fact captured at an Agent rejection boundary."""

    def __init__(
        self,
        message: str,
        *,
        rejection_stage: str = "action_contract_validation",
        reason_code: str = "invalid_action_contract",
        rejected_action: str | None = None,
        requested_capability_or_context: str | None = None,
        human_safe_detail: str = "The Agent response did not match the allowed action contract.",
        side_effect_started: bool = False,
    ) -> None:
        super().__init__(message)
        self.failure_diagnostic = {
            "schema_version": 1,
            "rejection_stage": _safe_diagnostic_identifier(
                rejection_stage, "action_contract_validation"
            ),
            "rejected_action": _safe_diagnostic_identifier(rejected_action),
            "reason_code": _safe_diagnostic_identifier(
                reason_code, "invalid_action_contract"
            ),
            "requested_capability_or_context": _safe_diagnostic_identifier(
                requested_capability_or_context
            ),
            "human_safe_detail": _short_text(human_safe_detail),
            "side_effect_started": side_effect_started is True,
        }


class UnknownAgentActionError(AgentActionRejection):
    """Raised before an action outside the public allowlist can be processed."""


class EpisodeContractError(AgentActionRejection):
    """Raised when an action attempts to cross the structured contract boundary."""


ALLOWLISTED_ACTIONS = frozenset({
    "request_context",
    "create_contract",
    "patch_contract",
    "submit_contract",
    "request_validation",
    "create_model_program",
    "patch_model_program",
    "request_execution",
    "inspect_observation",
    "repair_contract",
    "propose_work_design",
    "create_part_jobs",
    "ask_user",
    "stop",
})

CONTEXT_KEYS = frozenset({
    "intent_active",
    "part_job",
    "part_interfaces",
    "previous_candidates",
    "previous_validation_observations",
    "user_acceptance_or_revision",
    "requirement_active",
    "assembly_plan",
    "reviewed_part_handoff",
    "previous_cad_ir_attempts",
    "previous_validation_feedback",
    "user_stage_review",
    "work_request",
    "accepted_work_context",
    "previous_work_design",
    "work_clarification_answers",
})

_FORBIDDEN_EXECUTION_FIELDS = frozenset({
    "cad_code", "cadquery_code", "command", "model_code", "python_code",
    "shell", "shell_command", "script",
})


@dataclass(frozen=True)
class AgentObjective:
    operation: str
    summary: str
    work_id: str | None = None
    checkpoint: str = "cad_ir_draft"


@dataclass(frozen=True)
class AgentCapabilities:
    capability_mode: str = "deterministic_fallback"
    skill_id: str = "legacy_create_part_ir"
    skill_version: str = "0.1.0"
    allowed_actions: frozenset[str] = ALLOWLISTED_ACTIONS
    allowed_context_keys: frozenset[str] = CONTEXT_KEYS
    allowed_contract_types: frozenset[str] = frozenset({"cad_ir_draft"})
    allowed_stop_reasons: frozenset[str] = frozenset(
        reason.value for reason in StopReason if reason != StopReason.COMPLETED
    )
    direct_code_execution: bool = False
    delegated_skill_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.allowed_actions <= ALLOWLISTED_ACTIONS:
            raise ValueError("agent capabilities include an action outside the allowlist")
        if not self.allowed_context_keys <= CONTEXT_KEYS:
            raise ValueError("agent capabilities include an unknown context key")
        if self.direct_code_execution:
            raise ValueError("agent episodes cannot enable direct code execution")

    @classmethod
    def for_skill(
        cls,
        skill: SkillDefinition,
        *,
        capability_mode: str,
    ) -> "AgentCapabilities":
        return cls(
            capability_mode=capability_mode,
            skill_id=skill.skill_id,
            skill_version=skill.version,
            allowed_actions=skill.allowed_actions,
            allowed_context_keys=skill.allowed_context_keys,
            allowed_contract_types=skill.output_contract_types,
            allowed_stop_reasons=skill.stop_reasons,
            delegated_skill_ids=skill.delegated_skill_ids,
        )


@dataclass(frozen=True)
class EpisodeBudget:
    max_steps: int = 8
    max_context_requests: int = 4
    max_context_bytes: int = 65_536
    max_contract_submissions: int = 3
    max_repair_attempts: int = 2
    max_source_submissions: int = 4
    max_executions: int = 3
    max_observation_inspections: int = 3
    timeout_seconds: float = 180.0

    def __post_init__(self) -> None:
        if any(value < 0 for value in (
            self.max_steps, self.max_context_requests, self.max_context_bytes,
            self.max_contract_submissions, self.max_repair_attempts,
            self.max_source_submissions, self.max_executions,
            self.max_observation_inspections,
        )) or self.timeout_seconds < 0:
            raise ValueError("episode budgets must be non-negative")


@dataclass(frozen=True)
class ContextEnvelope:
    objective: AgentObjective
    workflow: dict[str, Any]
    accepted_decisions: tuple[str, ...]
    selected_part: dict[str, Any]
    constraints: tuple[str, ...]
    previous_attempts: tuple[dict[str, Any], ...]
    available_context: tuple[str, ...]
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "objective": {
                "operation": self.objective.operation,
                "summary": self.objective.summary,
                "work_id": self.objective.work_id,
                "checkpoint": self.objective.checkpoint,
            },
            "workflow": dict(self.workflow),
            "accepted_decisions": list(self.accepted_decisions),
            "selected_part": dict(self.selected_part),
            "constraints": list(self.constraints),
            "previous_attempts": list(self.previous_attempts),
            "available_context": list(self.available_context),
        }


@dataclass(frozen=True)
class AgentAction:
    action: str
    context_key: str | None = None
    reason: str | None = None
    contract_type: str | None = None
    contract: dict[str, Any] | None = None
    model_program: dict[str, Any] | None = None
    work_design: dict[str, Any] | None = None
    assumptions: tuple[str, ...] = ()
    summary: str | None = None
    questions: tuple[dict[str, str], ...] = ()
    stop_reason: StopReason | None = None

    @classmethod
    def from_value(cls, value: "AgentAction | dict[str, Any]") -> "AgentAction":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise UnknownAgentActionError(
                "agent action must be an object",
                reason_code="agent_action_not_object",
                human_safe_detail="The Agent returned a value instead of one typed action object.",
            )
        action = value.get("action")
        if not isinstance(action, str) or action not in ALLOWLISTED_ACTIONS:
            raise UnknownAgentActionError(
                f"unknown agent action: {action!r}",
                rejection_stage="skill_action_authorization",
                reason_code="action_not_registered",
                rejected_action=action if isinstance(action, str) else None,
                requested_capability_or_context=(
                    action if isinstance(action, str) else None
                ),
                human_safe_detail=(
                    "The Agent requested an action that is not registered for bounded Episodes."
                ),
            )
        allowed_fields = {
            "request_context": {"action", "context_key", "reason"},
            "create_contract": {"action", "contract_type", "contract", "assumptions", "summary"},
            "patch_contract": {"action", "contract_type", "contract", "assumptions", "summary"},
            "submit_contract": {"action", "contract_type", "contract", "assumptions", "summary"},
            "repair_contract": {"action", "contract_type", "contract", "assumptions", "summary"},
            "request_validation": {"action", "reason"},
            "create_model_program": {"action", "model_program", "assumptions", "summary"},
            "patch_model_program": {"action", "model_program", "assumptions", "summary"},
            "request_execution": {"action"},
            "inspect_observation": {"action"},
            "propose_work_design": {"action", "work_design", "assumptions", "summary"},
            "create_part_jobs": {"action"},
            "ask_user": {"action", "questions", "reason"},
            "stop": {"action", "stop_reason", "reason"},
        }[action]
        if set(value) != (set(value) & allowed_fields) or "action" not in value:
            raise EpisodeContractError(
                f"{action} contains fields outside its strict action contract",
                reason_code="action_contract_extra_fields",
                rejected_action=action,
                requested_capability_or_context=_first_safe_identifier(
                    set(value) - allowed_fields
                ),
                human_safe_detail=(
                    f"The Agent returned fields that the {action} action does not allow."
                ),
            )
        raw_reason = value.get("stop_reason")
        try:
            stop_reason = StopReason(raw_reason) if raw_reason is not None else None
        except ValueError as exc:
            raise EpisodeContractError(
                "stop action has an unknown typed stop reason",
                reason_code="unknown_stop_reason",
                rejected_action=action,
                requested_capability_or_context=(
                    raw_reason if isinstance(raw_reason, str) else None
                ),
                human_safe_detail="The Agent returned a stop reason that the active Episode does not recognize.",
            ) from exc
        assumptions = value.get("assumptions") or []
        questions = value.get("questions") or []
        contract = value.get("contract")
        model_program = value.get("model_program")
        work_design = value.get("work_design")
        if not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions):
            raise EpisodeContractError(
                "action assumptions must be a list of strings",
                reason_code="invalid_action_payload",
                rejected_action=action,
            )
        if not isinstance(questions, list) or not all(isinstance(item, dict) for item in questions):
            raise EpisodeContractError(
                "ask_user questions must be a list of objects",
                reason_code="invalid_action_payload",
                rejected_action=action,
            )
        if action == "ask_user" and (
            not questions
            or any(
                not isinstance(item.get("field"), str)
                or not item.get("field")
                or not isinstance(item.get("question"), str)
                or not item.get("question")
                for item in questions
            )
        ):
            raise EpisodeContractError(
                "ask_user requires focused field and question values",
                reason_code="invalid_question_contract",
                rejected_action=action,
            )
        if contract is not None and not isinstance(contract, dict):
            raise EpisodeContractError(
                "contract must be an object",
                reason_code="invalid_action_payload",
                rejected_action=action,
            )
        if action in {"create_model_program", "patch_model_program"}:
            _validate_model_program_action(
                model_program,
                rejected_action=action,
            )
        elif model_program is not None:
            raise EpisodeContractError(
                "model_program is not allowed for this action",
                reason_code="action_contract_extra_fields",
                rejected_action=action,
                requested_capability_or_context="model_program",
            )
        if action == "propose_work_design":
            if not isinstance(work_design, dict):
                raise EpisodeContractError(
                    "propose_work_design requires work_design",
                    reason_code="invalid_work_design_contract",
                    rejected_action=action,
                )
        elif work_design is not None:
            raise EpisodeContractError(
                "work_design is not allowed for this action",
                reason_code="action_contract_extra_fields",
                rejected_action=action,
                requested_capability_or_context="work_design",
            )
        return cls(
            action=action,
            context_key=value.get("context_key") if isinstance(value.get("context_key"), str) else None,
            reason=value.get("reason") if isinstance(value.get("reason"), str) else None,
            contract_type=value.get("contract_type") if isinstance(value.get("contract_type"), str) else None,
            contract=contract,
            model_program=dict(model_program) if isinstance(model_program, dict) else None,
            work_design=dict(work_design) if isinstance(work_design, dict) else None,
            assumptions=tuple(assumptions),
            summary=value.get("summary") if isinstance(value.get("summary"), str) else None,
            questions=tuple(dict(item) for item in questions),
            stop_reason=stop_reason,
        )


@dataclass(frozen=True)
class ContextItem:
    context_key: str
    source_run_id: str
    source_stage_id: str
    source_type: str
    summary: dict[str, Any]
    content: dict[str, Any] = field(repr=False)
    active: bool = True
    work_id: str | None = None
    part_job_id: str | None = None
    trust_role: str = "accepted_input"

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "context_key": self.context_key,
            "source_run_id": self.source_run_id,
            "source_stage_id": self.source_stage_id,
            "source_type": self.source_type,
            "work_id": self.work_id,
            "part_job_id": self.part_job_id,
            "source_checkpoint": self.source_stage_id,
            "trust_role": self.trust_role,
            "summary": self.summary,
            "raw_artifact_available": bool(self.content),
        }


class ContextBroker:
    """Resolve only semantic keys from the accepted active lineage."""

    def __init__(self, items: list[ContextItem]) -> None:
        self._items = {item.context_key: item for item in items if item.active}

    @property
    def available_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))

    def resolve(
        self,
        context_key: str,
        *,
        allowed_keys: frozenset[str] | None = None,
        expected_work_id: str | None = None,
    ) -> ContextItem:
        if context_key not in CONTEXT_KEYS:
            raise EpisodeContractError(
                "context requests must use an allowlisted semantic context key",
                rejection_stage="context_authorization",
                reason_code="context_key_not_registered",
                rejected_action="request_context",
                requested_capability_or_context=context_key,
                human_safe_detail=(
                    "The Agent requested a semantic context key that CadFlow does not register."
                ),
            )
        if allowed_keys is not None and context_key not in allowed_keys:
            raise EpisodeContractError(
                "active skill does not allow this semantic context key",
                rejection_stage="context_authorization",
                reason_code="context_not_allowed_for_skill",
                rejected_action="request_context",
                requested_capability_or_context=context_key,
                human_safe_detail=(
                    "The Agent requested context that is not granted to the active Skill."
                ),
            )
        item = self._items.get(context_key)
        if item is None:
            raise EpisodeContractError(
                f"active lineage does not provide context: {context_key}",
                rejection_stage="context_resolution",
                reason_code="context_not_available",
                rejected_action="request_context",
                requested_capability_or_context=context_key,
                human_safe_detail=(
                    "The requested context is allowed, but this Work scope does not provide it."
                ),
            )
        if (
            expected_work_id is not None
            and item.work_id is not None
            and item.work_id != expected_work_id
        ):
            raise EpisodeContractError(
                "semantic context belongs to an unrelated Work",
                rejection_stage="context_scope_validation",
                reason_code="context_belongs_to_other_work",
                rejected_action="request_context",
                requested_capability_or_context=context_key,
                human_safe_detail=(
                    "CadFlow rejected context that belongs to a different Work."
                ),
            )
        return item


@dataclass(frozen=True)
class AgentEpisodeResult:
    episode_id: str
    operation: str
    skill_id: str
    skill_version: str
    status: str
    stop_reason: StopReason
    capability_mode: str
    step_count: int
    context_request_count: int
    context_byte_count: int
    contract_submission_count: int
    repair_attempt_count: int
    final_contract: dict[str, Any] | None
    validation_feedback: dict[str, Any] | None
    validated: bool
    result_kind: str
    source_submission_count: int
    execution_count: int
    observation_inspection_count: int
    final_candidate_id: str | None
    final_observation_id: str | None
    execution_succeeded: bool
    output_validated: bool
    failure_diagnostic: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "episode_id": self.episode_id,
            "operation": self.operation,
            "skill": {"id": self.skill_id, "version": self.skill_version},
            "mode": self.capability_mode,
            "capability_mode": self.capability_mode,
            "status": self.status,
            "step_count": self.step_count,
            "context_request_count": self.context_request_count,
            "context_byte_count": self.context_byte_count,
            "contract_submission_count": self.contract_submission_count,
            "repair_attempt_count": self.repair_attempt_count,
            "stop_reason": self.stop_reason.value,
            "validated": self.validated,
            "final_contract_available": self.final_contract is not None,
            "result_kind": self.result_kind,
            "source_submission_count": self.source_submission_count,
            "execution_count": self.execution_count,
            "observation_inspection_count": self.observation_inspection_count,
            "final_candidate_id": self.final_candidate_id,
            "final_observation_id": self.final_observation_id,
            "execution_succeeded": self.execution_succeeded,
            "output_validated": self.output_validated,
            "failure_diagnostic": deepcopy(self.failure_diagnostic),
        }


@dataclass(frozen=True)
class WorkDesignEpisodeResult:
    """Bounded Work-level design/decomposition result without mutation authority."""

    episode_id: str
    status: str
    stop_reason: StopReason
    step_count: int
    context_request_count: int
    context_byte_count: int
    proposal_count: int
    work_design: dict[str, Any] | None
    part_job_creation_requested: bool
    failure_diagnostic: dict[str, Any] | None = None
    skill_id: str = "work_design"
    skill_version: str = "0.1.0"
    capability_mode: str = "provider_selected_work_design"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "episode_id": self.episode_id,
            "operation": "work_design",
            "skill": {"id": self.skill_id, "version": self.skill_version},
            "capability_mode": self.capability_mode,
            "status": self.status,
            "stop_reason": self.stop_reason.value,
            "step_count": self.step_count,
            "context_request_count": self.context_request_count,
            "context_byte_count": self.context_byte_count,
            "proposal_count": self.proposal_count,
            "work_design_available": self.work_design is not None,
            "part_job_creation_requested": self.part_job_creation_requested,
            "failure_diagnostic": deepcopy(self.failure_diagnostic),
        }


class ActionSupplier(Protocol):
    def __call__(self, state: dict[str, Any]) -> AgentAction | dict[str, Any]: ...


class EpisodeArtifactWriter:
    """Persists the reviewable episode record, never unrestricted transcripts."""

    def __init__(
        self,
        output_dir: Path,
        envelope: ContextEnvelope,
        tool_broker_manifest: dict[str, Any],
        provider_identity: dict[str, Any] | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.envelope = envelope
        self.tool_broker_manifest = tool_broker_manifest
        self.events: list[dict[str, Any]] = []
        self.context_manifest: list[dict[str, Any]] = []
        self.provider_identity = _safe_provider_identity(provider_identity or {})
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def provider_response(self, number: int, value: Any) -> None:
        """Append a product-safe external Agent response before validation.

        This intentionally records the response boundary even when the action
        contract is invalid. Source, parameters, credentials, headers, and
        private reasoning are never retained in this projection.
        """

        entry = {
            "schema_version": 1,
            "sequence": number,
            "event_type": "agent_response",
            "provider_identity": self.provider_identity,
            **_safe_agent_response(value),
            "private_reasoning_exposed": False,
            "credential_material_exposed": False,
        }
        path = self.output_dir / "agent_exchange.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")

    def event(self, value: dict[str, Any]) -> None:
        sanitized = sanitize_provider_payload(value)
        if not isinstance(sanitized, dict):
            raise ValueError("episode event sanitizer must return an object")
        self.events.append(sanitized)

    def add_context(self, item: ContextItem) -> None:
        entry = item.manifest_entry()
        if entry not in self.context_manifest:
            self.context_manifest.append(entry)

    def submission(self, number: int, contract: dict[str, Any]) -> None:
        destination = self.output_dir / "contract_submissions" / f"submission_{number:03d}.json"
        _write_json(destination, contract)

    def feedback(self, number: int, feedback: dict[str, Any]) -> None:
        destination = self.output_dir / "validation_feedback" / f"validation_{number:03d}.json"
        _write_json(destination, feedback)

    def model_program_submission(
        self,
        number: int,
        *,
        candidate_id: str,
        model_program: dict[str, Any],
    ) -> None:
        directory = self.output_dir / "model_program_submissions"
        directory.mkdir(parents=True, exist_ok=True)
        source = str(model_program["source"])
        _write_json(
            directory / f"submission_{number:03d}.json",
            {
                "schema_version": 1,
                "candidate_id": candidate_id,
                "api_id": model_program["api_id"],
                "source_hash": _sha256_text(source),
                "parameters_hash": _sha256_json(model_program["parameters"]),
                "requested_outputs": ["step"],
                "source_retained": False,
                "parameters_retained": False,
                "canonical_execution_evidence": (
                    "candidates/<cadflow_candidate>/<cadflow_execution>/"
                    "after policy and attestation gates"
                ),
                "trust_role": "candidate",
                "reviewable": False,
                "accepted": False,
                "deliverable": False,
            },
        )

    def execution_observation(
        self,
        number: int,
        *,
        observation_id: str,
        observation: dict[str, Any],
    ) -> None:
        destination = (
            self.output_dir
            / "execution_observations"
            / f"observation_{number:03d}.json"
        )
        _write_json(
            destination,
            {
                "schema_version": 1,
                "observation_id": observation_id,
                **observation,
                "reviewable": False,
                "accepted": False,
                "deliverable": False,
            },
        )

    def user_input_request(
        self,
        *,
        questions: tuple[dict[str, str], ...],
        reason: str | None,
    ) -> None:
        """Persist the focused question as product-safe episode evidence."""
        _write_json(
            self.output_dir / "user_input_request.json",
            {
                "schema_version": 1,
                "checkpoint": "clarification_decision",
                "status": "user_input_required",
                "questions": [dict(item) for item in questions],
                "why_it_matters": reason,
                "private_reasoning_exposed": False,
            },
        )

    def finish(self, result: AgentEpisodeResult) -> None:
        episode = result.as_dict()
        episode["provider_identity"] = self.provider_identity
        episode["objective"] = {"operation": self.envelope.objective.operation, "summary": self.envelope.objective.summary}
        lineage = {
            "work_id": self.envelope.objective.work_id or self.envelope.workflow.get("work_id"),
            "run_id": self.envelope.workflow.get("active_leaf_run_id"),
            "parent_run_id": self.envelope.workflow.get("active_root_run_id"),
            "part_id": self.envelope.selected_part.get("part_id"),
            "source_handoff": self.envelope.workflow.get("source_handoff"),
            "accepted_submission_id": f"submission_{result.contract_submission_count:03d}" if result.validated and result.result_kind == "structured_contract" else None,
            "candidate_id": result.final_candidate_id,
            "observation_id": result.final_observation_id,
        }
        episode["lineage"] = lineage
        _write_json(self.output_dir / "agent_episode.json", episode)
        _write_json(self.output_dir / "context_manifest.json", {"schema_version": 1, "items": self.context_manifest})
        _write_json(
            self.output_dir / "tool_broker_manifest.json",
            self.tool_broker_manifest,
        )
        events_path = self.output_dir / "agent_events.jsonl"
        events_path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in self.events), encoding="utf-8")
        _write_json(self.output_dir / "agent_result.json", {
            **result.as_dict(),
            "lineage": lineage,
            "submitted_contract": result.final_contract,
            "validator_feedback": result.validation_feedback,
        })


class EpisodeOrchestrator:
    """Budgeted state machine; it is the only component that advances state."""

    def __init__(
        self,
        objective: AgentObjective,
        context_envelope: ContextEnvelope,
        context_broker: ContextBroker,
        capabilities: AgentCapabilities,
        budget: EpisodeBudget,
        validate_contract: Callable[[dict[str, Any]], dict[str, Any]] | None,
        artifact_dir: Path,
        *,
        tool_broker: CadFlowToolBroker | None = None,
        provider_identity: dict[str, Any] | None = None,
    ) -> None:
        self.objective = objective
        self.context_envelope = context_envelope
        self.context_broker = context_broker
        self.capabilities = capabilities
        self.budget = budget
        if tool_broker is not None and validate_contract is not None:
            raise ValueError(
                "provide either a Tool Broker or a compatibility validator, not both"
            )
        self._validate_contract = validate_contract
        self.tool_broker = tool_broker or CadFlowToolBroker(
            structured_contract_validator=validate_contract
        )
        self.writer = EpisodeArtifactWriter(
            artifact_dir,
            context_envelope,
            self.tool_broker.manifest(
                active_skill_id=capabilities.skill_id,
                delegated_skill_ids=capabilities.delegated_skill_ids,
            ),
            provider_identity,
        )

    @property
    def validate_contract(
        self,
    ) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
        """Compatibility hook; validation still executes through Tool Broker."""

        return self._validate_contract

    @validate_contract.setter
    def validate_contract(
        self,
        validator: Callable[[dict[str, Any]], dict[str, Any]] | None,
    ) -> None:
        self._validate_contract = validator
        self.tool_broker = CadFlowToolBroker(
            structured_contract_validator=validator
        )
        if hasattr(self, "writer"):
            self.writer.tool_broker_manifest = self.tool_broker.manifest(
                active_skill_id=self.capabilities.skill_id,
                delegated_skill_ids=self.capabilities.delegated_skill_ids,
            )

    def run(self, supplier: ActionSupplier) -> AgentEpisodeResult:
        started = time.monotonic()
        episode_id = uuid4().hex
        steps = context_requests = context_bytes = submissions = repairs = 0
        source_submissions = executions = inspections = 0
        draft: dict[str, Any] | None = None
        feedback: dict[str, Any] | None = None
        current_program: dict[str, Any] | None = None
        current_candidate_id: str | None = None
        latest_observation: dict[str, Any] | None = None
        latest_observation_id: str | None = None
        latest_observation_inspected = False
        latest_failure_diagnostic: dict[str, Any] | None = None
        state = "created"
        supplied_context: list[dict[str, Any]] = []

        def finish(
            reason: StopReason,
            *,
            validated: bool = False,
            result_kind: str | None = None,
            output_validated: bool = False,
            failure_diagnostic: dict[str, Any] | None = None,
        ) -> AgentEpisodeResult:
            actual_result_kind = result_kind or (
                "model_program" if current_program is not None else "structured_contract"
            )
            observed_output_validated = bool(
                latest_observation is not None
                and latest_observation.get("success") is True
                and isinstance(latest_observation.get("output"), dict)
                and _execution_output_has_valid_reimport(
                    latest_observation["output"]
                )
            )
            status = "completed" if reason == StopReason.COMPLETED and (validated or output_validated) else "safely_blocked"
            result = AgentEpisodeResult(
                episode_id=episode_id, operation=self.objective.operation,
                skill_id=self.capabilities.skill_id,
                skill_version=self.capabilities.skill_version,
                status=status, stop_reason=reason,
                capability_mode=self.capabilities.capability_mode, step_count=steps,
                context_request_count=context_requests, contract_submission_count=submissions,
                context_byte_count=context_bytes,
                repair_attempt_count=repairs, final_contract=draft,
                validation_feedback=feedback, validated=validated,
                result_kind=actual_result_kind,
                source_submission_count=source_submissions,
                execution_count=executions,
                observation_inspection_count=inspections,
                final_candidate_id=current_candidate_id,
                final_observation_id=latest_observation_id,
                execution_succeeded=(
                    latest_observation is not None
                    and latest_observation.get("success") is True
                ),
                output_validated=(
                    output_validated or observed_output_validated
                ),
                failure_diagnostic=deepcopy(
                    failure_diagnostic or latest_failure_diagnostic
                ),
            )
            self.writer.finish(result)
            return result

        while True:
            if time.monotonic() - started >= self.budget.timeout_seconds:
                self.writer.event({"step": steps, "observation": "timeout"})
                return finish(StopReason.BUDGET_EXHAUSTED)
            if steps >= self.budget.max_steps:
                self.writer.event({"step": steps, "observation": "step_budget_exhausted"})
                return finish(StopReason.BUDGET_EXHAUSTED)

            provider_state = {
                "state": state,
                "context_envelope": self.context_envelope.as_dict(),
                "supplied_context": supplied_context,
                "draft": draft,
                "validation_feedback": feedback,
                "model_program": (
                    {
                        "candidate_id": current_candidate_id,
                        "api_id": current_program["api_id"],
                        "source": current_program["source"],
                        "parameters": current_program["parameters"],
                        "requested_outputs": ["step"],
                    }
                    if current_program is not None
                    else None
                ),
                "pending_observation": (
                    {
                        "observation_id": latest_observation_id,
                        "available": True,
                        "inspected": latest_observation_inspected,
                    }
                    if latest_observation is not None
                    else None
                ),
            }
            try:
                supplied_action = supplier(provider_state)
            except Exception as exc:
                self.writer.event(
                    {
                        "event_type": "system_observation",
                        "step": steps,
                        "observation": "provider_failure",
                        "error_type": type(exc).__name__,
                    }
                )
                return finish(StopReason.PROVIDER_FAILURE)
            self.writer.provider_response(steps + 1, supplied_action)
            action = AgentAction.from_value(supplied_action)
            if action.action not in self.capabilities.allowed_actions:
                raise UnknownAgentActionError(
                    f"action is not enabled for this episode: {action.action}",
                    rejection_stage="skill_action_authorization",
                    reason_code="action_not_allowed_for_skill",
                    rejected_action=action.action,
                    requested_capability_or_context=action.action,
                    human_safe_detail=(
                        "The Agent requested an action that the active Skill does not allow."
                    ),
                )
            steps += 1

            if action.action == "request_context":
                if context_requests >= self.budget.max_context_requests:
                    self.writer.event({"step": steps, "action": action.action, "context_key": action.context_key, "reason": action.reason, "observation": "context_budget_exhausted"})
                    return finish(StopReason.BUDGET_EXHAUSTED)
                if not action.context_key:
                    raise EpisodeContractError(
                        "request_context requires context_key",
                        reason_code="missing_context_key",
                        rejected_action=action.action,
                    )
                item = self.context_broker.resolve(
                    action.context_key,
                    allowed_keys=self.capabilities.allowed_context_keys,
                    expected_work_id=self.objective.work_id,
                )
                item_bytes = len(
                    json.dumps(item.content, sort_keys=True).encode("utf-8")
                )
                if context_bytes + item_bytes > self.budget.max_context_bytes:
                    self.writer.event(
                        {
                            "step": steps,
                            "action": action.action,
                            "context_key": item.context_key,
                            "observation": "context_byte_budget_exhausted",
                        }
                    )
                    return finish(StopReason.BUDGET_EXHAUSTED)
                context_requests += 1
                context_bytes += item_bytes
                self.writer.add_context(item)
                supplied_context.append({**item.manifest_entry(), "content": item.content})
                self.writer.event({"event_type": "agent_action", "step": steps, "action": action.action, "context_key": item.context_key, "reason": action.reason})
                state = "gathering_context"
                continue

            if action.action in {
                "create_contract",
                "patch_contract",
                "submit_contract",
                "repair_contract",
            }:
                if submissions >= self.budget.max_contract_submissions:
                    self.writer.event({"step": steps, "action": action.action, "observation": "submission_budget_exhausted"})
                    return finish(StopReason.BUDGET_EXHAUSTED)
                is_repair = action.action in {"patch_contract", "repair_contract"}
                if is_repair:
                    if repairs >= self.budget.max_repair_attempts:
                        self.writer.event({"step": steps, "action": action.action, "observation": "repair_budget_exhausted"})
                        return finish(StopReason.BUDGET_EXHAUSTED)
                    repairs += 1
                if (
                    action.contract_type not in self.capabilities.allowed_contract_types
                    or not isinstance(action.contract, dict)
                ):
                    raise EpisodeContractError(
                        "submitted contract type is not enabled for this episode",
                        rejection_stage="skill_action_authorization",
                        reason_code="contract_type_not_allowed",
                        rejected_action=action.action,
                        requested_capability_or_context=action.contract_type,
                        human_safe_detail=(
                            "The Agent submitted a contract type that the active Skill does not allow."
                        ),
                    )
                _reject_execution_fields(
                    action.contract,
                    rejected_action=action.action,
                )
                submissions += 1
                draft = action.contract
                self.writer.submission(submissions, draft)
                self.writer.event({
                    "event_type": "agent_action", "step": steps, "action": action.action, "contract_type": action.contract_type,
                    "proposal_summary": action.summary or _contract_summary(draft),
                    "assumptions": list(action.assumptions),
                    **({"repair_summary": action.summary or _contract_summary(draft)} if is_repair else {}),
                })
                state = "repairing" if is_repair else "proposing"
                continue

            if action.action in {
                "create_model_program",
                "patch_model_program",
            }:
                if source_submissions >= self.budget.max_source_submissions:
                    self.writer.event(
                        {
                            "step": steps,
                            "action": action.action,
                            "observation": "source_submission_budget_exhausted",
                        }
                    )
                    return finish(
                        StopReason.BUDGET_EXHAUSTED,
                        result_kind="model_program",
                    )
                is_repair = action.action == "patch_model_program"
                if action.action == "create_model_program" and current_program is not None:
                    raise EpisodeContractError(
                        "create_model_program requires no current candidate",
                        rejection_stage="episode_action_ordering",
                        reason_code="model_program_candidate_already_exists",
                        rejected_action=action.action,
                    )
                if is_repair:
                    if current_program is None:
                        raise EpisodeContractError(
                            "patch_model_program requires a current candidate",
                            rejection_stage="episode_action_ordering",
                            reason_code="model_program_candidate_missing",
                            rejected_action=action.action,
                        )
                    if latest_observation is None or not latest_observation_inspected:
                        raise EpisodeContractError(
                            "patch_model_program requires inspection of the latest execution observation",
                            rejection_stage="episode_action_ordering",
                            reason_code="observation_inspection_required",
                            rejected_action=action.action,
                        )
                    if repairs >= self.budget.max_repair_attempts:
                        self.writer.event(
                            {
                                "step": steps,
                                "action": action.action,
                                "observation": "repair_budget_exhausted",
                            }
                        )
                        return finish(
                            StopReason.BUDGET_EXHAUSTED,
                            result_kind="model_program",
                        )
                    repairs += 1
                assert action.model_program is not None
                source_submissions += 1
                current_candidate_id = f"candidate_{source_submissions:03d}"
                current_program = {
                    "api_id": action.model_program["api_id"],
                    "source": action.model_program["source"],
                    "parameters": dict(action.model_program["parameters"]),
                    "requested_outputs": ["step"],
                }
                latest_observation = None
                latest_observation_id = None
                latest_observation_inspected = False
                self.writer.model_program_submission(
                    source_submissions,
                    candidate_id=current_candidate_id,
                    model_program=current_program,
                )
                self.writer.event(
                    {
                        "event_type": "agent_action",
                        "step": steps,
                        "action": action.action,
                        "candidate_id": current_candidate_id,
                        "api_id": current_program["api_id"],
                        "source_hash": _sha256_text(current_program["source"]),
                        "parameters_hash": _sha256_json(current_program["parameters"]),
                        "proposal_summary": action.summary,
                        "assumptions": list(action.assumptions),
                    }
                )
                state = "repairing_model_program" if is_repair else "model_program_proposed"
                continue

            if action.action == "request_execution":
                if current_program is None or current_candidate_id is None:
                    raise EpisodeContractError(
                        "request_execution requires a current model-program candidate",
                        rejection_stage="episode_action_ordering",
                        reason_code="model_program_candidate_missing",
                        rejected_action=action.action,
                    )
                if latest_observation is not None:
                    raise EpisodeContractError(
                        "request_execution requires a new or patched candidate",
                        rejection_stage="episode_action_ordering",
                        reason_code="candidate_already_executed",
                        rejected_action=action.action,
                    )
                if executions >= self.budget.max_executions:
                    self.writer.event(
                        {
                            "step": steps,
                            "action": action.action,
                            "observation": "execution_budget_exhausted",
                        }
                    )
                    return finish(
                        StopReason.BUDGET_EXHAUSTED,
                        result_kind="model_program",
                    )
                run_id = str(
                    self.context_envelope.workflow.get("active_leaf_run_id")
                    or self.writer.output_dir.name
                )
                work_id = self.objective.work_id
                part_job_id = self.context_envelope.selected_part.get("part_id")
                try:
                    invocation_context = ToolInvocationContext(
                        work_id=str(work_id or ""),
                        run_id=run_id,
                        part_job_id=str(part_job_id or ""),
                        episode_id=episode_id,
                        evidence_root=self.writer.output_dir.resolve(),
                    )
                except ValueError as exc:
                    raise EpisodeContractError(
                        "model-program execution requires path-safe CadFlow lineage identity",
                        rejection_stage="tool_input_validation",
                        reason_code="invalid_execution_lineage",
                        rejected_action=action.action,
                        human_safe_detail="CadFlow could not bind the execution request to safe Work and Run identity.",
                    ) from exc
                observation = self.tool_broker.invoke(
                    MODEL_PROGRAM_TOOL,
                    skill_id="model_program",
                    payload={
                        "api_id": current_program["api_id"],
                        "candidate_id": current_candidate_id,
                        "source": current_program["source"],
                        "parameters": current_program["parameters"],
                        "requested_outputs": ["step"],
                    },
                    context=invocation_context,
                )
                executions += 1
                latest_observation_id = f"observation_{executions:03d}"
                latest_observation = observation.as_dict()
                latest_observation_inspected = False
                latest_failure_diagnostic = (
                    _tool_rejection_diagnostic(
                        latest_observation,
                        rejected_action=action.action,
                    )
                    if observation.success is not True
                    else None
                )
                self.writer.execution_observation(
                    executions,
                    observation_id=latest_observation_id,
                    observation=latest_observation,
                )
                self.writer.event(
                    {
                        "event_type": "system_observation",
                        "step": steps,
                        "action": action.action,
                        "owner": "cadflow_tool_broker",
                        "candidate_id": current_candidate_id,
                        "observation_id": latest_observation_id,
                        "tool_id": observation.tool_id,
                        "success": observation.success,
                        "codes": list(observation.codes),
                        "side_effect_started": observation.side_effect_started,
                        "exit_state": observation.exit_state,
                        "observation": "execution_observation_available",
                    }
                )
                state = "execution_observation_available"
                continue

            if action.action == "inspect_observation":
                if latest_observation is None or latest_observation_id is None:
                    raise EpisodeContractError(
                        "inspect_observation requires an execution observation",
                        rejection_stage="episode_action_ordering",
                        reason_code="execution_observation_missing",
                        rejected_action=action.action,
                    )
                if latest_observation_inspected:
                    raise EpisodeContractError(
                        "the latest execution observation was already inspected",
                        rejection_stage="episode_action_ordering",
                        reason_code="execution_observation_already_inspected",
                        rejected_action=action.action,
                    )
                if inspections >= self.budget.max_observation_inspections:
                    self.writer.event(
                        {
                            "step": steps,
                            "action": action.action,
                            "observation": "observation_inspection_budget_exhausted",
                        }
                    )
                    return finish(
                        StopReason.BUDGET_EXHAUSTED,
                        result_kind="model_program",
                    )
                inspections += 1
                latest_observation_inspected = True
                supplied_context.append(
                    {
                        "context_key": "latest_execution_observation",
                        "observation_id": latest_observation_id,
                        "content": _provider_execution_observation(latest_observation),
                    }
                )
                self.writer.event(
                    {
                        "event_type": "agent_action",
                        "step": steps,
                        "action": action.action,
                        "observation_id": latest_observation_id,
                    }
                )
                state = "observation_inspected"
                continue

            if action.action == "request_validation":
                if draft is None:
                    raise EpisodeContractError(
                        "request_validation requires a submitted contract",
                        rejection_stage="episode_action_ordering",
                        reason_code="structured_contract_missing",
                        rejected_action=action.action,
                    )
                observation = self.tool_broker.invoke(
                    STRUCTURED_CONTRACT_TOOL,
                    skill_id=self.capabilities.skill_id,
                    payload={
                        "contract_type": "cad_ir_draft",
                        "contract": draft,
                    },
                )
                feedback = observation.output
                if not isinstance(feedback, dict) or not isinstance(feedback.get("valid"), bool):
                    raise EpisodeContractError(
                        "Tool Broker must return structured validation feedback",
                        rejection_stage="tool_output_validation",
                        reason_code="invalid_tool_observation",
                        rejected_action=action.action,
                        human_safe_detail="CadFlow's local validator returned an invalid typed observation.",
                    )
                self.writer.feedback(submissions, feedback)
                self.writer.event({
                    "event_type": "system_observation", "step": steps, "action": action.action,
                    "owner": "cadflow_tool_broker",
                    "tool_id": observation.tool_id,
                    "execution_profile": observation.execution_profile,
                    "side_effect_started": observation.side_effect_started,
                    "validator_feedback": _feedback_summary(feedback),
                    "codes": list(observation.codes),
                    "observation": "validation_passed" if feedback["valid"] else "validation_failed",
                })
                if feedback["valid"]:
                    return finish(StopReason.COMPLETED, validated=True)
                state = "awaiting_validation"
                continue

            if action.action == "ask_user":
                self.writer.user_input_request(
                    questions=action.questions,
                    reason=action.reason,
                )
                self.writer.event({"step": steps, "action": action.action, "questions": list(action.questions), "reason": action.reason})
                return finish(StopReason.USER_INPUT_REQUIRED)

            if action.action == "stop":
                reason = action.stop_reason or StopReason.INSUFFICIENT_CONTEXT
                if reason == StopReason.COMPLETED:
                    execution_output = (
                        latest_observation.get("output", {})
                        if isinstance(latest_observation, dict)
                        and isinstance(latest_observation.get("output"), dict)
                        else {}
                    )
                    if not (
                        current_program is not None
                        and latest_observation is not None
                        and latest_observation.get("success") is True
                        and latest_observation_inspected
                        and _execution_output_has_valid_reimport(execution_output)
                    ):
                        raise EpisodeContractError(
                            "completed requires a successful, inspected, STEP-reimport-validated execution observation",
                            rejection_stage="reviewable_completion_validation",
                            reason_code="completion_evidence_incomplete",
                            rejected_action=action.action,
                            human_safe_detail="The Agent tried to complete before the required execution and inspection evidence existed.",
                        )
                    self.writer.event(
                        {
                            "step": steps,
                            "action": action.action,
                            "stop_reason": reason.value,
                            "candidate_id": current_candidate_id,
                            "observation_id": latest_observation_id,
                        }
                    )
                    return finish(
                        reason,
                        result_kind="model_program",
                        output_validated=True,
                    )
                if reason.value not in self.capabilities.allowed_stop_reasons:
                    raise EpisodeContractError(
                        "stop reason is not enabled for the active skill",
                        rejection_stage="skill_action_authorization",
                        reason_code="stop_reason_not_allowed_for_skill",
                        rejected_action=action.action,
                        requested_capability_or_context=reason.value,
                    )
                self.writer.event({"step": steps, "action": action.action, "stop_reason": reason.value, "reason": action.reason})
                return finish(
                    reason,
                    failure_diagnostic=(
                        _agent_reported_policy_block_diagnostic(action.action)
                        if reason == StopReason.POLICY_BLOCKED
                        and latest_failure_diagnostic is None
                        else None
                    ),
                )

            raise UnknownAgentActionError(
                f"unknown agent action: {action.action!r}",
                reason_code="action_not_registered",
                rejected_action=action.action,
                requested_capability_or_context=action.action,
            )


class DeterministicCreatePartIRProposer:
    """Minimal Phase 1 proposer wrapper around the existing deterministic adapter."""

    def __init__(self, adapter: Any, handoff: dict[str, Any], adapter_context: dict[str, Any]) -> None:
        self.adapter = adapter
        self.handoff = handoff
        self.adapter_context = adapter_context
        self._phase = 0

    def __call__(self, state: dict[str, Any]) -> AgentAction:
        if self._phase == 0:
            self._phase += 1
            return AgentAction(action="request_context", context_key="reviewed_part_handoff", reason="Confirm the approved selected-part handoff.")
        if self._phase == 1:
            self._phase += 1
            contract = self.adapter.create_part_ir(self.handoff, context=self.adapter_context)
            return AgentAction(
                action="submit_contract", contract_type="cad_ir_draft", contract=contract,
                summary="Deterministic CAD IR draft from the reviewed handoff.",
            )
        if self._phase == 2:
            self._phase += 1
            return AgentAction(action="request_validation", reason="Validate the submitted CAD IR through the existing validator.")
        return AgentAction(action="stop", stop_reason=StopReason.VALIDATION_EXHAUSTED, reason="No repair proposer is enabled in minimal Phase 1.")


class ProviderSelectedDesignPartSupplier:
    """Ask a provider adapter to choose every next design_part action."""

    def __init__(self, adapter: Any, skill: SkillDefinition) -> None:
        choose = getattr(adapter, "choose_design_action", None)
        if not callable(choose):
            raise TypeError(
                "provider-selected design requires choose_design_action"
            )
        self.adapter = adapter
        self.skill = skill

    def __call__(self, state: dict[str, Any]) -> AgentAction | dict[str, Any]:
        return self.adapter.choose_design_action(
            state=state,
            skill_manifest=self.skill.manifest(),
        )


def build_create_part_ir_context(
    handoff: dict[str, Any], *, run_id: str, execution_request: dict[str, Any],
) -> tuple[ContextEnvelope, ContextBroker]:
    """Create a compact, in-memory active-lineage context set for this slice."""

    context = handoff.get("preserved_assembly_context")
    context = context if isinstance(context, dict) else {}
    source_review = handoff.get("source_review")
    source_request = handoff.get("source_part_request")
    part_id = str(handoff.get("part_id") or "reviewed_part")
    source_type = "accepted_active_lineage"
    items = [
        ContextItem("reviewed_part_handoff", run_id, "reviewed_part_handoff", source_type,
                    {"part_id": part_id, "status": handoff.get("status"), "interface_constraint_count": len(handoff.get("interface_constraints", [])) if isinstance(handoff.get("interface_constraints"), list) else 0}, handoff),
        ContextItem("assembly_plan", run_id, "assembly_plan", source_type,
                    {"assembly_scope": context.get("assembly_scope"), "related_parts": list(context.get("related_parts", []))[:8] if isinstance(context.get("related_parts"), list) else []}, context),
        ContextItem("requirement_active", run_id, "requirement", source_type,
                    {"part_id": part_id, "part_brief": _short_text(handoff.get("part_brief"))}, {"part_id": part_id, "part_brief": handoff.get("part_brief")}),
        ContextItem("user_stage_review", run_id, "part_request_review", source_type,
                    {"source_review": source_review, "source_part_request": source_request}, {"source_review": source_review, "source_part_request": source_request}),
        ContextItem("previous_cad_ir_attempts", run_id, "cad_ir_draft", source_type, {"attempt_count": 0}, {}),
        ContextItem("previous_validation_feedback", run_id, "cad_ir_validation", source_type, {"validation_count": 0}, {}),
    ]
    broker = ContextBroker(items)
    envelope = ContextEnvelope(
        objective=AgentObjective("create_part_ir", f"Create a reviewed CAD IR draft for {part_id}", checkpoint="cad_ir_draft"),
        workflow={"checkpoint": "cad_ir_draft", "active_root_run_id": run_id, "active_leaf_run_id": run_id, "source_handoff": "reviewed_part_handoff.json"},
        accepted_decisions=("The selected part passed the reviewed handoff gate.",),
        selected_part={"part_id": part_id, "review_status": handoff.get("status")},
        constraints=("Output must be CAD IR, not executable Python.", "Only validated CAD IR may execute."),
        previous_attempts=(), available_context=broker.available_keys,
    )
    return envelope, broker


def run_create_part_ir_episode(
    *, adapter: Any, handoff: dict[str, Any], execution_request: dict[str, Any],
    adapter_context: dict[str, Any], artifact_dir: Path, budget: EpisodeBudget | None = None,
) -> AgentEpisodeResult:
    envelope, broker = build_create_part_ir_context(handoff, run_id=artifact_dir.name, execution_request=execution_request)

    orchestrator = EpisodeOrchestrator(
        objective=envelope.objective, context_envelope=envelope, context_broker=broker,
        capabilities=AgentCapabilities(), budget=budget or EpisodeBudget(),
        validate_contract=None, artifact_dir=artifact_dir,
    )
    return orchestrator.run(DeterministicCreatePartIRProposer(adapter, handoff, adapter_context))


def build_design_part_context(
    handoff: dict[str, Any],
    *,
    run_id: str,
    objective_summary: str | None = None,
) -> tuple[ContextEnvelope, ContextBroker]:
    """Project a reviewed legacy handoff into target semantic context keys."""
    part_id = str(handoff.get("part_id") or "reviewed_part")
    work_id = (
        handoff.get("work_id")
        if isinstance(handoff.get("work_id"), str)
        else None
    )
    preserved = handoff.get("preserved_assembly_context")
    preserved = preserved if isinstance(preserved, dict) else {}
    interfaces = handoff.get("interface_constraints")
    interfaces = interfaces if isinstance(interfaces, list) else []
    source_type = "accepted_active_lineage"
    items = [
        ContextItem(
            "intent_active",
            run_id,
            "intent_snapshot",
            source_type,
            {"part_id": part_id, "part_brief": _short_text(handoff.get("part_brief"))},
            {"part_id": part_id, "part_brief": handoff.get("part_brief")},
            work_id=work_id,
            part_job_id=part_id,
        ),
        ContextItem(
            "part_job",
            run_id,
            "part_job",
            source_type,
            {"part_id": part_id, "status": handoff.get("status")},
            {
                "part_id": part_id,
                "status": handoff.get("status"),
                "role": handoff.get("role"),
                "preserved_context": preserved,
            },
            work_id=work_id,
            part_job_id=part_id,
        ),
        ContextItem(
            "part_interfaces",
            run_id,
            "part_interfaces",
            source_type,
            {"part_id": part_id, "interface_count": len(interfaces)},
            {"part_id": part_id, "interfaces": interfaces},
            work_id=work_id,
            part_job_id=part_id,
        ),
        ContextItem(
            "previous_candidates",
            run_id,
            "geometry_candidate",
            "episode_observation",
            {"candidate_count": 0},
            {},
            work_id=work_id,
            part_job_id=part_id,
            trust_role="observation",
        ),
        ContextItem(
            "previous_validation_observations",
            run_id,
            "contract_validation",
            "episode_observation",
            {"observation_count": 0},
            {},
            work_id=work_id,
            part_job_id=part_id,
            trust_role="observation",
        ),
        ContextItem(
            "user_acceptance_or_revision",
            run_id,
            "user_decision",
            source_type,
            {"review_status": handoff.get("status")},
            {"review_status": handoff.get("status")},
            work_id=work_id,
            part_job_id=part_id,
        ),
    ]
    broker = ContextBroker(items)
    envelope = ContextEnvelope(
        objective=AgentObjective(
            "design_part",
            objective_summary or f"Design a structured candidate for {part_id}",
            work_id=work_id,
            checkpoint="geometry_candidate",
        ),
        workflow={
            "checkpoint": "geometry_candidate",
            "active_root_run_id": run_id,
            "active_leaf_run_id": run_id,
            "source_handoff": "reviewed_part_handoff.json",
        },
        accepted_decisions=("The selected Part Job handoff is active.",),
        selected_part={"part_id": part_id, "review_status": handoff.get("status")},
        constraints=(
            "Choose a structured CAD IR compatibility candidate or an untrusted cadquery_v1 model program.",
            "Model programs execute only through the attested CadFlow Tool Broker and remain candidate evidence.",
            "No result becomes reviewable, accepted, or deliverable in this episode.",
        ),
        previous_attempts=(),
        available_context=broker.available_keys,
    )
    return envelope, broker


def run_design_part_episode(
    *,
    adapter: Any,
    handoff: dict[str, Any],
    artifact_dir: Path,
    budget: EpisodeBudget | None = None,
    validate_contract: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    tool_broker: CadFlowToolBroker | None = None,
    run_id: str | None = None,
    objective_summary: str | None = None,
) -> AgentEpisodeResult:
    """Run a provider-selected contract or attested model-program action loop."""
    skill = RUNTIME_SKILL_REGISTRY.for_operation("design_part")
    envelope, broker = build_design_part_context(
        handoff,
        run_id=run_id or artifact_dir.name,
        objective_summary=objective_summary,
    )
    limits = skill.budget
    episode_budget = budget or EpisodeBudget(
        max_steps=limits.max_steps,
        max_context_requests=limits.max_context_requests,
        max_context_bytes=limits.max_context_bytes,
        max_contract_submissions=limits.max_contract_submissions,
        max_repair_attempts=limits.max_repair_attempts,
        max_source_submissions=limits.max_source_submissions,
        max_executions=limits.max_executions,
        max_observation_inspections=limits.max_observation_inspections,
        timeout_seconds=limits.timeout_seconds,
    )
    orchestrator = EpisodeOrchestrator(
        objective=envelope.objective,
        context_envelope=envelope,
        context_broker=broker,
        capabilities=AgentCapabilities.for_skill(
            skill,
            capability_mode="provider_selected_design_with_attested_model_program",
        ),
        budget=episode_budget,
        validate_contract=validate_contract,
        artifact_dir=artifact_dir,
        tool_broker=tool_broker,
        provider_identity=dict(getattr(adapter, "provider_identity", {}) or {}),
    )
    return orchestrator.run(ProviderSelectedDesignPartSupplier(adapter, skill))


def run_work_design_episode(
    *,
    adapter: Any,
    work_context: dict[str, Any],
    artifact_dir: Path,
    run_id: str,
    budget: EpisodeBudget | None = None,
) -> WorkDesignEpisodeResult:
    """Run the canonical Work-level design loop without Work mutation authority."""

    skill = RUNTIME_SKILL_REGISTRY.for_operation("work_design")
    work_id = str(work_context.get("work_id") or "")
    objective_text = str(work_context.get("description") or "").strip()
    if not work_id or not objective_text:
        raise ValueError("work_design requires a Work id and objective")
    answers = [
        deepcopy(item)
        for item in work_context.get("clarification_answers", [])
        if isinstance(item, dict)
    ]
    prior_design = (
        deepcopy(work_context.get("previous_work_design"))
        if isinstance(work_context.get("previous_work_design"), dict)
        else {}
    )
    items = [
        ContextItem(
            "work_request",
            run_id,
            "work_definition",
            "accepted_work_state",
            {"title": _short_text(work_context.get("title")), "objective": _short_text(objective_text)},
            {"title": work_context.get("title"), "objective": objective_text},
            work_id=work_id,
        ),
        ContextItem(
            "accepted_work_context",
            run_id,
            "accepted_work_context",
            "accepted_work_state",
            {
                "accepted_part_count": int(work_context.get("accepted_part_count") or 0),
                "existing_part_job_count": int(work_context.get("existing_part_job_count") or 0),
            },
            {
                "accepted_part_results": deepcopy(work_context.get("accepted_part_results") or {}),
                "existing_part_jobs": deepcopy(work_context.get("existing_part_jobs") or []),
            },
            work_id=work_id,
        ),
        ContextItem(
            "previous_work_design",
            run_id,
            "work_design",
            "accepted_work_state",
            {"present": bool(prior_design)},
            prior_design,
            work_id=work_id,
        ),
        ContextItem(
            "work_clarification_answers",
            run_id,
            "clarification_decision",
            "accepted_work_state",
            {"answer_count": len(answers)},
            {"answers": answers},
            work_id=work_id,
        ),
    ]
    broker = ContextBroker(items)
    envelope = ContextEnvelope(
        objective=AgentObjective(
            "work_design",
            objective_text,
            work_id=work_id,
            checkpoint="work_design",
        ),
        workflow={
            "work_id": work_id,
            "checkpoint": "work_design",
            "active_root_run_id": run_id,
            "active_leaf_run_id": run_id,
        },
        accepted_decisions=tuple(
            f"{item.get('field')}: {item.get('answer')}"
            for item in answers
            if item.get("field") and item.get("answer")
        ),
        selected_part={},
        constraints=(
            "CadFlow assigns Part Job and Run identities after validating the proposal.",
            "Reference components do not become generated Part Jobs.",
            "Assembly execution is not available in this milestone.",
        ),
        previous_attempts=(),
        available_context=broker.available_keys,
    )
    limits = skill.budget
    episode_budget = budget or EpisodeBudget(
        max_steps=limits.max_steps,
        max_context_requests=limits.max_context_requests,
        max_context_bytes=limits.max_context_bytes,
        max_contract_submissions=limits.max_contract_submissions,
        max_repair_attempts=limits.max_repair_attempts,
        max_source_submissions=0,
        max_executions=0,
        max_observation_inspections=0,
        timeout_seconds=limits.timeout_seconds,
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    provider_identity = _safe_provider_identity(
        dict(getattr(adapter, "provider_identity", {}) or {})
    )
    supplier = ProviderSelectedDesignPartSupplier(adapter, skill)
    episode_id = uuid4().hex
    started = time.monotonic()
    steps = context_requests = context_bytes = proposals = 0
    draft: dict[str, Any] | None = None
    supplied_context: list[dict[str, Any]] = []
    context_manifest: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    knowledge = RUNTIME_SKILL_REGISTRY.knowledge_for_skill(skill.skill_id)

    def persist_response(sequence: int, value: Any) -> None:
        entry = {
            "schema_version": 1,
            "sequence": sequence,
            "event_type": "agent_response",
            "provider_identity": provider_identity,
            **_safe_agent_response(value),
            "private_reasoning_exposed": False,
            "credential_material_exposed": False,
        }
        with (artifact_dir / "agent_exchange.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, sort_keys=True) + "\n")

    def finish(
        reason: StopReason,
        *,
        creation_requested: bool = False,
        failure_diagnostic: dict[str, Any] | None = None,
    ) -> WorkDesignEpisodeResult:
        completed = reason == StopReason.COMPLETED and draft is not None and creation_requested
        result = WorkDesignEpisodeResult(
            episode_id=episode_id,
            status="completed" if completed else "safely_blocked",
            stop_reason=reason,
            step_count=steps,
            context_request_count=context_requests,
            context_byte_count=context_bytes,
            proposal_count=proposals,
            work_design=deepcopy(draft),
            part_job_creation_requested=creation_requested,
            failure_diagnostic=deepcopy(failure_diagnostic),
            skill_id=skill.skill_id,
            skill_version=skill.version,
        )
        knowledge_manifest = [
            {
                "knowledge_id": item.knowledge_id,
                "scope": item.scope,
                "source": item.source,
                "sha256": _sha256_text(item.load_content()),
            }
            for item in knowledge
        ]
        episode = {
            **result.as_dict(),
            "provider_identity": provider_identity,
            "objective": {"operation": "work_design", "summary": objective_text},
            "knowledge": knowledge_manifest,
            "context_is_work_specific": True,
            "knowledge_is_static": True,
        }
        _write_json(artifact_dir / "agent_episode.json", episode)
        _write_json(
            artifact_dir / "context_manifest.json",
            {"schema_version": 1, "items": context_manifest},
        )
        _write_json(
            artifact_dir / "tool_broker_manifest.json",
            {
                "schema_version": 1,
                "active_skill_id": skill.skill_id,
                "allowed_tools": [],
                "side_effect_authority": "none",
            },
        )
        (artifact_dir / "agent_events.jsonl").write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in events),
            encoding="utf-8",
        )
        _write_json(
            artifact_dir / "agent_result.json",
            {**result.as_dict(), "work_design": draft},
        )
        return result

    state = "created"
    while True:
        if time.monotonic() - started >= episode_budget.timeout_seconds or steps >= episode_budget.max_steps:
            events.append({"step": steps, "observation": "budget_exhausted"})
            return finish(StopReason.BUDGET_EXHAUSTED)
        provider_state = {
            "state": state,
            "context_envelope": envelope.as_dict(),
            "supplied_context": supplied_context,
            "work_design": draft,
        }
        try:
            supplied_action = supplier(provider_state)
        except Exception as exc:
            events.append(
                {
                    "event_type": "system_observation",
                    "step": steps,
                    "observation": "provider_failure",
                    "error_type": type(exc).__name__,
                }
            )
            return finish(StopReason.PROVIDER_FAILURE)
        persist_response(steps + 1, supplied_action)
        action = AgentAction.from_value(supplied_action)
        if action.action not in skill.allowed_actions:
            raise UnknownAgentActionError(
                f"action is not enabled for this episode: {action.action}",
                rejection_stage="skill_action_authorization",
                reason_code="action_not_allowed_for_skill",
                rejected_action=action.action,
                requested_capability_or_context=action.action,
                human_safe_detail=(
                    "The Agent requested an action that the Work Design Skill does not allow."
                ),
            )
        steps += 1
        if action.action == "request_context":
            if context_requests >= episode_budget.max_context_requests:
                return finish(StopReason.BUDGET_EXHAUSTED)
            if not action.context_key:
                raise EpisodeContractError(
                    "request_context requires context_key",
                    reason_code="missing_context_key",
                    rejected_action=action.action,
                )
            item = broker.resolve(
                action.context_key,
                allowed_keys=skill.allowed_context_keys,
                expected_work_id=work_id,
            )
            encoded_size = len(json.dumps(item.content, sort_keys=True).encode("utf-8"))
            if context_bytes + encoded_size > episode_budget.max_context_bytes:
                return finish(StopReason.BUDGET_EXHAUSTED)
            context_requests += 1
            context_bytes += encoded_size
            entry = item.manifest_entry()
            if entry not in context_manifest:
                context_manifest.append(entry)
            supplied_context.append({**entry, "content": item.content})
            events.append(
                {
                    "event_type": "agent_action",
                    "step": steps,
                    "action": action.action,
                    "context_key": item.context_key,
                    "reason": action.reason,
                }
            )
            state = "gathering_context"
            continue
        if action.action == "propose_work_design":
            if proposals >= episode_budget.max_contract_submissions:
                return finish(StopReason.BUDGET_EXHAUSTED)
            assert action.work_design is not None
            draft = validate_work_design_proposal(action.work_design)
            proposals += 1
            _write_json(
                artifact_dir / "work_design_submissions" / f"submission_{proposals:03d}.json",
                draft,
            )
            events.append(
                {
                    "event_type": "agent_action",
                    "step": steps,
                    "action": action.action,
                    "proposal_summary": action.summary or draft["concept_summary"],
                    "generated_part_count": len(draft["generated_parts"]),
                    "reference_component_count": len(draft["reference_components"]),
                    "assumptions": list(draft["assumptions"]),
                }
            )
            state = "work_design_proposed"
            continue
        if action.action == "create_part_jobs":
            if draft is None:
                raise EpisodeContractError(
                    "create_part_jobs requires a valid Work Design proposal",
                    rejection_stage="episode_action_ordering",
                    reason_code="work_design_proposal_missing",
                    rejected_action=action.action,
                )
            if draft["unresolved_questions"]:
                raise EpisodeContractError(
                    "create_part_jobs requires no unresolved material questions",
                    rejection_stage="episode_action_ordering",
                    reason_code="work_design_questions_unresolved",
                    rejected_action=action.action,
                )
            events.append(
                {
                    "event_type": "agent_action",
                    "step": steps,
                    "action": action.action,
                    "requested_generated_part_count": len(draft["generated_parts"]),
                    "provider_mutation_authority": False,
                }
            )
            return finish(StopReason.COMPLETED, creation_requested=True)
        if action.action == "ask_user":
            _write_json(
                artifact_dir / "user_input_request.json",
                {
                    "schema_version": 1,
                    "checkpoint": "clarification_decision",
                    "scope": "work",
                    "status": "user_input_required",
                    "questions": [dict(item) for item in action.questions],
                    "why_it_matters": action.reason,
                    "private_reasoning_exposed": False,
                },
            )
            events.append(
                {
                    "event_type": "agent_action",
                    "step": steps,
                    "action": action.action,
                    "scope": "work",
                    "questions": list(action.questions),
                    "reason": action.reason,
                }
            )
            return finish(StopReason.USER_INPUT_REQUIRED)
        if action.action == "stop":
            reason = action.stop_reason or StopReason.INSUFFICIENT_CONTEXT
            if reason == StopReason.COMPLETED:
                raise EpisodeContractError(
                    "work_design completes only through create_part_jobs",
                    rejection_stage="episode_action_ordering",
                    reason_code="work_design_completion_action_required",
                    rejected_action=action.action,
                )
            if reason.value not in skill.stop_reasons:
                raise EpisodeContractError(
                    "stop reason is not enabled for the active skill",
                    rejection_stage="skill_action_authorization",
                    reason_code="stop_reason_not_allowed_for_skill",
                    rejected_action=action.action,
                    requested_capability_or_context=reason.value,
                )
            events.append(
                {
                    "event_type": "agent_action",
                    "step": steps,
                    "action": action.action,
                    "stop_reason": reason.value,
                    "reason": action.reason,
                }
            )
            return finish(
                reason,
                failure_diagnostic=(
                    _agent_reported_policy_block_diagnostic(action.action)
                    if reason == StopReason.POLICY_BLOCKED
                    else None
                ),
            )
        raise UnknownAgentActionError(
            f"unknown work_design action: {action.action!r}",
            reason_code="action_not_registered",
            rejected_action=action.action,
            requested_capability_or_context=action.action,
        )


def validate_work_design_proposal(value: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the small provider-authored Work Design contract."""

    if not isinstance(value, dict):
        raise EpisodeContractError(
            "work_design must be an object",
            reason_code="invalid_work_design_contract",
            rejected_action="propose_work_design",
        )
    allowed = {
        "objective",
        "concept_summary",
        "generated_parts",
        "reference_components",
        "interfaces",
        "dependencies",
        "assumptions",
        "unresolved_questions",
        "assembly_expected",
        "recommendation",
    }
    if set(value) != allowed:
        raise EpisodeContractError(
            "work_design fields do not match the canonical contract",
            reason_code="invalid_work_design_contract",
            rejected_action="propose_work_design",
            requested_capability_or_context=_first_safe_identifier(
                set(value) ^ allowed
            ),
            human_safe_detail="The Agent's Work Design fields did not match the typed Work Design contract.",
        )
    for forbidden in ("part_job_id", "run_id", "work_id", "manifest", "path", "command"):
        if _contains_key(value, forbidden):
            raise EpisodeContractError(
                "provider Work Design cannot supply product identities or side effects",
                rejection_stage="work_design_authority",
                reason_code="work_design_authority_violation",
                rejected_action="propose_work_design",
                requested_capability_or_context=forbidden,
                human_safe_detail="The Agent tried to supply a product identity or side effect that CadFlow owns.",
            )
    objective = _required_bounded_text(value["objective"], "objective", 2_000)
    concept = _required_bounded_text(value["concept_summary"], "concept_summary", 4_000)
    recommendation = _required_bounded_text(value["recommendation"], "recommendation", 1_000)
    raw_parts = value["generated_parts"]
    if not isinstance(raw_parts, list) or not 1 <= len(raw_parts) <= 12:
        raise _work_design_contract_error(
            "work_design requires one to twelve generated Parts",
            "generated_parts",
        )
    generated_parts: list[dict[str, Any]] = []
    keys: set[str] = set()
    for raw in raw_parts:
        if not isinstance(raw, dict) or set(raw) != {"key", "name", "role", "interfaces", "dependencies"}:
            raise _work_design_contract_error(
                "generated Part fields do not match the canonical contract",
                "generated_parts",
            )
        key = _required_bounded_text(raw["key"], "generated Part key", 120)
        if key in keys:
            raise _work_design_contract_error(
                "generated Part keys must be unique",
                "generated_parts.key",
            )
        keys.add(key)
        generated_parts.append(
            {
                "key": key,
                "name": _required_bounded_text(raw["name"], "generated Part name", 200),
                "role": _required_bounded_text(raw["role"], "generated Part role", 1_000),
                "interfaces": _bounded_text_list(raw["interfaces"], "generated Part interfaces", 24, 1_000),
                "dependencies": _bounded_text_list(raw["dependencies"], "generated Part dependencies", 12, 500),
            }
        )
    raw_references = value["reference_components"]
    if not isinstance(raw_references, list) or len(raw_references) > 24:
        raise _work_design_contract_error(
            "reference_components must be a bounded list",
            "reference_components",
        )
    reference_components: list[dict[str, Any]] = []
    for raw in raw_references:
        if not isinstance(raw, dict) or set(raw) != {"name", "role", "interfaces"}:
            raise _work_design_contract_error(
                "reference component fields do not match the canonical contract",
                "reference_components",
            )
        reference_components.append(
            {
                "name": _required_bounded_text(raw["name"], "reference component name", 200),
                "role": _required_bounded_text(raw["role"], "reference component role", 1_000),
                "interfaces": _bounded_text_list(raw["interfaces"], "reference component interfaces", 24, 1_000),
            }
        )
    interfaces = _bounded_relation_list(value["interfaces"], "interfaces", 48)
    dependencies = _bounded_relation_list(value["dependencies"], "dependencies", 24)
    if not isinstance(value["assembly_expected"], bool):
        raise _work_design_contract_error(
            "assembly_expected must be boolean",
            "assembly_expected",
        )
    return {
        "schema_version": 1,
        "objective": objective,
        "concept_summary": concept,
        "generated_parts": generated_parts,
        "reference_components": reference_components,
        "interfaces": interfaces,
        "dependencies": dependencies,
        "assumptions": _bounded_text_list(value["assumptions"], "assumptions", 24, 1_000),
        "unresolved_questions": _bounded_text_list(value["unresolved_questions"], "unresolved_questions", 12, 1_000),
        "assembly_expected": value["assembly_expected"],
        "recommendation": recommendation,
    }


def _bounded_relation_list(value: Any, label: str, maximum: int) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > maximum:
        raise _work_design_contract_error(f"{label} must be a bounded list", label)
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"from", "to", "description"}:
            raise _work_design_contract_error(
                f"{label} entries require from, to, and description",
                label,
            )
        result.append(
            {
                "from": _required_bounded_text(item["from"], f"{label} from", 200),
                "to": _required_bounded_text(item["to"], f"{label} to", 200),
                "description": _required_bounded_text(item["description"], f"{label} description", 1_000),
            }
        )
    return result


def _bounded_text_list(value: Any, label: str, maximum: int, item_limit: int) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise _work_design_contract_error(f"{label} must be a bounded list", label)
    return [_required_bounded_text(item, label, item_limit) for item in value]


def _required_bounded_text(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise _work_design_contract_error(
            f"{label} must be non-empty bounded text",
            label,
        )
    return value.strip()


def _work_design_contract_error(message: str, field: str) -> EpisodeContractError:
    return EpisodeContractError(
        message,
        reason_code="invalid_work_design_contract",
        rejected_action="propose_work_design",
        requested_capability_or_context=field,
        human_safe_detail=(
            "The Agent's Work Design did not match the bounded Work Design contract."
        ),
    )


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def _safe_provider_identity(value: dict[str, Any]) -> dict[str, Any]:
    allowed = {"provider", "model", "network_mode", "transport"}
    return {
        key: item
        for key, item in value.items()
        if key in allowed and isinstance(item, (str, int, float, bool, type(None)))
    }


def _safe_agent_response(value: Any) -> dict[str, Any]:
    if isinstance(value, AgentAction):
        raw = {
            "action": value.action,
            "context_key": value.context_key,
            "reason": value.reason,
            "contract_type": value.contract_type,
            "stop_reason": value.stop_reason.value if value.stop_reason else None,
            "summary": value.summary,
            "questions": list(value.questions),
            "assumptions": list(value.assumptions),
            "model_program": value.model_program,
            "contract": value.contract,
            "work_design": value.work_design,
        }
    elif isinstance(value, dict):
        raw = value
    else:
        return {"contract_status": "invalid", "response_type": type(value).__name__}
    allowed = {
        "action", "context_key", "reason", "contract_type", "stop_reason",
        "summary", "questions", "assumptions",
    }
    result: dict[str, Any] = {
        key: sanitize_provider_payload(raw[key])
        for key in allowed
        if key in raw
    }
    blocked_field_tokens = (
        "authorization", "credential", "api_key", "secret", "token",
        "password", "cookie", "reasoning", "chain_of_thought",
    )
    result["received_fields"] = sorted(
        str(key) for key in raw
        if not any(token in str(key).lower() for token in blocked_field_tokens)
    )
    result["contract_status"] = "received"
    program = raw.get("model_program")
    if isinstance(program, dict):
        source = program.get("source")
        parameters = program.get("parameters")
        result["model_program"] = {
            "api_id": program.get("api_id"),
            "requested_outputs": program.get("requested_outputs"),
            "source_hash": _sha256_text(source) if isinstance(source, str) else None,
            "parameters_hash": _sha256_json(parameters) if isinstance(parameters, dict) else None,
            "source_retained": False,
            "parameters_retained": False,
        }
    contract = raw.get("contract")
    if isinstance(contract, dict):
        result["contract"] = {
            "sha256": _sha256_json(contract),
            "top_level_fields": sorted(
                str(key) for key in contract
                if not any(token in str(key).lower() for token in blocked_field_tokens)
            ),
            "content_retained": False,
        }


    work_design = raw.get("work_design")
    if isinstance(work_design, dict):
        result["work_design"] = {
            "sha256": _sha256_json(work_design),
            "concept_summary": _short_text(work_design.get("concept_summary")),
            "generated_part_count": len(work_design.get("generated_parts", []))
            if isinstance(work_design.get("generated_parts"), list)
            else 0,
            "reference_component_count": len(work_design.get("reference_components", []))
            if isinstance(work_design.get("reference_components"), list)
            else 0,
            "content_retained_in": "work_design.json",
        }
    return result


def _reject_execution_fields(
    value: Any,
    path: str = "",
    *,
    rejected_action: str | None = None,
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key).lower() in _FORBIDDEN_EXECUTION_FIELDS:
                raise EpisodeContractError(
                    f"submitted contract contains forbidden execution field: {child_path}",
                    rejection_stage="action_contract_validation",
                    reason_code="structured_contract_execution_field",
                    rejected_action=rejected_action,
                    requested_capability_or_context=child_path,
                    human_safe_detail=(
                        "The Agent placed an executable-source field inside a structured geometry action."
                    ),
                )
            _reject_execution_fields(
                child,
                child_path,
                rejected_action=rejected_action,
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_execution_fields(
                child,
                f"{path}[{index}]",
                rejected_action=rejected_action,
            )


def _contract_summary(contract: dict[str, Any]) -> str:
    return f"{contract.get('part_name') or contract.get('part_type') or 'CAD IR'} draft"


def _feedback_summary(feedback: dict[str, Any]) -> dict[str, Any]:
    errors = feedback.get("errors") if isinstance(feedback.get("errors"), list) else []
    return {"valid": feedback.get("valid"), "codes": [item.get("code") for item in errors if isinstance(item, dict) and isinstance(item.get("code"), str)]}


def _validate_model_program_action(
    value: Any,
    *,
    rejected_action: str | None = None,
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "api_id",
        "source",
        "parameters",
        "requested_outputs",
    }:
        raise EpisodeContractError(
            "model-program submission requires exactly api_id, source, parameters, and requested_outputs",
            reason_code="invalid_model_program_contract",
            rejected_action=rejected_action,
            human_safe_detail=(
                "The Agent's model-program action did not match the typed model-program contract."
            ),
        )
    if value.get("api_id") != "cadquery_v1":
        raise EpisodeContractError(
            "model-program api_id must be cadquery_v1",
            rejection_stage="skill_action_authorization",
            reason_code="model_program_api_not_allowed",
            rejected_action=rejected_action,
            requested_capability_or_context=value.get("api_id"),
            human_safe_detail="The Agent requested a model-program API that this Skill does not allow.",
        )
    if not isinstance(value.get("source"), str) or not value["source"]:
        raise EpisodeContractError(
            "model-program source must be a non-empty string",
            reason_code="invalid_model_program_contract",
            rejected_action=rejected_action,
        )
    if not isinstance(value.get("parameters"), dict):
        raise EpisodeContractError(
            "model-program parameters must be an object",
            reason_code="invalid_model_program_contract",
            rejected_action=rejected_action,
        )
    try:
        validate_model_program_parameters(value["parameters"])
    except ValueError as exc:
        raise EpisodeContractError(
            str(exc),
            reason_code="invalid_model_program_parameters",
            rejected_action=rejected_action,
            human_safe_detail="The Agent returned model parameters outside the typed JSON contract.",
        ) from exc
    if value.get("requested_outputs") != ["step"]:
        raise EpisodeContractError(
            "model-program requested_outputs must be exactly ['step']",
            rejection_stage="skill_action_authorization",
            reason_code="model_program_output_not_allowed",
            rejected_action=rejected_action,
            requested_capability_or_context=_first_safe_identifier(
                value.get("requested_outputs")
            ),
            human_safe_detail="The Agent requested a model-program output that this Skill does not allow.",
        )


def _provider_execution_observation(value: dict[str, Any]) -> dict[str, Any]:
    output = value.get("output") if isinstance(value.get("output"), dict) else {}
    return {
        "success": value.get("success") is True,
        "observation_type": value.get("observation_type"),
        "codes": list(value.get("codes") or ()),
        "execution_profile": value.get("execution_profile"),
        "side_effect_started": value.get("side_effect_started") is True,
        "exit_state": value.get("exit_state"),
        "attestation_digest": value.get("attestation_digest"),
        "candidate_id": output.get("candidate_id"),
        "execution_id": output.get("execution_id"),
        "source_hash": output.get("source_hash"),
        "parameters_hash": output.get("parameters_hash"),
        "profile_digest": output.get("profile_digest"),
        "toolchain_digest": output.get("toolchain_digest"),
        "geometry": output.get("geometry") if isinstance(output.get("geometry"), dict) else {},
        "step_reimport": output.get("step_reimport") if isinstance(output.get("step_reimport"), dict) else {},
        "outputs": [
            {
                "name": item.get("name"),
                "sha256": item.get("sha256"),
                "size": item.get("size"),
            }
            for item in (output.get("outputs") or [])
            if isinstance(item, dict)
        ],
    }


def _execution_output_has_valid_reimport(value: dict[str, Any]) -> bool:
    geometry = value.get("geometry")
    reimport = value.get("step_reimport")
    imported_geometry = reimport.get("geometry") if isinstance(reimport, dict) else None
    outputs = value.get("outputs")
    step = outputs[0] if isinstance(outputs, list) and len(outputs) == 1 else None
    return bool(
        isinstance(geometry, dict)
        and geometry.get("valid") is True
        and isinstance(geometry.get("solid_count"), int)
        and geometry["solid_count"] >= 1
        and isinstance(reimport, dict)
        and reimport.get("valid") is True
        and isinstance(imported_geometry, dict)
        and imported_geometry.get("valid") is True
        and imported_geometry.get("solid_count") == geometry.get("solid_count")
        and isinstance(step, dict)
        and step.get("name") == "model.step"
        and isinstance(step.get("sha256"), str)
        and len(step["sha256"]) == 64
        and isinstance(step.get("size"), int)
        and step["size"] > 0
        and isinstance(value.get("source_hash"), str)
        and isinstance(value.get("parameters_hash"), str)
        and isinstance(value.get("profile_digest"), str)
        and isinstance(value.get("toolchain_digest"), str)
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _short_text(value: Any) -> str:
    return str(value or "").strip()[:240]


def _safe_diagnostic_identifier(
    value: Any,
    fallback: str | None = None,
) -> str | None:
    """Keep diagnostic identity bounded and free of source/prose payloads."""

    if not isinstance(value, str):
        return fallback
    text = value.strip()
    if not text or len(text) > 120:
        return fallback
    if not all(character.isalnum() or character in "_.:-[]" for character in text):
        return fallback
    return text


def _first_safe_identifier(values: Any) -> str | None:
    if not isinstance(values, (set, frozenset, list, tuple)):
        return None
    return next(
        (
            safe
            for safe in (
                _safe_diagnostic_identifier(value)
                for value in sorted(str(item) for item in values)
            )
            if safe is not None
        ),
        None,
    )


def _agent_reported_policy_block_diagnostic(
    rejected_action: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "rejection_stage": "agent_typed_stop",
        "rejected_action": _safe_diagnostic_identifier(rejected_action),
        "reason_code": "agent_reported_policy_block",
        "requested_capability_or_context": None,
        "human_safe_detail": (
            "The Agent reported a policy block; CadFlow recorded no local rejection fact."
        ),
        "side_effect_started": False,
    }


def _tool_rejection_diagnostic(
    observation: dict[str, Any],
    *,
    rejected_action: str,
) -> dict[str, Any]:
    observation_type = _safe_diagnostic_identifier(
        observation.get("observation_type"), "tool_observation_failed"
    )
    codes = observation.get("codes")
    reason_code = _first_safe_identifier(codes) or observation_type
    stage = {
        "policy_blocked": "tool_authorization",
        "sandbox_policy_rejected": "generated_code_policy",
        "tool_input_rejected": "tool_input_validation",
        "sandbox_unavailable": "local_execution_environment",
        "model_program_execution_failed": "local_execution_runtime",
        "sandbox_protocol_error": "local_execution_runtime",
    }.get(observation_type, "tool_execution")
    details = {
        "tool_authorization": "CadFlow rejected a tool request outside the active Skill authority.",
        "generated_code_policy": "The generated CAD program did not pass the local source policy.",
        "tool_input_validation": "The requested tool call did not match CadFlow's typed tool contract.",
        "local_execution_environment": "The isolated local CAD execution environment was unavailable.",
        "local_execution_runtime": "The isolated local CAD runtime could not complete the candidate.",
        "tool_execution": "A CadFlow tool returned a typed failed observation.",
    }
    return {
        "schema_version": 1,
        "rejection_stage": stage,
        "rejected_action": _safe_diagnostic_identifier(rejected_action),
        "reason_code": reason_code,
        "requested_capability_or_context": _safe_diagnostic_identifier(
            observation.get("tool_id")
        ),
        "human_safe_detail": details[stage],
        "side_effect_started": observation.get("side_effect_started") is True,
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
