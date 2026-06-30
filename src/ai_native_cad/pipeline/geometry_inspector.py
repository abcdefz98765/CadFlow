"""Geometry and artifact inspection for STEP-first pipeline validation."""

from __future__ import annotations

from math import isclose
from pathlib import Path
from typing import Any

import cadquery as cq

from ai_native_cad.cad_ir.schema import CADIR


def inspect_geometry(
    model: cq.Workplane | None,
    output_dir: str | Path,
    ir: CADIR | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return structured facts about generated CAD artifacts and geometry."""
    cad_ir = CADIR.from_dict(ir) if isinstance(ir, dict) else ir
    output_path = Path(output_dir)
    inspection: dict[str, Any] = {
        "artifact_roles": {
            "primary": "model.step",
            "derived": ["model.stl"],
        },
        "solid_count": None,
        "bounding_box": {},
        "volume": 0.0,
        "step_file": _file_fact(output_path / "model.step", role="primary_cad_artifact"),
        "stl_file": _file_fact(output_path / "model.stl", role="derived_mesh_output"),
        "features": _feature_scaffold(cad_ir),
        "errors": [],
    }

    if model is None:
        inspection["errors"].append({"code": "model_missing", "message": "No model object was available for inspection"})
        return inspection

    try:
        shape = model.val()
        bbox = shape.BoundingBox()
        volume = shape.Volume()
        solids = shape.Solids()
        faces = shape.Faces()
    except Exception as exc:
        inspection["errors"].append({"code": "geometry_measurement_failed", "message": str(exc)})
        return inspection

    inspection["solid_count"] = len(solids)
    inspection["bounding_box"] = {
        "x": round(bbox.xlen, 3),
        "y": round(bbox.ylen, 3),
        "z": round(bbox.zlen, 3),
    }
    inspection["volume"] = round(volume, 3)
    inspection["features"]["holes"] = _inspect_holes(cad_ir, faces)
    return inspection


def _file_fact(path: Path, role: str) -> dict[str, Any]:
    present = path.exists() and path.stat().st_size > 0
    return {
        "path": str(path),
        "present": present,
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "role": role,
    }


def _feature_scaffold(cad_ir: CADIR | None) -> dict[str, Any]:
    features = cad_ir.features if cad_ir else {}
    return {
        "holes": {
            "status": "scaffold",
            "expected": _expected_feature(features, "holes", aliases=("mounting_holes", "base_holes")),
            "measured": None,
            "note": "Hole count/diameter measurement is available for simple mounting_plate through-hole topology.",
        },
        "chamfers": {
            "status": "scaffold",
            "expected": _expected_feature(features, "chamfer"),
            "measured": None,
            "note": "Chamfer measurement is not inferred yet.",
        },
        "fillets": {
            "status": "scaffold",
            "expected": _expected_feature(features, "fillet"),
            "measured": None,
            "note": "Fillet measurement is not inferred yet.",
        },
    }


def _expected_feature(features: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> Any:
    for name in (key, *aliases):
        if name in features:
            return features[name]
    return None


def _inspect_holes(cad_ir: CADIR | None, faces: list[Any]) -> dict[str, Any]:
    features = cad_ir.features if cad_ir else {}
    expected_feature = _expected_feature(features, "holes", aliases=("mounting_holes", "base_holes"))
    if not expected_feature:
        return {
            "status": "scaffold",
            "expected": None,
            "measured": None,
            "note": "No hole feature was requested in IR.",
        }

    if cad_ir is None or cad_ir.part_type != "mounting_plate":
        return {
            "status": "unverified",
            "expected": expected_feature,
            "measured": None,
            "reason": "Hole topology inspection is currently limited to mounting_plate geometry.",
        }

    expectation = _hole_expectation(expected_feature)
    if expectation.get("status") != "known":
        return {
            "status": "unverified",
            "expected": expectation.get("expected", expected_feature),
            "measured": None,
            "reason": expectation.get("reason", "Hole expectation could not be inferred from IR."),
        }

    measured = _measure_mounting_plate_through_holes(faces, cad_ir.dimensions.get("thickness", 0))
    expected = expectation["expected"]
    if measured["reliable"] is False:
        return {
            "status": "unverified",
            "expected": expected,
            "measured": measured,
            "reason": measured["reason"],
        }

    count_matches = measured["count"] == expected["count"]
    diameter_matches = (
        measured["diameter"] is not None
        and isclose(measured["diameter"], expected["diameter"], abs_tol=0.2)
    )
    status = "verified" if count_matches and diameter_matches else "failed"
    result: dict[str, Any] = {
        "status": status,
        "expected": expected,
        "measured": measured,
    }
    if status == "failed":
        result["reason"] = "Measured through-hole topology does not match IR expectation."
    return result


def _hole_expectation(feature: Any) -> dict[str, Any]:
    items = feature if isinstance(feature, list) else [feature]
    items = [item for item in items if isinstance(item, dict)]
    if not items:
        return {"status": "unknown", "expected": feature, "reason": "Hole feature is not a dictionary."}

    counts: list[int] = []
    diameters: list[float] = []
    for item in items:
        diameter = float(item.get("diameter", 0) or 0)
        if diameter <= 0:
            return {"status": "unknown", "expected": item, "reason": "Hole feature is missing a usable diameter."}
        count = _expected_hole_count(item)
        if count is None:
            return {"status": "unknown", "expected": item, "reason": "Hole count could not be inferred from positions or pattern."}
        counts.append(count)
        diameters.append(diameter)

    unique_diameters = {round(value, 3) for value in diameters}
    if len(unique_diameters) != 1:
        return {"status": "unknown", "expected": feature, "reason": "Multiple hole diameters are not inspected yet."}

    return {
        "status": "known",
        "expected": {
            "count": sum(counts),
            "diameter": round(diameters[0], 3),
        },
    }


def _expected_hole_count(item: dict[str, Any]) -> int | None:
    positions = item.get("positions")
    if positions == "corner_4":
        return 4
    if item.get("pattern") == "corner" and int(item.get("count", 0) or 0) == 4:
        return 4
    if isinstance(positions, list):
        return len(positions)
    return None


def _measure_mounting_plate_through_holes(faces: list[Any], thickness: float) -> dict[str, Any]:
    if thickness <= 0:
        return {"reliable": False, "reason": "Plate thickness is missing or non-positive."}

    cylinders: list[dict[str, Any]] = []
    for face in faces:
        try:
            if face.geomType() != "CYLINDER":
                continue
            bbox = face.BoundingBox()
        except Exception:
            continue

        xy_diameter = (bbox.xlen + bbox.ylen) / 2
        if xy_diameter <= 0:
            continue
        if not isclose(bbox.xlen, bbox.ylen, abs_tol=0.1):
            continue
        if not isclose(bbox.zlen, thickness, abs_tol=0.2):
            continue
        cylinders.append({
            "diameter": round(xy_diameter, 3),
            "center": [round(value, 3) for value in face.Center().toTuple()],
        })

    diameter = None
    diameters = [item["diameter"] for item in cylinders]
    if diameters:
        diameter = round(sum(diameters) / len(diameters), 3)

    return {
        "reliable": True,
        "count": len(cylinders),
        "diameter": diameter,
        "diameters": diameters,
        "centers": [item["center"] for item in cylinders],
    }
