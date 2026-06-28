import tempfile
from pathlib import Path

import pytest
import cadquery as cq

from ai_native_cad.validator import (
    preflight_design_intent,
    validate_export_files,
    validate_generated_geometry,
    validate_intent_match,
    validate_output,
)


def _geometry_only_spec(spec):
    """Return a copy of spec with outputs cleared (skip file checks)."""
    return dict(spec, outputs=[])


class TestValidateOutput:
    def test_enclosure_base_geometry(self, enclosure_base_model):
        model, spec = enclosure_base_model
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_output(model, Path(tmp), _geometry_only_spec(spec))
            assert result["valid"] is True
            assert result["volume_mm3"] > 0
            bbox = result["bounding_box"]
            assert bbox["x"] == pytest.approx(100.0, abs=0.2)
            assert bbox["y"] == pytest.approx(60.0, abs=0.2)

    def test_enclosure_lid_geometry(self, enclosure_lid_model):
        model, spec = enclosure_lid_model
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_output(model, Path(tmp), _geometry_only_spec(spec))
            assert result["valid"] is True
            assert result["volume_mm3"] > 0
            bbox = result["bounding_box"]
            assert bbox["x"] == pytest.approx(100.0, abs=0.2)
            assert bbox["y"] == pytest.approx(60.0, abs=0.2)
            assert bbox["z"] == pytest.approx(3.0, abs=0.2)

    def test_spacer_geometry(self, spacer_model):
        model, spec = spacer_model
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_output(model, Path(tmp), _geometry_only_spec(spec))
            assert result["valid"] is True
            assert result["volume_mm3"] > 0
            bbox = result["bounding_box"]
            assert bbox["x"] == pytest.approx(12.0, abs=0.2)
            assert bbox["y"] == pytest.approx(12.0, abs=0.2)
            assert bbox["z"] == pytest.approx(20.0, abs=0.2)

    def test_wall_bracket_geometry(self, wall_bracket_model):
        model, spec = wall_bracket_model
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_output(model, Path(tmp), _geometry_only_spec(spec))
            assert result["valid"] is True
            assert result["volume_mm3"] > 0
            bbox = result["bounding_box"]
            assert bbox["y"] == pytest.approx(30.0, abs=0.2)

    def test_dimension_checks_lid(self, enclosure_lid_model):
        model, spec = enclosure_lid_model
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_output(model, Path(tmp), _geometry_only_spec(spec))
            dim_checks = [c for c in result["checks"] if "dimension" in c]
            keys = {c["dimension"] for c in dim_checks}
            assert "length" in keys
            assert "width" in keys
            assert "thickness" in keys
            for c in dim_checks:
                assert c["pass"] is True

    def test_volume_positive_check(self, enclosure_lid_model):
        model, spec = enclosure_lid_model
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_output(model, Path(tmp), _geometry_only_spec(spec))
            vol_checks = [c for c in result["checks"] if c.get("check") == "volume_positive"]
            assert len(vol_checks) == 1
            assert vol_checks[0]["pass"] is True

    def test_file_checks_with_existing_files(self, enclosure_lid_model, tmp_output_dir):
        from ai_native_cad.exporter import export_model

        model, spec = enclosure_lid_model
        export_model(model, tmp_output_dir, ["step", "stl"])
        result = validate_output(model, tmp_output_dir, spec)
        file_checks = [c for c in result["checks"] if "file" in c]
        assert len(file_checks) == 2
        assert all(c["pass"] for c in file_checks)
        assert result["valid"] is True

    def test_file_missing_sets_valid_false(self, enclosure_lid_model, tmp_output_dir):
        model, spec = enclosure_lid_model
        result = validate_output(model, tmp_output_dir, spec)
        assert result["valid"] is False
        file_checks = [c for c in result["checks"] if "file" in c]
        assert all(not c["pass"] for c in file_checks)

    def test_detects_wrong_dimension(self, enclosure_lid_model):
        model, _spec = enclosure_lid_model
        wrong_spec = {"part_type": "enclosure_lid", "dimensions": {"length": 999.0},
                       "outputs": []}
        with tempfile.TemporaryDirectory() as tmp:
            result = validate_output(model, Path(tmp), wrong_spec)
            length_check = [c for c in result["checks"]
                            if c.get("dimension") == "length"]
            assert len(length_check) == 1
            assert length_check[0]["pass"] is False
            assert length_check[0]["expected"] == 999.0
            assert length_check[0]["actual"] == pytest.approx(100.0, abs=0.2)
            assert result["valid"] is False

    def test_preflight_reports_missing_required_feature_fields(self):
        result = preflight_design_intent({
            "part_type": "plate",
            "unit": "mm",
            "dimensions": {"length": 80, "width": 40, "thickness": 4},
            "features": {
                "mount_holes": {
                    "type": "through_hole",
                    "diameter": 4.5,
                }
            },
        })

        assert result["valid"] is False
        assert any(error["code"] == "feature_missing_required_fields" for error in result["errors"])

    def test_geometry_detects_disconnected_solids(self):
        model = cq.Workplane("XY").box(10, 10, 2).union(cq.Workplane("XY").box(2, 2, 2).translate((20, 0, 0)), clean=False)
        result = validate_generated_geometry(model, {"part_type": "disconnected", "dimensions": {}, "outputs": []})

        assert result["valid"] is False
        assert result["solid_count"] == 2
        assert any(check.get("check") == "single_solid" and check.get("pass") is False for check in result["checks"])

    def test_intent_match_marks_unverified_button_features(self, circular_button_model):
        model, spec = circular_button_model
        geometry = validate_generated_geometry(model, _geometry_only_spec(spec))
        result = validate_intent_match(spec, geometry)

        unverified_names = {item["name"] for item in result["unverified"] if item["kind"] == "feature"}
        assert "wire_exit" in unverified_names
        assert "contact_slots" in unverified_names
        assert any(warning["code"] == "intent_items_unverified" for warning in result["warnings"])

    def test_export_file_validator_is_independent(self, enclosure_lid_model, tmp_output_dir):
        model, spec = enclosure_lid_model
        from ai_native_cad.exporter import export_model

        export_model(model, tmp_output_dir, ["step"])
        result = validate_export_files(tmp_output_dir, dict(spec, outputs=["step", "stl"]))

        assert result["valid"] is False
        assert any(check.get("file", "").endswith("model.step") and check["pass"] for check in result["checks"])
        assert any(check.get("file", "").endswith("model.stl") and not check["pass"] for check in result["checks"])
