import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_ROOT = PROJECT_ROOT / "examples" / "golden_desktop_robot_arm"
WORKFLOW_ROOT = GOLDEN_ROOT / "expected_workflow"

EXPECTED_STAGES = {
    "01_requirement",
    "02_planning",
    "03_part_request",
    "04_part_review",
    "05_handoff",
    "06_single_create",
    "07_workflow_review",
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_golden_workflow_expected_summaries_parse():
    summaries = sorted(WORKFLOW_ROOT.rglob("*.expected.summary.json"))

    assert len(summaries) == 13
    assert all(isinstance(_json(path), dict) for path in summaries)


def test_golden_workflow_contains_required_stages():
    stages = {path.name for path in WORKFLOW_ROOT.iterdir() if path.is_dir()}

    assert stages == EXPECTED_STAGES
    assert all((WORKFLOW_ROOT / stage / "notes.md").exists() for stage in stages)


def test_golden_assembly_plan_selects_upper_link_from_six_candidates():
    plan = _json(
        WORKFLOW_ROOT
        / "02_planning"
        / "assembly_plan.expected.summary.json"
    )

    assert len(plan["candidate_parts"]) == 6
    assert len(plan["reference_components"]) == 2
    assert plan["selected_candidate"] == "upper_link"
    assert plan["full_assembly_cad_supported"] is False


def test_golden_cad_ir_preserves_source_intent_and_uses_generic_family():
    draft = _json(
        WORKFLOW_ROOT
        / "06_single_create"
        / "cad_ir_draft.expected.summary.json"
    )

    assert draft["source_part_id"] == draft["source_intent"] == "upper_link"
    assert draft["part_type"] == "link_like_part"
    assert draft["geometry_family"] == "elongated_plate_with_end_holes"
    assert draft["mounting_plate_fallback"] is False
    assert draft["part_specific_template"] is False


def test_golden_report_does_not_claim_full_assembly():
    report = _json(
        WORKFLOW_ROOT / "06_single_create" / "report.expected.summary.json"
    )
    review = _json(
        WORKFLOW_ROOT
        / "07_workflow_review"
        / "workflow_review.expected.summary.json"
    )

    assert report["concept_scope"] == "single_generic_concept_part"
    assert report["assembly_generated"] is False
    assert report["all_parts_generated"] is False
    assert review["assembly_generated"] is False


def test_golden_acceptance_documents_web_graph_and_evidence_chain():
    acceptance = (GOLDEN_ROOT / "acceptance.md").read_text(encoding="utf-8")

    assert "Workflow graph" in acceptance
    assert "reference lane" in acceptance
    assert "selected part pipeline" in acceptance
    assert "Evidence chain" in acceptance
    assert "cad_ir_draft.json" in acceptance
    assert "model.step" in acceptance
    assert "model.stl" in acceptance
