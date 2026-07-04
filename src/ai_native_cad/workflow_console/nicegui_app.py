"""NiceGUI shell for the local reviewed-part workflow console.

The module keeps data shaping independent from NiceGUI so tests can exercise
the privacy and gating behavior without browser automation or the optional UI
dependency.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable

from ai_native_cad.workflow_console.actions import WorkflowConsoleActions
from ai_native_cad.workflow_console.actions import STAGE_REVIEW_STATUSES, STAGE_REVIEW_STAGES, STAGE_REWORK_TARGETS
from ai_native_cad.workflow_console.artifact_display import filter_artifacts_for_display
from ai_native_cad.workflow_console.backend import DOWNLOADABLE_FILES, WorkflowConsoleBackend
from ai_native_cad.workflow_console.routes import dispatch_route
from ai_native_cad.workflow_console.stage_runner import READABLE_ARTIFACTS

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8780
DEFAULT_RUN_PAGE_SIZE = 50

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
    "part_result_review.json",
    "stage_review.json",
    "lineage.json",
    "agent_trace.json",
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
    root: str | None = None,
    limit: int = DEFAULT_RUN_PAGE_SIZE,
    offset: int = 0,
    search: str | None = None,
) -> dict[str, Any]:
    """Build path-free data for the NiceGUI console pages."""
    backend = backend or WorkflowConsoleBackend()
    runs_response = dispatch_route(backend, "list_runs", query=_query(root, limit=limit, offset=offset, search=search))
    runs_page = runs_response["data"] if runs_response["ok"] and isinstance(runs_response["data"], dict) else {}
    runs = runs_page.get("runs") if isinstance(runs_page.get("runs"), list) else []
    pagination = runs_page.get("pagination") if isinstance(runs_page.get("pagination"), dict) else _empty_pagination(limit, offset)
    selected = selected_run_id or (runs[0]["run_id"] if runs else None)
    run_data = build_selected_run_data(backend, selected, root=root) if selected else empty_selected_run_data()
    return {
        "runs": runs,
        "pagination": pagination,
        "run_filters": runs_page.get("filters") if isinstance(runs_page.get("filters"), dict) else {},
        "selected_run_id": selected,
        **run_data,
    }


def build_selected_run_data(
    backend: WorkflowConsoleBackend,
    run_id: str,
    *,
    root: str | None = None,
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
    prompt = _read_public_artifact_content(backend, run_id, "prompt.txt", root=root)

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
    return {
        "saved": summary if summary.get("present") else None,
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
        and (item.get("name") in ARTIFACT_PAGE_ARTIFACTS or item.get("name") in {"planning_artifact.json", "input_ir.json"})
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
    if artifact not in READABLE_ARTIFACTS or artifact not in set(ARTIFACT_PAGE_ARTIFACTS) | {"planning_artifact.json", "input_ir.json"}:
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
    except ImportError as exc:  # pragma: no cover - exercised only without optional dependency at runtime
        raise RuntimeError("NiceGUI is not installed. Install the web extra, for example: cadflow[web].") from exc

    console_backend = backend or WorkflowConsoleBackend()
    actions = WorkflowConsoleActions(console_backend)
    state: dict[str, Any] = {"selected_run_id": None, "last_action_result": None}

    @ui.page("/")
    def index() -> None:
        ui.add_head_html("<style>body{background:#f7f8fa}.mono{font-family:ui-monospace, SFMono-Regular, Consolas, monospace}</style>")
        with ui.column().classes("w-full max-w-7xl mx-auto gap-4 p-4"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("CadFlow Workflow Console").classes("text-2xl font-semibold")
                ui.button("Refresh", icon="refresh", on_click=lambda: refresh()).props("outline")
            ui.label("Local NiceGUI shell for reviewed-part workflow actions.").classes("text-sm text-gray-600")
            tabs = ui.tabs().classes("w-full")
            with tabs:
                ui.tab("Runs")
                ui.tab("Review Report")
                ui.tab("Requirement Review")
                ui.tab("Assembly Plan")
                ui.tab("Part Workflow")
                ui.tab("Artifacts")
            panels = ui.tab_panels(tabs, value="Runs").classes("w-full")

            def refresh() -> None:
                panels.clear()
                data = build_console_page_data(
                    console_backend,
                    state.get("selected_run_id"),
                    limit=state.get("limit", DEFAULT_RUN_PAGE_SIZE),
                    offset=state.get("offset", 0),
                    search=state.get("search") or None,
                )
                state["selected_run_id"] = data.get("selected_run_id")
                with panels:
                    with ui.tab_panel("Runs"):
                        _render_runs(ui, data, state, lambda run_id: select_run(run_id), refresh)
                    with ui.tab_panel("Review Report"):
                        _render_workflow_review(ui, data, actions, state, refresh)
                    with ui.tab_panel("Requirement Review"):
                        _render_requirement_review(ui, data, actions, state, refresh)
                    with ui.tab_panel("Assembly Plan"):
                        _render_assembly_plan(ui, data, actions, state, refresh)
                    with ui.tab_panel("Part Workflow"):
                        _render_part_workflow(ui, data, actions, state, refresh)
                    with ui.tab_panel("Artifacts"):
                        _render_artifacts(ui, data, console_backend)

            def select_run(run_id: str) -> None:
                state["selected_run_id"] = run_id
                refresh()

            refresh()

    return app


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
    with ui.row().classes("w-full items-end gap-3"):
        search = ui.input("Search runs", value=state.get("search") or "").props("clearable").classes("w-72")
        page_size = ui.select(options=[25, 50, 100], value=state.get("limit", DEFAULT_RUN_PAGE_SIZE), label="Page size").classes("w-36")
        ui.button("Apply", icon="search", on_click=lambda: _apply_run_filters(state, search.value, page_size.value, refresh)).props("outline")
        previous_button = ui.button("Previous", icon="chevron_left", on_click=lambda: _change_run_page(state, -1, pagination, refresh)).props("outline")
        next_button = ui.button("Next", icon="chevron_right", on_click=lambda: _change_run_page(state, 1, pagination, refresh)).props("outline")
        ui.label(
            f"{pagination.get('offset', 0) + 1 if pagination.get('returned') else 0}-"
            f"{pagination.get('offset', 0) + pagination.get('returned', 0)} of {pagination.get('total', 0)}"
        ).classes("text-sm text-gray-600")
        if not pagination.get("has_previous"):
            previous_button.disable()
        if not pagination.get("has_next"):
            next_button.disable()
    if not runs:
        ui.label("No workflow runs found.").classes("text-gray-600")
        return
    columns = [
        {"name": "run_id", "label": "Run", "field": "run_id", "align": "left"},
        {"name": "status", "label": "Status", "field": "status", "align": "left"},
        {"name": "stage", "label": "Stage", "field": "stage", "align": "left"},
        {"name": "selected_part_id", "label": "Part", "field": "selected_part_id", "align": "left"},
        {"name": "step", "label": "STEP", "field": "step", "align": "left"},
        {"name": "stl", "label": "STL", "field": "stl", "align": "left"},
    ]
    rows = [_run_row(run, selected) for run in runs]
    table = ui.table(columns=columns, rows=rows, row_key="run_id").classes("w-full")
    table.on("rowClick", lambda event: on_select(event.args[1]["run_id"]))
    selected_run = data.get("selected_run") or {}
    with ui.row().classes("gap-3"):
        ui.badge(f"Selected: {selected or 'none'}")
        ui.badge(f"Children: {len(selected_run.get('child_runs') or [])}")
        ui.badge(f"Bridge: {_bridge_status(selected_run)}")
        ui.badge(f"Result review: {_part_result_review_status(selected_run)}")


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
        ui.label("Workflow Review").classes("text-xl font-semibold")
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
        button = ui.button("Create / Refresh Workflow Review", icon="summarize", on_click=lambda: _create_workflow_review_ui(actions, run_id, state, refresh))
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
    _render_stage_review_form(ui, data, actions, state, refresh, stage="requirement")


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
        _render_stage_review_form(ui, data, actions, state, refresh, stage="assembly_plan")
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
    _render_stage_review_form(ui, data, actions, state, refresh, stage="assembly_plan")


def _render_stage_review_form(
    ui: Any,
    data: dict[str, Any],
    actions: WorkflowConsoleActions,
    state: dict[str, Any],
    refresh: Callable[[], None],
    *,
    stage: str,
) -> None:
    run_id = data.get("selected_run_id")
    review_data = data.get("stage_review") or {}
    saved = review_data.get("saved") if isinstance(review_data.get("saved"), dict) else None
    with ui.card().classes("w-full"):
        ui.label("Stage Review").classes("text-lg font-medium")
        if saved is not None:
            _key_values(ui, {
                "Saved stage": saved.get("stage") or "Empty",
                "Saved status": saved.get("review_status") or "Empty",
                "Target rework stage": saved.get("target_rework_stage") or "Empty",
                "Requested changes": saved.get("requested_changes_count", 0),
                "Notes": saved.get("user_notes_preview") or "Empty",
            })
        else:
            ui.label("No stage review saved for this run.").classes("text-sm text-gray-500")

        status = ui.select(
            options=review_data.get("review_status_options") or ["approved", "needs_revision", "blocked"],
            value="approved",
            label="Review status",
        ).classes("w-full")
        target = ui.select(
            options=review_data.get("target_rework_stage_options") or ["requirement", "assembly_plan"],
            value="assembly_plan" if stage == "requirement" else "requirement",
            label="Target rework stage",
        ).classes("w-full")
        notes = ui.textarea("User notes").props("outlined autogrow").classes("w-full")
        changes = ui.textarea("Requested changes").props("outlined autogrow").classes("w-full")
        result_key = f"stage_review_result_{stage}"
        if state.get(result_key) is not None:
            ui.markdown(f"```json\n{json.dumps(state[result_key], indent=2, sort_keys=True)}\n```").classes("w-full")
        button = ui.button(
            "Save review",
            icon="save",
            on_click=lambda: _save_stage_review_ui(
                actions,
                run_id,
                stage,
                status.value,
                target.value,
                notes.value,
                changes.value,
                state,
                result_key,
                refresh,
            ),
        )
        if not run_id:
            button.disable()


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
                ui.label(card["title"]).classes("text-lg font-medium")
                ui.badge(card["current_status"])
            _key_values(ui, {
                "Required upstream artifact": card["required_upstream_artifact"],
                "Output artifact": card["output_artifact"],
                "Available": card["available"],
            })
            button = ui.button(card["action_label"], on_click=lambda c=card: _run_ui_action(actions, run_id, c, state, refresh))
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
        internal_toggle = ui.checkbox("Show internal artifacts", value=False)
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


def _save_stage_review_ui(
    actions: WorkflowConsoleActions,
    run_id: str | None,
    stage: str,
    review_status: str,
    target_rework_stage: str | None,
    user_notes: str | None,
    requested_changes: str | None,
    state: dict[str, Any],
    result_key: str,
    refresh: Callable[[], None],
) -> None:
    if run_id is None:
        state[result_key] = {"ok": False, "error": "Select a run first."}
        refresh()
        return
    try:
        state[result_key] = actions.save_stage_review(
            run_id,
            stage=stage,
            review_status=review_status,
            target_rework_stage=target_rework_stage if review_status == "needs_revision" else None,
            user_notes=user_notes,
            requested_changes=requested_changes,
        )
    except Exception as exc:
        state[result_key] = {"ok": False, "error": str(exc)}
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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


if __name__ == "__main__":
    main()
