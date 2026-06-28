"""Design-intent and manufacturability preflight checks.

These checks are deliberately conservative. They validate information that an
agent should know before modeling: required feature fields, basic dimensions,
edge clearances, wall thickness, and assembly-facing metadata.
"""

from __future__ import annotations

from typing import Any


FEATURE_SCHEMAS = {
    "through_hole": {"diameter", "positions"},
    "blind_hole": {"diameter", "positions", "depth"},
    "counterbore_hole": {"diameter", "positions", "counterbore_diameter", "counterbore_depth"},
    "slot": {"length", "width", "center"},
    "boss": {"diameter", "height", "positions"},
    "rib": {"thickness", "height"},
    "shell": {"wall_thickness"},
}

FASTENER_CLEARANCE_DIAMETERS = {
    "M2": 2.4,
    "M2.5": 2.9,
    "M3": 3.4,
    "M4": 4.5,
    "M5": 5.5,
    "M6": 6.6,
    "M8": 9.0,
}

DEFAULT_MIN_WALL_THICKNESS = 1.0
DEFAULT_MIN_EDGE_FACTOR = 1.5


def validate_design_intent(params: dict[str, Any]) -> dict[str, Any]:
    """Validate part parameters before or after geometry generation."""
    result = {"valid": True, "checks": [], "warnings": [], "errors": []}
    dimensions = params.get("dimensions", {})
    features = params.get("features", {})
    design = params.get("design", {})
    manufacturing = params.get("manufacturing", {})

    _check_positive_dimensions(dimensions, result)
    _check_feature_schemas(features, result)
    _check_wall_thickness(dimensions, design, manufacturing, result)
    _check_hole_edge_clearance(dimensions, features, manufacturing, result)
    _check_fastener_clearance(features, result)
    _check_assembly_metadata(params, result)

    result["valid"] = not result["errors"]
    return result


def _check_positive_dimensions(dimensions: dict[str, Any], result: dict[str, Any]) -> None:
    for key, value in dimensions.items():
        if isinstance(value, (int, float)):
            passed = value > 0
            _check(result, "positive_dimension", passed, dimension_name=key, actual=value)


def _check_feature_schemas(features: dict[str, Any], result: dict[str, Any]) -> None:
    for name, feature in features.items():
        if not isinstance(feature, dict):
            continue
        feature_type = feature.get("type")
        if feature_type is None:
            continue
        required = FEATURE_SCHEMAS.get(feature_type)
        if required is None:
            _warning(result, "unknown_feature_type", f"Unknown feature template type: {feature_type}", feature=name)
            continue
        missing = sorted(required - set(feature))
        if missing:
            _error(result, "feature_missing_required_fields", f"{name} missing fields: {', '.join(missing)}", feature=name)
        else:
            _check(result, "feature_schema", True, feature=name, feature_type=feature_type)


def _check_wall_thickness(
    dimensions: dict[str, Any],
    design: dict[str, Any],
    manufacturing: dict[str, Any],
    result: dict[str, Any],
) -> None:
    wall = dimensions.get("wall_thickness") or design.get("wall_thickness")
    if wall is None:
        return
    minimum = manufacturing.get("min_wall_thickness", DEFAULT_MIN_WALL_THICKNESS)
    passed = wall >= minimum
    _check(result, "min_wall_thickness", passed, expected_min=minimum, actual=wall)
    if not passed:
        _error(result, "wall_too_thin", f"Wall thickness {wall}mm is below minimum {minimum}mm")


def _check_hole_edge_clearance(
    dimensions: dict[str, Any],
    features: dict[str, Any],
    manufacturing: dict[str, Any],
    result: dict[str, Any],
) -> None:
    edge_factor = manufacturing.get("min_hole_edge_factor", DEFAULT_MIN_EDGE_FACTOR)
    length = dimensions.get("length") or dimensions.get("outer_length")
    width = dimensions.get("width") or dimensions.get("outer_width")

    for name, feature in features.items():
        if not isinstance(feature, dict):
            continue
        diameter = feature.get("diameter") or feature.get("hole_diameter")
        offset = feature.get("offset_from_edge")
        if diameter is None or offset is None:
            continue
        required = diameter * edge_factor
        passed = offset >= required
        _check(result, "hole_edge_clearance", passed, feature=name, expected_min=round(required, 3), actual=offset)
        if not passed:
            _warning(
                result,
                "hole_near_edge",
                f"{name} edge offset {offset}mm is below recommended {required:.3f}mm",
                feature=name,
            )
        if length and width and offset * 2 >= min(length, width):
            _error(result, "hole_offset_exceeds_part", f"{name} offset leaves no usable span", feature=name)


def _check_fastener_clearance(features: dict[str, Any], result: dict[str, Any]) -> None:
    for name, feature in features.items():
        if not isinstance(feature, dict):
            continue
        fastener = feature.get("fastener")
        diameter = feature.get("diameter") or feature.get("hole_diameter")
        if not fastener or diameter is None:
            continue
        recommended = FASTENER_CLEARANCE_DIAMETERS.get(str(fastener).upper())
        if recommended is None:
            _warning(result, "unknown_fastener", f"No clearance rule for fastener {fastener}", feature=name)
            continue
        passed = diameter >= recommended
        _check(result, "fastener_clearance", passed, feature=name, fastener=fastener, expected_min=recommended, actual=diameter)
        if not passed:
            _warning(
                result,
                "fastener_clearance_tight",
                f"{name} diameter {diameter}mm is tighter than {fastener} clearance {recommended}mm",
                feature=name,
            )


def _check_assembly_metadata(params: dict[str, Any], result: dict[str, Any]) -> None:
    role = params.get("assembly_role")
    mating_faces = params.get("mating_faces", [])
    if role and not mating_faces:
        _warning(
            result,
            "assembly_role_without_mating_faces",
            "Assembly-facing part should declare mating_faces for downstream checks",
        )


def _check(result: dict[str, Any], code: str, passed: bool, **extra: Any) -> None:
    result["checks"].append({"check": code, "pass": passed, **extra})


def _warning(result: dict[str, Any], code: str, message: str, **extra: Any) -> None:
    result["warnings"].append({"code": code, "message": message, **extra})
    result["checks"].append({"check": code, "pass": True, "severity": "warning", **extra})


def _error(result: dict[str, Any], code: str, message: str, **extra: Any) -> None:
    result["errors"].append({"code": code, "message": message, **extra})
    result["checks"].append({"check": code, "pass": False, "severity": "error", **extra})
