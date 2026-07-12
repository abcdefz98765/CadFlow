"""Create the executable Desktop 2DOF Robot Arm golden Work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ai_native_cad.workflow_console import WorkflowConsoleBackend
from ai_native_cad.workflow_console.actions import WorkflowConsoleActions


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = REPO_ROOT / "examples" / "golden_desktop_robot_arm"
WORK_ID = "golden_desktop_robot_arm"
RUN_ID = "golden_desktop_robot_arm_root"

CLARIFICATION_ANSWERS = [
    {"question_id": "q1", "field": "arm_reach_mm", "question": "Arm reach?", "answer": "220 mm"},
    {"question_id": "q2", "field": "degrees_of_freedom", "question": "Degrees of freedom?", "answer": "2"},
    {"question_id": "q3", "field": "payload_target_g", "question": "Payload target?", "answer": "100 g"},
    {"question_id": "q4", "field": "servo_reference_size_mm", "question": "Servo envelope?", "answer": "40x20x40"},
    {"question_id": "q5", "field": "gripper_opening_mm", "question": "Gripper opening?", "answer": "30 mm"},
    {"question_id": "q6", "field": "actuator_type", "question": "Actuator type?", "answer": "standard 20kg hobby servo"},
    {"question_id": "q7", "field": "manufacturing_method", "question": "Manufacturing method?", "answer": "FDM"},
    {"question_id": "q8", "field": "material", "question": "Material?", "answer": "PLA or PETG"},
    {"question_id": "q9", "field": "gripper_type", "question": "Gripper type?", "answer": "simple parallel or gripper mounting plate"},
    {"question_id": "q10", "field": "primary_generated_part", "question": "Selected part?", "answer": "upper_link"},
    {"question_id": "q11", "field": "safety_note", "question": "Safety scope?", "answer": "desktop demo only"},
]


def run_golden_workflow(
    workspace: str | Path,
    *,
    mode: str = "contract",
    project_root: str | Path = REPO_ROOT,
) -> dict[str, Any]:
    """Execute the real workflow and compare stable actual/expected contracts."""
    if mode not in {"contract", "full"}:
        raise ValueError("golden workflow mode must be 'contract' or 'full'")
    project = Path(project_root).resolve()
    workspace_path = Path(workspace)
    if not workspace_path.is_absolute():
        workspace_path = project / workspace_path
    workspace_path = workspace_path.resolve()
    try:
        workspace_path.relative_to(project)
    except ValueError as exc:
        raise ValueError("executable golden workspace must currently be inside project_root") from exc

    backend = WorkflowConsoleBackend(project_root=project, workspace_root=workspace_path)
    backend.create_workspace(name="CadFlow Golden Examples", advancement_mode="manual_confirm")
    backend.create_work(
        "Golden Desktop Robot Arm",
        description="Executable golden workflow for one reviewed generic link-like concept part.",
        work_id=WORK_ID,
        metadata={"example": "golden_desktop_robot_arm", "mode": mode},
    )
    prompt = (EXAMPLE_ROOT / "prompt.txt").read_text(encoding="utf-8").strip()
    backend.create_work_requirement_run(WORK_ID, prompt, run_id=RUN_ID)
    runs_root = backend._work_runs_root(WORK_ID)

    backend.run_stage_by_id(RUN_ID, "requirement", root=runs_root)
    backend.apply_requirement_clarification_by_id(
        RUN_ID,
        answers=CLARIFICATION_ANSWERS,
        notes="Fixed executable-example inputs; desktop demo only.",
        root=runs_root,
    )
    backend.run_stage_by_id(RUN_ID, "planning", root=runs_root)

    actions = WorkflowConsoleActions(backend)
    actions.create_part_request(RUN_ID, part_id="upper_link", root=runs_root)
    actions.review_part_request(RUN_ID, root=runs_root)
    actions.create_reviewed_handoff(RUN_ID, root=runs_root)
    actions.create_reviewed_part(RUN_ID, root=runs_root, execute_cad=mode == "full")
    if mode == "full":
        actions.review_part_result(RUN_ID, root=runs_root)
    actions.create_workflow_review(RUN_ID, root=runs_root)

    run_path = backend.resolve_run(RUN_ID, root=runs_root)
    comparison = compare_actual_to_expected(run_path, mode=mode)
    _write_comparison(run_path, comparison)
    backend.invalidate_work_index()
    return {
        "workspace": str(workspace_path),
        "work_id": WORK_ID,
        "run_id": RUN_ID,
        "mode": mode,
        "comparison": comparison,
        "work": backend.get_work_detail(WORK_ID),
    }


def compare_actual_to_expected(run_path: str | Path, *, mode: str) -> dict[str, Any]:
    """Compare stable semantic fields; expected files are never runtime inputs."""
    run = Path(run_path)
    child = run / "05_single_create" / "single_part_upper_link"
    actual = {
        "requirement": _read_json(run / "requirement.json"),
        "requirement_clarification": _read_json(run / "requirement_clarification.json"),
        "requirement_v2": _read_json(run / "requirement_v2.json"),
        "planning_artifact": _read_json(run / "planning_artifact.json"),
        "assembly_plan": _read_json(run / "assembly_plan.json"),
        "part_create_request": _read_json(run / "02_part_request" / "part_create_request.json"),
        "part_request_review": _read_json(run / "03_review" / "part_request_review.json"),
        "reviewed_part_handoff": _read_json(run / "04_handoff" / "reviewed_part_handoff.json"),
        "cad_ir_draft": _read_json(run / "05_single_create" / "cad_ir_draft.json"),
        "input_ir": _read_json(child / "input_ir.json"),
        "report": _read_json(run / "05_single_create" / "report.json"),
        "lineage": _read_json(run / "05_single_create" / "lineage.json"),
        "workflow_review": _read_json(run / "workflow_review.json"),
    }
    expected_files = sorted((EXAMPLE_ROOT / "expected_workflow").rglob("*.expected.summary.json"))
    results = []
    for expected_path in expected_files:
        key = expected_path.name.removesuffix(".expected.summary.json")
        expected = _read_json(expected_path)
        actual_value = actual.get(key)
        if actual_value is None:
            results.append({"stage": expected.get("stage") or key, "artifact": key, "passed": False, "mismatches": [], "missing_artifacts": [key], "unexpected_claims": []})
            continue
        checks = _stable_checks(key, actual_value, expected, mode=mode)
        mismatches = [item for item in checks if not item["passed"]]
        unexpected = _unexpected_claims(key, actual_value)
        results.append({
            "stage": expected.get("stage") or key,
            "artifact": key,
            "passed": not mismatches and not unexpected,
            "mismatches": mismatches,
            "missing_artifacts": [],
            "unexpected_claims": unexpected,
        })
    required_files = [
        run / "requirement.json", run / "requirement_clarification.json", run / "requirement_v2.json",
        run / "planning_artifact.json", run / "assembly_plan.json",
        run / "02_part_request" / "part_create_request.json",
        run / "03_review" / "part_request_review.json",
        run / "04_handoff" / "reviewed_part_handoff.json",
        run / "05_single_create" / "cad_ir_draft.json", child / "input_ir.json",
        run / "05_single_create" / "report.json", run / "05_single_create" / "lineage.json",
        run / "workflow_review.json",
    ]
    if mode == "full":
        required_files.extend([child / "model.step", child / "model.stl", run / "06_part_result_review" / "part_result_review.json"])
    missing = [path.name for path in required_files if not path.exists()]
    return {
        "schema_version": 1,
        "example": "golden_desktop_robot_arm",
        "mode": mode,
        "passed": all(item["passed"] for item in results) and not missing,
        "stages": results,
        "missing_required_artifacts": missing,
    }


def _stable_checks(key: str, value: dict[str, Any], expected: dict[str, Any], *, mode: str) -> list[dict[str, Any]]:
    assembly = value.get("assembly_planning") if isinstance(value.get("assembly_planning"), dict) else {}
    parts = value.get("parts") if isinstance(value.get("parts"), list) else []
    normalization = value.get("source", {}).get("normalization", {}) if isinstance(value.get("source"), dict) else {}
    runtime_route = _nested(value, "route", "selected")
    semantic_route = "assembly_decomposition" if runtime_route == "assembly_loop" else runtime_route
    predicates: dict[str, list[tuple[str, Any, Any]]] = {
        "requirement": [("scope", _nested(value, "intent", "scope") or value.get("scope"), expected.get("scope"))],
        "requirement_clarification": [("answer_count", len(value.get("answers", [])), len(expected.get("answers", {})))],
        "requirement_v2": [("missing_information", value.get("missing_information"), expected.get("missing_information")), ("flow_decision", _nested(value, "requirement_status", "flow_decision", "action"), expected.get("flow_decision"))],
        "planning_artifact": [("route", semantic_route, expected.get("route")), ("primary_candidate", assembly.get("primary_candidate_part"), expected.get("primary_candidate_part"))],
        "assembly_plan": [("candidate_count", sum(1 for part in parts if isinstance(part, dict) and part.get("supported_candidate")), len(expected.get("candidate_parts", []))), ("reference_count", sum(1 for part in parts if isinstance(part, dict) and (part.get("reference_only") is True or part.get("part_status") == "reference_only" or part.get("generation_strategy") == "reference_only")), len(expected.get("reference_components", []))), ("selected", value.get("selected_part_id"), expected.get("selected_candidate"))],
        "part_create_request": [("part_id", value.get("part_id"), expected.get("part_id")), ("status", value.get("status"), expected.get("status"))],
        "part_request_review": [("status", value.get("status"), expected.get("status"))],
        "reviewed_part_handoff": [("part_id", value.get("part_id"), expected.get("part_id")), ("status", value.get("status"), expected.get("status"))],
        "cad_ir_draft": [("source_part_id", value.get("source_part_id"), expected.get("source_part_id")), ("part_type", value.get("part_type"), expected.get("part_type")), ("geometry_family", value.get("geometry_family"), expected.get("geometry_family")), ("normalization_reason", bool(normalization.get("reason")), bool(_nested(expected, "normalization", "reason")))],
        "input_ir": [("source_part_id", value.get("source_part_id"), expected.get("source_part_id")), ("part_type", value.get("part_type"), expected.get("part_type")), ("geometry_family", value.get("geometry_family"), expected.get("geometry_family"))],
        "report": [("concept_scope", value.get("concept_scope"), expected.get("concept_scope")), ("assembly_generated", value.get("assembly_generated"), expected.get("assembly_generated"))],
        "lineage": [("part_id", value.get("part_id"), expected.get("part_id")), ("normalized_part_type", value.get("normalized_part_type"), expected.get("normalized_part_type"))],
        "workflow_review": [("assembly_generated_claim", value.get("assembly_generated", False), expected.get("assembly_generated"))],
    }
    return [{"field": field, "actual": actual, "expected": expected, "passed": actual == expected} for field, actual, expected in predicates.get(key, [])]


def _unexpected_claims(key: str, value: dict[str, Any]) -> list[str]:
    text = json.dumps(value, sort_keys=True).lower()
    claims = []
    if value.get("assembly_generated") is True or value.get("all_parts_generated") is True:
        claims.append("full assembly or all-parts generation claimed")
    if key in {"cad_ir_draft", "input_ir", "report"} and value.get("part_type") == "mounting_plate":
        claims.append("upper_link fell back to mounting_plate")
    if "upper_link_template" in text:
        claims.append("upper_link-specific template claimed")
    return claims


def _write_comparison(run_path: Path, comparison: dict[str, Any]) -> None:
    (run_path / "golden_comparison.json").write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Golden Workflow Comparison", "", f"- Mode: `{comparison['mode']}`", f"- Passed: `{str(comparison['passed']).lower()}`", "", "| Stage | Artifact | Passed | Mismatches | Missing | Unexpected claims |", "|---|---|---:|---|---|---|"]
    for item in comparison["stages"]:
        lines.append(f"| {item['stage']} | {item['artifact']} | {str(item['passed']).lower()} | {len(item['mismatches'])} | {', '.join(item['missing_artifacts']) or '-'} | {', '.join(item['unexpected_claims']) or '-'} |")
    (run_path / "golden_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Workspace path inside the project checkout")
    parser.add_argument("--mode", choices=("contract", "full"), default="contract")
    args = parser.parse_args()
    result = run_golden_workflow(args.workspace, mode=args.mode)
    print(json.dumps({"workspace": result["workspace"], "work_id": result["work_id"], "run_id": result["run_id"], "mode": result["mode"], "passed": result["comparison"]["passed"]}, indent=2))


if __name__ == "__main__":
    main()
