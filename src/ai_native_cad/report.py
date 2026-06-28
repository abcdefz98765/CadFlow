"""Report generator — produces JSON and Markdown reports."""

import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def generate_report(model, params: dict, files: dict, validation: dict, elapsed: float, output_dir: Path | None = None) -> dict:
    """Generate report.json and report.md."""
    part_type = params.get("part_type", "")
    if not part_type:
        raise ValueError("params must include a 'part_type' key")

    output_dir = Path(output_dir) if output_dir is not None else PROJECT_ROOT / "runs" / part_type

    report_data = {
        "part_type": part_type,
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "status": "success" if validation.get("valid") else "failed",
        "params": params,
        "validation": validation,
        "files": files,
    }

    # Write JSON
    json_path = output_dir / "report.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report_data, indent=2))

    # Write Markdown
    md_lines = [
        f"# {params.get('part_type', 'Part')} Report",
        "",
        f"**Status:** {report_data['status']}  ",
        f"**Time:** {report_data['timestamp']}  ",
        f"**Elapsed:** {report_data['elapsed_seconds']:.2f}s",
        "",
        "## Dimensions",
        "",
    ]

    bbox = validation.get("bounding_box", {})
    if bbox:
        md_lines.append(f"| Axis | Size |")
        md_lines.append(f"|------|------|")
        md_lines.append(f"| X | {bbox['x']:.1f} mm |")
        md_lines.append(f"| Y | {bbox['y']:.1f} mm |")
        md_lines.append(f"| Z | {bbox['z']:.1f} mm |")

    vol = validation.get("volume_mm3", 0)
    md_lines.append(f"\n**Volume:** {vol:.1f} mm³")

    md_lines.append("\n## Checks\n")
    for check in validation.get("checks", []):
        status = "PASS" if check.get("pass") else "FAIL"
        desc = check.get("dimension", check.get("file", check.get("check", "unknown")))
        md_lines.append(f"- [{status}] {desc}")

    md_lines.append("\n## Files\n")
    for fmt, path in files.items():
        md_lines.append(f"- `{path}` ({fmt.upper()})")

    md_path = output_dir / "report.md"
    md_path.write_text("\n".join(md_lines) + "\n")

    return {"report_json": str(json_path), "report_md": str(md_path)}
