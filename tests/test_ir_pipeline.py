from pathlib import Path
import json
import struct
import zlib

from ai_native_cad.cad_ir import CADIR, ir_from_text, validate_ir
from ai_native_cad.cadquery.generator import generate_cadquery_code
from ai_native_cad.agents import DesignPlannerFakeAgentAdapter
from ai_native_cad.exporter import export_model
from ai_native_cad.pipeline import run_agent_create_pipeline, run_agent_revision_pipeline, run_ir_pipeline
from ai_native_cad.pipeline import runner as pipeline_runner
from ai_native_cad.pipeline.report import write_pipeline_report
from ai_native_cad.pipeline.validator import validate_pipeline_outputs


def test_validate_ir_accepts_mounting_plate():
    ir = CADIR.from_dict({
        "part_type": "mounting_plate",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"holes": {"diameter": 5, "positions": "corner_4"}},
    })

    result = validate_ir(ir)

    assert result["valid"] is True


def test_validate_ir_accepts_default_unverified_features_without_bypassing_unknown_features():
    accepted = validate_ir({
        "part_type": "enclosure_base",
        "unit": "mm",
        "dimensions": {"outer_length": 100, "outer_width": 60, "outer_height": 25, "wall_thickness": 2},
        "features": {"bosses": {"diameter": 6}, "bottom_cutout": {"length": 60}, "fillet": {"radius": 1}},
    })

    assert accepted["valid"] is True
    assert not accepted["errors"]
    assert {warning["feature"] for warning in accepted["warnings"]} == {"bosses", "bottom_cutout", "fillet"}

    rejected = validate_ir({
        "part_type": "enclosure_base",
        "unit": "mm",
        "dimensions": {"outer_length": 100, "outer_width": 60, "outer_height": 25, "wall_thickness": 2},
        "features": {"snap_tabs": {"count": 2}},
    })

    assert rejected["valid"] is False
    assert any(error["code"] == "unsupported_feature" and error["feature"] == "snap_tabs" for error in rejected["errors"])


def test_validate_ir_rejects_missing_required_dimension():
    result = validate_ir({
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "thickness": 20},
    })

    assert result["valid"] is False
    assert any(error["code"] == "missing_dimension" and error["dimension"] == "inner_diameter" for error in result["errors"])


def test_invalid_ir_clears_untrusted_products_from_reused_output_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    output_dir = tmp_path / "outputs" / "reused_spacer"
    output_dir.mkdir(parents=True)
    for name in ("model.py", "model.step", "model.stl", "preview.png"):
        (output_dir / name).write_text("stale output", encoding="utf-8")

    result = run_ir_pipeline(
        {
            "part_type": "spacer",
            "part_name": "reused_spacer",
            "unit": "mm",
            "dimensions": {"outer_diameter": 12, "thickness": 20},
        },
        output_dir=output_dir,
    )

    assert result["status"] == "failed"
    assert result["validation"]["valid"] is False
    for name in ("model.py", "model.step", "model.stl", "preview.png"):
        assert not (output_dir / name).exists()
    for name in ("input_ir.json", "agent_trace.json", "report.json", "report.md"):
        assert (output_dir / name).exists()


def test_text_parser_returns_cad_ir():
    ir = ir_from_text("Generate an 80x40x5 mounting plate with four M4 holes.")

    assert ir.part_type == "mounting_plate"
    assert ir.unit == "mm"
    assert ir.dimensions["length"] == 80.0


def test_cad_ir_from_requirement_ignores_conflicting_source_prompt():
    requirement = {
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
        "outputs": ["step", "stl"],
        "source": {
            "input_text": "Generate an 80x40x5 mounting plate with four M4 holes.",
        },
    }

    ir = CADIR.from_dict(requirement)

    assert ir.part_type == "spacer"
    assert ir.dimensions == {"outer_diameter": 12.0, "inner_diameter": 6.5, "thickness": 20.0}
    assert ir.features == {}
    assert ir.source["input_text"].startswith("Generate an 80x40x5")


def test_cadquery_generation_is_deterministic():
    ir = CADIR.from_dict({
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
    })

    assert generate_cadquery_code(ir) == generate_cadquery_code(ir)


def test_generated_preview_png_placeholder_is_visible_not_black_pixel():
    namespace = {}
    exec(generate_cadquery_code({
        "part_type": "spacer",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
    }), namespace)

    preview = namespace["_preview_png_bytes"]()
    width, height = struct.unpack(">II", preview[16:24])
    idat_start = preview.index(b"IDAT") + 4
    idat_length = struct.unpack(">I", preview[idat_start - 8:idat_start - 4])[0]
    raw = zlib.decompress(preview[idat_start:idat_start + idat_length])

    assert width == 640
    assert height == 360
    assert b"CadFlow placeholder preview" in preview
    assert raw[1:4] != b"\x00\x00\x00"
    assert raw[1:4] in {bytes((248, 250, 247)), bytes((224, 226, 220))}


def test_ir_pipeline_writes_required_output_contract():
    ir = {
        "part_type": "spacer",
        "part_name": "pytest_spacer_contract",
        "unit": "mm",
        "dimensions": {"outer_diameter": 12, "inner_diameter": 6.5, "thickness": 20},
        "features": {},
        "outputs": ["step", "stl"],
    }

    output_root = Path.cwd() / "outputs"
    result = run_ir_pipeline(ir, output_root=output_root)

    part_dir = Path(result["output_dir"])
    assert result["status"] == "success"
    assert part_dir == output_root / "pytest_spacer_contract"
    assert (part_dir / "input_ir.json").exists()
    assert (part_dir / "model.py").exists()
    assert (part_dir / "model.step").exists()
    assert (part_dir / "model.stl").exists()
    assert (part_dir / "report.json").exists()
    assert (part_dir / "report.md").exists()
    assert (part_dir / "preview.png").exists()

    report = json.loads((part_dir / "report.json").read_text(encoding="utf-8"))
    assert report["success"] is True
    assert report["ir_valid"] is True
    assert report["execution_success"] is True
    assert result["validation"]["inspection"]["step_file"]["present"] is True
    assert result["validation"]["inspection"]["stl_file"]["present"] is True
    assert result["validation"]["inspection"]["solid_count"] == 1
    assert report["step_generated"] is True
    assert report["stl_generated"] is True
    assert report["inspection"]["artifact_roles"]["primary"] == "model.step"
    assert report["inspection"]["step_file"]["present"] is True
    assert report["inspection"]["step_file"]["size_bytes"] > 0
    assert report["inspection"]["stl_file"]["present"] is True
    assert report["inspection"]["solid_count"] == 1
    assert report["measured_validation_targets"]
    assert report["bounding_box"] == {"x": 12.0, "y": 12.0, "z": 20.0}
    assert report["volume"] > 0
    assert report["warnings"] == []
    assert report["errors"] == []
    assert report["flow_decision"]["action"] == "proceed"
    assert report["flow_decision"]["from_stage"] == "review"
    assert report["flow_decision"]["to_stage"] == "outputs"


def test_agent_create_pipeline_writes_planning_artifacts_and_real_cad_output():
    output_dir = Path.cwd() / "outputs" / "pytest_agent_create_mounting_plate"

    result = run_agent_create_pipeline(
        "Make an 80 x 40 x 5 mm mounting plate with four M4 corner holes.",
        DesignPlannerFakeAgentAdapter(),
        output_dir=output_dir,
    )

    assert result["status"] == "success"
    assert result["intent"]["recognized_part_type"] == "mounting_plate"
    assert result["design_brief"]["artifact_type"] == "design_brief"
    assert result["selected_plan"]["candidate_id"] == "A"
    assert result["input_ir"]["part_type"] == "mounting_plate"

    for artifact in (
        "prompt.txt",
        "intent.json",
        "design_brief.json",
        "candidate_plans.json",
        "selected_plan.json",
        "input_ir.json",
        "report.json",
        "report.md",
        "agent_trace.json",
        "model.step",
        "model.stl",
    ):
        assert (output_dir / artifact).exists()

    trace = json.loads((output_dir / "agent_trace.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert trace["agent_create"]["workflow"] == "agent_create"
    assert trace["agent_create"]["selected_candidate"] == "A"
    assert report["agent_create"]["artifacts"]["design_brief"] == "design_brief.json"
    assert result["files"]["intent"] == str(output_dir / "intent.json")


def test_agent_revision_pipeline_patches_parent_ir_and_records_lineage():
    parent_dir = Path.cwd() / "outputs" / "pytest_revision_parent_plate"
    child_dir = Path.cwd() / "outputs" / "pytest_revision_child_plate"
    parent = run_ir_pipeline(
        {
            "part_type": "mounting_plate",
            "part_name": "pytest_revision_parent_plate",
            "unit": "mm",
            "dimensions": {"length": 80, "width": 40, "thickness": 5},
            "features": {"holes": {"diameter": 4.5, "positions": "corner_4"}, "chamfer": {"size": 1}},
            "outputs": ["step", "stl"],
        },
        output_dir=parent_dir,
    )

    result = run_agent_revision_pipeline(
        parent["output_dir"],
        "Make the holes M5, increase thickness to 6 mm, and remove the chamfer.",
        DesignPlannerFakeAgentAdapter(),
        output_dir=child_dir,
    )

    assert result["status"] == "success"
    assert result["input_ir"]["dimensions"]["thickness"] == 6.0
    assert result["input_ir"]["features"]["holes"]["diameter"] == 5.5
    assert "chamfer" not in result["input_ir"]["features"]

    for artifact in (
        "revision_prompt.txt",
        "revision_request.json",
        "change_intent.json",
        "revision_plan.json",
        "patch.json",
        "parent_input_ir.json",
        "parent_report_snapshot.json",
        "parent_agent_trace_snapshot.json",
        "input_ir.json",
        "report.json",
        "agent_trace.json",
        "comparison.json",
        "revision_report.md",
        "lineage.json",
        "model.step",
        "model.stl",
    ):
        assert (child_dir / artifact).exists()

    patch = json.loads((child_dir / "patch.json").read_text(encoding="utf-8"))
    comparison = json.loads((child_dir / "comparison.json").read_text(encoding="utf-8"))
    lineage = json.loads((child_dir / "lineage.json").read_text(encoding="utf-8"))
    trace = json.loads((child_dir / "agent_trace.json").read_text(encoding="utf-8"))
    revision_request = json.loads((child_dir / "revision_request.json").read_text(encoding="utf-8"))
    assert {change["path"] for change in patch["changes"]} == {
        "dimensions.thickness",
        "features.holes.diameter",
        "features.chamfer",
    }
    assert all("before" in change and "after" in change and "reason" in change for change in patch["changes"])
    assert (child_dir / "revision_prompt.txt").read_text(encoding="utf-8").strip().startswith("Make the holes M5")
    assert revision_request["prompt_artifact"] == "revision_prompt.txt"
    assert comparison["parent_run_id"] == parent_dir.name
    assert comparison["child_run_id"] == child_dir.name
    assert {change["path"] for change in comparison["requested_changes"]} == {
        "dimensions.thickness",
        "features.holes.diameter",
        "features.chamfer",
    }
    assert comparison["actual_ir_changes"]
    assert "validation_changes" in comparison
    assert "system_repair_changes" in comparison
    assert lineage["relationship"] == "revision_child"
    assert lineage["root_run_id"] == parent_dir.name
    assert lineage["parent_run_id"] == parent_dir.name
    assert lineage["child_run_id"] == child_dir.name
    assert lineage["revision_index"] == 1
    assert trace["agent_revision"]["stages"][-1] == "record_lineage"
    assert trace["agent_revision"]["revision_index"] == 1


def test_agent_revision_pipeline_blocks_unsupported_prompt_without_model_generation():
    parent_dir = Path.cwd() / "outputs" / "pytest_revision_blocked_parent_plate"
    child_dir = Path.cwd() / "outputs" / "pytest_revision_blocked_child_plate"
    for generated_artifact in ("input_ir.json", "model.py", "model.step", "model.stl"):
        (child_dir / generated_artifact).unlink(missing_ok=True)
    parent = run_ir_pipeline(
        {
            "part_type": "mounting_plate",
            "part_name": "pytest_revision_blocked_parent_plate",
            "unit": "mm",
            "dimensions": {"length": 80, "width": 40, "thickness": 5},
            "features": {"holes": {"diameter": 4.5, "positions": "corner_4"}, "chamfer": {"size": 1}},
            "outputs": ["step", "stl"],
        },
        output_dir=parent_dir,
    )

    result = run_agent_revision_pipeline(
        parent["output_dir"],
        "Make it look more futuristic.",
        DesignPlannerFakeAgentAdapter(),
        output_dir=child_dir,
    )

    assert result["status"] == "blocked"
    assert result["revision_plan"]["status"] == "no_structured_changes"
    assert result["patch"]["changes"] == []

    for artifact in (
        "revision_prompt.txt",
        "revision_request.json",
        "change_intent.json",
        "revision_plan.json",
        "patch.json",
        "parent_input_ir.json",
        "parent_report_snapshot.json",
        "parent_agent_trace_snapshot.json",
        "report.json",
        "report.md",
        "revision_report.md",
        "comparison.json",
        "lineage.json",
        "agent_trace.json",
    ):
        assert (child_dir / artifact).exists()

    for generated_artifact in ("input_ir.json", "model.py", "model.step", "model.stl"):
        assert not (child_dir / generated_artifact).exists()

    comparison = json.loads((child_dir / "comparison.json").read_text(encoding="utf-8"))
    lineage = json.loads((child_dir / "lineage.json").read_text(encoding="utf-8"))
    report = json.loads((child_dir / "report.json").read_text(encoding="utf-8"))
    trace = json.loads((child_dir / "agent_trace.json").read_text(encoding="utf-8"))

    assert comparison["status"] == "blocked"
    assert comparison["requested_changes"] == []
    assert comparison["actual_ir_changes"] == []
    assert lineage["relationship"] == "revision_blocked"
    assert report["status"] == "blocked"
    assert "run_ir_pipeline" not in trace["agent_revision"]["stages"]


def test_agent_revision_pipeline_supports_chained_native_revisions():
    adapter = DesignPlannerFakeAgentAdapter()
    root_dir = Path.cwd() / "outputs" / "pytest_revision_chain_root"
    thickness_dir = Path.cwd() / "outputs" / "pytest_revision_chain_thickness"
    hole_dir = Path.cwd() / "outputs" / "pytest_revision_chain_hole"
    chamfer_dir = Path.cwd() / "outputs" / "pytest_revision_chain_no_chamfer"

    root = run_agent_create_pipeline(
        "Make an 80 x 40 x 5 mm mounting plate with four M4 corner holes and a chamfer.",
        adapter,
        output_dir=root_dir,
    )
    assert root["status"] == "success"
    assert "chamfer" in root["input_ir"]["features"]

    thickness = run_agent_revision_pipeline(
        root["output_dir"],
        "Increase thickness to 6 mm.",
        adapter,
        output_dir=thickness_dir,
    )
    hole = run_agent_revision_pipeline(
        thickness["output_dir"],
        "Change hole diameter to 6 mm.",
        adapter,
        output_dir=hole_dir,
    )
    no_chamfer = run_agent_revision_pipeline(
        hole["output_dir"],
        "Remove the chamfer.",
        adapter,
        output_dir=chamfer_dir,
    )

    assert thickness["input_ir"]["dimensions"]["thickness"] == 6.0
    assert hole["input_ir"]["features"]["holes"]["diameter"] == 6.0
    assert "chamfer" not in no_chamfer["input_ir"]["features"]

    for run_dir, parent_dir, revision_index in (
        (thickness_dir, root_dir, 1),
        (hole_dir, thickness_dir, 2),
        (chamfer_dir, hole_dir, 3),
    ):
        lineage = json.loads((run_dir / "lineage.json").read_text(encoding="utf-8"))
        comparison = json.loads((run_dir / "comparison.json").read_text(encoding="utf-8"))
        assert lineage["root_run_id"] == root_dir.name
        assert lineage["parent_run_id"] == parent_dir.name
        assert lineage["child_run_id"] == run_dir.name
        assert lineage["revision_index"] == revision_index
        assert comparison["requested_changes"]
        assert comparison["actual_ir_changes"]


def test_ir_pipeline_report_includes_mounting_plate_hole_inspection():
    ir = {
        "part_type": "mounting_plate",
        "part_name": "pytest_mounting_plate_hole_report",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"holes": {"diameter": 5, "positions": "corner_4"}},
        "outputs": ["step", "stl"],
    }

    result = run_ir_pipeline(ir, output_root=Path.cwd() / "outputs")
    part_dir = Path(result["output_dir"])
    report = json.loads((part_dir / "report.json").read_text(encoding="utf-8"))
    report_md = (part_dir / "report.md").read_text(encoding="utf-8")

    holes = report["inspection"]["features"]["holes"]
    assert holes["status"] == "verified"
    assert holes["measured"]["count"] == 4
    assert holes["measured"]["diameter"] == 5.0
    assert holes["spacing"]["status"] == "verified"
    assert holes["spacing"]["measured"]["x"] == 64.0
    assert holes["spacing"]["measured"]["y"] == 24.0
    assert "Holes: verified" in report_md
    assert "Hole spacing: verified" in report_md


def test_ir_pipeline_report_includes_mounting_plate_chamfer_inspection():
    ir = {
        "part_type": "mounting_plate",
        "part_name": "pytest_mounting_plate_chamfer_report",
        "unit": "mm",
        "dimensions": {"length": 80, "width": 40, "thickness": 5},
        "features": {"chamfer": 1.0},
        "outputs": ["step", "stl"],
    }

    result = run_ir_pipeline(ir, output_root=Path.cwd() / "outputs")
    part_dir = Path(result["output_dir"])
    report = json.loads((part_dir / "report.json").read_text(encoding="utf-8"))
    report_md = (part_dir / "report.md").read_text(encoding="utf-8")

    chamfers = report["inspection"]["features"]["chamfers"]
    targets = {target["target"]: target for target in report["measured_validation_targets"]}
    assert result["status"] == "success"
    assert chamfers["status"] == "verified"
    assert chamfers["measured"]["count"] == 4
    assert chamfers["measured"]["size"] == 1.0
    assert targets["chamfer_count"]["actual"] == 4
    assert targets["chamfer_count"]["feature"] == "chamfer"
    assert targets["chamfer_count"]["metric"] == "count"
    assert targets["chamfer_count"]["source"] == "geometry_inspector"
    assert targets["chamfer_size"]["actual"] == 1.0
    assert targets["chamfer_size"]["feature"] == "chamfer"
    assert targets["chamfer_size"]["metric"] == "size"
    assert targets["chamfer_size"]["source"] == "geometry_inspector"
    assert "Chamfers: verified" in report_md
    assert "size 1.000 mm" in report_md


def test_ir_pipeline_report_marks_requested_fillet_unverified():
    ir = {
        "part_type": "simple_bracket",
        "part_name": "pytest_simple_bracket_fillet_report",
        "unit": "mm",
        "dimensions": {"base_length": 60, "base_width": 30, "height": 45, "thickness": 4},
        "features": {"fillet": 1.5},
        "outputs": ["step", "stl"],
    }

    result = run_ir_pipeline(ir, output_root=Path.cwd() / "outputs")
    part_dir = Path(result["output_dir"])
    report = json.loads((part_dir / "report.json").read_text(encoding="utf-8"))
    report_md = (part_dir / "report.md").read_text(encoding="utf-8")

    fillets = report["inspection"]["features"]["fillets"]
    assert fillets["status"] == "unverified"
    assert any(
        warning["code"] == "feature_unverified" and warning.get("feature") == "fillet"
        for warning in report["warnings"]
    )
    assert "Fillets: unverified" in report_md


def test_report_marks_unsupported_chamfer_topology_unverified(tmp_path):
    ir = {
        "part_type": "simple_bracket",
        "part_name": "pytest_simple_bracket_unsupported_chamfer_report",
        "unit": "mm",
        "dimensions": {"base_length": 60, "base_width": 30, "height": 45, "thickness": 4},
        "features": {"chamfer": 1.0},
        "outputs": ["step", "stl"],
    }
    namespace = {}
    exec(generate_cadquery_code({**ir, "features": {}}), namespace)
    model = namespace["build_model"]({**ir, "features": {}})
    export_model(model, tmp_path, ["step", "stl"])
    (tmp_path / "report.json").write_text("{}\n", encoding="utf-8")
    validation = validate_pipeline_outputs(model, tmp_path, ir, {"status": "success"})

    write_pipeline_report(
        tmp_path,
        ir,
        {"status": "success"},
        validation,
        {"step": str(tmp_path / "model.step"), "stl": str(tmp_path / "model.stl")},
    )
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    report_md = (tmp_path / "report.md").read_text(encoding="utf-8")

    chamfers = report["inspection"]["features"]["chamfers"]
    assert chamfers["status"] == "unverified"
    assert "plate-like vertical edge chamfers" in chamfers["reason"]
    assert "Chamfers: unverified" in report_md
    assert "plate-like vertical edge chamfers" in report_md
