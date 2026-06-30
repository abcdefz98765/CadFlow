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
        failed = failed or result["status"] != "success"
        print(f"{case_id}: {result['status']} -> {result['output_dir']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
