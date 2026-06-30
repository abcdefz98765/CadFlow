import json
from pathlib import Path

from ai_native_cad.benchmarks import load_benchmarks, run_benchmark_suite


def test_load_benchmarks_returns_stable_case_order():
    cases = load_benchmarks()

    ids = [case["id"] for case in cases]
    assert ids == sorted(ids)
    assert "mounting_plate_four_holes" in ids
    assert "mounting_plate_repair_clearance" in ids


def test_benchmark_suite_runs_fixed_ir_cases_and_writes_summary():
    output_root = Path.cwd() / "outputs" / "pytest_benchmarks"

    summary = run_benchmark_suite(output_root=output_root)

    assert summary["status"] == "passed"
    assert summary["total"] == 5
    assert summary["passed"] == 5
    assert summary["failed"] == 0
    summary_path = output_root / "benchmark_summary.json"
    assert summary_path.exists()
    assert json.loads(summary_path.read_text(encoding="utf-8"))["status"] == "passed"

    by_id = {result["id"]: result for result in summary["results"]}
    repair = by_id["mounting_plate_repair_clearance"]
    assert repair["attempts"] == 2
    trace = json.loads((Path(repair["output_dir"]) / "agent_trace.json").read_text(encoding="utf-8"))
    repair_diff = trace["steps"][0]["ir_repair"]["diff"]
    assert any(item["path"] == "features.holes.offset_from_edge" for item in repair_diff)

    plate_report = json.loads((Path(by_id["mounting_plate_four_holes"]["output_dir"]) / "report.json").read_text(encoding="utf-8"))
    assert plate_report["inspection"]["features"]["holes"]["status"] == "verified"
