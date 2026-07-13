"""NiceGUI shell for the local reviewed-part workflow console.

The module keeps data shaping independent from NiceGUI so tests can exercise
the privacy and gating behavior without browser automation or the optional UI
dependency.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from ai_native_cad.workflow_console.actions import WorkflowConsoleActions
from ai_native_cad.workflow_console.actions import STAGE_REVIEW_STATUSES, STAGE_REVIEW_STAGES, STAGE_REWORK_TARGETS
from ai_native_cad.workflow_console.artifact_display import filter_artifacts_for_display
from ai_native_cad.workflow_console.backend import DOWNLOADABLE_FILES, WorkflowConsoleBackend
from ai_native_cad.workflow_console.review_surface import REVIEW_SURFACE_ARTIFACTS, build_workflow_review_surface
from ai_native_cad.workflow_console.work_stage_projection import build_work_stage_projection, unavailable_work_stage_projection
from ai_native_cad.workflow_console.workflow_page_view_model import build_workflow_page_view_model
from ai_native_cad.workflow_console.routes import dispatch_route
from ai_native_cad.workflow_console.server import resolve_downloadable
from ai_native_cad.workflow_console.stage_runner import READABLE_ARTIFACTS

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8780
DEFAULT_RUN_PAGE_SIZE = 50
WEB_VIEWER_ROOT = Path(__file__).resolve().parents[3] / "web-viewer"
WORK_USER_PAGES = (
    ("overview", "dashboard", "Overview"),
    ("workflow", "account_tree", "Workflow"),
    ("parts", "view_list", "Parts"),
    ("history", "history", "History"),
)

# The workflow cockpit deliberately has one visual vocabulary.  Keep semantic
# state, spacing, and responsive rules here instead of scattering styles among
# individual renderers.  NiceGUI still only receives presentation data from the
# workflow page view model; these classes never infer workflow state.
WORKFLOW_UI_CSS = """
:root {
  --wf-space-1:4px; --wf-space-2:8px; --wf-space-3:12px; --wf-space-4:16px;
  --wf-space-5:24px; --wf-space-6:32px; --wf-radius:10px; --wf-radius-sm:7px;
  --wf-border:#dbe3ea; --wf-surface:#ffffff; --wf-muted:#64748b;
  --wf-bg:#f6f8fb; --wf-ink:#172033; --wf-primary:#2563eb;
  --wf-completed:#15803d; --wf-running:#2563eb; --wf-review:#b7791f;
  --wf-blocked:#dc2626; --wf-stale:#a16207; --wf-unavailable:#475569;
  --wf-reference:#64748b; --wf-override:#7c3aed;
}
body{background:var(--wf-bg);color:var(--wf-ink)}
.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.sidebar{background:#fff;border-right:1px solid var(--wf-border);min-height:100vh}.content{min-height:100vh}.nav-btn{justify-content:flex-start;width:100%}
.work-tree-item{border:1px solid transparent;border-radius:var(--wf-radius-sm);padding:var(--wf-space-2) 10px;width:100%;cursor:pointer}.work-tree-item:hover{background:#f8fafc}.work-tree-item-active{background:#eef6ff;border-color:#bfdbfe}.work-page-tree{border-left:2px solid #dbeafe;margin-left:14px;padding-left:10px}.work-page-btn{font-size:12px;min-height:30px;justify-content:flex-start;width:100%}
.workflow-hero,.workflow-snapshot-banner,.workflow-run-strip-panel,.workflow-stage-detail-v2{background:var(--wf-surface);border:1px solid var(--wf-border);border-radius:var(--wf-radius);padding:var(--wf-space-4)}
.workflow-hero{border-color:#cbd5e1;box-shadow:0 1px 2px rgba(15,23,42,.04)}.workflow-snapshot-banner{border-left:4px solid var(--wf-review);background:#fffcf5}.workflow-eyebrow{font-size:12px;font-weight:700;letter-spacing:.08em;color:var(--wf-muted)}.workflow-summary{max-width:760px;line-height:1.55}.workflow-meta{font-size:12px;color:var(--wf-muted)}
.workflow-run-strip{overflow-x:auto;padding-bottom:var(--wf-space-1)}.workflow-run-strip-inner{min-width:max-content}.workflow-run-item{min-width:180px;border:1px solid var(--wf-border);border-radius:var(--wf-radius-sm);padding:var(--wf-space-3);cursor:pointer;background:#fff}.workflow-run-item:hover{border-color:#94a3b8}.workflow-run-current{border-color:#60a5fa;background:#eff6ff}.workflow-run-failed{border-color:#fecaca;background:#fff8f8}.workflow-run-state{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em}
.workflow-graph{overflow-x:auto;background:#fff;border:1px solid var(--wf-border);border-radius:var(--wf-radius);padding:var(--wf-space-5)}.workflow-graph-canvas{min-width:1120px}.workflow-graph-label{font-size:12px;font-weight:700;letter-spacing:.08em;color:var(--wf-muted)}.workflow-stage-row,.workflow-lane-row{display:flex;align-items:flex-start;gap:var(--wf-space-2);flex-wrap:nowrap}.workflow-step{align-items:center;gap:var(--wf-space-1);cursor:pointer;min-width:104px;max-width:132px;padding:var(--wf-space-2);border:1px solid transparent;border-radius:var(--wf-radius-sm)}.workflow-step:hover{background:#f8fafc}.workflow-step-selected{border-color:var(--wf-primary);background:#eff6ff;outline:2px solid #bfdbfe;outline-offset:1px}.workflow-connector{height:2px;min-width:24px;flex:1;background:#cbd5e1;margin-top:18px;position:relative}.workflow-connector:after{content:'›';position:absolute;right:-2px;top:-12px;color:#94a3b8;font-size:24px}.workflow-branch-note{margin-left:208px;color:var(--wf-muted);font-size:12px}.workflow-lane{border-left:2px solid #cbd5e1;margin-left:278px;padding-left:var(--wf-space-3)}
.workflow-dot{width:18px;height:18px;border:2px solid #fff;border-radius:999px;box-shadow:0 0 0 2px #cbd5e1}.workflow-dot.status-completed,.workflow-dot.status-contract_complete{background:var(--wf-completed);box-shadow:0 0 0 2px #86efac}.workflow-dot.status-running{background:var(--wf-running);box-shadow:0 0 0 2px #93c5fd;animation:wf-pulse 1.7s infinite}.workflow-dot.status-needs_review{background:var(--wf-review);box-shadow:0 0 0 2px #fde68a}.workflow-dot.status-blocked,.workflow-dot.status-failed{background:var(--wf-blocked);box-shadow:0 0 0 2px #fecaca}.workflow-dot.status-stale{background:#fff;border:3px solid var(--wf-stale);box-shadow:0 0 0 2px #fde68a}.workflow-dot.status-user_modified{background:var(--wf-override);box-shadow:0 0 0 2px #ddd6fe}.workflow-dot.status-execution_skipped,.workflow-dot.status-skipped{background:#f8fafc;border:3px double #64748b;box-shadow:0 0 0 2px #cbd5e1}.workflow-dot.status-unavailable{background:#fff;border:2px dashed var(--wf-unavailable);box-shadow:none}.workflow-dot.status-not_started{background:#fff;border-color:#94a3b8;box-shadow:none}.workflow-dot.status-reference_only{border-radius:3px;background:#fff;border-color:var(--wf-reference);box-shadow:none}.workflow-dot.kind-review,.workflow-dot.kind-rework{transform:rotate(45deg);border-radius:3px}.workflow-dot.kind-review+label,.workflow-dot.kind-rework+label{margin-top:2px}.workflow-attention{font-size:10px;color:var(--wf-review);font-weight:700}.workflow-node-status{font-size:11px;color:var(--wf-muted);text-transform:capitalize}
.workflow-part-candidate{min-width:146px;max-width:180px;border:1px solid var(--wf-border);border-radius:999px;padding:var(--wf-space-2) var(--wf-space-3);background:#fff}.workflow-part-candidate.reference-component{border-radius:var(--wf-radius-sm);border-style:dashed;background:#f8fafc}.workflow-part-selected{border-color:var(--wf-primary);outline:2px solid #bfdbfe;outline-offset:1px}
.stage-conclusion{border-bottom:1px solid var(--wf-border);padding-bottom:var(--wf-space-3)}.stage-detail-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--wf-space-3)}.stage-detail-card{border:1px solid var(--wf-border);border-radius:var(--wf-radius-sm);padding:var(--wf-space-3);min-height:156px}.stage-detail-card h3{margin:0 0 var(--wf-space-2);font-size:12px;letter-spacing:.07em;color:var(--wf-muted);font-weight:700}.stage-detail-card.decision{background:#fbfcff}.stage-artifact-list{margin-top:var(--wf-space-2);padding-top:var(--wf-space-2);border-top:1px solid #eef2f7}.workflow-evidence{border-top:1px solid var(--wf-border);padding-top:var(--wf-space-3)}.workflow-disabled-reason{font-size:12px;color:var(--wf-muted)}
.history-list{display:grid;gap:var(--wf-space-3)}.history-run-card{border:1px solid var(--wf-border);border-radius:var(--wf-radius-sm);padding:var(--wf-space-3);background:#fff;cursor:pointer}.history-run-card:hover{border-color:#94a3b8}.history-run-grid{display:grid;grid-template-columns:1.2fr repeat(4,minmax(0,1fr));gap:var(--wf-space-3)}.history-field-label{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--wf-muted)}
@keyframes wf-pulse{50%{box-shadow:0 0 0 5px #dbeafe}}@media(max-width:1100px){.stage-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr)}}@media(max-width:760px){.sidebar{width:100%;min-height:auto;border-right:0;border-bottom:1px solid var(--wf-border)}.content{min-width:0;padding:var(--wf-space-3)}.workflow-hero,.workflow-snapshot-banner,.workflow-run-strip-panel,.workflow-stage-detail-v2{padding:var(--wf-space-3)}.workflow-graph{padding:var(--wf-space-3)}.workflow-graph-canvas{min-width:1040px}.stage-detail-grid,.history-run-grid{grid-template-columns:1fr}.workflow-lane{margin-left:170px}.workflow-branch-note{margin-left:140px}}
"""

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
        query={"limit": 50, "offset": 0, "show_debug": False},
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
    load_runs = selected_run_id is not None
    if active_page in {"runs", "history"}:
        runs = [_run_history_row_as_run(row) for row in work_detail.get("run_history", []) if isinstance(row, dict)]
        selected = selected_run_id or (runs[0]["run_id"] if runs else selected)
    run_data = (
        build_selected_run_data(backend, selected, root=root, selected_stage_id=selected_stage_id, language=language)
        if selected and (active_page in {"workflow", "review", "products", "runs", "history"} or selected_run_id is not None or load_runs)
        else empty_selected_run_data()
    )
    work_projection = None
    if selected_work and active_page in {"workflow", "review"}:
        try:
            work_projection = build_work_stage_projection(backend, selected_work)
        except (FileNotFoundError, ValueError) as exc:
            # A missing/corrupt Work must degrade to explicit unavailable stage
            # data; history remains independently inspectable.
            work_projection = unavailable_work_stage_projection(selected_work, type(exc).__name__)
    provider = build_provider_config_data(backend) if active_page == "config" else {"provider_config": None, "provider_check": None}
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
        data["workflow_page"] = build_workflow_page_view_model(
            backend,
            selected_work,
            view_mode="run_snapshot" if view_mode == "run_snapshot" else "current_work",
            selected_run_id=selected_run_id if view_mode == "run_snapshot" else None,
            selected_stage_id=selected_stage_id,
            language=language,
        )
    data["view_mode"] = "run_snapshot" if view_mode == "run_snapshot" else "current_work"
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
        "products": {"human_facing": [], "downloadables": [], "artifacts_secondary_by_default": True},
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
        "workflow_review_surface": build_workflow_review_surface(WorkflowConsoleBackend(), None, {}),
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
        from starlette.responses import FileResponse
    except ImportError as exc:  # pragma: no cover - exercised only without optional dependency at runtime
        raise RuntimeError("NiceGUI is not installed. Install the web extra, for example: cadflow[web].") from exc

    console_backend = backend or WorkflowConsoleBackend()
    actions = WorkflowConsoleActions(console_backend)
    if WEB_VIEWER_ROOT.exists():
        app.add_static_files("/web-viewer", str(WEB_VIEWER_ROOT))

    @app.get("/api/downloads/{run_id}/{filename}")
    def download_file(run_id: str, filename: str, root: str | None = None) -> FileResponse:
        return FileResponse(resolve_downloadable(console_backend, run_id, filename, root=root))

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
        with ui.row().classes("w-full gap-0"):
            sidebar = ui.column().classes("sidebar w-80 gap-3 p-4")
            content = ui.column().classes("content flex-1 gap-4 p-5")

            def refresh() -> None:
                sidebar.clear()
                content.clear()
                data = build_console_page_data(
                    console_backend,
                    state.get("selected_run_id"),
                    selected_work_id=state.get("selected_work_id"),
                    active_page=state.get("active_page", "workspace"),
                    selected_node_id=state.get("selected_node_id"),
                    selected_stage_id=state.get("selected_stage_id"),
                    view_mode=state.get("view_mode", "current_work"),
                    language=state.get("language", "en"),
                    show_unclassified_runs=bool(state.get("show_unclassified_runs")),
                    show_low_level_details=bool(state.get("show_low_level_details")),
                    limit=state.get("limit", DEFAULT_RUN_PAGE_SIZE),
                    offset=state.get("offset", 0),
                    search=state.get("search") or None,
                )
                state["selected_work_id"] = data.get("selected_work_id")
                if state.get("view_mode") == "run_snapshot":
                    state["selected_run_id"] = data.get("selected_run_id")
                with sidebar:
                    _render_sidebar(ui, data, state, select_work, select_page, refresh)
                with content:
                    if state.get("active_page") in {"overview", "workflow", "node", "parts", "review", "products", "runs"}:
                        _render_work_header(ui, data)
                    _render_active_page(ui, data, actions, state, refresh, select_node, select_stage, lambda run_id: select_run(run_id), select_current_work, select_work, select_page)

            def select_work(work_id: str) -> None:
                state["selected_work_id"] = work_id
                state["selected_run_id"] = None
                state["view_mode"] = "current_work"
                state["selected_node_id"] = None
                state["selected_stage_id"] = None
                state["active_page"] = "overview"
                refresh()

            def select_page(page: str) -> None:
                state["active_page"] = page
                if page != "node":
                    state["selected_node_id"] = None
                if page != "workflow":
                    state["selected_stage_id"] = None
                refresh()

            def select_node(node_id: str) -> None:
                state["active_page"] = "node"
                state["selected_node_id"] = node_id
                refresh()

            def select_stage(stage_id: str) -> None:
                state["active_page"] = "workflow"
                state["selected_stage_id"] = stage_id
                refresh()

            def select_run(run_id: str) -> None:
                state["selected_run_id"] = run_id
                state["view_mode"] = "run_snapshot"
                state["active_page"] = "workflow"
                refresh()

            def select_current_work() -> None:
                state["view_mode"] = "current_work"
                state["selected_run_id"] = None
                refresh()

            refresh()

    return app


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
    for page, icon, text in (
        ("workspace", "folder", "Workspace"),
        ("works", "workspaces", "Works"),
        ("config", "settings", "Config"),
    ):
        button = ui.button(text, icon=icon, on_click=lambda p=page: on_select_page(p))
        button.props("flat dense" if state.get("active_page") != page else "unelevated dense color=primary").classes("nav-btn")
        button.tooltip(_nav_help(page))
    ui.label(f"Workspace: {workspace.get('name') or 'workspace'}").classes("text-xs text-gray-500")
    ui.label(workspace.get("display_path") or workspace.get("relative_path") or "workspace").classes("text-xs text-gray-500 break-all")
    ui.separator()
    ui.label("Works").classes("text-sm font-medium text-gray-500")
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
                    item = ui.button(text, icon=icon, on_click=lambda p=page: on_select_page(p))
                    item.props("flat dense" if state.get("active_page") != page else "unelevated dense color=secondary")
                    item.classes("work-page-btn")
                    item.tooltip(_nav_help(page))


def _render_work_header(ui: Any, data: dict[str, Any]) -> None:
    summary = _dict_get(data.get("selected_work"), "summary") or {}
    if not summary:
        ui.label("No Work selected").classes("text-2xl font-semibold")
        return
    counts = summary.get("part_counts") if isinstance(summary.get("part_counts"), dict) else {}
    with ui.row().classes("w-full items-start justify-between"):
        with ui.column().classes("gap-1"):
            ui.label(summary.get("title") or summary.get("work_id")).classes("text-2xl font-semibold")
            ui.label(f"Work: {summary.get('work_id')}").classes("text-sm text-gray-500")
        with ui.row().classes("gap-2"):
            ui.badge(summary.get("overall_status") or "unknown").classes(_badge_class(summary.get("overall_status")))
            ui.badge(f"Current run: {summary.get('latest_run_id') or 'none'}")
            ui.badge(f"Parts: {counts.get('accepted', 0)} accepted / {counts.get('blocked', 0)} blocked")
    ui.label(summary.get("next_action") or "").classes("text-sm text-gray-700")


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
    if page == "workspace":
        _render_workspace_page(ui, data, state, refresh, on_select_work)
    elif page == "works":
        _render_works(ui, data, state, on_select_work, refresh)
    elif page == "overview":
        _render_work_overview(ui, data, state, refresh)
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
    config = data.get("workspace_config") if isinstance(data.get("workspace_config"), dict) else {}
    with ui.row().classes("w-full items-center justify-between"):
        with ui.column().classes("gap-1"):
            _label_with_help(ui, "Workspace", "当前本地工作区。Work、配置和新的 run 都会写入这个 workspace。", "text-2xl font-semibold")
            ui.label(workspace.get("display_path") or "No workspace path").classes("text-sm text-gray-600 break-all")
        with ui.row().classes("gap-2"):
            _workspace_dialog_button(ui, "New Workspace", "create_new_folder", "create", workspace, state, refresh)
            _workspace_dialog_button(ui, "Load Workspace", "folder_open", "load", workspace, state, refresh)
    _key_values(ui, {
        "Name": workspace.get("name") or "workspace",
        "Initialized": workspace.get("present"),
        "External": workspace.get("is_external"),
        "Works": workspace.get("work_count", 0),
        "Runs": workspace.get("run_count", 0),
        "Advancement mode": config.get("advancement_mode") or workspace.get("advancement_mode") or "manual_confirm",
    })
    if state.get("workspace_result"):
        ui.markdown(f"```json\n{json.dumps(state['workspace_result'], indent=2, sort_keys=True)}\n```").classes("w-full mono")
    with ui.card().classes("w-full border border-amber-200 bg-amber-50 shadow-none"):
        _label_with_help(ui, "Examples", "创建真实可运行的产品示例 Work；所有阶段都通过共享 backend service 执行。", "text-lg font-medium")
        ui.label("Desktop 2DOF Robot Arm").classes("font-semibold text-gray-900")
        ui.label("Contract validates CAD IR and creates input_ir without STEP/STL. Full runs CadQuery and generates STEP/STL.").classes("text-sm text-gray-700")
        with ui.row().classes("gap-2"):
            ui.button("Create Contract Example", icon="fact_check", on_click=lambda: _create_golden_example_ui("contract", state, refresh)).tooltip("Run through validated input_ir; CAD execution is intentionally skipped.")
            ui.button("Create Full Example", icon="precision_manufacturing", on_click=lambda: _create_golden_example_ui("full", state, refresh)).tooltip("Run CadQuery and create STEP/STL for one generic concept part.")
        progress = state.get("golden_example_progress") if isinstance(state.get("golden_example_progress"), list) else []
        if progress:
            with ui.expansion("Example progress", value=True).classes("w-full"):
                for event in progress:
                    if isinstance(event, dict):
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.badge(event.get("status") or "unknown").classes(_badge_class(event.get("status")))
                            ui.label(event.get("stage") or "stage").classes("font-medium")
                            ui.label(event.get("message") or "").classes("text-sm text-gray-600")
    _label_with_help(ui, "Works", "当前 workspace 中的 Work/Project 列表，点击一行可进入对应 Work。", "text-lg font-medium")
    _render_work_table(ui, data.get("works") or [], data.get("selected_work_id"), on_select_work)
    selected_work = data.get("selected_work") if isinstance(data.get("selected_work"), dict) else {}
    directory_map = selected_work.get("directory_map") if isinstance(selected_work.get("directory_map"), dict) else {}
    if directory_map:
        _render_work_directory_map(ui, directory_map)


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
        default_path = workspace.get("display_path") or workspace.get("relative_path") or "workspace"
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


def _render_work_overview(ui: Any, data: dict[str, Any], state: dict[str, Any], refresh: Callable[[], None]) -> None:
    work = data.get("selected_work") or {}
    summary = work.get("summary") if isinstance(work.get("summary"), dict) else {}
    entity = work.get("entity_state") if isinstance(work.get("entity_state"), dict) else {}
    current = work.get("current_state") if isinstance(work.get("current_state"), dict) else {}
    workspace_config = data.get("workspace_config") if isinstance(data.get("workspace_config"), dict) else {}
    counts = current.get("part_counts") if isinstance(current.get("part_counts"), dict) else {}
    with ui.grid(columns=4).classes("w-full gap-3"):
        _overview_metric(ui, "Status", summary.get("overall_status") or "incomplete")
        _overview_metric(ui, "Current stage", _friendly_current_stage(work))
        _overview_metric(ui, "Parts", _sidebar_part_count_label(counts))
        _overview_metric(ui, "Mode", entity.get("advancement_mode") or workspace_config.get("advancement_mode") or "manual_confirm")
    with ui.card().classes("w-full shadow-none border border-blue-100 bg-blue-50"):
        ui.label("Next action").classes("text-sm font-medium text-blue-900")
        ui.label(current.get("next_action") or "Inspect workflow.").classes("text-base text-blue-950")
    if entity.get("description"):
        ui.label(entity["description"]).classes("text-sm text-gray-700")
    golden = work.get("golden_example") if isinstance(work.get("golden_example"), dict) else None
    if golden:
        _render_golden_comparison(ui, golden)
    requirement = entity.get("requirement") if isinstance(entity.get("requirement"), dict) else {}
    with ui.card().classes("w-full"):
        _label_with_help(ui, "Requirement", "Work 的需求入口。这里会创建 root run，保存用户输入和后续结构化需求文件。", "text-lg font-medium")
        _key_values(ui, {
            "Status": requirement.get("status") or "not_started",
            "Confirmation": "required" if requirement.get("confirmation_required") else "not required",
        })
        with ui.row().classes("w-full items-start gap-2"):
            prompt = ui.textarea("Requirement input", placeholder="Describe the product/work to start a root workflow run.").props("outlined autogrow").classes("flex-1")
            _help_icon(ui, "输入当前 Work 的原始需求。MVP 不做完整聊天 UI，而是把需求写入 root run 供后续 workflow 使用。")
        button = ui.button("Create Root Run", icon="play_arrow", on_click=lambda: _create_work_requirement_run_ui(summary.get("work_id"), prompt.value, state, refresh))
        button.tooltip("为当前 Work 创建 root run；不会直接批量生成所有 CAD。")
        if not summary.get("work_id"):
            button.disable()
        if state.get("requirement_run_result") is not None:
            with ui.expansion("Action result").classes("w-full"):
                ui.markdown(f"```json\n{json.dumps(state['requirement_run_result'], indent=2, sort_keys=True)}\n```").classes("w-full mono")
    with ui.card().classes("w-full"):
        _label_with_help(ui, "Part Runs", "根据拆分出的 parts 创建每个 part 对应的 run 容器。人工确认模式下需要手动点击。", "text-lg font-medium")
        ui.label("Manual mode creates part runs after you confirm the split; auto mode creates them when split artifacts are available.").classes("text-sm text-gray-600")
        button = ui.button("Confirm Split / Create Part Runs", icon="account_tree", on_click=lambda: _create_work_part_runs_ui(summary.get("work_id"), state, refresh))
        button.tooltip("确认当前 parts split，并为候选 part 创建 run 容器；不会自动执行批量 CAD。")
        if not summary.get("work_id") or not current.get("root_run_id"):
            button.disable()
        if state.get("part_runs_result") is not None:
            with ui.expansion("Action result").classes("w-full"):
                ui.markdown(f"```json\n{json.dumps(state['part_runs_result'], indent=2, sort_keys=True)}\n```").classes("w-full mono")


def _render_works(
    ui: Any,
    data: dict[str, Any],
    state: dict[str, Any],
    on_select: Callable[[str], None],
    refresh: Callable[[], None],
) -> None:
    works = data.get("works") or []
    selected = data.get("selected_work_id")
    with ui.card().classes("w-full"):
        _label_with_help(ui, "Create Work", "创建一个真实 Work/Project 实体，只写 manifest，不启动 provider 或 CAD。", "text-lg font-medium")
        with ui.row().classes("w-full items-center gap-2"):
            title = ui.input("Title").classes("flex-1")
            _help_icon(ui, "Work 的显示标题。会用于生成默认 work_id。")
        with ui.row().classes("w-full items-start gap-2"):
            description = ui.textarea("Description").props("outlined autogrow").classes("flex-1")
            _help_icon(ui, "Work 的简短说明。只保存在 workspace manifest 中。")
        result_key = "create_work_result"
        if state.get(result_key):
            ui.label(str(state[result_key])).classes("text-sm text-gray-600")
        ui.button(
            "Create Work",
            icon="add_circle",
            on_click=lambda: _create_work_ui(title.value, description.value, state, result_key, refresh),
        ).tooltip("创建 Work manifest，不创建 run，不调用 provider。")
    _label_with_help(ui, "Works", "当前 workspace 下的 Work 列表。点击行会切换到该 Work 的 Overview。", "text-xl font-semibold")
    if not works:
        ui.label("No Works in this workspace yet.").classes("text-gray-600")
        return
    _render_work_table(ui, works, selected, on_select)


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
    work = page.get("work") if isinstance(page.get("work"), dict) else {}
    lineage = page.get("active_lineage") if isinstance(page.get("active_lineage"), dict) else {}
    with ui.element("section").classes("workflow-snapshot-banner w-full" if snapshot else "workflow-hero w-full"):
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label("HISTORICAL RUN SNAPSHOT · READ-ONLY" if snapshot else "CURRENT WORK").classes("workflow-eyebrow")
                ui.label(work.get("title") or "Workflow").classes("text-2xl font-semibold")
                if snapshot:
                    ui.label(f"Run {page.get('viewed_run_id')} · immutable audit record").classes("text-sm text-amber-800")
                    ui.label("This snapshot does not represent the complete Current Work.").classes("workflow-summary text-sm text-gray-700")
                else:
                    leaf = lineage.get("active_leaf_run_id") or lineage.get("active_root_run_id") or "unavailable"
                    root = lineage.get("active_root_run_id")
                    ui.label(f"Active lineage: {root} → {leaf}" if root and root != leaf else f"Active lineage: {leaf}").classes("workflow-meta")
                    if page.get("lineage_inferred"):
                        ui.label("Active lineage inferred from legacy Work metadata.").classes("text-sm text-amber-800")
            with ui.row().classes("gap-2"):
                current = ui.button("Current Work", on_click=on_select_current_work).props("dense")
                current.tooltip("Show the actionable Current Work lineage. This does not modify any Run or artifact.")
                if not snapshot:
                    current.props("color=primary")
                if snapshot:
                    ui.button("Return to Current Work", icon="undo", on_click=on_select_current_work).props("outline dense") \
                        .tooltip("Leave this read-only historical Run and return to the actionable Current Work lineage.")
    if snapshot:
        with ui.element("section").classes("workflow-run-strip-panel w-full"):
            _render_run_strip(ui, page.get("run_strip"), on_select_run, on_select_current_work)
    conclusion = page.get("current_conclusion") if isinstance(page.get("current_conclusion"), dict) else {}
    with ui.element("section").classes("workflow-hero w-full"):
        ui.label("CURRENT CONCLUSION" if not snapshot else "SNAPSHOT CONCLUSION").classes("workflow-eyebrow")
        ui.label(conclusion.get("title") or "Current result").classes("text-xl font-semibold")
        ui.label(conclusion.get("summary") or "Inspect the selected workflow stage.").classes("workflow-summary text-sm text-gray-700")
        if conclusion.get("rationale"):
            ui.label(conclusion["rationale"]).classes("workflow-meta")
        action = page.get("recommended_next_action") if isinstance(page.get("recommended_next_action"), dict) else None
        if action and action.get("enabled"):
            ui.button(action.get("label") or action.get("key"), on_click=lambda a=action: _run_workflow_page_action(ui, actions, a, state, refresh)).props("color=primary") \
                .tooltip(action.get("tooltip") or "Run the recommended workflow action.")
    if not snapshot:
        with ui.element("section").classes("workflow-run-strip-panel w-full"):
            _render_run_strip(ui, page.get("run_strip"), on_select_run, on_select_current_work)
    _render_workflow_stage_graph(
        ui,
        {"workflow_graph": page.get("workflow_graph"), "selected_stage_id": _dict_get(page.get("selected_stage"), "stage_id")},
        on_select_stage,
        on_open_candidate=lambda candidate: _show_candidate_detail(
            ui, candidate, data, actions, state, refresh, read_only=snapshot
        ),
    )
    _render_selected_stage_detail_v2(ui, page.get("selected_stage"), data, actions, state, refresh, snapshot)


def _render_run_strip(ui: Any, runs: Any, on_select_run: Callable[[str], None], on_select_current_work: Callable[[], None]) -> None:
    ui.label("RUN LINEAGE").classes("workflow-eyebrow")
    with ui.row().classes("workflow-run-strip w-full"):
        with ui.row().classes("workflow-run-strip-inner gap-2 no-wrap"):
            current = ui.column().classes("workflow-run-item workflow-run-current gap-1")
            current.on("click", lambda _event: on_select_current_work())
            with current:
                ui.label("Current Work").classes("text-sm font-semibold")
                ui.label("Active aggregated lineage").classes("workflow-run-state text-blue-700")
                ui.label("Actionable workflow view").classes("text-xs text-gray-500")
            for run in runs if isinstance(runs, list) else []:
                if not isinstance(run, dict):
                    continue
                state = str(run.get("lineage_state") or "historical")
                classes = "workflow-run-item gap-1" + (" workflow-run-current" if run.get("is_current") else "") + (" workflow-run-failed" if state == "failed_branch" else "")
                item = ui.column().classes(classes)
                item.on("click", lambda _event, run_id=run.get("run_id"): on_select_run(str(run_id)))
                with item:
                    ui.label(run.get("display_label") or run.get("run_id") or "Run").classes("text-sm font-medium")
                    ui.label(state.replace("_", " ")).classes("workflow-run-state")
                    ui.label(str(run.get("status") or "unknown").replace("_", " ")).classes("text-xs text-gray-600")
                    ui.label(run.get("summary") or "Immutable workflow attempt.").classes("text-xs text-gray-500")
                    if run.get("parent_run_id"):
                        ui.label(f"Parent: {run['parent_run_id']}").classes("workflow-meta")


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
    with ui.element("section").classes("workflow-stage-detail-v2 w-full"):
        notice = state.pop("workflow_notice", None)
        if notice:
            ui.label(str(notice)).classes("text-sm text-green-700")
        with ui.row().classes("stage-conclusion w-full items-start justify-between gap-3"):
            with ui.column().classes("gap-1"):
                ui.label("SELECTED STAGE CONCLUSION").classes("workflow-eyebrow")
                ui.label(conclusion.get("title") or stage.get("stage_name") or stage.get("stage_id")).classes("text-xl font-semibold")
                ui.label(conclusion.get("summary") or stage.get("short_summary") or "Stage data unavailable.").classes("text-sm text-gray-700")
                ui.label(f"Source Run: {stage.get('source_run_id') or 'Work lineage'}" + (f" · Selected part: {stage.get('selected_part_id')}" if stage.get("selected_part_id") else "")).classes("workflow-meta")
            ui.badge(str(stage.get("status") or "unavailable").replace("_", " ")).classes(_badge_class(stage.get("status")))
        action = stage.get("primary_action") if isinstance(stage.get("primary_action"), dict) else None
        if action:
            ui.label(f"Recommended action: {action.get('label') or action.get('key')}").classes("workflow-meta")
            if not action.get("enabled"):
                ui.label(action.get("disabled_reason") or "Unavailable").classes("workflow-disabled-reason")
        with ui.element("div").classes("stage-detail-grid w-full"):
            _render_stage_contract_block(ui, "USER INPUT", stage.get("user_input"), read_only, actions.backend, state)
            _render_stage_contract_block(ui, "AGENT INTERPRETATION / DECISION", stage.get("agent_decision"), read_only, actions.backend, state)
            _render_stage_contract_block(ui, "AGENT OUTPUT", stage.get("agent_output"), read_only, actions.backend, state)
        _render_agent_review_panel(ui, stage, data, actions, state, refresh, read_only)
        _render_stage_review_panel(ui, stage, data, actions, state, refresh, read_only)
        if stage.get("stage_id") in {"requirement", "clarification"} and not read_only:
            _render_inline_requirement_clarification(ui, data, actions, state, refresh)
        secondary = stage.get("secondary_actions") if isinstance(stage.get("secondary_actions"), list) else []
        if secondary:
            ui.label("Secondary actions").classes("text-sm font-medium text-gray-600")
            with ui.row().classes("gap-2 flex-wrap"):
                for action in secondary:
                    button = ui.button(action.get("label") or action.get("key"), on_click=lambda a=action: _run_workflow_page_action(ui, actions, a, state, refresh)).props("outline dense")
                    button.tooltip(action.get("tooltip") or action.get("disabled_reason") or "Available")
                    if not action.get("enabled"):
                        button.disable()
        disabled_actions = stage.get("disabled_actions") if isinstance(stage.get("disabled_actions"), list) else []
        if disabled_actions:
            ui.label("Unavailable actions").classes("text-xs font-medium text-gray-500")
            with ui.row().classes("gap-2 flex-wrap"):
                for action in disabled_actions:
                    if isinstance(action, dict):
                        button = ui.button(action.get("label") or action.get("key")).props("outline dense")
                        button.disable()
                        button.tooltip(action.get("tooltip") or action.get("disabled_reason") or "Unavailable")
        evidence = stage.get("evidence") if isinstance(stage.get("evidence"), list) else []
        with ui.element("section").classes("workflow-evidence w-full"):
            ui.label("EVIDENCE").classes("workflow-eyebrow")
            if evidence:
                _render_stage_artifact_rows(ui, evidence, actions.backend, state, compact=True)
            else:
                ui.label("No additional evidence is available.").classes("text-sm text-gray-700")
        with ui.expansion("Advanced", icon="info").classes("w-full"):
            ui.label("Raw artifacts and diagnostics remain secondary to this stage summary.").classes("text-sm text-gray-500")


def _render_stage_contract_block(
    ui: Any,
    title: str,
    value: Any,
    read_only: bool,
    backend: WorkflowConsoleBackend | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    item = value if isinstance(value, dict) else {}
    classes = "stage-detail-card decision" if "DECISION" in title else "stage-detail-card"
    with ui.element("section").classes(classes):
        ui.html(f"<h3>{title}</h3>")
        ui.label(item.get("summary") or "No data is available for this stage section.").classes("text-sm text-gray-800")
        source = item.get("source_run_id")
        stage = item.get("source_stage_id")
        if source or stage:
            ui.label(f"Source: {source or 'Work lineage'}" + (f" · {stage}" if stage else "")).classes("text-xs text-gray-500")
        if title == "USER INPUT":
            ui.label("Read-only snapshot" if read_only else ("Active override" if item.get("source_type") == "active_override" else "Accepted input")).classes("text-xs text-gray-500")
            if item.get("stale_downstream"):
                ui.label("This active override may make downstream stages stale.").classes("text-xs text-amber-800")
        if title == "AGENT OUTPUT" and item.get("step_stl_expectation") == "not_expected":
            ui.label("CAD IR validated · execution skipped · STEP/STL not expected").classes("text-xs text-gray-600")
        for key, label in (("decisions", "Key decisions"), ("assumptions", "Assumptions"), ("artifacts", "Artifacts")):
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
                on_click=lambda a=primary: _run_workflow_page_action(ui, actions, a, state, refresh),
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
    review_stage = {"reviewed_handoff": "handoff", "part_result_review": "single_part_result"}.get(stage_id, stage_id)
    page = data.get("workflow_page") if isinstance(data.get("workflow_page"), dict) else {}
    target_run = page.get("active_lineage", {}).get("active_root_run_id") if isinstance(page.get("active_lineage"), dict) else None
    with ui.element("section").classes("workflow-evidence w-full"):
        ui.label("STAGE REVIEW").classes("workflow-eyebrow")
        ui.label(
            f"Review target: Run {target_run or 'unavailable'} · {review_stage}. Reviews are append-only; the latest compatible stage_review.json remains available to Rework."
        ).classes("text-sm text-gray-700")
        if read_only or not target_run:
            ui.label("This historical Run is read-only; return to Current Work to save a review.").classes("workflow-disabled-reason")
            return
        status = ui.select(["approved", "needs_revision", "blocked"], value="approved", label="Review status").props("outlined dense").classes("w-full")
        notes = ui.textarea("Notes / blocked reason").props("outlined autogrow").classes("w-full")
        changes = ui.textarea("Requested changes (required for Needs Revision)").props("outlined autogrow").classes("w-full")
        rework_target = ui.select(
            ["requirement", "design_brief", "assembly_plan", "candidate_parts", "part_request", "part_review", "handoff", "single_part_result", "workflow_review"],
            value="workflow_review",
            label="Target rework stage",
        ).props("outlined dense").classes("w-full")
        with ui.row().classes("gap-2 flex-wrap"):
            save = ui.button(
                "Save Stage Review",
                on_click=lambda: _save_stage_review_from_form(
                    actions, target_run, review_stage, status.value, notes.value, changes.value, rework_target.value, state, refresh
                ),
            ).props("color=primary")
            save.tooltip(
                f"Save an append-only review for Current Work · Run {target_run} · {review_stage}. It does not create a Run or overwrite original artifacts."
            )
            quick = ui.button(
                "Quick Approve",
                on_click=lambda: _save_stage_review_from_form(
                    actions, target_run, review_stage, "approved", None, None, None, state, refresh
                ),
            ).props("outline")
            quick.tooltip(
                f"Immediately save Approved for Current Work · Run {target_run} · {review_stage}, without notes. No Run is created and existing artifacts remain unchanged."
            )


def _save_stage_review_from_form(
    actions: WorkflowConsoleActions,
    run_id: str,
    stage: str,
    review_status: Any,
    notes: Any,
    changes: Any,
    rework_target: Any,
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    try:
        result = actions.save_stage_review(
            run_id,
            stage=stage,
            review_status=str(review_status),
            user_notes=str(notes or ""),
            requested_changes=str(changes or ""),
            target_rework_stage=str(rework_target) if rework_target else None,
        )
        state["surface_action_result"] = result
        state["workflow_notice"] = f"Stage Review saved as {review_status}; {result.get('review_id')} is retained in review history."
    except Exception as exc:
        state["workflow_notice"] = f"Stage Review could not be saved: {exc}"
    refresh()


def _render_stage_artifact_rows(
    ui: Any,
    artifacts: list[dict[str, Any]],
    backend: WorkflowConsoleBackend,
    state: dict[str, Any],
    *,
    compact: bool,
) -> None:
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        with ui.row().classes("w-full items-center justify-between gap-2"):
            with ui.column().classes("gap-0"):
                ui.label(artifact.get("display_name") or artifact.get("name") or "Artifact").classes("text-sm font-medium")
                ui.label(
                    f"{artifact.get('kind', 'file').upper()} · {artifact.get('validation_status') or 'available'} · "
                    f"Source: {artifact.get('source_run_id') or 'Work lineage'} · {artifact.get('source_stage_id') or 'stage'}"
                ).classes("workflow-meta")
                if artifact.get("summary") and not compact:
                    ui.label(str(artifact["summary"])).classes("text-xs text-gray-600")
            with ui.row().classes("gap-1"):
                open_button = ui.button("Open", on_click=lambda a=artifact: _show_artifact_contract_dialog(ui, backend, a, state)).props("outline dense")
                open_button.tooltip("Open the exact artifact shown here, including its source Run and stage. This does not change the workflow.")
                copy_button = ui.button("Copy", on_click=lambda a=artifact: _copy_artifact_raw(ui, a)).props("flat dense")
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
    _run_surface_action(actions, target, action, state, refresh)


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
            button = ui.button("查看摘要" if language == "zh" else "View summary", icon="visibility", on_click=lambda a=artifact: _show_artifact_summary_dialog(ui, a, language)).props("outline dense")
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
            preview = ui.button(icon="visibility", on_click=lambda a=artifact: _show_artifact_summary_dialog(ui, a, language)).props("flat round dense")
        else:
            preview = ui.button(artifact.get("display_name") or name, icon="visibility", on_click=lambda a=artifact: _show_artifact_summary_dialog(ui, a, language)).props("outline dense")
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
    on_open_candidate: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    graph = surface.get("workflow_graph") if isinstance(surface.get("workflow_graph"), dict) else {}
    selected = surface.get("selected_stage_id")
    if not graph:
        _render_graph_stage_row(ui, surface.get("graph_nodes") or [], selected, on_select_stage)
        return
    with ui.column().classes("workflow-graph w-full gap-4"):
        with ui.column().classes("workflow-graph-canvas gap-4"):
            ui.label("DOT WORKFLOW GRAPH").classes("workflow-graph-label")
            _render_graph_stage_row(ui, graph.get("stage_spine") or [], selected, on_select_stage)
            ui.label("Assembly Plan branches into candidates and reference context").classes("workflow-branch-note")
            candidates = graph.get("part_candidates") if isinstance(graph.get("part_candidates"), list) else []
            with ui.column().classes("workflow-lane gap-2"):
                ui.label("CANDIDATE PARTS").classes("workflow-graph-label")
                if candidates:
                    with ui.row().classes("workflow-lane-row"):
                        for candidate in candidates:
                            _render_part_candidate_node(ui, candidate, on_open_candidate)
                else:
                    ui.label("No generated part candidates have been identified yet.").classes("text-sm text-gray-500")
            references = graph.get("reference_lane") if isinstance(graph.get("reference_lane"), list) else []
            if references:
                with ui.column().classes("workflow-lane gap-2"):
                    ui.label("REFERENCE COMPONENTS").classes("workflow-graph-label")
                    with ui.row().classes("workflow-lane-row"):
                        for candidate in references:
                            _render_part_candidate_node(ui, candidate, on_open_candidate)
            selected_part = graph.get("selected_part_id") or "a selected candidate"
            ui.label(f"SELECTED PART PIPELINE · {selected_part}").classes("workflow-graph-label")
            _render_graph_stage_row(ui, graph.get("selected_part_pipeline") or [], selected, on_select_stage)
            tail = graph.get("review_tail") if isinstance(graph.get("review_tail"), list) else []
            if tail:
                ui.label("WORKFLOW REVIEW / REWORK").classes("workflow-graph-label")
                _render_graph_stage_row(ui, tail, selected, on_select_stage)


def _render_graph_stage_row(ui: Any, nodes: list[dict[str, Any]], selected: Any, on_select_stage: Callable[[str], None]) -> None:
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
                ui.label(node.get("label") or stage_id).classes("text-sm font-semibold text-center")
                ui.label(str(status).replace("_", " ")).classes("workflow-node-status text-center")
                if node.get("attention") not in {None, "none"}:
                    ui.label("attention required" if node.get("attention") == "required" else "in progress").classes("workflow-attention")
                if node.get("has_override"):
                    ui.label("override active").classes("workflow-attention")
            if index < len(nodes) - 1:
                ui.element("div").classes("workflow-connector")


def _render_part_candidate_node(ui: Any, candidate: dict[str, Any], on_open_candidate: Callable[[dict[str, Any]], None] | None) -> None:
    status = str(candidate.get("status") or "candidate")
    classes = "workflow-step workflow-part-candidate" + (" reference-component" if candidate.get("kind") == "reference_component" or candidate.get("reference_only") else "")
    if candidate.get("selected"):
        classes += " workflow-step-selected"
    node = ui.column().classes(classes)
    node.tooltip("Open Candidate Detail\n\nTarget: current Work · Assembly Plan\n\nResult: inspect this candidate; it does not change selection or active lineage.")
    if on_open_candidate is not None:
        node.on("click", lambda _event, value=dict(candidate): on_open_candidate(value))
    with node:
        ui.element("div").classes(f"workflow-dot status-{_dot_status(status)} kind-{candidate.get('kind') or 'candidate_part'}")
        ui.label(candidate.get("part_id") or "part").classes("text-sm font-semibold text-center")
        ui.label("reference-only" if candidate.get("reference_only") else (candidate.get("role") or "assembly component")).classes("text-xs text-gray-500 text-center")
        ui.label(status.replace("_", " ")).classes("workflow-node-status")
        if candidate.get("supported_candidate"):
            ui.label("supported candidate").classes("text-xs text-green-700 text-center")


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
    with ui.dialog() as dialog, ui.card().classes("w-[620px] max-w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Candidate Detail").classes("text-lg font-semibold")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense").tooltip("Close Candidate Detail without changing the selected part.")
        fields = (
            ("Part", candidate.get("part_id")), ("Role", candidate.get("role")),
            ("Brief", candidate.get("short_summary")), ("Status", candidate.get("status")),
            ("Generation strategy", candidate.get("generation_strategy")),
            ("Supported candidate", candidate.get("supported_candidate")),
            ("Reference only", candidate.get("reference_only")), ("Selected", candidate.get("selected")),
            ("Source Run", candidate.get("source_run_id")),
        )
        for label, value in fields:
            ui.label(f"{label}: {value if value not in (None, '') else 'Not available'}").classes("text-sm")
        selection_action = _candidate_selection_action(candidate, data, read_only)
        button = ui.button(
            selection_action["label"],
            on_click=lambda a=selection_action: _show_candidate_selection_confirmation(
                ui, dialog, a, candidate, actions, state, refresh
            ),
        ).props("outline dense")
        button.tooltip(selection_action["tooltip"])
        if not selection_action["enabled"]:
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
    if read_only:
        disabled_reason = "Run Snapshot is read-only. Return to Current Work to select a candidate."
    elif reference:
        disabled_reason = "Reference components are context only and cannot be selected for generation."
    elif not supported:
        disabled_reason = "This candidate is not supported by the current single-part workflow."
    elif current:
        disabled_reason = "This candidate is already selected; no duplicate override is needed."
    else:
        disabled_reason = None
    target_run = lineage.get("active_root_run_id") or candidate.get("source_run_id")
    target = f"Current Work · Run {target_run or 'unavailable'} · Assembly Plan"
    return {
        "key": "select_candidate_part",
        "label": "Use This Part Next",
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
            "Select this candidate for the next Part Request through a validated, versioned Assembly Plan override.",
            "",
            f"Target: {target}",
            "",
            "Result: preserves the original plan and old Runs, marks downstream stages stale, and recommends Create Part Request.",
            "Active lineage changes: no",
            "New Run: no",
            *(["", f"Currently unavailable: {disabled_reason}"] if disabled_reason else []),
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
    with ui.dialog() as confirm, ui.card().classes("w-[620px] max-w-full"):
        ui.label("Confirm candidate selection").classes("text-lg font-semibold")
        ui.label(f"Current selected candidate: {candidate.get('current_selected_part_id') or 'current Assembly Plan selection'}").classes("text-sm")
        ui.label(f"New candidate: {action.get('part_id')}").classes("text-sm")
        ui.label("The following stages become stale: Part Request, Part Review, Reviewed Handoff, CAD IR Draft, Part Modeling, Part Result Review, and Workflow Review.").classes("text-sm")
        ui.label("Old Runs and accepted part results are retained. CAD generation will not start automatically.").classes("text-sm text-gray-700")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancel", on_click=confirm.close).props("flat") \
                .tooltip("Cancel without changing the Assembly Plan override or Work pointers.")
            ui.button(
                "Confirm selection",
                on_click=lambda: _apply_candidate_selection(
                    action, actions, state, refresh, confirm, detail_dialog
                ),
            ).props("color=primary") \
                .tooltip("Write the validated versioned Assembly Plan override and refresh the Current Work view.")
    confirm.open()


def _apply_candidate_selection(
    action: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    confirm: Any,
    detail_dialog: Any,
) -> None:
    try:
        result = actions.select_candidate_part(
            str(action["target_run_id"]), work_id=str(action["target_work_id"]), part_id=str(action["part_id"])
        )
        state["candidate_selection_result"] = result
        state["selected_stage_id"] = "part_request"
        state["workflow_notice"] = "Candidate selection saved. Downstream stages are stale; Create Part Request is the recommended next step."
        confirm.close()
        detail_dialog.close()
    except Exception as exc:
        state["workflow_notice"] = f"Candidate selection could not be completed: {exc}"
    refresh()


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
                on_click=lambda a=action: _run_detail_action(ui, actions, data, a, state, refresh),
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
    _run_surface_action(actions, run_id, action, state, refresh)


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
                    on_click=lambda a=action: _run_surface_action(actions, a.get("target_run_id") or data.get("selected_run_id"), a, state, refresh),
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


def _run_surface_action(
    actions: WorkflowConsoleActions,
    run_id: str | None,
    action: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
) -> None:
    if not run_id:
        state["surface_action_result"] = {"ok": False, "error": "Select a run first."}
        refresh()
        return
    backend_action = action.get("backend_action")
    try:
        if backend_action == "save_stage_review":
            state["surface_action_result"] = actions.save_stage_review(
                run_id,
                stage=action.get("stage") or "workflow_review",
                review_status=action.get("review_status") or "approved",
            )
        elif backend_action == "part_request":
            state["surface_action_result"] = actions.create_part_request(run_id)
        elif backend_action == "part_review":
            state["surface_action_result"] = actions.review_part_request(run_id)
        elif backend_action == "reviewed_handoff":
            state["surface_action_result"] = actions.create_reviewed_handoff(run_id)
        elif backend_action == "reviewed_part_create":
            state["surface_action_result"] = actions.create_reviewed_part(run_id)
        elif backend_action == "part_result_review":
            state["surface_action_result"] = actions.review_part_result(run_id)
        elif backend_action == "approve_part_result":
            work_id = action.get("target_work_id")
            if not isinstance(work_id, str):
                raise ValueError("Approve Single Part Result requires a target Work")
            state["surface_action_result"] = actions.approve_part_result(run_id, work_id=work_id)
        elif backend_action == "create_workflow_review":
            state["surface_action_result"] = actions.create_workflow_review(run_id)
        elif backend_action == "run_rework":
            state["surface_action_result"] = actions.run_rework(run_id)
            result = state["surface_action_result"]
            decision = result.get("decision") if isinstance(result, dict) and isinstance(result.get("decision"), dict) else {}
            child_run_id = decision.get("child_run_id")
            target_work_id = action.get("target_work_id")
            if result.get("stage_count") and isinstance(target_work_id, str) and isinstance(child_run_id, str):
                actions.backend.activate_work_lineage(
                    target_work_id,
                    parent_run_id=run_id,
                    child_run_id=child_run_id,
                )
        else:
            state["surface_action_result"] = {"ok": False, "error": f"Unsupported surface action: {action.get('key')}"}
    except Exception as exc:
        state["surface_action_result"] = {"ok": False, "error": str(exc)}
    result = state.get("surface_action_result")
    if isinstance(result, dict) and not result.get("error") and action.get("next_stage_on_success"):
        state["selected_stage_id"] = action["next_stage_on_success"]
    state["workflow_notice"] = (
        "Workflow action could not be completed: " + str(result.get("error"))
        if isinstance(result, dict) and result.get("error")
        else "Workflow updated. The selected stage now reflects the latest agent output."
    )
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
                ui.button("Open node", icon="open_in_new", on_click=lambda n=node: on_select_node(n["id"])).props("outline").tooltip("打开该节点详情，查看输入文件、输出文件、启动条件和 review/rework 操作。")


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
    with ui.card().classes("w-full"):
        _label_with_help(ui, "Work Products", "优先展示面向用户的产物和下载文件，调试类 artifact 默认折叠或隐藏。", "text-xl font-semibold")
        if downloads:
            for item in downloads:
                ui.badge(f"{item.get('name')}: available")
        else:
            ui.label("No downloadable Work products found.").classes("text-sm text-gray-500")
        ui.label("Human-facing artifacts").classes("font-medium")
        if not human:
            ui.label("Empty").classes("text-sm text-gray-500")
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
    config = data.get("provider_config") if isinstance(data.get("provider_config"), dict) else {}
    identity = config.get("provider_identity") if isinstance(config.get("provider_identity"), dict) else {}
    workspace_config = data.get("workspace_config") if isinstance(data.get("workspace_config"), dict) else {}
    with ui.card().classes("w-full"):
        _label_with_help(ui, "Workspace Configuration", "当前 workspace 级配置。这里只保存 provider、模型、超时、重试和推进模式，不保存 API key。", "text-xl font-semibold")
        _key_values(ui, {
            "Provider": workspace_config.get("provider") or identity.get("provider") or "local/mock",
            "Model": workspace_config.get("model") or identity.get("model") or "Empty",
            "Timeout": workspace_config.get("timeout_seconds") or identity.get("timeout_seconds") or "Empty",
            "Retries": workspace_config.get("max_retries") if workspace_config.get("max_retries") is not None else "Empty",
            "Advancement mode": workspace_config.get("advancement_mode") or "manual_confirm",
            "API keys": "Read from environment only; never shown or saved here.",
        })
        with ui.row().classes("w-full items-center gap-2"):
            provider = ui.select(options=["local", "deepseek", "openai"], value=_provider_select_value(workspace_config or identity), label="Provider").classes("flex-1")
            _help_icon(ui, "选择当前 workspace 使用的 provider。local 用于本地/mock；deepseek/openai 需要环境变量中已有 API key。")
        with ui.row().classes("w-full items-center gap-2"):
            mode = ui.select(options=["manual_confirm", "auto_advance"], value=workspace_config.get("advancement_mode") or "manual_confirm", label="Advancement mode").classes("flex-1")
            _help_icon(ui, "manual_confirm 会等待人工确认再推进 part runs；auto_advance 在满足输入条件后自动创建下一步 run 容器。")
        with ui.row().classes("w-full items-center gap-2"):
            model = ui.input("Model", value=str(workspace_config.get("model") or "")).classes("flex-1")
            _help_icon(ui, "provider 使用的模型名称。留空时使用后端默认模型或环境配置。")
        with ui.row().classes("w-full items-center gap-2"):
            timeout = ui.number("Timeout seconds", value=workspace_config.get("timeout_seconds") or None, min=1, max=300).classes("flex-1")
            _help_icon(ui, "单次 provider 请求的超时时间，单位是秒。")
        with ui.row().classes("w-full items-center gap-2"):
            retries = ui.number("Max retries", value=workspace_config.get("max_retries") if workspace_config.get("max_retries") is not None else None, min=0, max=5).classes("flex-1")
            _help_icon(ui, "provider 请求失败时的最大重试次数。")
        with ui.row().classes("gap-2"):
            ui.button("Save", icon="save", on_click=lambda: _save_workspace_config_ui(backend, provider.value, mode.value, model.value, timeout.value, retries.value, state, refresh)).tooltip("保存 workspace 级配置到 config.json，不写入 API key。")
            ui.button("Test", icon="check_circle", on_click=lambda: _test_provider_ui(backend, state, refresh)).props("outline").tooltip("使用当前配置测试 provider 连接；API key 仍只从环境变量读取。")
        if state.get("config_result") is not None:
            ui.markdown(f"```json\n{json.dumps(state['config_result'], indent=2, sort_keys=True)}\n```").classes("w-full mono")


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
    available = len(downloads) + len(human)
    return {
        "id": "result",
        "label": "Result / Downloads",
        "kind": "summary",
        "status": "available" if available else "not_started",
        "summary": f"{available} user-facing outputs or files." if available else "Products and run history will appear here.",
        "artifacts": [item.get("name") for item in human if isinstance(item, dict) and item.get("name")],
        "actions": ["open_products", "open_runs"],
    }


def _graph_single_part_node(work: dict[str, Any]) -> dict[str, Any] | None:
    summary = work.get("summary") if isinstance(work.get("summary"), dict) else {}
    products = work.get("products") if isinstance(work.get("products"), dict) else {}
    downloads = products.get("downloadables") if isinstance(products.get("downloadables"), list) else []
    if not downloads and summary.get("overall_status") not in {"accepted", "completed"}:
        return None
    names = {item.get("name") for item in downloads if isinstance(item, dict)}
    artifacts = [name for name in ("model.step", "model.stl", "preview.png") if name in names]
    return {
        "id": "single_part",
        "label": "Single Part",
        "kind": "part",
        "status": summary.get("overall_status") or "completed",
        "summary": "Single-part output is available.",
        "artifacts": artifacts,
        "actions": [],
        "part_id": "single_part",
        "role": "single_part",
        "current_stage": "outputs",
        "has_step": "model.step" in names,
        "has_stl": "model.stl" in names,
        "has_preview": "preview.png" in names,
        "download_run_id": summary.get("latest_run_id") or summary.get("root_run_id"),
        "next_action": "View products",
        "review_status": summary.get("review_status") or summary.get("overall_status"),
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
    if value in {"completed", "contract_complete", "execution_skipped", "skipped", "unavailable", "user_modified", "stale", "accepted", "available", "ready", "running", "needs_review", "partial_success", "blocked", "reference_only", "not_started", "incomplete", "candidate", "selected", "generated", "failed"}:
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
    human = products.get("human_facing") if isinstance(products.get("human_facing"), list) else []
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
    if status in {"needs_review", "partial_success"}:
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
            button = ui.button(card["action_label"], on_click=lambda c=card: _run_ui_action(actions, run_id, c, state, refresh))
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
) -> None:
    if run_id is None or not artifact:
        state[result_key] = {"ok": False, "error": "Select a run and artifact first."}
        refresh()
        return
    try:
        content = json.loads(raw_json or "{}")
    except json.JSONDecodeError as exc:
        state[result_key] = {
            "ok": False,
            "error": "invalid JSON",
            "diagnostic_code": "artifact_override.invalid_json",
            "detail": str(exc),
        }
        refresh()
        return
    if not isinstance(content, dict):
        state[result_key] = {
            "ok": False,
            "error": "override JSON must be an object",
            "diagnostic_code": "artifact_override.not_object",
        }
        refresh()
        return
    try:
        state[result_key] = actions.backend.write_artifact_by_id(
            run_id,
            artifact,
            content,
            edit_reason=edit_reason,
        )
    except Exception as exc:
        state[result_key] = {
            "ok": False,
            "error": str(exc),
            "diagnostic_code": "artifact_override.validation_failed",
        }
    refresh()


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
