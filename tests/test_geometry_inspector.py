import pytest

from ai_native_cad.exporter import export_model
from ai_native_cad.pipeline.geometry_inspector import inspect_geometry


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
