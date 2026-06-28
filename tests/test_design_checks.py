from ai_native_cad.design_checks import validate_design_intent


def test_feature_template_requires_fields():
    result = validate_design_intent({
        "part_type": "plate",
        "dimensions": {"length": 80, "width": 40, "thickness": 4},
        "features": {
            "mount_holes": {
                "type": "counterbore_hole",
                "diameter": 4.5,
                "positions": [(0, 0)],
            }
        },
    })

    assert result["valid"] is False
    assert any(error["code"] == "feature_missing_required_fields" for error in result["errors"])


def test_design_checks_warn_for_tight_hole_edge_clearance():
    result = validate_design_intent({
        "part_type": "plate",
        "dimensions": {"length": 80, "width": 40, "thickness": 4},
        "features": {
            "mount_holes": {
                "diameter": 8,
                "offset_from_edge": 6,
            }
        },
    })

    assert result["valid"] is True
    assert any(warning["code"] == "hole_near_edge" for warning in result["warnings"])


def test_design_checks_warn_for_fastener_clearance():
    result = validate_design_intent({
        "part_type": "plate",
        "dimensions": {"length": 80, "width": 40, "thickness": 4},
        "features": {
            "mount_holes": {
                "diameter": 3.2,
                "fastener": "M4",
            }
        },
    })

    assert result["valid"] is True
    assert any(warning["code"] == "fastener_clearance_tight" for warning in result["warnings"])


def test_design_checks_fail_for_too_thin_wall():
    result = validate_design_intent({
        "part_type": "shell",
        "dimensions": {"outer_length": 80, "outer_width": 40, "outer_height": 20, "wall_thickness": 0.6},
        "manufacturing": {"min_wall_thickness": 1.2},
    })

    assert result["valid"] is False
    assert any(error["code"] == "wall_too_thin" for error in result["errors"])


def test_design_checks_warn_when_assembly_role_lacks_mating_faces():
    result = validate_design_intent({
        "part_type": "lid",
        "assembly_role": "cover",
        "dimensions": {"length": 80, "width": 40, "thickness": 3},
        "features": {},
    })

    assert result["valid"] is True
    assert any(warning["code"] == "assembly_role_without_mating_faces" for warning in result["warnings"])
