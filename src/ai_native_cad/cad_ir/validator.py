"""Validation for the CAD IR before backend code is generated."""

from __future__ import annotations

from typing import Any

from ai_native_cad.cad_ir.schema import CADIR

SUPPORTED_PART_TYPES = {
    "mounting_plate",
    "spacer",
    "simple_bracket",
    "wall_bracket",
    "circular_button",
    "enclosure_base",
    "enclosure_lid",
}
SUPPORTED_OUTPUTS = {"step", "stl"}

SUPPORTED_FEATURES_BY_PART_TYPE = {
    "mounting_plate": {"holes", "mounting_holes", "chamfer"},
    "spacer": set(),
    "simple_bracket": {"holes", "base_holes", "fillet"},
    "wall_bracket": {"base_holes", "wall_hole", "fillet"},
    "circular_button": {
        "switch_pocket",
        "actuator_post",
        "contact_slots",
        "wire_exit",
        "anti_slip_feet",
        "edge_finish",
    },
    "enclosure_base": {"bosses", "bottom_cutout", "fillet"},
    "enclosure_lid": {"holes", "chamfer"},
}

UNVERIFIED_FEATURES_BY_PART_TYPE = {
    "simple_bracket": {"fillet"},
    "wall_bracket": {"base_holes", "wall_hole", "fillet"},
    "circular_button": {
        "switch_pocket",
        "actuator_post",
        "contact_slots",
        "wire_exit",
        "anti_slip_feet",
        "edge_finish",
    },
    "enclosure_base": {"bosses", "bottom_cutout", "fillet"},
}

REQUIRED_DIMENSIONS = {
    "mounting_plate": {"length", "width", "thickness"},
    "spacer": {"outer_diameter", "inner_diameter", "thickness"},
    "simple_bracket": {"base_length", "base_width", "height", "thickness"},
    "wall_bracket": {"base_width", "base_depth", "wall_height", "material_thickness"},
    "circular_button": {"body_diameter", "body_height", "button_diameter", "button_height"},
    "enclosure_base": {"outer_length", "outer_width", "outer_height", "wall_thickness"},
    "enclosure_lid": {"length", "width", "thickness"},
}


def validate_ir(ir: CADIR | dict[str, Any]) -> dict[str, Any]:
    """Return structured validation results for an IR object."""
    cad_ir = CADIR.from_dict(ir) if isinstance(ir, dict) else ir
    result = {"valid": True, "checks": [], "warnings": [], "errors": []}

    _check(result, "unit_mm", cad_ir.unit == "mm", actual=cad_ir.unit)
    if cad_ir.unit != "mm":
        result["errors"].append({"code": "unsupported_unit", "message": "Only millimeter IR is supported today"})

    _check(result, "supported_part_type", cad_ir.part_type in SUPPORTED_PART_TYPES, actual=cad_ir.part_type)
    if cad_ir.part_type not in SUPPORTED_PART_TYPES:
        result["errors"].append({"code": "unsupported_part_type", "message": f"Unsupported part_type: {cad_ir.part_type}"})

    required = REQUIRED_DIMENSIONS.get(cad_ir.part_type, set())
    for name in sorted(required):
        present = name in cad_ir.dimensions
        positive = present and cad_ir.dimensions[name] > 0
        _check(result, "required_dimension", present and positive, dimension=name, actual=cad_ir.dimensions.get(name))
        if not present:
            result["errors"].append({"code": "missing_dimension", "message": f"Missing dimension: {name}", "dimension": name})
        elif not positive:
            result["errors"].append({"code": "invalid_dimension", "message": f"Dimension must be positive: {name}", "dimension": name})

    for output in cad_ir.outputs:
        supported = output in SUPPORTED_OUTPUTS
        _check(result, "supported_output", supported, output=output)
        if not supported:
            result["errors"].append({"code": "unsupported_output", "message": f"Unsupported output format: {output}"})

    _validate_supported_features(result, cad_ir)

    result["valid"] = not result["errors"]
    return result


def _check(result: dict[str, Any], name: str, passed: bool, **extra: Any) -> None:
    result["checks"].append({"check": name, "pass": passed, **extra})


def _validate_supported_features(result: dict[str, Any], cad_ir: CADIR) -> None:
    supported_features = SUPPORTED_FEATURES_BY_PART_TYPE.get(cad_ir.part_type, set())
    for feature_name, feature_value in cad_ir.features.items():
        supported = feature_name in supported_features
        _check(
            result,
            "supported_feature",
            supported,
            part_type=cad_ir.part_type,
            feature=feature_name,
        )
        if not supported:
            result["errors"].append({
                "code": "unsupported_feature",
                "message": (
                    f"Feature '{feature_name}' is not supported by the current "
                    f"Part Modeling backend for part_type '{cad_ir.part_type}'"
                ),
                "feature": feature_name,
                "part_type": cad_ir.part_type,
                "owner_stage": "planning",
            })
            continue
        if feature_name in UNVERIFIED_FEATURES_BY_PART_TYPE.get(cad_ir.part_type, set()):
            result["warnings"].append({
                "code": "feature_unverified",
                "message": (
                    f"Feature '{feature_name}' is accepted by the current "
                    f"Part Modeling backend for part_type '{cad_ir.part_type}', "
                    "but geometry verification is not implemented yet"
                ),
                "feature": feature_name,
                "part_type": cad_ir.part_type,
                "owner_stage": "review",
            })
        _validate_feature_semantics(result, cad_ir, feature_name, feature_value)


def _validate_feature_semantics(
    result: dict[str, Any],
    cad_ir: CADIR,
    feature_name: str,
    feature_value: Any,
) -> None:
    if feature_name not in {"holes", "mounting_holes", "base_holes"}:
        return
    holes = feature_value[0] if isinstance(feature_value, list) and feature_value else feature_value
    if not isinstance(holes, dict):
        _feature_semantic_error(result, cad_ir, feature_name, "Hole feature must be a dictionary or non-empty list of dictionaries")
        return
    positions = holes.get("positions")
    pattern = holes.get("pattern")
    count = holes.get("count")
    if positions is None:
        return
    if positions == "corner_4" or (pattern == "corner" and count == 4):
        return
    if isinstance(positions, list) and all(_is_xy_point(point) for point in positions):
        return
    _feature_semantic_error(
        result,
        cad_ir,
        feature_name,
        "Hole positions must be 'corner_4' or explicit [x, y] point coordinates",
    )


def _feature_semantic_error(result: dict[str, Any], cad_ir: CADIR, feature_name: str, message: str) -> None:
    _check(
        result,
        "supported_feature_semantics",
        False,
        part_type=cad_ir.part_type,
        feature=feature_name,
    )
    result["errors"].append({
        "code": "unsupported_feature_semantics",
        "message": message,
        "feature": feature_name,
        "part_type": cad_ir.part_type,
        "owner_stage": "planning",
    })


def _is_xy_point(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(item, (int, float)) for item in value)
    )
