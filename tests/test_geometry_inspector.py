import pytest

from ai_native_cad.exporter import export_model
from ai_native_cad.cadquery.generator import generate_cadquery_code
from ai_native_cad.pipeline.geometry_inspector import inspect_geometry
from ai_native_cad.pipeline.validator import validate_pipeline_outputs


def _build_generated_model(ir):
    namespace = {}
    exec(generate_cadquery_code(ir), namespace)
    return namespace["build_model"](ir)


def test_inspector_returns_step_stl_facts_for_successful_spacer(spacer_model, tmp_output_dir):
    model, spec = spacer_model
    export_model(model, tmp_output_dir, ["step", "stl"])

    result = inspect_geometry(model, tmp_output_dir, spec)

    assert result["artifact_roles"]["primary"] == "model.step"
    assert result["step_file"]["present"] is True
    assert result["step_file"]["size_bytes"] > 0
    assert result["step_file"]["role"] == "primary_cad_artifact"
    assert result["stl_file"]["present"] is True
    assert result["stl_file"]["size_bytes"] > 0
    assert result["stl_file"]["role"] == "derived_mesh_output"
    assert result["solid_count"] == 1
    assert result["bounding_box"]["x"] == pytest.approx(12.0, abs=0.01)
    assert result["bounding_box"]["y"] == pytest.approx(12.0, abs=0.01)
    assert result["bounding_box"]["z"] == pytest.approx(20.0, abs=0.01)
    assert result["volume"] > 0
    assert result["features"]["holes"]["status"] == "scaffold"


def test_inspector_verifies_four_corner_holes_for_mounting_plate(tmp_output_dir):
    ir = {
        "part_type": "mounting_plate",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"holes": {"diameter": 5, "positions": "corner_4"}},
    }
    model = _build_generated_model(ir)
    export_model(model, tmp_output_dir, ["step", "stl"])

    result = inspect_geometry(model, tmp_output_dir, ir)

    holes = result["features"]["holes"]
    assert holes["status"] == "verified"
    assert holes["expected"]["count"] == 4
    assert holes["expected"]["diameter"] == 5.0
    assert holes["expected"]["centers"] == [[-32.0, -12.0], [-32.0, 12.0], [32.0, -12.0], [32.0, 12.0]]
    assert holes["expected"]["spacing_x"] == 64.0
    assert holes["expected"]["spacing_y"] == 24.0
    assert holes["measured"]["count"] == 4
    assert holes["measured"]["diameter"] == pytest.approx(5.0, abs=0.01)
    expected_centers = [[-32.0, -12.0, 2.5], [-32.0, 12.0, 2.5], [32.0, -12.0, 2.5], [32.0, 12.0, 2.5]]
    for actual, expected in zip(holes["measured"]["centers"], expected_centers):
        assert actual == pytest.approx(expected, abs=0.01)
    assert holes["spacing"]["status"] == "verified"
    assert holes["spacing"]["measured"]["x"] == pytest.approx(64.0, abs=0.01)
    assert holes["spacing"]["measured"]["y"] == pytest.approx(24.0, abs=0.01)


def test_validator_adds_verified_hole_targets_for_mounting_plate(tmp_output_dir):
    ir = {
        "part_type": "mounting_plate",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"holes": {"diameter": 5, "positions": "corner_4"}},
    }
    model = _build_generated_model(ir)
    export_model(model, tmp_output_dir, ["step", "stl"])
    (tmp_output_dir / "report.json").write_text("{}\n", encoding="utf-8")

    result = validate_pipeline_outputs(model, tmp_output_dir, ir, {"status": "success"})

    assert result["valid"] is True
    assert result["inspection"]["features"]["holes"]["status"] == "verified"
    targets = {target["target"]: target for target in result["measured_validation_targets"]}
    assert targets["hole_count"]["actual"] == 4
    assert targets["hole_count"]["pass"] is True
    assert targets["hole_diameter"]["actual"] == pytest.approx(5.0, abs=0.01)
    assert targets["hole_diameter"]["pass"] is True
    assert targets["hole_spacing_x"]["actual"] == pytest.approx(64.0, abs=0.01)
    assert targets["hole_spacing_x"]["pass"] is True
    assert targets["hole_spacing_y"]["actual"] == pytest.approx(24.0, abs=0.01)
    assert targets["hole_spacing_y"]["pass"] is True


def test_validator_fails_when_expected_mounting_plate_holes_are_missing(tmp_output_dir):
    ir = {
        "part_type": "mounting_plate",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"holes": {"diameter": 5, "positions": "corner_4"}},
    }
    model = _build_generated_model({**ir, "features": {}})
    export_model(model, tmp_output_dir, ["step", "stl"])
    (tmp_output_dir / "report.json").write_text("{}\n", encoding="utf-8")

    result = validate_pipeline_outputs(model, tmp_output_dir, ir, {"status": "success"})

    assert result["valid"] is False
    assert result["inspection"]["features"]["holes"]["status"] == "failed"
    assert result["inspection"]["features"]["holes"]["measured"]["count"] == 0
    assert any(error["code"] == "missing_feature" and error.get("feature") == "holes" for error in result["errors"])


def test_validator_fails_when_mounting_plate_holes_have_wrong_spacing(tmp_output_dir):
    expected_ir = {
        "part_type": "mounting_plate",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"holes": {"diameter": 5, "positions": "corner_4"}},
    }
    wrong_position_ir = {
        **expected_ir,
        "features": {"holes": {"diameter": 5, "positions": [[-20, -8], [-20, 8], [20, -8], [20, 8]]}},
    }
    model = _build_generated_model(wrong_position_ir)
    export_model(model, tmp_output_dir, ["step", "stl"])
    (tmp_output_dir / "report.json").write_text("{}\n", encoding="utf-8")

    result = validate_pipeline_outputs(model, tmp_output_dir, expected_ir, {"status": "success"})

    holes = result["inspection"]["features"]["holes"]
    targets = {target["target"]: target for target in result["measured_validation_targets"]}
    assert result["valid"] is False
    assert holes["status"] == "failed"
    assert holes["spacing"]["status"] == "failed"
    assert targets["hole_spacing_x"]["expected"] == 64.0
    assert targets["hole_spacing_x"]["actual"] == pytest.approx(40.0, abs=0.01)
    assert targets["hole_spacing_x"]["pass"] is False
    assert targets["hole_spacing_y"]["expected"] == 24.0
    assert targets["hole_spacing_y"]["actual"] == pytest.approx(16.0, abs=0.01)
    assert targets["hole_spacing_y"]["pass"] is False
    assert any(error["code"] == "hole_spacing_mismatch" for error in result["errors"])
