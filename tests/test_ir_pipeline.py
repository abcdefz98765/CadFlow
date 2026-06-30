from pathlib import Path
import json

from ai_native_cad.cad_ir import CADIR, ir_from_text, validate_ir
from ai_native_cad.cadquery.generator import generate_cadquery_code
from ai_native_cad.pipeline import run_ir_pipeline


def test_validate_ir_accepts_mounting_plate():
    ir = CADIR.from_dict({
        "part_type": "mounting_plate",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"holes": {"diameter": 5, "positions": "corner_4"}},
    })

    result = validate_ir(ir)

    assert result["valid"] is True


def test_validate_ir_rejects_missing_required_dimension():
    result = validate_ir({
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "thickness": 20},
    })

    assert result["valid"] is False
    assert any(error["code"] == "missing_dimension" and error["dimension"] == "inner_diameter" for error in result["errors"])


def test_text_parser_returns_cad_ir():
    ir = ir_from_text("Generate an 80x40x5 mounting plate with four M4 holes.")

    assert ir.part_type == "mounting_plate"
    assert ir.unit == "mm"
    assert ir.dimensions["length"] == 80.0


def test_cad_ir_from_requirement_ignores_conflicting_source_prompt():
    requirement = {
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
        "outputs": ["step", "stl"],
        "source": {
            "input_text": "Generate an 80x40x5 mounting plate with four M4 holes.",
        },
    }

    ir = CADIR.from_dict(requirement)

    assert ir.part_type == "spacer"
    assert ir.dimensions == {"outer_diameter": 12.0, "inner_diameter": 6.5, "thickness": 20.0}
    assert ir.features == {}
    assert ir.source["input_text"].startswith("Generate an 80x40x5")


def test_cadquery_generation_is_deterministic():
    ir = CADIR.from_dict({
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
    })

    assert generate_cadquery_code(ir) == generate_cadquery_code(ir)


def test_ir_pipeline_writes_required_output_contract():
    ir = {
        "part_type": "spacer",
        "part_name": "pytest_spacer_contract",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
        "outputs": ["step", "stl"],
    }

    output_root = Path.cwd() / "outputs"
    result = run_ir_pipeline(ir, output_root=output_root)

    part_dir = Path(result["output_dir"])
    assert result["status"] == "success"
    assert part_dir == output_root / "pytest_spacer_contract"
    assert (part_dir / "input_ir.json").exists()
    assert (part_dir / "model.py").exists()
    assert (part_dir / "model.step").exists()
    assert (part_dir / "model.stl").exists()
    assert (part_dir / "report.json").exists()
    assert (part_dir / "report.md").exists()
    assert (part_dir / "preview.png").exists()

    report = json.loads((part_dir / "report.json").read_text(encoding="utf-8"))
    assert report["success"] is True
    assert report["ir_valid"] is True
    assert report["execution_success"] is True
    assert result["validation"]["inspection"]["step_file"]["present"] is True
    assert result["validation"]["inspection"]["stl_file"]["present"] is True
    assert result["validation"]["inspection"]["solid_count"] == 1
    assert report["step_generated"] is True
    assert report["stl_generated"] is True
    assert report["inspection"]["artifact_roles"]["primary"] == "model.step"
    assert report["inspection"]["step_file"]["present"] is True
    assert report["inspection"]["step_file"]["size_bytes"] > 0
    assert report["inspection"]["stl_file"]["present"] is True
    assert report["inspection"]["solid_count"] == 1
    assert report["measured_validation_targets"]
    assert report["bounding_box"] == {"x": 12.0, "y": 12.0, "z": 20.0}
    assert report["volume"] > 0
    assert report["warnings"] == []
    assert report["errors"] == []
    assert report["flow_decision"]["action"] == "proceed"
    assert report["flow_decision"]["from_stage"] == "review"
    assert report["flow_decision"]["to_stage"] == "outputs"


def test_ir_pipeline_report_includes_mounting_plate_hole_inspection():
    ir = {
        "part_type": "mounting_plate",
        "part_name": "pytest_mounting_plate_hole_report",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"holes": {"diameter": 5, "positions": "corner_4"}},
        "outputs": ["step", "stl"],
    }

    result = run_ir_pipeline(ir, output_root=Path.cwd() / "outputs")
    part_dir = Path(result["output_dir"])
    report = json.loads((part_dir / "report.json").read_text(encoding="utf-8"))
    report_md = (part_dir / "report.md").read_text(encoding="utf-8")

    holes = report["inspection"]["features"]["holes"]
    assert holes["status"] == "verified"
    assert holes["measured"]["count"] == 4
    assert holes["measured"]["diameter"] == 5.0
    assert holes["spacing"]["status"] == "verified"
    assert holes["spacing"]["measured"]["x"] == 64.0
    assert holes["spacing"]["measured"]["y"] == 24.0
    assert "Holes: verified" in report_md
    assert "Hole spacing: verified" in report_md


def test_ir_pipeline_report_includes_mounting_plate_chamfer_inspection():
    ir = {
        "part_type": "mounting_plate",
        "part_name": "pytest_mounting_plate_chamfer_report",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"chamfer": 1.0},
        "outputs": ["step", "stl"],
    }

    result = run_ir_pipeline(ir, output_root=Path.cwd() / "outputs")
    part_dir = Path(result["output_dir"])
    report = json.loads((part_dir / "report.json").read_text(encoding="utf-8"))
    report_md = (part_dir / "report.md").read_text(encoding="utf-8")

    chamfers = report["inspection"]["features"]["chamfers"]
    targets = {target["target"]: target for target in report["measured_validation_targets"]}
    assert result["status"] == "success"
    assert chamfers["status"] == "verified"
    assert chamfers["measured"]["count"] == 4
    assert chamfers["measured"]["size"] == 1.0
    assert targets["chamfer_count"]["actual"] == 4
    assert targets["chamfer_size"]["actual"] == 1.0
    assert "Chamfers: verified" in report_md
    assert "size 1.000 mm" in report_md
