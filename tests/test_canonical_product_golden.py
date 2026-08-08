from __future__ import annotations

import json
from pathlib import Path

import ai_native_cad.examples as examples_service
from ai_native_cad.agents.model_program_policy import (
    validate_cadquery_model_program_source,
)
from ai_native_cad.examples.canonical_product_golden import (
    PRODUCT_GOLDEN_ID,
    PRODUCT_GOLDEN_PART_JOB_ID,
    PRODUCT_GOLDEN_PROMPT,
    PRODUCT_GOLDEN_SOURCE,
)
from ai_native_cad.workflow_console import WorkflowConsoleBackend, dispatch_route
from ai_native_cad.workflow_console.i18n import copy as i18n_copy
from ai_native_cad.workflow_console.nicegui_app import WORKFLOW_UI_CSS
from ai_native_cad.workflow_console.workflow_page_view_model import (
    build_workbench_overview_view_model,
)


class GoldenProjectionBackend:
    def __init__(self) -> None:
        self.design_brief = {
            "artifact_type": "design_brief",
            "schema_version": 1,
            "content": {
                "concept": "Single-piece U-bracket with a panel base and two support ears.",
                "geometry_strategy": "Union the base and ears, then cut mounting and clearance features.",
                "important_parameters": [
                    {"name": "base", "value": "58 × 42 × 4", "unit": "mm"},
                ],
                "functional_features": ["Four panel holes", "Cable window"],
                "interfaces": ["Flat panel", "Generic micro servo"],
                "user_constraints": ["Single piece", "Four panel screws"],
                "assumptions": ["Generic prototype material"],
                "tradeoffs": ["Nominal servo spacing is not fit-validated"],
                "changes_after_repair": [],
                "repair_count": 0,
                "source_capability_mode": "scripted provider + attested cadquery_v1 model program",
                "external_provider_quality_proof": False,
            },
        }
        self.reviewable = {
            "reviewable_result_id": "reviewable_product_golden",
            "work_id": "product_golden_servo_bracket",
            "run_id": "servo_mounting_bracket_attempt_1",
            "part_job_id": PRODUCT_GOLDEN_PART_JOB_ID,
            "capability_mode": "provider_selected_design_with_attested_model_program",
            "geometry": {
                "valid": True,
                "solid_count": 1,
                "face_count": 31,
                "volume": 13445.2,
                "bounding_box": {"x": 58.0, "y": 42.0, "z": 34.0},
            },
            "validation": {"step_reimport_valid": True},
            "step": {"artifact_id": "product_golden_step"},
            "assumptions": ["Dimensions are in millimetres."],
            "limitations": ["Strength and manufacturer servo fit were not validated."],
            "reviewable": True,
            "source_hash": "1" * 64,
        }

    def get_work_detail(self, work_id: str) -> dict:
        assert work_id == "product_golden_servo_bracket"
        references = [
            {
                "artifact_id": "product_golden_design_brief",
                "work_id": work_id,
                "run_id": "servo_mounting_bracket_attempt_1",
                "part_job_id": PRODUCT_GOLDEN_PART_JOB_ID,
                "relative_path": "design_brief.json",
                "phase": "design",
                "checkpoint": "design_brief",
                "trust_role": "candidate",
                "validation_status": "not_validated",
            },
            {
                "artifact_id": "reviewable_product_golden",
                "work_id": work_id,
                "run_id": "servo_mounting_bracket_attempt_1",
                "part_job_id": PRODUCT_GOLDEN_PART_JOB_ID,
                "relative_path": "episodes/design_part/product_golden_design_1/reviewable_result.json",
                "phase": "build_evaluate",
                "checkpoint": "reviewable_result",
                "trust_role": "reviewable_result",
                "validation_status": "passed",
            },
            {
                "artifact_id": "product_golden_step",
                "work_id": work_id,
                "run_id": "servo_mounting_bracket_attempt_1",
                "part_job_id": PRODUCT_GOLDEN_PART_JOB_ID,
                "relative_path": "episodes/design_part/product_golden_design_1/candidates/candidate_001/exec_001/model.step",
                "phase": "build_evaluate",
                "checkpoint": "reviewable_result",
                "trust_role": "reviewable_result",
                "validation_status": "passed",
                "source_artifact_ids": ["reviewable_product_golden"],
            },
        ]
        return {
            "summary": {
                "title": "Compact Micro Servo Mounting Bracket",
                "overall_status": "needs_review",
            },
            "entity_state": {
                "description": PRODUCT_GOLDEN_PROMPT,
                "root_run_id": None,
                "run_ids": ["servo_mounting_bracket_attempt_1"],
                "metadata": {
                    "example_id": PRODUCT_GOLDEN_ID,
                    "example_classification": "product_golden",
                },
                "part_jobs": [
                    {
                        "part_job_id": PRODUCT_GOLDEN_PART_JOB_ID,
                        "role": "single-piece servo interface bracket",
                        "active_attempt_run_id": "servo_mounting_bracket_attempt_1",
                        "attempts": [
                            {
                                "run_id": "servo_mounting_bracket_attempt_1",
                                "source": "user_revision",
                            }
                        ],
                    }
                ],
                "accepted_part_results": {},
                "artifact_references": references,
            },
            "parts": [],
            "run_history": [{"run_id": "servo_mounting_bracket_attempt_1"}],
        }

    def read_work_artifact_reference(self, work_id: str, artifact_id: str) -> dict:
        if artifact_id == "product_golden_design_brief":
            return {"content": self.design_brief}
        if artifact_id == "reviewable_product_golden":
            return {"content": self.reviewable}
        raise FileNotFoundError(artifact_id)

    def read_work_run_prompt(self, work_id: str, run_id: str) -> str:
        return PRODUCT_GOLDEN_PROMPT


def test_canonical_product_golden_source_is_policy_valid_and_not_a_closed_family():
    result = validate_cadquery_model_program_source(PRODUCT_GOLDEN_SOURCE)

    assert result["valid"] is True
    assert result["executed"] is False
    assert "part_type" not in PRODUCT_GOLDEN_SOURCE
    assert "mounting_plate" not in PRODUCT_GOLDEN_SOURCE


def test_product_golden_projection_explains_request_design_build_and_result():
    overview = build_workbench_overview_view_model(
        GoldenProjectionBackend(),
        "product_golden_servo_bracket",
        language="en",
    )

    assert overview["capability"]["key"] == "reproducible_product_golden"
    assert overview["user_input"] == {
        "title": "Your Request",
        "original_request": PRODUCT_GOLDEN_PROMPT,
        "revision_request": None,
        "visible_constraints": ["Single piece", "Four panel screws"],
        "source_type": "initial_request",
        "source_label": "Initial request",
        "durable": True,
        "generated_summary_used": False,
    }
    assert overview["agent_design"]["concept"].startswith("Single-piece U-bracket")
    assert overview["agent_design"]["private_reasoning_exposed"] is False
    assert overview["agent_design"] != overview["agent_activity"]
    assert overview["transformation"]["chain"] == [
        "user_request",
        "agent_design",
        "build_evaluate",
        "result",
    ]
    assert all(item["status"] == "completed" for item in overview["transformation"]["events"])
    assert overview["preview"]["kind"] == "registered_step"
    assert "/web-viewer/index.html" in overview["preview"]["viewer_url"]
    assert overview["workflow"]["reachable"] is True
    assert overview["workflow"]["current_phase"] == "accept_deliver"
    assert overview["advanced"]["collapsed"] is True
    primary = dict(overview)
    primary.pop("advanced")
    serialized = json.dumps(primary).lower()
    assert "chain_of_thought" not in serialized
    assert "private reasoning" not in serialized
    assert "source_hash" not in serialized


def test_product_golden_route_uses_shared_service_and_preserves_old_golden(monkeypatch, tmp_path):
    backend = WorkflowConsoleBackend(project_root=tmp_path, workspace_root=tmp_path / "workspace")
    backend.create_workspace(name="Golden Route Test")
    calls = []

    def fake_product_golden(target, *, progress_callback=None):
        calls.append(target)
        return {"work_id": "product_golden", "created": True}

    monkeypatch.setattr(examples_service, "open_canonical_product_golden", fake_product_golden)
    response = dispatch_route(backend, "open_product_golden_example", body={})

    assert response["ok"] is True
    assert response["data"]["work_id"] == "product_golden"
    assert calls == [backend]
    assert any(spec.name == "create_golden_example" for spec in __import__(
        "ai_native_cad.workflow_console.routes", fromlist=["ROUTE_SPECS"]
    ).ROUTE_SPECS)


def test_live_product_example_is_primary_and_completed_golden_remains_secondary():
    source = __import__(
        "ai_native_cad.workflow_console.nicegui_app",
        fromlist=["placeholder"],
    ).__loader__.get_source("ai_native_cad.workflow_console.nicegui_app")
    examples_index = Path("examples/README.md").read_text(encoding="utf-8")
    robot_readme = Path("examples/golden_desktop_robot_arm/README.md").read_text(encoding="utf-8")

    assert source.index('"Start Product Example"') < source.index(
        'i18n_copy(language, "open_product_example")'
    )
    assert i18n_copy("en", "compatibility_examples") == "Compatibility examples"
    assert "PRODUCT GOLDEN" in examples_index
    assert "COMPATIBILITY / REGRESSION" in examples_index
    assert "Compatibility / Multi-Part Planning Regression" in robot_readme


def test_primary_product_labels_exist_in_english_and_chinese():
    assert i18n_copy("en", "your_request") == "Your Request"
    assert i18n_copy("zh", "your_request") == "你的要求"
    assert i18n_copy("en", "agent_design") == "Agent Design"
    assert i18n_copy("zh", "agent_design") == "Agent 设计"
    assert i18n_copy("zh", "open_product_example") == "打开产品示例"
    assert "workbench-narrative-grid" in WORKFLOW_UI_CSS
    assert "@media(max-width:1100px)" in WORKFLOW_UI_CSS
    assert "@media(max-width:760px)" in WORKFLOW_UI_CSS


def test_canonical_architecture_remains_the_four_phase_authority():
    architecture = Path(
        "docs/architecture/cadflow-canonical-product-architecture.md"
    ).read_text(encoding="utf-8")

    assert "Intent -> Design -> Build & Evaluate -> Accept & Deliver" in architecture
    assert "No implementation, test fixture, legacy document, UI layout, or Golden example" in architecture
    assert "M2.6" not in architecture
