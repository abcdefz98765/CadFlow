"""Display policy for workflow-console artifacts.

This is a UI policy over the existing readable-artifact allowlist. It does not
grant new filesystem access.
"""

from __future__ import annotations

from typing import Any

ARTIFACT_DISPLAY_CATEGORIES = {"human_facing", "review_debug", "internal_debug"}

HUMAN_FACING_ARTIFACTS = {
    "report.md",
    "workflow_review.md",
    "workflow_review.json",
    "stage_review.json",
    "requirement_clarification.json",
    "requirement_v2.json",
    "rework_decision.json",
    "assembly_plan.json",
    "part_result_review.json",
}

REVIEW_DEBUG_ARTIFACTS = {
    "requirement.json",
    "design_brief.json",
    "part_create_request.json",
    "part_request_review.json",
    "reviewed_part_handoff.json",
    "part_execution_request.json",
    "lineage.json",
    "agent_trace.json",
    "report.json",
    "assembly_plan.md",
}

INTERNAL_DEBUG_ARTIFACTS = {
    "input_ir.json",
    "planning_artifact.json",
    "parent_input_ir.json",
    "parent_report_snapshot.json",
    "parent_agent_trace_snapshot.json",
    "revision_request.json",
    "change_intent.json",
    "revision_plan.json",
    "patch.json",
    "comparison.json",
    "revision_report.md",
    "logs/runtime.json",
}


def artifact_display_category(name: str) -> str:
    """Return the display category for a known artifact name."""
    if name in HUMAN_FACING_ARTIFACTS:
        return "human_facing"
    if name in REVIEW_DEBUG_ARTIFACTS:
        return "review_debug"
    return "internal_debug"


def artifact_visible_by_default(name: str) -> bool:
    """Return whether an artifact should be visible in the default UI."""
    return artifact_display_category(name) == "human_facing"


def filter_artifacts_for_display(
    artifacts: list[dict[str, Any]],
    *,
    show_debug: bool = False,
    show_internal: bool = False,
) -> list[dict[str, Any]]:
    """Apply display policy to already-allowlisted artifact metadata."""
    visible = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not isinstance(artifact.get("name"), str):
            continue
        category = artifact_display_category(artifact["name"])
        if category == "internal_debug" and not show_internal:
            continue
        if category == "review_debug" and not show_debug and not show_internal:
            continue
        visible.append({**artifact, "display_category": category, "visible_by_default": category == "human_facing"})
    return visible
