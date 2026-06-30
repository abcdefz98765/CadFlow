"""Run prompt-to-output examples through the deterministic requirement parser."""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_native_cad.cad_ir import CADIR
from ai_native_cad.pipeline import run_ir_pipeline
from ai_native_cad.requirements import RequirementAgent

PROMPT_CASES = {
    "mounting_plate_by_holes": (
        "Generate a mounting plate 80 by 40 by 5 mm with four 5 mm holes in the corners. "
        "Export STEP and STL."
    ),
    "spacer_named_dims": "Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.",
    "enclosure_step_only": "Build an enclosure base 100x60x25 mm with wall thickness 2 mm and STEP output.",
}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    selected = argv or sorted(PROMPT_CASES)
    unknown = sorted(set(selected) - set(PROMPT_CASES))
    if unknown:
        print(f"Unknown prompt case(s): {', '.join(unknown)}")
        print(f"Available cases: {', '.join(sorted(PROMPT_CASES))}")
        return 2

    agent = RequirementAgent()
    failed = False
    for case_id in selected:
        output_dir = PROJECT_ROOT / "outputs" / "prompt_pipeline" / case_id
        output_dir.mkdir(parents=True, exist_ok=True)
        prompt = PROMPT_CASES[case_id]
        requirement = agent.parse(prompt)
        (output_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
        (output_dir / "requirement.json").write_text(
            json.dumps(requirement, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = run_ir_pipeline(CADIR.from_dict(requirement), output_dir=output_dir)
        summary = _prompt_summary(case_id, prompt, requirement, result)
        (output_dir / "prompt_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / "prompt_summary.md").write_text(_prompt_summary_markdown(summary), encoding="utf-8")
        failed = failed or result["status"] != "success"
        print(
            f"{case_id}: {result['status']} "
            f"attempts={summary['pipeline']['attempts']} "
            f"targets={summary['requirement']['cad_brief_validation_target_count']} "
            f"-> {result['output_dir']}"
        )
    return 1 if failed else 0


def _prompt_summary(
    case_id: str,
    prompt: str,
    requirement: dict[str, object],
    result: dict[str, object],
) -> dict[str, object]:
    validation = result.get("validation", {}) if isinstance(result.get("validation"), dict) else {}
    inspection = validation.get("inspection", {}) if isinstance(validation.get("inspection"), dict) else {}
    holes = inspection.get("features", {}).get("holes", {}) if isinstance(inspection.get("features"), dict) else {}
    agent_trace = result.get("agent_trace", {}) if isinstance(result.get("agent_trace"), dict) else {}
    cad_brief = requirement.get("cad_brief", {}) if isinstance(requirement.get("cad_brief"), dict) else {}
    requirement_status = (
        requirement.get("requirement_status", {}) if isinstance(requirement.get("requirement_status"), dict) else {}
    )
    return {
        "case_id": case_id,
        "prompt": prompt,
        "requirement": {
            "part_type": requirement.get("part_type"),
            "outputs": requirement.get("outputs"),
            "complete_for_generation": requirement_status.get("complete_for_generation"),
            "needs_user_input": requirement_status.get("needs_user_input"),
            "missing_fields": requirement_status.get("missing_fields", []),
            "cad_brief_validation_target_count": len(cad_brief.get("validation_targets", [])),
            "cad_brief_validation_targets": cad_brief.get("validation_targets", []),
        },
        "pipeline": {
            "status": result.get("status"),
            "attempts": agent_trace.get("total_attempts"),
            "final_selected_candidate": agent_trace.get("final_selected_candidate"),
            "bounding_box": validation.get("bounding_box", {}),
            "measured_validation_targets": validation.get("measured_validation_targets", []),
            "hole_inspection": holes,
        },
        "files": result.get("files", {}),
        "output_dir": result.get("output_dir"),
    }


def _prompt_summary_markdown(summary: dict[str, object]) -> str:
    requirement = summary["requirement"]
    pipeline = summary["pipeline"]
    files = summary["files"]
    assert isinstance(requirement, dict)
    assert isinstance(pipeline, dict)
    assert isinstance(files, dict)
    lines = [
        f"# Prompt Pipeline Summary: {summary['case_id']}",
        "",
        f"**Status:** {pipeline.get('status')}",
        f"**Part type:** {requirement.get('part_type')}",
        f"**Attempts:** {pipeline.get('attempts')}",
        f"**CAD Brief targets:** {requirement.get('cad_brief_validation_target_count')}",
        f"**Needs user input:** {requirement.get('needs_user_input')}",
        "",
        "## Prompt",
        "",
        str(summary["prompt"]),
        "",
        "## Validation",
        "",
        f"- Bounding box: `{pipeline.get('bounding_box', {})}`",
        f"- Measured targets: {len(pipeline.get('measured_validation_targets', []))}",
    ]
    hole_inspection = pipeline.get("hole_inspection") or {}
    if isinstance(hole_inspection, dict) and hole_inspection:
        lines.append(f"- Holes: {hole_inspection.get('status', 'unknown')}")
    missing_fields = requirement.get("missing_fields") or []
    if missing_fields:
        lines.extend(["", "## Missing Fields", ""])
        lines.extend(f"- `{field}`" for field in missing_fields)
    lines.extend(["", "## Files", ""])
    for label, path in sorted(files.items()):
        lines.append(f"- {label}: `{path}`")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
