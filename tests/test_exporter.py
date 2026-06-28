import pytest

from ai_native_cad.exporter import export_model


class TestExportModel:
    def test_export_step(self, enclosure_lid_model, tmp_output_dir):
        model, _spec = enclosure_lid_model
        files = export_model(model, tmp_output_dir, ["step"])
        step_path = tmp_output_dir / "model.step"
        assert step_path.exists()
        assert step_path.stat().st_size > 0
        assert files == {"step": str(step_path)}

    def test_export_stl(self, enclosure_lid_model, tmp_output_dir):
        model, _spec = enclosure_lid_model
        files = export_model(model, tmp_output_dir, ["stl"])
        stl_path = tmp_output_dir / "model.stl"
        assert stl_path.exists()
        assert stl_path.stat().st_size > 0
        assert files == {"stl": str(stl_path)}

    def test_export_both(self, enclosure_lid_model, tmp_output_dir):
        model, _spec = enclosure_lid_model
        files = export_model(model, tmp_output_dir, ["step", "stl"])
        assert (tmp_output_dir / "model.step").exists()
        assert (tmp_output_dir / "model.stl").exists()
        assert "step" in files
        assert "stl" in files

    def test_export_all_part_types(self, mounting_plate_model, circular_button_model, enclosure_base_model, enclosure_lid_model,
                                   spacer_model, wall_bracket_model, tmp_output_dir):
        for model, _spec in [mounting_plate_model, circular_button_model, enclosure_base_model, enclosure_lid_model,
                              spacer_model, wall_bracket_model]:
            files = export_model(model, tmp_output_dir, ["step", "stl"])
            step_path = tmp_output_dir / "model.step"
            stl_path = tmp_output_dir / "model.stl"
            assert step_path.exists() and step_path.stat().st_size > 0
            assert stl_path.exists() and stl_path.stat().st_size > 0

    def test_unsupported_format_raises(self, enclosure_lid_model, tmp_output_dir):
        model, _spec = enclosure_lid_model
        with pytest.raises(ValueError, match="Unsupported format"):
            export_model(model, tmp_output_dir, ["obj"])

    def test_case_insensitive_format(self, enclosure_lid_model, tmp_output_dir):
        model, _spec = enclosure_lid_model
        files = export_model(model, tmp_output_dir, ["STEP", "StL"])
        assert "step" in files
        assert "stl" in files
