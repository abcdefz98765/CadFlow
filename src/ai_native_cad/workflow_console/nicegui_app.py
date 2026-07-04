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
from ai_native_cad.workflow_console.backend import DOWNLOADABLE_FILES, WorkflowConsoleBackend
from ai_native_cad.workflow_console.routes import dispatch_route
from ai_native_cad.workflow_console.stage_runner import READABLE_ARTIFACTS

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8780

ARTIFACT_PAGE_ARTIFACTS = (
    "report.md",
    "report.json",
    "requirement.json",
    "design_brief.json",
    "assembly_plan.json",
    "part_create_request.json",
    "part_request_review.json",
    "reviewed_part_handoff.json",
    "part_execution_request.json",
    "part_result_review.json",
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
) -> dict[str, Any]:
    """Build path-free data for the NiceGUI console pages."""
    backend = backend or WorkflowConsoleBackend()
    runs_response = dispatch_route(backend, "list_runs", query=_query(root))
    runs = runs_response["data"] if runs_response["ok"] else []
    selected = selected_run_id or (runs[0]["run_id"] if runs else None)
    run_data = build_selected_run_data(backend, selected, root=root) if selected else empty_selected_run_data()
    return {
        "runs": runs,
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


def build_artifacts_page_data(run: dict[str, Any]) -> dict[str, Any]:
    """Return allowlisted artifact and model availability data."""
    artifacts = [
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
    return {"artifacts": artifacts, "downloadables": downloadables, "model_files": model_files}


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
                ui.tab("Requirement Review")
                ui.tab("Assembly Plan")
                ui.tab("Part Workflow")
                ui.tab("Artifacts")
            panels = ui.tab_panels(tabs, value="Runs").classes("w-full")

            def refresh() -> None:
                panels.clear()
                data = build_console_page_data(console_backend, state.get("selected_run_id"))
                state["selected_run_id"] = data.get("selected_run_id")
                with panels:
                    with ui.tab_panel("Runs"):
                        _render_runs(ui, data, lambda run_id: select_run(run_id))
                    with ui.tab_panel("Requirement Review"):
                        _render_requirement_review(ui, data["requirement_review"])
                    with ui.tab_panel("Assembly Plan"):
                        _render_assembly_plan(ui, data["assembly_plan"])
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


def _render_runs(ui: Any, data: dict[str, Any], on_select: Callable[[str], None]) -> None:
    runs = data.get("runs") or []
    selected = data.get("selected_run_id")
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


def _render_requirement_review(ui: Any, data: dict[str, Any]) -> None:
    _key_values(ui, {
        "Original prompt": data.get("original_prompt") or "Empty",
        "Detected scope": data.get("detected_scope") or "Empty",
        "Product family": data.get("product_family") or "Empty",
        "Part family": data.get("part_family") or "Empty",
        "Blocked reason": data.get("blocked_reason") or "Empty",
    })
    _list_block(ui, "Assumptions", data.get("assumptions"))
    _list_block(ui, "Missing information", data.get("missing_information"))
    _list_block(ui, "Clarification questions", data.get("clarification_questions"))
    _list_block(ui, "Diagnostics", data.get("diagnostics"))
    ui.textarea("User notes / future clarification draft").props("outlined autogrow").classes("w-full")


def _render_assembly_plan(ui: Any, data: dict[str, Any]) -> None:
    if not data.get("present"):
        ui.label("No assembly_plan.json found for this run.").classes("text-gray-600")
        return
    _key_values(ui, {
        "Scope": data.get("scope") or "Empty",
        "Status": data.get("status") or "Empty",
        "Part count": data.get("part_count"),
        "Candidate parts": ", ".join(data.get("candidate_part_ids") or []) or "Empty",
        "Reference-only parts": ", ".join(data.get("reference_only_part_ids") or []) or "Empty",
        "Blocked parts": ", ".join(data.get("blocked_part_ids") or []) or "Empty",
        "Interfaces": data.get("interface_count"),
        "Blocked reasons": ", ".join(data.get("blocked_reasons") or []) or "Empty",
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
    ui.table(columns=columns, rows=data.get("parts") or [], row_key="part_id").classes("w-full")


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
    for model in (data.get("artifacts_page") or {}).get("model_files", []):
        ui.badge(f"{model['name']}: {'available' if model['available'] else 'missing'}")
    for artifact in (data.get("artifacts_page") or {}).get("artifacts", []):
        with ui.expansion(artifact["name"]).classes("w-full"):
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


def _run_row(run: dict[str, Any], selected: str | None) -> dict[str, Any]:
    reviewed = run.get("reviewed_part_summary") if isinstance(run.get("reviewed_part_summary"), dict) else {}
    status = run.get("status") if isinstance(run.get("status"), dict) else {}
    downloadables = {item.get("name") for item in _as_list(run.get("downloadables")) if isinstance(item, dict)}
    return {
        "run_id": run.get("run_id"),
        "status": status.get("status"),
        "stage": status.get("stage"),
        "selected_part_id": _first_present(
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


def _query(root: str | None) -> dict[str, str] | None:
    return {"root": root} if root else None


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
