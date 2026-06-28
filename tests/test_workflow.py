from pathlib import Path

from ai_native_cad.requirements import RequirementAgent
from ai_native_cad.workflow import CHECK_LEVELS, run_workflow


def test_workflow_mounting_plate_outputs(tmp_output_dir):
    result = run_workflow(
        "Generate an 80x40x5 mounting plate with four M4 holes.",
        output_dir=tmp_output_dir / "mounting_plate_workflow",
    )

    assert result.status == "success"
    root = result.output_dir
    assert (root / "input.md").exists()
    assert (root / "requirement.json").exists()
    assert (root / "part_spec.json").exists()
    assert (root / "plan.md").exists()
    assert (root / "model.py").exists()
    assert (root / "review.md").exists()
    assert (root / "exports" / "model.step").exists()
    assert (root / "exports" / "model.stl").exists()
    assert (root / "logs" / "run.log").exists()
    assert (root / "logs" / "generation.json").exists()

    review = Path(result.review_path).read_text(encoding="utf-8")
    assert "Generation Loop" in review
    assert "Intent Match" in review


def test_workflow_l1_report_scaffold(tmp_output_dir):
    result = run_workflow(
        "Generate a maker mounting plate.",
        output_dir=tmp_output_dir / "maker_plate",
        overrides={"check_level": "L1"},
    )
    review = Path(result.review_path).read_text(encoding="utf-8")
    assert result.requirement["check_level"] == "L1"
    assert "L1 Maker Scaffold" in review


def test_workflow_detects_button_part(tmp_output_dir):
    result = run_workflow(
        "Create a circular button with a tactile switch pocket and wire outlet.",
        output_dir=tmp_output_dir / "button_workflow",
    )
    assert result.status == "success"
    assert result.requirement["part_type"] == "circular_button"
    assert result.requirement["intent"]["use_case"] == "unspecified"
    assert (result.output_dir / "exports" / "model.step").exists()


def test_check_levels_reserved():
    assert CHECK_LEVELS["L0"] == "Playground"
    assert CHECK_LEVELS["L4"] == "Safety Critical"


def test_requirement_agent_records_missing_l1_fields():
    requirement = RequirementAgent().parse(
        "Generate a maker mounting plate.",
        overrides={"check_level": "L1"},
    )

    assert requirement["field_policy"]["check_level"] == "L1"
    assert requirement["requirement_status"]["needs_user_input"] is True
    assert "manufacturing_process" in {item["field"] for item in requirement["missing_information"]}
    assert requirement["follow_up_questions"]
