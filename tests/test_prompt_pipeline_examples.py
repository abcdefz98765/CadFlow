import importlib.util
from pathlib import Path


def _load_prompt_examples_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "prompt_pipeline" / "run_prompt_examples.py"
    spec = importlib.util.spec_from_file_location("prompt_examples", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_prompt_summary_collects_requirement_and_pipeline_debug_fields():
    module = _load_prompt_examples_module()
    requirement = {
        "part_type": "mounting_plate",
        "outputs": ["step", "stl"],
        "requirement_status": {
            "complete_for_generation": True,
            "needs_user_input": False,
            "missing_fields": [],
        },
        "cad_brief": {
            "validation_targets": [
                {"kind": "bounding_box", "expected": {"x": 80.0, "y": 40.0, "z": 5.0}},
                {"kind": "feature", "feature": "holes", "field": "count", "expected": 4},
            ],
        },
    }
    result = {
        "status": "success",
        "output_dir": "outputs/prompt_pipeline/example",
        "agent_trace": {"total_attempts": 1, "final_selected_candidate": "A"},
        "validation": {
            "bounding_box": {"x": 80.0, "y": 40.0, "z": 5.0},
            "measured_validation_targets": [{"target": "bbox"}],
            "inspection": {"features": {"holes": {"status": "verified"}}},
        },
        "files": {"step": "model.step", "report_json": "report.json"},
    }

    summary = module._prompt_summary("example", "Make a plate", requirement, result)
    markdown = module._prompt_summary_markdown(summary)

    assert summary["requirement"]["cad_brief_validation_target_count"] == 2
    assert summary["pipeline"]["attempts"] == 1
    assert summary["pipeline"]["hole_inspection"]["status"] == "verified"
    assert "**CAD Brief targets:** 2" in markdown
    assert "model.step" in markdown
