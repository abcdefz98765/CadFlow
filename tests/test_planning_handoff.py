import json
from pathlib import Path

import pytest

from ai_native_cad.cad_ir import ir_from_planning_artifact, validate_ir
from ai_native_cad.cadquery.generator import generate_cadquery_code
from ai_native_cad.pipeline import run_ir_pipeline
from ai_native_cad.planning import PlanningHandoffBlocked, create_planning_artifact
from ai_native_cad.requirements import RequirementAgent
from ai_native_cad.workflow import run_workflow


def test_requirement_to_planning_artifact_field_handoff():
    requirement = RequirementAgent().parse(
        "Generate an 80x40x5 mm mounting plate with four M4 holes in the corners."
    )

    artifact = create_planning_artifact(requirement)

    assert artifact["artifact_type"] == "planning"
    assert artifact["route"]["selected"] == "single_part"
    assert artifact["flow_gate_status"]["status"] == "ready_for_cad_ir"
    assert artifact["flow_gate_status"]["rework_decision"]["action"] == "proceed"
    assert artifact["flow_gate_status"]["rework_decision"]["to_stage"] == "cad_ir"
    assert artifact["functional_datums"][0]["axes"] == {"x": "length", "y": "width", "z": "thickness"}
    assert artifact["interfaces"][0]["name"] == "holes"
    assert artifact["template_candidates"][0]["template"] == "mounting_plate"
    assert artifact["review_targets"] == requirement["cad_brief"]["validation_targets"]

    part = artifact["selected_parts"][0]
    assert part["part_name"] == "mounting_plate"
    assert part["resolved"] is True
    assert part["resolved_decisions"]["part_type"] == requirement["part_type"]
    assert part["resolved_decisions"]["dimensions"] == requirement["dimensions"]
    assert part["resolved_decisions"]["features"] == requirement["features"]
    assert part["resolved_decisions"]["outputs"] == requirement["outputs"]
    assert part["resolved_decisions"]["check_level"] == requirement["check_level"]


def test_planning_artifact_to_input_ir_consumes_resolved_decisions_only():
    requirement = RequirementAgent().parse("Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.")
    artifact = create_planning_artifact(requirement)
    artifact["open_analysis_notes"] = {
        "do_not_consume": "Maybe turn this into a large mounting plate.",
        "dimensions": {"length": 999, "width": 999, "thickness": 999},
    }
    artifact["risk_notes"].append({
        "code": "non_blocking_comment",
        "category": "structural",
        "message": "Open analysis only; not geometry authority.",
        "requires_requirement_confirmation": False,
        "blocks_cad_ir": False,
    })

    ir = ir_from_planning_artifact(artifact)

    assert ir.part_type == "spacer"
    assert ir.dimensions == {"outer_diameter": 12.0, "inner_diameter": 6.5, "thickness": 20.0}
    assert validate_ir(ir)["valid"] is True
    handoff = ir.source["planning_handoff"]
    assert handoff["consumed_fields"] == [
        "part_type",
        "part_name",
        "unit",
        "dimensions",
        "features",
        "outputs",
        "check_level",
    ]
    assert "open_analysis_notes" in handoff["ignored_planning_fields"]


def test_unresolved_topology_risk_blocks_cad_ir_and_returns_to_requirement():
    requirement = RequirementAgent().parse("Make a mounting plate.", {"check_level": "L1"})
    artifact = create_planning_artifact(requirement)

    assert artifact["route"]["selected"] == "confirmation_needed"
    assert artifact["flow_gate_status"]["status"] == "return_to_requirement"
    rework = artifact["flow_gate_status"]["rework_decision"]
    assert rework["action"] == "return"
    assert rework["from_stage"] == "planning"
    assert rework["to_stage"] == "requirement"
    assert artifact["selected_parts"][0]["resolved"] is False
    assert any(reason["code"] == "requirement_incomplete_for_generation" for reason in artifact["flow_gate_status"]["blocking_reasons"])

    with pytest.raises(PlanningHandoffBlocked) as exc_info:
        ir_from_planning_artifact(artifact)

    assert any(error["code"] == "requirement_incomplete_for_generation" for error in exc_info.value.reasons)
    assert any(error.get("category") == "topology" for error in exc_info.value.reasons)


def test_unresolved_interface_risk_blocks_cad_ir_even_when_route_is_selected():
    requirement = RequirementAgent().parse("Make an 80x40x5 mm mounting plate.")
    artifact = create_planning_artifact(requirement)
    artifact["risk_notes"].append({
        "code": "unknown_mating_hole_pattern",
        "category": "interface",
        "message": "Mating hole pattern changes required interfaces.",
        "requires_requirement_confirmation": True,
        "blocks_cad_ir": True,
    })

    with pytest.raises(PlanningHandoffBlocked) as exc_info:
        ir_from_planning_artifact(artifact)

    assert any(error["code"] == "unknown_mating_hole_pattern" for error in exc_info.value.reasons)


def test_part_modeling_uses_cad_ir_not_open_planning_notes(tmp_output_dir):
    requirement = RequirementAgent().parse("Make a spacer washer with OD 12 mm, ID 6.5 mm, thickness 20 mm.")
    artifact = create_planning_artifact(requirement)
    artifact["design_analysis"] = {
        "not_geometry_authority": "A stronger part might use OD 50 mm, but this is unresolved analysis."
    }
    ir = ir_from_planning_artifact(artifact)

    code = generate_cadquery_code(ir)

    assert "outer_diameter" in code
    assert "not_geometry_authority" not in code
    assert '\\"outer_diameter\\": 12.0' in code
    assert ir.dimensions["outer_diameter"] == 12.0

    result = run_ir_pipeline(
        ir,
        output_dir=Path.cwd() / "outputs" / "pytest_planning_part_modeling_contract",
    )
    trace = json.loads((Path(result["output_dir"]) / "agent_trace.json").read_text(encoding="utf-8"))
    assert trace["part_modeling_contract"]["geometry_source"] == "cad_ir"
    assert "part_structure_redesign" in trace["part_modeling_contract"]["does_not_own"]
    assert result["ir"]["dimensions"]["outer_diameter"] == 12.0


def test_invalid_cad_ir_returns_to_planning_before_part_modeling():
    result = run_ir_pipeline(
        {
            "part_type": "spacer",
            "part_name": "pytest_invalid_ir_rework",
            "unit": "mm",
            "dimensions": {"outer_diameter": 12, "thickness": 20},
            "features": {},
            "outputs": ["step", "stl"],
        },
        output_dir=Path.cwd() / "outputs" / "pytest_invalid_ir_rework",
    )

    assert result["status"] == "failed"
    decision = result["flow_decision"]
    assert decision["action"] == "return"
    assert decision["from_stage"] == "cad_ir"
    assert decision["to_stage"] == "planning"
    assert any(reason["code"] == "missing_dimension" for reason in decision["reasons"])

    trace = json.loads((Path(result["output_dir"]) / "agent_trace.json").read_text(encoding="utf-8"))
    assert trace["total_attempts"] == 0
    assert trace["rework_decision"] == decision


def test_legacy_workflow_writes_planning_artifact_without_removing_old_entries(tmp_output_dir):
    result = run_workflow(
        "Generate an 80x40x5 mounting plate with four M4 holes.",
        output_dir=tmp_output_dir / "legacy_workflow_planning_artifact",
    )

    assert (result.output_dir / "requirement.json").exists()
    assert (result.output_dir / "plan.md").exists()
    assert (result.output_dir / "part_spec.json").exists()
    assert (result.output_dir / "planning_artifact.json").exists()
