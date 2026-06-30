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
) -> dict[str, str]:
    output_path = Path(output_dir)
    report = {
        "part_type": ir["part_type"],
        "part_name": ir.get("part_name", ir["part_type"]),
        "timestamp": datetime.now().isoformat(),
        "status": "success" if execution.get("status") == "success" and validation.get("valid") else "failed",
        "ir": ir,
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
    bbox = validation.get("bounding_box", {})
    if bbox:
        lines.extend([
            f"- Bounding box: {bbox['x']:.3f} x {bbox['y']:.3f} x {bbox['z']:.3f} mm",
            f"- Volume: {validation.get('volume_mm3', 0):.3f} mm^3",
        ])
    for check in validation.get("checks", []):
        status = "PASS" if check.get("pass") else "FAIL"
        label = check.get("dimension") or check.get("check") or check.get("file") or "check"
        lines.append(f"- [{status}] {label}")
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
