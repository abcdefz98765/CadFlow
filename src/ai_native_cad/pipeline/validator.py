"""Validation for completed IR-first pipeline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cadquery as cq

from ai_native_cad.cad_ir.schema import CADIR
from ai_native_cad.pipeline.geometry_inspector import inspect_geometry


BOUNDING_BOX_TOLERANCE_MM = 0.2
EXTREME_DIMENSION_DEVIATION_RATIO = 0.2


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
        "inspection": {},
        "measured_validation_targets": [],
        "checks": [],
        "warnings": [],
        "errors": [],
    }
    inspection = inspect_geometry(model, output_path, cad_ir)
    result["inspection"] = inspection

    _check(result, "model_execution_success", result["execution_success"])
    if not result["execution_success"]:
        result["errors"].append({
            "code": "execution_failed",
            "message": execution.get("stderr") or execution.get("stdout") or "Generated model execution failed",
        })

    artifact_checks = (
        ("model.step", "step_generated", inspection["step_file"]),
        ("model.stl", "stl_generated", inspection["stl_file"]),
    )
    for filename, key, fact in artifact_checks:
        result[key] = fact["present"]
        _check(result, f"{filename}_exists", fact["present"], file=fact["path"], size_bytes=fact["size_bytes"], role=fact["role"])
        if not fact["present"]:
            result["errors"].append({
                "code": "required_output_missing",
                "message": f"Required output file was not generated: {filename}",
                "file": fact["path"],
            })

    report_path = output_path / "report.json"
    result["report_generated"] = report_path.exists() and report_path.stat().st_size > 0
    _check(result, "report_json_exists", result["report_generated"], file=str(report_path))

    if model is None:
        result["valid"] = False
        result["errors"].append({"code": "model_missing", "message": "No model object was available for validation"})
        return _finalize(result)

    if inspection["errors"]:
        result["errors"].extend(inspection["errors"])
        result["valid"] = False
        return _finalize(result)

    result["bounding_box"] = inspection["bounding_box"]
    result["volume"] = inspection["volume"]
    volume = result["volume"]
    _check(result, "volume_positive", volume > 0)
    if volume <= 0:
        result["errors"].append({"code": "non_positive_volume", "message": "Generated model volume must be greater than zero"})

    solid_count = inspection["solid_count"]
    _check(result, "invalid_solids", solid_count == 1, solid_count=solid_count)
    if solid_count != 1:
        result["errors"].append({
            "code": "invalid_solid",
            "message": "Generated geometry must resolve to exactly one solid",
            "solid_count": solid_count,
        })

    for dimension, axis, expected in _expected_bbox_dimensions(cad_ir):
        actual = result["bounding_box"][axis]
        passed = abs(actual - expected) <= BOUNDING_BOX_TOLERANCE_MM
        _check(result, "bounding_box_dimension", passed, dimension=dimension, axis=axis, expected=expected, actual=actual)
        result["measured_validation_targets"].append({
            "target": "bounding_box_dimension",
            "dimension": dimension,
            "axis": axis,
            "expected": expected,
            "actual": actual,
            "pass": passed,
        })
        if not passed:
            deviation = abs(actual - expected)
            ratio = deviation / expected if expected else 0
            result["errors"].append({
                "code": "bounding_box_mismatch",
                "message": f"Bounding box {axis} dimension does not match IR dimension {dimension}",
                "dimension": dimension,
                "axis": axis,
                "expected": expected,
                "actual": actual,
            })
            if ratio > EXTREME_DIMENSION_DEVIATION_RATIO:
                result["errors"].append({
                    "code": "extreme_dimension_deviation",
                    "message": f"Bounding box {axis} deviates from IR dimension {dimension} by more than 20%",
                    "dimension": dimension,
                    "axis": axis,
                    "expected": expected,
                    "actual": actual,
                })

    _validate_features(result, cad_ir, inspection)

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


def _validate_features(result: dict[str, Any], cad_ir: CADIR, inspection: dict[str, Any]) -> None:
    features = cad_ir.features
    holes = features.get("holes") or features.get("mounting_holes") or features.get("base_holes")
    if holes:
        _validate_hole_inspection(result, inspection)
        hole_items = holes if isinstance(holes, list) else [holes]
        for item in hole_items:
            diameter = float(item.get("diameter", 0) or 0)
            if diameter <= 0:
                _check(result, "feature_clearance_feasible", False, feature="holes")
                result["errors"].append({"code": "missing_feature", "message": "Hole feature is missing a usable diameter", "feature": "holes"})
                continue
            span = min(_hole_spans(cad_ir) or [0])
            offset = float(item.get("offset_from_edge", max(diameter, span * 0.2)) or 0)
            has_clearance = span <= 0 or (diameter < span and offset >= diameter * 0.5 and offset <= span / 2)
            _check(result, "feature_clearance_feasible", has_clearance, feature="holes", diameter=diameter, offset_from_edge=offset)
            if not has_clearance:
                result["errors"].append({
                    "code": "missing_feature",
                    "message": "Hole feature cannot be reliably realized within IR dimensions",
                    "feature": "holes",
                })

    for key, size_key in (("chamfer", "size"), ("fillet", "radius")):
        value = features.get(key)
        if not value:
            continue
        if key == "chamfer":
            _validate_chamfer_inspection(result, inspection)
        size = float(value.get(size_key, 0) if isinstance(value, dict) else value)
        smallest_dim = min((dim for dim in cad_ir.dimensions.values() if dim > 0), default=0)
        valid_relief = smallest_dim <= 0 or size <= smallest_dim / 2
        _check(result, "boolean_artifact_absent", valid_relief, feature=key, size=size)
        if not valid_relief:
            result["errors"].append({
                "code": "boolean_failure_artifact",
                "message": f"{key} size is too large for the available geometry",
                "feature": key,
            })

    if cad_ir.part_type in {"mounting_plate", "enclosure_lid", "spacer", "circular_button"}:
        bbox = result.get("bounding_box", {})
        symmetric = bool(bbox) and abs(bbox.get("x", 0) - bbox.get("y", 0)) <= max(bbox.get("x", 0), bbox.get("y", 0), 1) * 0.01
        should_be_symmetric = cad_ir.part_type in {"spacer", "circular_button"}
        _check(result, "symmetry_correctness", (not should_be_symmetric) or symmetric)


def _validate_hole_inspection(result: dict[str, Any], inspection: dict[str, Any]) -> None:
    hole_inspection = inspection.get("features", {}).get("holes", {})
    status = hole_inspection.get("status")

    if status == "verified":
        expected = hole_inspection.get("expected", {})
        measured = hole_inspection.get("measured", {})
        _check(result, "hole_topology_inspection", True, feature="holes", status=status)
        result["measured_validation_targets"].append({
            "target": "hole_count",
            "expected": expected.get("count"),
            "actual": measured.get("count"),
            "pass": measured.get("count") == expected.get("count"),
        })
        diameter_pass = abs(float(measured.get("diameter", 0) or 0) - float(expected.get("diameter", 0) or 0)) <= 0.2
        result["measured_validation_targets"].append({
            "target": "hole_diameter",
            "expected": expected.get("diameter"),
            "actual": measured.get("diameter"),
            "pass": diameter_pass,
        })
        _add_hole_spacing_targets(result, hole_inspection)
        return

    if status == "failed":
        _check(result, "hole_topology_inspection", False, feature="holes", status=status)
        _add_hole_spacing_targets(result, hole_inspection)
        result["errors"].append({
            "code": "missing_feature",
            "message": "Expected mounting plate through holes were not realized in generated geometry",
            "feature": "holes",
            "inspection": hole_inspection,
        })
        return

    result["warnings"].append({
        "code": "feature_unverified",
        "message": "Hole feature topology could not be reliably verified",
        "feature": "holes",
        "inspection": hole_inspection,
    })


def _add_hole_spacing_targets(result: dict[str, Any], hole_inspection: dict[str, Any]) -> None:
    spacing = hole_inspection.get("spacing") or {}
    status = spacing.get("status")
    if status == "verified":
        expected = spacing.get("expected", {})
        measured = spacing.get("measured", {})
        for axis in ("x", "y"):
            result["measured_validation_targets"].append({
                "target": f"hole_spacing_{axis}",
                "expected": expected.get(axis),
                "actual": measured.get(axis),
                "pass": True,
            })
        return

    if status == "failed":
        expected = spacing.get("expected", {})
        measured = spacing.get("measured", {})
        checks = spacing.get("checks", {})
        for axis in ("x", "y"):
            passed = bool(checks.get(axis))
            result["measured_validation_targets"].append({
                "target": f"hole_spacing_{axis}",
                "expected": expected.get(axis),
                "actual": measured.get(axis),
                "pass": passed,
            })
        result["errors"].append({
            "code": "hole_spacing_mismatch",
            "message": "Measured mounting plate hole spacing does not match IR expectation",
            "feature": "holes",
            "inspection": spacing,
        })
        return

    if status == "unverified":
        result["warnings"].append({
            "code": "feature_unverified",
            "message": "Hole spacing could not be reliably verified",
            "feature": "holes",
            "inspection": spacing,
        })


def _validate_chamfer_inspection(result: dict[str, Any], inspection: dict[str, Any]) -> None:
    chamfer_inspection = inspection.get("features", {}).get("chamfers", {})
    status = chamfer_inspection.get("status")

    if status == "verified":
        expected = chamfer_inspection.get("expected", {})
        measured = chamfer_inspection.get("measured", {})
        _check(result, "chamfer_topology_inspection", True, feature="chamfer", status=status)
        result["measured_validation_targets"].append({
            "target": "chamfer_count",
            "expected": expected.get("count"),
            "actual": measured.get("count"),
            "pass": measured.get("count") == expected.get("count"),
        })
        size_pass = abs(float(measured.get("size", 0) or 0) - float(expected.get("size", 0) or 0)) <= 0.2
        result["measured_validation_targets"].append({
            "target": "chamfer_size",
            "expected": expected.get("size"),
            "actual": measured.get("size"),
            "pass": size_pass,
        })
        return

    if status == "failed":
        _check(result, "chamfer_topology_inspection", False, feature="chamfer", status=status)
        expected = chamfer_inspection.get("expected", {})
        measured = chamfer_inspection.get("measured", {})
        result["measured_validation_targets"].append({
            "target": "chamfer_count",
            "expected": expected.get("count"),
            "actual": measured.get("count"),
            "pass": measured.get("count") == expected.get("count"),
        })
        result["measured_validation_targets"].append({
            "target": "chamfer_size",
            "expected": expected.get("size"),
            "actual": measured.get("size"),
            "pass": False,
        })
        result["errors"].append({
            "code": "missing_feature",
            "message": "Expected vertical edge chamfer was not realized in generated geometry",
            "feature": "chamfer",
            "inspection": chamfer_inspection,
        })
        return

    result["warnings"].append({
        "code": "feature_unverified",
        "message": "Chamfer feature topology could not be reliably verified",
        "feature": "chamfer",
        "inspection": chamfer_inspection,
    })


def _hole_spans(cad_ir: CADIR) -> list[float]:
    dims = cad_ir.dimensions
    if cad_ir.part_type in {"mounting_plate", "enclosure_lid"}:
        return [dims.get("length", 0), dims.get("width", 0)]
    if cad_ir.part_type == "simple_bracket":
        return [dims.get("base_length", 0), dims.get("base_width", 0)]
    if cad_ir.part_type == "wall_bracket":
        return [dims.get("base_depth", 0), dims.get("base_width", 0), dims.get("wall_height", 0)]
    return [value for value in dims.values() if value > 0]


def _finalize(result: dict[str, Any]) -> dict[str, Any]:
    result["valid"] = not result["errors"] and all(check.get("pass") for check in result["checks"])
    return result
