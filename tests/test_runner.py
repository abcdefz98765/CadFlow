import pytest
from pathlib import Path

from ai_native_cad.runner import load_builder, run_part


class TestLoadBuilder:
    def test_load_mounting_plate(self):
        fn = load_builder("mounting_plate")
        assert callable(fn)

    def test_load_circular_button(self):
        fn = load_builder("circular_button")
        assert callable(fn)

    def test_load_enclosure_base(self):
        fn = load_builder("enclosure_base")
        assert callable(fn)

    def test_load_enclosure_lid(self):
        fn = load_builder("enclosure_lid")
        assert callable(fn)

    def test_load_spacer(self):
        fn = load_builder("spacer")
        assert callable(fn)

    def test_load_wall_bracket(self):
        fn = load_builder("wall_bracket")
        assert callable(fn)

    def test_unknown_part_raises(self):
        with pytest.raises(FileNotFoundError):
            load_builder("nonexistent_part")


class TestRunPart:
    def test_run_mounting_plate(self):
        from ai_native_cad.generator import get_part_spec
        spec = get_part_spec("mounting_plate")
        result = run_part("mounting_plate", spec)
        assert result["status"] == "success"
        assert result["validation"]["valid"] is True

    def test_run_circular_button(self):
        from ai_native_cad.generator import get_part_spec
        spec = get_part_spec("circular_button")
        result = run_part("circular_button", spec)
        assert result["status"] == "success"
        assert result["validation"]["valid"] is True

    def test_run_enclosure_base(self):
        from ai_native_cad.generator import get_part_spec
        spec = get_part_spec("enclosure_base")
        result = run_part("enclosure_base", spec)
        assert result["status"] == "success"
        assert result["validation"]["valid"] is True

    def test_run_enclosure_lid(self):
        from ai_native_cad.generator import get_part_spec
        spec = get_part_spec("enclosure_lid")
        result = run_part("enclosure_lid", spec)
        assert result["status"] == "success"
        assert result["validation"]["valid"] is True

    def test_run_spacer(self):
        from ai_native_cad.generator import get_part_spec
        spec = get_part_spec("spacer")
        result = run_part("spacer", spec)
        assert result["status"] == "success"
        assert result["validation"]["valid"] is True

    def test_run_wall_bracket(self):
        from ai_native_cad.generator import get_part_spec
        spec = get_part_spec("wall_bracket")
        result = run_part("wall_bracket", spec)
        assert result["status"] == "success"
        assert result["validation"]["valid"] is True

    def test_run_part_generates_files(self):
        from pathlib import Path
        from ai_native_cad.generator import get_part_spec

        spec = get_part_spec("enclosure_lid")
        result = run_part("enclosure_lid", spec)
        part_dir = Path(result["output_dir"])
        assert part_dir == Path.cwd() / "outputs" / "enclosure_lid"
        assert (part_dir / "model.step").exists()
        assert (part_dir / "model.stl").exists()
        assert (part_dir / "report.json").exists()

    def test_run_part_respects_output_dir(self, tmp_output_dir):
        from ai_native_cad.generator import get_part_spec

        spec = dict(get_part_spec("spacer"), output_dir=str(tmp_output_dir))
        result = run_part("spacer", spec)
        part_dir = Path.cwd() / "outputs" / "spacer"
        assert result["status"] == "success"
        assert (part_dir / "model.step").exists()
        assert (part_dir / "model.stl").exists()
        assert (part_dir / "report.json").exists()

    def test_run_part_respects_instance_name(self, tmp_output_dir):
        from ai_native_cad.generator import get_part_spec

        spec = dict(get_part_spec("wall_bracket"), output_dir=str(tmp_output_dir), instance_name="wall_bracket_left")
        result = run_part("wall_bracket", spec)
        part_dir = Path.cwd() / "outputs" / "wall_bracket_left"
        assert result["status"] == "success"
        assert (part_dir / "model.step").exists()
        assert (part_dir / "report.json").exists()

    def test_bad_part_type_returns_error(self):
        result = run_part("nonexistent", {})
        assert result["status"] == "error"
        assert "error" in result
