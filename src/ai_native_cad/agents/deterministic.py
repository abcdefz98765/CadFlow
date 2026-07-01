"""Deterministic adapter backed by the current rule/template pipeline."""

from __future__ import annotations

from typing import Any

from ai_native_cad.agents.base import AgentAdapter
from ai_native_cad.cad_ir.repair import repair_ir
from ai_native_cad.pipeline.failure_analyzer import analyze_failure
from ai_native_cad.planning import create_planning_artifact
from ai_native_cad.requirements import RequirementAgent


class DeterministicAgentAdapter(AgentAdapter):
    """Rule-based adapter for tests, CI, demos, and fallback execution."""

    def __init__(self, requirement_agent: RequirementAgent | None = None) -> None:
        self.requirement_agent = requirement_agent or RequirementAgent()

    def parse_requirement(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        overrides = context.get("overrides")
        if overrides is not None and not isinstance(overrides, dict):
            raise TypeError("context['overrides'] must be a dict when provided")
        return self.requirement_agent.parse(prompt, overrides=overrides)

    def create_plan(self, requirement: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        return create_planning_artifact(requirement)

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
        return {
            "analysis": analysis,
            "repair": repair,
            "mode": "deterministic",
        }

    def explain_review(
        self,
        report: dict[str, Any],
        trace: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        status = report.get("status") or ("success" if report.get("success") else "failed")
        return {
            "status": status,
            "summary": _review_summary(report, trace),
            "errors": list(report.get("errors", [])),
            "warnings": list(report.get("warnings", [])),
            "mode": "deterministic",
        }


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
