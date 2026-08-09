"""Typed runtime registry for canonical Work Design and bounded Part Design.

The registry constrains provider authority while leaving action choice to the
provider. Model-program tools are reachable only through the declared
CadFlow-owned delegate and remain independently gated by live attestation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class BudgetDefinition:
    max_steps: int
    max_context_requests: int
    max_context_bytes: int
    max_contract_submissions: int
    max_repair_attempts: int
    max_source_submissions: int
    max_executions: int
    max_observation_inspections: int
    timeout_seconds: float


@dataclass(frozen=True)
class KnowledgeDefinition:
    knowledge_id: str
    scope: str
    source: str
    max_chars: int = 12_000

    def load_content(self) -> str:
        """Load one declared repository source within a small fixed bound."""

        root = Path(__file__).resolve().parents[3]
        source = (root / self.source).resolve()
        if source != root and root not in source.parents:
            raise ValueError("knowledge source must stay inside the repository")
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"declared knowledge source is unavailable: {self.knowledge_id}")
        content = source.read_text(encoding="utf-8")
        if len(content) > self.max_chars:
            content = content[: self.max_chars].rstrip() + "\n[bounded]"
        return content

    @property
    def summary(self) -> str:
        """Compatibility accessor; Markdown remains the sole text authority."""

        return self.load_content()


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
    delegated_skill_ids: tuple[str, ...] = ()

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


WORK_DESIGN_SKILL = SkillDefinition(
    skill_id="work_design",
    version="0.1.0",
    role="work_design",
    phase="intent_design",
    checkpoints=("work_design", "part_job_definition"),
    operations=("work_design",),
    allowed_actions=frozenset(
        {
            "request_context",
            "propose_work_design",
            "create_part_jobs",
            "ask_user",
            "stop",
        }
    ),
    allowed_context_keys=frozenset(
        {
            "work_request",
            "accepted_work_context",
            "previous_work_design",
            "work_clarification_answers",
        }
    ),
    allowed_tools=frozenset(),
    output_contract_types=frozenset({"work_design"}),
    shared_knowledge_ids=("verification_state_vocabulary",),
    private_knowledge_ids=(
        "work_design_missing_information",
        "work_design_analysis",
        "work_design_decomposition",
        "work_design_risk_confirmation",
        "work_design_routing",
    ),
    stop_reasons=frozenset(
        {
            "user_input_required",
            "unsupported_capability",
            "insufficient_context",
            "budget_exhausted",
            "provider_failure",
            "policy_blocked",
            "completed",
        }
    ),
    prohibited_side_effects=(
        "No provider-selected Part Job, Run, artifact, path, or manifest identity.",
        "No direct Work mutation, CAD execution, publication, acceptance, Assembly execution, or Deliverables.",
        "No arbitrary filesystem, repository, environment, credential, shell, subprocess, or network authority.",
        "No legacy part-family template may define the Work design space.",
    ),
    budget=BudgetDefinition(
        max_steps=10,
        max_context_requests=4,
        max_context_bytes=65_536,
        max_contract_submissions=2,
        max_repair_attempts=1,
        max_source_submissions=0,
        max_executions=0,
        max_observation_inspections=0,
        timeout_seconds=120.0,
    ),
    system_rules=(
        "Return exactly one JSON Agent action and no markdown or private reasoning.",
        "Understand the overall Work before choosing generated Parts.",
        "Ask one focused question when a missing user decision materially changes topology, Part count, interfaces, service method, manufacturing route, load-bearing intent, or acceptance.",
        "Use visible reversible assumptions for low-risk exploratory details.",
        "Distinguish generated Parts from purchased or existing reference components.",
        "Propose a concise Work Design before requesting creation of Part Jobs.",
        "CadFlow assigns identities and owns every Work mutation.",
    ),
    action_contract_rules=(
        "request_context requires one declared semantic context_key.",
        "propose_work_design requires work_design and may not contain product identities or side-effect fields.",
        "create_part_jobs contains only the action and requests CadFlow to apply the latest valid Work Design.",
        "ask_user requires focused questions when material intent is missing.",
        "stop requires one declared typed stop_reason.",
    ),
)


DESIGN_PART_SKILL = SkillDefinition(
    skill_id="design_part",
    version="0.2.0",
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
            "create_model_program",
            "patch_model_program",
            "request_execution",
            "inspect_observation",
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
    allowed_tools=frozenset({"validate_structured_contract"}),
    output_contract_types=frozenset({"cad_ir_draft", "model_program_candidate"}),
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
            "completed",
        }
    ),
    prohibited_side_effects=(
        "No filesystem paths or arbitrary repository context.",
        "No shell, subprocess, network, arbitrary filesystem, credentials, or dependency installation.",
        "Model source may execute only through the delegated CadFlow model_program skill and attested Tool Broker.",
        "No Work mutation, publication, acceptance, or deliverable authority.",
        "No fabricated validator, geometry, fit, tolerance, strength, or safety claims.",
    ),
    budget=BudgetDefinition(
        max_steps=16,
        max_context_requests=4,
        max_context_bytes=65_536,
        max_contract_submissions=3,
        max_repair_attempts=2,
        max_source_submissions=4,
        max_executions=3,
        max_observation_inspections=3,
        timeout_seconds=180.0,
    ),
    system_rules=(
        "Return exactly one JSON Agent action and no markdown or private reasoning.",
        "Choose the next action from the declared design_part action allowlist.",
        "Request semantic context only when it materially affects the design decision.",
        "Treat validator feedback as system evidence and decide whether to patch, change strategy, ask, or stop.",
        "Choose either the structured CAD IR compatibility strategy or the delegated model_program strategy.",
        "Treat source as untrusted; request execution only through CadFlow and inspect each new structured observation before repairing or completing.",
        "Do not claim that a contract or candidate is reviewable, accepted, deliverable, or production geometry.",
    ),
    action_contract_rules=(
        "request_context requires context_key.",
        "create_contract and patch_contract require contract_type='cad_ir_draft' and a contract object.",
        "request_validation validates the most recent submitted contract.",
        "create_model_program and patch_model_program require exactly api_id, source, parameters, and requested_outputs=['step']; patch is a complete replacement, never a diff.",
        "request_execution executes only the latest CadFlow-assigned candidate; it accepts no provider path, command, candidate id, UID, or environment.",
        "inspect_observation inspects only the latest uninspected CadFlow observation and accepts no provider-selected identity.",
        "ask_user requires focused questions when material information is missing.",
        "stop requires one declared typed stop_reason.",
        "Never return code, commands, paths, secrets, raw provider messages, or validator facts not supplied by CadFlow.",
    ),
    delegated_skill_ids=("model_program",),
)


MODEL_PROGRAM_SKILL = SkillDefinition(
    skill_id="model_program",
    version="0.1.0",
    role="geometry_agent",
    phase="design",
    checkpoints=("model_program_candidate", "execution_observation"),
    operations=("model_program",),
    allowed_actions=frozenset(
        {
            "create_model_program",
            "patch_model_program",
            "request_execution",
            "inspect_observation",
        }
    ),
    allowed_context_keys=frozenset(),
    allowed_tools=frozenset(
        {"validate_model_program_source", "execute_model_program"}
    ),
    output_contract_types=frozenset({"model_program_candidate"}),
    shared_knowledge_ids=("verification_state_vocabulary",),
    private_knowledge_ids=("model_program_cadquery_v1",),
    stop_reasons=frozenset(),
    prohibited_side_effects=(
        "No provider-selected paths, commands, environment, UID, shell, subprocess, network, arbitrary filesystem, or dependency installation.",
        "Execution requires a live attestation bound to the pinned profile and toolchain.",
        "Execution observations are candidate evidence only and grant no publication or acceptance authority.",
    ),
    budget=BudgetDefinition(
        max_steps=16,
        max_context_requests=0,
        max_context_bytes=0,
        max_contract_submissions=0,
        max_repair_attempts=2,
        max_source_submissions=4,
        max_executions=3,
        max_observation_inspections=3,
        timeout_seconds=180.0,
    ),
    system_rules=(
        "Use only cadquery_v1 source accepted by the CadFlow static policy.",
        "Return a single declared action; CadFlow assigns every candidate, observation, execution, and evidence identity.",
        "Inspect the latest observation before patching or completing.",
    ),
    action_contract_rules=(
        "A source submission is a complete immutable candidate.",
        "Execution and inspection actions contain only the action field.",
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
        for skill in skills:
            if skill.skill_id in skill.delegated_skill_ids:
                raise ValueError("a skill cannot delegate to itself")
            unknown = set(skill.delegated_skill_ids) - set(by_id)
            if unknown:
                raise ValueError(
                    f"skill delegates to unknown skills: {skill.skill_id}"
                )
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
    ),
    KnowledgeDefinition(
        knowledge_id="model_program_cadquery_v1",
        scope="skill_private",
        source="policies/model_program_cadquery_v1.md",
        max_chars=12_000,
    ),
    KnowledgeDefinition(
        knowledge_id="design_part_structured_contract_strategy",
        scope="skill_private",
        source=(
            "skills/design_part/knowledge/structured_contract_strategy.md"
        ),
    ),
    KnowledgeDefinition(
        knowledge_id="work_design_missing_information",
        scope="skill_private",
        source="skills/requirement/knowledge/missing_info_policy.md",
    ),
    KnowledgeDefinition(
        knowledge_id="work_design_analysis",
        scope="skill_private",
        source="skills/planning/knowledge/design_analysis.md",
    ),
    KnowledgeDefinition(
        knowledge_id="work_design_decomposition",
        scope="skill_private",
        source="skills/planning/knowledge/product_decomposition.md",
    ),
    KnowledgeDefinition(
        knowledge_id="work_design_risk_confirmation",
        scope="skill_private",
        source="skills/planning/knowledge/risk_and_confirmation_gates.md",
    ),
    KnowledgeDefinition(
        knowledge_id="work_design_routing",
        scope="skill_private",
        source="skills/planning/knowledge/workflow_routing.md",
    ),
)


RUNTIME_SKILL_REGISTRY = SkillRegistry(
    (WORK_DESIGN_SKILL, DESIGN_PART_SKILL, MODEL_PROGRAM_SKILL),
    RUNTIME_KNOWLEDGE,
)


__all__ = [
    "BudgetDefinition",
    "DESIGN_PART_SKILL",
    "MODEL_PROGRAM_SKILL",
    "WORK_DESIGN_SKILL",
    "KnowledgeDefinition",
    "RUNTIME_KNOWLEDGE",
    "RUNTIME_SKILL_REGISTRY",
    "SkillDefinition",
    "SkillRegistry",
]
