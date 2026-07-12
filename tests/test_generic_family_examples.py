import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = PROJECT_ROOT / "examples" / "reviewed_part_generic_link_like"


def _summary(name: str) -> dict:
    return json.loads((EXAMPLE_DIR / name).read_text(encoding="utf-8"))


def test_generic_link_like_example_summaries_preserve_intent_and_share_family():
    upper = _summary("upper_link_expected_ir.summary.json")
    lower = _summary("lower_link_expected_ir.summary.json")

    assert upper["source_part_id"] == upper["source_intent"] == "upper_link"
    assert lower["source_part_id"] == lower["source_intent"] == "lower_link"
    for summary in (upper, lower):
        assert summary["part_type"] == "link_like_part"
        assert summary["geometry_family"] == "elongated_plate_with_end_holes"
        assert summary["normalization"]["from"] == summary["source_part_id"]
        assert summary["normalization"]["to"] == "link_like_part/elongated_plate_with_end_holes"
        assert summary["normalization"]["reason"]
        assert summary["report_scope"] == "single_generic_concept_part"
        assert summary["not_assembly_result"] is True
        assert summary["validation_expectations"]["strength_validated"] is False


def test_generic_link_like_examples_do_not_claim_full_assembly():
    readme = (EXAMPLE_DIR / "README.md").read_text(encoding="utf-8").lower()
    assert "not a complete robot-arm assembly" in readme
    assert "full_assembly" not in json.dumps(
        [_summary("upper_link_expected_ir.summary.json"), _summary("lower_link_expected_ir.summary.json")]
    )


def test_negative_example_lists_forbidden_template_and_fallback_paths():
    readme = (
        PROJECT_ROOT / "examples" / "negative_no_template_fallback" / "README.md"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "upper_link -> mounting_plate",
        "upper_link -> upper_link_template",
        "no template -> terminal block before AgentAdapter.create_part_ir",
        "Provider-generated CadQuery or Python bypasses CAD IR",
        "Successful STEP/STL reports a full robot-arm assembly",
    ):
        assert forbidden in readme


def test_robot_arm_smoke_documents_single_generic_concept_scope():
    smoke = (
        PROJECT_ROOT / "docs" / "smoke-tests" / "desktop-robot-arm.md"
    ).read_text(encoding="utf-8")

    assert "single_generic_concept_part" in smoke
    assert "part_type`: `link_like_part" in smoke
    assert "geometry_family`: `elongated_plate_with_end_holes" in smoke
    assert "complete robot-arm assembly" in smoke
