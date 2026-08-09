import json
import os
from pathlib import Path

import pytest

from ai_native_cad.cadquery import executor as cadquery_executor
from ai_native_cad.pipeline import runner as pipeline_runner
from ai_native_cad.examples import golden_desktop_robot_arm as golden_service
from ai_native_cad.workflow_console import WorkflowConsoleBackend


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_golden_desktop_robot_arm.py"


def _module():
    return golden_service


def _run_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    module = _module()
    workspace = tmp_path / "workspace"
    result = module.run_golden_workflow(workspace, mode="contract", project_root=tmp_path)
    run = workspace / "works" / module.WORK_ID / "runs" / module.RUN_ID
    return module, workspace, run, result


def test_executable_golden_contract_creates_real_work_and_required_artifacts(tmp_path, monkeypatch):
    module, workspace, run, result = _run_contract(tmp_path, monkeypatch)

    manifest = json.loads((workspace / "works" / module.WORK_ID / "work_manifest.json").read_text(encoding="utf-8"))
    assert manifest["title"] == "Golden Desktop Robot Arm"
    assert manifest["root_run_id"] == module.RUN_ID
    assert manifest["active_lineage"]["active_root_run_id"] == module.RUN_ID
    assert manifest["active_lineage"]["accepted_run_ids"] == [module.RUN_ID]
    for relative in (
        "requirement.json",
        "requirement_clarification.json",
        "requirement_v2.json",
        "planning_artifact.json",
        "assembly_plan.json",
        "02_part_request/part_create_request.json",
        "03_review/part_request_review.json",
        "04_handoff/reviewed_part_handoff.json",
        "05_single_create/cad_ir_draft.json",
        "05_single_create/single_part_upper_link/input_ir.json",
        "05_single_create/report.json",
        "05_single_create/lineage.json",
        "workflow_review.json",
        "golden_comparison.json",
        "golden_comparison.md",
    ):
        assert (run / relative).exists(), relative
    assert result["comparison"]["passed"] is True


def test_executable_golden_contract_uses_generic_ir_without_assembly_claim(tmp_path, monkeypatch):
    _, _, run, _ = _run_contract(tmp_path, monkeypatch)
    draft = json.loads((run / "05_single_create/cad_ir_draft.json").read_text(encoding="utf-8"))
    report = json.loads((run / "05_single_create/report.json").read_text(encoding="utf-8"))

    assert draft["source_part_id"] == "upper_link"
    assert draft["part_type"] == "link_like_part"
    assert draft["geometry_family"] == "elongated_plate_with_end_holes"
    assert report["concept_scope"] == "single_generic_concept_part"
    assert report["assembly_generated"] is False
    assert "mounting_plate" not in json.dumps({"draft": draft, "report": report})
    assert not (run / "05_single_create/single_part_upper_link/model.step").exists()
    assert not (run / "05_single_create/single_part_upper_link/model.stl").exists()


def test_executable_golden_work_is_discoverable_by_web_backend(tmp_path, monkeypatch):
    module, workspace, _, _ = _run_contract(tmp_path, monkeypatch)
    backend = WorkflowConsoleBackend(project_root=tmp_path, workspace_root=workspace)

    works = backend.list_works(filters={"show_developer": True})["works"]
    work = backend.get_work_detail(module.WORK_ID)
    assert module.WORK_ID in {item["work_id"] for item in works}
    assert work["summary"]["title"] == "Golden Desktop Robot Arm"


def test_executable_runner_does_not_copy_expected_artifacts():
    source = Path(golden_service.__file__).read_text(encoding="utf-8").lower()
    cli = SCRIPT.read_text(encoding="utf-8")

    assert "copyfile" not in source
    assert "copytree" not in source
    assert "shutil" not in source
    assert source.index("actions.create_reviewed_part") < source.index("compare_actual_to_expected")
    assert "from ai_native_cad.examples.golden_desktop_robot_arm import main" in cli


@pytest.mark.skipif(os.environ.get("CADFLOW_RUN_SLOW_GOLDEN") != "1", reason="slow CadQuery golden smoke is opt-in")
def test_executable_golden_full_mode_generates_step_and_stl(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cadquery_executor, "PROJECT_ROOT", tmp_path)
    module = _module()
    workspace = tmp_path / "workspace"

    result = module.run_golden_workflow(workspace, mode="full", project_root=tmp_path)
    run = workspace / "works" / module.WORK_ID / "runs" / module.RUN_ID
    child = run / "05_single_create" / "single_part_upper_link"
    assert result["comparison"]["passed"] is True
    assert (child / "model.step").exists()
    assert (child / "model.stl").exists()
    assert (run / "06_part_result_review/part_result_review.json").exists()
