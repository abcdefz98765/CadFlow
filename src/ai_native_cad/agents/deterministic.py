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
