import pytest

from ai_native_cad.generator import get_part_spec, merge_params


class TestGetPartSpec:
    def test_mounting_plate(self):
        spec = get_part_spec("mounting_plate")
        assert spec["part_type"] == "mounting_plate"
        assert spec["dimensions"]["length"] == 80.0
        assert spec["dimensions"]["width"] == 40.0
        assert spec["dimensions"]["thickness"] == 5.0
        assert spec["features"]["mounting_holes"]["diameter"] == 4.5
        assert spec["check_level"] == "L0"

    def test_circular_button(self):
        spec = get_part_spec("circular_button")
        assert spec["part_type"] == "circular_button"
        assert spec["dimensions"]["body_diameter"] == 92.0
        assert spec["dimensions"]["button_diameter"] == 72.0
        assert spec["features"]["switch_pocket"]["length"] == 7.4
        assert spec["features"]["wire_exit"]["width"] == 8.0
        assert spec["features"]["actuator_post"]["diameter"] == 4.0
        assert spec["check_level"] == "L0"

    def test_enclosure_base(self):
        spec = get_part_spec("enclosure_base")
        assert spec["part_type"] == "enclosure_base"
        assert spec["dimensions"]["outer_length"] == 100.0
        assert spec["dimensions"]["outer_width"] == 60.0
        assert spec["dimensions"]["outer_height"] == 25.0
        assert spec["dimensions"]["wall_thickness"] == 2.0
        assert spec["features"]["bosses"]["diameter"] == 6.0
        assert spec["outputs"] == ["step", "stl"]

    def test_enclosure_lid(self):
        spec = get_part_spec("enclosure_lid")
        assert spec["part_type"] == "enclosure_lid"
        assert spec["dimensions"]["length"] == 100.0
        assert spec["dimensions"]["width"] == 60.0
        assert spec["dimensions"]["thickness"] == 3.0
        assert spec["outputs"] == ["step", "stl"]

    def test_spacer(self):
        spec = get_part_spec("spacer")
        assert spec["part_type"] == "spacer"
        assert spec["dimensions"]["outer_diameter"] == 12.0
        assert spec["dimensions"]["inner_diameter"] == 6.5
        assert spec["dimensions"]["thickness"] == 20.0
        assert spec["outputs"] == ["step", "stl"]

    def test_wall_bracket(self):
        spec = get_part_spec("wall_bracket")
        assert spec["part_type"] == "wall_bracket"
        assert spec["dimensions"]["base_width"] == 30.0
        assert spec["dimensions"]["base_depth"] == 20.0
        assert spec["dimensions"]["wall_height"] == 20.0
        assert spec["dimensions"]["material_thickness"] == 4.0
        assert spec["features"]["wall_hole"]["diameter"] == 4.5
        assert spec["outputs"] == ["step", "stl"]

    def test_unknown_part_type_raises(self):
        with pytest.raises(ValueError, match="Unknown part_type"):
            get_part_spec("nonexistent_part")

    def test_returns_copy_not_reference(self):
        spec1 = get_part_spec("enclosure_lid")
        spec2 = get_part_spec("enclosure_lid")
        spec1["dimensions"]["length"] = 999.0
        assert spec2["dimensions"]["length"] == 100.0


class TestMergeParams:
    def test_shallow_merge(self):
        defaults = {"a": 1, "b": 2}
        overrides = {"b": 99}
        result = merge_params(defaults, overrides)
        assert result == {"a": 1, "b": 99}

    def test_deep_merge(self):
        defaults = {"a": {"x": 1, "y": 2}, "b": 3}
        overrides = {"a": {"y": 99}}
        result = merge_params(defaults, overrides)
        assert result == {"a": {"x": 1, "y": 99}, "b": 3}

    def test_new_key_added(self):
        defaults = {"a": 1}
        overrides = {"b": 2}
        result = merge_params(defaults, overrides)
        assert result == {"a": 1, "b": 2}

    def test_do_not_mutate_defaults(self):
        defaults = {"a": {"x": 1}}
        overrides = {"a": {"x": 99}}
        result = merge_params(defaults, overrides)
        assert defaults["a"]["x"] == 1

    def test_dimension_override(self):
        spec = get_part_spec("enclosure_lid")
        result = merge_params(spec, {"dimensions": {"length": 120.0}})
        assert result["dimensions"]["length"] == 120.0
        assert result["dimensions"]["width"] == 60.0
