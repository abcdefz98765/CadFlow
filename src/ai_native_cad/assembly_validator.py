"""Assembly self-checks for generated CAD assemblies.

This module intentionally does not depend on FreeCAD. It validates the
assembly intent that agents can reason about: referenced files, part reports,
single-solid parts, coarse bbox placement, required contacts, and floating
components.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONTACT_TOLERANCE = 0.1
DEFAULT_MIN_CLEARANCE = 0.5


@dataclass(frozen=True)
class BBox:
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float

    @property
    def x(self) -> float:
        return self.xmax - self.xmin

    @property
    def y(self) -> float:
        return self.ymax - self.ymin

    @property
    def z(self) -> float:
        return self.zmax - self.zmin

    def translated(self, position: list[float]) -> "BBox":
        return BBox(
            self.xmin + position[0],
            self.xmax + position[0],
            self.ymin + position[1],
            self.ymax + position[1],
            self.zmin + position[2],
            self.zmax + position[2],
        )


@dataclass
class PartInstance:
    name: str
    step_path: Path
    report_path: Path
    position: list[float]
    rotation: list[float]
    bbox: BBox | None = None
    report: dict[str, Any] | None = None


def validate_assembly_config(config_path: str | Path, project_root: str | Path | None = None) -> dict:
    """Validate an assembly JSON file and write validation reports."""
    config_path = Path(config_path)
    root = Path(project_root) if project_root is not None else Path.cwd()
    config = json.loads((root / config_path).read_text() if not config_path.is_absolute() else config_path.read_text())
    return validate_assembly(config, root)


def validate_assembly(config: dict, project_root: str | Path = ".") -> dict:
    """Run deterministic assembly self-checks.

    The validator treats FreeCAD boolean interference as a later diagnostic.
    Here we check stable facts that an agent can repair before exporting FCStd.
    """
    root = Path(project_root)
    output_dir = root / config.get("output_dir", "runs/assembly")
    output_dir.mkdir(parents=True, exist_ok=True)

    validation_cfg = config.get("validation", {})
    contact_tolerance = float(validation_cfg.get("contact_tolerance", DEFAULT_CONTACT_TOLERANCE))
    min_clearance = float(validation_cfg.get("min_clearance", DEFAULT_MIN_CLEARANCE))
    anchors = set(validation_cfg.get("anchors", []))
    allowed_overlaps = validation_cfg.get("allowed_bbox_overlaps", [])
    allowed_close_clearances = validation_cfg.get("allowed_close_clearances", [])
    required_contacts = validation_cfg.get("required_contacts", [])

    result = {
        "status": "success",
        "project": config.get("name", "assembly"),
        "output_dir": str(output_dir),
        "stages": {},
        "checks": [],
        "parts": [],
        "contacts": [],
        "possible_interferences": [],
        "errors": [],
        "warnings": [],
        "files": {},
    }

    _run_stage(result, "preflight_assembly_intent", lambda: preflight_assembly_intent(config, validation_cfg, result))
    parts = _run_stage(result, "validate_part_inputs", lambda: validate_part_inputs(config, root, result))
    positioned = [p for p in parts if p.bbox is not None]
    name_to_part = {p.name: p for p in positioned}

    _run_stage(
        result,
        "validate_placement_relationships",
        lambda: validate_placement_relationships(
            positioned,
            allowed_overlaps,
            allowed_close_clearances,
            contact_tolerance,
            min_clearance,
            anchors,
            result,
        ),
    )
    _run_stage(
        result,
        "validate_constraints",
        lambda: validate_constraints(config, name_to_part, required_contacts, contact_tolerance, result),
    )
    _run_stage(result, "validate_assembly_exports", lambda: validate_assembly_exports(config, root, result))

    if result["errors"]:
        result["status"] = "failed"
    elif result["warnings"] or result["possible_interferences"]:
        result["status"] = "warning"

    json_path = output_dir / "assembly_validation.json"
    md_path = output_dir / "assembly_validation.md"
    review_path = output_dir / "assembly_review.md"
    result["files"]["validation_json"] = str(json_path)
    result["files"]["validation_md"] = str(md_path)
    result["files"]["assembly_review_md"] = str(review_path)
    json_path.write_text(json.dumps(result, indent=2))
    markdown = _render_markdown(result)
    md_path.write_text(markdown)
    review_path.write_text(markdown)
    return result


def preflight_assembly_intent(config: dict, validation_cfg: dict | None = None, result: dict | None = None) -> dict:
    """Check whether assembly intent has enough traceable structure."""
    validation_cfg = validation_cfg if validation_cfg is not None else config.get("validation", {})
    local = result if result is not None else _empty_result(config)

    if not config.get("parts"):
        _error(local, "assembly_parts_missing", "Assembly config must include at least one part.")
    if not config.get("name"):
        _warning(local, "assembly_name_missing", "Assembly config should include a traceable name.")

    for field in ["allowed_bbox_overlaps", "allowed_close_clearances"]:
        for rule in validation_cfg.get(field, []):
            if not rule.get("reason"):
                _warning(
                    local,
                    "validation_rule_missing_reason",
                    f"{field} rule should include a reason: {rule}",
                    rule=rule,
                )

    for rule in validation_cfg.get("required_contacts", []):
        if not rule.get("intent"):
            _warning(
                local,
                "required_contact_missing_intent",
                f"required_contacts rule should include intent: {rule}",
                rule=rule,
            )

    return _summary(local)


def validate_part_inputs(config: dict, root: Path | str = ".", result: dict | None = None) -> list[PartInstance]:
    """Load part reports and validate that each assembly input is usable."""
    root = Path(root)
    local = result if result is not None else _empty_result(config)
    seen_names = set()
    parts = []
    for part_cfg in config.get("parts", []):
        name = part_cfg.get("name") or Path(part_cfg.get("step", "")).stem
        if "step" not in part_cfg:
            _error(local, "missing_step_field", f"Part entry lacks step path: {part_cfg}", part=name)
            continue
        step_path = root / part_cfg["step"]
        report_path = step_path.parent / "report.json"
        position = [float(v) for v in part_cfg.get("position", [0, 0, 0])]
        rotation = [float(v) for v in part_cfg.get("rotation", [0, 0, 0])]
        part = PartInstance(name, step_path, report_path, position, rotation)
        parts.append(part)
        local["parts"].append({"name": name, "step": str(step_path), "report": str(report_path)})

        if name in seen_names:
            _error(local, "duplicate_part_name", f"Duplicate part name: {name}", part=name)
        seen_names.add(name)

        if not step_path.exists():
            _error(local, "missing_step", f"STEP not found: {step_path}", part=name)
            continue
        if not report_path.exists():
            _error(local, "missing_report", f"report.json not found for part: {name}", part=name)
            continue

        try:
            report = json.loads(report_path.read_text())
        except json.JSONDecodeError as exc:
            _error(local, "invalid_report_json", f"Invalid report.json for {name}: {exc}", part=name)
            continue

        part.report = report
        validation = report.get("validation", {})
        if report.get("status") != "success" or validation.get("valid") is False:
            _error(local, "invalid_part_report", f"Part report is not valid: {name}", part=name)

        solid_count = validation.get("solid_count")
        if solid_count is not None and solid_count != 1:
            _error(local, "multi_solid_part", f"Part is not a single solid: {name} ({solid_count})", part=name)

        bbox = _bbox_from_report(validation.get("bounding_box", {}), local, name)
        if bbox is not None:
            part.bbox = bbox.translated(position)

        if rotation != [0.0, 0.0, 0.0]:
            _warning(local, "rotation_not_checked", f"Rotation is not included in bbox self-check: {name}", part=name)

    return parts


def _bbox_from_report(data: dict, result: dict, part_name: str) -> BBox | None:
    required_extents = {"xmin", "xmax", "ymin", "ymax", "zmin", "zmax"}
    if required_extents.issubset(data):
        return BBox(
            float(data["xmin"]), float(data["xmax"]),
            float(data["ymin"]), float(data["ymax"]),
            float(data["zmin"]), float(data["zmax"]),
        )

    if {"x", "y", "z"}.issubset(data):
        _warning(
            result,
            "bbox_origin_assumed",
            f"Report lacks bbox min/max; assuming centered X/Y and bottom Z=0 for {part_name}",
            part=part_name,
        )
        return BBox(-data["x"] / 2, data["x"] / 2, -data["y"] / 2, data["y"] / 2, 0.0, data["z"])

    _error(result, "missing_bbox", f"Report lacks bounding_box for part: {part_name}", part=part_name)
    return None


def _check_bbox_relationships(
    parts: list[PartInstance],
    allowed_overlaps: list[dict],
    allowed_close_clearances: list[dict],
    contact_tolerance: float,
    min_clearance: float,
    result: dict,
) -> None:
    for index, part_a in enumerate(parts):
        for part_b in parts[index + 1:]:
            assert part_a.bbox is not None and part_b.bbox is not None
            contact = _contact_between(part_a.bbox, part_b.bbox, contact_tolerance)
            if contact:
                contact.update({"part1": part_a.name, "part2": part_b.name})
                result["contacts"].append(contact)
                continue

            overlap = _overlap_volume(part_a.bbox, part_b.bbox)
            if overlap > 0 and not _pair_allowed(part_a.name, part_b.name, allowed_overlaps):
                item = {
                    "part1": part_a.name,
                    "part2": part_b.name,
                    "overlap_volume_mm3": round(overlap, 3),
                    "message": "Axis-aligned bbox overlap; verify with assembly intent or add allowed_bbox_overlaps if this is a cavity/container case.",
                }
                result["possible_interferences"].append(item)
                _warning(result, "possible_bbox_interference", item["message"], part=f"{part_a.name}/{part_b.name}")

            gap = _minimum_axis_gap(part_a.bbox, part_b.bbox)
            if 0 < gap < min_clearance and not _pair_allowed(part_a.name, part_b.name, allowed_close_clearances):
                _warning(
                    result,
                    "clearance_below_minimum",
                    f"{part_a.name} and {part_b.name} clearance {gap:.3f}mm is below {min_clearance:.3f}mm",
                    part=f"{part_a.name}/{part_b.name}",
                )


def validate_placement_relationships(
    parts: list[PartInstance],
    allowed_overlaps: list[dict],
    allowed_close_clearances: list[dict],
    contact_tolerance: float = DEFAULT_CONTACT_TOLERANCE,
    min_clearance: float = DEFAULT_MIN_CLEARANCE,
    anchors: set[str] | None = None,
    result: dict | None = None,
) -> dict:
    """Validate coarse bbox placement, overlaps, clearances, and floating parts."""
    local = result if result is not None else _empty_result({"name": "assembly"})
    _check_bbox_relationships(parts, allowed_overlaps, allowed_close_clearances, contact_tolerance, min_clearance, local)
    _check_floating_parts(parts, anchors or set(), local)
    return _summary(local)


def _check_required_contacts(
    name_to_part: dict[str, PartInstance],
    required_contacts: list[dict],
    contact_tolerance: float,
    result: dict,
) -> None:
    for rule in required_contacts:
        part1 = name_to_part.get(rule.get("part1", ""))
        part2 = name_to_part.get(rule.get("part2", ""))
        axis = rule.get("axis")
        if part1 is None or part2 is None:
            _error(result, "required_contact_missing_part", f"Required contact references missing part: {rule}", rule=rule)
            continue
        assert part1.bbox is not None and part2.bbox is not None
        contact = _contact_between(part1.bbox, part2.bbox, contact_tolerance, axis)
        if not contact:
            _error(
                result,
                "required_contact_failed",
                f"Required contact not satisfied: {part1.name} <-> {part2.name}",
                rule=rule,
            )


def validate_constraints(
    config: dict,
    name_to_part: dict[str, PartInstance],
    required_contacts: list[dict],
    contact_tolerance: float = DEFAULT_CONTACT_TOLERANCE,
    result: dict | None = None,
) -> dict:
    """Validate lightweight constraint intent without binding to a CAD solver."""
    local = result if result is not None else _empty_result(config)
    _check_required_contacts(name_to_part, required_contacts, contact_tolerance, local)

    known_parts = set(name_to_part)
    for constraint in config.get("constraints", []):
        ctype = constraint.get("type")
        if ctype not in {"fixed", "coincident", "concentric", "parallel", "distance"}:
            _error(local, "unsupported_constraint_type", f"Unsupported constraint type: {constraint}", rule=constraint)
        for field in ["part1", "part2"]:
            part_name = constraint.get(field)
            if part_name and part_name not in known_parts:
                _error(local, "constraint_missing_part", f"Constraint references missing part: {constraint}", rule=constraint)
        if not constraint.get("name"):
            _warning(local, "constraint_name_missing", f"Constraint should include a traceable name: {constraint}", rule=constraint)

    return _summary(local)


def validate_assembly_exports(config: dict, root: Path | str = ".", result: dict | None = None) -> dict:
    """Validate declared assembly export artifacts when the config declares them."""
    root = Path(root)
    local = result if result is not None else _empty_result(config)
    for export_path in config.get("expected_exports", []):
        path = root / export_path
        if not path.exists():
            _warning(local, "assembly_export_missing", f"Declared assembly export does not exist yet: {path}", path=str(path))
        elif path.is_file() and path.stat().st_size == 0:
            _warning(local, "assembly_export_empty", f"Declared assembly export is empty: {path}", path=str(path))
    return _summary(local)


def _check_floating_parts(parts: list[PartInstance], anchors: set[str], result: dict) -> None:
    contacted = set()
    for contact in result["contacts"]:
        contacted.add(contact["part1"])
        contacted.add(contact["part2"])

    if not anchors and parts:
        anchors.add(parts[0].name)

    for part in parts:
        if part.name in anchors:
            continue
        if part.name not in contacted:
            _error(
                result,
                "floating_part",
                f"Part has no bbox contact/support relationship: {part.name}",
                part=part.name,
            )


def _overlap_volume(a: BBox, b: BBox) -> float:
    dx = max(0.0, min(a.xmax, b.xmax) - max(a.xmin, b.xmin))
    dy = max(0.0, min(a.ymax, b.ymax) - max(a.ymin, b.ymin))
    dz = max(0.0, min(a.zmax, b.zmax) - max(a.zmin, b.zmin))
    return dx * dy * dz


def _contact_between(a: BBox, b: BBox, tolerance: float, axis: str | None = None) -> dict | None:
    axes = [axis] if axis else ["x", "y", "z"]
    for ax in axes:
        gap = _axis_face_gap(a, b, ax)
        if gap <= tolerance and _projected_overlap(a, b, ax):
            return {"axis": ax, "gap_mm": round(gap, 3)}
    return None


def _axis_face_gap(a: BBox, b: BBox, axis: str) -> float:
    amin, amax = getattr(a, f"{axis}min"), getattr(a, f"{axis}max")
    bmin, bmax = getattr(b, f"{axis}min"), getattr(b, f"{axis}max")
    return min(abs(amax - bmin), abs(bmax - amin))


def _projected_overlap(a: BBox, b: BBox, contact_axis: str) -> bool:
    for axis in {"x", "y", "z"} - {contact_axis}:
        if min(getattr(a, f"{axis}max"), getattr(b, f"{axis}max")) <= max(getattr(a, f"{axis}min"), getattr(b, f"{axis}min")):
            return False
    return True


def _minimum_axis_gap(a: BBox, b: BBox) -> float:
    gaps = []
    for axis in ["x", "y", "z"]:
        amin, amax = getattr(a, f"{axis}min"), getattr(a, f"{axis}max")
        bmin, bmax = getattr(b, f"{axis}min"), getattr(b, f"{axis}max")
        if amax < bmin:
            gaps.append(bmin - amax)
        elif bmax < amin:
            gaps.append(amin - bmax)
    return min(gaps) if gaps else 0.0


def _pair_allowed(part1: str, part2: str, rules: list[dict]) -> bool:
    for rule in rules:
        a = rule.get("part1", "")
        b = rule.get("part2", "")
        if (fnmatch.fnmatch(part1, a) and fnmatch.fnmatch(part2, b)) or (
            fnmatch.fnmatch(part1, b) and fnmatch.fnmatch(part2, a)
        ):
            return True
    return False


def _error(result: dict, code: str, message: str, **extra) -> None:
    item = {"code": code, "message": message, **extra}
    result["errors"].append(item)
    result["checks"].append({"status": "error", **item})


def _warning(result: dict, code: str, message: str, **extra) -> None:
    item = {"code": code, "message": message, **extra}
    result["warnings"].append(item)
    result["checks"].append({"status": "warning", **item})


def _empty_result(config: dict) -> dict:
    return {
        "status": "success",
        "project": config.get("name", "assembly"),
        "output_dir": "",
        "stages": {},
        "checks": [],
        "parts": [],
        "contacts": [],
        "possible_interferences": [],
        "errors": [],
        "warnings": [],
        "files": {},
    }


def _run_stage(result: dict, name: str, fn):
    start_errors = len(result["errors"])
    start_warnings = len(result["warnings"])
    start_checks = len(result["checks"])
    value = fn()
    new_errors = result["errors"][start_errors:]
    new_warnings = result["warnings"][start_warnings:]
    status = "success"
    if new_errors:
        status = "failed"
    elif new_warnings:
        status = "warning"
    result["stages"][name] = {
        "status": status,
        "errors": new_errors,
        "warnings": new_warnings,
        "checks": result["checks"][start_checks:],
    }
    return value


def _summary(result: dict) -> dict:
    return {
        "status": "failed" if result["errors"] else "warning" if result["warnings"] else "success",
        "error_count": len(result["errors"]),
        "warning_count": len(result["warnings"]),
        "check_count": len(result["checks"]),
    }


def _render_markdown(result: dict) -> str:
    lines = [
        f"# {result['project']} Assembly Review",
        "",
        f"**Status:** {result['status']}",
        "",
        "## Stages",
        "",
    ]
    if result.get("stages"):
        lines.extend(f"- {name}: {stage['status']}" for name, stage in result["stages"].items())
    else:
        lines.append("- None")
    lines.extend([
        "",
        "## Errors",
        "",
    ])
    lines.extend(_items(result["errors"]))
    lines.extend(["", "## Warnings", ""])
    lines.extend(_items(result["warnings"]))
    lines.extend(["", "## Contacts", ""])
    lines.extend(
        f"- {c['part1']} <-> {c['part2']} ({c['axis']}, gap={c['gap_mm']}mm)"
        for c in result["contacts"]
    )
    lines.extend(["", "## Possible Interferences", ""])
    lines.extend(
        f"- {i['part1']} <-> {i['part2']}: bbox overlap {i['overlap_volume_mm3']} mm3"
        for i in result["possible_interferences"]
    )
    return "\n".join(lines) + "\n"


def _items(items: list[dict]) -> list[str]:
    if not items:
        return ["- None"]
    return [f"- [{item['code']}] {item['message']}" for item in items]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m ai_native_cad.assembly_validator <assembly.json>")
        raise SystemExit(1)
    print(json.dumps(validate_assembly_config(sys.argv[1]), indent=2))
