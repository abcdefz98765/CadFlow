from ai_native_cad.cad_ir import ir_from_text, validate_ir
from ai_native_cad.requirements import RequirementAgent


def test_parser_extracts_mounting_plate_dimensions_and_four_corner_holes():
    requirement = RequirementAgent().parse(
        "Generate an 80x40x5 mm mounting plate with four M4 holes in the corners."
    )

    assert requirement["part_type"] == "mounting_plate"
    assert requirement["dimensions"] == {"length": 80.0, "width": 40.0, "thickness": 5.0}
    assert requirement["features"]["holes"]["count"] == 4
    assert requirement["features"]["holes"]["diameter"] == 4.5
    assert requirement["features"]["holes"]["positions"] == "corner_4"
    assert requirement["missing_information"] == []
    assert validate_ir(ir_from_text("Generate an 80x40x5 mm mounting plate with four M4 holes in the corners."))["valid"]


def test_parser_extracts_spacer_od_id_thickness():
    requirement = RequirementAgent().parse("Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.")

    assert requirement["part_type"] == "spacer"
    assert requirement["dimensions"] == {"outer_diameter": 12.0, "inner_diameter": 6.5, "thickness": 20.0}
    assert requirement["missing_information"] == []
    assert validate_ir(ir_from_text("Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm."))["valid"]


def test_parser_extracts_simple_l_bracket_dimensions():
    requirement = RequirementAgent().parse(
        "Create a simple L-bracket with base length 60 mm, base width 30 mm, height 45 mm, thickness 4 mm."
    )

    assert requirement["part_type"] == "simple_bracket"
    assert requirement["dimensions"] == {
        "base_length": 60.0,
        "base_width": 30.0,
        "height": 45.0,
        "thickness": 4.0,
    }
    assert requirement["missing_information"] == []
    assert validate_ir(ir_from_text(
        "Create a simple L-bracket with base length 60 mm, base width 30 mm, height 45 mm, thickness 4 mm."
    ))["valid"]


def test_parser_extracts_enclosure_base_dimensions_and_wall_thickness():
    requirement = RequirementAgent().parse(
        "Build an enclosure base 100x60x25 mm with wall thickness 2 mm and STEP output."
    )

    assert requirement["part_type"] == "enclosure_base"
    assert requirement["dimensions"] == {
        "outer_length": 100.0,
        "outer_width": 60.0,
        "outer_height": 25.0,
        "wall_thickness": 2.0,
    }
    assert requirement["outputs"] == ["step"]
    assert requirement["missing_information"] == []
    assert validate_ir(ir_from_text("Build an enclosure base 100x60x25 mm with wall thickness 2 mm."))["valid"]


def test_parser_reports_missing_dimensions_without_blocking_l0_template_generation():
    requirement = RequirementAgent().parse("Make a mounting plate.")

    missing_fields = {item["field"] for item in requirement["missing_information"]}
    assert missing_fields == {"dimensions.length", "dimensions.thickness", "dimensions.width"}
    assert {item["category"] for item in requirement["missing_information"]} == {"primary_dimensions"}
    assert all(item["default_used"] is True for item in requirement["missing_information"])
    assert requirement["follow_up_questions"] == []
    assert requirement["follow_up_requests"] == []
    assert requirement["requirement_status"]["complete_for_generation"] is True
    assert requirement["requirement_status"]["needs_user_input"] is False
    assert requirement["requirement_status"]["blocking_fields"] == []
    assert requirement["requirement_status"]["missing_count"] == 3
    assert requirement["requirement_status"]["follow_up_count"] == 0
    assert requirement["assumptions"]
    assert validate_ir(ir_from_text("Make a mounting plate."))["valid"]


def test_parser_marks_missing_dimensions_blocking_for_l1():
    requirement = RequirementAgent().parse("Make a mounting plate.", {"check_level": "L1"})

    assert requirement["requirement_status"]["complete_for_generation"] is False
    assert requirement["requirement_status"]["needs_user_input"] is True
    assert set(requirement["requirement_status"]["blocking_fields"]) == {
        "dimensions.length",
        "dimensions.thickness",
        "dimensions.width",
    }
    assert len(requirement["follow_up_questions"]) == 4
    assert len(requirement["follow_up_requests"]) == 4
    dimension_requests = [
        item for item in requirement["follow_up_requests"] if item["category"] == "primary_dimensions"
    ]
    assert {item["field"] for item in dimension_requests} == {
        "dimensions.length",
        "dimensions.thickness",
        "dimensions.width",
    }
    assert requirement["requirement_status"]["blocking_count"] == 3
    assert requirement["requirement_status"]["follow_up_count"] == 4


def test_parser_extracts_named_dimensions_symbolic_hole_and_edge_offset():
    requirement = RequirementAgent().parse(
        "Make a mounting plate 80 mm long by 40 mm wide and 5 mm thick with four Ø5 holes 8 mm from edge."
    )

    assert requirement["dimensions"] == {"length": 80.0, "width": 40.0, "thickness": 5.0}
    assert requirement["features"]["holes"]["count"] == 4
    assert requirement["features"]["holes"]["diameter"] == 5.0
    assert requirement["features"]["holes"]["offset_from_edge"] == 8.0
    assert requirement["missing_information"] == []
    assert validate_ir(ir_from_text(
        "Make a mounting plate 80 mm long by 40 mm wide and 5 mm thick with four Ø5 holes 8 mm from edge."
    ))["valid"]


def test_parser_reports_conflicting_dimensions_as_missing_information():
    requirement = RequirementAgent().parse("Make an 80x40x5 mm mounting plate with length 90 mm.", {"check_level": "L1"})

    diagnostics = requirement["source"]["parser"]["diagnostics"]
    assert diagnostics[0]["code"] == "conflicting_dimension"
    assert diagnostics[0]["field"] == "dimensions.length"
    assert requirement["missing_information"][0]["category"] == "parser_diagnostic"
    assert requirement["follow_up_requests"][0]["code"] == "conflicting_dimension"
    assert "dimensions.length" in requirement["requirement_status"]["blocking_fields"]
    assert requirement["requirement_status"]["complete_for_generation"] is False


def test_parser_reports_unsupported_inch_units_without_converting():
    requirement = RequirementAgent().parse('Make a 3x2x0.25 inch mounting plate with four holes.', {"check_level": "L1"})

    diagnostics = requirement["source"]["parser"]["diagnostics"]
    assert diagnostics[0]["code"] == "unsupported_unit_in_text"
    assert requirement["source"]["parser"]["extracted_dimensions"] == []
    assert requirement["follow_up_requests"][0]["field"] == "unit"
    assert requirement["follow_up_requests"][0]["category"] == "parser_diagnostic"
    assert "unit" in requirement["requirement_status"]["blocking_fields"]
    assert requirement["requirement_status"]["complete_for_generation"] is False
