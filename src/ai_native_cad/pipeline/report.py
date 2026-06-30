"""Report helpers for the IR-first pipeline."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def write_pipeline_report(
    output_dir: str | Path,
    ir: dict[str, Any],
    execution: dict[str, Any],
    validation: dict[str, Any],
    files: dict[str, str],
    ir_validation: dict[str, Any] | None = None,
) -> dict[str, str]:
    output_path = Path(output_dir)
    ir_valid = True if ir_validation is None else bool(ir_validation.get("valid"))
    execution_success = execution.get("status") == "success"
    success = ir_valid and execution_success and validation.get("valid", False)
    report = {
        "success": success,
        "ir_valid": ir_valid,
        "execution_success": execution_success,
        "step_generated": bool(validation.get("step_generated")),
        "stl_generated": bool(validation.get("stl_generated")),
        "bounding_box": validation.get("bounding_box", {}),
        "volume": validation.get("volume", validation.get("volume_mm3", 0)),
        "inspection": validation.get("inspection", {}),
        "measured_validation_targets": validation.get("measured_validation_targets", []),
        "warnings": list((ir_validation or {}).get("warnings", [])) + list(validation.get("warnings", [])),
        "errors": list((ir_validation or {}).get("errors", [])) + list(validation.get("errors", [])),
        "part_type": ir["part_type"],
        "part_name": ir.get("part_name", ir["part_type"]),
        "timestamp": datetime.now().isoformat(),
        "status": "success" if success else "failed",
        "ir": ir,
        "ir_validation": ir_validation or {"valid": True, "checks": [], "warnings": [], "errors": []},
        "execution": execution,
        "validation": validation,
        "files": files,
    }
    json_path = output_path / "report.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# {report['part_name']} CAD Report",
        "",
        f"**Status:** {report['status']}",
        f"**Part type:** {report['part_type']}",
        f"**Unit:** {ir.get('unit', 'mm')}",
        "",
        "## Validation",
        "",
    ]
    bbox = report["bounding_box"]
    if bbox:
        lines.extend([
            f"- Bounding box: {bbox['x']:.3f} x {bbox['y']:.3f} x {bbox['z']:.3f} mm",
            f"- Volume: {report['volume']:.3f} mm^3",
        ])
    for check in validation.get("checks", []):
        status = "PASS" if check.get("pass") else "FAIL"
        label = check.get("dimension") or check.get("check") or check.get("file") or "check"
        lines.append(f"- [{status}] {label}")
    inspection = validation.get("inspection", {})
    if inspection:
        step_file = inspection.get("step_file", {})
        stl_file = inspection.get("stl_file", {})
        lines.extend([
            "",
            "## Inspection",
            "",
            f"- Primary artifact: `{inspection.get('artifact_roles', {}).get('primary', 'model.step')}`",
            f"- STEP file: {'present' if step_file.get('present') else 'missing'} ({step_file.get('size_bytes', 0)} bytes)",
            f"- STL file: {'present' if stl_file.get('present') else 'missing'} ({stl_file.get('size_bytes', 0)} bytes)",
            f"- Solid count: {inspection.get('solid_count')}",
        ])
    if validation.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in validation["errors"]:
            lines.append(f"- {error.get('code', 'error')}: {error.get('message', error)}")
    lines.extend(["", "## Files", ""])
    for label, path in files.items():
        lines.append(f"- {label}: `{path}`")
    md_path = output_path / "report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"report_json": str(json_path), "report_md": str(md_path)}
