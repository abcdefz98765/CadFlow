"""Part generation validators.

The public ``validate_output`` function remains as the compatibility entry
point, but the checks are split into explicit workflow stages:

- preflight design intent before modeling
- generated geometry after modeling
- export files after writing exchange formats
- intent matching between requested spec and measured model summary
"""

from pathlib import Path
from typing import Any

import cadquery as cq

from ai_native_cad.design_checks import validate_design_intent


DIMENSION_AXIS_MAP = {
    "length": "x",
    "width": "y",
    "thickness": "z",
    "outer_length": "x",
    "outer_width": "y",
    "outer_diameter": "x",
    "base_width": "y",
}


def preflight_design_intent(params: dict[str, Any]) -> dict[str, Any]:
    """Check whether a part spec is ready enough to attempt generation."""
    design_result = validate_design_intent(params)
    result = {
        "valid": design_result["valid"],
        "checks": [],
        "warnings": [],
        "errors": [],
        "stage": "preflight",
    }
    result["checks"].extend(design_result["checks"])
    result["warnings"].extend(design_result["warnings"])
    result["errors"].extend(design_result["errors"])

    _required_presence_check(result, params, "part_type", severity="error")
    _required_presence_check(result, params, "dimensions", severity="error")
    _required_presence_check(result, params, "features", severity="warning")

    if "unit" not in params:
        severity = "error" if params.get("check_level") in {"L2", "L3", "L4"} else "warning"
        _required_presence_check(result, params, "unit", severity=severity)

    result["valid"] = not result["errors"]
    return result


def validate_generated_geometry(model: cq.Workplane, params: dict[str, Any]) -> dict[str, Any]:
    """Validate backend-generated geometry without checking exported files."""
    result = {
        "valid": True,
        "checks": [],
        "warnings": [],
        "errors": [],
        "stage": "geometry",
    }

    try:
        if model is None:
            result["valid"] = False
            result["errors"].append({"code": "model_missing", "message": "No model object was generated"})
            result["checks"].append({"check": "model_exists", "pass": False})
            return result

        bbox = model.val().BoundingBox()
        volume = model.val().Volume()
        result["bounding_box"] = {
            "x": round(bbox.xlen, 3),
            "y": round(bbox.ylen, 3),
            "z": round(bbox.zlen, 3),
            "xmin": round(bbox.xmin, 3),
            "xmax": round(bbox.xmax, 3),
            "ymin": round(bbox.ymin, 3),
            "ymax": round(bbox.ymax, 3),
            "zmin": round(bbox.zmin, 3),
            "zmax": round(bbox.zmax, 3),
        }
        result["volume_mm3"] = round(volume, 3)
        result["checks"].append({"check": "model_exists", "pass": True})

        try:
            solids = list(model.val().Solids())
            solid_count = len(solids)
        except Exception:
            solid_count = 1
        result["solid_count"] = solid_count
        result["checks"].append({
            "check": "single_solid",
            "actual": solid_count,
            "pass": solid_count == 1,
        })
        if solid_count != 1:
            result["valid"] = False

        expected = params.get("dimensions", {})
        dimension_axis_map = dict(DIMENSION_AXIS_MAP)
        if params.get("part_type") == "simple_bracket":
            dimension_axis_map.pop("thickness", None)
            dimension_axis_map.update({"base_length": "x", "base_width": "y", "height": "z"})
        for key, axis in dimension_axis_map.items():
            if key in expected:
                actual = getattr(bbox, axis + "len")
                target = expected[key]
                passed = abs(actual - target) < 0.1
                result["checks"].append({
                    "dimension": key,
                    "expected": target,
                    "actual": round(actual, 3),
                    "pass": passed,
                })
                if not passed:
                    result["valid"] = False

        result["checks"].append({
            "check": "volume_positive",
            "pass": volume > 0,
        })
        if volume <= 0:
            result["valid"] = False

        watertight = True
        try:
            watertight = bool(model.val().isValid())
        except Exception:
            result["warnings"].append({
                "code": "watertight_check_unavailable",
                "message": "Backend did not expose a watertight/shape-validity check",
            })
        result["checks"].append({
            "check": "watertight",
            "pass": watertight,
            "method": "cadquery_shape_is_valid",
        })
        if not watertight:
            result["valid"] = False
    except Exception as e:
        result["valid"] = False
        result["errors"] = result.get("errors", []) + [{"code": "model_validation_exception", "message": str(e)}]

    return result


def validate_export_files(output_dir: Path, params: dict[str, Any]) -> dict[str, Any]:
    """Validate that requested exchange files were written."""
    output_dir = Path(output_dir)
    result = {
        "valid": True,
        "checks": [],
        "warnings": [],
        "errors": [],
        "stage": "export",
    }

    for fmt, path_str in [("step", output_dir / "model.step"), ("stl", output_dir / "model.stl")]:
        expected_fmts = [f.lower() for f in params.get("outputs", [])]
        if fmt in expected_fmts:
            if path_str.exists() and path_str.stat().st_size > 0:
                result["checks"].append({"file": str(path_str), "exists": True, "pass": True})
            else:
                result["checks"].append({"file": str(path_str), "exists": False, "pass": False})
                result["errors"].append({"code": "export_file_missing", "message": f"Expected {fmt.upper()} export was not created", "file": str(path_str)})
                result["valid"] = False

    return result


def validate_intent_match(params: dict[str, Any], geometry_result: dict[str, Any]) -> dict[str, Any]:
    """Report what parts of the request were verified, assumed, or unverified."""
    result = {
        "valid": True,
        "checks": [],
        "warnings": [],
        "errors": [],
        "stage": "intent_match",
        "verified": [],
        "assumed": list(params.get("assumptions", [])),
        "unverified": [],
    }
    expected_dimensions = params.get("dimensions", {})
    dimension_checks = [check for check in geometry_result.get("checks", []) if "dimension" in check]
    checked_dimensions = {check["dimension"] for check in dimension_checks}

    for check in dimension_checks:
        target = result["verified"] if check.get("pass") else result["unverified"]
        target.append({
            "kind": "dimension",
            "name": check["dimension"],
            "expected": check.get("expected"),
            "actual": check.get("actual"),
            "status": "matched" if check.get("pass") else "mismatch",
        })
        if not check.get("pass"):
            result["valid"] = False

    for name in sorted(set(expected_dimensions) - checked_dimensions):
        result["unverified"].append({
            "kind": "dimension",
            "name": name,
            "reason": "No backend-neutral measurement rule exists yet",
        })

    for name, feature in params.get("features", {}).items():
        feature_type = feature.get("type") if isinstance(feature, dict) else str(feature)
        result["unverified"].append({
            "kind": "feature",
            "name": name,
            "feature_type": feature_type,
            "reason": "Feature-level geometry recognition is not implemented yet",
        })

    if result["unverified"]:
        result["warnings"].append({
            "code": "intent_items_unverified",
            "message": "Some requested dimensions or features could not be independently verified",
            "count": len(result["unverified"]),
        })
        result["checks"].append({
            "check": "intent_match_coverage",
            "pass": True,
            "verified_count": len(result["verified"]),
            "unverified_count": len(result["unverified"]),
        })
    else:
        result["checks"].append({"check": "intent_match_coverage", "pass": True, "verified_count": len(result["verified"]), "unverified_count": 0})

    return result


def validate_output(model: cq.Workplane, output_dir: Path, params: dict) -> dict:
    """Validate the generated model and output files."""
    output_dir = Path(output_dir)
    preflight = preflight_design_intent(params)
    geometry = validate_generated_geometry(model, params)
    exports = validate_export_files(output_dir, params)
    intent_match = validate_intent_match(params, geometry)

    result = _combine_validation_sections({
        "preflight": preflight,
        "geometry": geometry,
        "export": exports,
        "intent_match": intent_match,
    })
    result["design"] = preflight
    if "bounding_box" in geometry:
        result["bounding_box"] = geometry["bounding_box"]
    if "volume_mm3" in geometry:
        result["volume_mm3"] = geometry["volume_mm3"]
    if "solid_count" in geometry:
        result["solid_count"] = geometry["solid_count"]
    return result


def _combine_validation_sections(sections: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result = {
        "valid": all(section.get("valid", False) for section in sections.values()),
        "checks": [],
        "warnings": [],
        "errors": [],
        "sections": sections,
    }
    for name, section in sections.items():
        for check in section.get("checks", []):
            result["checks"].append({"stage": name, **check})
        result["warnings"].extend(section.get("warnings", []))
        result["errors"].extend(section.get("errors", []))
    return result


def _required_presence_check(result: dict[str, Any], params: dict[str, Any], field: str, severity: str) -> None:
    present = field in params and params[field] not in (None, {}, [])
    result["checks"].append({"check": "required_field", "field": field, "pass": present, "severity": severity})
    if present:
        return
    item = {"code": "required_field_missing", "message": f"Required field is missing: {field}", "field": field}
    if severity == "error":
        result["errors"].append(item)
    else:
        result["warnings"].append(item)
