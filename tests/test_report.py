import json
from pathlib import Path

import pytest

from ai_native_cad.report import generate_report


class TestGenerateReport:
    def test_generates_report_json(self, enclosure_lid_model):
        model, spec = enclosure_lid_model
        spec = dict(spec, output_dir="outputs")
        validation = {"valid": True, "checks": [], "bounding_box": {"x": 100, "y": 60, "z": 3},
                      "volume_mm3": 17000}
        files = {"step": "outputs/test/model.step"}
        result = generate_report(model, spec, files, validation, 1.23)
        json_path = Path(result["report_json"])
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert data["part_type"] == "enclosure_lid"
        assert data["status"] == "success"
        assert data["elapsed_seconds"] == 1.23

    def test_generates_report_md(self, enclosure_lid_model):
        model, spec = enclosure_lid_model
        spec = dict(spec, output_dir="outputs")
        validation = {"valid": True, "checks": [], "bounding_box": {"x": 100, "y": 60, "z": 3},
                      "volume_mm3": 17000}
        files = {"step": "outputs/test/model.step"}
        result = generate_report(model, spec, files, validation, 1.23)
        md_path = Path(result["report_md"])
        assert md_path.exists()
        content = md_path.read_text()
        assert "# enclosure_lid Report" in content
        assert "100.0 mm" in content

    def test_failed_status(self, enclosure_lid_model):
        model, spec = enclosure_lid_model
        spec = dict(spec, output_dir="outputs")
        validation = {"valid": False, "checks": [], "errors": ["test error"]}
        files = {}
        result = generate_report(model, spec, files, validation, 0.5)
        json_path = Path(result["report_json"])
        data = json.loads(json_path.read_text())
        assert data["status"] == "failed"

    def test_missing_part_type_raises(self, enclosure_lid_model):
        model, _spec = enclosure_lid_model
        with pytest.raises(ValueError, match="params must include a 'part_type' key"):
            generate_report(model, {}, {}, {"valid": True, "checks": []}, 0.1)

    def test_empty_part_type_raises(self, enclosure_lid_model):
        model, _spec = enclosure_lid_model
        with pytest.raises(ValueError, match="params must include a 'part_type' key"):
            generate_report(model, {"part_type": ""}, {}, {"valid": True, "checks": []}, 0.1)

    def test_report_includes_dimension_checks(self, enclosure_lid_model):
        model, spec = enclosure_lid_model
        spec = dict(spec, output_dir="outputs")
        validation = {
            "valid": True,
            "checks": [
                {"dimension": "length", "expected": 100, "actual": 100.0, "pass": True},
                {"check": "volume_positive", "pass": True},
            ],
            "bounding_box": {"x": 100, "y": 60, "z": 3},
            "volume_mm3": 17000,
        }
        files = {}
        result = generate_report(model, spec, files, validation, 0.1)
        md_content = Path(result["report_md"]).read_text()
        assert "[PASS]" in md_content
