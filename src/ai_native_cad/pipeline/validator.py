"""Validation for completed IR-first pipeline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cadquery as cq

from ai_native_cad.cad_ir.schema import CADIR


BOUNDING_BOX_TOLERANCE_MM = 0.2


def validate_pipeline_outputs(
    model: cq.Workplane | None,
    output_dir: str | Path,
    ir: CADIR | dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    """Validate generated geometry and required output artifacts."""
    cad_ir = CADIR.from_dict(ir) if isinstance(ir, dict) else ir
    output_path = Path(output_dir)
    result: dict[str, Any] = {
        "valid": True,
        "execution_success": execution.get("status") == "success",
        "step_generated": False,
        "stl_generated": False,
        "report_generated": False,
        "bounding_box": {},
        "volume": 0.0,
        "checks": [],
        "warnings": [],
        "errors": [],
    }

    _check(result, "model_execution_success", result["execution_success"])
    if not result["execution_success"]:
        result["errors"].append({
            "code": "execution_failed",
            "message": execution.get("stderr") or execution.get("stdout") or "Generated model execution failed",
        })

    for filename, key in (("model.step", "step_generated"), ("model.stl", "stl_generated")):
        path = output_path / filename
        exists = path.exists() and path.stat().st_size > 0
        result[key] = exists
        _check(result, f"{filename}_exists", exists, file=str(path))
        if not exists:
            result["errors"].append({
                "code": "required_output_missing",
                "message": f"Required output file was not generated: {filename}",
                "file": str(path),
            })

    report_path = output_path / "report.json"
    result["report_generated"] = report_path.exists() and report_path.stat().st_size > 0
    _check(result, "report_json_exists", result["report_generated"], file=str(report_path))

    if model is None:
        result["valid"] = False
        result["errors"].append({"code": "model_missing", "message": "No model object was available for validation"})
        return _finalize(result)

    try:
        shape = model.val()
        bbox = shape.BoundingBox()
        volume = shape.Volume()
    except Exception as exc:
        result["errors"].append({"code": "geometry_measurement_failed", "message": str(exc)})
        result["valid"] = False
        return _finalize(result)

    result["bounding_box"] = {
        "x": round(bbox.xlen, 3),
        "y": round(bbox.ylen, 3),
        "z": round(bbox.zlen, 3),
    }
    result["volume"] = round(volume, 3)
    _check(result, "volume_positive", volume > 0)
    if volume <= 0:
        result["errors"].append({"code": "non_positive_volume", "message": "Generated model volume must be greater than zero"})

    for dimension, axis, expected in _expected_bbox_dimensions(cad_ir):
        actual = result["bounding_box"][axis]
        passed = abs(actual - expected) <= BOUNDING_BOX_TOLERANCE_MM
        _check(result, "bounding_box_dimension", passed, dimension=dimension, axis=axis, expected=expected, actual=actual)
        if not passed:
            result["errors"].append({
                "code": "bounding_box_mismatch",
                "message": f"Bounding box {axis} dimension does not match IR dimension {dimension}",
                "dimension": dimension,
                "axis": axis,
                "expected": expected,
                "actual": actual,
            })

    return _finalize(result)


def _expected_bbox_dimensions(cad_ir: CADIR) -> list[tuple[str, str, float]]:
    dims = cad_ir.dimensions
    if cad_ir.part_type == "mounting_plate":
        return [("length", "x", dims["length"]), ("width", "y", dims["width"]), ("thickness", "z", dims["thickness"])]
    if cad_ir.part_type == "spacer":
        return [
            ("outer_diameter", "x", dims["outer_diameter"]),
            ("outer_diameter", "y", dims["outer_diameter"]),
            ("thickness", "z", dims["thickness"]),
        ]
    if cad_ir.part_type == "simple_bracket":
        return [("base_length", "x", dims["base_length"]), ("base_width", "y", dims["base_width"]), ("height", "z", dims["height"])]
    if cad_ir.part_type == "wall_bracket":
        return [
            ("base_depth", "x", dims["base_depth"]),
            ("base_width", "y", dims["base_width"]),
            ("wall_height", "z", dims["wall_height"]),
        ]
    if cad_ir.part_type == "circular_button":
        return [
            ("body_diameter", "x", dims["body_diameter"]),
            ("body_diameter", "y", dims["body_diameter"]),
        ]
    if cad_ir.part_type == "enclosure_base":
        return [
            ("outer_length", "x", dims["outer_length"]),
            ("outer_width", "y", dims["outer_width"]),
            ("outer_height", "z", dims["outer_height"]),
        ]
    if cad_ir.part_type == "enclosure_lid":
        return [("length", "x", dims["length"]), ("width", "y", dims["width"]), ("thickness", "z", dims["thickness"])]
    return []


def _check(result: dict[str, Any], name: str, passed: bool, **extra: Any) -> None:
    result["checks"].append({"check": name, "pass": passed, **extra})


def _finalize(result: dict[str, Any]) -> dict[str, Any]:
    result["valid"] = not result["errors"] and all(check.get("pass") for check in result["checks"])
    return result
