"""NiceGUI shell for the local reviewed-part workflow console.

The module keeps data shaping independent from NiceGUI so tests can exercise
the privacy and gating behavior without browser automation or the optional UI
dependency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from html import escape as html_escape
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from ai_native_cad.workflow_console.actions import WorkflowConsoleActions
from ai_native_cad.workflow_console.actions import STAGE_REVIEW_STATUSES, STAGE_REVIEW_STAGES, STAGE_REWORK_TARGETS
from ai_native_cad.workflow_console.artifact_display import filter_artifacts_for_display
from ai_native_cad.workflow_console.backend import DOWNLOADABLE_FILES, WorkflowConsoleBackend
from ai_native_cad.workflow_console.action_lifecycle import (
    ActionExecutionState,
    _accept_reviewable_result_async,
    _agent_terminal_outcome,
    _action_identity,
    _answer_and_continue_agent_async,
    _continue_agent_async,
    _continue_work_design_async,
    _execute_action_lifecycle,
    _pending_action_matches,
    _revise_blocked_request_async,
    _revise_reviewable_result_async,
    _runtime_message,
    _schedule_action,
    _set_action_execution,
    _start_work_intent_async,
)
from ai_native_cad.workflow_console.review_surface import REVIEW_SURFACE_ARTIFACTS, build_workflow_review_surface
from ai_native_cad.workflow_console.product_usability import build_home_view_model
from ai_native_cad.workflow_console.agent_activity_ui import render_agent_activity
from ai_native_cad.workflow_console.technical_evidence_ui import render_lazy_technical_evidence
from ai_native_cad.workflow_console.attempt_ui import render_stopped_attempt
from ai_native_cad.workflow_console.selected_node_inspector_ui import (
    SelectedInspectorRenderers,
    render_selected_node_inspector,
)
from ai_native_cad.workflow_console.workbench_styles import WORKFLOW_UI_CSS
from ai_native_cad.workflow_console.work_design_ui import render_work_design
from ai_native_cad.workflow_console.workflow_graph_ui import (
    render_current_attention,
    render_dynamic_work_graph,
    workflow_graph_with_runtime,
)

# Compatibility import for renderer-free tests and older local callers.
_workflow_graph_with_runtime = workflow_graph_with_runtime
from ai_native_cad.workflow_console.work_stage_projection import build_work_stage_projection, unavailable_work_stage_projection
from ai_native_cad.workflow_console.workflow_page_view_model import build_workflow_page_view_model
from ai_native_cad.workflow_console.workflow_page_view_model import build_workbench_overview_view_model
from ai_native_cad.workflow_console.workflow_page_view_model import select_projected_workflow_node
from ai_native_cad.workflow_console.routes import dispatch_route
from ai_native_cad.workflow_console.server import resolve_downloadable
from ai_native_cad.workflow_console.stage_runner import READABLE_ARTIFACTS
from ai_native_cad.workflow_console.i18n import copy as i18n_copy, stage_label, status_label
from ai_native_cad.workflow_console.ui_performance import ui_trace_event, ui_trace_start

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8780
DEFAULT_RUN_PAGE_SIZE = 50
WEB_VIEWER_ROOT = Path(__file__).resolve().parents[3] / "web-viewer"
WORK_USER_PAGES = (
    ("overview", "dashboard", "Overview"),
    ("workflow", "account_tree", "Workflow"),
)
PAGE_IDS = frozenset({
    "workspace",
    "works",
    "config",
    "overview",
    "workflow",
    "node",
    "parts",
    "review",
    "products",
    "runs",
    "history",
})
def _localized_stage_title(stage: dict[str, Any], language: str) -> str:
    stage_id = str(stage.get("stage_id") or "")
    return stage_label(language, stage_id, stage.get("stage_name") or stage.get("label"))


def _display_status(status: Any, language: str) -> str:
    return status_label(language, status)


def _require_page_id(value: Any) -> str:
    """Accept only declared page ids; browser event objects are never page ids."""
    if not isinstance(value, str):
        raise ValueError("page selection requires a page id")
    if value not in PAGE_IDS:
        raise ValueError(f"unknown console page: {value}")
    return value


def _select_console_page(state: dict[str, Any], page: Any, refresh: Callable[[], None]) -> None:
    """Apply the Work-page navigation contract without changing selected Work."""
    page_id = _require_page_id(page)
    state["active_page"] = page_id
    state["selected_node_id"] = None
    if page_id != "workflow":
        state["selected_stage_id"] = None
    refresh()


def _select_console_work(state: dict[str, Any], work_id: str, refresh: Callable[[], None]) -> None:
    if not isinstance(work_id, str) or not work_id:
        raise ValueError("work selection requires a work id")
    state["selected_work_id"] = work_id
    state["selected_run_id"] = None
    state["view_mode"] = "current_work"
    state["selected_node_id"] = None
    state["selected_stage_id"] = None
    # Action feedback belongs to the Work that produced it.  Keeping it while
    # switching Works makes a successful accept/revise look as if it happened
    # on the newly selected Work.
    state["action_execution"] = None
    state["active_page"] = "overview"
    refresh()


def _select_console_run(state: dict[str, Any], run_id: str, refresh: Callable[[], None]) -> None:
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run selection requires a run id")
    state["selected_run_id"] = run_id
    state["view_mode"] = "run_snapshot"
    state["active_page"] = "workflow"
    refresh()


def _select_current_console_work(state: dict[str, Any], refresh: Callable[[], None]) -> None:
    state["view_mode"] = "current_work"
    state["selected_run_id"] = None
    state["active_page"] = "workflow"
    refresh()


def _page_selection_callback(on_select_page: Callable[[str], None], page: str) -> Callable[[Any], None]:
    """Bind a declared page id while deliberately consuming NiceGUI's event."""
    page_id = _require_page_id(page)

    def callback(_event: Any = None) -> None:
        on_select_page(page_id)

    return callback


def _run_selection_callback(
    on_select_run: Callable[[str], None], run_id: str
) -> Callable[[Any], None]:
    """Bind one immutable Run id while consuming NiceGUI's click event."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run selection requires a run id")

    def callback(_event: Any = None) -> None:
        on_select_run(run_id)

    return callback

# The workflow cockpit deliberately has one visual vocabulary.  Keep semantic
# state, spacing, and responsive rules here instead of scattering styles among
# individual renderers.  NiceGUI still only receives presentation data from the
# workflow page view model; these classes never infer workflow state.

ARTIFACT_PAGE_ARTIFACTS = (
    "report.md",
    "report.json",
    "workflow_review.md",
    "workflow_review.json",
    "requirement.json",
    "design_brief.json",
    "assembly_plan.json",
    "part_create_request.json",
    "part_request_review.json",
    "reviewed_part_handoff.json",
    "part_execution_request.json",
    "cad_ir_draft.json",
    "part_result_review.json",
    "stage_review.json",
    "rework_decision.json",
    "lineage.json",
    "agent_trace.json",
    "logs/runtime.json",
)

REVIEWED_PART_ACTIONS = (
    {
        "key": "part_request",
        "title": "Part Request",
        "action_label": "Create request",
        "method": "create_part_request",
        "upstream_artifacts": ("assembly_plan.json",),
        "output_artifact": "part_create_request.json",
    },
    {
        "key": "part_review",
        "title": "Part Review",
        "action_label": "Review request",
        "method": "review_part_request",
        "upstream_artifacts": ("part_create_request.json",),
        "output_artifact": "part_request_review.json",
    },
    {
        "key": "reviewed_handoff",
        "title": "Reviewed Handoff",
        "action_label": "Create handoff",
        "method": "create_reviewed_handoff",
        "upstream_artifacts": ("part_create_request.json", "part_request_review.json"),
        "output_artifact": "reviewed_part_handoff.json",
    },
    {
        "key": "reviewed_part_create",
        "title": "Reviewed Single-Part Create",
        "action_label": "Create one part",
        "method": "create_reviewed_part",
        "upstream_artifacts": ("reviewed_part_handoff.json",),
        "output_artifact": "lineage.json",
    },
    {
        "key": "part_result_review",
        "title": "Part Result Review",
        "action_label": "Review result",
        "method": "review_part_result",
        "upstream_artifacts": ("reviewed_part_handoff.json", "lineage.json"),
        "output_artifact": "part_result_review.json",
    },
)




def build_console_page_data(
    backend: WorkflowConsoleBackend | None = None,
    selected_run_id: str | None = None,
    *,
    selected_work_id: str | None = None,
    active_page: str = "workspace",
    selected_node_id: str | None = None,
    selected_stage_id: str | None = None,
    view_mode: str = "current_work",
    language: str = "en",
    show_debug_works: bool = False,
    show_unclassified_runs: bool = False,
    show_low_level_details: bool = False,
    root: str | None = None,
    limit: int = DEFAULT_RUN_PAGE_SIZE,
    offset: int = 0,
    search: str | None = None,
) -> dict[str, Any]:
    """Build path-free data for the NiceGUI console pages."""
    backend = backend or WorkflowConsoleBackend()
    works_response = dispatch_route(
        backend,
        "list_works",
        query={
            "limit": 50,
            "offset": 0,
            "show_developer": show_debug_works,
        },
    )
    workspace_response = dispatch_route(backend, "read_workspace")
    config_response = dispatch_route(backend, "read_workspace_config")
    works_page = works_response["data"] if works_response["ok"] and isinstance(works_response["data"], dict) else {}
    works = works_page.get("works") if isinstance(works_page.get("works"), list) else []
    selected_work = selected_work_id
    work_detail = build_selected_work_data(backend, selected_work) if selected_work else empty_selected_work_data()
    runs: list[dict[str, Any]] = []
    pagination = _empty_pagination(limit, offset)
    run_filters: dict[str, Any] = {}
    selected = selected_run_id or _dict_get(work_detail.get("summary"), "latest_run_id")
    load_runs = selected_run_id is not None and not (
        selected_work
        and active_page in {"overview", "workflow", "parts"}
        and view_mode == "current_work"
    )
    if active_page in {"runs", "history"}:
        runs = [_run_history_row_as_run(row) for row in work_detail.get("run_history", []) if isinstance(row, dict)]
        selected = selected_run_id or (runs[0]["run_id"] if runs else selected)
    run_data = (
        build_selected_run_data(backend, selected, root=root, selected_stage_id=selected_stage_id, language=language)
        if selected
        and (
            active_page in {"review", "products", "runs", "history"}
            or view_mode == "run_snapshot"
            or load_runs
        )
        else empty_selected_run_data()
    )
    work_projection = None
    projection_reference_cache: dict[str, dict[str, Any]] = {}
    compatibility_work = (
        _dict_get(work_detail.get("entity_state"), "state_authority")
        == "compatibility"
    )
    if selected_work and active_page == "review" and compatibility_work:
        try:
            work_projection = build_work_stage_projection(backend, selected_work)
        except (FileNotFoundError, ValueError) as exc:
            # A missing/corrupt Work must degrade to explicit unavailable stage
            # data; history remains independently inspectable.
            work_projection = unavailable_work_stage_projection(selected_work, type(exc).__name__)
    provider = build_provider_config_data(backend) if active_page == "config" else {"provider_config": None, "provider_check": None}
    # Home reads recent Work summaries. Building it for every selected-node
    # interaction made the whole workspace pay for data that was not rendered.
    home = (
        build_home_view_model(backend, works, language=language)
        if active_page == "workspace"
        else {}
    )
    data = {
        "workspace": workspace_response["data"] if workspace_response["ok"] else {"present": False, "relative_path": "workspace"},
        "workspace_config": config_response["data"] if config_response["ok"] else {"advancement_mode": "manual_confirm"},
        "works": works,
        "works_pagination": works_page.get("pagination") if isinstance(works_page.get("pagination"), dict) else _empty_pagination(50, 0),
        "work_filters": works_page.get("filters") if isinstance(works_page.get("filters"), dict) else {"show_debug": show_debug_works},
        "selected_work_id": selected_work,
        "selected_work": work_detail,
        "active_page": active_page,
        "show_unclassified_runs": show_unclassified_runs,
        "show_low_level_details": show_low_level_details,
        "selected_node_id": selected_node_id,
        "selected_stage_id": selected_stage_id,
        "language": language,
        "home": home,
        "product_readiness": home.get("environment", {}),
        "selected_node": _selected_node(work_detail, selected_node_id),
        "runs": runs,
        "pagination": pagination,
        "run_filters": run_filters,
        "selected_run_id": selected,
        **provider,
        **run_data,
    }
    if work_projection is not None:
        selected_run = data.get("selected_run") if isinstance(data.get("selected_run"), dict) else {}
        data["work_stage_projection"] = work_projection
        data["workflow_review_surface"] = build_workflow_review_surface(
            backend,
            selected,
            selected_run,
            root=root,
            selected_stage_id=selected_stage_id,
            language=language,
            projection=work_projection,
        )
    data["view_mode"] = "run_snapshot" if view_mode == "run_snapshot" else "current_work"
    if selected_work and active_page in {"overview", "workflow", "parts", "history"}:
        try:
            data["workbench_overview"] = build_workbench_overview_view_model(
                backend,
                selected_work,
                language=language,
                work_detail=work_detail,
                reference_cache=projection_reference_cache,
            )
        except (FileNotFoundError, ValueError):
            data["workbench_overview"] = {}
    if selected_work and active_page == "workflow":
        data["workflow_page"] = build_workflow_page_view_model(
            backend,
            selected_work,
            view_mode="run_snapshot" if view_mode == "run_snapshot" else "current_work",
            selected_run_id=selected_run_id if view_mode == "run_snapshot" else None,
            selected_stage_id=selected_stage_id,
            language=language,
            overview=data.get("workbench_overview"),
            work_detail=work_detail,
            reference_cache=projection_reference_cache,
        )
    return data


def build_selected_work_data(backend: WorkflowConsoleBackend, work_id: str) -> dict[str, Any]:
    """Build the selected Work view-model lazily."""
    response = dispatch_route(backend, "read_work", path_params={"work_id": work_id})
    if not response["ok"]:
        return {**empty_selected_work_data(), "error": response["error"]}
    data = response["data"]
    data["workflow_graph"] = build_workflow_graph_data(data)
    return data


def empty_selected_work_data() -> dict[str, Any]:
    """Return empty Work state for consoles with no inferred Works."""
    return {
        "work_id": None,
        "summary": None,
        "current_state": None,
        "parts": [],
        "nodes": [],
        "workflow_graph": {
            "stage_nodes": [],
            "part_nodes": [],
            "review_nodes": [],
            "has_parts": False,
            "layout": "empty",
        },
        "run_history": [],
        "products": {
            "artifact_state": {
                "accepted_deliverable_count": 0,
                "reviewable_output_count": 0,
                "failed_attempt_output_count": 0,
                "untrusted_output_count": 0,
            },
            "accepted_deliverables": [],
            "reviewable_outputs": [],
            "supporting_artifacts": [],
            "human_facing": [],
            "downloadables": [],
            "artifacts_secondary_by_default": True,
        },
        "available_actions": [],
        "history_semantics": {
            "runs_are_immutable": True,
            "rework_creates_new_runs": True,
            "old_runs_remain_visible": True,
        },
        "error": None,
    }


def build_provider_config_data(backend: WorkflowConsoleBackend) -> dict[str, Any]:
    """Return sanitized provider configuration view data."""
    response = dispatch_route(backend, "read_provider_config")
    return {
        "provider_config": response["data"] if response["ok"] else {"provider_identity": {}},
        "provider_check": None,
    }


def build_workflow_graph_data(work: dict[str, Any]) -> dict[str, Any]:
    """Build a presentation-only workflow graph from Work nodes and parts."""
    nodes = [node for node in work.get("nodes") or [] if isinstance(node, dict)]
    parts = [part for part in work.get("parts") or [] if isinstance(part, dict)]
    by_id = {node.get("id"): node for node in nodes if isinstance(node.get("id"), str)}
    plan_node = by_id.get("assembly_plan") or by_id.get("planning")
    stage_nodes = [
        _graph_node(by_id.get("requirement"), fallback_id="requirement", fallback_label="Requirement"),
        _graph_node(plan_node, fallback_id="planning", fallback_label="Planning"),
    ]
    graph_parts = _workflow_graph_parts(parts)
    part_nodes = [_graph_part_node(part, by_id.get(f"part:{part.get('part_id')}")) for part in graph_parts]
    if not part_nodes:
        synthetic_part = _graph_single_part_node(work)
        if synthetic_part is not None:
            part_nodes.append(synthetic_part)
    if not part_nodes and by_id.get("part"):
        part_nodes.append(_graph_node(by_id.get("part"), fallback_id="part", fallback_label="Part"))
    review_nodes = [_graph_result_node(work)]
    return {
        "stage_nodes": stage_nodes,
        "part_nodes": part_nodes,
        "review_nodes": review_nodes,
        "has_parts": bool(part_nodes),
        "layout": "multi_part" if len(part_nodes) > 1 else ("single_part" if part_nodes else "planning_only"),
    }


def _workflow_graph_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [
        part for part in parts
        if part.get("attempt_count")
        or part.get("has_step")
        or part.get("has_stl")
        or part.get("status") in {"accepted", "completed", "blocked", "needs_review"}
    ]
    return active or parts


def build_selected_run_data(
    backend: WorkflowConsoleBackend,
    run_id: str,
    *,
    root: str | None = None,
    selected_stage_id: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Build all tab view-models for one selected run id."""
    response = dispatch_route(backend, "read_run_metadata", path_params={"run_id": run_id}, query=_query(root))
    if not response["ok"]:
        return {
            **empty_selected_run_data(),
            "error": response["error"],
        }
    run = response["data"]
    artifacts = _artifact_names(run)
    return {
        "selected_run": run,
        "requirement_review": build_requirement_review_data(backend, run_id, run, root=root),
        "assembly_plan": build_assembly_plan_data(run),
        "workflow_review": build_workflow_review_data(run),
        "stage_review": build_stage_review_data(run),
        "part_workflow": build_part_workflow_data(run),
        "workflow_review_surface": build_workflow_review_surface(backend, run_id, run, root=root, selected_stage_id=selected_stage_id, language=language),
        "artifacts_page": build_artifacts_page_data(run),
        "artifact_names": sorted(artifacts),
        "error": None,
    }


def empty_selected_run_data() -> dict[str, Any]:
    """Return empty tab data for consoles with no runs yet."""
    return {
        "selected_run": None,
        "requirement_review": {
            "original_prompt": None,
            "detected_scope": None,
            "product_family": None,
            "part_family": None,
            "assumptions": [],
            "missing_information": [],
            "clarification_questions": [],
            "clarification_requests": [],
            "clarification_applied": False,
            "requirement_v2_present": False,
            "can_run_planning": False,
            "blocked_reason": None,
            "diagnostics": [],
            "notes_enabled": True,
        },
        "assembly_plan": {
            "present": False,
            "scope": None,
            "status": None,
            "part_count": 0,
            "candidate_part_ids": [],
            "reference_only_part_ids": [],
            "blocked_part_ids": [],
            "interface_count": 0,
            "blocked_reasons": [],
            "parts": [],
        },
        "part_workflow": {"actions": []},
        "workflow_review_surface": {
            "stages": [],
            "selected_stage": None,
            "workflow_graph": {"nodes": [], "edges": []},
        },
        "workflow_review": build_workflow_review_data({}),
        "stage_review": build_stage_review_data({}),
        "artifacts_page": {"artifacts": [], "downloadables": [], "model_files": []},
        "artifact_names": [],
        "error": None,
    }


def build_requirement_review_data(
    backend: WorkflowConsoleBackend,
    run_id: str,
    run: dict[str, Any],
    *,
    root: str | None = None,
) -> dict[str, Any]:
    """Return read-only requirement negotiation data with graceful empty states."""
    report_summary = run.get("report_summary") if isinstance(run.get("report_summary"), dict) else {}
    requirement = report_summary.get("requirement_summary") if isinstance(report_summary.get("requirement_summary"), dict) else {}
    planning = report_summary.get("planning_summary") if isinstance(report_summary.get("planning_summary"), dict) else {}
    negotiation = report_summary.get("negotiation") if isinstance(report_summary.get("negotiation"), dict) else {}
    requirement_artifact = _read_public_artifact_content(backend, run_id, "requirement.json", root=root)
    requirement_v2 = _read_public_artifact_content(backend, run_id, "requirement_v2.json", root=root)
    prompt = _read_public_artifact_content(backend, run_id, "prompt.txt", root=root)
    active_requirement = requirement_v2 if isinstance(requirement_v2, dict) else requirement_artifact

    return {
        "original_prompt": prompt if isinstance(prompt, str) else None,
        "detected_scope": _first_present(
            _dict_get(requirement_artifact, "scope"),
            _dict_get(requirement_artifact, "detected_scope"),
            _dict_get(planning, "scope"),
        ),
        "product_family": _first_present(
            _dict_get(requirement_artifact, "product_family"),
            _dict_get(requirement_artifact, "product_type"),
        ),
        "part_family": _first_present(
            _dict_get(requirement_artifact, "part_family"),
            _dict_get(requirement_artifact, "part_type"),
        ),
        "assumptions": _as_list(negotiation.get("assumptions")),
        "missing_information": _as_list(negotiation.get("missing_information")),
        "clarification_questions": _as_list(negotiation.get("clarification_questions")),
        "clarification_requests": _clarification_requests(active_requirement),
        "clarification_applied": isinstance(requirement_v2, dict) and requirement_v2.get("clarification_applied") is True,
        "requirement_v2_present": isinstance(requirement_v2, dict),
        "can_run_planning": _can_run_planning(active_requirement),
        "blocked_reason": negotiation.get("blocked_reason"),
        "diagnostics": _collect_diagnostics(run, requirement, report_summary),
        "notes_enabled": True,
    }


def build_assembly_plan_data(run: dict[str, Any]) -> dict[str, Any]:
    """Return a compact assembly-plan table without raw JSON."""
    reviewed = run.get("reviewed_part_summary") if isinstance(run.get("reviewed_part_summary"), dict) else {}
    assembly = reviewed.get("assembly_plan") if isinstance(reviewed.get("assembly_plan"), dict) else {}
    parts = [_assembly_part_row(part) for part in _as_list(assembly.get("parts")) if isinstance(part, dict)]
    return {
        "present": bool(assembly.get("present")),
        "scope": assembly.get("scope"),
        "status": assembly.get("status"),
        "part_count": assembly.get("part_count") if isinstance(assembly.get("part_count"), int) else len(parts),
        "candidate_part_ids": [part["part_id"] for part in parts if part.get("supported_candidate") and part.get("part_id")],
        "reference_only_part_ids": [part["part_id"] for part in parts if part.get("reference_only") and part.get("part_id")],
        "blocked_part_ids": [
            part["part_id"]
            for part in parts
            if part.get("status") == "blocked" and part.get("part_id")
        ],
        "interface_count": assembly.get("interface_count") if isinstance(assembly.get("interface_count"), int) else 0,
        "blocked_reasons": _as_list(assembly.get("blocked_reason_codes")),
        "parts": parts,
    }


def build_stage_review_data(run: dict[str, Any]) -> dict[str, Any]:
    """Return saved stage-review state plus explicit selector options."""
    summary = run.get("stage_review_summary") if isinstance(run.get("stage_review_summary"), dict) else {}
    rework = run.get("rework_decision_summary") if isinstance(run.get("rework_decision_summary"), dict) else {}
    target = summary.get("target_rework_stage")
    return {
        "saved": summary if summary.get("present") else None,
        "rework_decision": rework if rework.get("present") else None,
        "rework_available": summary.get("review_status") == "needs_revision" and target in {"workflow_review", "assembly_plan", "part_request"},
        "rework_supported": target == "workflow_review",
        "rework_blocked_reason": None
        if target in (None, "workflow_review")
        else "Target rework stage is recorded but execution is not supported in this MVP.",
        "stage_options": sorted(STAGE_REVIEW_STAGES),
        "review_status_options": sorted(STAGE_REVIEW_STATUSES),
        "target_rework_stage_options": sorted(STAGE_REWORK_TARGETS),
    }


def build_workflow_review_data(run: dict[str, Any]) -> dict[str, Any]:
    """Return workflow review summary for the top-level review page."""
    summary = run.get("workflow_review_summary") if isinstance(run.get("workflow_review_summary"), dict) else {}
    return {
        "present": bool(summary.get("present")),
        "overall_status": summary.get("overall_status"),
        "readiness_score": summary.get("readiness_score"),
        "risk_level": summary.get("risk_level"),
        "recommended_next_action_count": summary.get("recommended_next_action_count", 0),
        "risk_count": summary.get("risk_count", 0),
        "summary_preview": _as_list(summary.get("summary_preview")),
        "artifact_availability": summary.get("artifact_availability") if isinstance(summary.get("artifact_availability"), dict) else {},
    }


def build_part_workflow_data(run: dict[str, Any]) -> dict[str, Any]:
    """Return one-stage action cards gated by upstream artifacts."""
    artifacts = _artifact_names(run)
    reviewed = run.get("reviewed_part_summary") if isinstance(run.get("reviewed_part_summary"), dict) else {}
    status_by_key = {
        "part_request": _dict_get(reviewed.get("part_request"), "status"),
        "part_review": _dict_get(reviewed.get("part_request_review"), "status"),
        "reviewed_handoff": _dict_get(reviewed.get("reviewed_part_handoff"), "status"),
        "reviewed_part_create": _dict_get(reviewed.get("lineage"), "relationship"),
        "part_result_review": _dict_get(reviewed.get("part_result_review"), "status"),
    }
    cards = []
    for definition in REVIEWED_PART_ACTIONS:
        missing = [name for name in definition["upstream_artifacts"] if name not in artifacts]
        output = definition["output_artifact"]
        cards.append({
            "key": definition["key"],
            "title": definition["title"],
            "current_status": status_by_key.get(definition["key"]) or ("present" if output in artifacts else "not_started"),
            "required_upstream_artifact": ", ".join(definition["upstream_artifacts"]),
            "output_artifact": output,
            "action": definition["method"],
            "action_label": definition["action_label"],
            "available": not missing,
            "missing_upstream_artifacts": missing,
            "stage_count": 1,
        })
    return {"actions": cards}


def build_artifacts_page_data(
    run: dict[str, Any],
    *,
    show_debug: bool = False,
    show_internal: bool = False,
) -> dict[str, Any]:
    """Return allowlisted artifact and model availability data."""
    artifact_candidates = [
        {
            "name": item["name"],
            "size_bytes": item.get("size_bytes"),
            "updated_at": item.get("updated_at"),
            "collapsed": True,
            "read_on_demand": True,
        }
        for item in _as_list(run.get("artifacts"))
        if isinstance(item, dict)
        and item.get("name") in READABLE_ARTIFACTS
        and (item.get("name") in ARTIFACT_PAGE_ARTIFACTS or item.get("name") in set(REVIEW_SURFACE_ARTIFACTS))
    ]
    artifacts = filter_artifacts_for_display(artifact_candidates, show_debug=show_debug, show_internal=show_internal)
    downloadables = [
        {"name": item["name"], "available": True}
        for item in _as_list(run.get("downloadables"))
        if isinstance(item, dict) and item.get("name") in DOWNLOADABLE_FILES
    ]
    present_downloadables = {item["name"] for item in downloadables}
    model_files = [
        {"name": name, "available": name in present_downloadables}
        for name in ("model.step", "model.stl")
    ]
    return {
        "artifacts": artifacts,
        "downloadables": downloadables,
        "model_files": model_files,
        "show_debug": show_debug,
        "show_internal": show_internal,
    }


def read_artifact_page_content(
    backend: WorkflowConsoleBackend,
    run_id: str,
    artifact: str,
    *,
    root: str | None = None,
) -> dict[str, Any]:
    """Read one allowlisted artifact through the existing public route sanitizer."""
    if artifact not in READABLE_ARTIFACTS or artifact not in set(ARTIFACT_PAGE_ARTIFACTS) | set(REVIEW_SURFACE_ARTIFACTS):
        raise ValueError(f"artifact is not readable by the NiceGUI console: {artifact}")
    response = dispatch_route(
        backend,
        "read_artifact",
        path_params={"run_id": run_id, "artifact": artifact},
        query=_query(root),
    )
    if not response["ok"]:
        error = response["error"] or {}
        raise FileNotFoundError(error.get("message") or artifact)
    artifact_data = response["data"]
    return _drop_path_like_keys(_unwrap_artifact_data(artifact_data))


def create_nicegui_app(backend: WorkflowConsoleBackend | None = None) -> Any:
    """Create the NiceGUI UI. Importing NiceGUI is optional until this is called."""
    try:
        from nicegui import app, ui
        from starlette.background import BackgroundTask
        from starlette.responses import FileResponse
    except ImportError as exc:  # pragma: no cover - exercised only without optional dependency at runtime
        raise RuntimeError("NiceGUI is not installed. Install the web extra, for example: cadflow[web].") from exc

    console_backend = backend or WorkflowConsoleBackend(restore_saved_provider=True)
    actions = WorkflowConsoleActions(console_backend)
    if WEB_VIEWER_ROOT.exists():
        app.add_static_files("/web-viewer", str(WEB_VIEWER_ROOT))

    @app.get("/api/downloads/{run_id}/{filename}")
    def download_file(run_id: str, filename: str, root: str | None = None) -> FileResponse:
        return FileResponse(resolve_downloadable(console_backend, run_id, filename, root=root))

    @app.get("/api/work-artifacts/{work_id}/{artifact_id}/download")
    def download_work_artifact(work_id: str, artifact_id: str) -> FileResponse:
        reference, artifact_path = console_backend.resolve_work_artifact_reference(
            work_id,
            artifact_id,
        )
        if reference.get("trust_role") not in {
            "reviewable_result",
            "accepted_result",
        }:
            raise ValueError("only reviewable or accepted Work artifacts are downloadable")
        return FileResponse(artifact_path, filename=artifact_path.name)

    @app.get("/api/work-artifacts/{work_id}/{artifact_id}/preview.stl")
    def preview_work_step(work_id: str, artifact_id: str) -> FileResponse:
        reference, step_path = console_backend.resolve_work_artifact_reference(
            work_id,
            artifact_id,
        )
        if not (
            reference.get("trust_role") in {"reviewable_result", "accepted_result"}
            and reference.get("validation_status") == "passed"
            and step_path.suffix.lower() in {".step", ".stp"}
        ):
            raise ValueError("only validated reviewable or accepted STEP can be previewed")
        preview_path = _step_preview_stl(step_path)
        return FileResponse(
            preview_path,
            media_type="model/stl",
            background=BackgroundTask(
                lambda path=preview_path: path.unlink(missing_ok=True)
            ),
        )

    state: dict[str, Any] = {
        "_backend": console_backend,
        "selected_work_id": None,
        "selected_run_id": None,
        "selected_node_id": None,
        "selected_stage_id": None,
        "view_mode": "current_work",
        "language": "en",
        "active_page": "workspace",
        "last_action_result": None,
    }

    @ui.page("/")
    def index() -> None:
        ui.add_head_html(f"<style>{WORKFLOW_UI_CSS}</style>")
        with ui.row().classes("workbench-shell w-full gap-0"):
            sidebar = ui.column().classes("sidebar w-80 gap-3 p-4")
            content = ui.column().classes("content flex-1 gap-4 p-5")

            def refresh(*, reproject: bool = True, refresh_sidebar: bool = True) -> None:
                refresh_started = ui_trace_start()
                if refresh_sidebar:
                    sidebar.clear()
                content.clear()
                data = state.get("_page_data") if not reproject else None
                if not isinstance(data, dict):
                    projection_started = ui_trace_start()
                    data = build_console_page_data(
                        console_backend,
                        state.get("selected_run_id"),
                        selected_work_id=state.get("selected_work_id"),
                        active_page=state.get("active_page", "workspace"),
                        selected_node_id=state.get("selected_node_id"),
                        selected_stage_id=state.get("selected_stage_id"),
                        view_mode=state.get("view_mode", "current_work"),
                        language=state.get("language", "en"),
                        show_debug_works=bool(state.get("show_developer_content")),
                        show_unclassified_runs=bool(state.get("show_unclassified_runs")),
                        show_low_level_details=bool(state.get("show_low_level_details")),
                        limit=state.get("limit", DEFAULT_RUN_PAGE_SIZE),
                        offset=state.get("offset", 0),
                        search=state.get("search") or None,
                    )
                    state["_page_data"] = data
                    ui_trace_event(
                        "page_projection",
                        projection_started,
                        page=str(state.get("active_page") or ""),
                    )
                state["selected_work_id"] = data.get("selected_work_id")
                if state.get("view_mode") == "run_snapshot":
                    state["selected_run_id"] = data.get("selected_run_id")
                if refresh_sidebar:
                    sidebar_started = ui_trace_start()
                    with sidebar:
                        _render_sidebar(ui, data, state, select_work, select_page, refresh)
                    ui_trace_event("sidebar_render", sidebar_started)
                content_started = ui_trace_start()
                with content:
                    if state.get("active_page") in {"overview", "workflow", "node", "parts", "review", "products", "runs", "history"}:
                        _render_work_header(ui, data)
                    _render_active_page(ui, data, actions, state, refresh, select_node, select_stage, select_run, select_current_work, select_work, select_page)
                ui_trace_event(
                    "content_render",
                    content_started,
                    page=str(state.get("active_page") or ""),
                )
                ui_trace_event(
                    "page_refresh",
                    refresh_started,
                    reproject=reproject,
                    sidebar=refresh_sidebar,
                )

            def refresh_content_only(*, reproject: bool = True) -> None:
                refresh(reproject=reproject, refresh_sidebar=False)

            def refresh_pending() -> None:
                # Pending is process-local presentation state over the current
                # canonical page projection. The terminal refresh re-reads the
                # backend after the mutation has invalidated its Work index.
                refresh_content_only(reproject=False)

            refresh.pending = refresh_pending  # type: ignore[attr-defined]

            def select_work(work_id: str) -> None:
                _select_console_work(state, work_id, refresh)

            def select_page(page: str) -> None:
                try:
                    _select_console_page(state, page, refresh)
                except ValueError:
                    # This is a safe presentation error for an unexpected UI
                    # callback; it deliberately does not fall back to Overview.
                    state["navigation_error"] = "Unable to open that page."
                    refresh()

            def select_node(node_id: str) -> None:
                state["active_page"] = "node"
                state["selected_node_id"] = node_id
                refresh()

            def select_stage(stage_id: str) -> None:
                selection_started = ui_trace_start()
                state["active_page"] = "workflow"
                state["selected_stage_id"] = stage_id
                cached = state.get("_page_data")
                page = cached.get("workflow_page") if isinstance(cached, dict) else None
                if isinstance(page, dict) and page.get("projection_mode") == "agent_first":
                    try:
                        select_projected_workflow_node(page, stage_id)
                    except ValueError:
                        refresh()
                    else:
                        cached["selected_stage_id"] = stage_id
                        inspector = state.get("_workflow_inspector")
                        if inspector is None:
                            refresh(reproject=False, refresh_sidebar=False)
                        else:
                            # Node selection is a presentation transition. Keep
                            # the graph, sidebar, viewer, and disclosures stable;
                            # only replace the scoped inspector.
                            inspector.clear()
                            inspector_started = ui_trace_start()
                            with inspector:
                                _render_dynamic_node_detail(
                                    ui,
                                    page,
                                    actions,
                                    state,
                                    refresh,
                                    select_run,
                                    str(cached.get("language") or "en"),
                                )
                            ui_trace_event(
                                "workflow_inspector_render",
                                inspector_started,
                                stage_id=stage_id,
                            )
                            encoded_stage = json.dumps(stage_id)
                            ui.run_javascript(
                                "document.querySelectorAll('.dynamic-node').forEach("
                                "node => node.classList.toggle('selected', "
                                f"node.dataset.nodeId === {encoded_stage}));"
                            )
                            ui_trace_event(
                                "workflow_node_selection",
                                selection_started,
                                stage_id=stage_id,
                            )
                else:
                    refresh()

            def select_run(run_id: str) -> None:
                _select_console_run(state, run_id, refresh)

            def select_current_work() -> None:
                _select_current_console_work(state, refresh)

            refresh()

    return app


def _step_preview_stl(step_path: Path) -> Path:
    """Create an ephemeral mesh for the existing STL viewer.

    The source is an exact, locally validated Work artifact.  The mesh is a
    presentation derivative in the system temporary directory: it is never
    registered as product evidence or treated as a deliverable.
    """

    import cadquery as cq

    with tempfile.NamedTemporaryFile(
        prefix="cadflow-preview-",
        suffix=".stl",
        delete=False,
    ) as handle:
        preview_path = Path(handle.name)
    try:
        model = cq.importers.importStep(str(step_path))
        cq.exporters.export(model, str(preview_path))
        if not preview_path.is_file() or preview_path.stat().st_size <= 0:
            raise ValueError("STEP preview conversion produced no mesh")
        return preview_path
    except Exception:
        preview_path.unlink(missing_ok=True)
        raise


def _render_sidebar(
    ui: Any,
    data: dict[str, Any],
    state: dict[str, Any],
    on_select_work: Callable[[str], None],
    on_select_page: Callable[[str], None],
    refresh: Callable[[], None],
) -> None:
    workspace = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    ui.label("CadFlow").classes("text-2xl font-semibold")
    ui.label("Work Console").classes("text-sm text-gray-500")
    language = ui.select(
        {"en": "English", "zh": "中文"},
        value=state.get("language", "en"),
        label="Language / 语言",
        on_change=lambda event: _set_console_language(state, event.value, refresh),
    ).props("dense outlined").classes("w-full")
    language.tooltip("Changes display language only; workflow artifacts and actions are unchanged.")
    ui.button("Refresh", icon="refresh", on_click=refresh).props("outline dense").classes("w-full").tooltip("重新读取当前 workspace、work 和页面数据。")
    language_code = str(data.get("language") or "en")
    for page, icon, text in (
        ("workspace", "home", "首页" if language_code == "zh" else "Home"),
        ("works", "workspaces", "设计项目" if language_code == "zh" else "Works"),
        ("config", "settings", "设置" if language_code == "zh" else "Settings"),
    ):
        button = ui.button(text, icon=icon, on_click=_page_selection_callback(on_select_page, page))
        button.props("flat dense" if state.get("active_page") != page else "unelevated dense color=primary").classes("nav-btn")
        button.tooltip(_nav_help(page))
    ui.label(f"Workspace: {workspace.get('name') or 'workspace'}").classes("text-xs text-gray-500")
    ui.label(workspace.get("display_path") or workspace.get("relative_path") or "workspace").classes("text-xs text-gray-500 break-all")
    ui.separator()
    ui.label("当前设计" if language_code == "zh" else "Current Designs").classes("text-sm font-medium text-gray-500")
    for work in data.get("works") or []:
        _render_sidebar_work_item(ui, work, data, state, on_select_work, on_select_page)


def _set_console_language(state: dict[str, Any], value: Any, refresh: Callable[[], None]) -> None:
    state["language"] = "zh" if value == "zh" else "en"
    refresh()


def _render_sidebar_work_item(
    ui: Any,
    work: dict[str, Any],
    data: dict[str, Any],
    state: dict[str, Any],
    on_select_work: Callable[[str], None],
    on_select_page: Callable[[str], None],
) -> None:
    selected = work.get("work_id") == data.get("selected_work_id")
    counts = work.get("part_counts") if isinstance(work.get("part_counts"), dict) else {}
    status = work.get("overall_status") or "unknown"
    item_classes = "work-tree-item work-tree-item-active" if selected else "work-tree-item"
    with ui.column().classes("w-full gap-1"):
        row = ui.row().classes(item_classes + " items-start gap-2")
        row.on("click", lambda _event, w=work: on_select_work(w["work_id"]))
        with row:
            ui.icon("folder_open" if selected else "folder").classes("text-blue-500 mt-1")
            with ui.column().classes("gap-1 flex-1 min-w-0"):
                ui.label(work.get("title") or work.get("work_id")).classes("text-sm font-medium leading-snug line-clamp-2")
                with ui.row().classes("items-center gap-2"):
                    ui.badge(status).classes(_badge_class(status))
                    ui.label(_sidebar_part_count_label(counts)).classes("text-xs text-gray-500")
        if selected:
            with ui.column().classes("work-page-tree w-full gap-1"):
                for page, icon, text in WORK_USER_PAGES:
                    localized = {
                        "overview": i18n_copy(str(data.get("language") or "en"), "overview_design"),
                        "workflow": i18n_copy(str(data.get("language") or "en"), "detailed_workflow"),
                        "parts": i18n_copy(str(data.get("language") or "en"), "part_jobs"),
                        "history": i18n_copy(str(data.get("language") or "en"), "history"),
                    }.get(page, text)
                    item = ui.button(localized, icon=icon, on_click=_page_selection_callback(on_select_page, page))
                    item.props("flat dense" if state.get("active_page") != page else "unelevated dense color=secondary")
                    item.classes("work-page-btn")
                    item.tooltip(_nav_help(page))


def _render_work_header(ui: Any, data: dict[str, Any]) -> None:
    summary = _dict_get(data.get("selected_work"), "summary") or {}
    if not summary:
        ui.label("No Work selected").classes("text-2xl font-semibold")
        return
    language = str(data.get("language") or "en")
    overview = data.get("workbench_overview") if isinstance(data.get("workbench_overview"), dict) else {}
    workbench_work = overview.get("work") if isinstance(overview.get("work"), dict) else {}
    phase = overview.get("phase") if isinstance(overview.get("phase"), dict) else {}
    counts = summary.get("part_counts") if isinstance(summary.get("part_counts"), dict) else {}
    with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
        with ui.column().classes("gap-1"):
            ui.label(summary.get("title") or summary.get("work_id")).classes("text-2xl font-semibold")
            if workbench_work.get("active_part"):
                ui.label(
                    ("当前零件：" if language == "zh" else "Active part: ")
                    + str(workbench_work["active_part"])
                ).classes("text-sm text-gray-600")
        with ui.row().classes("gap-2"):
            if phase.get("label"):
                ui.badge(phase["label"]).classes("bg-blue-600")
            part_count = int(workbench_work.get("part_count") or counts.get("total") or 0)
            ui.badge(
                f"{part_count} 个零件" if language == "zh" else f"{part_count} Part{'s' if part_count != 1 else ''}"
            ).classes("bg-slate-600")
            if workbench_work.get("accepted_part_count"):
                ui.badge(
                    f"已接受 {workbench_work['accepted_part_count']} 个" if language == "zh" else f"{workbench_work['accepted_part_count']} accepted"
                ).classes("bg-green-700")
    if phase.get("items"):
        with ui.element("div").classes("workbench-phase"):
            for item in phase["items"]:
                ui.label(item.get("label") or "").classes(
                    "workbench-phase-item" + (" current" if item.get("current") else "")
                )


def _render_active_page(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    on_select_node: Callable[[str], None],
    on_select_stage: Callable[[str], None],
    on_select_run: Callable[[str], None],
    on_select_current_work: Callable[[], None],
    on_select_work: Callable[[str], None],
    on_select_page: Callable[[str], None],
) -> None:
    page = data.get("active_page") or "overview"
    if state.pop("navigation_error", None):
        ui.label("Unable to open that page. Select a page from the navigation.").classes("text-negative")
    if page == "workspace":
        _render_workspace_page(ui, data, state, refresh, on_select_work)
    elif page == "works":
        _render_works(ui, data, state, on_select_work, refresh)
    elif page == "overview":
        _render_work_overview(ui, data, actions, state, refresh, on_select_page)
    elif page == "workflow":
        _render_workflow_page_v2(ui, data, actions, state, refresh, on_select_stage, on_select_run, on_select_current_work)
    elif page == "node":
        _render_node_detail(ui, data, actions, state, refresh, on_back_to_workflow=lambda: on_select_page("workflow"))
    elif page == "parts":
        _render_parts_matrix(ui, data)
    elif page == "review":
        _render_workflow_review(ui, data, actions, state, refresh)
        _render_part_workflow(ui, data, actions, state, refresh)
    elif page == "products":
        _render_work_products(ui, data)
        _render_artifacts(ui, data, console_backend_from_actions(actions))
    elif page in {"runs", "history"}:
        _render_runs(ui, data, state, on_select_run, refresh)
    elif page == "config":
        _render_config(ui, data, actions.backend, state, refresh)
    else:
        ui.label(f"Unknown page: {page}").classes("text-negative")


def console_backend_from_actions(actions: WorkflowConsoleActions) -> WorkflowConsoleBackend:
    return actions.backend


def _render_workspace_page(
    ui: Any,
    data: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
    on_select_work: Callable[[str], None],
) -> None:
    workspace = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
    home = data.get("home") if isinstance(data.get("home"), dict) else {}
    environment = home.get("environment") if isinstance(home.get("environment"), dict) else {}
    language = str(data.get("language") or "en")
    _render_action_feedback_panel(ui, state, language)
    with ui.row().classes("w-full items-start justify-between gap-4 flex-wrap"):
        with ui.column().classes("gap-1"):
            ui.label("开始一个 CAD 设计" if language == "zh" else "Start a CAD design").classes("text-3xl font-semibold")
            ui.label(
                "描述你要创建的零件，CadFlow Agent 会设计、构建并验证几何。" if language == "zh"
                else "Describe the part you need. The CadFlow Agent will design, build, and validate its geometry."
            ).classes("text-base text-gray-600 max-w-2xl")
        with ui.row().classes("gap-2"):
            _new_design_dialog_button(ui, state, refresh, language)

    ui.label(i18n_copy(language, "product_examples")).classes("text-xl font-semibold")
    ui.label(
        "开始产品示例：两个示例用途不同，一个展示真实 Agent 过程，一个展示稳定的完成结果。" if language == "zh"
        else "These teach different things: one shows a real Agent process; one shows a stable completed result."
    ).classes("text-sm text-gray-600")
    examples = home.get("product_examples") if isinstance(home.get("product_examples"), list) else []
    with ui.element("section").classes("workbench-primary-grid w-full"):
        for example in examples:
            if not isinstance(example, dict):
                continue
            with ui.element("article").classes("workbench-panel"):
                with ui.row().classes("w-full items-start justify-between gap-2"):
                    ui.label(str(example.get("title") or "Example")).classes("text-lg font-semibold")
                    ui.badge(str(example.get("badge") or "")).classes("bg-purple-700" if example.get("key") == "live_agent" else "bg-green-700")
                ui.label(str(example.get("demonstrates") or "")).classes("text-sm text-gray-700 mt-2")
                for label, key in (
                    ("你会看到" if language == "zh" else "You will see", "will_see"),
                    ("你可以尝试" if language == "zh" else "You can try", "can_try"),
                    ("要求" if language == "zh" else "Requirements", "requirements"),
                ):
                    ui.label(f"{label}: {example.get(key) or '—'}").classes("text-xs text-gray-600 mt-1")
                work_id = example.get("work_id")
                if isinstance(work_id, str):
                    ui.button(str(example.get("action") or "Open"), icon="arrow_forward", on_click=lambda _event=None, wid=work_id: on_select_work(wid)).props("outline").classes("mt-3")
                elif example.get("key") == "live_agent":
                    ui.button(str(example.get("action") or "Start"), icon="science", on_click=lambda: _schedule_action(_start_live_product_example_async(state.get("_backend"), state, refresh, language))).props("outline").classes("mt-3")
                else:
                    ui.button(str(example.get("action") or "Create"), icon="view_in_ar", on_click=lambda: _schedule_action(_open_product_example_async(state.get("_backend"), state, refresh, language))).props("outline").classes("mt-3")

    with ui.element("section").classes("workbench-primary-grid w-full"):
        for key, label in (("provider", "AI Provider"), ("local_execution", "Local CAD execution")):
            readiness = environment.get(key) if isinstance(environment.get(key), dict) else {}
            ready = readiness.get("ready") is True
            with ui.element("article").classes("workbench-panel"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(label if language != "zh" else ("AI Provider" if key == "provider" else "本地 CAD 执行")).classes("font-semibold")
                    ui.badge("Ready" if ready else ("需要设置" if language == "zh" else "Needs setup")).classes("bg-green-700" if ready else "bg-amber-700")
                detail = readiness.get("model") or readiness.get("runtime") or readiness.get("status")
                ui.label(str(detail or "—")).classes("text-sm text-gray-600")
                if not ready:
                    ui.button("打开设置" if language == "zh" else "Open Settings", icon="settings", on_click=lambda: _go_to_settings(state, refresh)).props("flat dense")

    ui.label("最近设计" if language == "zh" else "Recent Works").classes("text-xl font-semibold")
    recent = home.get("recent_works") if isinstance(home.get("recent_works"), list) else []
    if not recent:
        ui.label("还没有设计。新建设计开始。" if language == "zh" else "No designs yet. Start with New Design.").classes("text-gray-600")
    for item in recent[:8]:
        with ui.card().classes("w-full shadow-none border border-gray-200"):
            with ui.row().classes("w-full items-center justify-between gap-3"):
                with ui.column().classes("gap-1"):
                    ui.label(item.get("title") or item.get("work_id")).classes("font-semibold")
                    ui.label(f"{item.get('phase')} · {item.get('state')} · {item.get('updated')}").classes("text-sm text-gray-600")
                    ui.label(str(item.get("next_action") or "")).classes("text-sm text-blue-700")
                ui.button("打开" if language == "zh" else "Open", icon="arrow_forward", on_click=lambda _event=None, work=item: on_select_work(work["work_id"])).props("flat")

    with ui.expansion("高级工作区" if language == "zh" else "Advanced workspace", icon="tune").classes("w-full"):
        ui.label(workspace.get("display_path") or "No workspace path").classes("text-sm text-gray-600 break-all")
        with ui.row().classes("gap-2"):
            _workspace_dialog_button(ui, "New Workspace", "create_new_folder", "create", workspace, state, refresh)
            _workspace_dialog_button(ui, "Load Workspace", "folder_open", "load", workspace, state, refresh)


def _render_work_directory_map(ui: Any, directory_map: dict[str, Any]) -> None:
    _label_with_help(ui, "Work structure", "按 Work 组织输入、规划、零件、交付物和历史；调试文件不会出现在此处。", "text-lg font-medium")
    with ui.element("div").classes("stage-detail-grid w-full"):
        for key in ("inputs", "planning", "parts", "deliverables", "history"):
            group = directory_map.get(key) if isinstance(directory_map.get(key), dict) else {}
            with ui.element("section").classes("stage-detail-card"):
                ui.html(f"<h3>{group.get('title') or key.title()}</h3>")
                items = group.get("items") if isinstance(group.get("items"), list) else []
                if not items:
                    ui.label("Not available yet.").classes("text-sm text-gray-500")
                for item in items[:6]:
                    if isinstance(item, dict):
                        with ui.row().classes("w-full items-center justify-between gap-2"):
                            ui.label(item.get("label") or "").classes("text-sm text-gray-700")
                            ui.badge(item.get("status") or "not_started").classes(_badge_class(item.get("status")))


def _workspace_dialog_button(
    ui: Any,
    label: str,
    icon: str,
    action: str,
    workspace: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[640px] max-w-full"):
        _label_with_help(ui, label, "创建或加载一个明确的 workspace 根目录，避免误用默认路径。", "text-xl font-semibold")
        ui.label("Choose an explicit local workspace path. The path can be outside this repository.").classes("text-sm text-gray-600")
        default_path = workspace.get("relative_path") or ("" if workspace.get("is_external") else "workspace")
        with ui.row().classes("w-full items-center gap-2"):
            path = ui.input("Workspace path", value=default_path).classes("flex-1")
            _help_icon(ui, "workspace 的完整本地路径。可以在仓库外，例如 D:\\CadFlowWorkspaces\\client_a。")
        with ui.row().classes("w-full items-center gap-2"):
            name = ui.input("Workspace name", value=workspace.get("name") or "workspace").classes("flex-1")
            _help_icon(ui, "显示用名称，只用于帮助你识别当前 workspace，不影响文件路径。")
        include_examples = None
        if action != "load":
            with ui.row().classes("w-full items-center gap-2"):
                include_examples = ui.checkbox("Include example Works", value=False)
                _help_icon(ui, "初始化 3 个静态示例 Work：单 part、多 part planning、以及多 part 中推进一个 part。不会调用 provider 或 CAD。")
        ui.label(
            "New initializes workspace.json/config.json. Load only accepts an existing initialized workspace."
            if action == "load"
            else "New creates the directory if needed and initializes workspace.json/config.json. Optional examples are copied into this workspace."
        ).classes("text-sm text-gray-600")
        with ui.row().classes("gap-2 justify-end"):
            ui.button("Cancel", on_click=dialog.close).props("outline").tooltip("关闭弹框，不改变当前 workspace。")
            ui.button(
                "Confirm",
                icon="check",
                on_click=lambda: _confirm_workspace_dialog(
                    action,
                    path.value,
                    name.value,
                    bool(include_examples.value) if include_examples is not None else False,
                    state,
                    refresh,
                    dialog,
                ),
            ).tooltip("确认创建或加载该 workspace。")
    ui.button(label, icon=icon, on_click=dialog.open).props("outline").tooltip("打开路径确认弹框。")


def _confirm_workspace_dialog(
    action: str,
    path: str | None,
    name: str | None,
    include_examples: bool,
    state: dict[str, Any],
    refresh: Callable[[], None],
    dialog: Any,
) -> None:
    dialog.close()
    if action == "load":
        _load_workspace_ui(path, state, refresh)
    else:
        _create_workspace_ui(path, name, include_examples, state, refresh)


def _render_work_overview(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    on_select_page: Callable[[str], None],
) -> None:
    """Evolve the existing Overview into the primary Agent-first Work surface."""

    overview = data.get("workbench_overview") if isinstance(data.get("workbench_overview"), dict) else {}
    language = str(data.get("language") or "en")
    if not overview:
        ui.label("Work overview is unavailable." if language != "zh" else "Work 概览当前不可用。").classes("text-negative")
        return
    work = overview.get("work") if isinstance(overview.get("work"), dict) else {}
    objective = overview.get("objective") if isinstance(overview.get("objective"), dict) else {}
    user_input = overview.get("user_input") if isinstance(overview.get("user_input"), dict) else {}
    agent_design = overview.get("agent_design") if isinstance(overview.get("agent_design"), dict) else {}
    transformation = overview.get("transformation") if isinstance(overview.get("transformation"), dict) else {}
    recommendation = overview.get("recommendation") if isinstance(overview.get("recommendation"), dict) else {}
    capability = overview.get("capability") if isinstance(overview.get("capability"), dict) else {}
    activity = overview.get("agent_activity") if isinstance(overview.get("agent_activity"), dict) else {}
    preview = overview.get("preview") if isinstance(overview.get("preview"), dict) else {}
    result = overview.get("current_result") if isinstance(overview.get("current_result"), dict) else None
    recovery = overview.get("recovery") if isinstance(overview.get("recovery"), dict) else None
    agent_output = overview.get("agent_output") if isinstance(overview.get("agent_output"), dict) else {}
    active_job = next(
        (
            item
            for item in overview.get("part_jobs", [])
            if isinstance(item, dict) and item.get("part_job_id") == work.get("active_part")
        ),
        None,
    )

    _render_action_feedback_panel(ui, state, language)
    if recovery:
        _render_recovery_card(ui, recovery, overview, actions.backend, state, refresh, language)
    has_agent_design = agent_design.get("evidence_status") in {
        "persisted_summary",
        "persisted_work_design",
    }
    with ui.element("section").classes(
        "workbench-narrative-grid w-full" + ("" if has_agent_design else " request-only")
    ):
        with ui.element("article").classes("workbench-request workbench-panel"):
            with ui.row().classes("w-full items-start justify-between gap-3"):
                ui.label(user_input.get("title") or i18n_copy(language, "your_request")).classes("workflow-eyebrow")
                ui.badge(user_input.get("source_label") or "").classes("bg-blue-700")
            ui.label(user_input.get("original_request") or objective.get("summary") or "—").classes(
                "text-lg font-semibold leading-relaxed mt-2"
            )
            if user_input.get("revision_request"):
                with ui.element("div").classes("workbench-revision-request mt-3"):
                    ui.label(i18n_copy(language, "request_source_revision")).classes("workflow-eyebrow")
                    ui.label(str(user_input["revision_request"])).classes("text-base font-medium")
            constraints = user_input.get("visible_constraints") if isinstance(user_input.get("visible_constraints"), list) else []
            if constraints:
                ui.label(i18n_copy(language, "visible_constraints")).classes("workflow-eyebrow mt-3")
                with ui.row().classes("w-full gap-2 flex-wrap"):
                    for item in constraints:
                        ui.badge(str(item)).classes("bg-slate-100 text-slate-700")

        if has_agent_design:
            _render_agent_design_summary(ui, agent_design, capability, language)

    if not recovery:
        _render_overview_current_task(
            ui,
            recommendation,
            active_job,
            result,
            overview,
            actions.backend,
            state,
            refresh,
            language,
        )

    has_preview = bool(preview.get("viewer_url"))
    completed_events = [
        event
        for event in transformation.get("events", [])
        if isinstance(event, dict) and event.get("status") == "completed"
    ]
    # Normal Work setup milestones are not Agent activity. Show this surface
    # only when persisted Agent evidence exists for the selected scope.
    has_activity = bool(agent_output.get("items"))

    # The current engineering artifact becomes the visual center only when it
    # exists. New Work and Work Design therefore do not receive an empty CAD
    # dashboard, while a reviewable result places geometry ahead of telemetry.
    if has_preview:
        with ui.element("section").classes("w-full"):
            _render_overview_geometry(ui, preview, language)

    if result:
        _render_workbench_result(
            ui, result, overview, actions.backend, state, refresh, language, show_actions=False
        )
    elif recommendation.get("key") == "start_design":
        _render_workbench_start_design(ui, data, state, refresh, language)

    if has_activity:
        with ui.element("article").classes("workbench-panel workbench-activity"):
            ui.label(i18n_copy(language, "agent_activity")).classes("workflow-eyebrow")
            with ui.row().classes("items-center gap-3 mt-2"):
                ui.icon("smart_toy").classes("text-2xl text-blue-600")
                ui.label(activity.get("label") or "—").classes("text-lg font-semibold")
            ui.label(activity.get("summary") or "").classes("text-sm text-gray-700 mt-1")
            if completed_events:
                with ui.expansion(
                    transformation.get("title") or i18n_copy(language, "what_happened"),
                    icon="timeline",
                ).classes("w-full mt-2"):
                    for event in completed_events:
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("check_circle", size="xs").classes("text-green-700")
                            ui.label(str(event.get("label") or "")).classes("text-sm")
        render_agent_activity(ui, agent_output, language, backend=actions.backend)

    parts = [item for item in overview.get("part_jobs", []) if isinstance(item, dict)]
    if len(parts) > 1:
        _render_workbench_parts_summary(ui, overview, on_select_page, language)

    with ui.row().classes("w-full gap-2 flex-wrap"):
        ui.button(
            i18n_copy(language, "detailed_workflow"),
            icon="account_tree",
            on_click=_page_selection_callback(on_select_page, "workflow"),
        ).props("outline")
        if len(parts) > 1:
            ui.button(
                i18n_copy(language, "part_jobs"),
                icon="view_list",
                on_click=_page_selection_callback(on_select_page, "parts"),
            ).props("flat")
        history = overview.get("history") if isinstance(overview.get("history"), dict) else {}
        if int(history.get("run_count") or 0) > 1:
            ui.button(
                i18n_copy(language, "history"),
                icon="history",
                on_click=_page_selection_callback(on_select_page, "history"),
            ).props("flat")

    _render_workbench_advanced(ui, overview, language)


def _render_agent_design_summary(
    ui: Any,
    agent_design: dict[str, Any],
    capability: dict[str, Any],
    language: str,
) -> None:
    with ui.element("article").classes("workbench-design workbench-panel"):
        with ui.row().classes("w-full items-start justify-between gap-3"):
            ui.label(agent_design.get("title") or i18n_copy(language, "agent_design")).classes("workflow-eyebrow")
            ui.badge(capability.get("label") or "").classes(
                "bg-purple-700 workbench-capability"
                if capability.get("experimental")
                else "bg-slate-600 workbench-capability"
            )
        ui.label(agent_design.get("summary") or "—").classes(
            "text-lg font-semibold leading-relaxed mt-2"
        )
        if agent_design.get("geometry_strategy"):
            ui.label(i18n_copy(language, "geometry_strategy")).classes("workflow-eyebrow mt-3")
            ui.label(str(agent_design["geometry_strategy"])).classes("text-sm text-gray-700")
        parameters = [
            item
            for item in agent_design.get("important_parameters", [])
            if isinstance(item, dict)
        ]
        if parameters:
            with ui.row().classes("w-full gap-2 flex-wrap mt-3"):
                for item in parameters:
                    label = f"{item.get('name')}: {item.get('value')} {item.get('unit') or ''}".strip()
                    ui.badge(label).classes("bg-indigo-50 text-indigo-800")
        features = [str(item) for item in agent_design.get("functional_features", [])]
        if features:
            with ui.expansion(i18n_copy(language, "functional_features"), icon="construction").classes("w-full mt-2"):
                for item in features:
                    ui.label(f"• {item}").classes("text-sm")
        if capability.get("key") == "reproducible_product_golden":
            ui.label(i18n_copy(language, "product_golden_scope")).classes("text-xs text-purple-800 mt-2")


def _render_overview_current_task(
    ui: Any,
    recommendation: dict[str, Any],
    active_job: dict[str, Any] | None,
    result: dict[str, Any] | None,
    overview: dict[str, Any],
    backend: WorkflowConsoleBackend,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> None:
    task_state = str((active_job or {}).get("state") or "ready")
    execution = state.get("action_execution") if isinstance(state.get("action_execution"), dict) else {}
    action_running = execution.get("status") == "pending"
    user_state = {
        "design": "ready",
        "reviewable": "review",
        "accepted": "accepted",
        "not_started": "ready",
    }.get(task_state, "ready")
    if action_running:
        user_state = "running"
    state_label = {
        "ready": "就绪" if language == "zh" else "Ready",
        "running": "运行中" if language == "zh" else "Running",
        "review": "待审查" if language == "zh" else "Review",
        "accepted": "已接受" if language == "zh" else "Accepted",
    }.get(user_state, task_state)
    with ui.element("section").classes("workbench-recommendation w-full"):
        with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label("当前任务" if language == "zh" else "CURRENT TASK").classes("workflow-eyebrow")
                title = (active_job or {}).get("name") or recommendation.get("label") or "—"
                ui.label(str(title)).classes("text-lg font-semibold")
                ui.label(str(recommendation.get("summary") or "")).classes("text-sm text-gray-600")
            with ui.row().classes("items-center gap-2 flex-wrap"):
                ui.label(state_label).classes(f"workflow-state-pill {user_state}")
                key = str(recommendation.get("key") or "")
                if key == "continue_work_design":
                    button = ui.button(
                        recommendation.get("label") or ("继续 Work 设计" if language == "zh" else "Continue Work Design"),
                        icon="account_tree",
                        on_click=lambda: _show_continue_work_design_confirmation(
                            ui, backend, overview, state, refresh, language
                        ),
                    ).props("color=primary")
                    if action_running:
                        button.disable()
                elif key == "continue_agent" and active_job:
                    part_label = str(active_job.get("name") or active_job.get("part_job_id") or "Part")
                    button = ui.button(
                        f"继续 {part_label}" if language == "zh" else f"Continue {part_label}",
                        icon="play_arrow",
                        on_click=lambda: _show_continue_agent_confirmation(
                            ui, backend, overview, state, refresh, language
                        ),
                    ).props("color=primary")
                    if action_running:
                        button.disable()
                elif result and result.get("reviewable_result_id") and key == "accept_reviewable_result":
                    part_id = str((active_job or {}).get("part_job_id") or "")
                    result_id = str(result["reviewable_result_id"])
                    ui.button(
                        i18n_copy(language, "accept_result"),
                        icon="check_circle",
                        on_click=lambda: _show_accept_result_confirmation(
                            ui,
                            backend,
                            str(_dict_get(overview.get("advanced"), "work_id")),
                            part_id,
                            result_id,
                            state,
                            refresh,
                            language,
                        ),
                    ).props("color=positive")
                    ui.button(
                        i18n_copy(language, "revise"),
                        icon="edit",
                        on_click=lambda: _show_revision_dialog(
                            ui,
                            backend,
                            str(_dict_get(overview.get("advanced"), "work_id")),
                            part_id,
                            result_id,
                            state,
                            refresh,
                            language,
                        ),
                    ).props("flat")
                elif result and result.get("reviewable_result_id") and key == "revise_reviewable_result":
                    ui.button(
                        i18n_copy(language, "revise"),
                        icon="edit",
                        on_click=lambda: _show_revision_dialog(
                            ui,
                            backend,
                            str(_dict_get(overview.get("advanced"), "work_id")),
                            str((active_job or {}).get("part_job_id") or ""),
                            str(result["reviewable_result_id"]),
                            state,
                            refresh,
                            language,
                        ),
                    ).props("outline")


def _render_overview_geometry(ui: Any, preview: dict[str, Any], language: str) -> None:
    with ui.element("article").classes("workbench-panel workbench-geometry has-preview"):
        with ui.row().classes("w-full items-center justify-between gap-2"):
            ui.label(i18n_copy(language, "geometry_preview")).classes("workflow-eyebrow")
            ui.badge(preview.get("label") or i18n_copy(language, "preview_unavailable")).classes(
                _badge_class(preview.get("status"))
            )
        ui.html(
            f'<iframe class="workbench-viewer" title="Geometry preview" '
            f'src="{html_escape(str(preview["viewer_url"]), quote=True)}"></iframe>',
            sanitize=False,
        ).classes("w-full mt-3")
        geometry = preview.get("geometry") if isinstance(preview.get("geometry"), dict) else {}
        bbox = geometry.get("bounding_box") if isinstance(geometry.get("bounding_box"), dict) else {}
        if geometry:
            with ui.row().classes("w-full gap-2 flex-wrap mt-2"):
                ui.badge(
                    f"{('边界框' if language == 'zh' else 'Bounding box')}: "
                    f"{bbox.get('x', '—')} × {bbox.get('y', '—')} × {bbox.get('z', '—')} mm"
                ).classes("bg-slate-100 text-slate-800")
                ui.badge(
                    f"{('实体数' if language == 'zh' else 'Solid count')}: {geometry.get('solid_count', '—')}"
                ).classes("bg-slate-100 text-slate-800")
        if preview.get("download_url"):
            ui.link("STEP", preview["download_url"]).classes("text-sm mt-2")


def _render_recovery_card(
    ui: Any,
    recovery: dict[str, Any],
    overview: dict[str, Any],
    backend: WorkflowConsoleBackend,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> None:
    owner_labels = {
        "user": "需要你的输入" if language == "zh" else "Needs your input",
        "configuration": "设置问题" if language == "zh" else "Setup issue",
        "environment": "本机环境" if language == "zh" else "Local environment",
        "cadflow": "CadFlow 已安全停止" if language == "zh" else "CadFlow stopped safely",
        "agent": "Agent 动作需要更正" if language == "zh" else "Agent action needs correction",
        "unknown_historical": "历史证据" if language == "zh" else "Historical evidence",
        "unsupported": "当前不支持" if language == "zh" else "Not currently supported",
    }
    with ui.element("section").classes("workflow-action-feedback failed w-full"):
        with ui.row().classes("w-full items-start justify-between gap-3"):
            with ui.column().classes("gap-1"):
                ui.label(owner_labels.get(str(recovery.get("resolution_owner")), "Recovery")).classes("workflow-eyebrow")
                if not recovery.get("typed_stop_reason"):
                    ui.label(str(recovery.get("title") or "Design needs attention")).classes("text-xl font-semibold")
                    ui.label(str(recovery.get("summary") or "")).classes("text-sm")
                    ui.label(str(recovery.get("why_it_stopped") or "")).classes("text-xs text-gray-600")
        if recovery.get("typed_stop_reason"):
            render_stopped_attempt(ui, recovery, language)
        action = recovery.get("recommended_action") if isinstance(recovery.get("recommended_action"), dict) else {}
        key = action.get("key")
        with ui.row().classes("gap-2 mt-3 flex-wrap"):
            if key == "open_settings" or key == "check_environment":
                ui.button(action.get("label") or "Open Settings", icon="settings", on_click=lambda: _go_to_settings(state, refresh)).props("color=primary")
            elif key in {"retry_agent", "start_new_attempt"}:
                recovery_part_job_id = recovery.get("part_job_id")
                active_part_job_id = (
                    recovery_part_job_id
                    if isinstance(recovery_part_job_id, str) and recovery_part_job_id
                    else _dict_get(overview.get("work"), "active_part")
                )
                active = next((item for item in overview.get("part_jobs", []) if isinstance(item, dict) and item.get("part_job_id") == active_part_job_id), None)
                if active:
                    retry_action = {"key": "retry_agent", "label": action.get("label") or "Start a new attempt", "target_work_id": _dict_get(overview.get("advanced"), "work_id"), "part_job_id": active.get("part_job_id"), "target_run_id": recovery.get("run_id") or active.get("active_attempt_run_id"), **({"recovery_mode": "new_attempt"} if key == "start_new_attempt" else {})}
                    ui.button(action.get("label") or "Start a new attempt", icon="refresh", on_click=lambda: _show_continue_agent_confirmation(ui, backend, overview, state, refresh, language, scoped_action=retry_action)).props("color=primary")
                else:
                    work_action = {"key": "continue_work_design", "label": action.get("label") or "Retry Work Design", "target_work_id": _dict_get(overview.get("advanced"), "work_id"), "target_run_id": recovery.get("run_id")}
                    ui.button(
                        action.get("label") or "Retry Work Design",
                        icon="refresh",
                        on_click=lambda: _show_continue_work_design_confirmation(ui, backend, overview, state, refresh, language, scoped_action=work_action),
                    ).props("color=primary")
            elif key == "answer_question":
                questions = recovery.get("questions") if isinstance(recovery.get("questions"), list) else []
                question = questions[0] if questions and isinstance(questions[0], dict) else {}
                answer = ui.input(str(question.get("question") or recovery.get("summary") or "Answer")).props("outlined").classes("min-w-[320px] flex-1")
                ui.button(
                    action.get("label") or "Answer question",
                    icon="send",
                    on_click=lambda: _schedule_action(_answer_and_continue_agent_async(backend, recovery, question, answer.value, state, refresh, language)),
                ).props("color=primary")
            elif key == "modify_request":
                revision = ui.textarea("修改后的设计要求" if language == "zh" else "Revised design request").props("outlined autogrow").classes("min-w-[360px] flex-1")
                ui.button(action.get("label") or "Modify request", icon="edit", on_click=lambda: _schedule_action(_revise_blocked_request_async(backend, overview, revision.value, state, refresh, language))).props("color=primary")
            else:
                ui.button(action.get("label") or "View technical details", icon="info", on_click=lambda: _show_recovery_details_dialog(ui, recovery, language)).props("outline")
            if key != "view_details":
                ui.button(
                    "查看技术详情" if language == "zh" else "View technical details",
                    icon="info",
                    on_click=lambda: _show_recovery_details_dialog(ui, recovery, language),
                ).props("outline")
        if recovery.get("retryable"):
            ui.label(
                str(
                    recovery.get("retry_reason")
                    or (
                        "可以重试；历史证据和已接受结果保持不变。"
                        if language == "zh"
                        else "Retry is available; historical evidence and accepted results remain unchanged."
                    )
                )
            ).classes("text-xs text-gray-500 mt-2")


def _show_recovery_details_dialog(ui: Any, recovery: dict[str, Any], language: str) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[640px] max-w-full"):
        ui.label("技术详情" if language == "zh" else "Technical details").classes("text-xl font-semibold")
        ui.label(str(recovery.get("why_it_stopped") or recovery.get("summary") or "")).classes("text-sm")
        _key_values(ui, {
            "Typed stop reason": recovery.get("technical_reason") or recovery.get("category"),
            "Last Agent action": recovery.get("last_agent_action") or "Not recorded",
            "Last system observation": recovery.get("last_observation") or "Not recorded",
        })
        history = recovery.get("history") if isinstance(recovery.get("history"), list) else []
        if history:
            with ui.expansion("恢复历史" if language == "zh" else "Recovery history", icon="timeline").classes("w-full"):
                for item in history:
                    if isinstance(item, dict):
                        ui.label(f"{item.get('title')}: {item.get('summary') or item.get('stop_reason') or '—'}").classes("text-sm")
        recommended = recovery.get("recommended_action") if isinstance(recovery.get("recommended_action"), dict) else {}
        if recommended.get("key") and recommended.get("key") != "view_details":
            ui.label(
                ("建议下一步：" if language == "zh" else "Recommended next action: ")
                + str(recommended.get("label") or recommended.get("key"))
            ).classes("text-sm text-blue-700")
        else:
            ui.label(
                "没有自动恢复操作。请保留当前证据，并根据上面的建议继续。" if language == "zh"
                else "No automatic recovery is available. Existing evidence is preserved; continue with the recommendation above."
            ).classes("text-sm text-gray-600")
        ui.button("关闭" if language == "zh" else "Close", on_click=dialog.close).props("outline")
    dialog.open()


def _render_workbench_start_design(
    ui: Any,
    data: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> None:
    summary = _dict_get(data.get("selected_work"), "summary") or {}
    with ui.element("section").classes("workbench-panel w-full"):
        ui.label(i18n_copy(language, "start_design")).classes("text-lg font-semibold")
        prompt = ui.textarea(
            i18n_copy(language, "current_objective"),
            value=state.get("intent_draft") or "",
            placeholder=(
                "描述需要设计的零件、关键尺寸和用途。"
                if language == "zh"
                else "Describe the part, its important dimensions, and intended use."
            ),
        ).props("outlined autogrow").classes("w-full")
        prompt.on_value_change(
            lambda event: state.__setitem__("intent_draft", event.value or "")
        )
        button = ui.button(
            i18n_copy(language, "start_design"),
            icon="play_arrow",
            on_click=lambda: _schedule_action(
                _start_work_intent_async(
                    state.get("_backend"),
                    summary.get("work_id"),
                    prompt.value,
                    state,
                    refresh,
                    language,
                )
            ),
        ).props("color=primary")
        if not summary.get("work_id"):
            button.disable()


def _render_workbench_result(
    ui: Any,
    result: dict[str, Any],
    overview: dict[str, Any],
    backend: WorkflowConsoleBackend,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
    *,
    show_actions: bool = True,
) -> None:
    accepted = result.get("accepted") is True
    with ui.element("section").classes(
        "workbench-result w-full" + (" accepted" if accepted else "")
    ):
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label(result.get("title") or i18n_copy(language, "current_result")).classes("text-xl font-semibold")
                ui.label(
                    f"{('零件' if language == 'zh' else 'Part')}: {result.get('part') or '—'}"
                ).classes("text-sm")
                ui.label(
                    f"{('角色' if language == 'zh' else 'Role')}: {result.get('role') or '—'}"
                ).classes("text-sm text-gray-600")
            ui.badge(
                i18n_copy(language, "result_accepted" if accepted else "result_ready_review")
            ).classes("bg-green-700" if accepted else "bg-amber-700")

        geometry = result.get("geometry") if isinstance(result.get("geometry"), dict) else {}
        bbox = geometry.get("bounding_box") if isinstance(geometry.get("bounding_box"), dict) else {}
        with ui.element("div").classes("workbench-validation-grid w-full mt-4"):
            with ui.column().classes("gap-2"):
                ui.label(i18n_copy(language, "validation")).classes("workflow-eyebrow")
                for item in result.get("verified", []):
                    ui.label(f"✓ {item}").classes("text-sm text-green-800")
                if geometry:
                    ui.label(
                        (
                            f"{('边界框' if language == 'zh' else 'Bounding box')}: "
                            f"{bbox.get('x', '—')} × {bbox.get('y', '—')} × {bbox.get('z', '—')} mm"
                        )
                    ).classes("text-sm")
                    ui.label(
                        f"{('实体数' if language == 'zh' else 'Solid count')}: {geometry.get('solid_count', '—')}"
                    ).classes("text-sm")
                    if geometry.get("volume") is not None:
                        ui.label(
                            f"{('体积' if language == 'zh' else 'Volume')}: {geometry.get('volume')} mm³"
                        ).classes("text-sm")
            with ui.column().classes("gap-2"):
                ui.label(i18n_copy(language, "assumptions")).classes("workflow-eyebrow")
                for item in result.get("assumptions", []):
                    ui.label(f"◇ {item}").classes("text-sm text-blue-800")
                ui.label(i18n_copy(language, "not_verified")).classes("workflow-eyebrow mt-2")
                for item in result.get("unverified", []):
                    ui.label(f"△ {item}").classes("text-sm text-amber-800")
            with ui.column().classes("gap-2"):
                ui.label(i18n_copy(language, "unsupported")).classes("workflow-eyebrow")
                for item in result.get("unsupported", []):
                    ui.label(f"— {item}").classes("text-sm text-red-800")
                ui.label(i18n_copy(language, "not_requested")).classes("workflow-eyebrow mt-2")
                for item in result.get("not_requested", []):
                    ui.label(f"○ {item}").classes("text-sm text-gray-700")
        if result.get("limitations"):
            with ui.expansion(i18n_copy(language, "limitations"), icon="warning_amber").classes("w-full"):
                for item in result["limitations"]:
                    ui.label(f"• {item}").classes("text-sm")

        result_id = result.get("reviewable_result_id")
        part_id = _dict_get(overview.get("work"), "active_part")
        if show_actions and isinstance(result_id, str) and isinstance(part_id, str):
            with ui.row().classes("gap-2 mt-4 flex-wrap"):
                if not accepted:
                    accept = ui.button(
                        i18n_copy(language, "accept_result"),
                        icon="check_circle",
                        on_click=lambda: _show_accept_result_confirmation(
                            ui,
                            backend,
                            str(_dict_get(overview.get("advanced"), "work_id")),
                            part_id,
                            result_id,
                            state,
                            refresh,
                            language,
                        ),
                    ).props("color=positive")
                    if _pending_action_matches(
                        state,
                        {
                            "key": "accept_reviewable_result",
                            "target_work_id": _dict_get(overview.get("advanced"), "work_id"),
                            "part_job_id": part_id,
                        },
                    ):
                        accept.disable()
                if not result.get("revision_in_progress"):
                    ui.button(
                        i18n_copy(language, "revise"),
                        icon="edit",
                        on_click=lambda: _show_revision_dialog(
                            ui,
                            backend,
                            str(_dict_get(overview.get("advanced"), "work_id")),
                            part_id,
                            result_id,
                            state,
                            refresh,
                            language,
                        ),
                    ).props("outline")


def _render_workbench_parts_summary(
    ui: Any,
    overview: dict[str, Any],
    on_select_page: Callable[[str], None] | None,
    language: str,
) -> None:
    parts = [item for item in overview.get("part_jobs", []) if isinstance(item, dict)]
    with ui.element("section").classes("workbench-panel w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(i18n_copy(language, "part_jobs")).classes("text-lg font-semibold")
            if on_select_page is not None:
                ui.button(
                    i18n_copy(language, "details"),
                    icon="arrow_forward",
                    on_click=_page_selection_callback(on_select_page, "parts"),
                ).props("flat dense")
        if not parts:
            ui.label(
                "尚未创建零件任务。" if language == "zh" else "No Part Jobs have been created yet."
            ).classes("text-sm text-gray-500")
            return
        with ui.element("div").classes("workbench-part-grid w-full mt-3"):
            for part in parts:
                card = ui.element("article").classes("workbench-part-card")
                if on_select_page is not None:
                    card.on(
                        "click",
                        lambda _event: on_select_page("workflow"),
                    )
                with card:
                    with ui.row().classes("w-full items-start justify-between gap-2"):
                        with ui.column().classes("gap-1"):
                            ui.label(part.get("name") or part.get("part_job_id") or "Part").classes("font-semibold")
                            ui.label(part.get("role") or "—").classes("text-sm text-gray-600")
                        ui.badge(part.get("state_label") or part.get("state") or "—").classes(
                            _badge_class(part.get("state"))
                        )
                    with ui.row().classes("w-full gap-2 flex-wrap mt-2"):
                        ui.badge(
                            f"{i18n_copy(language, 'attempts')} {part.get('attempt_count', 0)}"
                        ).classes("bg-slate-100 text-slate-700")
                        if part.get("has_reviewable_result"):
                            ui.badge("待审查结果" if language == "zh" else "Reviewable result").classes("bg-orange-100 text-orange-800")
                        if part.get("has_accepted_result"):
                            ui.badge("已接受结果" if language == "zh" else "Accepted result").classes("bg-green-100 text-green-800")
                    ui.label(
                        "在工作流中查看当前步骤 →" if language == "zh" else "View current step in Workflow →"
                    ).classes("text-xs text-blue-700 mt-2")


def _render_workbench_advanced(
    ui: Any,
    overview: dict[str, Any],
    language: str,
) -> None:
    advanced = overview.get("advanced") if isinstance(overview.get("advanced"), dict) else {}
    render_lazy_technical_evidence(
        ui,
        title=str(advanced.get("label") or i18n_copy(language, "advanced_evidence")),
        language=language,
        icon="science",
        classes="workbench-advanced w-full",
        metadata={"Evidence scope": "Current Work"},
        evidence={
            "reviewable_evidence": advanced.get("reviewable_evidence") or {},
            "artifact_references": advanced.get("artifact_references") or [],
        },
    )


def _show_accept_result_confirmation(
    ui: Any,
    backend: WorkflowConsoleBackend,
    work_id: str,
    part_id: str,
    result_id: str,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> None:
    action = {
        "key": "accept_reviewable_result",
        "label": "Accept result",
        "target_work_id": work_id,
        "part_job_id": part_id,
        "reviewable_result_id": result_id,
    }
    if _pending_action_matches(state, action):
        return
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[560px] max-w-full"):
        ui.label(i18n_copy(language, "accept_result")).classes("text-xl font-semibold")
        ui.label(i18n_copy(language, "accept_consequence")).classes("text-sm text-gray-700")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(i18n_copy(language, "cancel"), on_click=dialog.close).props("outline")
            ui.button(
                i18n_copy(language, "accept_result"),
                icon="check",
                on_click=lambda: (
                    dialog.close(),
                    _schedule_action(
                        _accept_reviewable_result_async(
                            backend, action, state, refresh, language
                        )
                    ),
                ),
            ).props("color=positive")
    dialog.open()


def _show_revision_dialog(
    ui: Any,
    backend: WorkflowConsoleBackend,
    work_id: str,
    part_id: str,
    result_id: str,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> None:
    action = {
        "key": "revise_reviewable_result",
        "label": "Revise",
        "target_work_id": work_id,
        "part_job_id": part_id,
        "reviewable_result_id": result_id,
    }
    if _pending_action_matches(state, action):
        return
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[640px] max-w-full"):
        ui.label(i18n_copy(language, "revise")).classes("text-xl font-semibold")
        ui.label(i18n_copy(language, "revision_preserves_acceptance")).classes("text-sm text-gray-700")
        revision = ui.textarea(
            i18n_copy(language, "revision_request"),
            value=state.get("revision_draft") or "",
            placeholder=(
                "例如：把长度增加 10 mm，并将中心孔直径改为 5 mm。"
                if language == "zh"
                else "For example: increase the length by 10 mm and change the center bore to 5 mm."
            ),
        ).props("outlined autogrow").classes("w-full")
        revision.on_value_change(
            lambda event: state.__setitem__("revision_draft", event.value or "")
        )
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(i18n_copy(language, "cancel"), on_click=dialog.close).props("outline")
            ui.button(
                i18n_copy(language, "revise"),
                icon="edit",
                on_click=lambda: (
                    dialog.close(),
                    _schedule_action(
                        _revise_reviewable_result_async(
                            backend,
                            action,
                            revision.value,
                            state,
                            refresh,
                            language,
                        )
                    ),
                ),
            ).props("color=primary")
    dialog.open()


def _show_continue_work_design_confirmation(
    ui: Any,
    backend: WorkflowConsoleBackend,
    overview: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
    *,
    scoped_action: dict[str, Any] | None = None,
) -> None:
    advanced = overview.get("advanced") if isinstance(overview.get("advanced"), dict) else {}
    work_id = advanced.get("work_id")
    if not isinstance(work_id, str):
        return
    action = (
        dict(scoped_action)
        if isinstance(scoped_action, dict)
        else {
            "key": "continue_work_design",
            "label": "Continue Work Design",
            "target_work_id": work_id,
        }
    )
    action_label_text = str(
        action.get("label")
        or ("继续 Work 设计" if language == "zh" else "Continue Work Design")
    )
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[560px] max-w-full"):
        ui.label(action_label_text).classes("text-xl font-semibold")
        ui.label(
            "Agent 将分析整个目标、现有上下文和接口，并提出零件边界。只有完成且有效的提案才会创建 Part Jobs。"
            if language == "zh"
            else "The Agent will analyze the whole objective, context, and interfaces, then propose Part boundaries. Part Jobs are created only from a completed valid proposal."
        ).classes("text-sm text-gray-700")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(i18n_copy(language, "cancel"), on_click=dialog.close).props("outline")
            ui.button(
                action_label_text,
                icon="account_tree",
                on_click=lambda: (
                    dialog.close(),
                    _schedule_action(
                        _continue_work_design_async(backend, action, state, refresh, language)
                    ),
                ),
            ).props("color=primary")
    dialog.open()


def _show_continue_agent_confirmation(
    ui: Any,
    backend: WorkflowConsoleBackend,
    overview: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
    *,
    scoped_action: dict[str, Any] | None = None,
) -> None:
    work = overview.get("work") if isinstance(overview.get("work"), dict) else {}
    advanced = overview.get("advanced") if isinstance(overview.get("advanced"), dict) else {}
    part_id = (
        scoped_action.get("part_job_id")
        if isinstance(scoped_action, dict)
        else work.get("active_part")
    )
    work_id = advanced.get("work_id")
    job = next(
        (item for item in overview.get("part_jobs", []) if isinstance(item, dict) and item.get("part_job_id") == part_id),
        None,
    )
    if not (isinstance(work_id, str) and isinstance(part_id, str) and isinstance(job, dict)):
        return
    action = (
        dict(scoped_action)
        if isinstance(scoped_action, dict)
        else {
            "key": "continue_agent",
            "label": "Continue Agent",
            "target_work_id": work_id,
            "part_job_id": part_id,
            "target_run_id": job.get("latest_attempt_run_id"),
        }
    )
    part_label = str(action.get("scope_label") or job.get("name") or part_id)
    action["scope_label"] = part_label
    action_label_text = str(
        action.get("label")
        or (f"继续 {part_label}" if language == "zh" else f"Continue {part_label}")
    )
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[560px] max-w-full"):
        ui.label(action_label_text).classes("text-xl font-semibold")
        ui.label(
            f"Agent 将为 {part_label} 准备候选设计、在隔离环境中生成几何并检查结果。"
            if language == "zh"
            else f"The Agent will prepare a candidate for {part_label}, build geometry in isolation, and inspect the result."
        ).classes("text-sm text-gray-700")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(i18n_copy(language, "cancel"), on_click=dialog.close).props("outline")
            ui.button(
                action_label_text,
                icon="play_arrow",
                on_click=lambda: (
                    dialog.close(),
                    _schedule_action(
                        _continue_agent_async(backend, action, state, refresh, language)
                    ),
                ),
            ).props("color=primary")
    dialog.open()




def _render_works(
    ui: Any,
    data: dict[str, Any],
    state: dict[str, Any],
    on_select: Callable[[str], None],
    refresh: Callable[[], None],
) -> None:
    language = str(data.get("language") or "en")
    home = data.get("home") if isinstance(data.get("home"), dict) else {}
    recent = home.get("recent_works") if isinstance(home.get("recent_works"), list) else []
    with ui.row().classes("w-full items-start justify-between gap-3"):
        with ui.column().classes("gap-1"):
            ui.label("设计" if language == "zh" else "Works").classes("text-3xl font-semibold")
            ui.label("每个 Work 是一个可持续修改的工程目标；每次 Agent 尝试都会保留为 Run。" if language == "zh" else "Each Work is one evolving engineering objective; every Agent attempt remains as a Run.").classes("text-gray-600")
        with ui.column().classes("items-end gap-2"):
            _new_design_dialog_button(ui, state, refresh, language)
            toggle = ui.switch(
                i18n_copy(language, "show_developer_content"),
                value=bool(state.get("show_developer_content")),
            )
            toggle.on_value_change(lambda event: (state.__setitem__("show_developer_content", bool(event.value)), refresh()))
    if not recent:
        ui.label("还没有设计。" if language == "zh" else "No Works yet.").classes("text-gray-600")
        return
    for item in recent:
        attention = item.get("needs_user_action") is True
        with ui.card().classes("w-full shadow-none border " + ("border-amber-300" if attention else "border-gray-200")):
            with ui.row().classes("w-full items-center justify-between gap-4"):
                with ui.column().classes("gap-1 min-w-0"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(item.get("title") or item.get("work_id")).classes("text-lg font-semibold")
                        if attention:
                            ui.badge("需要操作" if language == "zh" else "Action needed").classes("bg-amber-700")
                    ui.label(f"{item.get('phase')} · {item.get('state')}").classes("text-sm text-gray-700")
                    ui.label(str(item.get("next_action") or "")).classes("text-sm text-blue-700")
                    ui.label(str(item.get("updated") or "")).classes("text-xs text-gray-500")
                    classification = str(item.get("work_classification") or "user")
                    if state.get("show_developer_content"):
                        labels = {
                            "user": "User Work",
                            "product_example": "Product example",
                            "developer_fixture": "Developer fixture",
                            "compatibility_regression": "Compatibility regression",
                            "infrastructure_test": "Infrastructure test",
                        }
                        purposes = {
                            "developer_fixture": "Exercises a focused recovery or UI state.",
                            "compatibility_regression": "Preserves an older deterministic behavior contract.",
                            "infrastructure_test": "Checks local infrastructure, not product onboarding.",
                        }
                        ui.badge(labels.get(classification, classification)).classes("bg-slate-600")
                        if classification in purposes:
                            ui.label(purposes[classification]).classes("text-xs text-gray-500")
                ui.button("打开设计" if language == "zh" else "Open Design", icon="arrow_forward", on_click=lambda _event=None, work=item: on_select(work["work_id"])).props("outline")


def _render_work_table(
    ui: Any,
    works: list[dict[str, Any]],
    selected: str | None,
    on_select: Callable[[str], None],
) -> None:
    columns = [
        {"name": "title", "label": "Work", "field": "title", "align": "left"},
        {"name": "overall_status", "label": "Status", "field": "overall_status", "align": "left"},
        {"name": "parts", "label": "Parts", "field": "parts", "align": "left"},
        {"name": "readiness_score", "label": "Readiness", "field": "readiness_score", "align": "left"},
        {"name": "risk_level", "label": "Risk", "field": "risk_level", "align": "left"},
        {"name": "review_status", "label": "Review", "field": "review_status", "align": "left"},
        {"name": "next_action", "label": "Next", "field": "next_action", "align": "left"},
        {"name": "updated_at", "label": "Updated", "field": "updated_at", "align": "left"},
    ]
    rows = [_work_row(work, selected) for work in works]
    table = ui.table(columns=columns, rows=rows, row_key="work_id").classes("w-full")
    table.on("rowClick", lambda event: on_select(event.args[1]["work_id"]))


def _render_workflow_stage_review_surface(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    on_select_stage: Callable[[str], None],
) -> None:
    surface = data.get("workflow_review_surface") if isinstance(data.get("workflow_review_surface"), dict) else {}
    _label_with_help(ui, "Workflow Graph", "按真实 workflow stage 导航；点击节点查看该阶段详情。", "text-xl font-semibold")
    if state.get("surface_action_result") is not None:
        ui.markdown(f"```json\n{json.dumps(state['surface_action_result'], indent=2, sort_keys=True)}\n```").classes("w-full")
    _render_workflow_stage_graph(ui, surface, on_select_stage)
    selected_stage = surface.get("selected_stage") if isinstance(surface.get("selected_stage"), dict) else None
    _render_workflow_context(ui, surface.get("workflow_context"), data, actions)
    _render_selected_stage_detail(ui, selected_stage, data, actions, state, refresh)


def _render_workflow_page_v2(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    on_select_stage: Callable[[str], None],
    on_select_run: Callable[[str], None],
    on_select_current_work: Callable[[], None],
) -> None:
    """Render only the unified Workflow page contract, never a mixed surface."""
    page = data.get("workflow_page") if isinstance(data.get("workflow_page"), dict) else {}
    if not page:
        ui.label("Workflow data is unavailable.").classes("text-negative")
        return
    snapshot = page.get("view_mode") == "run_snapshot"
    language = str(data.get("language") or "en")
    if page.get("projection_mode") == "agent_first" and not snapshot:
        _render_agent_first_workflow_page(
            ui,
            page,
            actions,
            state,
            refresh,
            on_select_stage,
            on_select_run,
            on_select_current_work,
            language,
        )
        return
    work = page.get("work") if isinstance(page.get("work"), dict) else {}
    lineage = page.get("active_lineage") if isinstance(page.get("active_lineage"), dict) else {}
    with ui.element("section").classes("workflow-snapshot-banner w-full" if snapshot else "workflow-hero w-full"):
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label(("历史 Run 快照 · 只读" if snapshot else "当前工作") if language == "zh" else ("HISTORICAL RUN SNAPSHOT · READ-ONLY" if snapshot else "CURRENT WORK")).classes("workflow-eyebrow")
                ui.label(work.get("title") or "Workflow").classes("text-2xl font-semibold")
                if snapshot:
                    ui.label("Immutable audit record" if language != "zh" else "不可变审计记录").classes("text-sm text-amber-800")
                    ui.label("这份快照不代表完整的当前 Work。" if language == "zh" else "This snapshot does not represent the complete Current Work.").classes("workflow-summary text-sm text-gray-700")
                else:
                    ui.label("Active lineage · actionable current workflow" if language != "zh" else "当前谱系 · 可操作的当前工作流").classes("workflow-meta")
                    if page.get("lineage_inferred"):
                        ui.label("Active lineage inferred from legacy Work metadata.").classes("text-sm text-amber-800")
            with ui.row().classes("gap-2"):
                current = ui.button("当前 Work" if language == "zh" else "Current Work", on_click=on_select_current_work).props("dense")
                current.tooltip("查看可操作的当前 Work 谱系；不会修改任何 Run 或资料。" if language == "zh" else "Show the actionable Current Work lineage. This does not modify any Run or artifact.")
                if not snapshot:
                    current.props("color=primary")
                if snapshot:
                    ui.button("返回当前 Work" if language == "zh" else "Return to Current Work", icon="undo", on_click=on_select_current_work).props("outline dense") \
                        .tooltip("离开此只读历史 Run，返回可操作的当前 Work 谱系。" if language == "zh" else "Leave this read-only historical Run and return to the actionable Current Work lineage.")
    if snapshot:
        _render_historical_run_summary(
            ui,
            page,
            data,
            actions,
            state,
            refresh,
            on_select_stage,
            on_select_run,
            on_select_current_work,
            language,
        )
        return
    conclusion = page.get("current_conclusion") if isinstance(page.get("current_conclusion"), dict) else {}
    with ui.element("section").classes("workflow-hero w-full"):
        ui.label(("当前结论" if not snapshot else "快照结论") if language == "zh" else ("CURRENT CONCLUSION" if not snapshot else "SNAPSHOT CONCLUSION")).classes("workflow-eyebrow")
        ui.label(conclusion.get("title") or "Current result").classes("text-xl font-semibold")
        ui.label(conclusion.get("summary") or "Inspect the selected workflow stage.").classes("workflow-summary text-sm text-gray-700")
        if conclusion.get("rationale"):
            ui.label(conclusion["rationale"]).classes("workflow-meta")
        action = page.get("recommended_next_action") if isinstance(page.get("recommended_next_action"), dict) else None
        if action and action.get("enabled"):
            ui.button(action.get("label") or action.get("key"), on_click=lambda _event=None, a=action: _run_workflow_page_action(ui, actions, a, state, refresh)).props("color=primary") \
                .tooltip(action.get("tooltip") or "Run the recommended workflow action.")
    if not snapshot:
        with ui.element("section").classes("workflow-run-strip-panel w-full"):
            _render_run_strip(ui, page.get("run_strip"), on_select_run, on_select_current_work, language=language)
    _render_workflow_stage_graph(
        ui,
        {"workflow_graph": page.get("workflow_graph"), "selected_stage_id": _dict_get(page.get("selected_stage"), "stage_id")},
        on_select_stage,
        language=str(data.get("language") or "en"),
        on_open_candidate=lambda candidate: _show_candidate_detail(
            ui, candidate, data, actions, state, refresh, read_only=snapshot
        ),
    )
    _render_selected_stage_detail_v2(ui, page.get("selected_stage"), data, actions, state, refresh, snapshot)


def _render_historical_run_summary(
    ui: Any,
    page: dict[str, Any],
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    on_select_stage: Callable[[str], None],
    on_select_run: Callable[[str], None],
    on_select_current_work: Callable[[], None],
    language: str,
) -> None:
    summary = page.get("historical_run_summary") if isinstance(page.get("historical_run_summary"), dict) else {}
    validation = summary.get("validation") if isinstance(summary.get("validation"), dict) else {}
    with ui.element("section").classes("workflow-hero w-full"):
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label(summary.get("title") or ("历史 Run 摘要" if language == "zh" else "Historical Run summary")).classes("workflow-eyebrow")
                ui.label(str(summary.get("summary") or "Immutable attempt evidence.")).classes("text-xl font-semibold")
                if summary.get("latest_evidence"):
                    ui.label(
                        ("最后有效证据：" if language == "zh" else "Latest meaningful evidence: ")
                        + str(summary["latest_evidence"])
                    ).classes("text-sm text-gray-600")
            ui.badge(_display_status(summary.get("status") or "unknown", language)).classes(
                _badge_class(summary.get("status"))
            )
        ui.label("原始请求" if language == "zh" else "Request represented by this Run").classes("workflow-eyebrow mt-4")
        ui.label(str(summary.get("request") or "—")).classes("text-sm")

    viewer_url = summary.get("geometry_viewer_url")
    artifacts = [item for item in summary.get("model_artifacts", []) if isinstance(item, dict)]
    with ui.element("section").classes("workbench-panel w-full"):
        ui.label("结果与几何" if language == "zh" else "RESULT & GEOMETRY").classes("workflow-eyebrow")
        if viewer_url:
            ui.html(
                f'<iframe class="workbench-viewer" title="Historical geometry preview" '
                f'src="{html_escape(str(viewer_url), quote=True)}"></iframe>',
                sanitize=False,
            ).classes("w-full mt-3")
        elif artifacts:
            ui.label(
                "该 Run 保存了模型资料，但没有可用的浏览器预览。" if language == "zh"
                else "This Run retained model artifacts, but no browser preview is available."
            ).classes("text-sm text-gray-600")
        else:
            ui.label(
                "该 Run 没有生成可审查几何。" if language == "zh" else "This Run did not produce reviewable geometry."
            ).classes("text-sm text-gray-600")
        for artifact in artifacts:
            ui.label(f"• {artifact.get('display_name') or artifact.get('name')}").classes("text-sm")

    with ui.element("section").classes(
        "workflow-action-feedback failed w-full" if validation.get("blocked") else "workbench-panel w-full"
    ):
        ui.label("验证 / 停止原因" if language == "zh" else "VALIDATION / STOP").classes("workflow-eyebrow")
        ui.label(str(validation.get("title") or validation.get("summary") or "No blocking validation evidence.")).classes("font-semibold")
        if validation.get("summary") and validation.get("summary") != validation.get("title"):
            ui.label(str(validation["summary"])).classes("text-sm")
        if validation.get("consequence"):
            ui.label(str(validation["consequence"])).classes("text-sm text-gray-600")

    agent_output = summary.get("agent_output") if isinstance(summary.get("agent_output"), dict) else {}
    if agent_output:
        with ui.element("section").classes("workbench-panel w-full"):
            ui.label("Agent 输出" if language == "zh" else "AGENT OUTPUT").classes("workflow-eyebrow")
            ui.label(str(agent_output.get("summary") or agent_output.get("title") or "Persisted Agent evidence is available.")).classes("text-sm")

    with ui.expansion(
        "Run 历史与谱系" if language == "zh" else "Run history and lineage",
        icon="history",
        value=False,
    ).classes("workflow-run-strip-panel w-full"):
        _render_run_strip(ui, page.get("run_strip"), on_select_run, on_select_current_work, language=language)

    with ui.expansion(
        "兼容性详情 · 旧版 Workflow 证据" if language == "zh" else "Compatibility details · Legacy Workflow evidence",
        icon="account_tree",
        value=False,
    ).classes("workflow-run-strip-panel w-full"):
        ui.label(
            "以下固定阶段图仅用于读取旧版证据，不代表当前产品的 Work 状态模型。"
            if language == "zh"
            else "The fixed-stage graph below is compatibility evidence, not the Current Work product model."
        ).classes("text-sm text-gray-600")
        _render_workflow_stage_graph(
            ui,
            {"workflow_graph": page.get("workflow_graph"), "selected_stage_id": _dict_get(page.get("selected_stage"), "stage_id")},
            on_select_stage,
            language=language,
            on_open_candidate=lambda candidate: _show_candidate_detail(
                ui, candidate, data, actions, state, refresh, read_only=True
            ),
        )
        _render_selected_stage_detail_v2(ui, page.get("selected_stage"), data, actions, state, refresh, True)


def _render_agent_first_workflow_page(
    ui: Any,
    page: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    on_select_stage: Callable[[str], None],
    on_select_run: Callable[[str], None],
    on_select_current_work: Callable[[], None],
    language: str,
) -> None:
    work = page.get("work") if isinstance(page.get("work"), dict) else {}
    graph = workflow_graph_with_runtime(
        page.get("workflow_graph") if isinstance(page.get("workflow_graph"), dict) else {},
        state,
        language,
    )
    with ui.element("section").classes("workflow-hero w-full"):
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label("动态工作图" if language == "zh" else "DYNAMIC WORK GRAPH").classes("workflow-eyebrow")
                ui.label(work.get("title") or "Workflow").classes("text-2xl font-semibold")
                ui.label(
                    "从当前 Work、零件任务、尝试、结果和接受指针实时投影；选择节点不会修改工程状态。"
                    if language == "zh"
                    else "Live projection of Current Work, Part Jobs, attempts, results, and accepted pointers. Selecting a node does not modify engineering state."
                ).classes("text-sm text-gray-600")
            if graph.get("compatibility_mode"):
                ui.badge("兼容模式 · 旧版 Work" if language == "zh" else "COMPATIBILITY MODE · LEGACY WORK").classes("bg-amber-700")
    render_current_attention(ui, graph, on_select_stage, language, state=state)
    with ui.element("section").classes("workflow-master-detail w-full"):
        with ui.element("div").classes("workflow-graph-pane"):
            render_dynamic_work_graph(ui, graph, on_select_stage, language)
        inspector = ui.element("aside").classes("workflow-inspector-pane")
        state["_workflow_inspector"] = inspector
        with inspector:
            _render_dynamic_node_detail(ui, page, actions, state, refresh, on_select_run, language)
    with ui.expansion(
        "Run 历史与谱系" if language == "zh" else "Run history and lineage",
        icon="history",
        value=False,
    ).classes("workflow-run-strip-panel w-full"):
        _render_run_strip(ui, page.get("run_strip"), on_select_run, on_select_current_work, language=language)



def _render_dynamic_node_detail(
    ui: Any,
    page: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    on_select_run: Callable[[str], None],
    language: str,
) -> None:
    render_selected_node_inspector(
        ui,
        page,
        actions,
        state,
        refresh,
        on_select_run,
        language,
        renderers=SelectedInspectorRenderers(
            action_feedback=_render_action_feedback_panel,
            display_status=_display_status,
            pending_action_matches=_pending_action_matches,
            node_actions=_render_dynamic_node_actions,
            key_values=_key_values,
            agent_design_summary=_render_agent_design_summary,
            preview=_render_dynamic_preview,
            workbench_result=_render_workbench_result,
        ),
    )


def _render_dynamic_node_actions(
    ui: Any,
    node: dict[str, Any],
    interaction: dict[str, Any],
    overview: dict[str, Any],
    backend: WorkflowConsoleBackend,
    state: dict[str, Any],
    refresh: Callable[[], None],
    on_select_run: Callable[[str], None],
    language: str,
) -> None:
    primary = interaction.get("primary_action") if isinstance(interaction.get("primary_action"), dict) else None
    secondary = [item for item in interaction.get("secondary_actions", []) if isinstance(item, dict)]
    detail = node.get("detail") if isinstance(node.get("detail"), dict) else {}
    recovery = _dict_get(detail, "recovery") or {}
    if primary or secondary:
        with ui.element("section").classes("dynamic-node-actions w-full mt-3"):
            if primary:
                key = str(primary.get("key") or "")
                if key == "answer_question":
                    questions = recovery.get("questions") if isinstance(recovery.get("questions"), list) else detail.get("questions", [])
                    question = questions[0] if questions and isinstance(questions[0], dict) else {}
                    answer = ui.input(str(question.get("question") or recovery.get("summary") or "Answer")).props("outlined").classes("min-w-[320px] w-full")
                    button = ui.button(
                        str(primary.get("label") or "Answer and continue"),
                        icon="send",
                        on_click=lambda: _schedule_action(
                            _answer_and_continue_agent_async(
                                backend,
                                recovery,
                                question,
                                answer.value,
                                state,
                                refresh,
                                language,
                                source_action=primary,
                            )
                        ),
                    ).props("color=primary").classes("mt-2")
                    if _pending_action_matches(state, primary):
                        button.disable()
                elif key in {"continue_agent", "retry_agent"}:
                    button = ui.button(
                        str(primary.get("label") or "Continue Agent"),
                        icon="refresh" if key == "retry_agent" else "play_arrow",
                        on_click=lambda: _show_continue_agent_confirmation(
                            ui,
                            backend,
                            overview,
                            state,
                            refresh,
                            language,
                            scoped_action=primary,
                        ),
                    ).props("color=primary")
                    if _pending_action_matches(state, primary):
                        button.disable()
                elif key == "continue_work_design":
                    button = ui.button(
                        str(primary.get("label") or "Continue Work Design"),
                        icon="account_tree",
                        on_click=lambda: _show_continue_work_design_confirmation(
                            ui,
                            backend,
                            overview,
                            state,
                            refresh,
                            language,
                            scoped_action=primary,
                        ),
                    ).props("color=primary")
                    if _pending_action_matches(state, primary):
                        button.disable()
                elif key == "open_settings":
                    ui.button(str(primary.get("label") or "Open Settings"), icon="settings", on_click=lambda: _go_to_settings(state, refresh)).props("color=primary")
                elif key == "modify_request":
                    revision = ui.textarea("修改后的设计要求" if language == "zh" else "Revised design request").props("outlined autogrow").classes("w-full")
                    ui.button(
                        str(primary.get("label") or "Modify request"),
                        icon="edit",
                        on_click=lambda: _schedule_action(_revise_blocked_request_async(backend, overview, revision.value, state, refresh, language)),
                    ).props("color=primary").classes("mt-2")
                elif key == "accept_reviewable_result":
                    ui.button(
                        str(primary.get("label") or "Accept result"),
                        icon="check_circle",
                        on_click=lambda: _show_accept_result_confirmation(
                            ui, backend, str(primary.get("target_work_id")), str(primary.get("part_job_id")), str(primary.get("reviewable_result_id")), state, refresh, language
                        ),
                    ).props("color=positive")
            if secondary:
                with ui.row().classes("gap-2 mt-2 flex-wrap"):
                    for secondary_action in secondary:
                        key = str(secondary_action.get("key") or "")
                        if key == "revise_reviewable_result":
                            ui.button(
                                str(secondary_action.get("label") or "Revise"),
                                icon="fork_right",
                                on_click=lambda _event=None, selected_action=secondary_action: _show_revision_dialog(
                                    ui, backend, str(selected_action.get("target_work_id")), str(selected_action.get("part_job_id")), str(selected_action.get("reviewable_result_id")), state, refresh, language
                                ),
                            ).props("outline")
                        elif key == "open_run" and secondary_action.get("target_run_id"):
                            ui.button(
                                str(secondary_action.get("label") or "Open historical Run"),
                                icon="history",
                                on_click=_run_selection_callback(on_select_run, str(secondary_action["target_run_id"])),
                            ).props("outline")
                        elif key == "technical_details" and recovery:
                            ui.button(
                                str(secondary_action.get("label") or "Technical details"),
                                icon="info",
                                on_click=lambda: _show_recovery_details_dialog(ui, recovery, language),
                            ).props("outline")
    elif interaction.get("unavailable_reason"):
        ui.label(str(interaction["unavailable_reason"])).classes("workflow-disabled-reason mt-3")


def _render_dynamic_preview(
    ui: Any,
    preview: dict[str, Any],
    result: dict[str, Any],
    language: str,
) -> None:
    if not preview or preview.get("result_id") not in {None, result.get("reviewable_result_id")}:
        return
    with ui.element("section").classes("workbench-panel workbench-geometry w-full mt-3"):
        ui.label("几何预览" if language == "zh" else "GEOMETRY PREVIEW").classes("workflow-eyebrow")
        if preview.get("viewer_url"):
            ui.html(
                f'<iframe class="workbench-viewer" title="Geometry preview" '
                f'src="{html_escape(str(preview["viewer_url"]), quote=True)}"></iframe>',
                sanitize=False,
            ).classes("w-full mt-3")
        else:
            ui.label(str(preview.get("label") or ("预览不可用" if language == "zh" else "Preview unavailable"))).classes("text-sm text-gray-500 mt-3")


def _render_run_strip(
    ui: Any,
    runs: Any,
    on_select_run: Callable[[str], None],
    on_select_current_work: Callable[[], None],
    *,
    language: str = "en",
) -> None:
    ui.label("运行谱系" if language == "zh" else "RUN LINEAGE").classes("workflow-eyebrow")
    with ui.row().classes("workflow-run-strip w-full"):
        with ui.row().classes("workflow-run-strip-inner gap-2 no-wrap"):
            current = ui.column().classes("workflow-run-item workflow-run-current gap-1")
            current.on("click", lambda _event: on_select_current_work())
            with current:
                ui.label("当前 Work" if language == "zh" else "Current Work").classes("text-sm font-semibold")
                ui.label("当前汇总谱系" if language == "zh" else "Active aggregated lineage").classes("workflow-run-state text-blue-700")
                ui.label("可操作的工作流视图" if language == "zh" else "Actionable workflow view").classes("text-xs text-gray-500")
            for run in runs if isinstance(runs, list) else []:
                if not isinstance(run, dict):
                    continue
                state = str(run.get("lineage_state") or "historical")
                classes = "workflow-run-item gap-1" + (" workflow-run-current" if run.get("is_current") else "") + (" workflow-run-failed" if state == "failed_branch" else "")
                item = ui.column().classes(classes)
                item.on("click", lambda _event, run_id=run.get("run_id"): on_select_run(str(run_id)))
                with item:
                    ui.label(run.get("display_label") or run.get("run_id") or "Run").classes("text-sm font-medium")
                    ui.label(_display_status(state, language)).classes("workflow-run-state")
                    ui.label(_display_status(run.get("status") or "unknown", language)).classes("text-xs text-gray-600")
                    ui.label(run.get("summary") or "Immutable workflow attempt.").classes("text-xs text-gray-500")
                    if run.get("parent_run_id"):
                        ui.label("Based on an earlier attempt" if not run.get("is_current") else "Current attempt").classes("workflow-meta")


def _render_action_feedback_panel(ui: Any, state: dict[str, Any], language: str) -> None:
    """Show the latest action result persistently instead of a transient toast."""
    execution = state.get("action_execution")
    if not isinstance(execution, dict) or execution.get("status") in {None, "idle", "confirming"}:
        return
    status = str(execution.get("status"))
    outcome = str(execution.get("runtime_outcome") or "")
    if status == "pending":
        title = "命令已接受" if language == "zh" else "Command accepted"
    elif outcome == "user_input_required":
        title = "需要你的输入" if language == "zh" else "Needs your input"
    elif outcome == "reviewable_result_ready":
        title = "可供审查" if language == "zh" else "Ready for review"
    elif status == "succeeded":
        title = "已完成" if language == "zh" else "Completed"
    elif status == "warning":
        title = "设计已停止" if language == "zh" else "Design stopped"
    else:
        title = "设计失败" if language == "zh" else "Design failed"
    with ui.element("section").classes(f"workflow-action-feedback {status} w-full"):
        with ui.row().classes("w-full items-start justify-between gap-3"):
            with ui.column().classes("gap-1"):
                ui.label(title).classes("text-sm font-semibold")
                ui.label(str(execution.get("message") or "")).classes("text-sm")
                if status == "pending":
                    ui.label(
                        "运行中；完成后将显示实际 Episode 结果。"
                        if language == "zh"
                        else "Running; the actual Episode outcome will replace this acknowledgement."
                    ).classes("text-xs text-blue-800")
                if status == "succeeded" and execution.get("action_key") == "select_candidate_part":
                    ui.label("装配计划已保存为用户覆盖版本。零件请求及后续阶段已标记为过期。已有 Run 和已批准结果保持不变。" if language == "zh" else "The Assembly Plan was saved as a user override. Part Request and downstream stages are stale. Existing Runs and accepted results are unchanged.").classes("text-xs")
                    ui.label(i18n_copy(language, "next_create_part_request")).classes("text-xs font-medium")
                if status == "succeeded" and execution.get("action_key") == "accept_reviewable_result":
                    ui.label(i18n_copy(language, "accept_success_detail")).classes("text-xs")
                if status == "succeeded" and execution.get("action_key") == "revise_reviewable_result":
                    ui.label(i18n_copy(language, "revise_success_detail")).classes("text-xs")
                if status in {"failed", "warning"} and execution.get("error_detail"):
                    with ui.expansion(i18n_copy(language, "details"), icon="error_outline").classes("w-full"):
                        ui.label(str(execution["error_detail"])).classes("text-xs whitespace-pre-wrap")
                with ui.expansion(i18n_copy(language, "action_details"), icon="rule").classes("w-full"):
                    target = {key: execution.get(key) for key in ("action_key", "target_work_id", "target_part_job_id", "target_run_id", "target_stage_id", "runtime_outcome")}
                    ui.label(json.dumps(target, ensure_ascii=False, sort_keys=True)).classes("text-xs whitespace-pre-wrap workflow-meta")
            close = ui.button(icon="close", on_click=lambda: state.__setitem__("action_execution", None)).props("flat round dense")
            close.tooltip(i18n_copy(language, "close"))


def _render_selected_stage_detail_v2(
    ui: Any,
    stage: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    read_only: bool,
) -> None:
    if not isinstance(stage, dict):
        ui.label("Select a workflow stage.").classes("text-gray-600")
        return
    conclusion = stage.get("conclusion") if isinstance(stage.get("conclusion"), dict) else {}
    language = str(data.get("language") or stage.get("display_language") or "en")
    with ui.element("section").classes("workflow-stage-detail-v2 w-full"):
        _render_action_feedback_panel(ui, state, language)
        guidance = stage.get("guidance") if isinstance(stage.get("guidance"), dict) else {}
        with ui.row().classes("stage-conclusion w-full items-start justify-between gap-3"):
            with ui.column().classes("gap-1"):
                ui.label(i18n_copy(language, "selected_stage").upper()).classes("workflow-eyebrow")
                ui.label(_localized_stage_title(stage, language)).classes("text-xl font-semibold")
                ui.label(guidance.get("current_conclusion") or conclusion.get("summary") or stage.get("short_summary") or i18n_copy(language, "not_available")).classes("text-sm text-gray-700")
            ui.badge(str(stage.get("status") or "unavailable").replace("_", " ")).classes(_badge_class(stage.get("status")))
        action = stage.get("primary_action") if isinstance(stage.get("primary_action"), dict) else None
        _render_guidance_contract(ui, guidance, action, language)
        if action and action.get("enabled"):
            button = ui.button(action.get("label") or action.get("key"), on_click=lambda _event=None, a=action: _run_workflow_page_action(ui, actions, a, state, refresh)).props("color=primary")
            button.tooltip(action.get("tooltip") or i18n_copy(language, "recommended_action"))
        elif action:
            ui.label(action.get("disabled_reason") or ("当前不可用" if language == "zh" else "Unavailable")).classes("workflow-disabled-reason")
        # Keep causal information in the decision order rather than three equal cards.
        _render_stage_contract_block(ui, i18n_copy(language, "user_input"), stage.get("user_input"), read_only, actions.backend, state, language=language)
        _render_stage_contract_block(ui, i18n_copy(language, "agent_decision"), stage.get("agent_decision"), read_only, actions.backend, state, language=language)
        _render_stage_contract_block(ui, i18n_copy(language, "agent_output"), stage.get("agent_output"), read_only, actions.backend, state, language=language)
        if stage.get("stage_id") in {"requirement", "clarification"} and not read_only:
            _render_inline_requirement_clarification(ui, data, actions, state, refresh)
        evidence = stage.get("evidence") if isinstance(stage.get("evidence"), list) else []
        with ui.element("section").classes("workflow-evidence w-full"):
            ui.label(i18n_copy(language, "evidence").upper()).classes("workflow-eyebrow")
            if evidence:
                _render_stage_artifact_rows(ui, evidence, actions.backend, state, compact=True)
            else:
                ui.label("没有额外证据可用。" if language == "zh" else "No additional evidence is available.").classes("text-sm text-gray-700")
        _render_stage_review_panel(ui, stage, data, actions, state, refresh, read_only)
        secondary = stage.get("secondary_actions") if isinstance(stage.get("secondary_actions"), list) else []
        if secondary:
            ui.label(i18n_copy(language, "secondary_actions")).classes("text-sm font-medium text-gray-600")
            with ui.row().classes("gap-2 flex-wrap"):
                for action in secondary:
                    button = ui.button(action.get("label") or action.get("key"), on_click=lambda _event=None, a=action: _run_workflow_page_action(ui, actions, a, state, refresh)).props("outline dense")
                    button.tooltip(action.get("tooltip") or action.get("disabled_reason") or i18n_copy(language, "available"))
                    if not action.get("enabled") or _pending_action_matches(state, action):
                        button.disable()
        disabled_actions = stage.get("disabled_actions") if isinstance(stage.get("disabled_actions"), list) else []
        if disabled_actions:
            ui.label(i18n_copy(language, "unavailable_actions")).classes("text-xs font-medium text-gray-500")
            with ui.row().classes("gap-2 flex-wrap"):
                for action in disabled_actions:
                    if isinstance(action, dict):
                        button = ui.button(action.get("label") or action.get("key")).props("outline dense")
                        button.disable()
                        button.tooltip(action.get("tooltip") or action.get("disabled_reason") or ("当前不可用" if language == "zh" else "Unavailable"))
        with ui.expansion(i18n_copy(language, "advanced"), icon="info").classes("w-full"):
            ui.label("原始资料和诊断信息仍作为该阶段摘要的辅助信息。" if language == "zh" else "Raw artifacts and diagnostics remain secondary to this stage summary.").classes("text-sm text-gray-500")
            _render_action_details(ui, stage, language)


def _render_guidance_contract(ui: Any, guidance: dict[str, Any], action: dict[str, Any] | None, language: str) -> None:
    """Render the decision-critical guidance before causal implementation detail."""
    with ui.element("section").classes("workflow-evidence w-full"):
        ui.label(i18n_copy(language, "stage_purpose").upper()).classes("workflow-eyebrow")
        ui.label(str(guidance.get("stage_purpose") or "")).classes("text-sm text-gray-700")
        ui.label(i18n_copy(language, "decision_required").upper()).classes("workflow-eyebrow mt-3")
        decision = guidance.get("user_decision_summary") or ""
        prefix = "需要用户决定。" if guidance.get("user_decision_required") and language == "zh" else "No user decision is required now." if not guidance.get("user_decision_required") and language != "zh" else "User decision required." if guidance.get("user_decision_required") else "当前无需用户决定。"
        ui.label(f"{prefix} {decision}".strip()).classes("text-sm text-gray-700")
        ui.label(i18n_copy(language, "recommended_action").upper()).classes("workflow-eyebrow mt-3")
        ui.label(str((action or {}).get("label") or guidance.get("recommended_next_action") or "")).classes("text-sm font-medium text-gray-800")
        ui.label(i18n_copy(language, "expected_result").upper()).classes("workflow-eyebrow mt-3")
        ui.label(str(guidance.get("expected_result") or "")).classes("text-sm text-gray-700")
        if guidance.get("blocked_reason"):
            ui.label(("阻断原因" if language == "zh" else "Blocked reason").upper()).classes("workflow-eyebrow mt-3")
            ui.label(str(guidance["blocked_reason"])).classes("workflow-disabled-reason")
            ui.label(str(guidance.get("recovery_action") or "")).classes("text-sm text-gray-700")
        limitations = guidance.get("limitations") if isinstance(guidance.get("limitations"), list) else []
        if limitations:
            ui.label(i18n_copy(language, "limitations").upper()).classes("workflow-eyebrow mt-3")
            ui.label(" · ".join(str(item) for item in limitations[:2])).classes("text-sm text-gray-700")


def _render_action_details(ui: Any, stage: dict[str, Any], language: str) -> None:
    """Keep audit targets and internal action metadata inspectable but off the primary surface."""
    with ui.expansion(i18n_copy(language, "action_details"), icon="rule").classes("w-full"):
        actions = [item for item in [stage.get("primary_action")] if isinstance(item, dict)]
        actions.extend(item for item in stage.get("secondary_actions", []) if isinstance(item, dict))
        if not actions:
            ui.label("暂无操作审计详情。" if language == "zh" else "No action audit details are available.").classes("text-sm text-gray-600")
        for action in actions:
            ui.label(str(action.get("label") or action.get("key") or "Action")).classes("text-sm font-medium")
            audit = {
                "backend_action": action.get("backend_action"),
                "target_work_id": action.get("target_work_id"),
                "target_run_id": action.get("target_run_id"),
                "target_stage_id": action.get("target_stage_id"),
                "creates_new_run": action.get("creates_new_run"),
                "updates_active_lineage": action.get("updates_active_lineage"),
                "expected_postcondition": action.get("expected_postcondition"),
            }
            ui.label(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True)).classes("text-xs whitespace-pre-wrap workflow-meta")


def _render_stage_contract_block(
    ui: Any,
    title: str,
    value: Any,
    read_only: bool,
    backend: WorkflowConsoleBackend | None = None,
    state: dict[str, Any] | None = None,
    language: str = "en",
) -> None:
    item = value if isinstance(value, dict) else {}
    classes = "stage-detail-card decision" if ("DECISION" in title or "决策" in title) else "stage-detail-card"
    with ui.element("section").classes(classes):
        ui.html(f"<h3>{title}</h3>")
        ui.label(item.get("summary") or ("此阶段区域暂无数据。" if language == "zh" else "No data is available for this stage section.")).classes("text-sm text-gray-800")
        if title in {"USER INPUT", "用户输入"}:
            ui.label(("只读快照" if read_only else ("当前覆盖版本" if item.get("source_type") == "active_override" else "已接受输入")) if language == "zh" else ("Read-only snapshot" if read_only else ("Active override" if item.get("source_type") == "active_override" else "Accepted input"))).classes("text-xs text-gray-500")
            if item.get("stale_downstream"):
                ui.label("当前覆盖版本可能使下游阶段过期。" if language == "zh" else "This active override may make downstream stages stale.").classes("text-xs text-amber-800")
        if title in {"AGENT OUTPUT", "Agent 输出"} and item.get("step_stl_expectation") == "not_expected":
            ui.label("CAD IR 已验证 · 已跳过执行 · 不预期 STEP/STL" if language == "zh" else "CAD IR validated · execution skipped · STEP/STL not expected").classes("text-xs text-gray-600")
        for key, label in (("decisions", "关键决策" if language == "zh" else "Key decisions"), ("assumptions", "假设" if language == "zh" else "Assumptions"), ("artifacts", "资料" if language == "zh" else "Artifacts")):
            values = item.get(key) if isinstance(item.get(key), list) else []
            if values:
                ui.label(label).classes("text-xs font-medium text-gray-500 mt-2")
                if key == "artifacts" and backend is not None:
                    _render_stage_artifact_rows(ui, _group_stage_artifacts(values), backend, state or {}, compact=True)
                else:
                    ui.label(" · ".join(str(entry.get("name") if isinstance(entry, dict) else entry) for entry in values[:4])).classes("text-xs text-gray-600")


def _render_agent_review_panel(
    ui: Any,
    stage: dict[str, Any],
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    read_only: bool,
) -> None:
    """Keep assessment agent-owned; users inspect its evidence rather than score it."""
    primary = stage.get("primary_action") if isinstance(stage.get("primary_action"), dict) else None
    with ui.element("section").classes("workflow-evidence w-full"):
        ui.label("AGENT REVIEW").classes("workflow-eyebrow")
        ui.label("Ask CadFlow to assess the current lineage, artifact completeness, and design confidence. The assessment is saved as review artifacts; users inspect the result rather than assigning the score.").classes("text-sm text-gray-700")
        if read_only:
            ui.label("This historical Run is read-only; return to Current Work to refresh an agent review.").classes("workflow-disabled-reason")
        elif primary:
            button = ui.button(
                primary.get("label") or "Request agent review",
                icon="smart_toy",
                on_click=lambda _event=None, a=primary: _run_workflow_page_action(ui, actions, a, state, refresh),
            ).props("color=primary")
            button.tooltip(primary.get("tooltip") or "Generate a traceable agent review without changing the CAD model.")
        else:
            ui.label("Agent review is not available until this stage has an active Run.").classes("workflow-disabled-reason")


def _render_stage_review_panel(
    ui: Any,
    stage: dict[str, Any],
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    read_only: bool,
) -> None:
    """Provide one explicit, append-only human review for every visible stage."""
    stage_id = str(stage.get("stage_id") or "workflow_review")
    language = str(data.get("language") or stage.get("display_language") or "en")
    review_stage = {"reviewed_handoff": "handoff", "part_result_review": "single_part_result"}.get(stage_id, stage_id)
    page = data.get("workflow_page") if isinstance(data.get("workflow_page"), dict) else {}
    target_run = page.get("active_lineage", {}).get("active_root_run_id") if isinstance(page.get("active_lineage"), dict) else None
    with ui.element("section").classes("workflow-evidence w-full"):
        ui.label(i18n_copy(language, "stage_review").upper()).classes("workflow-eyebrow")
        ui.label("记录对此阶段的决定。评审是追加记录，不会修改原有结果。" if language == "zh" else "Record your decision for this stage. Reviews are append-only and do not change the original result.").classes("text-sm text-gray-700")
        if read_only or not target_run:
            ui.label("This historical Run is read-only; return to Current Work to save a review.").classes("workflow-disabled-reason")
            return
        status = ui.select(["approved", "needs_revision", "blocked"], value="approved", label=i18n_copy(language, "review_status")).props("outlined dense").classes("w-full")
        notes = ui.textarea(i18n_copy(language, "notes")).props("outlined autogrow").classes("w-full")
        changes = ui.textarea(i18n_copy(language, "requested_changes")).props("outlined autogrow").classes("w-full")
        rework_target = ui.select(
            ["requirement", "design_brief", "assembly_plan", "candidate_parts", "part_request", "part_review", "handoff", "single_part_result", "workflow_review"],
            value="workflow_review",
            label=i18n_copy(language, "target_rework_stage"),
        ).props("outlined dense").classes("w-full")
        with ui.row().classes("gap-2 flex-wrap"):
            save = ui.button(
                i18n_copy(language, "save_stage_review"),
                on_click=lambda: _schedule_action(_save_stage_review_from_form(
                    actions, target_run, review_stage, status.value, notes.value, changes.value, rework_target.value, state, refresh, target_work_id=(data.get("workflow_page") or {}).get("work", {}).get("work_id")
                )),
            ).props("color=primary")
            save.tooltip("保存可追溯的阶段评审；不会创建 Run 或覆盖原有结果。" if language == "zh" else "Save a traceable stage review. It does not create a Run or overwrite original results.")
            quick = ui.button(
                i18n_copy(language, "quick_approve"),
                on_click=lambda: _schedule_action(_save_stage_review_from_form(
                    actions, target_run, review_stage, "approved", None, None, None, state, refresh, target_work_id=(data.get("workflow_page") or {}).get("work", {}).get("work_id")
                )),
            ).props("outline")
            quick.tooltip("立即保存“已批准”；不会创建 Run，已有结果保持不变。" if language == "zh" else "Immediately save Approved. No Run is created and existing results remain unchanged.")


async def _save_stage_review_from_form(
    actions: WorkflowConsoleActions,
    run_id: str,
    stage: str,
    review_status: Any,
    notes: Any,
    changes: Any,
    rework_target: Any,
    state: dict[str, Any],
    refresh: Callable[[], None],
    target_work_id: str | None = None,
) -> None:
    action = {
        "key": "quick_approve" if review_status == "approved" and not notes and not changes else "save_stage_review",
        "label": "Quick Approve" if review_status == "approved" and not notes and not changes else "Save Stage Review",
        "target_run_id": run_id,
        "target_stage_id": stage,
        "target_work_id": target_work_id,
    }
    language = str(state.get("language") or "en")
    def execute() -> dict[str, Any]:
        return actions.save_stage_review(
            run_id,
            stage=stage,
            review_status=str(review_status),
            user_notes=str(notes or ""),
            requested_changes=str(changes or ""),
            target_rework_stage=str(rework_target) if rework_target else None,
        )
    def verify(result: dict[str, Any]) -> tuple[bool, str | None]:
        return bool(result.get("review_id")), "Stage Review was not assigned an append-only review id."
    await _execute_action_lifecycle(action, state, refresh, execute, language=language, verify=verify)


def _render_stage_artifact_rows(
    ui: Any,
    artifacts: list[dict[str, Any]],
    backend: WorkflowConsoleBackend,
    state: dict[str, Any],
    *,
    compact: bool,
) -> None:
    language = str(state.get("language") or "en")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        with ui.row().classes("w-full items-center justify-between gap-2"):
            with ui.column().classes("gap-0"):
                ui.label(artifact.get("display_name") or artifact.get("name") or "Artifact").classes("text-sm font-medium")
                source_stage = artifact.get("source_stage_id") or "stage"
                if language == "zh":
                    ui.label(f"{artifact.get('kind', 'file').upper()} · {artifact.get('validation_status') or 'available'} · 阶段：{source_stage}").classes("workflow-meta")
                else:
                    ui.label(f"{artifact.get('kind', 'file').upper()} · {artifact.get('validation_status') or 'available'} · Stage: {source_stage}").classes("workflow-meta")
                if artifact.get("summary") and not compact:
                    ui.label(str(artifact["summary"])).classes("text-xs text-gray-600")
            with ui.row().classes("gap-1"):
                open_button = ui.button("Open", on_click=lambda _event=None, a=artifact: _show_artifact_contract_dialog(ui, backend, a, state)).props("outline dense")
                open_button.tooltip("Open the exact artifact shown here, including its source Run and stage. This does not change the workflow.")
                copy_button = ui.button("Copy", on_click=lambda _event=None, a=artifact: _copy_artifact_raw(ui, a)).props("flat dense")
                copy_button.tooltip("Copy the raw artifact content to the clipboard. This does not change the workflow.")
                if artifact.get("kind") == "stl" and artifact.get("source_run_id"):
                    run = quote(str(artifact.get("source_run_id")), safe="")
                    file_url = quote(f"/api/downloads/{run}/model.stl", safe="")
                    viewer = ui.link("View STL", target=f"/web-viewer/index.html?file={file_url}").classes("text-sm")
                    viewer.tooltip("Open this STL in the model viewer for its source Run.")
                if artifact.get("downloadable") and artifact.get("source_run_id"):
                    name = str(artifact.get("name"))
                    run = quote(str(artifact.get("source_run_id")), safe="")
                    download = ui.link("Download", target=f"/api/downloads/{run}/{quote(name, safe='')}").classes("text-sm")
                    download.tooltip("Download this generated model from its source Run.")
        related = artifact.get("related") if isinstance(artifact.get("related"), list) else []
        if related:
            with ui.expansion(f"Related {artifact.get('display_name') or artifact.get('name')} ({len(related)})").classes("w-full"):
                _render_stage_artifact_rows(ui, related, backend, state, compact=True)


def _group_stage_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Show one primary file per name and retain distinct lineage copies."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        if isinstance(artifact, dict):
            grouped.setdefault(str(artifact.get("name") or "artifact"), []).append(artifact)
    result = []
    for items in grouped.values():
        primary, *related = items
        result.append({**primary, "related": related, "related_count": len(related)})
    return result


def _copy_artifact_raw(ui: Any, artifact: dict[str, Any]) -> None:
    value = artifact.get("content")
    raw = value if isinstance(value, str) else json.dumps(value if value is not None else {}, indent=2, sort_keys=True)
    ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(raw)})")
    ui.notify("Artifact copied to clipboard.")


def _show_artifact_contract_dialog(ui: Any, backend: WorkflowConsoleBackend, artifact: dict[str, Any], state: dict[str, Any]) -> None:
    """Open one artifact using its explicit source contract, never just its name."""
    value = artifact.get("content")
    if value is None and artifact.get("source_run_id") and artifact.get("name"):
        try:
            value = read_artifact_page_content(backend, str(artifact["source_run_id"]), str(artifact["name"])).get("content")
        except Exception as exc:
            value = {"error": f"Unable to open artifact: {exc}"}
    with ui.dialog() as dialog, ui.card().classes("w-[860px] max-w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(artifact.get("display_name") or artifact.get("name") or "Artifact").classes("text-lg font-semibold")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense").tooltip("Close the artifact viewer without changing the workflow.")
        _key_values(ui, {
            "Artifact name": artifact.get("name"),
            "Source Run": artifact.get("source_run_id") or "Work lineage",
            "Source Stage": artifact.get("source_stage_id") or "Unknown",
            "Source": artifact.get("source_type") or "original",
            "Validation": artifact.get("validation_status") or "available",
            "Modified": artifact.get("modified_at") or "Not available",
        })
        tabs = ui.tabs().classes("w-full")
        with tabs:
            summary_tab = ui.tab("Summary")
            rendered_tab = ui.tab("Rendered / Structured")
            raw_tab = ui.tab("Raw")
        with ui.tab_panels(tabs, value=summary_tab).classes("w-full"):
            with ui.tab_panel(summary_tab):
                ui.label(artifact.get("summary") or "No user-facing summary is available.").classes("text-sm text-gray-700")
            with ui.tab_panel(rendered_tab):
                if artifact.get("kind") == "markdown" and isinstance(value, str):
                    ui.markdown(value).classes("w-full")
                elif artifact.get("kind") in {"step", "stl"}:
                    ui.label("This model artifact can be downloaded; STL can also be opened from the Parts page.").classes("text-sm text-gray-700")
                else:
                    ui.markdown(f"```json\n{json.dumps(value, indent=2, sort_keys=True) if not isinstance(value, str) else value}\n```").classes("w-full mono")
            with ui.tab_panel(raw_tab):
                raw = value if isinstance(value, str) else json.dumps(value, indent=2, sort_keys=True)
                ui.markdown(f"```\n{raw}\n```").classes("w-full mono")
    dialog.open()


def _run_workflow_page_action(ui: Any, actions: WorkflowConsoleActions, action: dict[str, Any], state: dict[str, Any], refresh: Callable[[], None]) -> None:
    if not action.get("enabled"):
        return
    if action.get("presentation_action") == "view_diagnostics":
        ui.notify("Open Advanced to inspect the raw diagnostic details.")
        return
    target = action.get("target_run_id")
    _schedule_action(_run_surface_action(actions, target, action, state, refresh))


def _render_workflow_context(ui: Any, context: Any, data: dict[str, Any], actions: WorkflowConsoleActions) -> None:
    if not isinstance(context, dict):
        return
    language = data.get("language", "en")
    run_id = data.get("selected_run_id")
    with ui.element("section").classes("workflow-context w-full"):
        ui.label(context.get("title") or _artifact_copy(language, "title")).classes("text-lg font-semibold")
        with ui.element("div").classes("workflow-context-grid w-full"):
            with ui.column().classes("w-full gap-2"):
                ui.label("用户输入" if language == "zh" else "User input").classes("text-sm font-medium text-gray-600")
                prompt = context.get("prompt") if isinstance(context.get("prompt"), dict) else None
                if prompt and prompt.get("present"):
                    ui.label("Prompt").classes("text-sm font-semibold")
                    try:
                        content = read_artifact_page_content(actions.backend, run_id, "prompt.txt")
                        ui.label(str(content.get("content") or "")).classes("workflow-prompt text-sm w-full")
                    except Exception as exc:
                        ui.label(f"Unable to read prompt: {exc}").classes("text-sm text-red-700")
                else:
                    ui.label("尚未提供 Prompt。" if language == "zh" else "No prompt is available yet.").classes("text-sm text-gray-500")
                requirements = context.get("requirements") if isinstance(context.get("requirements"), list) else []
                if requirements:
                    ui.label("需求资料" if language == "zh" else "Requirement records").classes("text-sm font-medium text-gray-600")
                    with ui.element("div").classes("workflow-record-list w-full"):
                        for artifact in requirements:
                            _render_context_record(ui, artifact, actions, language)
            with ui.column().classes("w-full gap-2"):
                stage_label = context.get("selected_stage_label") or ("所选阶段" if language == "zh" else "Selected stage")
                ui.label(("当前阶段资料: " if language == "zh" else "Current stage artifacts: ") + str(stage_label)).classes("text-sm font-medium text-gray-600")
                artifacts = context.get("stage_artifacts") if isinstance(context.get("stage_artifacts"), list) else []
                if artifacts:
                    _render_artifact_status_table(ui, artifacts, run_id, actions, context.get("table_columns") or [], language)
                else:
                    ui.label(context.get("empty_message") or "").classes("text-sm text-gray-500")


def _render_context_record(ui: Any, artifact: dict[str, Any], actions: WorkflowConsoleActions, language: str) -> None:
    with ui.element("div").classes("workflow-record w-full"):
        with ui.element("div").classes("workflow-record-copy"):
            ui.label(artifact.get("display_name") or "").classes("text-sm font-medium")
            ui.label(artifact.get("purpose") or "").classes("text-xs text-gray-500")
        if artifact.get("preview"):
            button = ui.button("查看摘要" if language == "zh" else "View summary", icon="visibility", on_click=lambda _event=None, a=artifact: _show_artifact_summary_dialog(ui, a, language)).props("outline dense")
            button.tooltip("查看用户可读摘要" if language == "zh" else "View user-readable summary")


def _render_artifact_status_table(
    ui: Any,
    artifacts: list[dict[str, Any]],
    run_id: str | None,
    actions: WorkflowConsoleActions,
    columns: list[str],
    language: str,
) -> None:
    with ui.element("div").classes("artifact-status-table w-full"):
        with ui.element("div").classes("artifact-status-head"):
            for label in columns:
                ui.label(label)
        for artifact in artifacts:
            with ui.element("div").classes("artifact-status-row"):
                ui.label(artifact.get("display_name") or artifact.get("name") or "").classes("text-sm font-medium")
                ui.label(artifact.get("purpose") or "").classes("text-sm text-gray-600")
                ui.badge(artifact.get("direction_label") or "").classes("bg-slate-100 text-slate-700")
                status = ui.badge(artifact.get("status_label") or "").classes(_badge_class(artifact.get("status")))
                status.tooltip(artifact.get("status_help") or "")
                with ui.row().classes("gap-1"):
                    _render_artifact_access(ui, artifact, run_id, actions, language, compact=True)


def _render_artifact_access(
    ui: Any,
    artifact: dict[str, Any],
    run_id: str | None,
    actions: WorkflowConsoleActions,
    language: str,
    *,
    compact: bool = False,
) -> None:
    name = str(artifact.get("name") or "")
    if artifact.get("preview"):
        if compact:
            preview = ui.button(icon="visibility", on_click=lambda _event=None, a=artifact: _show_artifact_summary_dialog(ui, a, language)).props("flat round dense")
        else:
            preview = ui.button(artifact.get("display_name") or name, icon="visibility", on_click=lambda _event=None, a=artifact: _show_artifact_summary_dialog(ui, a, language)).props("outline dense")
        preview.tooltip("查看摘要" if language == "zh" else "View summary")
    if artifact.get("stl_previewable") and run_id:
        file_url = quote(f"/api/downloads/{quote(run_id, safe='')}/model.stl", safe="")
        viewer = ui.link("STL", target=f"/web-viewer/index.html?file={file_url}").classes("text-sm")
        viewer.tooltip("查看 STL" if language == "zh" else "View STL")
    if artifact.get("downloadable") and run_id:
        download = ui.link("下载" if language == "zh" else "Download", target=f"/api/downloads/{quote(run_id, safe='')}/{quote(name, safe='')}").classes("text-sm")
        download.tooltip("下载" if language == "zh" else "Download")
    if not compact and artifact.get("previewable"):
        ui.label(artifact.get("purpose") or "").classes("text-xs text-gray-500")


def _show_artifact_summary_dialog(ui: Any, artifact: dict[str, Any], language: str) -> None:
    preview = artifact.get("preview") if isinstance(artifact.get("preview"), dict) else {}
    with ui.dialog() as dialog, ui.card().classes("w-[560px] max-w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(preview.get("title") or artifact.get("display_name") or "").classes("text-lg font-semibold")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense").tooltip("Close this summary without changing the workflow.")
        ui.label(preview.get("summary") or artifact.get("purpose") or "").classes("text-sm text-gray-600")
        for item in preview.get("items") or []:
            if isinstance(item, dict):
                with ui.row().classes("w-full items-start justify-between gap-4"):
                    ui.label(item.get("label") or "").classes("text-sm text-gray-500")
                    ui.label(item.get("value") or "").classes("text-sm text-gray-800 text-right")
    dialog.open()


def _render_artifact_audit_entry(
    ui: Any,
    artifact: dict[str, Any],
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> None:
    name = artifact.get("name") or "artifact"
    with ui.expansion(name, icon="description", value=name == "prompt.txt").classes("artifact-audit-card w-full"):
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            ui.badge(_artifact_source_label(language, artifact)).classes("bg-slate-100 text-slate-700")
            ui.badge(_artifact_edit_label(language, artifact)).classes("bg-blue-50 text-blue-700" if artifact.get("editable") else "bg-gray-100 text-gray-600")
            if artifact.get("override_present"):
                ui.badge(_artifact_copy(language, "override_active")).classes("bg-purple-50 text-purple-700")
            validation = artifact.get("validation_status")
            if validation:
                ui.badge(f"{_artifact_copy(language, 'validation')}: {validation}").classes("bg-green-50 text-green-700")
        ui.label(artifact.get("summary") or _artifact_copy(language, "available")).classes("artifact-summary text-sm text-gray-700")
        downstream = artifact.get("downstream_stages_affected") or []
        if downstream:
            ui.label(f"{_artifact_copy(language, 'affects')}: {', '.join(downstream)}").classes("text-xs text-gray-500")
        if artifact.get("raw_json_available"):
            ui.label("用户可读摘要可从当前阶段的输入与输出区域查看。" if language == "zh" else "A user-readable summary is available from the current stage inputs and outputs area.").classes("text-xs text-gray-500")
        elif artifact.get("name") == "prompt.txt":
            with ui.expansion(_artifact_copy(language, "content"), icon="text_snippet").classes("w-full"):
                content = read_artifact_page_content(actions.backend, data.get("selected_run_id"), artifact["name"])
                ui.label(str(content.get("content") or "")).classes("text-sm whitespace-pre-wrap")
        elif not artifact.get("editable"):
            ui.label(artifact.get("edit_disabled_reason") or _artifact_copy(language, "read_only")).classes("text-xs text-gray-500")


def _artifact_copy(language: str, key: str) -> str:
    english = {
        "title": "Workflow inputs & artifacts",
        "intro": "Review the requirement, prompts, plans, and generated records used by this workflow. Original files are preserved.",
        "source": "Original artifact",
        "override_source": "Validated override",
        "editable": "Editable override",
        "read_only": "Read-only record",
        "override_active": "Override active",
        "validation": "Validation",
        "affects": "Affects downstream stages",
        "content": "View content",
        "available": "Available",
    }
    chinese = {
        "title": "工作流输入与资料",
        "intro": "查看此工作流使用的需求、提示词、计划和生成记录。原始文件会被保留。",
        "source": "原始资料",
        "override_source": "已验证的覆盖版本",
        "editable": "可编辑覆盖版本",
        "read_only": "只读记录",
        "override_active": "覆盖版本生效中",
        "validation": "验证状态",
        "affects": "影响下游阶段",
        "content": "查看内容",
        "available": "可用",
    }
    return (chinese if language == "zh" else english)[key]


def _artifact_source_label(language: str, artifact: dict[str, Any]) -> str:
    return _artifact_copy(language, "override_source" if artifact.get("source") == "user_override" else "source")


def _artifact_edit_label(language: str, artifact: dict[str, Any]) -> str:
    return _artifact_copy(language, "editable" if artifact.get("editable") else "read_only")


def _render_workflow_stage_graph(
    ui: Any,
    surface: dict[str, Any],
    on_select_stage: Callable[[str], None],
    language: str = "en",
    on_open_candidate: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    graph = surface.get("workflow_graph") if isinstance(surface.get("workflow_graph"), dict) else {}
    selected = surface.get("selected_stage_id")
    if not graph:
        _render_graph_stage_row(ui, surface.get("graph_nodes") or [], selected, on_select_stage)
        return
    with ui.column().classes("workflow-graph w-full gap-4"):
        with ui.column().classes("workflow-graph-canvas gap-4"):
            ui.label("工作流图" if language == "zh" else "DOT WORKFLOW GRAPH").classes("workflow-graph-label")
            _render_graph_stage_row(ui, graph.get("stage_spine") or [], selected, on_select_stage, language=language)
            ui.label("装配计划分为候选零件和参考上下文" if language == "zh" else "Assembly Plan branches into candidates and reference context").classes("workflow-branch-note")
            candidates = graph.get("part_candidates") if isinstance(graph.get("part_candidates"), list) else []
            with ui.column().classes("workflow-lane gap-2"):
                ui.label("候选零件" if language == "zh" else "CANDIDATE PARTS").classes("workflow-graph-label")
                if candidates:
                    with ui.row().classes("workflow-lane-row"):
                        for candidate in candidates:
                            _render_part_candidate_node(ui, candidate, on_open_candidate, language=language)
                else:
                    ui.label("尚未识别可生成的候选零件。" if language == "zh" else "No generated part candidates have been identified yet.").classes("text-sm text-gray-500")
            references = graph.get("reference_lane") if isinstance(graph.get("reference_lane"), list) else []
            if references:
                with ui.column().classes("workflow-lane gap-2"):
                    ui.label("参考组件" if language == "zh" else "REFERENCE COMPONENTS").classes("workflow-graph-label")
                    with ui.row().classes("workflow-lane-row"):
                        for candidate in references:
                            _render_part_candidate_node(ui, candidate, on_open_candidate, language=language)
            selected_part = graph.get("selected_part_id") or ("已选候选零件" if language == "zh" else "a selected candidate")
            ui.label((f"已选零件流程 · {selected_part}" if language == "zh" else f"SELECTED PART PIPELINE · {selected_part}")).classes("workflow-graph-label")
            _render_graph_stage_row(ui, graph.get("selected_part_pipeline") or [], selected, on_select_stage, language=language)
            tail = graph.get("review_tail") if isinstance(graph.get("review_tail"), list) else []
            if tail:
                ui.label("工作流评审 / 返工" if language == "zh" else "WORKFLOW REVIEW / REWORK").classes("workflow-graph-label")
                _render_graph_stage_row(ui, tail, selected, on_select_stage, language=language)


def _render_graph_stage_row(
    ui: Any,
    nodes: list[dict[str, Any]],
    selected: Any,
    on_select_stage: Callable[[str], None],
    *,
    language: str = "en",
) -> None:
    with ui.row().classes("workflow-stage-row w-full"):
        for index, node in enumerate(nodes):
            stage_id = str(node.get("stage_id") or "")
            status = node.get("status") or "unknown"
            step_classes = "workflow-step"
            if stage_id == selected:
                step_classes += " workflow-step-selected"
            step = ui.column().classes(step_classes)
            step.tooltip(_workflow_node_tooltip(node))
            step.on("click", lambda _event, s=stage_id: on_select_stage(s))
            with step:
                ui.element("div").classes(f"workflow-dot status-{_dot_status(status)} kind-{node.get('kind') or 'stage'}")
                ui.label(stage_label(language, stage_id, node.get("label"))).classes("text-sm font-semibold text-center")
                ui.label(_display_status(status, language)).classes("workflow-node-status text-center")
                if node.get("attention") not in {None, "none"}:
                    ui.label(
                        ("需要处理" if node.get("attention") == "required" else "进行中")
                        if language == "zh"
                        else ("attention required" if node.get("attention") == "required" else "in progress")
                    ).classes("workflow-attention")
                if node.get("has_override"):
                    ui.label("覆盖版本生效" if language == "zh" else "override active").classes("workflow-attention")
            if index < len(nodes) - 1:
                ui.element("div").classes("workflow-connector")


def _render_part_candidate_node(
    ui: Any,
    candidate: dict[str, Any],
    on_open_candidate: Callable[[dict[str, Any]], None] | None,
    *,
    language: str = "en",
) -> None:
    status = str(candidate.get("status") or "candidate")
    classes = "workflow-step workflow-part-candidate" + (" reference-component" if candidate.get("kind") == "reference_component" or candidate.get("reference_only") else "")
    if candidate.get("selected"):
        classes += " workflow-step-selected"
    node = ui.column().classes(classes)
    node.tooltip(
        "查看候选零件详情。\n\n结果：仅查看候选零件，不会改变当前选择或当前 Work。"
        if language == "zh"
        else "Open Candidate Detail.\n\nResult: inspect this candidate; it does not change selection or Current Work."
    )
    if on_open_candidate is not None:
        node.on("click", lambda _event, value=dict(candidate): on_open_candidate(value))
    with node:
        ui.element("div").classes(f"workflow-dot status-{_dot_status(status)} kind-{candidate.get('kind') or 'candidate_part'}")
        ui.label(candidate.get("part_id") or "part").classes("text-sm font-semibold text-center")
        ui.label(
            ("仅参考" if language == "zh" else "reference-only")
            if candidate.get("reference_only")
            else (candidate.get("role") or ("装配组件" if language == "zh" else "assembly component"))
        ).classes("text-xs text-gray-500 text-center")
        ui.label(_display_status(status, language)).classes("workflow-node-status")
        if candidate.get("supported_candidate"):
            ui.label("支持生成" if language == "zh" else "supported candidate").classes("text-xs text-green-700 text-center")




def _show_candidate_detail(
    ui: Any,
    candidate: dict[str, Any],
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    *,
    read_only: bool,
) -> None:
    """Open candidate detail and expose its explicit, confirmable Work action."""
    language = str(data.get("language") or "en")
    with ui.dialog() as dialog, ui.card().classes("w-[620px] max-w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(i18n_copy(language, "candidate_detail")).classes("text-lg font-semibold")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense").tooltip("关闭候选零件详情；不会改变选择。" if language == "zh" else "Close Candidate Detail without changing the selected part.")
        fields = (
            (("零件" if language == "zh" else "Part"), candidate.get("part_id")), (("角色" if language == "zh" else "Role"), candidate.get("role")),
            (("说明" if language == "zh" else "Brief"), candidate.get("short_summary")), (("状态" if language == "zh" else "Status"), candidate.get("status")),
            (("生成策略" if language == "zh" else "Generation strategy"), candidate.get("generation_strategy")),
            (("支持生成" if language == "zh" else "Supported candidate"), candidate.get("supported_candidate")),
            (("仅参考" if language == "zh" else "Reference only"), candidate.get("reference_only")), (("已选择" if language == "zh" else "Selected"), candidate.get("selected")),
        )
        for label, value in fields:
            ui.label(f"{label}: {value if value not in (None, '') else i18n_copy(language, 'not_available')}").classes("text-sm")
        selection_action = _candidate_selection_action(candidate, data, read_only)
        button = ui.button(
            selection_action["label"],
            on_click=lambda _event=None, a=selection_action: _show_candidate_selection_confirmation(
                ui, dialog, a, candidate, actions, state, refresh
            ),
        ).props("outline dense")
        button.tooltip(selection_action["tooltip"])
        if not selection_action["enabled"] or _pending_action_matches(state, selection_action):
            button.disable()
    dialog.open()


def _candidate_selection_action(candidate: dict[str, Any], data: dict[str, Any], read_only: bool) -> dict[str, Any]:
    page = data.get("workflow_page") if isinstance(data.get("workflow_page"), dict) else {}
    work = page.get("work") if isinstance(page.get("work"), dict) else data.get("selected_work") or {}
    summary = work.get("summary") if isinstance(work.get("summary"), dict) else {}
    work_id = summary.get("work_id") or work.get("work_id")
    lineage = page.get("active_lineage") if isinstance(page.get("active_lineage"), dict) else {}
    part_id = candidate.get("part_id")
    current = bool(candidate.get("selected"))
    supported = bool(candidate.get("supported_candidate"))
    reference = bool(candidate.get("reference_only")) or candidate.get("generation_strategy") == "reference_only"
    enabled = bool(part_id and work_id and lineage.get("active_root_run_id")) and not read_only and supported and not reference and not current
    language = str(data.get("language") or "en")
    if read_only:
        disabled_reason = "Run 快照只读。请返回当前 Work 后再选择候选零件。" if language == "zh" else "Run Snapshot is read-only. Return to Current Work to select a candidate."
    elif reference:
        disabled_reason = "参考组件仅用于上下文，不能用于生成。" if language == "zh" else "Reference components are context only and cannot be selected for generation."
    elif not supported:
        disabled_reason = "当前单零件流程不支持该候选零件。" if language == "zh" else "This candidate is not supported by the current single-part workflow."
    elif current:
        disabled_reason = "该候选零件已被选定；无需重复创建覆盖版本。" if language == "zh" else "This candidate is already selected; no duplicate override is needed."
    else:
        disabled_reason = None
    target_run = lineage.get("active_root_run_id") or candidate.get("source_run_id")
    return {
        "key": "select_candidate_part",
        "label": i18n_copy(language, "use_this_part_next"),
        "category": "structured_input",
        "scope": "run_snapshot" if read_only else "current_work",
        "target_work_id": work_id,
        "target_run_id": target_run,
        "target_stage_id": "assembly_plan",
        "part_id": part_id,
        "requires_confirmation": True,
        "creates_new_run": False,
        "updates_active_lineage": False,
        "enabled": enabled,
        "disabled_reason": disabled_reason,
        "tooltip": "\n".join([
            "将此零件设为下一步建模对象。" if language == "zh" else "Set this part as the next modeling target.",
            "",
            "系统会保存新的装配计划覆盖版本，并将旧的下游结果标记为过期。已有 Run 和已批准结果不会被删除。" if language == "zh" else "CadFlow saves a new Assembly Plan override and marks old downstream results stale. Existing Runs and accepted results remain.",
            *(["", (f"当前不可用：{disabled_reason}" if language == "zh" else f"Currently unavailable: {disabled_reason}")] if disabled_reason else []),
        ]),
    }


def _show_candidate_selection_confirmation(
    ui: Any,
    detail_dialog: Any,
    action: dict[str, Any],
    candidate: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    if not action.get("enabled"):
        return
    language = str(state.get("language") or "en")
    pending = ActionExecutionState.from_action(action, status="confirming", message=("等待确认选择候选零件。" if language == "zh" else "Waiting for candidate selection confirmation."))
    _set_action_execution(state, pending, action)
    with ui.dialog() as confirm, ui.card().classes("w-[620px] max-w-full"):
        ui.label("确认候选零件选择" if language == "zh" else "Confirm candidate selection").classes("text-lg font-semibold")
        ui.label((f"当前已选候选零件: {candidate.get('current_selected_part_id') or '当前装配计划选择'}" if language == "zh" else f"Current selected candidate: {candidate.get('current_selected_part_id') or 'current Assembly Plan selection'}")).classes("text-sm")
        ui.label((f"新候选零件: {action.get('part_id')}" if language == "zh" else f"New candidate: {action.get('part_id')}")).classes("text-sm")
        ui.label("以下阶段将变为过期：零件请求、零件评审、已评审交接、CAD IR 草稿、零件建模、零件结果评审和工作流评审。" if language == "zh" else "The following stages become stale: Part Request, Part Review, Reviewed Handoff, CAD IR Draft, Part Modeling, Part Result Review, and Workflow Review.").classes("text-sm")
        ui.label("旧 Run 和已接受零件结果会保留；不会自动开始 CAD 生成。" if language == "zh" else "Old Runs and accepted part results are retained. CAD generation will not start automatically.").classes("text-sm text-gray-700")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(i18n_copy(language, "cancel"), on_click=lambda: (confirm.close(), state.__setitem__("action_execution", None))).props("flat") \
                .tooltip("取消，不改变装配计划覆盖版本或 Work 指针。" if language == "zh" else "Cancel without changing the Assembly Plan override or Work pointers.")
            ui.button(
                i18n_copy(language, "confirm_selection"),
                on_click=lambda: _schedule_action(_apply_candidate_selection(
                    action, actions, state, refresh, confirm, detail_dialog
                )),
            ).props("color=primary") \
                .tooltip("写入经过验证、版本化的装配计划覆盖版本，并刷新当前 Work 视图。" if language == "zh" else "Write the validated versioned Assembly Plan override and refresh the Current Work view.")
    confirm.open()


async def _apply_candidate_selection(
    action: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    confirm: Any,
    detail_dialog: Any,
) -> None:
    language = str(state.get("language") or "en")
    backend = actions.backend
    before = backend._read_work_manifest(str(action["target_work_id"])).get("accepted_part_results")

    def execute() -> dict[str, Any]:
        return actions.select_candidate_part(
            str(action["target_run_id"]), work_id=str(action["target_work_id"]), part_id=str(action["part_id"])
        )

    def verify(result: dict[str, Any]) -> tuple[bool, str | None]:
        run_path = backend.resolve_run(str(action["target_run_id"]))
        override = backend.active_override_path(run_path, "assembly_plan.json")
        active = backend.read_active_artifact_content(run_path, "assembly_plan.json")
        original = next((path for path in run_path.rglob("assembly_plan.json") if "edits" not in path.parts), None)
        original_data = json.loads(original.read_text(encoding="utf-8")) if original else None
        work_after = backend._read_work_manifest(str(action["target_work_id"]))
        stale = result.get("downstream_stages_affected") or []
        expected_stale = {"part_request", "part_review", "reviewed_handoff", "cad_ir_draft", "part_modeling", "part_result_review", "workflow_review"}
        ok = bool(override) and isinstance(active, dict) and active.get("selected_part_id") == action.get("part_id") and isinstance(original_data, dict) and original_data.get("selected_part_id") != action.get("part_id") and expected_stale.issubset(set(stale)) and work_after.get("accepted_part_results") == before and result.get("next_action") == "Create Part Request"
        return ok, None if ok else "Candidate selection postcondition verification failed: active override, original plan, stale stages, accepted results, or next action did not match."

    result = await _execute_action_lifecycle(action, state, refresh, execute, language=language, verify=verify)
    if result is not None:
        state["candidate_selection_result"] = result
        # Keep the user at the changed source of truth; do not jump ahead.
        state["selected_stage_id"] = "assembly_plan"
        confirm.close()
        detail_dialog.close()


def _workflow_node_tooltip(node: dict[str, Any]) -> str:
    hover = node.get("hover") if isinstance(node.get("hover"), dict) else {}
    if not hover:
        return str(node.get("short_summary") or node.get("primary_action") or "Select stage")
    lines = [value for value in (
        hover.get("title"),
        hover.get("summary"),
        hover.get("reason"),
        hover.get("consequence"),
        hover.get("recommended_action"),
    ) if value]
    return "\n".join(str(value) for value in lines)


def _render_selected_stage_detail(
    ui: Any,
    stage: dict[str, Any] | None,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    if stage is None:
        ui.label("Select a workflow stage.").classes("text-gray-600")
        return
    with ui.card().classes("w-full shadow-none border border-gray-200"):
        _render_status_hero_banner(ui, stage.get("status_banner"), stage)
        _render_status_explanation(ui, stage.get("status_explanation"), stage.get("display_language"), bool(stage.get("current_block")))
        action_groups = stage.get("action_groups") if isinstance(stage.get("action_groups"), dict) else {}
        language = stage.get("display_language")
        _render_action_group(ui, _detail_label("Primary actions", language), action_groups.get("primary"), data, actions, state, refresh, primary=True)
        cards = stage.get("detail_cards") if isinstance(stage.get("detail_cards"), list) else []
        with ui.element("div").classes("stage-detail-grid w-full"):
            for card in cards:
                if card.get("title") not in {"What happened", "Why it stopped", "Why it matters", "发生了什么", "为什么停止", "为什么重要"}:
                    _render_stage_detail_card(ui, card)
        other_actions = [
            *[action for action in action_groups.get("secondary", []) if isinstance(action, dict)],
            *[action for action in action_groups.get("advanced", []) if isinstance(action, dict)],
            *[action for action in action_groups.get("disabled", []) if isinstance(action, dict)],
        ]
        _render_action_group(ui, _detail_label("Other actions", language), other_actions, data, actions, state, refresh)
        with ui.expansion("高级详情" if language == "zh" else "Advanced details", icon="info").classes("w-full"):
            debug = stage.get("debug") if isinstance(stage.get("debug"), dict) else {}
            codes = debug.get("diagnostic_codes") if isinstance(debug.get("diagnostic_codes"), list) else []
            if codes:
                _list_block(ui, "诊断标记" if language == "zh" else "Diagnostic markers", codes)
            else:
                ui.label("没有需要额外处理的诊断信息。" if language == "zh" else "No additional diagnostic markers are available.").classes("text-sm text-gray-500")


def _detail_label(text: str, language: Any) -> str:
    if language != "zh":
        return text
    return {
        "Primary actions": "主要操作",
        "Other actions": "其他操作",
    }.get(text, text)


def _render_status_hero_banner(ui: Any, banner: Any, stage: dict[str, Any]) -> None:
    value = banner if isinstance(banner, dict) else {}
    status = str(value.get("status") or stage.get("status") or "unknown")
    with ui.column().classes(f"stage-status-banner {status} w-full gap-2"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(value.get("title") or stage.get("stage_name") or stage.get("key")).classes("text-xl font-semibold")
            ui.badge(status.replace("_", " ")).classes(_badge_class(status))
        ui.label(value.get("summary") or stage.get("human_summary") or "").classes("text-sm text-gray-700")
        if value.get("consequence"):
            ui.label(value["consequence"]).classes("text-sm font-medium text-gray-800")
        with ui.row().classes("w-full gap-2 flex-wrap"):
            for badge in value.get("badges") or []:
                if isinstance(badge, dict):
                    ui.badge(f"{badge.get('label')}: {badge.get('value')}").classes(_badge_class(badge.get("status")))


def _render_status_explanation(ui: Any, explanation: Any, language: Any, blocked: bool) -> None:
    if not isinstance(explanation, dict):
        return
    what_happened = explanation.get("what_happened") if isinstance(explanation.get("what_happened"), list) else []
    why = explanation.get("why")
    if not what_happened and not why:
        return
    labels = ("发生了什么", "为什么停止" if blocked else "为什么重要") if language == "zh" else ("What happened", "Why it stopped" if blocked else "Why it matters")
    with ui.element("div").classes("stage-status-explanation w-full"):
        if what_happened:
            with ui.column().classes("gap-1"):
                ui.label(labels[0]).classes("text-sm font-medium text-gray-600")
                for item in what_happened[:2]:
                    ui.label(str(item)).classes("text-sm text-gray-700")
        if why:
            with ui.column().classes("gap-1"):
                ui.label(labels[1]).classes("text-sm font-medium text-gray-600")
                ui.label(str(why)).classes("text-sm text-gray-700")


def _render_stage_detail_card(ui: Any, card: Any) -> None:
    if not isinstance(card, dict):
        return
    with ui.element("section").classes("stage-detail-card"):
        ui.html(f"<h3>{card.get('title') or 'Details'}</h3>")
        items = card.get("items") if isinstance(card.get("items"), list) else []
        if card.get("kind") == "chips":
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for item in items:
                    if isinstance(item, dict):
                        ui.badge(item.get("label") or "").classes(_badge_class(item.get("status")))
        else:
            with ui.column().classes("w-full gap-1"):
                for item in items[:5]:
                    if isinstance(item, dict):
                        with ui.row().classes("w-full items-center justify-between gap-2"):
                            ui.label(item.get("label") or "").classes("text-sm text-gray-700")
                            ui.badge(item.get("value") or "").classes(_badge_class(item.get("status")))
                    else:
                        with ui.row().classes("items-start gap-2"):
                            ui.label("•").classes("text-sm text-gray-500")
                            ui.label(str(item)).classes("text-sm text-gray-700")


def _render_action_group(
    ui: Any,
    title: str,
    group: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    *,
    primary: bool = False,
) -> None:
    action_list = group if isinstance(group, list) else []
    if not action_list:
        return
    if title:
        ui.label(title).classes("text-sm font-medium text-gray-600")
    with ui.row().classes("w-full gap-2 flex-wrap"):
        for action in action_list:
            if not isinstance(action, dict):
                continue
            button = ui.button(
                action.get("label") or action.get("key"),
                on_click=lambda _event=None, a=action: _run_detail_action(ui, actions, data, a, state, refresh),
            ).props("dense" if primary else "outline dense")
            button.tooltip(action.get("tooltip") or action.get("disabled_reason") or "Unavailable action")
            if not action.get("enabled"):
                button.disable()


def _run_detail_action(
    ui: Any,
    actions: WorkflowConsoleActions,
    data: dict[str, Any],
    action: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    run_id = action.get("target_run_id") if isinstance(action.get("target_run_id"), str) else data.get("selected_run_id")
    if action.get("presentation_action") == "view_cad_ir_draft" and run_id:
        _show_stage_artifact_dialog(ui, actions.backend, run_id, str(action.get("artifact_name") or "cad_ir_draft.json"), language=str(state.get("language") or "en"))
        return
    if action.get("presentation_action") == "edit_assembly_plan" and run_id:
        _show_stage_artifact_dialog(
            ui,
            actions.backend,
            run_id,
            str(action.get("artifact_name") or "assembly_plan.json"),
            editor_context=(data, actions, state, refresh),
            language=str(state.get("language") or "en"),
        )
        return
    if action.get("presentation_action") == "view_diagnostics":
        ui.notify("Open Debug / Diagnostics below to inspect the raw diagnostic details.")
        return
    _schedule_action(_run_surface_action(actions, run_id, action, state, refresh))


def _show_stage_artifact_dialog(
    ui: Any,
    backend: WorkflowConsoleBackend,
    run_id: str,
    artifact_name: str,
    *,
    editor_context: tuple[dict[str, Any], WorkflowConsoleActions, dict[str, Any], Callable[[], None]] | None = None,
    language: str = "en",
) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(artifact_name).classes("text-lg font-semibold")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense").tooltip("Close this artifact viewer without changing the workflow.")
        try:
            content = read_artifact_page_content(backend, run_id, artifact_name)
            value = content.get("content")
            if isinstance(value, str):
                ui.label(value).classes("text-sm whitespace-pre-wrap w-full")
            else:
                _render_artifact_content_summary(ui, artifact_name, value, language)
            if editor_context and artifact_name == "assembly_plan.json":
                ui.separator()
                page_data, console_actions, state, refresh = editor_context
                _render_artifact_override_editor(
                    ui,
                    page_data,
                    console_actions,
                    state,
                    refresh,
                    {"name": artifact_name, "editable": True, "canonical_name": "assembly_plan.json"},
                    content.get("content"),
                )
        except Exception as exc:
            ui.label(f"Unable to open this artifact: {exc}").classes("text-sm text-red-700")
    dialog.open()


def _render_artifact_content_summary(ui: Any, artifact_name: str, value: Any, language: str) -> None:
    data = value if isinstance(value, dict) else {}
    is_zh = language == "zh"
    fields = {
        "requirement.json": (("object_goal", "目标" if is_zh else "Goal"), ("part_type", "类型" if is_zh else "Type"), ("scope", "范围" if is_zh else "Scope")),
        "requirement_v2.json": (("object_goal", "目标" if is_zh else "Goal"), ("part_type", "类型" if is_zh else "Type"), ("requirement_status", "状态" if is_zh else "Status")),
        "assembly_plan.json": (("selected_candidate", "选定零件" if is_zh else "Selected part"), ("part_count", "零件数" if is_zh else "Part count")),
        "part_create_request.json": (("part_id", "零件" if is_zh else "Part"), ("role", "职责" if is_zh else "Role"), ("brief", "说明" if is_zh else "Brief")),
        "cad_ir_draft.json": (("part_id", "零件" if is_zh else "Part"), ("part_type", "零件类型" if is_zh else "Part type"), ("status", "状态" if is_zh else "Status")),
    }.get(artifact_name, (("status", "状态" if is_zh else "Status"), ("artifact_type", "记录类型" if is_zh else "Record type"), ("part_id", "零件" if is_zh else "Part")))
    shown = False
    for key, label in fields:
        field_value = data.get(key)
        if field_value not in (None, "", [], {}):
            shown = True
            with ui.row().classes("w-full items-start justify-between gap-4"):
                ui.label(label).classes("text-sm text-gray-500")
                ui.label(_compact_display(field_value)).classes("text-sm text-gray-800 text-right")
    if artifact_name == "assembly_plan.json":
        parts = [str(item.get("part_id")) for item in data.get("parts", []) if isinstance(item, dict) and item.get("part_id")]
        if parts:
            shown = True
            ui.label("候选零件" if is_zh else "Candidate parts").classes("text-sm text-gray-500")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for part in parts[:8]:
                    ui.badge(part).classes("bg-slate-100 text-slate-700")
    if not shown:
        ui.label("该记录可用，但没有可展示的用户摘要字段。" if is_zh else "This record is available, but it has no user-facing summary fields.").classes("text-sm text-gray-500")


def _render_stage_review_card(
    ui: Any,
    card: dict[str, Any],
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    with ui.card().classes("w-full shadow-none border border-gray-200"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(card.get("stage_name") or card.get("key")).classes("text-lg font-medium")
            ui.badge(card.get("status") or "unknown").classes(_badge_class(card.get("status")))
        _key_values(ui, {
            "Gate decision": _compact_display(card.get("gate_decision")),
            "Agent / adapter": _compact_display(card.get("agent_identity")),
            "Diagnostics": ", ".join(card.get("diagnostic_codes") or []) or "Empty",
            "Blocked reasons": _compact_display(card.get("blocked_reasons")) or "Empty",
        })
        _artifact_chip_row(ui, "Inputs", card.get("input_artifacts"))
        _artifact_chip_row(ui, "Outputs", card.get("output_artifacts"))
        summary = card.get("report_summary")
        if summary:
            with ui.expansion("Readable summary").classes("w-full"):
                ui.markdown(f"```json\n{json.dumps(summary, indent=2, sort_keys=True)}\n```").classes("w-full mono")
        with ui.row().classes("w-full gap-2"):
            for action in card.get("available_actions") or []:
                button = ui.button(
                    action.get("label") or action.get("key"),
                    on_click=lambda _event=None, a=action: _schedule_action(_run_surface_action(actions, a.get("target_run_id"), a, state, refresh)),
                ).props("outline dense")
                button.tooltip(action.get("tooltip") or action.get("disabled_reason") or "Run this action for the displayed Work, Run, and stage.")
                if not action.get("enabled"):
                    button.disable()
        if card.get("raw_artifacts"):
            with ui.row().classes("w-full gap-2"):
                for artifact in card.get("raw_artifacts") or []:
                    ui.badge(artifact.get("name")).classes("bg-gray-100 text-gray-700")


def _render_artifact_override_editor(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    artifact: dict[str, Any],
    content: Any,
) -> None:
    if not artifact.get("editable"):
        ui.label(artifact.get("edit_disabled_reason") or "Not editable").classes("text-sm text-gray-500")
        return
    with ui.expansion("Edit Artifact Override", icon="edit").classes("w-full"):
        ui.label("Saved edits are validated and versioned under edits/. The original artifact is preserved.").classes("text-sm text-gray-500")
        reason = ui.input("Edit reason").props("outlined").classes("w-full")
        editor = ui.textarea(
            "JSON override",
            value=json.dumps(content if isinstance(content, dict) else {}, indent=2, sort_keys=True),
        ).props("outlined autogrow").classes("w-full mono")
        result_key = f"artifact_override_result_{artifact.get('canonical_name') or artifact.get('name')}"
        if state.get(result_key) is not None:
            ui.markdown(f"```json\n{json.dumps(state[result_key], indent=2, sort_keys=True)}\n```").classes("w-full")
        with ui.row().classes("gap-2"):
            ui.button(
                "Validate / Save as override",
                icon="save",
                on_click=lambda: _save_artifact_override_ui(
                    actions,
                    data.get("selected_run_id"),
                    artifact.get("canonical_name") or artifact.get("name"),
                    editor.value,
                    reason.value,
                    state,
                    result_key,
                    refresh,
                ),
            ).tooltip("Parse JSON, validate schema/security rules, then save as active user override.")
            disabled = ui.button("Revert to original", icon="undo").props("outline")
            disabled.disable()
            disabled.tooltip("Revert/deactivate is not implemented in this MVP; edit artifacts remain auditable.")


def _artifact_chip_row(ui: Any, title: str, artifacts: Any) -> None:
    ui.label(title).classes("text-sm font-medium text-gray-600")
    with ui.row().classes("w-full gap-2"):
        for artifact in artifacts or []:
            name = artifact.get("name")
            present = artifact.get("present")
            ui.badge(f"{name}: {'present' if present else 'missing'}").classes(_badge_class("completed" if present else "not_started"))


def _perform_surface_action(
    actions: WorkflowConsoleActions,
    run_id: str | None,
    action: dict[str, Any],
 ) -> dict[str, Any]:
    if not run_id:
        raise ValueError("Select a run first.")
    backend_action = action.get("backend_action")
    if backend_action == "save_stage_review":
        return actions.save_stage_review(
                run_id,
                stage=action.get("stage") or "workflow_review",
                review_status=action.get("review_status") or "approved",
        )
    if backend_action == "part_request":
        return actions.create_part_request(run_id)
    if backend_action == "part_review":
        return actions.review_part_request(run_id)
    if backend_action == "reviewed_handoff":
        return actions.create_reviewed_handoff(run_id)
    if backend_action == "reviewed_part_create":
        return actions.create_reviewed_part(run_id)
    if backend_action == "part_result_review":
        return actions.review_part_result(run_id)
    if backend_action == "approve_part_result":
        work_id = action.get("target_work_id")
        if not isinstance(work_id, str):
            raise ValueError("Approve Single Part Result requires a target Work")
        return actions.approve_part_result(run_id, work_id=work_id)
    if backend_action == "create_workflow_review":
        return actions.create_workflow_review(run_id)
    if backend_action == "run_rework":
        result = actions.run_rework(run_id)
        decision = result.get("decision") if isinstance(result, dict) and isinstance(result.get("decision"), dict) else {}
        child_run_id = decision.get("child_run_id")
        target_work_id = action.get("target_work_id")
        if result.get("stage_count") and isinstance(target_work_id, str) and isinstance(child_run_id, str):
            actions.backend.activate_work_lineage(target_work_id, parent_run_id=run_id, child_run_id=child_run_id)
        return result
    raise ValueError(f"Unsupported surface action: {action.get('key')}")


async def _run_surface_action(
    actions: WorkflowConsoleActions,
    run_id: str | None,
    action: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    language = str(state.get("language") or "en")
    result = await _execute_action_lifecycle(
        action,
        state,
        refresh,
        lambda: _perform_surface_action(actions, run_id, action),
        language=language,
    )
    if result is not None and action.get("next_stage_on_success"):
        state["selected_stage_id"] = action["next_stage_on_success"]
        refresh()


def _render_workflow_nodes(
    ui: Any,
    data: dict[str, Any],
    on_select_node: Callable[[str], None] | None = None,
    on_select_page: Callable[[str], None] | None = None,
) -> None:
    work = data.get("selected_work") or {}
    current = work.get("current_state") if isinstance(work.get("current_state"), dict) else {}
    graph = work.get("workflow_graph") if isinstance(work.get("workflow_graph"), dict) else {}
    _label_with_help(ui, "Debug / Raw Workflow Graph", "保留原始节点图用于调试。主流程审阅请看上方 Workflow Stage Review。", "text-xl font-semibold")
    _key_values(ui, {
        "Current state": current.get("current_run_id") or "Empty",
        "Root run": current.get("root_run_id") or "Empty",
        "Next action": current.get("next_action") or "Empty",
        "History": current.get("immutability_note") or "Runs are immutable.",
    })
    _render_workflow_graph(ui, graph, on_select_node, on_select_page)
    _label_with_help(ui, "Debug Node Details", "紧凑节点清单。这里保留 artifact/action 细节，但不作为用户主概念。", "text-lg font-medium")
    for node in work.get("nodes") or []:
        with ui.card().classes("w-full shadow-none border border-gray-200"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(node.get("label") or node.get("id")).classes("text-lg font-medium")
                ui.badge(node.get("status") or "unknown").classes(_badge_class(node.get("status")))
            ui.label(node.get("summary") or "").classes("text-sm text-gray-700")
            _key_values(ui, {
                "Kind": node.get("kind"),
                "Artifacts": ", ".join(node.get("artifacts") or []) or "Empty",
                "Actions": ", ".join(node.get("actions") or []) or "Empty",
            })
            if on_select_node is not None:
                ui.button("Open node", icon="open_in_new", on_click=lambda _event=None, n=node: on_select_node(n["id"])).props("outline").tooltip("打开该节点详情，查看输入文件、输出文件、启动条件和 review/rework 操作。")


def _render_workflow_graph(
    ui: Any,
    graph: dict[str, Any],
    on_select_node: Callable[[str], None] | None,
    on_select_page: Callable[[str], None] | None,
) -> None:
    stage_nodes = graph.get("stage_nodes") if isinstance(graph.get("stage_nodes"), list) else []
    part_nodes = graph.get("part_nodes") if isinstance(graph.get("part_nodes"), list) else []
    review_nodes = graph.get("review_nodes") if isinstance(graph.get("review_nodes"), list) else []
    with ui.column().classes("workflow-graph w-full gap-4"):
        with ui.row().classes("w-full items-start gap-3"):
            for index, node in enumerate(stage_nodes):
                _render_graph_node_card(ui, node, "stage", on_select_node)
                if index < len(stage_nodes):
                    ui.label("->").classes("workflow-arrow self-center")
        if part_nodes:
            with ui.grid(columns=min(max(len(part_nodes), 1), 4)).classes("w-full gap-4"):
                for node in part_nodes:
                    _render_graph_node_card(ui, node, "part", on_select_node)
        else:
            with ui.card().classes("w-full shadow-none border border-dashed border-gray-300 bg-gray-50"):
                ui.label("No part split yet").classes("text-sm font-medium text-gray-600")
                ui.label("Requirement and planning nodes are available; part lanes appear after a split/assembly plan.").classes("text-xs text-gray-500")
        if review_nodes:
            with ui.row().classes("w-full items-start gap-3"):
                ui.label("->").classes("workflow-arrow self-center")
                for node in review_nodes:
                    can_open = node.get("id") not in {"products", "result"}
                    _render_graph_node_card(ui, node, "review", on_select_node if can_open else None, on_select_page)


def _render_graph_node_card(
    ui: Any,
    node: dict[str, Any],
    group: str,
    on_select_node: Callable[[str], None] | None,
    on_select_page: Callable[[str], None] | None = None,
) -> None:
    status = node.get("status") or "unknown"
    step = ui.column().classes("workflow-step")
    step.tooltip(_graph_tooltip(node))
    if on_select_node is not None and node.get("id") not in {"products", "result"} and not node.get("synthetic"):
        step.on("click", lambda _event, n=node: on_select_node(str(n.get("id"))))
    with step:
        ui.element("div").classes(f"workflow-dot {_dot_status(status)}")
        ui.label(node.get("label") or node.get("id")).classes("text-sm font-semibold text-center")
        ui.label(str(status)).classes("text-xs text-gray-500 text-center")
        if node.get("role"):
            ui.label(str(node.get("role"))).classes("text-xs text-gray-500")
        if group == "part":
            flags = []
            flags.append("STEP" if node.get("has_step") else "no STEP")
            flags.append("STL" if node.get("has_stl") else "no STL")
            ui.label(" / ".join(flags)).classes("text-xs text-gray-600 text-center")
        if node.get("id") in {"products", "result"} and on_select_page is not None:
            with ui.row().classes("gap-2"):
                ui.button("Parts", icon="view_list", on_click=lambda: on_select_page("parts")).props("outline dense").tooltip("打开当前 Work 的 Part 预览与下载。")
                ui.button("Runs", icon="history", on_click=lambda: on_select_page("runs")).props("outline dense").tooltip("打开当前 Work 的 run history。")


def _render_node_detail(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    *,
    on_back_to_workflow: Callable[[], None],
) -> None:
    node = data.get("selected_node") if isinstance(data.get("selected_node"), dict) else None
    if node is None:
        ui.label("Select a workflow node.").classes("text-gray-600")
        _render_workflow_nodes(ui, data)
        return
    summary = _dict_get(data.get("selected_work"), "summary") or {}
    with ui.row().classes("w-full items-center justify-between"):
        ui.label(f"{summary.get('title') or 'Work'} > Workflow > {node.get('label') or node.get('id')}").classes("text-sm text-gray-500")
        ui.button("Back to Workflow", icon="arrow_back", on_click=on_back_to_workflow).props("outline dense").tooltip("返回当前 Work 的 Workflow 流程图。")
    with ui.card().classes("w-full shadow-none border border-gray-200"):
        with ui.row().classes("w-full items-center justify-between"):
            _label_with_help(ui, node.get("label") or node.get("id"), "核心状态已放在 Workflow dot hover 中；这里保留本节点可执行的 review/rework 操作。", "text-xl font-semibold")
            ui.badge(node.get("status") or "unknown").classes(_badge_class(node.get("status")))
        ui.label(node.get("summary") or "Hover the workflow dot for inputs, outputs, start flag, review status, and next action.").classes("text-sm text-gray-700")
        artifacts = node.get("artifacts") or []
        actions_list = node.get("actions") or []
        with ui.row().classes("gap-2"):
            ui.badge(f"Review: {_node_review_status(data.get('selected_work') or {}, node)}")
            ui.badge(f"Outputs: {len(artifacts)}")
            ui.badge(f"Start: {_node_start_flag(node)}")
        if actions_list:
            ui.label("Available actions: " + ", ".join(actions_list)).classes("text-xs text-gray-500")
    if "run_rework" in actions_list:
        ui.label("Rework is available from this node context when a needs_revision stage review is saved.").classes("text-sm text-gray-600")


def _render_work_products(ui: Any, data: dict[str, Any]) -> None:
    products = _dict_get(data.get("selected_work"), "products") or {}
    human = products.get("human_facing") if isinstance(products.get("human_facing"), list) else []
    downloads = products.get("downloadables") if isinstance(products.get("downloadables"), list) else []
    reviewable = products.get("reviewable_outputs") if isinstance(products.get("reviewable_outputs"), list) else []
    artifact_state = products.get("artifact_state") if isinstance(products.get("artifact_state"), dict) else {}
    language = str(data.get("language") or "en")
    with ui.card().classes("w-full"):
        _label_with_help(
            ui,
            "已批准交付物" if language == "zh" else "Accepted Deliverables",
            "这里只展示用户明确批准的结果。未批准结果仍可在 Parts 或 Run Snapshot 中评审。" if language == "zh" else "Only explicitly approved results appear here. Reviewable attempts remain available from Parts or Run Snapshot.",
            "text-xl font-semibold",
        )
        if downloads:
            for item in downloads:
                ui.badge(f"{item.get('name')}: {'已批准' if language == 'zh' else 'accepted'}")
        else:
            ui.label("尚无已批准的可下载交付物。" if language == "zh" else "No accepted downloadable deliverables yet.").classes("text-sm text-gray-500")
        ui.label("可评审输出" if language == "zh" else "Reviewable Outputs").classes("font-medium")
        if reviewable:
            for item in reviewable:
                ui.badge(f"{item.get('name')}: {'等待批准' if language == 'zh' else 'awaiting approval'}")
        else:
            ui.label("当前没有等待批准的输出。" if language == "zh" else "No outputs are awaiting approval.").classes("text-sm text-gray-500")
        if int(artifact_state.get("failed_attempt_output_count") or 0) or int(artifact_state.get("untrusted_output_count") or 0):
            ui.label(
                "失败或状态未经确认的尝试只保留诊断记录，不作为产品下载。" if language == "zh"
                else "Failed or unverified attempts retain diagnostic records only; they are not product downloads."
            ).classes("text-sm text-amber-800")
        ui.label("已批准结果证据" if language == "zh" else "Accepted Result Evidence").classes("font-medium")
        if not human:
            ui.label("暂无。" if language == "zh" else "None.").classes("text-sm text-gray-500")
        for artifact in human:
            ui.badge(artifact.get("name") or "artifact")


def _node_report_title(node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "")
    if node_id == "requirement":
        return "Requirement Review"
    if node_id == "planning":
        return "Planning Review"
    if node_id == "assembly_plan":
        return "Split / Assembly Plan Review"
    if node_id.startswith("part:") or node.get("kind") == "part":
        return "Part Result Review"
    return "Step Review"


def _node_review_status(work: dict[str, Any], node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "")
    if node_id.startswith("part:"):
        part = _part_by_id(work, node_id.split(":", 1)[1])
        return str(part.get("review_status") or part.get("status") or node.get("review_status") or "Empty")
    if node.get("review_status"):
        return str(node.get("review_status"))
    if node_id == "requirement":
        summary = work.get("summary") if isinstance(work.get("summary"), dict) else {}
        return str(summary.get("requirement_status") or node.get("status") or "Empty")
    if node_id in {"planning", "assembly_plan"}:
        artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), list) else []
        if "stage_review.json" in artifacts:
            return "stage review available"
        return str(node.get("status") or "Empty")
    return str(node.get("status") or "Empty")


def _render_node_report(ui: Any, data: dict[str, Any], node: dict[str, Any]) -> None:
    work = data.get("selected_work") if isinstance(data.get("selected_work"), dict) else {}
    node_id = str(node.get("id") or "")
    with ui.card().classes("w-full shadow-none border border-gray-200"):
        _label_with_help(ui, _node_report_title(node), "当前节点对应的 review/report 摘要。Review 不再作为独立页面，而是挂在相关节点下。", "text-lg font-medium")
        if node_id.startswith("part:"):
            part_id = node_id.split(":", 1)[1]
            part = _part_by_id(work, part_id)
            _key_values(ui, {
                "Part": part_id,
                "Status": part.get("status") or node.get("status") or "unknown",
                "Review": part.get("review_status") or "Empty",
                "Next action": part.get("next_action") or "Empty",
            })
            return
        summary = work.get("summary") if isinstance(work.get("summary"), dict) else {}
        current = work.get("current_state") if isinstance(work.get("current_state"), dict) else {}
        if node_id == "requirement":
            _key_values(ui, {
                "Requirement": summary.get("requirement_status") or node.get("status") or "Empty",
                "Review": _node_review_status(work, node),
                "Output": ", ".join(node.get("artifacts") or []) or "Empty",
                "Next action": current.get("next_action") or "Empty",
            })
            return
        if node_id in {"planning", "assembly_plan"}:
            _key_values(ui, {
                "Planning": node.get("status") or "Empty",
                "Review": _node_review_status(work, node),
                "Parts": summary.get("part_count") if summary.get("part_count") is not None else len(work.get("parts") or []),
                "Output": ", ".join(node.get("artifacts") or []) or "Empty",
                "Next action": current.get("next_action") or "Empty",
            })
            return
        _key_values(ui, {
            "Status": node.get("status") or "unknown",
            "Review": _node_review_status(work, node),
            "Artifacts": ", ".join(node.get("artifacts") or []) or "Empty",
            "Next action": current.get("next_action") or "Empty",
        })


def _render_config(
    ui: Any,
    data: dict[str, Any],
    backend: WorkflowConsoleBackend,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    workspace_config = data.get("workspace_config") if isinstance(data.get("workspace_config"), dict) else {}
    readiness = data.get("product_readiness") if isinstance(data.get("product_readiness"), dict) else {}
    provider_readiness = readiness.get("provider") if isinstance(readiness.get("provider"), dict) else {}
    local_readiness = readiness.get("local_execution") if isinstance(readiness.get("local_execution"), dict) else {}
    language = str(data.get("language") or "en")
    draft = state.get("provider_draft") if isinstance(state.get("provider_draft"), dict) else None
    if draft is None:
        saved_provider = _provider_select_value(workspace_config)
        draft = {
            "provider": "deepseek" if saved_provider == "local" else saved_provider,
            "model": str(workspace_config.get("model") or "deepseek-v4-flash"),
            "api_key": "",
            "base_url": str(workspace_config.get("base_url") or ""),
            "timeout_seconds": workspace_config.get("timeout_seconds") or 60,
            "max_retries": workspace_config.get("max_retries") if workspace_config.get("max_retries") is not None else 1,
            "advancement_mode": workspace_config.get("advancement_mode") or "manual_confirm",
        }
        state["provider_draft"] = draft
        state.setdefault(
            "provider_draft_status",
            "connected" if provider_readiness.get("ready") is True else "not_tested",
        )
    draft_credential = backend.read_provider_credential_source(str(draft.get("provider") or "deepseek"))

    with ui.row().classes("w-full items-start justify-between gap-3"):
        with ui.column().classes("gap-1"):
            ui.label("设置" if language == "zh" else "Settings").classes("text-3xl font-semibold")
            ui.label("连接 Agent 使用的 AI Provider，并检查本机 CAD 执行环境。" if language == "zh" else "Connect the AI provider used by the Agent and check local CAD execution.").classes("text-gray-600")
        if state.get("settings_origin_work_id"):
            ui.button("返回设计" if language == "zh" else "Return to Design", icon="arrow_back", on_click=lambda: _return_to_design(state, refresh)).props("outline")

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("AI Provider").classes("text-xl font-semibold")
            status = str(state.get("provider_draft_status") or "not_tested")
            status_label_text = {
                "not_tested": "未测试" if language == "zh" else "Not tested",
                "testing": "测试中" if language == "zh" else "Testing…",
                "connected": "已连接" if language == "zh" else "Connected",
                "failed": "连接失败" if language == "zh" else "Connection failed",
                "changed_since_test": "测试后已修改" if language == "zh" else "Changed since test",
            }.get(status, status)
            ui.badge(status_label_text).classes("bg-green-700" if status == "connected" else "bg-amber-700" if status in {"not_tested", "changed_since_test", "testing"} else "bg-red-700")

        def changed(field: str, value: Any) -> None:
            if _mark_provider_draft_changed(state, field, value):
                refresh()

        provider = ui.select(options={"deepseek": "DeepSeek", "openai": "OpenAI"}, value=draft["provider"], label="Provider").classes("w-full")
        model = ui.input("Model", value=draft["model"]).classes("w-full")
        api_key = ui.input("API Key", value=draft.get("api_key") or "", password=True, password_toggle_button=True).props("autocomplete=new-password").classes("w-full")
        credential_source = str(draft_credential.get("source") or "unavailable")
        credential_variable = draft_credential.get("variable")
        source_labels = {
            "session": "当前会话" if language == "zh" else "current session",
            "process_environment": "进程环境变量" if language == "zh" else "process environment",
            "project_env": "项目根目录 .env" if language == "zh" else "project-root .env",
            "unavailable": "未检测到" if language == "zh" else "not detected",
        }
        ui.label(
            (f"凭据来源：{source_labels.get(credential_source, credential_source)}" if language == "zh" else f"Credential source: {source_labels.get(credential_source, credential_source)}")
            + (f" · {credential_variable}" if credential_variable else "")
        ).classes("text-sm text-green-700" if draft_credential.get("available") else "text-sm text-amber-700")
        ui.label(
            "优先级：当前会话 → 进程环境变量 → 项目根目录 .env。值从不显示，也不会写入 workspace、日志或页面数据。" if language == "zh"
            else "Precedence: current session → process environment → project-root .env. The value is never displayed or written to workspace, logs, or page data."
        ).classes("text-xs text-gray-500")
        provider.on_value_change(lambda event: changed("provider", event.value))
        model.on_value_change(lambda event: changed("model", event.value or ""))
        api_key.on_value_change(lambda event: changed("api_key", event.value or ""))

        with ui.expansion("高级连接设置" if language == "zh" else "Advanced connection", icon="tune").classes("w-full"):
            base_url = ui.input("Base URL", value=draft["base_url"], placeholder="https://api.deepseek.com").classes("w-full")
            timeout = ui.number("Timeout seconds", value=draft["timeout_seconds"], min=1, max=300).classes("w-full")
            retries = ui.number("Max retries", value=draft["max_retries"], min=0, max=5).classes("w-full")
            mode = ui.select(options=["manual_confirm", "auto_advance"], value=draft["advancement_mode"], label="Advancement mode").classes("w-full")
            base_url.on_value_change(lambda event: changed("base_url", event.value or ""))
            timeout.on_value_change(lambda event: changed("timeout_seconds", event.value))
            retries.on_value_change(lambda event: changed("max_retries", event.value))
            mode.on_value_change(lambda event: changed("advancement_mode", event.value))
        with ui.row().classes("gap-2"):
            test_button = ui.button("测试当前草稿" if language == "zh" else "Test current draft", icon="network_check", on_click=lambda: _schedule_action(_test_provider_draft_async(backend, state, refresh, language))).props("outline")
            save_button = ui.button("保存并验证" if language == "zh" else "Save & Verify", icon="save", on_click=lambda: _schedule_action(_save_verify_provider_draft_async(backend, state, refresh, language))).props("color=primary")
            if status == "testing":
                test_button.disable()
                save_button.disable()
        result = state.get("provider_draft_result") if isinstance(state.get("provider_draft_result"), dict) else {}
        if status == "connected":
            ui.label("连接已通过真实请求验证；安全配置已保存。" if language == "zh" else "The connection passed a real request and safe settings are saved.").classes("text-sm text-green-700")
        elif status == "failed":
            ui.label(str(result.get("message") or ("请检查密钥、模型和网络后重试。" if language == "zh" else "Check the key, model, and network, then try again."))).classes("text-sm text-red-700")

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("本地 CAD 执行" if language == "zh" else "Local CAD execution").classes("text-xl font-semibold")
            ui.badge("Ready" if local_readiness.get("ready") else "Unavailable").classes("bg-green-700" if local_readiness.get("ready") else "bg-red-700")
        ui.label(f"CadQuery · isolated execution: {local_readiness.get('isolated_execution') or 'unknown'}").classes("text-sm")
        codes = local_readiness.get("reason_codes") if isinstance(local_readiness.get("reason_codes"), list) else []
        if codes:
            ui.label(", ".join(str(item) for item in codes)).classes("text-xs text-gray-500")


def _create_work_ui(
    title: str | None,
    description: str | None,
    state: dict[str, Any],
    result_key: str,
    refresh: Callable[[], None],
) -> None:
    backend = state.get("_backend")
    if backend is None:
        state[result_key] = {"ok": False, "error": "Backend is unavailable."}
        refresh()
        return
    response = dispatch_route(
        backend,
        "create_work",
        body={"title": title or "", "description": description or ""},
    )
    state[result_key] = response["data"] if response["ok"] else response["error"]
    if response["ok"]:
        state["selected_work_id"] = response["data"]["work"]["work_id"]
        state["active_page"] = "overview"
    refresh()


def _go_to_settings(state: dict[str, Any], refresh: Callable[[], None]) -> None:
    state["settings_origin_work_id"] = state.get("selected_work_id")
    state["active_page"] = "config"
    refresh()


def _new_design_dialog_button(ui: Any, state: dict[str, Any], refresh: Callable[[], None], language: str) -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[680px] max-w-full"):
        ui.label("新建设计" if language == "zh" else "New Design").classes("text-2xl font-semibold")
        ui.label(
            "从你的真实要求创建一个 Work。Agent 会在你继续后先设计整个 Work，再决定是否以及如何创建 Part Jobs。" if language == "zh"
            else "Create a Work from your actual request. When you continue, the Agent designs the whole Work before deciding whether and how to create Part Jobs."
        ).classes("text-sm text-gray-600")
        request = ui.textarea(
            "设计要求" if language == "zh" else "Design request",
            value=state.get("new_design_request") or "",
            placeholder="例如：设计一个可安装到 2020 铝型材的紧凑相机支架……" if language == "zh" else "For example: Design a compact camera bracket for 2020 extrusion…",
        ).props("outlined autogrow").classes("w-full")
        title = ui.input("标题（可选）" if language == "zh" else "Title (optional)", value=state.get("new_design_title") or "").classes("w-full")
        request.on_value_change(lambda event: state.__setitem__("new_design_request", event.value or ""))
        title.on_value_change(lambda event: state.__setitem__("new_design_title", event.value or ""))
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("取消" if language == "zh" else "Cancel", on_click=dialog.close).props("outline")
            ui.button(
                "创建设计" if language == "zh" else "Create Design",
                icon="arrow_forward",
                on_click=lambda: _create_product_design_ui(request.value, title.value, state, refresh, dialog, language),
            ).props("color=primary")
    ui.button("新建设计" if language == "zh" else "New Design", icon="add", on_click=dialog.open).props("color=primary")


def _create_product_design_ui(
    request: str | None,
    title: str | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
    dialog: Any,
    language: str,
) -> None:
    backend = state.get("_backend")
    action = {"key": "start_design", "label": "New Design"}
    if backend is None or not isinstance(request, str) or not request.strip():
        failed = ActionExecutionState.from_action(action, status="failed", message=_runtime_message(action, language, "failed"))
        failed.error_detail = "请先描述设计要求。" if language == "zh" else "Describe the design request first."
        _set_action_execution(state, failed, action)
        refresh()
        return
    response = dispatch_route(backend, "create_product_design", body={"request": request.strip(), "title": (title or "").strip() or None})
    if not response.get("ok"):
        failed = ActionExecutionState.from_action(action, status="failed", message=_runtime_message(action, language, "failed"))
        failed.error_detail = str(response.get("error") or "Unable to create design.")
        _set_action_execution(state, failed, action)
        refresh()
        return
    result = response["data"]
    state["selected_work_id"] = result["work_id"]
    state["selected_run_id"] = None
    state["view_mode"] = "current_work"
    state["active_page"] = "overview"
    state["new_design_request"] = ""
    state["new_design_title"] = ""
    dialog.close()
    _set_action_execution(state, ActionExecutionState.from_action(action, status="succeeded", message=_runtime_message(action, language, "success")), action)
    refresh()


async def _start_live_product_example_async(
    backend: WorkflowConsoleBackend | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> dict[str, Any] | None:
    action = {"key": "start_design", "label": "Start Product Example", "target_work_id": "new"}
    if backend is None:
        return None

    def execute() -> dict[str, Any]:
        return backend.start_live_product_example()

    def verify(result: dict[str, Any]) -> tuple[bool, str | None]:
        manifest = backend._read_work_manifest(str(result.get("work_id")))
        ok = not manifest.get("artifact_references") and not manifest.get("accepted_part_results")
        return ok, None if ok else "Live example did not begin from an empty evidence state."

    result = await _execute_action_lifecycle(action, state, refresh, execute, language=language, verify=verify)
    if result is not None:
        state["selected_work_id"] = result["work_id"]
        state["selected_run_id"] = None
        state["view_mode"] = "current_work"
        state["active_page"] = "overview"
        refresh()
    return result


async def _open_product_example_async(
    backend: WorkflowConsoleBackend | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> dict[str, Any] | None:
    action = {
        "key": "open_product_example",
        "label": "Open Product Example",
        "target_work_id": "product_golden",
    }
    if backend is None:
        failed = ActionExecutionState.from_action(
            action,
            status="failed",
            message=_runtime_message(action, language, "failed"),
        )
        failed.error_detail = "Backend is unavailable."
        _set_action_execution(state, failed, action)
        refresh()
        return None

    def execute() -> dict[str, Any]:
        return backend.open_product_golden_example()

    def verify(result: dict[str, Any]) -> tuple[bool, str | None]:
        work_id = result.get("work_id")
        if not isinstance(work_id, str):
            return False, "Product Example did not return a Work."
        manifest = backend._read_work_manifest(work_id)
        metadata = _dict_get(manifest, "metadata") or {}
        has_reviewable = any(
            isinstance(item, dict)
            and item.get("checkpoint") == "reviewable_result"
            and item.get("trust_role") == "reviewable_result"
            for item in manifest.get("artifact_references", [])
        )
        ok = metadata.get("example_classification") == "product_golden" and has_reviewable
        return ok, None if ok else "Product Example is missing its reviewable product evidence."

    result = await _execute_action_lifecycle(
        action,
        state,
        refresh,
        execute,
        language=language,
        verify=verify,
    )
    if result is not None:
        state["selected_work_id"] = result["work_id"]
        state["selected_run_id"] = None
        state["view_mode"] = "current_work"
        state["selected_node_id"] = None
        state["selected_stage_id"] = None
        state["active_page"] = "overview"
        refresh()
    return result


def _create_golden_example_ui(mode: str, state: dict[str, Any], refresh: Callable[[], None]) -> None:
    backend = state.get("_backend")
    if backend is None:
        state["golden_example_result"] = {"ok": False, "error": "Backend is unavailable."}
        refresh()
        return
    state["golden_example_progress"] = [{"stage": "workspace", "status": "running", "message": "Starting executable golden example"}]
    refresh()

    def on_progress(event: dict[str, Any]) -> None:
        state.setdefault("golden_example_progress", []).append(event)

    try:
        result = backend.create_golden_example(mode, progress_callback=on_progress)
    except Exception as exc:
        state["golden_example_result"] = {"ok": False, "error": type(exc).__name__}
        state["golden_example_progress"].append({"stage": "example", "status": "failed", "message": str(exc)})
    else:
        state["golden_example_result"] = result
        state["golden_example_progress"] = result.get("progress") or []
        state["selected_work_id"] = result.get("work_id")
        state["selected_run_id"] = None
        state["view_mode"] = "current_work"
        state["selected_stage_id"] = None
        state["active_page"] = "workflow"
    refresh()


def _render_golden_comparison(ui: Any, golden: dict[str, Any]) -> None:
    execution = golden.get("execution") if isinstance(golden.get("execution"), dict) else {}
    comparison = golden.get("comparison") if isinstance(golden.get("comparison"), dict) else {}
    with ui.card().classes("w-full shadow-none border border-amber-200 bg-amber-50"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Golden comparison").classes("text-lg font-medium")
            ui.badge("Passed" if comparison.get("passed") else "Failed").classes("bg-green-100 text-green-800" if comparison.get("passed") else "bg-red-100 text-red-800")
        _key_values(ui, {
            "Mode": golden.get("mode"),
            "Execution": execution.get("status"),
            "CAD IR validated": execution.get("cad_ir_validated"),
            "CAD execution skipped": execution.get("execution_skipped"),
            "Matched stages": f"{comparison.get('matched_stage_count', 0)} / {comparison.get('stage_count', 0)}",
            "Mismatches": comparison.get("mismatch_count", 0),
            "Missing artifacts": comparison.get("missing_artifact_count", 0),
            "Unexpected claims": comparison.get("unexpected_claim_count", 0),
        })
        failed = [item for item in comparison.get("stages", []) if isinstance(item, dict) and not item.get("passed")]
        if failed:
            with ui.expansion("Stage mismatches").classes("w-full"):
                for item in failed:
                    ui.label(f"{item.get('stage')}: {len(item.get('mismatches', []))} mismatch(es), {len(item.get('missing_artifacts', []))} missing").classes("text-sm")


def _create_workspace_ui(
    workspace_path: str | None,
    name: str | None,
    include_examples: bool,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    backend = state.get("_backend")
    body = {"path": workspace_path or "workspace", "name": name or "workspace", "include_examples": include_examples}
    response = dispatch_route(backend, "create_workspace", body=body) if backend is not None else {"ok": False, "error": "Backend is unavailable."}
    state["workspace_result"] = response["data"] if response.get("ok") else response.get("error")
    state["selected_work_id"] = None
    state["selected_run_id"] = None
    refresh()


def _load_workspace_ui(
    workspace_path: str | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    backend = state.get("_backend")
    body = {"path": workspace_path or "workspace"}
    response = dispatch_route(backend, "load_workspace", body=body) if backend is not None else {"ok": False, "error": "Backend is unavailable."}
    state["workspace_result"] = response["data"] if response.get("ok") else response.get("error")
    state["selected_work_id"] = None
    state["selected_run_id"] = None
    refresh()


def _create_work_requirement_run_ui(
    work_id: str | None,
    prompt: str | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    backend = state.get("_backend")
    if backend is None or not work_id:
        state["requirement_run_result"] = {"ok": False, "error": "Select a Work first."}
        refresh()
        return
    response = dispatch_route(
        backend,
        "create_work_requirement_run",
        path_params={"work_id": work_id},
        body={"prompt": prompt or ""},
    )
    state["requirement_run_result"] = response["data"] if response["ok"] else response["error"]
    if response["ok"]:
        state["selected_run_id"] = response["data"]["run"]["run_id"]
    refresh()


def _create_work_part_runs_ui(
    work_id: str | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    backend = state.get("_backend")
    if backend is None or not work_id:
        state["part_runs_result"] = {"ok": False, "error": "Select a Work first."}
        refresh()
        return
    response = dispatch_route(backend, "create_work_part_runs", path_params={"work_id": work_id})
    state["part_runs_result"] = response["data"] if response["ok"] else response["error"]
    refresh()


def _save_workspace_config_ui(
    backend: WorkflowConsoleBackend,
    provider: str,
    advancement_mode: str,
    model: str | None,
    timeout_seconds: Any,
    max_retries: Any,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    body: dict[str, Any] = {"provider": provider, "advancement_mode": advancement_mode}
    if model:
        body["model"] = str(model).strip()
    if timeout_seconds not in (None, ""):
        body["timeout_seconds"] = int(timeout_seconds)
    if max_retries not in (None, ""):
        body["max_retries"] = int(max_retries)
    state["config_result"] = dispatch_route(backend, "write_workspace_config", body=body)
    refresh()


def _configure_provider_ui(
    backend: WorkflowConsoleBackend,
    provider: str,
    model: str | None,
    timeout_seconds: Any,
    max_retries: Any,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    body: dict[str, Any] = {"provider": provider}
    if model:
        body["model"] = str(model).strip()
    if timeout_seconds not in (None, ""):
        body["timeout_seconds"] = int(timeout_seconds)
    if max_retries not in (None, ""):
        body["max_retries"] = int(max_retries)
    state["provider_result"] = dispatch_route(backend, "configure_provider", body=body)
    refresh()


def _test_provider_ui(backend: WorkflowConsoleBackend, state: dict[str, Any], refresh: Callable[[], None]) -> None:
    state["config_result"] = dispatch_route(backend, "test_provider_connection")
    refresh()


def _provider_draft_body(state: dict[str, Any]) -> dict[str, Any]:
    draft = state.get("provider_draft") if isinstance(state.get("provider_draft"), dict) else {}
    body: dict[str, Any] = {
        "provider": draft.get("provider") or "deepseek",
        "model": str(draft.get("model") or "deepseek-v4-flash").strip(),
    }
    for key in ("base_url", "api_key"):
        value = draft.get(key)
        if isinstance(value, str) and value.strip():
            body[key] = value.strip()
    for key in ("timeout_seconds", "max_retries"):
        value = draft.get(key)
        if value not in (None, ""):
            body[key] = int(value)
    return body


def _mark_provider_draft_changed(state: dict[str, Any], field: str, value: Any) -> bool:
    draft = state.setdefault("provider_draft", {})
    draft[field] = value
    if state.get("provider_draft_status") == "connected":
        state["provider_draft_status"] = "changed_since_test"
        return True
    return False


async def _test_provider_draft_async(
    backend: WorkflowConsoleBackend,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> None:
    state["provider_draft_status"] = "testing"
    state["provider_draft_result"] = {}
    refresh()
    response = await asyncio.to_thread(dispatch_route, backend, "test_provider_connection", body=_provider_draft_body(state))
    result = response.get("data") if response.get("ok") and isinstance(response.get("data"), dict) else {}
    connected = result.get("status") == "ok"
    state["provider_draft_status"] = "connected" if connected else "failed"
    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    state["provider_draft_result"] = {
        "status": "connected" if connected else "failed",
        "message": (
            ("连接测试通过。保存并验证后会用于此工作区。" if language == "zh" else "Connection test passed. Save & Verify to use it for this workspace.")
            if connected
            else _provider_error_message(str(error.get("category") or response.get("error") or "connection_failed"), language)
        ),
    }
    refresh()


async def _save_verify_provider_draft_async(
    backend: WorkflowConsoleBackend,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> None:
    state["provider_draft_status"] = "testing"
    state["provider_draft_result"] = {}
    refresh()
    response = await asyncio.to_thread(dispatch_route, backend, "save_and_verify_provider", body=_provider_draft_body(state))
    result = response.get("data") if response.get("ok") and isinstance(response.get("data"), dict) else {}
    connected = result.get("status") == "ok" and result.get("saved") is True
    if connected:
        draft = state.get("provider_draft") if isinstance(state.get("provider_draft"), dict) else {}
        backend.write_workspace_config({"advancement_mode": draft.get("advancement_mode") or "manual_confirm"}, merge=True)
        draft["api_key"] = ""
    state["provider_draft_status"] = "connected" if connected else "failed"
    verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
    error = verification.get("error") if isinstance(verification.get("error"), dict) else {}
    state["provider_draft_result"] = {
        "status": "connected" if connected else "failed",
        "message": (
            ("连接已验证并保存。" if language == "zh" else "Connection verified and saved.")
            if connected
            else _provider_error_message(str(error.get("category") or response.get("error") or "connection_failed"), language)
        ),
    }
    refresh()


def _provider_error_message(category: str, language: str) -> str:
    if "auth" in category.lower():
        return "身份验证失败，请检查 API Key。" if language == "zh" else "Authentication failed. Check the API key."
    if "timeout" in category.lower():
        return "连接超时，请检查网络或增加超时时间。" if language == "zh" else "The connection timed out. Check the network or increase the timeout."
    return "连接失败，请检查 Provider、模型、Base URL 和网络。" if language == "zh" else "Connection failed. Check the provider, model, Base URL, and network."


def _return_to_design(state: dict[str, Any], refresh: Callable[[], None]) -> None:
    work_id = state.pop("settings_origin_work_id", None)
    if isinstance(work_id, str):
        state["selected_work_id"] = work_id
    state["active_page"] = "overview"
    refresh()


def _provider_select_value(identity: dict[str, Any]) -> str:
    provider = str(identity.get("provider") or "local/mock").lower()
    if provider in {"deepseek", "openai"}:
        return provider
    return "local"


def _graph_node(
    node: dict[str, Any] | None,
    *,
    fallback_id: str,
    fallback_label: str,
) -> dict[str, Any]:
    node = node or {}
    return {
        "id": node.get("id") or fallback_id,
        "label": node.get("label") or fallback_label,
        "kind": node.get("kind") or "stage",
        "status": node.get("status") or "not_started",
        "summary": node.get("summary") or "",
        "artifacts": node.get("artifacts") if isinstance(node.get("artifacts"), list) else [],
        "actions": node.get("actions") if isinstance(node.get("actions"), list) else [],
    }


def _graph_part_node(part: dict[str, Any], node: dict[str, Any] | None) -> dict[str, Any]:
    graph = _graph_node(
        node,
        fallback_id=f"part:{part.get('part_id') or 'part'}",
        fallback_label=str(part.get("part_id") or "part"),
    )
    graph.update({
        "part_id": part.get("part_id"),
        "role": part.get("role"),
        "current_stage": part.get("current_stage"),
        "has_step": bool(part.get("has_step")),
        "has_stl": bool(part.get("has_stl")),
        "has_preview": bool(part.get("has_preview")),
        "download_run_id": part.get("download_run_id") or part.get("latest_run_id"),
        "next_action": part.get("next_action"),
        "review_status": part.get("review_status"),
    })
    return graph


def _graph_result_node(work: dict[str, Any]) -> dict[str, Any]:
    products = work.get("products") if isinstance(work.get("products"), dict) else {}
    downloads = products.get("downloadables") if isinstance(products.get("downloadables"), list) else []
    human = products.get("human_facing") if isinstance(products.get("human_facing"), list) else []
    reviewable = products.get("reviewable_outputs") if isinstance(products.get("reviewable_outputs"), list) else []
    supporting = products.get("supporting_artifacts") if isinstance(products.get("supporting_artifacts"), list) else []
    available = len(downloads) + len(human) + len(reviewable) + len(supporting)
    status = "accepted" if downloads else "needs_review" if reviewable else "available" if supporting else "not_started"
    return {
        "id": "result",
        "label": "Result / Downloads",
        "kind": "summary",
        "status": status,
        "summary": (
            f"{len(downloads)} accepted deliverables."
            if downloads
            else f"{len(reviewable)} outputs are ready for review."
            if reviewable
            else f"{available} supporting records."
            if available
            else "Products and run history will appear here."
        ),
        "artifacts": [item.get("name") for item in [*human, *supporting] if isinstance(item, dict) and item.get("name")],
        "actions": ["open_products", "open_runs"],
    }


def _graph_single_part_node(work: dict[str, Any]) -> dict[str, Any] | None:
    summary = work.get("summary") if isinstance(work.get("summary"), dict) else {}
    products = work.get("products") if isinstance(work.get("products"), dict) else {}
    accepted = products.get("downloadables") if isinstance(products.get("downloadables"), list) else []
    reviewable = products.get("reviewable_outputs") if isinstance(products.get("reviewable_outputs"), list) else []
    downloads = accepted or reviewable
    if not downloads:
        return None
    names = {item.get("name") for item in downloads if isinstance(item, dict)}
    accepted_result = bool(accepted)
    artifacts = [name for name in ("model.step", "model.stl", "preview.png") if name in names]
    return {
        "id": "single_part",
        "label": "Single Part",
        "kind": "part",
        "status": "accepted" if accepted_result else "needs_review",
        "summary": "Accepted single-part deliverable." if accepted_result else "Single-part output is ready for review.",
        "artifacts": artifacts,
        "actions": [],
        "part_id": "single_part",
        "role": "single_part",
        "current_stage": "outputs",
        "has_step": "model.step" in names,
        "has_stl": "model.stl" in names,
        "has_preview": "preview.png" in names,
        "download_run_id": next((item.get("source_run_id") for item in downloads if isinstance(item, dict) and item.get("source_run_id")), None) or summary.get("latest_run_id") or summary.get("root_run_id"),
        "next_action": "View products" if accepted_result else "Review result",
        "review_status": "approved" if accepted_result else "not_reviewed",
        "synthetic": True,
    }


def _graph_tooltip(node: dict[str, Any]) -> str:
    parts = [
        f"步骤：{node.get('label') or node.get('id')}",
        f"状态：{node.get('status') or 'unknown'}",
    ]
    if node.get("role"):
        parts.append(f"角色：{node.get('role')}")
    inputs = _node_input_artifacts(node)
    if inputs:
        parts.append(f"输入：{', '.join(inputs[:5])}")
    artifacts = node.get("artifacts") if isinstance(node.get("artifacts"), list) else []
    if artifacts:
        parts.append(f"输出：{', '.join(str(item) for item in artifacts[:5])}")
    parts.append(f"启动标志：{_node_start_flag(node)}")
    if node.get("review_status"):
        parts.append(f"Review：{node.get('review_status')}")
    if node.get("next_action"):
        parts.append(f"下一步：{node.get('next_action')}")
    if node.get("summary"):
        parts.append(str(node.get("summary")))
    return "\n".join(parts)


def _dot_status(status: Any) -> str:
    value = str(status or "unknown")
    if value in {"accepted_for_preview", "success"}:
        return "accepted"
    if value in {"completed", "contract_complete", "execution_skipped", "skipped", "unavailable", "user_modified", "stale", "accepted", "reviewable", "available", "ready", "running", "needs_review", "partial_success", "blocked", "reference_only", "not_started", "incomplete", "candidate", "selected", "generated", "failed"}:
        return value
    if "blocked" in value:
        return "blocked"
    return "unknown"


def _selected_node(work: dict[str, Any], node_id: str | None) -> dict[str, Any] | None:
    if not node_id:
        return None
    for node in work.get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == node_id:
            return node
    return None


def _node_input_artifacts(node: dict[str, Any]) -> list[str]:
    node_id = node.get("id")
    if node_id == "planning":
        return ["requirement.json"]
    if node_id == "assembly_plan":
        return ["requirement.json", "design_brief.json"]
    if isinstance(node_id, str) and node_id.startswith("part:"):
        return ["assembly_plan.json", "reviewed_part_handoff.json"]
    if node_id in {"workflow_review", "stage_review", "rework_decision"}:
        return ["run summaries", "review artifacts"]
    return ["prompt.txt"] if node_id == "requirement" else []


def _node_start_flag(node: dict[str, Any]) -> str:
    status = node.get("status")
    if status in {"completed", "accepted"}:
        return "completed"
    if status == "blocked":
        return "blocked"
    if node.get("artifacts"):
        return "ready"
    return "waiting_for_inputs"


def _node_stage_for_review(node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "")
    if node_id == "assembly_plan":
        return "assembly_plan"
    if node_id == "planning":
        return "requirement"
    if node_id.startswith("part:"):
        return "single_part_result"
    if node_id in STAGE_REVIEW_STAGES:
        return node_id
    return "workflow_review"


def _render_parts_matrix(ui: Any, data: dict[str, Any]) -> None:
    work = data.get("selected_work") or {}
    overview = data.get("workbench_overview") if isinstance(data.get("workbench_overview"), dict) else {}
    language = str(data.get("language") or "en")
    if overview:
        _render_workbench_parts_summary(ui, overview, None, language)
        legacy_parts = work.get("parts") if isinstance(work.get("parts"), list) else []
        if legacy_parts:
            with ui.expansion(
                "Model and compatibility details" if language != "zh" else "模型与兼容详情",
                icon="view_in_ar",
            ).classes("w-full"):
                with ui.element("div").classes("workbench-part-grid w-full"):
                    for part in legacy_parts:
                        if isinstance(part, dict):
                            _render_part_card(ui, part)
        return
    graph = work.get("workflow_graph") if isinstance(work.get("workflow_graph"), dict) else {}
    parts = work.get("parts") or []
    display_parts = parts or graph.get("part_nodes") or []
    _label_with_help(ui, "Parts", "当前 Work 的 part 状态、预览、报告和下载。", "text-xl font-semibold")
    _render_planning_artifact_downloads(ui, work)
    if not display_parts:
        ui.label("No part jobs inferred for this Work.").classes("text-gray-600")
        return
    with ui.grid(columns=2).classes("w-full gap-4"):
        for part in display_parts:
            _render_part_card(ui, part)
    _label_with_help(ui, "Parts Matrix", "紧凑扫描视图，方便比较 base/lid/screws 等状态。", "text-lg font-medium")
    if not parts:
        ui.label("No split parts yet; showing single-part preview above.").classes("text-sm text-gray-500")
        return
    columns = [
        {"name": key, "label": label, "field": key, "align": "left"}
        for key, label in (
            ("part_id", "part_id"),
            ("role", "role"),
            ("status", "status"),
            ("current_stage", "current_stage"),
            ("attempt_count", "attempts"),
            ("step_stl", "STEP/STL"),
            ("review_status", "review"),
            ("next_action", "next_action"),
        )
    ]
    rows = [{**part, "step_stl": f"{'yes' if part.get('has_step') else 'no'} / {'yes' if part.get('has_stl') else 'no'}"} for part in parts]
    ui.table(columns=columns, rows=rows, row_key="part_id").classes("w-full")


def _render_planning_artifact_downloads(ui: Any, work: dict[str, Any]) -> None:
    products = work.get("products") if isinstance(work.get("products"), dict) else {}
    human = products.get("supporting_artifacts") if isinstance(products.get("supporting_artifacts"), list) else []
    planning = [
        item.get("name")
        for item in human
        if isinstance(item, dict) and item.get("name") in {"assembly_plan.md", "assembly_plan.json", "workflow_review.md"}
    ]
    if planning:
        with ui.row().classes("gap-2"):
            for name in planning:
                ui.badge(str(name))


def _render_part_card(ui: Any, part: dict[str, Any]) -> None:
    part_id = part.get("part_id") or part.get("label") or "part"
    run_id = part.get("download_run_id") or part.get("latest_run_id")
    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(str(part_id)).classes("text-lg font-semibold")
            ui.badge(part.get("status") or "unknown").classes(_badge_class(part.get("status")))
        _key_values(ui, {
            "Role": part.get("role") or "Empty",
            "Stage": part.get("current_stage") or "Empty",
            "Review": part.get("review_status") or "Empty",
            "Next": part.get("next_action") or "Empty",
        })
        _render_part_preview(ui, part, run_id if isinstance(run_id, str) else None)
        _render_part_downloads(ui, part, run_id if isinstance(run_id, str) else None)


def _render_part_preview(ui: Any, part: dict[str, Any], run_id: str | None) -> None:
    with ui.element("div").classes("part-preview w-full"):
        viewer_url = _part_viewer_url(part, run_id)
        if viewer_url:
            ui.html(f'<iframe title="STL preview" src="{viewer_url}"></iframe>')
        elif run_id and part.get("has_preview"):
            ui.image(f"/api/downloads/{quote(run_id, safe='')}/preview.png").classes("w-full")
        else:
            with ui.column().classes("w-full h-full items-center justify-center p-6"):
                ui.icon("view_in_ar").classes("text-4xl text-gray-400")
                ui.label("No 3D preview yet").classes("text-sm text-gray-500")


def _render_part_downloads(ui: Any, part: dict[str, Any], run_id: str | None) -> None:
    if not run_id:
        ui.label("No downloadable run yet.").classes("text-sm text-gray-500")
        return
    with ui.row().classes("gap-2"):
        if part.get("has_step"):
            ui.link("STEP", f"/api/downloads/{quote(run_id, safe='')}/model.step").classes("text-sm")
        if part.get("has_stl"):
            ui.link("STL", f"/api/downloads/{quote(run_id, safe='')}/model.stl").classes("text-sm")
        if part.get("has_preview"):
            ui.link("Preview PNG", f"/api/downloads/{quote(run_id, safe='')}/preview.png").classes("text-sm")


def _part_viewer_url(part: dict[str, Any], run_id: str | None) -> str | None:
    if not run_id or not part.get("has_stl"):
        return None
    file_url = quote(f"/api/downloads/{quote(run_id, safe='')}/model.stl", safe="")
    return f"/web-viewer/index.html?file={file_url}"


def _work_row(work: dict[str, Any], selected: str | None) -> dict[str, Any]:
    counts = work.get("part_counts") if isinstance(work.get("part_counts"), dict) else {}
    return {
        "work_id": work.get("work_id"),
        "title": work.get("title"),
        "overall_status": work.get("overall_status"),
        "parts": (
            f"{counts.get('accepted', 0)} accepted, {counts.get('blocked', 0)} blocked, "
            f"{counts.get('reference_only', 0)} reference"
        ),
        "readiness_score": work.get("readiness_score"),
        "risk_level": work.get("risk_level"),
        "review_status": work.get("review_status"),
        "next_action": work.get("next_action"),
        "updated_at": work.get("updated_at"),
        "selected": work.get("work_id") == selected,
    }


def _overview_metric(ui: Any, label: str, value: Any) -> None:
    with ui.card().classes("w-full shadow-none border border-gray-200"):
        ui.label(label).classes("text-xs uppercase text-gray-500")
        ui.label(str(value or "Empty")).classes("text-base font-semibold")


def _friendly_current_stage(work: dict[str, Any]) -> str:
    parts = work.get("parts") if isinstance(work.get("parts"), list) else []
    if any(isinstance(part, dict) and part.get("status") == "blocked" for part in parts):
        return "Review needed"
    if any(isinstance(part, dict) and part.get("status") == "accepted" for part in parts):
        return "Part result"
    nodes = work.get("nodes") if isinstance(work.get("nodes"), list) else []
    for node in reversed(nodes):
        if isinstance(node, dict) and node.get("status") in {"completed", "accepted", "available"}:
            return str(node.get("label") or node.get("id") or "Workflow")
    return "Requirement"


def _sidebar_part_count_label(counts: dict[str, Any]) -> str:
    total = int(counts.get("total") or 0)
    accepted = int(counts.get("accepted") or 0)
    blocked = int(counts.get("blocked") or 0)
    reference = int(counts.get("reference_only") or 0)
    if total <= 0:
        return "0 parts"
    details = []
    if accepted:
        details.append(f"{accepted} accepted")
    if blocked:
        details.append(f"{blocked} blocked")
    if reference:
        details.append(f"{reference} ref")
    return f"{total} parts" + (f" ({', '.join(details)})" if details else "")


def _badge_class(status: Any) -> str:
    if status in {"accepted", "completed", "generated", "selected"}:
        return "bg-green-600"
    if status in {"reviewable", "needs_review", "partial_success"}:
        return "bg-yellow-600"
    if status == "user_modified":
        return "bg-purple-600"
    if status in {"blocked", "failed"}:
        return "bg-red-600"
    if status in {"ready", "running"}:
        return "bg-blue-600"
    return "bg-gray-500"


def _label_with_help(ui: Any, text: Any, help_text: str, classes: str = "") -> None:
    with ui.row().classes("items-center gap-1"):
        ui.label(str(text)).classes(classes)
        _help_icon(ui, help_text)


def _help_icon(ui: Any, help_text: str) -> None:
    ui.label("?").classes(
        "inline-flex items-center justify-center rounded-full border border-gray-300 "
        "text-gray-500 text-xs w-4 h-4 cursor-help"
    ).tooltip(help_text)


def _nav_help(page: str) -> str:
    return {
        "workspace": "查看当前 workspace，创建或加载 workspace，并从 workspace 进入 Work。",
        "works": "查看和创建当前 workspace 下的 Work/Project。",
        "config": "配置当前 workspace 的 provider、模型、超时、重试和推进模式。",
        "overview": "查看当前 Work 的基本状态、需求入口、root run 和 part run 创建入口。",
        "workflow": "查看当前 Work 的阶段/part 节点、状态和文件关系。",
        "parts": "查看当前 Work 拆分出的 part job、run、状态和产物。",
        "review": "执行阶段 review、workflow review 和明确的 rework/打回操作。",
        "products": "查看面向用户的产物和可下载文件。",
        "runs": "查看当前 Work 的 run history；按需打开低层/未归类 runs。",
        "node": "查看选中 workflow 节点的输入、输出、状态和可执行动作。",
    }.get(page, "切换到该页面。")


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, reload: bool = False) -> None:
    """Run the local NiceGUI console bound to localhost by default."""
    try:
        from nicegui import ui
    except ImportError as exc:  # pragma: no cover - runtime path
        raise RuntimeError("NiceGUI is not installed. Install the web extra, for example: cadflow[web].") from exc

    create_nicegui_app()
    print(f"CadFlow NiceGUI Workflow Console: http://{host}:{port}/")
    ui.run(host=host, port=port, reload=reload, title="CadFlow Workflow Console")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local NiceGUI CadFlow workflow console.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host. Defaults to 127.0.0.1.")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="Bind port. Defaults to 8780.")
    parser.add_argument("--reload", action="store_true", help="Enable NiceGUI reload for local UI development.")
    args = parser.parse_args(argv)
    serve(host=args.host, port=args.port, reload=args.reload)


def _render_runs(
    ui: Any,
    data: dict[str, Any],
    state: dict[str, Any],
    on_select: Callable[[str], None],
    refresh: Callable[[], None],
) -> None:
    runs = data.get("runs") or []
    selected = data.get("selected_run_id")
    pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else _empty_pagination(DEFAULT_RUN_PAGE_SIZE, 0)
    _label_with_help(ui, "History", "Immutable Run lineage for this Work. Open a Run to inspect a read-only snapshot.", "text-xl font-semibold")
    ui.label("Runs are shown as Work lineage first; debug and unclassified runs remain excluded by default.").classes("text-sm text-gray-600")
    if not runs:
        ui.label("No workflow runs found.").classes("text-gray-600")
        return
    with ui.element("section").classes("history-list w-full"):
        for run in runs:
            if not isinstance(run, dict):
                continue
            row = _run_row(run, selected)
            card = ui.element("article").classes("history-run-card" + (" workflow-run-current" if row.get("selected") else ""))
            card.on("click", lambda _event, run_id=row["run_id"]: on_select(run_id))
            with card:
                with ui.row().classes("w-full items-start justify-between gap-3"):
                    with ui.column().classes("gap-1"):
                        ui.label(row.get("run_id") or "Run").classes("text-base font-semibold")
                        ui.label(run.get("summary") or "Immutable workflow attempt.").classes("text-sm text-gray-700")
                    ui.badge(str(row.get("status") or "unknown").replace("_", " ")).classes(_badge_class(row.get("status")))
                with ui.element("div").classes("history-run-grid w-full mt-3"):
                    _history_field(ui, "Relation", run.get("relation") or run.get("lineage_state") or "historical")
                    _history_field(ui, "Parent", run.get("parent_run_id") or "—")
                    _history_field(ui, "Active part", row.get("selected_part_id") or "—")
                    _history_field(ui, "Artifacts", f"STEP {row.get('step')} · STL {row.get('stl')}")
                    _history_field(ui, "Created", run.get("created_at") or "—")
                ui.label("Open Snapshot · read-only audit").classes("workflow-meta mt-2")


def _toggle_run_detail_option(
    state: dict[str, Any],
    key: str,
    value: bool,
    refresh: Callable[[], None],
) -> None:
    state[key] = value
    state["selected_run_id"] = None
    state["offset"] = 0
    refresh()


def _apply_run_filters(state: dict[str, Any], search: str | None, limit: Any, refresh: Callable[[], None]) -> None:
    state["search"] = (search or "").strip()
    state["limit"] = int(limit or DEFAULT_RUN_PAGE_SIZE)
    state["offset"] = 0
    state["selected_run_id"] = None
    refresh()


def _change_run_page(
    state: dict[str, Any],
    direction: int,
    pagination: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    limit = int(pagination.get("limit") or state.get("limit") or DEFAULT_RUN_PAGE_SIZE)
    offset = int(pagination.get("offset") or 0) + (direction * limit)
    state["offset"] = max(0, offset)
    state["limit"] = limit
    state["selected_run_id"] = None
    refresh()


def _render_workflow_review(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    run_id = data.get("selected_run_id")
    review = data.get("workflow_review") or {}
    last = state.get("workflow_review_result")
    with ui.card().classes("w-full"):
        _label_with_help(ui, "Agent Workflow Review", "CadFlow 基于当前 lineage 的 artifacts 自评完整性、风险和设计可信度，并写入可追溯 review artifacts。", "text-xl font-semibold")
        if review.get("present"):
            _key_values(ui, {
                "Overall status": review.get("overall_status") or "Empty",
                "Readiness score": review.get("readiness_score"),
                "Risk level": review.get("risk_level") or "Empty",
                "Risks": review.get("risk_count", 0),
                "Recommended actions": review.get("recommended_next_action_count", 0),
            })
            _list_block(ui, "Summary", review.get("summary_preview"))
        else:
            ui.label("No workflow review has been generated for this run.").classes("text-sm text-gray-500")
        if last is not None:
            ui.markdown(f"```json\n{json.dumps(last, indent=2, sort_keys=True)}\n```").classes("w-full")
        button = ui.button("Refresh agent workflow review", icon="smart_toy", on_click=lambda: _create_workflow_review_ui(actions, run_id, state, refresh))
        button.tooltip("Ask CadFlow to reassess the current Run lineage. Target: selected Run. Result: workflow_review.json and workflow_review.md are updated; no CAD model is generated.")
        if not run_id:
            button.disable()


def _render_requirement_review(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    review_data = data["requirement_review"]
    _key_values(ui, {
        "Original prompt": review_data.get("original_prompt") or "Empty",
        "Detected scope": review_data.get("detected_scope") or "Empty",
        "Product family": review_data.get("product_family") or "Empty",
        "Part family": review_data.get("part_family") or "Empty",
        "Blocked reason": review_data.get("blocked_reason") or "Empty",
    })
    _list_block(ui, "Assumptions", review_data.get("assumptions"))
    _list_block(ui, "Missing information", review_data.get("missing_information"))
    _list_block(ui, "Clarification questions", review_data.get("clarification_questions"))
    _list_block(ui, "Diagnostics", review_data.get("diagnostics"))
    _render_requirement_clarification_form(ui, data, actions, state, refresh, review_data)


def _render_requirement_clarification_form(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    review_data: dict[str, Any],
) -> None:
    run_id = data.get("selected_run_id")
    requests = review_data.get("clarification_requests") or []
    with ui.card().classes("w-full"):
        _label_with_help(ui, "Requirement Clarification", "结构化回答 Requirement 阶段提出的问题；保存后由后端生成 requirement_v2.json。", "text-lg font-medium")
        _key_values(ui, {
            "requirement_v2.json": "generated" if review_data.get("requirement_v2_present") else "not generated",
            "Clarification applied": review_data.get("clarification_applied"),
            "Planning allowed": review_data.get("can_run_planning"),
        })
        if not requests:
            ui.label("No open clarification questions.").classes("text-sm text-gray-500")
        inputs = []
        for request in requests:
            field = request.get("field") or "unknown"
            question = request.get("question") or field
            answer = ui.input(question).props("outlined").classes("w-full")
            inputs.append((request, answer))
        notes = ui.textarea("Notes").props("outlined autogrow").classes("w-full")
        if state.get("requirement_clarification_result") is not None:
            ui.markdown(f"```json\n{json.dumps(state['requirement_clarification_result'], indent=2, sort_keys=True)}\n```").classes("w-full")
        button = ui.button(
            "Apply clarification",
            icon="save",
            on_click=lambda: _apply_requirement_clarification_ui(actions, run_id, inputs, notes.value, state, refresh),
        )
        button.tooltip("Save these answers as a validated requirement clarification. Target: selected Run. Result: preserves the original requirement and updates requirement_v2.json; no CAD is generated.")
        if not run_id or not inputs:
            button.disable()


def _render_inline_requirement_clarification(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    """Offer the existing structured clarification action in its causal context."""
    review = data.get("requirement_review") if isinstance(data.get("requirement_review"), dict) else {}
    requests = review.get("clarification_requests") if isinstance(review.get("clarification_requests"), list) else []
    if not requests:
        return
    with ui.element("section").classes("stage-detail-card w-full"):
        ui.html("<h3>REQUIREMENT CLARIFICATION</h3>")
        ui.label("Answer the open questions here. CadFlow creates a validated requirement_v2 record and preserves the original requirement.").classes("text-sm text-gray-700")
        inputs = []
        for request in requests:
            if not isinstance(request, dict):
                continue
            question = request.get("question") or request.get("field") or "Clarification"
            answer = ui.input(str(question)).props("outlined").classes("w-full")
            inputs.append((request, answer))
        notes = ui.textarea("Notes").props("outlined autogrow").classes("w-full")
        result = state.get("requirement_clarification_result")
        if isinstance(result, dict):
            if result.get("ok") is False or result.get("error"):
                ui.label("Clarification could not be saved: " + str(result.get("error") or "validation failed")).classes("text-sm text-red-700")
            else:
                ui.label("Clarification saved. The workflow has been refreshed with the updated requirement.").classes("text-sm text-green-700")
        button = ui.button(
            "Submit clarification",
            icon="save",
            on_click=lambda: _apply_requirement_clarification_ui(actions, data.get("selected_run_id"), inputs, notes.value, state, refresh),
        ).props("outline")
        button.tooltip("Save these answers as a validated requirement clarification. Target: selected Run. Result: preserves the original requirement and updates requirement_v2.json; no CAD is generated.")
        if not data.get("selected_run_id") or not inputs:
            button.disable()


def _render_assembly_plan(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    assembly = data["assembly_plan"]
    if not assembly.get("present"):
        ui.label("No assembly_plan.json found for this run.").classes("text-gray-600")
        return
    _key_values(ui, {
        "Scope": assembly.get("scope") or "Empty",
        "Status": assembly.get("status") or "Empty",
        "Part count": assembly.get("part_count"),
        "Candidate parts": ", ".join(assembly.get("candidate_part_ids") or []) or "Empty",
        "Reference-only parts": ", ".join(assembly.get("reference_only_part_ids") or []) or "Empty",
        "Blocked parts": ", ".join(assembly.get("blocked_part_ids") or []) or "Empty",
        "Interfaces": assembly.get("interface_count"),
        "Blocked reasons": ", ".join(assembly.get("blocked_reasons") or []) or "Empty",
    })
    columns = [
        {"name": key, "label": label, "field": key, "align": "left"}
        for key, label in (
            ("part_id", "part_id"),
            ("role", "role"),
            ("status", "status"),
            ("generation_strategy", "generation_strategy"),
            ("supported_candidate", "supported_candidate"),
            ("reason", "reason"),
        )
    ]
    ui.table(columns=columns, rows=assembly.get("parts") or [], row_key="part_id").classes("w-full")


def _render_part_workflow(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    run_id = data.get("selected_run_id")
    if not run_id:
        ui.label("Select a run first.").classes("text-gray-600")
        return
    last = state.get("last_action_result")
    if last is not None:
        ui.markdown(f"```json\n{json.dumps(last, indent=2, sort_keys=True)}\n```").classes("w-full")
    for card in (data.get("part_workflow") or {}).get("actions", []):
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between"):
                _label_with_help(ui, card["title"], "当前 part workflow 可执行动作。可用性由上游 artifact 是否存在决定。", "text-lg font-medium")
                ui.badge(card["current_status"])
            _key_values(ui, {
                "Required upstream artifact": card["required_upstream_artifact"],
                "Output artifact": card["output_artifact"],
                "Available": card["available"],
            })
            button = ui.button(card["action_label"], on_click=lambda _event=None, c=card: _run_ui_action(actions, run_id, c, state, refresh))
            button.tooltip("执行该阶段动作并写入新的 artifact；如果缺少上游文件则按钮不可用。")
            if not card["available"]:
                button.disable()


def _render_artifacts(ui: Any, data: dict[str, Any], backend: WorkflowConsoleBackend) -> None:
    run_id = data.get("selected_run_id")
    if not run_id:
        ui.label("Select a run first.").classes("text-gray-600")
        return
    artifact_options = {"show_debug": False, "show_internal": False}
    with ui.row().classes("gap-4"):
        debug_toggle = ui.checkbox("Show debug artifacts", value=False)
        _help_icon(ui, "显示调试类 artifact。默认隐藏，避免暴露不必要的低层信息。")
        internal_toggle = ui.checkbox("Show internal artifacts", value=False)
        _help_icon(ui, "显示内部流程 artifact。默认隐藏，用户产物优先显示。")
    current_page = build_artifacts_page_data(data.get("selected_run") or {}, **artifact_options)

    def refresh_artifacts() -> None:
        nonlocal current_page
        current_page = build_artifacts_page_data(
            data.get("selected_run") or {},
            show_debug=bool(debug_toggle.value),
            show_internal=bool(internal_toggle.value),
        )
        artifact_container.clear()
        with artifact_container:
            _render_artifact_list(ui, current_page, backend, run_id)

    debug_toggle.on_value_change(lambda _: refresh_artifacts())
    internal_toggle.on_value_change(lambda _: refresh_artifacts())
    artifact_container = ui.column().classes("w-full")
    with artifact_container:
        _render_artifact_list(ui, current_page, backend, run_id)


def _render_artifact_list(ui: Any, artifacts_page: dict[str, Any], backend: WorkflowConsoleBackend, run_id: str) -> None:
    for model in artifacts_page.get("model_files", []):
        ui.badge(f"{model['name']}: {'available' if model['available'] else 'missing'}")
    for artifact in artifacts_page.get("artifacts", []):
        with ui.expansion(artifact["name"]).classes("w-full"):
            ui.badge(artifact.get("display_category", "unknown"))
            try:
                content = read_artifact_page_content(backend, run_id, artifact["name"])
                ui.markdown(f"```json\n{json.dumps(content.get('content'), indent=2, sort_keys=True)}\n```").classes("w-full mono")
            except Exception as exc:
                ui.label(str(exc)).classes("text-negative")


def _run_ui_action(
    actions: WorkflowConsoleActions,
    run_id: str,
    card: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    method = getattr(actions, card["action"])
    try:
        state["last_action_result"] = method(run_id)
    except Exception as exc:
        state["last_action_result"] = {"ok": False, "error": str(exc)}
    refresh()


def _save_artifact_override_ui(
    actions: WorkflowConsoleActions,
    run_id: str | None,
    artifact: str | None,
    raw_json: str | None,
    edit_reason: str | None,
    state: dict[str, Any],
    result_key: str,
    refresh: Callable[[], None],
) -> Any:
    return _schedule_action(_save_artifact_override_ui_async(actions, run_id, artifact, raw_json, edit_reason, state, result_key, refresh))


async def _save_artifact_override_ui_async(
    actions: WorkflowConsoleActions,
    run_id: str | None,
    artifact: str | None,
    raw_json: str | None,
    edit_reason: str | None,
    state: dict[str, Any],
    result_key: str,
    refresh: Callable[[], None],
) -> None:
    action = {
        "key": "save_assembly_plan_override" if artifact == "assembly_plan.json" else "save_artifact_override",
        "label": "Save Assembly Plan Override" if artifact == "assembly_plan.json" else "Save Artifact Override",
        "target_work_id": None,
        "target_run_id": run_id,
        "target_stage_id": "assembly_plan" if artifact == "assembly_plan.json" else None,
    }
    language = str(state.get("language") or "en")
    if run_id is None or not artifact:
        await _execute_action_lifecycle(action, state, refresh, lambda: (_ for _ in ()).throw(ValueError("Select a run and artifact first.")), language=language)
        return
    try:
        content = json.loads(raw_json or "{}")
    except json.JSONDecodeError as exc:
        state[result_key] = {"ok": False, "error": "invalid JSON", "diagnostic_code": "artifact_override.invalid_json", "detail": str(exc)}
        await _execute_action_lifecycle(action, state, refresh, lambda: (_ for _ in ()).throw(ValueError("invalid JSON")), language=language)
        return
    if not isinstance(content, dict):
        state[result_key] = {"ok": False, "error": "override JSON must be an object", "diagnostic_code": "artifact_override.not_object"}
        await _execute_action_lifecycle(action, state, refresh, lambda: (_ for _ in ()).throw(ValueError("override JSON must be an object")), language=language)
        return
    def execute() -> dict[str, Any]:
        return actions.backend.write_artifact_by_id(
            run_id,
            artifact,
            content,
            edit_reason=edit_reason,
        )
    result = await _execute_action_lifecycle(action, state, refresh, execute, language=language)
    if result is not None:
        state[result_key] = result


def _apply_requirement_clarification_ui(
    actions: WorkflowConsoleActions,
    run_id: str | None,
    inputs: list[tuple[dict[str, Any], Any]],
    notes: str | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    if run_id is None:
        state["requirement_clarification_result"] = {"ok": False, "error": "Select a run first."}
        refresh()
        return
    answers = []
    for index, (request, widget) in enumerate(inputs, start=1):
        answer = str(getattr(widget, "value", "") or "").strip()
        if not answer:
            continue
        answers.append({
            "question_id": request.get("question_id") or f"q{index}",
            "field": request.get("field"),
            "question": request.get("question"),
            "answer": answer,
        })
    try:
        state["requirement_clarification_result"] = actions.apply_requirement_clarification(
            run_id,
            answers=answers,
            notes=notes,
        )
    except Exception as exc:
        state["requirement_clarification_result"] = {"ok": False, "error": str(exc)}
    refresh()


def _create_workflow_review_ui(
    actions: WorkflowConsoleActions,
    run_id: str | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    if run_id is None:
        state["workflow_review_result"] = {"ok": False, "error": "Select a run first."}
        refresh()
        return
    try:
        state["workflow_review_result"] = actions.create_workflow_review(run_id)
    except Exception as exc:
        state["workflow_review_result"] = {"ok": False, "error": str(exc)}
    refresh()


def _run_row(run: dict[str, Any], selected: str | None) -> dict[str, Any]:
    reviewed = run.get("reviewed_part_summary") if isinstance(run.get("reviewed_part_summary"), dict) else {}
    status = run.get("status") if isinstance(run.get("status"), dict) else {}
    downloadables = {item.get("name") for item in _as_list(run.get("downloadables")) if isinstance(item, dict)}
    return {
        "run_id": run.get("run_id"),
        "status": status.get("status"),
        "stage": status.get("stage"),
        "selected_part_id": _first_present(
            run.get("selected_part_id"),
            _dict_get(reviewed.get("part_request"), "part_id"),
            _dict_get(reviewed.get("reviewed_part_handoff"), "part_id"),
            _dict_get(reviewed.get("part_result_review"), "part_id"),
        ),
        "step": "yes" if "model.step" in downloadables else "no",
        "stl": "yes" if "model.stl" in downloadables else "no",
        "selected": run.get("run_id") == selected,
    }


def _history_field(ui: Any, label: str, value: Any) -> None:
    with ui.column().classes("gap-1 min-w-0"):
        ui.label(label).classes("history-field-label")
        ui.label(str(value)).classes("text-sm text-gray-700 break-words")


def _run_history_row_as_run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row.get("run_id"),
        "status": {"status": row.get("status")},
        "stage": row.get("kind"),
        "selected_part_id": None,
        "downloadables": [],
        "child_runs": [],
        "reviewed_part_summary": {},
    }


def _artifact_names(run: dict[str, Any]) -> set[str]:
    return {
        item["name"]
        for item in _as_list(run.get("artifacts"))
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def _assembly_part_row(part: dict[str, Any]) -> dict[str, Any]:
    reasons = _as_list(part.get("blocked_reason_codes"))
    return {
        "part_id": part.get("part_id"),
        "role": part.get("role"),
        "status": part.get("part_status"),
        "generation_strategy": part.get("generation_strategy"),
        "supported_candidate": part.get("supported_candidate") is True,
        "reason": ", ".join(str(item) for item in reasons) if reasons else "",
        "reference_only": part.get("reference_only") is True,
    }


def _read_public_artifact_content(
    backend: WorkflowConsoleBackend,
    run_id: str,
    artifact: str,
    *,
    root: str | None = None,
) -> Any:
    response = dispatch_route(backend, "read_artifact", path_params={"run_id": run_id, "artifact": artifact}, query=_query(root))
    if not response["ok"]:
        return None
    artifact_data = _unwrap_artifact_data(response["data"])
    return artifact_data.get("content") if isinstance(artifact_data, dict) else None


def _collect_diagnostics(run: dict[str, Any], requirement: dict[str, Any], report_summary: dict[str, Any]) -> list[Any]:
    diagnostics: list[Any] = []
    for key in ("warnings", "errors"):
        diagnostics.extend(_as_list(report_summary.get(key)))
    reviewed = run.get("reviewed_part_summary") if isinstance(run.get("reviewed_part_summary"), dict) else {}
    for section in ("assembly_plan", "part_request", "part_request_review", "reviewed_part_handoff", "part_result_review"):
        diagnostics.extend(_as_list(_dict_get(reviewed.get(section), "diagnostic_codes")))
    diagnostics.extend(_as_list(_dict_get(requirement, "diagnostic_codes")))
    return diagnostics


def _bridge_status(run: dict[str, Any]) -> str:
    reviewed = run.get("reviewed_part_summary") if isinstance(run.get("reviewed_part_summary"), dict) else {}
    lineage = reviewed.get("lineage") if isinstance(reviewed.get("lineage"), dict) else {}
    return "created" if lineage.get("present") else "not created"


def _part_result_review_status(run: dict[str, Any]) -> str:
    reviewed = run.get("reviewed_part_summary") if isinstance(run.get("reviewed_part_summary"), dict) else {}
    return _dict_get(reviewed.get("part_result_review"), "status") or "not reviewed"


def _key_values(ui: Any, values: dict[str, Any]) -> None:
    with ui.grid(columns=2).classes("w-full gap-2"):
        for key, value in values.items():
            ui.label(str(key)).classes("text-sm text-gray-500")
            ui.label(str(value)).classes("text-sm")


def _compact_display(value: Any) -> str:
    if value in (None, "", [], {}):
        return "Empty"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)[:220]
    return str(value)


def _list_block(ui: Any, title: str, items: Any) -> None:
    ui.label(title).classes("font-medium")
    values = _as_list(items)
    if not values:
        ui.label("Empty").classes("text-sm text-gray-500")
        return
    for item in values:
        ui.label(json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)).classes("text-sm")


def _query(
    root: str | None,
    *,
    limit: int | None = None,
    offset: int | None = None,
    search: str | None = None,
) -> dict[str, Any] | None:
    query: dict[str, Any] = {}
    if root:
        query["root"] = root
    if limit is not None:
        query["limit"] = limit
    if offset is not None:
        query["offset"] = offset
    if search:
        query["search"] = search
    return query or None


def _empty_pagination(limit: int, offset: int) -> dict[str, Any]:
    return {
        "limit": limit,
        "offset": offset,
        "returned": 0,
        "total": 0,
        "has_previous": False,
        "has_next": False,
    }


def _unwrap_artifact_data(value: Any) -> Any:
    if isinstance(value, dict) and "artifact" in value and isinstance(value["artifact"], dict):
        return value["artifact"]
    return value


def _drop_path_like_keys(value: Any) -> Any:
    if isinstance(value, list):
        return [_drop_path_like_keys(item) for item in value]
    if not isinstance(value, dict):
        return value
    public = {}
    for key, item in value.items():
        if str(key).lower() in {"path", "run_dir", "root", "output_dir", "child_output_dir"}:
            continue
        public[key] = _drop_path_like_keys(item)
    return public


def _dict_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _clarification_requests(requirement: Any) -> list[dict[str, Any]]:
    if not isinstance(requirement, dict):
        return []
    requests = requirement.get("follow_up_requests")
    if not isinstance(requests, list) or not requests:
        requests = [
            item
            for item in requirement.get("missing_information", [])
            if isinstance(item, dict) and item.get("ask_user")
        ]
    result = []
    for index, item in enumerate(requests, start=1):
        if not isinstance(item, dict):
            continue
        result.append({
            "question_id": item.get("question_id") or f"q{index}",
            "field": item.get("field"),
            "question": item.get("question") or item.get("message") or item.get("field"),
        })
    return result


def _can_run_planning(requirement: Any) -> bool:
    if not isinstance(requirement, dict):
        return False
    action = _dict_get(_dict_get(requirement.get("requirement_status"), "flow_decision"), "action")
    return action not in {"ask_user", "return", "return_to_requirement"}


def _part_by_id(work: dict[str, Any], part_id: str) -> dict[str, Any]:
    for part in work.get("parts") or []:
        if isinstance(part, dict) and part.get("part_id") == part_id:
            return part
    graph = _dict_get(work, "workflow_graph")
    graph_parts = graph.get("part_nodes", []) if isinstance(graph, dict) else []
    for part in graph_parts:
        if isinstance(part, dict) and part.get("part_id") == part_id:
            return part
    return {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


if __name__ == "__main__":
    main()
