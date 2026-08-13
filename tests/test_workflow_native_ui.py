from copy import deepcopy

import pytest

from ai_native_cad.workflow_console.agent_activity import bounded_evidence, significant_activity
from ai_native_cad.workflow_console.work_outcome import project_stopped_attempt
from ai_native_cad.workflow_console.product_usability import _workflow_node_interaction
from ai_native_cad.workflow_console.workflow_page_view_model import select_projected_workflow_node


def test_specific_policy_block_explains_pre_execution_rejection_and_safe_retry():
    outcome = project_stopped_attempt(
        stop_reason="policy_blocked",
        episode={"execution_succeeded": False},
        agent_items=[{
            "kind": "agent_response",
            "action": "create_contract",
            "contract_fields": ["schema_version", "operations", "python_code"],
        }],
        scope_label="Camera Cradle",
        language="en",
    )

    assert outcome["technical_reason"] == "structured_contract_contains_execution_field"
    assert outcome["geometry_generated"] is False
    assert outcome["result_published"] is False
    assert outcome["user_input_required"] is False
    assert outcome["retryable"] is True
    assert "outside the create_contract Skill action" in outcome["why"]
    assert outcome["next_action"] == "Retry Camera Cradle"


def test_activity_collapses_protocol_repetition_without_becoming_evidence():
    items = [
        {"kind": "agent_response", "action": "request_context", "summary": "Read the Work"},
        {"kind": "agent_response", "action": "request_context", "summary": "Read the Part"},
        {"kind": "agent_response", "action": "create_contract", "summary": "Prepared geometry"},
    ]
    rows = significant_activity(items, language="en")

    assert [row["key"] for row in rows] == ["request_context", "prepared_candidate"]
    assert rows[0]["count"] == 2
    assert "contract_fields" not in rows[1]
    assert bounded_evidence(list(range(30)), max_items=4)[-1] == {
        "truncated": True,
        "remaining_items": 26,
    }


def test_local_workflow_selection_preserves_exact_scoped_action_without_projection():
    camera_action = {
        "key": "retry_agent",
        "target_work_id": "owner_fixture",
        "part_job_id": "camera_cradle",
        "target_run_id": "run_camera_1",
        "label": "Retry Camera Cradle",
    }
    page = {
        "projection_mode": "agent_first",
        "read_only": False,
        "nodes": [
            {"id": "work_design", "selected": True, "interaction": {}},
            {
                "id": "attempt_camera_1",
                "selected": False,
                "part_job_id": "camera_cradle",
                "run_id": "run_camera_1",
                "interaction": {"primary_action": camera_action, "secondary_actions": []},
            },
        ],
        "workflow_graph": {
            "nodes": [
                {"id": "work_design", "selected": True},
                {"id": "attempt_camera_1", "selected": False},
            ],
            "edges": [],
        },
    }
    durable_snapshot = deepcopy(page)

    selected = select_projected_workflow_node(page, "attempt_camera_1")

    assert selected["selected_node"]["part_job_id"] == "camera_cradle"
    assert selected["recommended_next_action"] == camera_action
    assert selected["available_actions"]["primary_action"]["target_run_id"] == "run_camera_1"
    assert selected["workflow_graph"]["nodes"][1]["selected"] is True
    # The helper can only mutate presentation selection/action fields; source
    # node identity and scoped interaction remain byte-for-byte equivalent.
    assert selected["nodes"][1]["interaction"] == durable_snapshot["nodes"][1]["interaction"]


def test_local_workflow_selection_rejects_snapshot_and_unknown_nodes():
    with pytest.raises(ValueError, match="actionable Agent-first"):
        select_projected_workflow_node({"projection_mode": "agent_first", "read_only": True}, "x")
    with pytest.raises(ValueError, match="unknown projected workflow node"):
        select_projected_workflow_node({
            "projection_mode": "agent_first",
            "read_only": False,
            "nodes": [],
            "workflow_graph": {"nodes": [], "edges": []},
        }, "x")


def test_scoped_recovery_command_is_not_replaced_by_sibling_or_generic_part_authority():
    interaction = _workflow_node_interaction(
        {
            "id": "attempt:camera_cradle:camera_attempt_1",
            "part_job_id": "camera_cradle",
            "run_id": "camera_attempt_1",
            "status": "blocked",
            "detail": {
                "type": "attempt",
                "recovery": {
                    "part_job_id": "camera_cradle",
                    "run_id": "camera_attempt_1",
                    "retryable": True,
                    "recommended_action": {"key": "retry_agent"},
                },
            },
        },
        work_id="owner_fixture",
        jobs_by_id={
            "camera_cradle": {"active_attempt_run_id": "camera_attempt_1", "attempts": []},
            "extrusion_adapter": {"active_attempt_run_id": "adapter_attempt_1", "attempts": []},
        },
        overview_parts={
            "camera_cradle": {"name": "Camera Cradle", "state": "design"},
            "extrusion_adapter": {"name": "Extrusion Adapter", "state": "design"},
        },
        references=[],
        accepted={},
        command_authority={
            "work": {},
            "parts": {
                # The coarse current command may still say continue; exact
                # persisted selected-attempt recovery must remain authoritative.
                "camera_cradle": {"primary_action": {
                    "key": "continue_agent",
                    "part_job_id": "camera_cradle",
                    "target_run_id": "camera_attempt_1",
                }},
                "extrusion_adapter": {"primary_action": {
                    "key": "retry_agent",
                    "part_job_id": "extrusion_adapter",
                    "target_run_id": "adapter_attempt_1",
                }},
            },
        },
        language="en",
    )

    assert interaction["primary_action"]["key"] == "retry_agent"
    assert interaction["primary_action"]["part_job_id"] == "camera_cradle"
    assert interaction["primary_action"]["target_run_id"] == "camera_attempt_1"
