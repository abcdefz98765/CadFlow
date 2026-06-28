"""Requirement agent for workflow-first CAD.

The first implementation is intentionally deterministic. It turns natural
language plus optional overrides into the stable ``requirement.json`` contract,
records assumptions, and emits follow-up questions when important information is
missing. It does not stop L0 playground generation yet.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from ai_native_cad.generator import get_part_spec, merge_params

CHECK_LEVELS = {
    "L0": "Playground",
    "L1": "Maker",
    "L2": "Engineering",
    "L3": "Industrial",
    "L4": "Safety Critical",
}

FIELD_POLICY_VERSION = "requirement-fields-v0.1"

REQUIREMENT_FIELD_POLICY = {
    "L0": {
        "required": ["object_goal", "scope", "primary_dimensions", "functional_features"],
        "optional": ["material", "manufacturing_process", "assembly_method"],
        "defer": ["tolerances", "surface_finish", "loads", "certification"],
    },
    "L1": {
        "required": [
            "object_goal",
            "scope",
            "primary_dimensions",
            "functional_features",
            "manufacturing_process",
            "assembly_clearance",
            "serviceability",
        ],
        "optional": ["material", "fasteners", "reference_components"],
        "defer": ["precision_tolerances", "surface_finish", "certification"],
    },
    "L2": {
        "required": [
            "object_goal",
            "scope",
            "primary_dimensions",
            "functional_features",
            "material",
            "manufacturing_process",
            "functional_tolerances",
            "interface_definitions",
            "loads",
            "environment",
        ],
        "optional": ["surface_finish_by_functional_face", "inspection_method"],
        "defer": ["industrial_dfa", "safety_case"],
    },
    "L3": {
        "required": [
            "object_goal",
            "scope",
            "primary_dimensions",
            "material",
            "manufacturing_process",
            "functional_tolerances",
            "inspection_method",
            "bom_strategy",
            "dfm_dfa_constraints",
        ],
        "optional": ["supplier_constraints", "versioning_policy"],
        "defer": ["safety_case"],
    },
    "L4": {
        "required": [
            "object_goal",
            "scope",
            "primary_dimensions",
            "material",
            "manufacturing_process",
            "functional_tolerances",
            "applicable_standards",
            "hazard_analysis",
            "verification_plan",
            "human_signoff",
        ],
        "optional": [],
        "defer": [],
    },
}


class RequirementAgent:
    """Create structured CAD requirements and missing-info prompts."""

    def parse(self, text: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        overrides = overrides or {}
        part_type = overrides.get("part_type") or self._detect_part_type(text)
        base = deepcopy(get_part_spec(part_type))
        requirement = merge_params(base, overrides)
        requirement.setdefault("unit", "mm")
        requirement.setdefault("outputs", ["step", "stl"])
        requirement["check_level"] = normalize_check_level(requirement.get("check_level", "L0"))
        requirement.setdefault("source", {})
        requirement["source"]["input_text"] = text
        requirement["intent"] = self._infer_intent(text, requirement)
        requirement["field_policy"] = {
            "version": FIELD_POLICY_VERSION,
            "check_level": requirement["check_level"],
            **REQUIREMENT_FIELD_POLICY[requirement["check_level"]],
        }
        requirement["assumptions"] = self._assumptions(text, requirement, overrides)
        requirement["missing_information"] = self._missing_information(text, requirement, overrides)
        requirement["follow_up_questions"] = [
            item["question"] for item in requirement["missing_information"] if item.get("ask_user")
        ]
        requirement["requirement_status"] = self._status(requirement)
        return requirement

    def _detect_part_type(self, text: str) -> str:
        lowered = text.lower()
        if "button" in lowered or "pushbutton" in lowered or "按钮" in text or "按键" in text:
            return "circular_button"
        if "mounting" in lowered or "安装板" in text or "四角" in text:
            return "mounting_plate"
        if "spacer" in lowered or "standoff" in lowered or "隔套" in text:
            return "spacer"
        if "bracket" in lowered or "支架" in text:
            return "wall_bracket"
        if "enclosure" in lowered or "外壳" in text:
            return "enclosure_base"
        return "mounting_plate"

    def _infer_intent(self, text: str, requirement: dict[str, Any]) -> dict[str, Any]:
        lowered = text.lower()
        scope = "assembly" if any(token in lowered or token in text for token in ("assembly", "装配", "组装")) else "part"
        if requirement["part_type"].startswith("pet_button_"):
            scope = "assembly_part"
        return {
            "object_goal": requirement["part_type"],
            "scope": scope,
            "use_case": _detect_use_case(text),
        }

    def _assumptions(self, text: str, requirement: dict[str, Any], overrides: dict[str, Any]) -> list[str]:
        assumptions = list(requirement.get("assumptions", []))
        if not assumptions:
            assumptions.append("L0 workflow uses template-backed parameter extraction for the MVP.")
        if not _has_dimension_hint(text) and "dimensions" not in overrides:
            assumptions.append("Primary dimensions were taken from the selected part template.")
        if "manufacturing_process" not in requirement:
            assumptions.append("Manufacturing process is unspecified; L0 treats it as non-blocking.")
        return assumptions

    def _missing_information(
        self,
        text: str,
        requirement: dict[str, Any],
        overrides: dict[str, Any],
    ) -> list[dict[str, Any]]:
        level = requirement["check_level"]
        missing: list[dict[str, Any]] = []
        if not _has_dimension_hint(text) and "dimensions" not in overrides:
            missing.append(_question(
                "primary_dimensions",
                "What are the main dimensions or size limits?",
                "critical",
                level in {"L1", "L2", "L3", "L4"},
                "Topology may stay valid, but scale and fit depend on these values.",
            ))
        if level in {"L1", "L2", "L3", "L4"} and "manufacturing_process" not in requirement:
            missing.append(_question(
                "manufacturing_process",
                "What manufacturing process should be assumed, such as FDM, SLA, CNC, or sheet cutting?",
                "important",
                True,
                "Manufacturing process changes wall thickness, clearances, and review checks.",
            ))
        if level in {"L2", "L3", "L4"} and "material" not in requirement:
            missing.append(_question(
                "material",
                "What material or material family should be used?",
                "important",
                True,
                "Material affects strength, process limits, tolerances, and surface expectations.",
            ))
        if level in {"L2", "L3", "L4"} and "functional_tolerances" not in requirement:
            missing.append(_question(
                "functional_tolerances",
                "Which interfaces need tolerances or fits?",
                "important",
                True,
                "Engineering-level models need tolerances only where they affect function.",
            ))
        if level == "L4":
            missing.append(_question(
                "human_signoff",
                "Who is responsible for safety-critical review and approval?",
                "critical",
                True,
                "Safety-critical workflows require explicit human approval and standards context.",
            ))
        return missing

    def _status(self, requirement: dict[str, Any]) -> dict[str, Any]:
        blocking = [
            item["field"]
            for item in requirement["missing_information"]
            if item.get("ask_user") and item.get("severity") == "critical"
        ]
        return {
            "complete_for_generation": not blocking or requirement["check_level"] == "L0",
            "needs_user_input": any(item.get("ask_user") for item in requirement["missing_information"]),
            "blocking_fields": blocking,
        }


def normalize_check_level(value: str) -> str:
    level = str(value).upper().split()[0]
    if level not in CHECK_LEVELS:
        return "L0"
    return level


def _detect_use_case(text: str) -> str:
    lowered = text.lower()
    if "pet" in lowered or "宠物" in text:
        return "pet_product"
    if "mount" in lowered or "安装" in text:
        return "mounting"
    if "enclosure" in lowered or "外壳" in text:
        return "enclosure"
    return "unspecified"


def _has_dimension_hint(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\d", text):
        return True
    return any(token in lowered or token in text for token in ("mm", "cm", "diameter", "length", "width", "height", "直径", "长度", "宽度", "高度", "厚度", "尺寸"))


def _question(field: str, question: str, severity: str, ask_user: bool, reason: str) -> dict[str, Any]:
    return {
        "field": field,
        "question": question,
        "severity": severity,
        "ask_user": ask_user,
        "reason": reason,
    }
