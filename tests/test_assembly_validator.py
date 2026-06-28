import json
from pathlib import Path

from ai_native_cad.assembly_planner import create_assembly_configs, create_assembly_plan, write_assembly_plan
from ai_native_cad.assembly_validator import validate_assembly


def _write_part(root: Path, name: str, bbox: dict, *, solid_count: int = 1):
    part_dir = root / "outputs" / name
    part_dir.mkdir(parents=True)
    (part_dir / "model.step").write_text("dummy step")
    report = {
        "part_type": name,
        "status": "success",
        "validation": {
            "valid": True,
            "bounding_box": bbox,
            "solid_count": solid_count,
            "checks": [],
        },
    }
    (part_dir / "report.json").write_text(json.dumps(report))
    return f"outputs/{name}/model.step"


def _box(x=10, y=10, z=5):
    return {"xmin": -x / 2, "xmax": x / 2, "ymin": -y / 2, "ymax": y / 2, "zmin": 0, "zmax": z}


def test_validate_stacked_contact_passes(tmp_path):
    base_step = _write_part(tmp_path, "base", _box(z=5))
    lid_step = _write_part(tmp_path, "lid", _box(z=2))
    config = {
        "name": "stacked",
        "output_dir": "outputs/stacked",
        "validation": {
            "anchors": ["base"],
            "required_contacts": [{"part1": "lid", "part2": "base", "axis": "z", "intent": "lid sits on base"}],
        },
        "parts": [
            {"name": "base", "step": base_step, "position": [0, 0, 0]},
            {"name": "lid", "step": lid_step, "position": [0, 0, 5]},
        ],
    }

    result = validate_assembly(config, tmp_path)

    assert result["status"] == "success"
    assert result["errors"] == []
    assert result["contacts"][0]["axis"] == "z"
    assert result["stages"]["preflight_assembly_intent"]["status"] == "success"
    assert result["stages"]["validate_part_inputs"]["status"] == "success"
    assert result["stages"]["validate_placement_relationships"]["status"] == "success"
    assert result["stages"]["validate_constraints"]["status"] == "success"
    assert result["stages"]["validate_assembly_exports"]["status"] == "success"
    assert (tmp_path / "outputs" / "stacked" / "assembly_validation.json").exists()
    assert (tmp_path / "outputs" / "stacked" / "assembly_validation.md").exists()
    assert (tmp_path / "outputs" / "stacked" / "assembly_review.md").exists()


def test_missing_report_fails(tmp_path):
    part_dir = tmp_path / "outputs" / "part"
    part_dir.mkdir(parents=True)
    (part_dir / "model.step").write_text("dummy step")
    config = {
        "name": "missing_report",
        "output_dir": "outputs/missing_report",
        "parts": [{"name": "part", "step": "outputs/part/model.step"}],
    }

    result = validate_assembly(config, tmp_path)

    assert result["status"] == "failed"
    assert result["errors"][0]["code"] == "missing_report"


def test_floating_part_fails(tmp_path):
    base_step = _write_part(tmp_path, "base", _box(z=5))
    floating_step = _write_part(tmp_path, "floating", _box(z=2))
    config = {
        "name": "floating",
        "output_dir": "outputs/floating_check",
        "validation": {"anchors": ["base"]},
        "parts": [
            {"name": "base", "step": base_step, "position": [0, 0, 0]},
            {"name": "floating", "step": floating_step, "position": [100, 0, 0]},
        ],
    }

    result = validate_assembly(config, tmp_path)

    assert result["status"] == "failed"
    assert any(error["code"] == "floating_part" for error in result["errors"])


def test_required_contact_fails_when_gap_is_wrong(tmp_path):
    base_step = _write_part(tmp_path, "base", _box(z=5))
    lid_step = _write_part(tmp_path, "lid", _box(z=2))
    config = {
        "name": "bad_contact",
        "output_dir": "outputs/bad_contact",
        "validation": {"required_contacts": [{"part1": "lid", "part2": "base", "axis": "z"}]},
        "parts": [
            {"name": "base", "step": base_step, "position": [0, 0, 0]},
            {"name": "lid", "step": lid_step, "position": [0, 0, 8]},
        ],
    }

    result = validate_assembly(config, tmp_path)

    assert result["status"] == "failed"
    assert any(error["code"] == "required_contact_failed" for error in result["errors"])


def test_multi_solid_part_fails(tmp_path):
    step = _write_part(tmp_path, "bad_part", _box(), solid_count=2)
    config = {
        "name": "multi_solid",
        "output_dir": "outputs/multi_solid",
        "parts": [{"name": "bad_part", "step": step}],
    }

    result = validate_assembly(config, tmp_path)

    assert result["status"] == "failed"
    assert any(error["code"] == "multi_solid_part" for error in result["errors"])


def test_allowed_bbox_overlap_is_not_possible_interference(tmp_path):
    box_a = _write_part(tmp_path, "container", _box(x=20, y=20, z=20))
    box_b = _write_part(tmp_path, "inside", _box(x=5, y=5, z=5))
    config = {
        "name": "allowed_overlap",
        "output_dir": "outputs/allowed_overlap",
        "validation": {
            "allowed_bbox_overlaps": [{"part1": "container", "part2": "inside", "reason": "inside is contained"}]
        },
        "parts": [
            {"name": "container", "step": box_a},
            {"name": "inside", "step": box_b, "position": [0, 0, 5]},
        ],
    }

    result = validate_assembly(config, tmp_path)

    assert result["possible_interferences"] == []


def test_validation_rules_warn_without_reason_or_intent(tmp_path):
    base_step = _write_part(tmp_path, "base", _box(z=5))
    lid_step = _write_part(tmp_path, "lid", _box(z=2))
    config = {
        "name": "missing_intent",
        "output_dir": "outputs/missing_intent",
        "validation": {
            "anchors": ["base"],
            "required_contacts": [{"part1": "lid", "part2": "base", "axis": "z"}],
            "allowed_bbox_overlaps": [{"part1": "base", "part2": "lid"}],
        },
        "parts": [
            {"name": "base", "step": base_step, "position": [0, 0, 0]},
            {"name": "lid", "step": lid_step, "position": [0, 0, 5]},
        ],
    }

    result = validate_assembly(config, tmp_path)

    assert result["status"] == "warning"
    codes = {warning["code"] for warning in result["warnings"]}
    assert "required_contact_missing_intent" in codes
    assert "validation_rule_missing_reason" in codes


def test_pet_button_assembly_plan_needs_confirmation_for_missing_high_risk_fields(tmp_path):
    requirement = {
        "name": "pet_button",
        "check_level": "L0",
        "features": {"wire_exit": {"direction": "side"}},
        "intent": {"scope": "assembly", "use_case": "pet communication button"},
    }
    parts = [
        {"name": "pet_button_base", "assembly_role": "base"},
        {"name": "pet_button_cap", "assembly_role": "moving_actuator"},
        {"name": "pet_button_tactile_switch", "kind": "reference", "assembly_role": "switch_reference"},
    ]

    plan = create_assembly_plan(requirement, parts)
    files = write_assembly_plan(plan, tmp_path)

    assert plan["status"] == "confirmation_needed"
    assert plan["confirmation_gate"]["needs_user_confirmation"] is True
    assert "switch" in plan["confirmation_gate"]["high_risk_topics"]
    assert any("switch_envelope" in q for q in plan["confirmation_gate"]["unresolved_questions"])
    assert Path(files["assembly_plan_json"]).exists()
    assert Path(files["assembly_plan_md"]).exists()


def test_pet_button_assembly_plan_generates_backend_neutral_configs(tmp_path):
    requirement = {
        "name": "pet_button",
        "check_level": "L0",
        "features": {
            "switch_envelope": {"x": 6, "y": 6, "z": 5},
            "cap_travel": 1.2,
            "wire_exit": {"direction": "side"},
        },
        "assembly": {"fastening_method": "snap"},
    }
    parts = [
        {"name": "pet_button_base", "assembly_role": "base"},
        {"name": "pet_button_switch_plate", "assembly_role": "carrier"},
        {"name": "pet_button_tactile_switch", "kind": "reference", "assembly_role": "switch_reference"},
        {"name": "pet_button_cap", "assembly_role": "moving_actuator"},
    ]
    plan = create_assembly_plan(requirement, parts)
    configs = create_assembly_configs(
        plan,
        [
            {"name": "pet_button_base", "step": "parts/pet_button_base/model.step"},
            {"name": "pet_button_switch_plate", "step": "parts/pet_button_switch_plate/model.step", "position": [0, 0, 2]},
            {"name": "pet_button_tactile_switch", "step": "parts/pet_button_tactile_switch/model.step", "position": [0, 0, 4]},
            {"name": "pet_button_cap", "step": "parts/pet_button_cap/model.step", "position": [0, 0, 16]},
        ],
        tmp_path,
    )

    assert plan["status"] == "ready_for_assembly_config"
    assert plan["confirmation_gate"]["needs_user_confirmation"] is False
    assert (tmp_path / "assembly.json").exists()
    assert (tmp_path / "constraint_assembly.json").exists()
    assert configs["assembly"]["validation"]["required_contacts"][0]["part1"] == "pet_button_switch_plate"
    assert configs["constraint_assembly"]["constraints"][0]["type"] == "fixed"
