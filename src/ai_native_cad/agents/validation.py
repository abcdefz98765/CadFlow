"""Validation helpers for AgentAdapter outputs.

These checks are intentionally narrow. They verify the structured draft shape
that adapters are allowed to return before workflow code persists or consumes
the result.
"""

from __future__ import annotations

from typing import Any

from ai_native_cad.cad_ir.validator import validate_ir

FORBIDDEN_BYPASS_KEYS = {
    "cad_code",
    "cadquery_code",
    "command",
    "model_code",
    "python_code",
    "shell",
    "shell_command",
    "script",
}


def validate_adapter_result(operation: str, content: dict[str, Any]) -> None:
    """Validate a structured adapter result for a known operation."""

    if operation == "parse_requirement":
        validate_requirement_draft(content)
        return
    if operation == "create_plan":
        validate_planning_draft(content)
        return
    if operation == "interpret_user_intent":
        validate_intent_draft(content)
        return
    if operation == "propose_design_brief":
        validate_design_brief_draft(content)
        return
    if operation == "convert_plan_to_ir":
        validate_input_ir_draft(content)
        return
    if operation in {"parse_revision_request", "create_revision_plan"}:
        _require_object(content, f"{operation} adapter output")
        _reject_direct_cad_bypass(content)
        return
    if operation == "suggest_repair":
        validate_repair_suggestion(content)
        return
    if operation == "explain_review":
        validate_review_explanation(content)
        return
    raise ValueError(f"unsupported adapter operation: {operation}")


def validate_requirement_draft(content: dict[str, Any]) -> None:
    _require_object(content, "requirement adapter output")
    _reject_direct_cad_bypass(content)
    _require_keys(content, "requirement.json", ("part_type", "dimensions"))
    if not isinstance(content.get("part_type"), str) or not content["part_type"]:
        raise ValueError("requirement.json part_type must be a non-empty string")
    if not isinstance(content.get("dimensions"), dict):
        raise ValueError("requirement.json dimensions must be a dictionary")
    if "features" in content and not isinstance(content["features"], dict):
        raise ValueError("requirement.json features must be a dictionary")
    if "requirement_status" in content and not isinstance(content["requirement_status"], dict):
        raise ValueError("requirement.json requirement_status must be a dictionary")


def validate_planning_draft(content: dict[str, Any]) -> None:
    _require_object(content, "planning adapter output")
    _reject_direct_cad_bypass(content)
    _require_keys(content, "planning_artifact.json", ("artifact_type", "route", "selected_parts", "flow_gate_status"))
    if content.get("artifact_type") != "planning":
        raise ValueError("planning_artifact.json artifact_type must be 'planning'")
    if not isinstance(content.get("route"), dict):
        raise ValueError("planning_artifact.json route must be a dictionary")
    if not isinstance(content.get("selected_parts"), list):
        raise ValueError("planning_artifact.json selected_parts must be a list")
    if not isinstance(content.get("flow_gate_status"), dict):
        raise ValueError("planning_artifact.json flow_gate_status must be a dictionary")


def validate_intent_draft(content: dict[str, Any]) -> None:
    _require_object(content, "intent adapter output")
    _reject_direct_cad_bypass(content)
    _require_keys(content, "intent.json", ("artifact_type", "recognized_part_type", "interpreted_constraints"))
    if content.get("artifact_type") != "intent":
        raise ValueError("intent.json artifact_type must be 'intent'")
    if not isinstance(content.get("recognized_part_type"), str) or not content["recognized_part_type"]:
        raise ValueError("intent.json recognized_part_type must be a non-empty string")
    if not isinstance(content.get("interpreted_constraints"), dict):
        raise ValueError("intent.json interpreted_constraints must be a dictionary")


def validate_design_brief_draft(content: dict[str, Any]) -> None:
    _require_object(content, "design brief adapter output")
    _reject_direct_cad_bypass(content)
    _require_keys(content, "design_brief.json", ("artifact_type", "part_type", "geometry_constraints"))
    if content.get("artifact_type") != "design_brief":
        raise ValueError("design_brief.json artifact_type must be 'design_brief'")
    if not isinstance(content.get("part_type"), str) or not content["part_type"]:
        raise ValueError("design_brief.json part_type must be a non-empty string")
    if not isinstance(content.get("geometry_constraints"), dict):
        raise ValueError("design_brief.json geometry_constraints must be a dictionary")


def validate_input_ir_draft(content: dict[str, Any]) -> None:
    _require_object(content, "input_ir adapter output")
    _reject_direct_cad_bypass(content)
    validation = validate_ir(content)
    if not validation["valid"]:
        codes = ", ".join(error.get("code", "unknown") for error in validation["errors"])
        raise ValueError(f"input_ir.json failed CAD IR validation: {codes}")


def validate_repair_suggestion(content: dict[str, Any]) -> None:
    _require_object(content, "repair adapter output")
    _reject_direct_cad_bypass(content)
    _require_keys(content, "repair adapter output", ("analysis", "repair"))
    if not isinstance(content.get("analysis"), dict):
        raise ValueError("repair adapter output analysis must be a dictionary")
    if not isinstance(content.get("repair"), dict):
        raise ValueError("repair adapter output repair must be a dictionary")
    repaired_ir = content["repair"].get("repaired_ir")
    if repaired_ir is not None:
        validate_input_ir_draft(repaired_ir)


def validate_review_explanation(content: dict[str, Any]) -> None:
    _require_object(content, "review adapter output")
    _reject_direct_cad_bypass(content)
    _require_keys(content, "review adapter output", ("status", "summary"))
    if not isinstance(content.get("status"), str) or not content["status"]:
        raise ValueError("review adapter output status must be a non-empty string")
    if not isinstance(content.get("summary"), str) or not content["summary"]:
        raise ValueError("review adapter output summary must be a non-empty string")
    if "errors" in content and not isinstance(content["errors"], list):
        raise ValueError("review adapter output errors must be a list")
    if "warnings" in content and not isinstance(content["warnings"], list):
        raise ValueError("review adapter output warnings must be a list")


def _reject_direct_cad_bypass(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text.lower() in FORBIDDEN_BYPASS_KEYS:
                raise ValueError(f"adapter output contains forbidden bypass field: {child_path}")
            _reject_direct_cad_bypass(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_direct_cad_bypass(child, f"{path}[{index}]")


def _require_object(content: Any, label: str) -> None:
    if not isinstance(content, dict):
        raise ValueError(f"{label} must be a JSON object")


def _require_keys(content: dict[str, Any], artifact: str, keys: tuple[str, ...]) -> None:
    missing = [key for key in keys if key not in content]
    if missing:
        raise ValueError(f"{artifact} is missing required fields: {', '.join(missing)}")
