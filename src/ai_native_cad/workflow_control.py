"""Workflow flow-gate and rework decision helpers."""

from __future__ import annotations

from typing import Any


PROCEED = "proceed"
RETURN = "return"
RETRY = "retry"


def make_flow_decision(
    *,
    from_stage: str,
    proceed_to: str,
    return_to: str,
    blocking_reasons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a structured proceed/return decision for a stage handoff."""

    reasons = blocking_reasons or []
    if reasons:
        return {
            "action": RETURN,
            "from_stage": from_stage,
            "to_stage": return_to,
            "owner_stage": return_to,
            "reasons": reasons,
        }
    return {
        "action": PROCEED,
        "from_stage": from_stage,
        "to_stage": proceed_to,
        "owner_stage": proceed_to,
        "reasons": [],
    }


def cad_ir_to_part_modeling_decision(ir_validation: dict[str, Any]) -> dict[str, Any]:
    """Decide whether CAD IR may enter Part Modeling."""

    if ir_validation.get("valid"):
        return make_flow_decision(
            from_stage="cad_ir",
            proceed_to="part_modeling",
            return_to="planning",
            blocking_reasons=[],
        )
    reasons = [
        {
            "code": error.get("code", "ir_invalid"),
            "message": error.get("message", "CAD IR validation failed"),
            **{key: value for key, value in error.items() if key not in {"code", "message"}},
        }
        for error in ir_validation.get("errors", [])
        if isinstance(error, dict)
    ] or [{"code": "ir_invalid", "message": "CAD IR validation failed"}]
    return make_flow_decision(
        from_stage="cad_ir",
        proceed_to="part_modeling",
        return_to="planning",
        blocking_reasons=reasons,
    )


def requirement_to_planning_decision(requirement_status: dict[str, Any]) -> dict[str, Any]:
    """Decide whether Requirement has enough structured data for Planning."""

    if requirement_status.get("complete_for_generation", False):
        return make_flow_decision(
            from_stage="requirement",
            proceed_to="planning",
            return_to="requirement",
            blocking_reasons=[],
        )
    blocking_fields = list(requirement_status.get("blocking_fields", []))
    reasons = [
        {
            "code": "requirement_field_blocked",
            "field": field,
            "message": f"Requirement field needs upstream clarification: {field}",
        }
        for field in blocking_fields
    ] or [{"code": "requirement_incomplete", "message": "Requirement is incomplete for generation"}]
    return make_flow_decision(
        from_stage="requirement",
        proceed_to="planning",
        return_to="requirement",
        blocking_reasons=reasons,
    )


def part_modeling_retry_decision(
    failure_analysis: dict[str, Any],
    repaired: dict[str, Any],
) -> dict[str, Any]:
    """Record an implementation-level Part Modeling retry decision."""

    return {
        "action": RETRY,
        "from_stage": "part_modeling",
        "to_stage": "part_modeling",
        "owner_stage": "part_modeling",
        "reason": failure_analysis.get("root_cause", "validation_failed"),
        "repair_scope": "implementation_level_ir_or_mapping",
        "preserves_design_intent": True,
        "changes": list(repaired.get("changes", [])),
    }


def part_modeling_final_decision(
    *,
    status: str,
    validation: dict[str, Any],
) -> dict[str, Any]:
    """Decide what owns the result after Part Modeling attempts finish."""

    if status == "success" and validation.get("valid"):
        return make_flow_decision(
            from_stage="part_modeling",
            proceed_to="assembly_or_review",
            return_to="planning",
            blocking_reasons=[],
        )
    reasons = [
        {
            "code": error.get("code", "part_modeling_failed"),
            "message": error.get("message", "Part Modeling failed"),
            **{key: value for key, value in error.items() if key not in {"code", "message"}},
        }
        for error in validation.get("errors", [])
        if isinstance(error, dict)
    ] or [{"code": "part_modeling_failed", "message": "Part Modeling did not produce valid artifacts"}]
    return make_flow_decision(
        from_stage="part_modeling",
        proceed_to="assembly_or_review",
        return_to="planning",
        blocking_reasons=reasons,
    )


def assembly_plan_decision(plan: dict[str, Any]) -> dict[str, Any]:
    """Decide whether Assembly planning may emit assembly configs."""

    gate = plan.get("confirmation_gate", {})
    unresolved = gate.get("unresolved_questions", [])
    if not gate.get("needs_user_confirmation") and plan.get("status") != "confirmation_needed":
        return make_flow_decision(
            from_stage="assembly",
            proceed_to="assembly_config",
            return_to="planning",
            blocking_reasons=[],
        )
    reasons = [
        {
            "code": "assembly_confirmation_required",
            "message": question,
        }
        for question in unresolved
    ] or [{"code": "assembly_confirmation_required", "message": "Assembly plan needs confirmation"}]
    return make_flow_decision(
        from_stage="assembly",
        proceed_to="assembly_config",
        return_to="planning",
        blocking_reasons=reasons,
    )


def assembly_validation_decision(result: dict[str, Any]) -> dict[str, Any]:
    """Decide whether validated assembly artifacts may enter Review."""

    errors = result.get("errors", [])
    if not errors:
        return make_flow_decision(
            from_stage="assembly",
            proceed_to="review",
            return_to="part_modeling_or_planning",
            blocking_reasons=[],
        )
    reasons = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        code = error.get("code", "assembly_validation_failed")
        owner = _assembly_error_owner(code)
        reasons.append({
            "code": code,
            "message": error.get("message", "Assembly validation failed"),
            "owner_stage": owner,
            **{key: value for key, value in error.items() if key not in {"code", "message"}},
        })
    return make_flow_decision(
        from_stage="assembly",
        proceed_to="review",
        return_to=_assembly_return_target(reasons),
        blocking_reasons=reasons or [{"code": "assembly_validation_failed", "message": "Assembly validation failed"}],
    )


def review_to_outputs_decision(report: dict[str, Any]) -> dict[str, Any]:
    """Decide whether Review can publish final outputs."""

    if report.get("success") or report.get("status") in {"success", "warning"}:
        return make_flow_decision(
            from_stage="review",
            proceed_to="outputs",
            return_to="review",
            blocking_reasons=[],
        )
    reasons = [
        {
            "code": error.get("code", "review_blocked"),
            "message": error.get("message", "Review found blocking output issue"),
            **{key: value for key, value in error.items() if key not in {"code", "message"}},
        }
        for error in report.get("errors", [])
        if isinstance(error, dict)
    ] or [{"code": "review_blocked", "message": "Review cannot publish successful outputs"}]
    return make_flow_decision(
        from_stage="review",
        proceed_to="outputs",
        return_to="part_modeling_or_planning",
        blocking_reasons=reasons,
    )


def _assembly_error_owner(code: str) -> str:
    if code in {"missing_step", "missing_report", "invalid_part_report", "multi_solid_part", "missing_bbox"}:
        return "part_modeling"
    if code in {"required_contact_failed", "floating_part", "possible_bbox_interference", "constraint_missing_part"}:
        return "planning"
    return "assembly"


def _assembly_return_target(reasons: list[dict[str, Any]]) -> str:
    owners = {reason.get("owner_stage") for reason in reasons}
    if "planning" in owners:
        return "planning"
    if "part_modeling" in owners:
        return "part_modeling"
    return "assembly"
