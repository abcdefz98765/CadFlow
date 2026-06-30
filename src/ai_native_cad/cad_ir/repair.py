"""Structured CAD IR repair helpers for the agent loop."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ai_native_cad.cad_ir.schema import CADIR


def repair_ir(ir: CADIR | dict[str, Any], failure_analysis: dict[str, Any]) -> dict[str, Any]:
    """Repair only the fields implicated by failure analysis while preserving design intent."""
    cad_ir = CADIR.from_dict(ir) if isinstance(ir, dict) else ir
    original = cad_ir.to_dict()
    repaired = deepcopy(original)
    changes: list[str] = []
    fix = failure_analysis.get("suggested_ir_fix", {})
    strategy = fix.get("strategy")
    affected = failure_analysis.get("affected_feature")

    if repaired.get("outputs") != ["step", "stl"]:
        repaired["outputs"] = ["step", "stl"]
        changes.append("restored required STEP/STL outputs")

    if strategy in {"increase_spacing", "repair_feature_clearance", "conservative_geometry"} or affected == "holes":
        changes.extend(_repair_holes(repaired))

    if strategy == "reduce_size" or affected in {"chamfer", "fillet"}:
        changes.extend(_repair_edge_relief(repaired, affected))

    if repaired["part_type"] == "spacer":
        changes.extend(_repair_spacer(repaired))

    if repaired["part_type"] == "enclosure_base":
        changes.extend(_repair_enclosure_base(repaired))

    if not changes:
        changes.append("no IR fields changed; failure requires code-level handling")

    repaired["part_type"] = original["part_type"]
    return {
        "original_ir": original,
        "repaired_ir": repaired,
        "changes": changes,
        "diff": _repair_diff(original, repaired, failure_analysis),
    }


def _repair_diff(original: dict[str, Any], repaired: dict[str, Any], failure_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    root_cause = str(failure_analysis.get("root_cause") or "unknown")
    affected_feature = failure_analysis.get("affected_feature")
    diff = []
    for item in _diff_values(original, repaired):
        feature = affected_feature or _feature_from_path(item["path"])
        entry = {
            "path": item["path"],
            "before": item["before"],
            "after": item["after"],
            "reason": root_cause,
        }
        if feature:
            entry["affected_feature"] = str(feature)
        diff.append(entry)
    return diff


def _diff_values(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        diff = []
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in before:
                diff.append({"path": child_path, "before": None, "after": after[key]})
            elif key not in after:
                diff.append({"path": child_path, "before": before[key], "after": None})
            else:
                diff.extend(_diff_values(before[key], after[key], child_path))
        return diff

    if isinstance(before, list) and isinstance(after, list):
        diff = []
        for index in range(max(len(before), len(after))):
            child_path = f"{path}[{index}]"
            if index >= len(before):
                diff.append({"path": child_path, "before": None, "after": after[index]})
            elif index >= len(after):
                diff.append({"path": child_path, "before": before[index], "after": None})
            else:
                diff.extend(_diff_values(before[index], after[index], child_path))
        return diff

    if before != after:
        return [{"path": path, "before": before, "after": after}]
    return []


def _feature_from_path(path: str) -> str | None:
    if not path.startswith("features."):
        return None
    feature_path = path.removeprefix("features.")
    feature = feature_path.split(".", 1)[0].split("[", 1)[0]
    return feature or None


def _repair_holes(ir: dict[str, Any]) -> list[str]:
    features = ir.get("features", {})
    dims = ir.get("dimensions", {})
    changes: list[str] = []
    for key in ("holes", "mounting_holes", "base_holes"):
        holes = features.get(key)
        hole_items = holes if isinstance(holes, list) else [holes] if isinstance(holes, dict) else []
        for item in hole_items:
            diameter = float(item.get("diameter", 0) or 0)
            if diameter <= 0:
                continue
            min_span = min(_dimension_values_for_holes(ir["part_type"], dims) or [0])
            if min_span <= 0:
                continue
            if diameter > min_span * 0.3:
                item["diameter"] = round(min_span * 0.25, 3)
                diameter = float(item["diameter"])
                changes.append("reduced oversized hole diameter")
            min_offset = diameter * 0.75
            max_offset = max(min_span / 2 - diameter * 0.75, min_offset)
            current = float(item.get("offset_from_edge", min_offset) or min_offset)
            repaired_offset = min(max(current, min_offset), max_offset)
            if repaired_offset != current:
                item["offset_from_edge"] = round(repaired_offset, 3)
                changes.append("adjusted hole spacing")
    return changes


def _repair_edge_relief(ir: dict[str, Any], affected: str | None) -> list[str]:
    features = ir.get("features", {})
    dims = ir.get("dimensions", {})
    smallest = min((value for value in dims.values() if value > 0), default=0)
    max_size = smallest * 0.2 if smallest else 0
    changes: list[str] = []
    for key, size_key in (("chamfer", "size"), ("fillet", "radius")):
        if affected not in {None, key, "geometry"} and key not in features:
            continue
        value = features.get(key)
        if isinstance(value, dict):
            current = float(value.get(size_key, 0) or 0)
            if max_size and current > max_size:
                value[size_key] = round(max_size, 3)
                changes.append(f"reduced {key} size")
        elif isinstance(value, (int, float)) and max_size and float(value) > max_size:
            features[key] = round(max_size, 3)
            changes.append(f"reduced {key} size")
    return changes


def _repair_spacer(ir: dict[str, Any]) -> list[str]:
    dims = ir.get("dimensions", {})
    outer = dims.get("outer_diameter", 0)
    inner = dims.get("inner_diameter", 0)
    if outer > 0 and inner >= outer:
        dims["inner_diameter"] = round(outer * 0.55, 3)
        return ["reduced inner diameter below outer diameter"]
    return []


def _repair_enclosure_base(ir: dict[str, Any]) -> list[str]:
    dims = ir.get("dimensions", {})
    wall = dims.get("wall_thickness", 0)
    limit = min(dims.get("outer_length", 0), dims.get("outer_width", 0)) / 2
    if wall > 0 and limit > 0 and wall >= limit:
        dims["wall_thickness"] = round(limit * 0.25, 3)
        return ["reduced wall thickness to preserve cavity"]
    return []


def _dimension_values_for_holes(part_type: str, dims: dict[str, float]) -> list[float]:
    if part_type in {"mounting_plate", "enclosure_lid"}:
        return [dims.get("length", 0), dims.get("width", 0)]
    if part_type == "simple_bracket":
        return [dims.get("base_length", 0), dims.get("base_width", 0)]
    return [value for value in dims.values() if value > 0]
