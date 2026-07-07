"""Deterministic adapter backed by the current rule/template pipeline."""

from __future__ import annotations

from typing import Any

from ai_native_cad.agents.base import AgentAdapter
from ai_native_cad.agents.validation import (
    validate_planning_draft,
    validate_repair_suggestion,
    validate_requirement_draft,
    validate_review_explanation,
)
from ai_native_cad.cad_ir.repair import repair_ir
from ai_native_cad.pipeline.failure_analyzer import analyze_failure
from ai_native_cad.planning import create_planning_artifact
from ai_native_cad.requirements import RequirementAgent


LOCAL_MOCK_PROVIDER_IDENTITY = {
    "provider": "local/mock",
    "adapter": "deterministic",
    "network": "disabled",
    "api_key_required": False,
}


class DeterministicAgentAdapter(AgentAdapter):
    """Rule-based adapter for tests, CI, demos, and fallback execution."""

    def __init__(self, requirement_agent: RequirementAgent | None = None) -> None:
        self.requirement_agent = requirement_agent or RequirementAgent()

    @property
    def provider_identity(self) -> dict[str, Any]:
        return dict(LOCAL_MOCK_PROVIDER_IDENTITY)

    def parse_requirement(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        overrides = context.get("overrides")
        if overrides is not None and not isinstance(overrides, dict):
            raise TypeError("context['overrides'] must be a dict when provided")
        requirement = self.requirement_agent.parse(prompt, overrides=overrides)
        validate_requirement_draft(requirement)
        return requirement

    def create_plan(self, requirement: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        planning_artifact = create_planning_artifact(requirement)
        validate_planning_draft(planning_artifact)
        return planning_artifact

    def interpret_user_intent(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        from ai_native_cad.agents.design_planner_fake import DesignPlannerFakeAgentAdapter

        return DesignPlannerFakeAgentAdapter(self.requirement_agent).interpret_user_intent(prompt, context=context)

    def propose_design_brief(self, intent: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        from ai_native_cad.agents.design_planner_fake import DesignPlannerFakeAgentAdapter

        return DesignPlannerFakeAgentAdapter(self.requirement_agent).propose_design_brief(intent, context=context)

    def generate_candidate_plans(
        self,
        design_brief: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        from ai_native_cad.agents.design_planner_fake import DesignPlannerFakeAgentAdapter

        return DesignPlannerFakeAgentAdapter(self.requirement_agent).generate_candidate_plans(design_brief, context=context)

    def convert_plan_to_ir(self, selected_plan: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        from ai_native_cad.agents.design_planner_fake import DesignPlannerFakeAgentAdapter

        return DesignPlannerFakeAgentAdapter(self.requirement_agent).convert_plan_to_ir(selected_plan, context=context)

    def create_part_ir(
        self,
        reviewed_part_handoff: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a local/mock CAD IR draft for one reviewed part handoff.

        This is a conservative fallback and test adapter. It does not choose an
        unrelated template when a reviewed part is unsupported.
        """

        return _part_ir_from_reviewed_handoff(reviewed_part_handoff, context or {})

    def parse_revision_request(
        self,
        prompt: str,
        model_context: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from ai_native_cad.agents.design_planner_fake import DesignPlannerFakeAgentAdapter

        return DesignPlannerFakeAgentAdapter(self.requirement_agent).parse_revision_request(
            prompt,
            model_context,
            context=context,
        )

    def create_revision_plan(
        self,
        change_intent: dict[str, Any],
        model_context: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from ai_native_cad.agents.design_planner_fake import DesignPlannerFakeAgentAdapter

        return DesignPlannerFakeAgentAdapter(self.requirement_agent).create_revision_plan(
            change_intent,
            model_context,
            context=context,
        )

    def suggest_repair(
        self,
        failure: dict[str, Any],
        ir: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        analysis = dict(failure)
        if "suggested_ir_fix" not in analysis:
            analysis = analyze_failure(
                execution=analysis.get("execution"),
                validation=analysis.get("validation"),
            )
        repair = repair_ir(ir, analysis)
        result = {
            "analysis": analysis,
            "repair": repair,
            "mode": "deterministic",
        }
        validate_repair_suggestion(result)
        return result

    def explain_review(
        self,
        report: dict[str, Any],
        trace: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = report.get("status") or ("success" if report.get("success") else "failed")
        result = {
            "status": status,
            "summary": _review_summary(report, trace),
            "errors": list(report.get("errors", [])),
            "warnings": list(report.get("warnings", [])),
            "mode": "deterministic",
        }
        validate_review_explanation(result)
        return result


def _review_summary(report: dict[str, Any], trace: dict[str, Any]) -> str:
    part_name = report.get("part_name") or report.get("part_type") or "model"
    attempts = trace.get("total_attempts")
    if report.get("success") or report.get("status") == "success":
        return f"{part_name} generated successfully with STEP as the primary CAD artifact."
    if report.get("status") == "blocked":
        stage = report.get("blocked_stage") or trace.get("text_pipeline", {}).get("blocked_stage") or "workflow"
        return f"{part_name} is blocked at the {stage} stage before model generation."
    if attempts is not None:
        return f"{part_name} did not pass validation after {attempts} attempt(s)."
    return f"{part_name} did not pass validation."


def _part_ir_from_reviewed_handoff(reviewed_part_handoff: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    part_id = _safe_token(reviewed_part_handoff.get("part_id") or "reviewed_part")
    brief = " ".join(
        str(value)
        for value in (
            reviewed_part_handoff.get("part_brief"),
            reviewed_part_handoff.get("single_part_prompt"),
            context.get("prompt"),
        )
        if isinstance(value, str)
    ).lower()
    source = {
        "agent_operation": "create_part_ir",
        "adapter": "deterministic",
        "mode": "local_mock_fallback",
        "reviewed_part_handoff": {
            "part_id": part_id,
            "status": reviewed_part_handoff.get("status"),
        },
    }
    if part_id in {"base", "enclosure_base"} or ("base" in part_id and "robot" not in brief):
        return {
            "part_type": "enclosure_base",
            "part_name": f"single_part_{part_id}",
            "unit": "mm",
            "dimensions": {"outer_length": 80, "outer_width": 50, "outer_height": 18, "wall_thickness": 2},
            "features": {},
            "outputs": ["step", "stl"],
            "check_level": "L0",
            "source": source,
        }
    if part_id in {"spacer", "standoff"}:
        return {
            "part_type": "spacer",
            "part_name": f"single_part_{part_id}",
            "unit": "mm",
            "dimensions": {"outer_diameter": 12, "inner_diameter": 5, "thickness": 10},
            "features": {},
            "outputs": ["step", "stl"],
            "check_level": "L0",
            "source": source,
        }
    if part_id in {"bracket", "servo_bracket", "shoulder_servo_bracket", "elbow_servo_bracket"}:
        return {
            "part_type": "simple_bracket",
            "part_name": f"single_part_{part_id}",
            "unit": "mm",
            "dimensions": {"base_length": 45, "base_width": 28, "height": 35, "thickness": 4},
            "features": {},
            "outputs": ["step", "stl"],
            "check_level": "L0",
            "source": source,
        }
    return {
        "part_type": part_id,
        "part_name": f"single_part_{part_id}",
        "unit": "mm",
        "dimensions": _link_like_dimensions(reviewed_part_handoff, context),
        "features": {},
        "outputs": ["step", "stl"],
        "check_level": "L0",
        "source": source,
    }


def _link_like_dimensions(reviewed_part_handoff: dict[str, Any], context: dict[str, Any]) -> dict[str, float]:
    assembly_context = reviewed_part_handoff.get("preserved_assembly_context")
    if not isinstance(assembly_context, dict):
        assembly_context = {}
    reach = _number_or_none(assembly_context.get("arm_reach_mm")) or _number_or_none(context.get("arm_reach_mm")) or 220.0
    return {
        "length": round(float(reach) / 2.4, 3),
        "width": 22.0,
        "thickness": 6.0,
    }


def _safe_token(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    safe = "".join(char for char in text if char.isalnum() or char == "_").strip("_")
    return safe or "reviewed_part"


def _number_or_none(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().split()[0] if value.strip() else ""
        try:
            return float(text)
        except ValueError:
            return None
    return None
