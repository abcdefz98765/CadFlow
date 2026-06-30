"""Structured Planning artifacts for workflow handoff.

Planning is intentionally a narrow handoff layer here. It records routing,
selected parts, risks, and review targets, while CAD IR conversion consumes
only the resolved part-level decisions.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ai_native_cad.workflow_control import make_flow_decision


PLANNING_ARTIFACT_VERSION = "planning-artifact-v0.1"
READY_FOR_CAD_IR = "ready_for_cad_ir"
RETURN_TO_REQUIREMENT = "return_to_requirement"

BLOCKING_RISK_CATEGORIES = {"topology", "interface", "assembly", "motion", "fit"}


class PlanningHandoffBlocked(ValueError):
    """Raised when Planning has not resolved enough decisions for CAD IR."""

    def __init__(self, message: str, reasons: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.reasons = reasons or []


def create_planning_artifact(requirement: dict[str, Any]) -> dict[str, Any]:
    """Create the minimum structured Planning handoff artifact.

    The artifact can coexist with the legacy ``plan.md``. It deliberately keeps
    resolved part geometry under ``selected_parts[].resolved_decisions`` so CAD
    IR conversion has one small, auditable input surface.
    """

    route = _route(requirement)
    risk_notes = _risk_notes(requirement)
    blocking_reasons = _blocking_reasons(requirement, risk_notes, route)
    gate_status = RETURN_TO_REQUIREMENT if blocking_reasons else READY_FOR_CAD_IR
    selected_parts = [_selected_part(requirement, resolved=not blocking_reasons)]
    functional_datums = _functional_datums(requirement)
    interfaces = _interfaces(requirement)
    template_candidates = _template_candidates(requirement)
    review_targets = _review_targets(requirement)

    return {
        "artifact_type": "planning",
        "version": PLANNING_ARTIFACT_VERSION,
        "route": route,
        "selected_parts": selected_parts,
        "functional_datums": functional_datums,
        "interfaces": interfaces,
        "template_candidates": template_candidates,
        "risk_notes": risk_notes,
        "review_targets": review_targets,
        "flow_gate_status": _flow_gate_status(gate_status, blocking_reasons),
        "source": {
            "requirement_status": deepcopy(requirement.get("requirement_status", {})),
            "requirement_part_type": requirement.get("part_type"),
            "requirement_check_level": requirement.get("check_level", "L0"),
        },
    }


def resolved_part_decision(planning_artifact: dict[str, Any], part_name: str | None = None) -> dict[str, Any]:
    """Return the resolved part-level decision for CAD IR conversion.

    Open-ended planning notes, design analysis, and risk text are intentionally
    ignored by this function. If the flow gate is blocked or the selected part
    is not resolved, a structured exception is raised before CAD IR exists.
    """

    validate_planning_handoff(planning_artifact)
    selected_parts = planning_artifact.get("selected_parts", [])
    if part_name is None:
        part = selected_parts[0]
    else:
        matches = [item for item in selected_parts if item.get("part_name") == part_name]
        if not matches:
            raise PlanningHandoffBlocked(
                f"Planning artifact has no selected part named {part_name}",
                [{"code": "part_not_selected", "part_name": part_name}],
            )
        part = matches[0]

    decisions = part.get("resolved_decisions", {})
    if not isinstance(decisions, dict):
        raise PlanningHandoffBlocked(
            "Selected part is missing resolved_decisions",
            [{"code": "missing_resolved_decisions", "part_name": part.get("part_name")}],
        )
    return deepcopy(decisions)


def validate_planning_handoff(planning_artifact: dict[str, Any]) -> dict[str, Any]:
    """Validate the Planning -> CAD IR gate."""

    errors: list[dict[str, Any]] = []
    gate = planning_artifact.get("flow_gate_status", {})
    if gate.get("status") != READY_FOR_CAD_IR:
        errors.extend(gate.get("blocking_reasons", []))
        if not errors:
            errors.append({"code": "flow_gate_not_ready", "status": gate.get("status")})

    for risk in planning_artifact.get("risk_notes", []):
        if risk.get("blocks_cad_ir") or risk.get("requires_requirement_confirmation"):
            errors.append({
                "code": risk.get("code", "blocking_planning_risk"),
                "category": risk.get("category"),
                "message": risk.get("message", "Planning risk blocks CAD IR"),
            })

    route = planning_artifact.get("route", {})
    if route.get("selected") == "confirmation_needed":
        errors.append({"code": "route_requires_confirmation", "route": route.get("selected")})

    selected_parts = planning_artifact.get("selected_parts", [])
    if not selected_parts:
        errors.append({"code": "no_selected_parts", "message": "Planning selected no parts for CAD IR"})
    for part in selected_parts:
        if not part.get("resolved"):
            errors.append({
                "code": "part_decision_unresolved",
                "part_name": part.get("part_name"),
                "message": "Selected part decisions are not resolved",
            })
        decisions = part.get("resolved_decisions")
        if not isinstance(decisions, dict):
            errors.append({"code": "missing_resolved_decisions", "part_name": part.get("part_name")})

    result = {"valid": not errors, "errors": errors, "warnings": []}
    if errors:
        raise PlanningHandoffBlocked("Planning handoff is not ready for CAD IR", errors)
    return result


def _route(requirement: dict[str, Any]) -> dict[str, Any]:
    scope = requirement.get("intent", {}).get("scope", "part")
    if not requirement.get("requirement_status", {}).get("complete_for_generation", True):
        selected = "confirmation_needed"
    elif scope == "assembly":
        selected = "assembly_loop"
    else:
        selected = "single_part"
    return {
        "selected": selected,
        "scope": scope,
        "reason": "selected from structured requirement intent and generation gate",
    }


def _selected_part(requirement: dict[str, Any], resolved: bool) -> dict[str, Any]:
    part_name = requirement.get("instance_name") or requirement.get("part_name") or requirement["part_type"]
    decisions = {
        "part_type": requirement["part_type"],
        "part_name": part_name,
        "unit": requirement.get("unit", "mm"),
        "dimensions": deepcopy(requirement.get("dimensions", {})),
        "features": deepcopy(requirement.get("features", {})),
        "outputs": list(requirement.get("outputs", ["step", "stl"])),
        "check_level": requirement.get("check_level", "L0"),
    }
    return {
        "part_name": part_name,
        "generation_order": 1,
        "resolved": resolved,
        "resolved_decisions": decisions,
        "functional_datums": _functional_datums(requirement),
        "interfaces": _interfaces(requirement),
        "template_candidates": _template_candidates(requirement),
        "review_targets": _review_targets(requirement),
    }


def _functional_datums(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    convention = requirement.get("cad_brief", {}).get("coordinate_convention", {})
    axes = convention.get("axes", {})
    return [{
        "name": "part_local_origin",
        "origin": convention.get("origin", "part_local_centered_or_template_defined"),
        "axes": deepcopy(axes),
        "unit": requirement.get("unit", "mm"),
        "source": "cad_brief.coordinate_convention",
    }]


def _interfaces(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    interfaces = []
    for name, feature in sorted(requirement.get("features", {}).items()):
        if isinstance(feature, dict) and any(key in feature for key in ("diameter", "fastener", "positions", "count")):
            interfaces.append({
                "name": name,
                "kind": "feature_interface",
                "feature": deepcopy(feature),
                "resolved": True,
            })
    return interfaces


def _template_candidates(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "template": requirement["part_type"],
        "part_type": requirement["part_type"],
        "reason": "part_type matches template catalog family",
    }]


def _review_targets(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    return deepcopy(requirement.get("cad_brief", {}).get("validation_targets", []))


def _risk_notes(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    notes = []
    for item in requirement.get("missing_information", []):
        field = item.get("field", "unknown")
        category = _risk_category(item)
        note = {
            "code": item.get("code", "missing_information"),
            "category": category,
            "field": field,
            "severity": item.get("severity", "important"),
            "message": item.get("reason", item.get("question", "Missing planning input")),
            "requires_requirement_confirmation": bool(item.get("ask_user")),
            "blocks_cad_ir": bool(item.get("ask_user")) and category in BLOCKING_RISK_CATEGORIES,
        }
        notes.append(note)
    return notes


def _risk_category(item: dict[str, Any]) -> str:
    field = item.get("field", "")
    category = item.get("category", "")
    if field.startswith("dimensions.") or category == "primary_dimensions":
        return "topology"
    if "interface" in field or category == "engineering_constraints":
        return "interface"
    if category == "manufacturing_context":
        return "manufacturing"
    if category == "safety_review":
        return "safety"
    return category or "general"


def _blocking_reasons(
    requirement: dict[str, Any],
    risk_notes: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[dict[str, Any]]:
    reasons = []
    if not requirement.get("requirement_status", {}).get("complete_for_generation", True):
        reasons.append({
            "code": "requirement_incomplete_for_generation",
            "fields": list(requirement.get("requirement_status", {}).get("blocking_fields", [])),
        })
    if route.get("selected") == "assembly_loop":
        reasons.append({
            "code": "assembly_route_not_part_level",
            "message": "Assembly route must be decomposed before single-part CAD IR conversion",
        })
    for risk in risk_notes:
        if risk.get("blocks_cad_ir"):
            reasons.append({
                "code": risk.get("code", "blocking_planning_risk"),
                "category": risk.get("category"),
                "field": risk.get("field"),
                "message": risk.get("message"),
            })
    return reasons


def _flow_gate_status(gate_status: str, blocking_reasons: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": gate_status,
        "blocking_reasons": blocking_reasons,
        "rework_decision": make_flow_decision(
            from_stage="planning",
            proceed_to="cad_ir",
            return_to="requirement",
            blocking_reasons=blocking_reasons,
        ),
    }
