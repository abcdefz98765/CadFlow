from copy import deepcopy

import pytest

from ai_native_cad.workflow_console.agent_activity import bounded_evidence, significant_activity
from ai_native_cad.workflow_console.work_outcome import project_stopped_attempt
from ai_native_cad.workflow_console.product_usability import _workflow_node_interaction
from ai_native_cad.workflow_console.product_usability import build_agent_output_projection
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
        failure_diagnostic={
            "schema_version": 1,
            "rejection_stage": "action_contract_validation",
            "rejected_action": "create_contract",
            "reason_code": "structured_contract_execution_field",
            "requested_capability_or_context": "python_code",
            "human_safe_detail": "Executable source is not allowed in this action.",
            "side_effect_started": False,
        },
    )

    assert outcome["technical_reason"] == "structured_contract_execution_field"
    assert outcome["geometry_generated"] is False
    assert outcome["result_published"] is False
    assert outcome["user_input_required"] is False
    assert outcome["retryable"] is True
    assert "python_code" in outcome["why"]
    assert outcome["cause_category"] == "agent_action_problem"
    assert outcome["resolution_owner"] == "agent"
    assert outcome["next_action"] == "Start a new Camera Cradle attempt"


def test_historical_policy_block_is_honest_and_does_not_infer_from_agent_payload():
    outcome = project_stopped_attempt(
        stop_reason="policy_blocked",
        episode={"execution_succeeded": False},
        agent_items=[{
            "kind": "agent_response",
            "action": "create_contract",
            "contract_fields": ["source", "password"],
        }],
        scope_label="Camera Cradle",
        language="en",
    )

    assert outcome["cause_category"] == "historical_policy_block"
    assert outcome["historical_diagnostic_missing"] is True
    assert outcome["retryable"] is False
    assert outcome["recovery_action_key"] == "start_new_attempt"
    assert "source" not in outcome["why"]
    assert outcome["next_action"] == "Start a new Camera Cradle attempt"


@pytest.mark.parametrize(
    ("stage", "reason_code", "category", "owner", "action_key"),
    [
        (
            "context_authorization",
            "context_not_allowed_for_skill",
            "context_permission_problem",
            "agent",
            "start_new_attempt",
        ),
        (
            "generated_code_policy",
            "sandbox_source_policy",
            "generated_code_policy_problem",
            "agent",
            "start_new_attempt",
        ),
        (
            "local_execution_environment",
            "sandbox_unavailable",
            "environment_problem",
            "environment",
            "check_environment",
        ),
        (
            "reviewable_publication",
            "step_hash_mismatch",
            "publication_integrity_problem",
            "cadflow",
            "no_user_action",
        ),
        (
            "agent_typed_stop",
            "agent_reported_policy_block",
            "agent_reported_policy_block",
            "agent",
            "start_new_attempt",
        ),
    ],
)
def test_policy_diagnostics_map_to_stable_product_categories(
    stage, reason_code, category, owner, action_key
):
    outcome = project_stopped_attempt(
        stop_reason="policy_blocked",
        episode={"execution_succeeded": False},
        agent_items=[],
        scope_label="Part",
        language="en",
        failure_diagnostic={
            "schema_version": 1,
            "rejection_stage": stage,
            "rejected_action": "request_execution",
            "reason_code": reason_code,
            "requested_capability_or_context": "cadquery_v1",
            "human_safe_detail": "Typed local rejection.",
            "side_effect_started": False,
        },
    )

    assert outcome["cause_category"] == category
    assert outcome["resolution_owner"] == owner
    assert outcome["recovery_action_key"] == action_key


def test_page_local_reference_cache_reads_relevant_artifact_once():
    class Backend:
        def __init__(self):
            self.reads = 0

        def read_work_artifact_reference(self, work_id, artifact_id):
            assert (work_id, artifact_id) == ("work", "agent-output")
            self.reads += 1
            return {"content": {"records": [{"action": "stop"}]}}

    backend = Backend()
    references = [{
        "artifact_id": "agent-output",
        "checkpoint": "agent_output",
        "trust_role": "observation",
    }, {
        "artifact_id": "step-binary",
        "checkpoint": "reviewable_step",
        "trust_role": "reviewable_result",
    }]
    cache = {}

    build_agent_output_projection(
        backend, "work", references, language="en", reference_cache=cache
    )
    build_agent_output_projection(
        backend, "work", references, language="en", reference_cache=cache
    )

    assert backend.reads == 1
    assert "step-binary" not in cache


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
