"""Deterministic benchmark runner for the IR-first CAD pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_native_cad.pipeline.runner import PROJECT_ROOT, run_ir_pipeline

DEFAULT_CASES_DIR = PROJECT_ROOT / "benchmarks" / "cases"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "benchmarks"
REQUIRED_ARTIFACTS = ("input_ir.json", "model.py", "model.step", "model.stl", "report.json", "report.md", "preview.png", "agent_trace.json")


def load_benchmarks(cases_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Load benchmark manifests in deterministic order."""
    root = Path(cases_dir) if cases_dir is not None else DEFAULT_CASES_DIR
    cases = []
    for path in sorted(root.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_manifest_path"] = str(path)
        cases.append(data)
    return cases


def run_benchmark_suite(
    cases_dir: str | Path | None = None,
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    """Run all benchmark manifests and write a compact summary JSON."""
    cases = load_benchmarks(cases_dir)
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    root.mkdir(parents=True, exist_ok=True)

    results = [_run_case(case, root) for case in cases]
    summary = {
        "status": "passed" if all(result["passed"] for result in results) else "failed",
        "total": len(results),
        "passed": sum(1 for result in results if result["passed"]),
        "failed": sum(1 for result in results if not result["passed"]),
        "results": results,
    }
    (root / "benchmark_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def _run_case(case: dict[str, Any], output_root: Path) -> dict[str, Any]:
    case_id = case["id"]
    ir = dict(case["ir"])
    ir["part_name"] = case_id
    pipeline_result = run_ir_pipeline(ir, output_root=output_root)
    output_dir = Path(pipeline_result["output_dir"])
    report = _read_json(output_dir / "report.json")
    trace = _read_json(output_dir / "agent_trace.json")
    failures = _evaluate_case(case, pipeline_result, report, trace, output_dir)
    return {
        "id": case_id,
        "description": case.get("description", ""),
        "output_dir": str(output_dir),
        "status": "passed" if not failures else "failed",
        "passed": not failures,
        "failures": failures,
        "attempts": trace.get("total_attempts"),
        "final_selected_candidate": trace.get("final_selected_candidate"),
    }


def _evaluate_case(
    case: dict[str, Any],
    pipeline_result: dict[str, Any],
    report: dict[str, Any],
    trace: dict[str, Any],
    output_dir: Path,
) -> list[str]:
    expected = case.get("expect", {})
    failures = []

    if expected.get("status", "success") != pipeline_result.get("status"):
        failures.append(f"pipeline status expected {expected.get('status', 'success')}, got {pipeline_result.get('status')}")

    if expected.get("artifacts", True):
        for name in REQUIRED_ARTIFACTS:
            path = output_dir / name
            if not path.exists() or path.stat().st_size <= 0:
                failures.append(f"missing or empty artifact: {name}")

    failures.extend(_check_bounding_box(expected.get("bounding_box", {}), report.get("bounding_box", {})))
    failures.extend(_check_trace(expected.get("trace", {}), trace))
    failures.extend(_check_features(expected.get("features", {}), report.get("inspection", {}).get("features", {})))
    failures.extend(_check_measured_targets(expected.get("measured_targets", []), report.get("measured_validation_targets", [])))
    return failures


def _check_bounding_box(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    tolerance = float(expected.get("tolerance", 0.2) or 0.2)
    failures = []
    for axis in ("x", "y", "z"):
        if axis not in expected:
            continue
        expected_value = float(expected[axis])
        actual_value = actual.get(axis)
        if actual_value is None or abs(float(actual_value) - expected_value) > tolerance:
            failures.append(f"bounding_box.{axis} expected {expected_value}, got {actual_value}")
    return failures


def _check_trace(expected: dict[str, Any], trace: dict[str, Any]) -> list[str]:
    failures = []
    if "max_attempts" in expected and trace.get("max_attempts") != expected["max_attempts"]:
        failures.append(f"trace.max_attempts expected {expected['max_attempts']}, got {trace.get('max_attempts')}")
    if "total_attempts" in expected and trace.get("total_attempts") != expected["total_attempts"]:
        failures.append(f"trace.total_attempts expected {expected['total_attempts']}, got {trace.get('total_attempts')}")
    if expected.get("requires_repair_diff") and not _has_repair_diff(trace, expected.get("repair_diff_path")):
        failures.append(f"trace missing repair diff path: {expected.get('repair_diff_path')}")
    if expected.get("no_repair_diff") and _has_repair_diff(trace, None):
        failures.append("trace should not include repair diff")
    if expected.get("final_inspection_summary") and not trace.get("final_inspection_summary"):
        failures.append("trace missing final inspection summary")
    return failures


def _check_features(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    failures = []
    holes = expected.get("holes")
    if holes:
        actual_holes = actual.get("holes", {})
        if holes.get("status") and actual_holes.get("status") != holes["status"]:
            failures.append(f"features.holes.status expected {holes['status']}, got {actual_holes.get('status')}")
        measured = actual_holes.get("measured") or {}
        if "count" in holes and measured.get("count") != holes["count"]:
            failures.append(f"features.holes.count expected {holes['count']}, got {measured.get('count')}")
        if "diameter" in holes and measured.get("diameter") != holes["diameter"]:
            failures.append(f"features.holes.diameter expected {holes['diameter']}, got {measured.get('diameter')}")
    return failures


def _check_measured_targets(expected: list[str], actual: list[dict[str, Any]]) -> list[str]:
    available = {item.get("target") for item in actual}
    return [f"missing measured target: {target}" for target in expected if target not in available]


def _has_repair_diff(trace: dict[str, Any], path: str | None) -> bool:
    for step in trace.get("steps", []):
        for item in step.get("ir_repair", {}).get("diff", []):
            if path is None or item.get("path") == path:
                return True
    return False


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    summary = run_benchmark_suite()
    print(json.dumps(summary, indent=2))
    if summary["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
