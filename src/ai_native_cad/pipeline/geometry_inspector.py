"""Geometry and artifact inspection for STEP-first pipeline validation."""

from __future__ import annotations

from math import isclose
from pathlib import Path
from typing import Any

import cadquery as cq

from ai_native_cad.cad_ir.schema import CADIR

HOLE_TOLERANCE_MM = 0.2
CHAMFER_TOLERANCE_MM = 0.2


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
    inspection["features"]["chamfers"] = _inspect_chamfers(cad_ir, faces)
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
            "note": "Hole count, diameter, and spacing measurement is available for simple mounting_plate through-hole topology.",
        },
        "chamfers": {
            "status": "scaffold",
            "expected": _expected_feature(features, "chamfer"),
            "measured": None,
            "note": "Chamfer measurement is available for simple vertical edge chamfers on plate-like parts.",
        },
        "fillets": _fillet_scaffold(features),
    }


def _expected_feature(features: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> Any:
    for name in (key, *aliases):
        if name in features:
            return features[name]
    return None


def _fillet_scaffold(features: dict[str, Any]) -> dict[str, Any]:
    expected = _expected_feature(features, "fillet")
    if not expected:
        return {
            "status": "scaffold",
            "expected": None,
            "measured": None,
            "note": "No fillet feature was requested in IR.",
        }
    return {
        "status": "unverified",
        "expected": expected,
        "measured": None,
        "reason": "Fillet topology measurement is not implemented yet.",
    }


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

    spacing = _inspect_mounting_plate_hole_spacing(cad_ir, measured)
    if spacing.get("expected"):
        expected["centers"] = spacing["expected"].get("centers")
        expected["spacing_x"] = spacing["expected"].get("x")
        expected["spacing_y"] = spacing["expected"].get("y")
    count_matches = measured["count"] == expected["count"]
    diameter_matches = (
        measured["diameter"] is not None
        and isclose(measured["diameter"], expected["diameter"], abs_tol=HOLE_TOLERANCE_MM)
    )
    spacing_status = spacing.get("status")
    status = "verified" if count_matches and diameter_matches and spacing_status != "failed" else "failed"
    result: dict[str, Any] = {
        "status": status,
        "expected": expected,
        "measured": measured,
        "spacing": spacing,
    }
    if status == "failed":
        result["reason"] = "Measured through-hole topology does not match IR expectation."
    return result


def _inspect_chamfers(cad_ir: CADIR | None, faces: list[Any]) -> dict[str, Any]:
    features = cad_ir.features if cad_ir else {}
    expected_feature = _expected_feature(features, "chamfer")
    if not expected_feature:
        return {
            "status": "scaffold",
            "expected": None,
            "measured": None,
            "note": "No chamfer feature was requested in IR.",
        }

    expectation = _chamfer_expectation(expected_feature)
    if expectation.get("status") != "known":
        return {
            "status": "unverified",
            "expected": expectation.get("expected", expected_feature),
            "measured": None,
            "reason": expectation.get("reason", "Chamfer expectation could not be inferred from IR."),
        }

    if cad_ir is None or cad_ir.part_type not in {"mounting_plate", "enclosure_lid"}:
        return {
            "status": "unverified",
            "expected": expectation["expected"],
            "measured": None,
            "reason": "Chamfer topology inspection is currently limited to plate-like vertical edge chamfers.",
        }

    thickness = cad_ir.dimensions.get("thickness", 0)
    measured = _measure_vertical_edge_chamfers(faces, thickness, expectation["expected"]["size"])
    count_matches = measured["count"] == expectation["expected"]["count"]
    size_matches = (
        measured["size"] is not None
        and isclose(measured["size"], expectation["expected"]["size"], abs_tol=CHAMFER_TOLERANCE_MM)
    )
    status = "verified" if count_matches and size_matches else "failed"
    result: dict[str, Any] = {
        "status": status,
        "expected": expectation["expected"],
        "measured": measured,
    }
    if status == "failed":
        result["reason"] = "Measured chamfer topology does not match IR expectation."
    return result


def _hole_expectation(feature: Any) -> dict[str, Any]:
    items = feature if isinstance(feature, list) else [feature]
    items = [item for item in items if isinstance(item, dict)]
    if not items:
        return {"status": "unknown", "expected": feature, "reason": "Hole feature is not a dictionary."}

    counts: list[int] = []
    diameters: list[float] = []
    expected_centers: list[list[float]] | None = None
    spacing: dict[str, float] | None = None
    for item in items:
        diameter = float(item.get("diameter", 0) or 0)
        if diameter <= 0:
            return {"status": "unknown", "expected": item, "reason": "Hole feature is missing a usable diameter."}
        count = _expected_hole_count(item)
        if count is None:
            return {"status": "unknown", "expected": item, "reason": "Hole count could not be inferred from positions or pattern."}
        counts.append(count)
        diameters.append(diameter)
        centers = _expected_hole_centers(item)
        if centers is not None:
            expected_centers = centers
            spacing = _spacing_from_centers(centers)

    unique_diameters = {round(value, 3) for value in diameters}
    if len(unique_diameters) != 1:
        return {"status": "unknown", "expected": feature, "reason": "Multiple hole diameters are not inspected yet."}

    expected = {
        "count": sum(counts),
        "diameter": round(diameters[0], 3),
    }
    if len(items) == 1 and expected_centers is not None:
        expected["centers"] = expected_centers
    if len(items) == 1 and spacing is not None:
        expected.update(spacing)
    return {"status": "known", "expected": expected}


def _chamfer_expectation(feature: Any) -> dict[str, Any]:
    if isinstance(feature, dict):
        size = float(feature.get("size", 0) or 0)
    else:
        size = float(feature or 0)
    if size <= 0:
        return {"status": "unknown", "expected": feature, "reason": "Chamfer feature is missing a usable size."}
    return {
        "status": "known",
        "expected": {
            "count": 4,
            "size": round(size, 3),
            "edge_set": "vertical_edges",
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


def _expected_hole_centers(item: dict[str, Any]) -> list[list[float]] | None:
    positions = item.get("positions")
    if isinstance(positions, list):
        centers = []
        for point in positions:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                return None
            centers.append([round(float(point[0]), 3), round(float(point[1]), 3)])
        return _sort_xy_centers(centers)
    return None


def _expected_corner_centers(cad_ir: CADIR, item: dict[str, Any]) -> list[list[float]] | None:
    dims = cad_ir.dimensions
    length = dims.get("length", 0)
    width = dims.get("width", 0)
    if length <= 0 or width <= 0:
        return None
    diameter = float(item.get("diameter", 0) or 0)
    offset = float(item.get("offset_from_edge", max(diameter, min(length, width) * 0.2)) or 0)
    if offset <= 0:
        return None
    x = length / 2 - offset
    y = width / 2 - offset
    return _sort_xy_centers([[-x, -y], [-x, y], [x, -y], [x, y]])


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
        "centers": _sort_centers([item["center"] for item in cylinders]),
    }


def _measure_vertical_edge_chamfers(faces: list[Any], thickness: float, expected_size: float) -> dict[str, Any]:
    if thickness <= 0:
        return {"reliable": False, "count": 0, "size": None, "sizes": [], "reason": "Part thickness is missing or non-positive."}

    candidates = []
    for face in faces:
        try:
            if face.geomType() != "PLANE":
                continue
            bbox = face.BoundingBox()
        except Exception:
            continue
        if not isclose(bbox.zlen, thickness, abs_tol=CHAMFER_TOLERANCE_MM):
            continue
        spans = sorted([round(bbox.xlen, 3), round(bbox.ylen, 3)])
        if not isclose(spans[0], expected_size, abs_tol=CHAMFER_TOLERANCE_MM):
            continue
        if not isclose(spans[1], expected_size, abs_tol=CHAMFER_TOLERANCE_MM):
            continue
        candidates.append({
            "size": round((bbox.xlen + bbox.ylen) / 2, 3),
            "center": [round(value, 3) for value in face.Center().toTuple()],
        })

    sizes = [item["size"] for item in candidates]
    size = round(sum(sizes) / len(sizes), 3) if sizes else None
    return {
        "reliable": True,
        "count": len(candidates),
        "size": size,
        "sizes": sizes,
        "centers": _sort_centers([item["center"] for item in candidates]),
    }


def _inspect_mounting_plate_hole_spacing(
    cad_ir: CADIR,
    measured: dict[str, Any],
) -> dict[str, Any]:
    expected_spacing = _expected_spacing(cad_ir)
    if expected_spacing.get("status") != "known":
        return {
            "status": "unverified",
            "expected": None,
            "measured": None,
            "reason": expected_spacing.get("reason", "Expected hole spacing could not be inferred from IR."),
        }

    measured_spacing = _measured_spacing(measured)
    if measured_spacing.get("status") != "known":
        return {
            "status": "unverified",
            "expected": expected_spacing["expected"],
            "measured": measured_spacing.get("measured"),
            "reason": measured_spacing.get("reason", "Measured hole spacing could not be inferred from topology."),
        }

    expected_value = expected_spacing["expected"]
    measured_value = measured_spacing["measured"]
    x_pass = isclose(measured_value["x"], expected_value["x"], abs_tol=HOLE_TOLERANCE_MM)
    y_pass = isclose(measured_value["y"], expected_value["y"], abs_tol=HOLE_TOLERANCE_MM)
    return {
        "status": "verified" if x_pass and y_pass else "failed",
        "expected": expected_value,
        "measured": measured_value,
        "tolerance": HOLE_TOLERANCE_MM,
        "checks": {
            "x": x_pass,
            "y": y_pass,
        },
    }


def _expected_spacing(cad_ir: CADIR) -> dict[str, Any]:
    features = cad_ir.features
    feature = _expected_feature(features, "holes", aliases=("mounting_holes", "base_holes"))
    items = feature if isinstance(feature, list) else [feature]
    items = [item for item in items if isinstance(item, dict)]
    if len(items) != 1:
        return {"status": "unknown", "reason": "Hole spacing inspection requires one mounting_plate hole feature."}

    item = items[0]
    positions = item.get("positions")
    if positions == "corner_4" or (item.get("pattern") == "corner" and int(item.get("count", 0) or 0) == 4):
        centers = _expected_corner_centers(cad_ir, item)
    elif isinstance(positions, list):
        centers = _expected_hole_centers(item)
    else:
        centers = None

    if centers is None:
        return {"status": "unknown", "reason": "Expected hole center positions could not be inferred from IR."}

    spacing = _spacing_from_centers(centers)
    if spacing is None:
        return {"status": "unknown", "reason": "Expected centers do not form a four-corner spacing pattern."}

    return {
        "status": "known",
        "expected": {
            "centers": centers,
            "x": spacing["spacing_x"],
            "y": spacing["spacing_y"],
        },
    }


def _measured_spacing(measured: dict[str, Any]) -> dict[str, Any]:
    centers = measured.get("centers") or []
    spacing = _spacing_from_centers([[center[0], center[1]] for center in centers if len(center) >= 2])
    if spacing is None:
        return {
            "status": "unknown",
            "measured": {"centers": centers},
            "reason": "Measured centers do not form a four-corner spacing pattern.",
        }
    return {
        "status": "known",
        "measured": {
            "centers": _sort_centers(centers),
            "x": spacing["spacing_x"],
            "y": spacing["spacing_y"],
        },
    }


def _spacing_from_centers(centers: list[list[float]]) -> dict[str, float] | None:
    if len(centers) != 4:
        return None
    xs = _cluster_axis([center[0] for center in centers])
    ys = _cluster_axis([center[1] for center in centers])
    if len(xs) != 2 or len(ys) != 2:
        return None
    return {
        "spacing_x": round(xs[1] - xs[0], 3),
        "spacing_y": round(ys[1] - ys[0], 3),
    }


def _cluster_axis(values: list[float]) -> list[float]:
    clusters: list[list[float]] = []
    for value in sorted(values):
        if not clusters or abs(value - clusters[-1][-1]) > HOLE_TOLERANCE_MM:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [round(sum(cluster) / len(cluster), 3) for cluster in clusters]


def _sort_centers(centers: list[list[float]]) -> list[list[float]]:
    return sorted(([round(float(value), 3) for value in center] for center in centers), key=lambda center: (center[0], center[1], center[2] if len(center) > 2 else 0))


def _sort_xy_centers(centers: list[list[float]]) -> list[list[float]]:
    return sorted(([round(float(center[0]), 3), round(float(center[1]), 3)] for center in centers), key=lambda center: (center[0], center[1]))
