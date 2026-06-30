"""Validation for the CAD IR before backend code is generated."""

from __future__ import annotations

from typing import Any

from ai_native_cad.cad_ir.schema import CADIR

SUPPORTED_PART_TYPES = {"mounting_plate", "spacer", "simple_bracket", "wall_bracket"}
SUPPORTED_OUTPUTS = {"step", "stl"}

REQUIRED_DIMENSIONS = {
    "mounting_plate": {"length", "width", "thickness"},
    "spacer": {"outer_diameter", "inner_diameter", "thickness"},
    "simple_bracket": {"base_length", "base_width", "height", "thickness"},
    "wall_bracket": {"base_width", "base_depth", "wall_height", "material_thickness"},
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

    result["valid"] = not result["errors"]
    return result


def _check(result: dict[str, Any], name: str, passed: bool, **extra: Any) -> None:
    result["checks"].append({"check": name, "pass": passed, **extra})
