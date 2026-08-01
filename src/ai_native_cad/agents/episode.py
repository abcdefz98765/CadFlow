"""Bounded, provider-independent agent episodes for structured contracts.

This module deliberately contains no filesystem browsing, shell execution, or
CAD execution.  An adapter may propose actions; the orchestrator owns budgets,
state transitions, validation, and the compact audit trail.
"""

from __future__ import annotations

import json
import time
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
    STRUCTURED_CONTRACT_TOOL,
    CadFlowToolBroker,
)


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


class UnknownAgentActionError(ValueError):
    """Raised before an action outside the public allowlist can be processed."""


class EpisodeContractError(ValueError):
    """Raised when an action attempts to cross the structured contract boundary."""


ALLOWLISTED_ACTIONS = frozenset({
    "request_context",
    "create_contract",
    "patch_contract",
    "submit_contract",
    "request_validation",
    "repair_contract",
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
        )


@dataclass(frozen=True)
class EpisodeBudget:
    max_steps: int = 8
    max_context_requests: int = 4
    max_context_bytes: int = 65_536
    max_contract_submissions: int = 3
    max_repair_attempts: int = 2
    timeout_seconds: float = 180.0

    def __post_init__(self) -> None:
        if any(value < 0 for value in (
            self.max_steps, self.max_context_requests, self.max_context_bytes,
            self.max_contract_submissions, self.max_repair_attempts,
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
    assumptions: tuple[str, ...] = ()
    summary: str | None = None
    questions: tuple[dict[str, str], ...] = ()
    stop_reason: StopReason | None = None

    @classmethod
    def from_value(cls, value: "AgentAction | dict[str, Any]") -> "AgentAction":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise UnknownAgentActionError("agent action must be an object")
        action = value.get("action")
        if not isinstance(action, str) or action not in ALLOWLISTED_ACTIONS:
            raise UnknownAgentActionError(f"unknown agent action: {action!r}")
        raw_reason = value.get("stop_reason")
        try:
            stop_reason = StopReason(raw_reason) if raw_reason is not None else None
        except ValueError as exc:
            raise EpisodeContractError("stop action has an unknown typed stop reason") from exc
        assumptions = value.get("assumptions") or []
        questions = value.get("questions") or []
        contract = value.get("contract")
        if not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions):
            raise EpisodeContractError("action assumptions must be a list of strings")
        if not isinstance(questions, list) or not all(isinstance(item, dict) for item in questions):
            raise EpisodeContractError("ask_user questions must be a list of objects")
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
                "ask_user requires focused field and question values"
            )
        if contract is not None and not isinstance(contract, dict):
            raise EpisodeContractError("contract must be an object")
        return cls(
            action=action,
            context_key=value.get("context_key") if isinstance(value.get("context_key"), str) else None,
            reason=value.get("reason") if isinstance(value.get("reason"), str) else None,
            contract_type=value.get("contract_type") if isinstance(value.get("contract_type"), str) else None,
            contract=contract,
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
            raise EpisodeContractError("context requests must use an allowlisted semantic context key")
        if allowed_keys is not None and context_key not in allowed_keys:
            raise EpisodeContractError("active skill does not allow this semantic context key")
        item = self._items.get(context_key)
        if item is None:
            raise EpisodeContractError(f"active lineage does not provide context: {context_key}")
        if (
            expected_work_id is not None
            and item.work_id is not None
            and item.work_id != expected_work_id
        ):
            raise EpisodeContractError(
                "semantic context belongs to an unrelated Work"
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
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
    ) -> None:
        self.output_dir = output_dir
        self.envelope = envelope
        self.tool_broker_manifest = tool_broker_manifest
        self.events: list[dict[str, Any]] = []
        self.context_manifest: list[dict[str, Any]] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def event(self, value: dict[str, Any]) -> None:
        self.events.append(value)

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

    def finish(self, result: AgentEpisodeResult) -> None:
        episode = result.as_dict()
        episode["objective"] = {"operation": self.envelope.objective.operation, "summary": self.envelope.objective.summary}
        lineage = {
            "work_id": self.envelope.objective.work_id or self.envelope.workflow.get("work_id"),
            "run_id": self.envelope.workflow.get("active_leaf_run_id"),
            "parent_run_id": self.envelope.workflow.get("active_root_run_id"),
            "part_id": self.envelope.selected_part.get("part_id"),
            "source_handoff": self.envelope.workflow.get("source_handoff"),
            "accepted_submission_id": f"submission_{result.contract_submission_count:03d}" if result.validated else None,
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
            self.tool_broker.manifest(active_skill_id=capabilities.skill_id),
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
                active_skill_id=self.capabilities.skill_id
            )

    def run(self, supplier: ActionSupplier) -> AgentEpisodeResult:
        started = time.monotonic()
        episode_id = uuid4().hex
        steps = context_requests = context_bytes = submissions = repairs = 0
        draft: dict[str, Any] | None = None
        feedback: dict[str, Any] | None = None
        state = "created"
        supplied_context: list[dict[str, Any]] = []

        def finish(reason: StopReason, *, validated: bool = False) -> AgentEpisodeResult:
            status = "completed" if reason == StopReason.COMPLETED and validated else "safely_blocked"
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
            action = AgentAction.from_value(supplied_action)
            if action.action not in self.capabilities.allowed_actions:
                raise UnknownAgentActionError(f"action is not enabled for this episode: {action.action}")
            steps += 1

            if action.action == "request_context":
                if context_requests >= self.budget.max_context_requests:
                    self.writer.event({"step": steps, "action": action.action, "context_key": action.context_key, "reason": action.reason, "observation": "context_budget_exhausted"})
                    return finish(StopReason.BUDGET_EXHAUSTED)
                if not action.context_key:
                    raise EpisodeContractError("request_context requires context_key")
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
                        "submitted contract type is not enabled for this episode"
                    )
                _reject_execution_fields(action.contract)
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

            if action.action == "request_validation":
                if draft is None:
                    raise EpisodeContractError("request_validation requires a submitted contract")
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
                        "Tool Broker must return structured validation feedback"
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
                self.writer.event({"step": steps, "action": action.action, "questions": list(action.questions), "reason": action.reason})
                return finish(StopReason.USER_INPUT_REQUIRED)

            if action.action == "stop":
                reason = action.stop_reason or StopReason.INSUFFICIENT_CONTEXT
                if reason == StopReason.COMPLETED:
                    raise EpisodeContractError("only a successful validator result may complete an episode")
                if reason.value not in self.capabilities.allowed_stop_reasons:
                    raise EpisodeContractError(
                        "stop reason is not enabled for the active skill"
                    )
                self.writer.event({"step": steps, "action": action.action, "stop_reason": reason.value, "reason": action.reason})
                return finish(reason)

            raise UnknownAgentActionError(f"unknown agent action: {action.action!r}")


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
            "Only a structured CAD IR compatibility candidate is enabled.",
            "No CAD execution or model-program source is enabled.",
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
    """Run the first provider-selected M2 action loop without CAD execution."""
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
        timeout_seconds=limits.timeout_seconds,
    )
    orchestrator = EpisodeOrchestrator(
        objective=envelope.objective,
        context_envelope=envelope,
        context_broker=broker,
        capabilities=AgentCapabilities.for_skill(
            skill,
            capability_mode="provider_selected_structured_contract_preview",
        ),
        budget=episode_budget,
        validate_contract=validate_contract,
        artifact_dir=artifact_dir,
        tool_broker=tool_broker,
    )
    return orchestrator.run(ProviderSelectedDesignPartSupplier(adapter, skill))


def _reject_execution_fields(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key).lower() in _FORBIDDEN_EXECUTION_FIELDS:
                raise EpisodeContractError(f"submitted contract contains forbidden execution field: {child_path}")
            _reject_execution_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_execution_fields(child, f"{path}[{index}]")


def _contract_summary(contract: dict[str, Any]) -> str:
    return f"{contract.get('part_name') or contract.get('part_type') or 'CAD IR'} draft"


def _feedback_summary(feedback: dict[str, Any]) -> dict[str, Any]:
    errors = feedback.get("errors") if isinstance(feedback.get("errors"), list) else []
    return {"valid": feedback.get("valid"), "codes": [item.get("code") for item in errors if isinstance(item, dict) and isinstance(item.get("code"), str)]}


def _short_text(value: Any) -> str:
    return str(value or "").strip()[:240]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
