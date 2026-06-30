import json
from pathlib import Path

from ai_native_cad.cad_ir.repair import repair_ir
from ai_native_cad.cadquery.generator import generate_cadquery_candidates
from ai_native_cad.pipeline import run_ir_pipeline
from ai_native_cad.pipeline.failure_analyzer import analyze_failure
from ai_native_cad.pipeline.scorer import score_candidate


def test_candidate_generator_emits_multiple_profiles_for_hole_plate():
    ir = {
        "part_type": "mounting_plate",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"holes": {"diameter": 5, "positions": "corner_4"}},
    }

    candidates = generate_cadquery_candidates(ir, max_candidates=3)

    assert [candidate["candidate"] for candidate in candidates] == ["A", "B", "C"]
    assert {candidate["strategy"] for candidate in candidates} == {"conservative", "optimized", "fallback_simplified"}


def test_failure_analyzer_returns_structured_ir_fix():
    result = analyze_failure(
        {"status": "error", "stderr": "BOPAlgo boolean cut failed while creating holes"},
        {"errors": []},
    )

    assert result["failure_type"] == "execution_failure"
    assert result["root_cause"] == "boolean_operation_failed"
    assert result["affected_feature"] == "holes"
    assert result["suggested_ir_fix"] == {"modify": "hole_positions", "strategy": "increase_spacing"}


def test_repair_ir_preserves_part_type_and_repairs_hole_spacing():
    ir = {
        "part_type": "mounting_plate",
        "unit": "mm",
        "dimensions": {"length": 30, "width": 20, "thickness": 4},
        "features": {"holes": {"diameter": 8, "positions": "corner_4", "offset_from_edge": 1}},
    }

    result = repair_ir(ir, {"affected_feature": "holes", "suggested_ir_fix": {"strategy": "increase_spacing"}})

    assert result["repaired_ir"]["part_type"] == "mounting_plate"
    assert result["repaired_ir"]["features"]["holes"]["offset_from_edge"] > 1
    assert "adjusted hole spacing" in result["changes"]


def test_score_candidate_prefers_valid_geometry():
    valid = score_candidate("A", {"valid": True, "step_generated": True, "stl_generated": True, "volume": 1, "checks": [{"pass": True}]}, {"status": "success"})
    invalid = score_candidate("B", {"valid": False, "step_generated": False, "stl_generated": False, "volume": 0, "checks": [{"pass": False}]}, {"status": "error"})

    assert valid["score"] > invalid["score"]


def test_agent_loop_repairs_failed_hole_clearance_and_writes_trace():
    ir = {
        "part_type": "mounting_plate",
        "part_name": "pytest_agent_loop_repair",
        "unit": "mm",
        "dimensions": {"length": 30, "width": 20, "thickness": 4},
        "features": {"holes": {"diameter": 8, "positions": "corner_4", "offset_from_edge": 1}},
        "outputs": ["step", "stl"],
    }

    result = run_ir_pipeline(ir, output_root=Path.cwd() / "outputs")
    output_dir = Path(result["output_dir"])
    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert trace["total_attempts"] == 2
    assert trace["steps"][0]["status"] == "failed"
    assert trace["steps"][0]["reason"] == "feature_not_realized"
    assert trace["steps"][1]["status"] == "success"
    assert trace["final_selected_candidate"] in {"A", "B"}
    assert trace["steps"][1]["inspection_summary"]["step_file"]["present"] is True
    assert trace["steps"][1]["inspection_summary"]["solid_count"] == 1
    assert trace["steps"][1]["inspection_summary"]["features"]["holes"]["status"] == "verified"
    assert trace["steps"][1]["inspection_summary"]["hole_spacing_status"] == "verified"
    assert trace["steps"][1]["measured_validation_targets"]
    assert trace["final_inspection_summary"]["step_file"]["present"] is True
    assert trace["final_inspection_summary"]["stl_file"]["present"] is True
    assert trace["final_inspection_summary"]["features"]["holes"]["status"] == "verified"
    assert trace["final_inspection_summary"]["hole_spacing_status"] == "verified"
    assert trace["final_measured_validation_targets"]
    assert (output_dir / "model.py").exists()
    assert (output_dir / "model.step").exists()
    assert (output_dir / "model.stl").exists()
    assert (output_dir / "preview.png").exists()
    assert (output_dir / "report.json").exists()
    assert (output_dir / "report.md").exists()
