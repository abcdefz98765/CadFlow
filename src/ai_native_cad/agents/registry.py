"""Typed runtime registry for the first M2 design-part slice.

The registry constrains provider authority while leaving action choice to the
provider.  It deliberately exposes no model-program execution tool until an
enforceable sandbox profile exists.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class BudgetDefinition:
    max_steps: int
    max_context_requests: int
    max_context_bytes: int
    max_contract_submissions: int
    max_repair_attempts: int
    timeout_seconds: float


@dataclass(frozen=True)
class KnowledgeDefinition:
    knowledge_id: str
    scope: str
    source: str
    summary: str


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    version: str
    role: str
    phase: str
    checkpoints: tuple[str, ...]
    operations: tuple[str, ...]
    allowed_actions: frozenset[str]
    allowed_context_keys: frozenset[str]
    allowed_tools: frozenset[str]
    output_contract_types: frozenset[str]
    shared_knowledge_ids: tuple[str, ...]
    private_knowledge_ids: tuple[str, ...]
    stop_reasons: frozenset[str]
    prohibited_side_effects: tuple[str, ...]
    budget: BudgetDefinition
    system_rules: tuple[str, ...]
    action_contract_rules: tuple[str, ...]

    def manifest(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "allowed_actions",
            "allowed_context_keys",
            "allowed_tools",
            "output_contract_types",
            "stop_reasons",
        ):
            value[key] = sorted(value[key])
        return value

    def compile_system_prompt(self) -> str:
        return "\n".join(f"- {item}" for item in self.system_rules)

    def compile_action_contract(self) -> str:
        return "\n".join(f"- {item}" for item in self.action_contract_rules)


DESIGN_PART_SKILL = SkillDefinition(
    skill_id="design_part",
    version="0.1.0",
    role="geometry_agent",
    phase="design",
    checkpoints=("geometry_candidate", "contract_validation"),
    operations=("design_part",),
    allowed_actions=frozenset(
        {
            "request_context",
            "create_contract",
            "patch_contract",
            "request_validation",
            "ask_user",
            "stop",
        }
    ),
    allowed_context_keys=frozenset(
        {
            "intent_active",
            "part_job",
            "part_interfaces",
            "previous_candidates",
            "previous_validation_observations",
            "user_acceptance_or_revision",
        }
    ),
    # M2 package 1 validates a structured compatibility contract only.  Model
    # source and CAD execution remain unavailable until the Tool Broker sandbox.
    allowed_tools=frozenset({"validate_structured_contract"}),
    output_contract_types=frozenset({"cad_ir_draft"}),
    shared_knowledge_ids=("verification_state_vocabulary",),
    private_knowledge_ids=("design_part_structured_contract_strategy",),
    stop_reasons=frozenset(
        {
            "user_input_required",
            "unsupported_capability",
            "insufficient_context",
            "validation_exhausted",
            "budget_exhausted",
            "provider_failure",
            "policy_blocked",
        }
    ),
    prohibited_side_effects=(
        "No filesystem paths or arbitrary repository context.",
        "No Python, CAD source, shell, subprocess, network, or dependency installation.",
        "No Work mutation, execution, publication, acceptance, or deliverable authority.",
        "No fabricated validator, geometry, fit, tolerance, strength, or safety claims.",
    ),
    budget=BudgetDefinition(
        max_steps=10,
        max_context_requests=4,
        max_context_bytes=65_536,
        max_contract_submissions=3,
        max_repair_attempts=2,
        timeout_seconds=180.0,
    ),
    system_rules=(
        "Return exactly one JSON Agent action and no markdown or private reasoning.",
        "Choose the next action from the declared design_part action allowlist.",
        "Request semantic context only when it materially affects the design decision.",
        "Treat validator feedback as system evidence and decide whether to patch, change strategy, ask, or stop.",
        "Submit structured CAD IR compatibility contracts only; executable model source is unavailable.",
        "Do not claim that a validated contract is executed, reviewable, accepted, or production geometry.",
    ),
    action_contract_rules=(
        "request_context requires context_key.",
        "create_contract and patch_contract require contract_type='cad_ir_draft' and a contract object.",
        "request_validation validates the most recent submitted contract.",
        "ask_user requires focused questions when material information is missing.",
        "stop requires one declared typed stop_reason.",
        "Never return code, commands, paths, secrets, raw provider messages, or validator facts not supplied by CadFlow.",
    ),
)


class SkillRegistry:
    """Small authoritative registry; it is intentionally not a plugin system."""

    def __init__(
        self,
        skills: tuple[SkillDefinition, ...],
        knowledge: tuple[KnowledgeDefinition, ...],
    ) -> None:
        by_id: dict[str, SkillDefinition] = {}
        by_operation: dict[str, SkillDefinition] = {}
        knowledge_by_id = {item.knowledge_id: item for item in knowledge}
        if len(knowledge_by_id) != len(knowledge):
            raise ValueError("duplicate knowledge id")
        for skill in skills:
            if skill.skill_id in by_id:
                raise ValueError(f"duplicate skill id: {skill.skill_id}")
            by_id[skill.skill_id] = skill
            declared_knowledge = {
                *skill.shared_knowledge_ids,
                *skill.private_knowledge_ids,
            }
            if not declared_knowledge <= set(knowledge_by_id):
                raise ValueError(
                    f"skill references unknown knowledge: {skill.skill_id}"
                )
            for operation in skill.operations:
                if operation in by_operation:
                    raise ValueError(f"duplicate skill operation: {operation}")
                by_operation[operation] = skill
        self._by_id = MappingProxyType(by_id)
        self._by_operation = MappingProxyType(by_operation)
        self._knowledge_by_id = MappingProxyType(knowledge_by_id)

    def skill(self, skill_id: str) -> SkillDefinition:
        try:
            return self._by_id[skill_id]
        except KeyError as exc:
            raise ValueError(f"unknown skill id: {skill_id}") from exc

    def for_operation(self, operation: str) -> SkillDefinition:
        try:
            return self._by_operation[operation]
        except KeyError as exc:
            raise ValueError(f"no skill registered for operation: {operation}") from exc

    def knowledge_for_skill(
        self,
        skill_id: str,
        knowledge_id: str | None = None,
    ) -> tuple[KnowledgeDefinition, ...]:
        skill = self.skill(skill_id)
        allowed = (*skill.shared_knowledge_ids, *skill.private_knowledge_ids)
        if knowledge_id is not None:
            if knowledge_id not in allowed:
                raise ValueError(
                    "knowledge is not declared by the active skill"
                )
            allowed = (knowledge_id,)
        return tuple(self._knowledge_by_id[item] for item in allowed)


RUNTIME_KNOWLEDGE = (
    KnowledgeDefinition(
        knowledge_id="verification_state_vocabulary",
        scope="shared",
        source="knowledge/README.md",
        summary=(
            "Keep candidate, validated contract, executed geometry, reviewable "
            "result, accepted result, and deliverable states distinct."
        ),
    ),
    KnowledgeDefinition(
        knowledge_id="design_part_structured_contract_strategy",
        scope="skill_private",
        source=(
            "skills/design_part/knowledge/structured_contract_strategy.md"
        ),
        summary=(
            "Preserve intent and interfaces, use explicit units and dimensions, "
            "and ask or stop when the compatibility contract cannot express the design."
        ),
    ),
)


RUNTIME_SKILL_REGISTRY = SkillRegistry(
    (DESIGN_PART_SKILL,),
    RUNTIME_KNOWLEDGE,
)


__all__ = [
    "BudgetDefinition",
    "DESIGN_PART_SKILL",
    "KnowledgeDefinition",
    "RUNTIME_KNOWLEDGE",
    "RUNTIME_SKILL_REGISTRY",
    "SkillDefinition",
    "SkillRegistry",
]
