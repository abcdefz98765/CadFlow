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

REQUIRED_REQUIREMENT_DIMENSIONS = {
    "mounting_plate": {"length", "width", "thickness"},
    "spacer": {"outer_diameter", "inner_diameter", "thickness"},
    "simple_bracket": {"base_length", "base_width", "height", "thickness"},
    "wall_bracket": {"base_width", "base_depth", "wall_height", "material_thickness"},
    "circular_button": {"body_diameter", "body_height", "button_diameter", "button_height"},
    "enclosure_base": {"outer_length", "outer_width", "outer_height", "wall_thickness"},
    "enclosure_lid": {"length", "width", "thickness"},
}

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
        extracted = self._extract_requirement_fields(text, part_type)
        requirement = merge_params(base, extracted)
        requirement = merge_params(requirement, overrides)
        requirement.setdefault("unit", "mm")
        requirement.setdefault("outputs", ["step", "stl"])
        requirement["unit"] = _detect_unit(text, requirement["unit"])
        requirement["outputs"] = _detect_outputs(text, requirement["outputs"])
        requirement["check_level"] = normalize_check_level(requirement.get("check_level", "L0"))
        requirement.setdefault("source", {})
        requirement["source"]["input_text"] = text
        requirement["source"]["parser"] = {
            "version": "deterministic-requirements-v0.2",
            "extracted_dimensions": sorted(extracted.get("dimensions", {})),
            "extracted_features": sorted(extracted.get("features", {})),
            "diagnostics": _parser_diagnostics(text, part_type, extracted),
        }
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
        requirement["follow_up_requests"] = [
            _follow_up_request(item) for item in requirement["missing_information"] if item.get("ask_user")
        ]
        requirement["requirement_status"] = self._status(requirement)
        requirement["cad_brief"] = _cad_brief(requirement)
        return requirement

    def _detect_part_type(self, text: str) -> str:
        lowered = text.lower()
        if "button" in lowered or "pushbutton" in lowered or "按钮" in text or "按键" in text:
            return "circular_button"
        if "mounting" in lowered or "安装板" in text or "四角" in text:
            return "mounting_plate"
        if "spacer" in lowered or "standoff" in lowered or "washer" in lowered or "隔套" in text:
            return "spacer"
        if "l-bracket" in lowered or "l bracket" in lowered or "simple bracket" in lowered:
            return "simple_bracket"
        if "bracket" in lowered or "支架" in text:
            return "wall_bracket"
        if "enclosure" in lowered or "外壳" in text:
            return "enclosure_base"
        return "mounting_plate"

    def _extract_requirement_fields(self, text: str, part_type: str) -> dict[str, Any]:
        dimensions = _extract_dimensions(text, part_type)
        features = _extract_features(text, part_type, dimensions)
        extracted: dict[str, Any] = {}
        if dimensions:
            extracted["dimensions"] = dimensions
        if features:
            extracted["features"] = features
        return extracted

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
        for diagnostic in requirement.get("source", {}).get("parser", {}).get("diagnostics", []):
            if diagnostic["severity"] == "critical":
                missing.append(_question(
                    diagnostic["field"],
                    diagnostic["question"],
                    "critical",
                    True,
                    diagnostic["message"],
                    category="parser_diagnostic",
                    source="parser",
                    code=diagnostic["code"],
                ))
        parsed_dimensions = set(requirement.get("source", {}).get("parser", {}).get("extracted_dimensions", []))
        for dimension in sorted(REQUIRED_REQUIREMENT_DIMENSIONS.get(requirement["part_type"], set())):
            override_dimensions = overrides.get("dimensions", {})
            if dimension in parsed_dimensions or dimension in override_dimensions:
                continue
            missing.append(_question(
                f"dimensions.{dimension}",
                f"What value should be used for {dimension.replace('_', ' ')}?",
                "critical",
                level in {"L1", "L2", "L3", "L4"},
                "Template defaults can support L0 exploration, but this dimension controls scale or fit.",
                category="primary_dimensions",
                source="parser",
                code="missing_dimension",
                default_used=dimension in requirement.get("dimensions", {}),
                default_value=requirement.get("dimensions", {}).get(dimension),
            ))
        if not _has_dimension_hint(text) and "dimensions" not in overrides and not missing:
            missing.append(_question(
                "primary_dimensions",
                "What are the main dimensions or size limits?",
                "critical",
                level in {"L1", "L2", "L3", "L4"},
                "Topology may stay valid, but scale and fit depend on these values.",
                category="primary_dimensions",
                source="parser",
                code="missing_primary_dimensions",
            ))
        if level in {"L1", "L2", "L3", "L4"} and "manufacturing_process" not in requirement:
            missing.append(_question(
                "manufacturing_process",
                "What manufacturing process should be assumed, such as FDM, SLA, CNC, or sheet cutting?",
                "important",
                True,
                "Manufacturing process changes wall thickness, clearances, and review checks.",
                category="manufacturing_context",
                source="field_policy",
                code="missing_manufacturing_process",
            ))
        if level in {"L2", "L3", "L4"} and "material" not in requirement:
            missing.append(_question(
                "material",
                "What material or material family should be used?",
                "important",
                True,
                "Material affects strength, process limits, tolerances, and surface expectations.",
                category="manufacturing_context",
                source="field_policy",
                code="missing_material",
            ))
        if level in {"L2", "L3", "L4"} and "functional_tolerances" not in requirement:
            missing.append(_question(
                "functional_tolerances",
                "Which interfaces need tolerances or fits?",
                "important",
                True,
                "Engineering-level models need tolerances only where they affect function.",
                category="engineering_constraints",
                source="field_policy",
                code="missing_functional_tolerances",
            ))
        if level == "L4":
            missing.append(_question(
                "human_signoff",
                "Who is responsible for safety-critical review and approval?",
                "critical",
                True,
                "Safety-critical workflows require explicit human approval and standards context.",
                category="safety_review",
                source="field_policy",
                code="missing_human_signoff",
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
            "missing_count": len(requirement["missing_information"]),
            "follow_up_count": sum(1 for item in requirement["missing_information"] if item.get("ask_user")),
            "blocking_count": len(blocking),
            "missing_fields": [item["field"] for item in requirement["missing_information"]],
            "non_blocking_fields": [
                item["field"]
                for item in requirement["missing_information"]
                if not (item.get("ask_user") and item.get("severity") == "critical")
            ],
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


def _detect_unit(text: str, default: str) -> str:
    lowered = text.lower()
    if re.search(r"\bmillimet(?:er|re)s?\b|\bmm\b", lowered):
        return "mm"
    if re.search(r"\bcentimet(?:er|re)s?\b|\bcm\b", lowered):
        return "mm"
    return default


def _detect_outputs(text: str, default: list[str]) -> list[str]:
    lowered = text.lower()
    outputs = []
    if "step" in lowered or ".step" in lowered or ".stp" in lowered:
        outputs.append("step")
    if "stl" in lowered or ".stl" in lowered:
        outputs.append("stl")
    return outputs or list(default)


def _parser_diagnostics(text: str, part_type: str, extracted: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    if _has_unsupported_unit(text):
        diagnostics.append({
            "code": "unsupported_unit_in_text",
            "field": "unit",
            "severity": "critical",
            "message": "The parser detected inch units, but the CAD IR currently supports millimeters only.",
            "question": "Please provide all dimensions in millimeters.",
        })
    diagnostics.extend(_dimension_conflict_diagnostics(text, part_type, extracted.get("dimensions", {})))
    return diagnostics


def _has_unsupported_unit(text: str) -> bool:
    return bool(re.search(r"\d+(?:\.\d+)?\s*(?:in|inch|inches|\")\b", text, flags=re.IGNORECASE))


def _dimension_conflict_diagnostics(
    text: str,
    part_type: str,
    extracted_dimensions: dict[str, float],
) -> list[dict[str, Any]]:
    values = _dimension_triplet(text)
    if not values:
        return []
    triplet_fields = {
        "mounting_plate": ("length", "width", "thickness"),
        "spacer": ("outer_diameter", "inner_diameter", "thickness"),
        "simple_bracket": ("base_length", "base_width", "height"),
        "enclosure_base": ("outer_length", "outer_width", "outer_height"),
    }.get(part_type)
    if not triplet_fields:
        return []

    named = _named_dimensions(text, _dimension_aliases_for_part(part_type))
    diagnostics = []
    for field, triplet_value in zip(triplet_fields, values):
        named_value = named.get(field)
        if named_value is None:
            continue
        if abs(named_value - triplet_value) > 0.001:
            diagnostics.append({
                "code": "conflicting_dimension",
                "field": f"dimensions.{field}",
                "severity": "critical",
                "message": (
                    f"Conflicting values for {field.replace('_', ' ')}: "
                    f"{triplet_value:g} mm from the size tuple and {named_value:g} mm from the named dimension."
                ),
                "question": f"Which {field.replace('_', ' ')} value should be used?",
                "tuple_value": triplet_value,
                "named_value": named_value,
                "selected_value": extracted_dimensions.get(field),
            })
    return diagnostics


def _dimension_aliases_for_part(part_type: str) -> dict[str, tuple[str, ...]]:
    aliases = {
        "mounting_plate": {
            "length": ("length", "long"),
            "width": ("width", "wide"),
            "thickness": ("thickness", "thick"),
        },
        "spacer": {
            "outer_diameter": ("outer diameter", "outside diameter", "od"),
            "inner_diameter": ("inner diameter", "inside diameter", "id", "hole diameter"),
            "thickness": ("thickness", "thick", "height", "tall", "long"),
        },
        "simple_bracket": {
            "base_length": ("base length", "length", "long"),
            "base_width": ("base width", "width", "wide"),
            "height": ("height", "tall"),
            "thickness": ("thickness", "thick", "material thickness"),
        },
        "enclosure_base": {
            "outer_length": ("outer length", "length", "long"),
            "outer_width": ("outer width", "width", "wide"),
            "outer_height": ("outer height", "height", "tall"),
            "wall_thickness": ("wall thickness", "wall"),
        },
    }
    return aliases.get(part_type, {})


def _extract_dimensions(text: str, part_type: str) -> dict[str, float]:
    extractors = {
        "mounting_plate": _extract_mounting_plate_dimensions,
        "spacer": _extract_spacer_dimensions,
        "simple_bracket": _extract_simple_bracket_dimensions,
        "enclosure_base": _extract_enclosure_base_dimensions,
    }
    extractor = extractors.get(part_type)
    return extractor(text) if extractor else {}


def _extract_mounting_plate_dimensions(text: str) -> dict[str, float]:
    values = _dimension_triplet(text)
    named = _named_dimensions(text, _dimension_aliases_for_part("mounting_plate"))
    if values:
        dims = {"length": values[0], "width": values[1], "thickness": values[2]}
        dims.update({key: value for key, value in named.items() if key not in dims})
        return dims
    return named


def _extract_spacer_dimensions(text: str) -> dict[str, float]:
    values = _dimension_triplet(text)
    if values:
        return {"outer_diameter": values[0], "inner_diameter": values[1], "thickness": values[2]}
    dims = {}
    patterns = {
        "outer_diameter": r"(?:od|outer\s+diameter|outside\s+diameter)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*([a-z\"]+)?",
        "inner_diameter": r"(?:id|inner\s+diameter|inside\s+diameter|hole\s+diameter)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*([a-z\"]+)?",
        "thickness": r"(?:thickness|thick|height|tall|long)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*([a-z\"]+)?",
    }
    for name, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _to_mm(float(match.group(1)), match.group(2))
            if value is not None:
                dims[name] = value
    return dims


def _extract_simple_bracket_dimensions(text: str) -> dict[str, float]:
    values = _dimension_triplet(text)
    if values:
        return {"base_length": values[0], "base_width": values[1], "height": values[2]}
    return _named_dimensions(text, _dimension_aliases_for_part("simple_bracket"))


def _extract_enclosure_base_dimensions(text: str) -> dict[str, float]:
    values = _dimension_triplet(text)
    dims = {}
    if values:
        dims.update({"outer_length": values[0], "outer_width": values[1], "outer_height": values[2]})
    dims.update(_named_dimensions(text, _dimension_aliases_for_part("enclosure_base")))
    return dims


def _extract_features(text: str, part_type: str, dimensions: dict[str, float]) -> dict[str, Any]:
    if part_type == "mounting_plate":
        holes = _extract_holes(text)
        if holes:
            if holes.get("count") == 4 and ("corner" in text.lower() or "four" in text.lower() or "4" in text):
                holes.setdefault("positions", "corner_4")
                holes.setdefault("pattern", "corner")
                if dimensions:
                    holes.setdefault("offset_from_edge", min(dimensions.values()) * 0.2)
            return {"holes": holes}
    if part_type == "simple_bracket":
        holes = _extract_holes(text)
        if holes:
            return {"base_holes": holes}
    return {}


def _extract_holes(text: str) -> dict[str, Any]:
    lowered = text.lower()
    if "hole" not in lowered and not re.search(r"\bm\d+(?:\.\d+)?\b", lowered):
        return {}
    holes: dict[str, Any] = {}
    count = _extract_count(text)
    if count:
        holes["count"] = count
    metric = re.search(r"\bM(\d+(?:\.\d+)?)\b", text, flags=re.IGNORECASE)
    if metric:
        holes["fastener"] = f"M{metric.group(1).rstrip('0').rstrip('.')}"
        holes["diameter"] = round(float(metric.group(1)) + 0.5, 3)
    diameter = re.search(
        r"(?:hole|holes|diameter|dia|ø|Ø)\D{0,12}(\d+(?:\.\d+)?)\s*([a-z\"]+)?",
        text,
        flags=re.IGNORECASE,
    )
    if diameter:
        value = _to_mm(float(diameter.group(1)), diameter.group(2))
        if value is not None:
            holes["diameter"] = value
    if "corner" in lowered or "corners" in lowered:
        holes["pattern"] = "corner"
        if holes.get("count") == 4:
            holes["positions"] = "corner_4"
    offset = re.search(r"(?:offset|inset|from edge)\D{0,12}(\d+(?:\.\d+)?)\s*([a-z\"]+)?", text, flags=re.IGNORECASE)
    if not offset:
        offset = re.search(r"(\d+(?:\.\d+)?)\s*([a-z\"]+)?\s*(?:from|off)\s+(?:the\s+)?edge", text, flags=re.IGNORECASE)
    if offset:
        value = _to_mm(float(offset.group(1)), offset.group(2))
        if value is not None:
            holes["offset_from_edge"] = value
    return holes


def _dimension_triplet(text: str) -> tuple[float, float, float] | None:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:mm|cm|millimeters?|millimetres?|centimeters?|centimetres?|in|inch|inches|\")?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:mm|cm|millimeters?|millimetres?|centimeters?|centimetres?|in|inch|inches|\")?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(mm|cm|millimeters?|millimetres?|centimeters?|centimetres?|in|inch|inches|\")?",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    unit = match.group(4)
    converted = [_to_mm(float(match.group(index)), unit) for index in (1, 2, 3)]
    if any(value is None for value in converted):
        return None
    return (
        converted[0],
        converted[1],
        converted[2],
    )


def _named_dimensions(text: str, aliases: dict[str, tuple[str, ...]]) -> dict[str, float]:
    dimensions = {}
    for field, names in aliases.items():
        for name in names:
            pattern = rf"(?:{re.escape(name)})\s*[:=]?\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*([a-z\"]+)?"
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = _to_mm(float(match.group(1)), match.group(2))
                if value is not None:
                    dimensions[field] = value
                break
            reverse = rf"(\d+(?:\.\d+)?)\s*([a-z\"]+)?\s*(?:{re.escape(name)})"
            match = re.search(reverse, text, flags=re.IGNORECASE)
            if match:
                value = _to_mm(float(match.group(1)), match.group(2))
                if value is not None:
                    dimensions[field] = value
                break
    return dimensions


def _extract_count(text: str) -> int | None:
    lowered = text.lower()
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
    for word, value in words.items():
        if re.search(rf"\b{word}\b", lowered):
            return value
    match = re.search(r"\b(\d+)\s*(?:x\s*)?(?:mounting\s*)?holes?\b", lowered)
    if match:
        return int(match.group(1))
    return None


def _to_mm(value: float, unit: str | None) -> float | None:
    if not unit:
        return value
    normalized = unit.lower().strip()
    if normalized in {"mm", "millimeter", "millimeters", "millimetre", "millimetres"}:
        return value
    if normalized in {"cm", "centimeter", "centimeters", "centimetre", "centimetres"}:
        return value * 10
    if normalized in {"in", "inch", "inches", '"'}:
        return None
    return value


def _has_dimension_hint(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\d", text):
        return True
    return any(token in lowered or token in text for token in ("mm", "cm", "diameter", "length", "width", "height", "直径", "长度", "宽度", "高度", "厚度", "尺寸"))


def _question(
    field: str,
    question: str,
    severity: str,
    ask_user: bool,
    reason: str,
    category: str = "general",
    source: str = "field_policy",
    code: str = "missing_information",
    default_used: bool = False,
    default_value: Any | None = None,
) -> dict[str, Any]:
    item = {
        "field": field,
        "category": category,
        "code": code,
        "question": question,
        "severity": severity,
        "ask_user": ask_user,
        "reason": reason,
        "source": source,
        "default_used": default_used,
    }
    if default_used:
        item["default_value"] = default_value
    return item


def _follow_up_request(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "field": item["field"],
        "category": item["category"],
        "code": item["code"],
        "question": item["question"],
        "severity": item["severity"],
        "reason": item["reason"],
        "source": item["source"],
    }


def _cad_brief(requirement: dict[str, Any]) -> dict[str, Any]:
    parser = requirement.get("source", {}).get("parser", {})
    extracted_dimensions = set(parser.get("extracted_dimensions", []))
    extracted_features = set(parser.get("extracted_features", []))
    return {
        "part_type": requirement["part_type"],
        "intent": deepcopy(requirement.get("intent", {})),
        "coordinate_convention": _coordinate_convention(requirement),
        "dimension_fields": _brief_dimension_fields(requirement, extracted_dimensions),
        "feature_fields": _brief_feature_fields(requirement, extracted_features),
        "validation_targets": _brief_validation_targets(requirement),
        "assumption_policy": _brief_assumption_policy(requirement),
        "clarification_summary": _brief_clarification_summary(requirement),
    }


def _coordinate_convention(requirement: dict[str, Any]) -> dict[str, Any]:
    axes = {
        "mounting_plate": {"x": "length", "y": "width", "z": "thickness"},
        "spacer": {"x": "outer_diameter", "y": "outer_diameter", "z": "thickness"},
        "simple_bracket": {"x": "base_length", "y": "base_width", "z": "height"},
        "enclosure_base": {"x": "outer_length", "y": "outer_width", "z": "outer_height"},
    }
    return {
        "unit": requirement.get("unit", "mm"),
        "origin": "part_local_centered_or_template_defined",
        "axes": axes.get(requirement["part_type"], {}),
        "source": "cad_ir_generator_convention",
    }


def _brief_dimension_fields(requirement: dict[str, Any], extracted_dimensions: set[str]) -> list[dict[str, Any]]:
    dimensions = requirement.get("dimensions", {})
    missing_fields = {
        item["field"].removeprefix("dimensions.")
        for item in requirement.get("missing_information", [])
        if item.get("field", "").startswith("dimensions.")
    }
    fields = []
    for name in sorted(dimensions):
        fields.append({
            "field": name,
            "value": dimensions[name],
            "unit": requirement.get("unit", "mm"),
            "source": "parsed_text" if name in extracted_dimensions else "template_or_override",
            "missing_or_ambiguous": name in missing_fields,
        })
    for name in sorted(missing_fields - set(dimensions)):
        fields.append({
            "field": name,
            "value": None,
            "unit": requirement.get("unit", "mm"),
            "source": "missing_information",
            "missing_or_ambiguous": True,
        })
    return fields


def _brief_feature_fields(requirement: dict[str, Any], extracted_features: set[str]) -> list[dict[str, Any]]:
    fields = []
    for name, value in sorted(requirement.get("features", {}).items()):
        fields.append({
            "field": name,
            "value": deepcopy(value),
            "source": "parsed_text" if name in extracted_features else "template_or_override",
        })
    return fields


def _brief_validation_targets(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    targets = []
    bbox = _brief_bounding_box_target(requirement)
    if bbox:
        targets.append(bbox)
    targets.extend(_brief_hole_targets(requirement))
    return targets


def _brief_bounding_box_target(requirement: dict[str, Any]) -> dict[str, Any] | None:
    dimensions = requirement.get("dimensions", {})
    mappings = {
        "mounting_plate": {"x": "length", "y": "width", "z": "thickness"},
        "spacer": {"x": "outer_diameter", "y": "outer_diameter", "z": "thickness"},
        "simple_bracket": {"x": "base_length", "y": "base_width", "z": "height"},
        "enclosure_base": {"x": "outer_length", "y": "outer_width", "z": "outer_height"},
    }
    mapping = mappings.get(requirement["part_type"])
    if not mapping or not all(field in dimensions for field in mapping.values()):
        return None
    return {
        "kind": "bounding_box",
        "expected": {axis: dimensions[field] for axis, field in mapping.items()},
        "dimension_fields": mapping,
        "unit": requirement.get("unit", "mm"),
        "source": "cad_ir_dimensions",
    }


def _brief_hole_targets(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    targets = []
    for feature_name in ("holes", "base_holes"):
        holes = requirement.get("features", {}).get(feature_name)
        if not isinstance(holes, dict):
            continue
        for field in ("count", "diameter"):
            if field in holes:
                targets.append({
                    "kind": "feature",
                    "feature": feature_name,
                    "field": field,
                    "expected": holes[field],
                    "unit": requirement.get("unit", "mm") if field == "diameter" else None,
                    "source": "cad_ir_features",
                })
    return targets


def _brief_assumption_policy(requirement: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_level": requirement.get("check_level", "L0"),
        "defaults_allowed_for_generation": requirement.get("check_level") == "L0",
        "assumptions": list(requirement.get("assumptions", [])),
        "missing_information_policy": "ask_user_when_topology_fit_manufacturing_or_safety_changes",
    }


def _brief_clarification_summary(requirement: dict[str, Any]) -> dict[str, Any]:
    parser = requirement.get("source", {}).get("parser", {})
    return {
        "missing_fields": [item["field"] for item in requirement.get("missing_information", [])],
        "follow_up_fields": [item["field"] for item in requirement.get("follow_up_requests", [])],
        "blocking_fields": list(requirement.get("requirement_status", {}).get("blocking_fields", [])),
        "needs_user_input": requirement.get("requirement_status", {}).get("needs_user_input", False),
        "diagnostics": deepcopy(parser.get("diagnostics", [])),
    }
