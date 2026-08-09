"""Deterministic test/example adapter for the legacy staged create workflow."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from ai_native_cad.agents.deterministic import DeterministicAgentAdapter
from ai_native_cad.agents.validation import validate_input_ir_draft


class DesignPlannerFakeAgentAdapter(DeterministicAgentAdapter):
    """Local adapter that exercises the LLM-first planning artifact shape.

    It is deterministic and provider-free, but it models the same boundary a
    JSON-only LLM adapter should later implement: intent, brief, candidates,
    selected plan, and CAD IR. CAD execution remains outside the adapter.
    """

    @property
    def provider_identity(self) -> dict[str, Any]:
        return {
            "provider": "local/fake",
            "adapter": "design_planner_fake",
            "network": "disabled",
            "api_key_required": False,
        }

    def interpret_user_intent(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        requirement = self.parse_requirement(prompt, context=context)
        intent = requirement.get("intent", {})
        return {
            "artifact_type": "intent",
            "version": "intent-v0.1",
            "prompt_summary": _prompt_summary(prompt),
            "object_goal": intent.get("object_goal", requirement["part_type"]),
            "scope": intent.get("scope", "part"),
            "use_case": intent.get("use_case", "unspecified"),
            "recognized_part_type": requirement["part_type"],
            "unit": requirement.get("unit", "mm"),
            "requested_outputs": list(requirement.get("outputs", ["step", "stl"])),
            "interpreted_constraints": {
                "dimensions": deepcopy(requirement.get("dimensions", {})),
                "features": deepcopy(requirement.get("features", {})),
                "check_level": requirement.get("check_level", "L0"),
            },
            "assumptions": list(requirement.get("assumptions", [])),
            "open_questions": list(requirement.get("follow_up_questions", [])),
            "requirement_snapshot": requirement,
        }

    def propose_design_brief(self, intent: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        requirement = deepcopy(intent.get("requirement_snapshot", {}))
        if not requirement:
            requirement = {
                "part_type": intent["recognized_part_type"],
                "unit": intent.get("unit", "mm"),
                "dimensions": deepcopy(intent.get("interpreted_constraints", {}).get("dimensions", {})),
                "features": deepcopy(intent.get("interpreted_constraints", {}).get("features", {})),
                "outputs": list(intent.get("requested_outputs", ["step", "stl"])),
                "check_level": intent.get("interpreted_constraints", {}).get("check_level", "L0"),
            }
        cad_brief = deepcopy(requirement.get("cad_brief", {}))
        return {
            "artifact_type": "design_brief",
            "version": "design-brief-v0.1",
            "part_type": requirement["part_type"],
            "design_goal": {
                "object_goal": intent.get("object_goal", requirement["part_type"]),
                "scope": intent.get("scope", "part"),
                "use_case": intent.get("use_case", "unspecified"),
            },
            "functional_requirements": _functional_requirements(requirement),
            "geometry_constraints": {
                "unit": requirement.get("unit", "mm"),
                "dimensions": deepcopy(requirement.get("dimensions", {})),
                "features": deepcopy(requirement.get("features", {})),
            },
            "validation_targets": deepcopy(cad_brief.get("validation_targets", [])),
            "assumptions": list(requirement.get("assumptions", [])),
            "candidate_strategy": "generate small template-backed alternatives and select one for CAD IR",
            "requirement_snapshot": requirement,
            "source": {"intent_version": intent.get("version")},
        }

    def generate_candidate_plans(
        self,
        design_brief: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        requirement = deepcopy(design_brief.get("requirement_snapshot", {}))
        if not requirement:
            requirement = _requirement_from_brief(design_brief)
        planning_artifact = self.create_plan(requirement, context=context)
        selected = planning_artifact["selected_parts"][0]["resolved_decisions"]
        baseline_ir = _ir_from_decisions(selected, source_stage="candidate_plan")
        conservative_ir = deepcopy(baseline_ir)
        conservative_ir["part_name"] = f"{baseline_ir['part_name']}_candidate_a"
        alternate_ir = _alternate_ir(baseline_ir)
        return [
            _candidate(
                candidate_id="A",
                label="template_resolved",
                summary="Uses the closest supported CadFlow template with the interpreted dimensions and features.",
                ir=conservative_ir,
                design_brief=design_brief,
                planning_artifact=planning_artifact,
                selected=True,
            ),
            _candidate(
                candidate_id="B",
                label="manufacturing_conservative",
                summary="Keeps the same topology but nudges optional feature choices toward conservative fabrication.",
                ir=alternate_ir,
                design_brief=design_brief,
                planning_artifact=planning_artifact,
                selected=False,
            ),
        ]

    def convert_plan_to_ir(self, selected_plan: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        ir = deepcopy(selected_plan.get("cad_ir", {}))
        if not ir:
            ir = _ir_from_decisions(selected_plan.get("resolved_decisions", {}), source_stage="selected_plan")
        source = dict(ir.get("source", {}))
        source["agent_create_workflow"] = {
            "selected_candidate": selected_plan.get("candidate_id"),
            "candidate_label": selected_plan.get("label"),
            "adapter": "design_planner_fake",
            "consumed_fields": ["cad_ir", "resolved_decisions"],
        }
        ir["source"] = source
        validate_input_ir_draft(ir)
        return ir

    def parse_revision_request(
        self,
        prompt: str,
        model_context: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_ir = model_context.get("input_ir", {})
        changes = _parse_revision_changes(prompt, current_ir)
        return {
            "artifact_type": "revision_intent",
            "version": "revision-intent-v0.1",
            "prompt_summary": _prompt_summary(prompt),
            "requested_change": prompt.strip(),
            "target_part_type": current_ir.get("part_type"),
            "changes": changes,
            "model_context_keys": sorted(model_context.keys()),
            "status": "parsed",
        }

    def create_revision_plan(
        self,
        change_intent: dict[str, Any],
        model_context: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_ir = model_context.get("input_ir", {})
        operations = []
        for change in change_intent.get("changes", []):
            path = change.get("path")
            if not path:
                continue
            operations.append({
                "op": change.get("op", "replace"),
                "path": path,
                "before": _get_path(current_ir, path),
                "after": change.get("value"),
                "reason": change.get("reason", change_intent.get("requested_change", "revision request")),
            })
        return {
            "artifact_type": "revision_plan",
            "version": "revision-plan-v0.1",
            "status": "ready_for_patch" if operations else "no_structured_changes",
            "change_intent": deepcopy(change_intent),
            "model_context_keys": sorted(model_context.keys()),
            "target_artifact": "input_ir.json",
            "strategy": "cadflow_native_cad_ir_patch",
            "planned_operations": operations,
        }


def _prompt_summary(prompt: str) -> str:
    return " ".join(prompt.strip().split())[:240]


def _functional_requirements(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = [{
        "kind": "primary_shape",
        "part_type": requirement["part_type"],
        "reason": "recognized as a supported CadFlow part family",
    }]
    for name, value in sorted(requirement.get("features", {}).items()):
        requirements.append({
            "kind": "feature",
            "feature": name,
            "value": deepcopy(value),
            "reason": "requested or defaulted feature for the selected design family",
        })
    return requirements


def _requirement_from_brief(design_brief: dict[str, Any]) -> dict[str, Any]:
    constraints = design_brief.get("geometry_constraints", {})
    return {
        "part_type": design_brief["part_type"],
        "unit": constraints.get("unit", "mm"),
        "dimensions": deepcopy(constraints.get("dimensions", {})),
        "features": deepcopy(constraints.get("features", {})),
        "outputs": ["step", "stl"],
        "check_level": "L0",
    }


def _ir_from_decisions(decisions: dict[str, Any], source_stage: str) -> dict[str, Any]:
    ir = {
        "part_type": decisions["part_type"],
        "part_name": decisions.get("part_name") or decisions["part_type"],
        "unit": decisions.get("unit", "mm"),
        "dimensions": deepcopy(decisions.get("dimensions", {})),
        "features": deepcopy(decisions.get("features", {})),
        "outputs": list(decisions.get("outputs", ["step", "stl"])),
        "check_level": decisions.get("check_level", "L0"),
        "source": deepcopy(decisions.get("source", {})),
    }
    ir["source"]["agent_planning_stage"] = source_stage
    return ir


def _alternate_ir(ir: dict[str, Any]) -> dict[str, Any]:
    alternate = deepcopy(ir)
    alternate["part_name"] = f"{ir['part_name']}_candidate_b"
    features = deepcopy(alternate.get("features", {}))
    if alternate["part_type"] == "mounting_plate":
        features.setdefault("chamfer", {"size": 0.5})
    elif alternate["part_type"] == "spacer":
        dimensions = deepcopy(alternate["dimensions"])
        dimensions["outer_diameter"] = round(dimensions["outer_diameter"] + 2.0, 3)
        alternate["dimensions"] = dimensions
    elif alternate["part_type"] == "simple_bracket":
        features.pop("fillet", None)
    alternate["features"] = features
    return alternate


def _candidate(
    *,
    candidate_id: str,
    label: str,
    summary: str,
    ir: dict[str, Any],
    design_brief: dict[str, Any],
    planning_artifact: dict[str, Any],
    selected: bool,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "label": label,
        "summary": summary,
        "selected_by_default": selected,
        "part_type": ir["part_type"],
        "resolved_decisions": {
            "part_type": ir["part_type"],
            "part_name": ir["part_name"],
            "unit": ir.get("unit", "mm"),
            "dimensions": deepcopy(ir.get("dimensions", {})),
            "features": deepcopy(ir.get("features", {})),
            "outputs": list(ir.get("outputs", ["step", "stl"])),
            "check_level": ir.get("check_level", "L0"),
        },
        "design_rationale": [
            "Keeps geometry inside the current validated CadFlow IR contract.",
            "Leaves execution to run_ir_pipeline after CAD IR validation.",
        ],
        "tradeoffs": ["Template-backed topology limits novelty but produces executable CAD output."],
        "cad_ir": ir,
        "source": {
            "design_brief_version": design_brief.get("version"),
            "planning_artifact_version": planning_artifact.get("version"),
        },
    }


def _parse_revision_changes(prompt: str, current_ir: dict[str, Any]) -> list[dict[str, Any]]:
    lowered = prompt.lower()
    changes: list[dict[str, Any]] = []
    for dimension in current_ir.get("dimensions", {}):
        label = dimension.replace("_", " ")
        pattern = rf"(?:{re.escape(label)}|{re.escape(dimension)})\D{{0,18}}(\d+(?:\.\d+)?)\s*(?:mm)?"
        match = re.search(pattern, lowered)
        if match:
            changes.append({
                "op": "replace",
                "path": f"dimensions.{dimension}",
                "value": float(match.group(1)),
                "reason": f"User requested {label} change.",
            })
    thickness_match = re.search(r"(?:thickness|thick|thicker)\D{0,18}(\d+(?:\.\d+)?)\s*(?:mm)?", lowered)
    if thickness_match and "thickness" in current_ir.get("dimensions", {}):
        _upsert_change(changes, {
            "op": "replace",
            "path": "dimensions.thickness",
            "value": float(thickness_match.group(1)),
            "reason": "User requested thickness change.",
        })
    metric_fastener = re.search(r"\bM(\d+(?:\.\d+)?)\b", prompt, flags=re.IGNORECASE)
    if metric_fastener:
        hole_path = _hole_diameter_path(current_ir)
        if hole_path:
            nominal = float(metric_fastener.group(1))
            _upsert_change(changes, {
                "op": "replace",
                "path": hole_path,
                "value": round(nominal + 0.5, 3),
                "reason": f"User requested M{metric_fastener.group(1)} clearance holes.",
            })
    hole_diameter = re.search(r"(?:hole|holes|diameter|dia)\D{0,18}(\d+(?:\.\d+)?)\s*(?:mm)?", lowered)
    if hole_diameter and not metric_fastener:
        hole_path = _hole_diameter_path(current_ir)
        if hole_path:
            _upsert_change(changes, {
                "op": "replace",
                "path": hole_path,
                "value": float(hole_diameter.group(1)),
                "reason": "User requested hole diameter change.",
            })
    if re.search(r"\b(?:remove|delete|drop|without|no)\b.{0,24}\bchamfer\b", lowered) and "chamfer" in current_ir.get("features", {}):
        _upsert_change(changes, {
            "op": "remove",
            "path": "features.chamfer",
            "value": None,
            "reason": "User requested chamfer removal.",
        })
    return changes


def _hole_diameter_path(current_ir: dict[str, Any]) -> str | None:
    features = current_ir.get("features", {})
    for feature_name in ("holes", "mounting_holes", "base_holes", "wall_hole"):
        feature = features.get(feature_name)
        if isinstance(feature, dict) and "diameter" in feature:
            return f"features.{feature_name}.diameter"
    return None


def _upsert_change(changes: list[dict[str, Any]], change: dict[str, Any]) -> None:
    for index, existing in enumerate(changes):
        if existing.get("path") == change.get("path"):
            changes[index] = change
            return
    changes.append(change)


def _get_path(data: dict[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return deepcopy(current)
