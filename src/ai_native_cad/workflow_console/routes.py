"""Dependency-free route contract for future workflow-console HTTP layers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.actions import WorkflowConsoleActions


@dataclass(frozen=True)
class RouteSpec:
    """Future HTTP route semantics mapped to safe backend operations."""

    name: str
    method: str
    path: str
    backend_operation: str
    description: str


ROUTE_SPECS: tuple[RouteSpec, ...] = (
    RouteSpec(
        name="create_run",
        method="POST",
        path="/workflow/runs/{run_id}",
        backend_operation="create_run_by_id",
        description="Create a file-backed workflow run from a safe run id.",
    ),
    RouteSpec(
        name="read_workspace",
        method="GET",
        path="/api/workspace",
        backend_operation="read_workspace",
        description="Read the active local workspace identity.",
    ),
    RouteSpec(
        name="create_workspace",
        method="POST",
        path="/api/workspace",
        backend_operation="create_workspace",
        description="Create or initialize a local workspace, optionally outside the repository.",
    ),
    RouteSpec(
        name="load_workspace",
        method="POST",
        path="/api/workspace/load",
        backend_operation="load_workspace",
        description="Load an existing initialized local workspace.",
    ),
    RouteSpec(
        name="read_workspace_config",
        method="GET",
        path="/api/config",
        backend_operation="read_workspace_config",
        description="Read workspace-scoped console config without secrets.",
    ),
    RouteSpec(
        name="write_workspace_config",
        method="PUT",
        path="/api/config",
        backend_operation="write_workspace_config",
        description="Persist workspace-scoped provider and workflow mode config.",
    ),
    RouteSpec(
        name="list_runs",
        method="GET",
        path="/api/runs",
        backend_operation="list_runs",
        description="List workflow runs under configured run roots.",
    ),
    RouteSpec(
        name="list_works",
        method="GET",
        path="/api/works",
        backend_operation="list_works",
        description="List inferred user-visible Works under configured run roots.",
    ),
    RouteSpec(
        name="create_work",
        method="POST",
        path="/api/works",
        backend_operation="create_work",
        description="Create a real local Work entity without executing workflow stages.",
    ),
    RouteSpec(
        name="open_product_golden_example",
        method="POST",
        path="/api/examples/product-golden",
        backend_operation="open_product_golden_example",
        description="Create or reopen the reproducible current Product Golden Work.",
    ),
    RouteSpec(
        name="start_live_product_example",
        method="POST",
        path="/api/examples/live-product",
        backend_operation="start_live_product_example",
        description="Create a new beginning-state Product Example for the configured real Agent.",
    ),
    RouteSpec(
        name="create_product_design",
        method="POST",
        path="/api/designs",
        backend_operation="create_product_design",
        description="Create a normal single-Part Job design Work from a user request.",
    ),
    RouteSpec(
        name="create_golden_example",
        method="POST",
        path="/api/examples/golden-desktop-robot-arm",
        backend_operation="create_golden_example",
        description="Create the compatibility Golden Desktop Robot Arm Work.",
    ),
    RouteSpec(
        name="read_work",
        method="GET",
        path="/api/works/{work_id}",
        backend_operation="get_work_detail",
        description="Read one inferred Work detail by safe Work id.",
    ),
    RouteSpec(
        name="create_work_requirement_run",
        method="POST",
        path="/api/works/{work_id}/requirement-run",
        backend_operation="create_work_requirement_run",
        description="Create a root requirement run for one Work.",
    ),
    RouteSpec(
        name="create_work_part_runs",
        method="POST",
        path="/api/works/{work_id}/part-runs",
        backend_operation="create_work_part_runs",
        description="Create part run containers for one Work after split confirmation.",
    ),
    RouteSpec(
        name="create_work_part_attempt",
        method="POST",
        path="/api/works/{work_id}/parts/{part_job_id}/attempts",
        backend_operation="create_work_part_attempt",
        description="Append another explicit Run attempt to one Part Job.",
    ),
    RouteSpec(
        name="run_work_part_design_episode",
        method="POST",
        path="/api/works/{work_id}/parts/{part_job_id}/design-episodes",
        backend_operation="run_work_part_design_episode",
        description=(
            "Append one provider-selected Design Episode to "
            "an owned Part Job attempt Run."
        ),
    ),
    RouteSpec(
        name="answer_work_part_design_question",
        method="POST",
        path="/api/works/{work_id}/parts/{part_job_id}/design-answers",
        backend_operation="answer_work_part_design_question",
        description="Append one focused user answer and preserve prior Run evidence.",
    ),
    RouteSpec(
        name="accept_work_reviewable_result",
        method="POST",
        path=(
            "/api/works/{work_id}/parts/{part_job_id}/reviewable-results/"
            "{reviewable_result_id}/accept"
        ),
        backend_operation="accept_work_reviewable_result",
        description=(
            "Explicitly accept one registered reviewable Part result."
        ),
    ),
    RouteSpec(
        name="revise_work_reviewable_result",
        method="POST",
        path=(
            "/api/works/{work_id}/parts/{part_job_id}/reviewable-results/"
            "{reviewable_result_id}/revisions"
        ),
        backend_operation="revise_work_reviewable_result",
        description=(
            "Create a new Part Job attempt from one registered reviewable result."
        ),
    ),
    RouteSpec(
        name="read_provider_config",
        method="GET",
        path="/workflow/provider",
        backend_operation="read_provider_config",
        description="Read the active workflow-console provider identity.",
    ),
    RouteSpec(
        name="configure_provider",
        method="POST",
        path="/workflow/provider",
        backend_operation="configure_provider",
        description="Configure the in-process workflow-console provider without secrets.",
    ),
    RouteSpec(
        name="test_provider_connection",
        method="POST",
        path="/workflow/provider/test",
        backend_operation="test_provider_connection",
        description="Test the current provider draft without persisting settings or credentials.",
    ),
    RouteSpec(
        name="save_and_verify_provider",
        method="POST",
        path="/workflow/provider/save-and-verify",
        backend_operation="save_and_verify_provider",
        description="Verify a provider draft and persist only non-secret settings on success.",
    ),
    RouteSpec(
        name="read_product_readiness",
        method="GET",
        path="/api/readiness",
        backend_operation="read_product_readiness",
        description="Read real provider and local CAD execution readiness.",
    ),
    RouteSpec(
        name="read_run_metadata",
        method="GET",
        path="/api/runs/{run_id}/summary",
        backend_operation="read_run_metadata_by_id",
        description="Read metadata and derived status for a safe run id.",
    ),
    RouteSpec(
        name="run_stage",
        method="POST",
        path="/workflow/runs/{run_id}/stages/{stage}",
        backend_operation="run_stage_by_id",
        description="Run a supported deterministic workflow stage for a safe run id.",
    ),
    RouteSpec(
        name="run_revision",
        method="POST",
        path="/workflow/runs/{run_id}/revisions/{child_run_id}",
        backend_operation="run_revision_by_id",
        description="Run a CadFlow-native revision into a safe child run id.",
    ),
    RouteSpec(
        name="list_artifacts",
        method="GET",
        path="/workflow/runs/{run_id}/artifacts",
        backend_operation="list_artifacts_by_id",
        description="List readable workflow artifacts for a safe run id.",
    ),
    RouteSpec(
        name="read_artifact",
        method="GET",
        path="/api/runs/{run_id}/artifacts/{artifact}",
        backend_operation="read_artifact_by_id",
        description="Read one whitelisted workflow artifact for a safe run id.",
    ),
    RouteSpec(
        name="action_part_request",
        method="POST",
        path="/api/actions/part-request",
        backend_operation="WorkflowConsoleActions.create_part_request",
        description="Create one part request from one assembly plan artifact.",
    ),
    RouteSpec(
        name="action_part_review",
        method="POST",
        path="/api/actions/part-review",
        backend_operation="WorkflowConsoleActions.review_part_request",
        description="Review one part request artifact.",
    ),
    RouteSpec(
        name="action_reviewed_handoff",
        method="POST",
        path="/api/actions/reviewed-handoff",
        backend_operation="WorkflowConsoleActions.create_reviewed_handoff",
        description="Create one reviewed part handoff from reviewed request artifacts.",
    ),
    RouteSpec(
        name="action_reviewed_part_create",
        method="POST",
        path="/api/actions/reviewed-part-create",
        backend_operation="WorkflowConsoleActions.create_reviewed_part",
        description="Run one reviewed single-part create bridge.",
    ),
    RouteSpec(
        name="action_part_result_review",
        method="POST",
        path="/api/actions/part-result-review",
        backend_operation="WorkflowConsoleActions.review_part_result",
        description="Review one child result from a reviewed single-part create bridge.",
    ),
    RouteSpec(
        name="action_save_stage_review",
        method="POST",
        path="/api/actions/stage-review",
        backend_operation="WorkflowConsoleActions.save_stage_review",
        description="Save one local stage review/rework intent artifact without rerunning workflow stages.",
    ),
    RouteSpec(
        name="action_create_workflow_review",
        method="POST",
        path="/api/actions/workflow-review",
        backend_operation="WorkflowConsoleActions.create_workflow_review",
        description="Create one deterministic local workflow review report.",
    ),
    RouteSpec(
        name="action_run_rework",
        method="POST",
        path="/api/actions/rework",
        backend_operation="WorkflowConsoleActions.run_rework",
        description="Run one explicit local rework action from a saved stage review.",
    ),
    RouteSpec(
        name="write_artifact",
        method="PUT",
        path="/workflow/runs/{run_id}/artifacts/{artifact}",
        backend_operation="write_artifact_by_id",
        description="Write one editable JSON workflow artifact for a safe run id.",
    ),
    RouteSpec(
        name="list_downloadables",
        method="GET",
        path="/workflow/runs/{run_id}/downloadables",
        backend_operation="list_downloadables_by_id",
        description="List whitelisted downloadable files for a safe run id.",
    ),
    RouteSpec(
        name="record_gate_decision",
        method="POST",
        path="/workflow/runs/{run_id}/gate-decisions",
        backend_operation="record_gate_decision_by_id",
        description="Record an approve/reject/return/override gate decision.",
    ),
    RouteSpec(
        name="apply_requirement_clarification",
        method="POST",
        path="/api/actions/requirement-clarification",
        backend_operation="apply_requirement_clarification_by_id",
        description="Apply structured requirement clarification answers and write requirement_v2.json.",
    ),
)

ROUTE_SPECS_BY_NAME = {spec.name: spec for spec in ROUTE_SPECS}


def dispatch_route(
    backend: WorkflowConsoleBackend,
    route_name: str,
    path_params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invoke a route contract by name and return a stable response envelope."""
    try:
        if route_name not in ROUTE_SPECS_BY_NAME:
            raise ValueError(f"unknown workflow console route: {route_name}")
        handler = _ROUTE_HANDLERS[route_name]
        data = handler(
            backend,
            _require_dict(path_params, "path_params"),
            _require_dict(body, "body"),
            _require_dict(query, "query"),
        )
        return success_response(_public_route_data(data), status_code=_success_status_code(route_name))
    except Exception as exc:
        return error_response(exc)


def success_response(data: Any, status_code: int = 200) -> dict[str, Any]:
    """Return a stable success envelope for future route adapters."""
    return {
        "ok": True,
        "status_code": status_code,
        "data": data,
        "error": None,
    }


def error_response(exc: Exception) -> dict[str, Any]:
    """Return a stable error envelope without exposing local filesystem paths."""
    status_code = status_code_for_exception(exc)
    return {
        "ok": False,
        "status_code": status_code,
        "data": None,
        "error": {
            "type": _public_error_type(exc),
            "message": _public_error_message(exc, status_code),
        },
    }


def status_code_for_exception(exc: Exception) -> int:
    """Map backend exceptions to future HTTP-like status codes."""
    if isinstance(exc, ValueError):
        return 400
    if isinstance(exc, FileNotFoundError):
        return 404
    if isinstance(exc, FileExistsError):
        return 409
    return 500


def _public_error_type(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return "bad_request"
    if isinstance(exc, FileNotFoundError):
        return "not_found"
    if isinstance(exc, FileExistsError):
        return "conflict"
    return "internal_error"


def _public_error_message(exc: Exception, status_code: int) -> str:
    if status_code == 500:
        return "internal workflow console error"
    return str(exc)


def _create_run(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.create_run_by_id(
        _require_value(path_params, "run_id"),
        _require_value(body, "prompt"),
        root=query.get("root", "outputs"),
    )


def _read_workspace(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.read_workspace()


def _create_workspace(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    return backend.create_workspace(
        body.get("path"),
        name=body.get("name"),
        advancement_mode=body.get("advancement_mode"),
        include_examples=_optional_bool(body, "include_examples", False),
    )


def _load_workspace(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    return backend.load_workspace(_require_value(body, "path"))


def _read_workspace_config(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.read_workspace_config()


def _write_workspace_config(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    return backend.write_workspace_config(body, merge=True)


def _list_runs(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    filters = {}
    if query.get("search") is not None:
        filters["search"] = _require_string(query, "search")
    return backend.list_runs_page(
        limit=_optional_int(query, "limit", 50),
        offset=_optional_int(query, "offset", 0),
        filters=filters,
    )


def _list_works(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    filters = {}
    if query.get("show_debug") is not None:
        filters["show_debug"] = _optional_bool(query, "show_debug", False)
    return backend.list_works(
        limit=_optional_int(query, "limit", 50),
        offset=_optional_int(query, "offset", 0),
        filters=filters,
    )


def _create_work(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    metadata = body.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("workflow console work metadata must be a dictionary")
    return backend.create_work(
        _require_value(body, "title"),
        description=body.get("description"),
        work_id=body.get("work_id"),
        metadata=metadata,
    )


def _create_golden_example(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    mode = body.get("mode") or "contract"
    if mode not in {"contract", "full"}:
        raise ValueError("golden example mode must be contract or full")
    return backend.create_golden_example(mode)


def _open_product_golden_example(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    if body:
        raise ValueError("product Golden example does not accept request fields")
    return backend.open_product_golden_example()


def _start_live_product_example(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    if body:
        raise ValueError("live Product Example does not accept request fields")
    return backend.start_live_product_example()


def _create_product_design(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    unknown = set(body) - {"request", "title"}
    if unknown:
        raise ValueError("new design body contains unknown fields")
    return backend.create_product_design(
        _require_value(body, "request"),
        title=body.get("title"),
    )


def _read_work(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.get_work_detail(_require_value(path_params, "work_id"))


def _create_work_requirement_run(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    return backend.create_work_requirement_run(
        _require_value(path_params, "work_id"),
        _require_value(body, "prompt"),
        run_id=body.get("run_id"),
    )


def _create_work_part_runs(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.create_work_part_runs(_require_value(path_params, "work_id"))


def _create_work_part_attempt(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    return backend.create_work_part_attempt(
        _require_value(path_params, "work_id"),
        _require_value(path_params, "part_job_id"),
        prompt=body.get("prompt"),
        role=body.get("role"),
        run_id=body.get("run_id"),
    )


def _run_work_part_design_episode(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    return backend.run_work_part_design_episode(
        _require_value(path_params, "work_id"),
        _require_value(path_params, "part_job_id"),
        request_id=_require_value(body, "request_id"),
        attempt_run_id=body.get("attempt_run_id"),
        objective=body.get("objective"),
    )


def _answer_work_part_design_question(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    unknown = set(body) - {
        "run_id", "answer_id", "question_artifact_id", "field", "question", "answer"
    }
    if unknown:
        raise ValueError("design answer body contains unknown fields")
    return backend.answer_work_part_design_question(
        _require_value(path_params, "work_id"),
        _require_value(path_params, "part_job_id"),
        run_id=_require_value(body, "run_id"),
        answer_id=_require_value(body, "answer_id"),
        question_artifact_id=_require_value(body, "question_artifact_id"),
        field=_require_value(body, "field"),
        question=_require_value(body, "question"),
        answer=_require_value(body, "answer"),
    )


def _accept_work_reviewable_result(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    if body:
        raise ValueError("reviewable acceptance body must be empty")
    return backend.accept_work_reviewable_result(
        _require_value(path_params, "work_id"),
        _require_value(path_params, "part_job_id"),
        _require_value(path_params, "reviewable_result_id"),
    )


def _revise_work_reviewable_result(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    unknown = set(body) - {"revision_prompt", "run_id"}
    if unknown:
        raise ValueError("reviewable revision body contains unknown fields")
    return backend.revise_work_reviewable_result(
        _require_value(path_params, "work_id"),
        _require_value(path_params, "part_job_id"),
        _require_value(path_params, "reviewable_result_id"),
        revision_prompt=_require_value(body, "revision_prompt"),
        run_id=body.get("run_id"),
    )


def _read_run_metadata(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.read_run_metadata_by_id(_require_value(path_params, "run_id"), root=query.get("root"))


def _read_provider_config(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.read_provider_config()


def _configure_provider(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    return backend.configure_provider(
        _require_value(body, "provider"),
        model=body.get("model"),
        base_url=body.get("base_url"),
        timeout_seconds=body.get("timeout_seconds"),
        max_retries=body.get("max_retries"),
    )


def _test_provider_connection(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    unknown = set(body) - {
        "provider", "model", "base_url", "timeout_seconds", "max_retries", "api_key"
    }
    if unknown:
        raise ValueError("provider test body contains unknown fields")
    return backend.test_provider_connection(
        body.get("provider"),
        model=body.get("model"),
        base_url=body.get("base_url"),
        timeout_seconds=body.get("timeout_seconds"),
        max_retries=body.get("max_retries"),
        api_key=body.get("api_key"),
    )


def _save_and_verify_provider(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    unknown = set(body) - {
        "provider", "model", "base_url", "timeout_seconds", "max_retries", "api_key"
    }
    if unknown:
        raise ValueError("provider save body contains unknown fields")
    return backend.save_and_verify_provider(
        _require_value(body, "provider"),
        model=body.get("model"),
        base_url=body.get("base_url"),
        timeout_seconds=body.get("timeout_seconds"),
        max_retries=body.get("max_retries"),
        api_key=body.get("api_key"),
    )


def _read_product_readiness(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.read_product_readiness()


def _run_stage(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.run_stage_by_id(
        _require_value(path_params, "run_id"),
        _require_value(path_params, "stage"),
        prompt=body.get("prompt"),
        context=body.get("context"),
        root=query.get("root"),
    )


def _run_revision(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.run_revision_by_id(
        _require_value(path_params, "run_id"),
        _require_value(path_params, "child_run_id"),
        _require_value(body, "prompt"),
        root=query.get("root", "outputs"),
        child_root=query.get("child_root"),
    )


def _list_artifacts(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> list[dict[str, Any]]:
    return backend.list_artifacts_by_id(_require_value(path_params, "run_id"), root=query.get("root"))


def _read_artifact(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.read_artifact_by_id(
        _require_value(path_params, "run_id"),
        _require_value(path_params, "artifact"),
        root=query.get("root"),
    )


def _write_artifact(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.write_artifact_by_id(
        _require_value(path_params, "run_id"),
        _require_value(path_params, "artifact"),
        _require_value(body, "content"),
        root=query.get("root"),
        edit_reason=body.get("edit_reason"),
    )


def _list_downloadables(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> list[dict[str, Any]]:
    return backend.list_downloadables_by_id(_require_value(path_params, "run_id"), root=query.get("root"))


def _record_gate_decision(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.record_gate_decision_by_id(
        _require_value(path_params, "run_id"),
        stage=_require_value(body, "stage"),
        action=_require_value(body, "action"),
        reason=body.get("reason"),
        payload=body.get("payload"),
        root=query.get("root"),
    )


def _apply_requirement_clarification(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    _reject_secret_fields(body)
    return backend.apply_requirement_clarification_by_id(
        _require_value(body, "run_id"),
        answers=_require_value(body, "answers"),
        notes=body.get("notes"),
        root=query.get("root"),
    )


def _action_part_request(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return WorkflowConsoleActions(backend).create_part_request(
        _require_value(body, "run_id"),
        part_id=body.get("part_id"),
        root=query.get("root"),
    )


def _action_part_review(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return WorkflowConsoleActions(backend).review_part_request(_require_value(body, "run_id"), root=query.get("root"))


def _action_reviewed_handoff(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return WorkflowConsoleActions(backend).create_reviewed_handoff(_require_value(body, "run_id"), root=query.get("root"))


def _action_reviewed_part_create(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return WorkflowConsoleActions(backend).create_reviewed_part(_require_value(body, "run_id"), root=query.get("root"))


def _action_part_result_review(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    expected_stl = body.get("expected_stl", True)
    if not isinstance(expected_stl, bool):
        raise ValueError("workflow console action expected_stl must be a boolean")
    return WorkflowConsoleActions(backend).review_part_result(
        _require_value(body, "run_id"),
        child_run_id=body.get("child_run_id"),
        root=query.get("root"),
        expected_stl=expected_stl,
    )


def _action_save_stage_review(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return WorkflowConsoleActions(backend).save_stage_review(
        _require_value(body, "run_id"),
        stage=_require_value(body, "stage"),
        review_status=_require_value(body, "review_status"),
        user_notes=body.get("user_notes"),
        target_rework_stage=body.get("target_rework_stage"),
        requested_changes=body.get("requested_changes"),
        root=query.get("root"),
    )


def _action_create_workflow_review(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return WorkflowConsoleActions(backend).create_workflow_review(
        _require_value(body, "run_id"),
        root=query.get("root"),
    )


def _action_run_rework(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return WorkflowConsoleActions(backend).run_rework(
        _require_value(body, "run_id"),
        root=query.get("root"),
    )


RouteHandler = Callable[
    [WorkflowConsoleBackend, dict[str, Any], dict[str, Any], dict[str, Any]],
    Any,
]

_ROUTE_HANDLERS: dict[str, RouteHandler] = {
    "create_run": _create_run,
    "read_workspace": _read_workspace,
    "create_workspace": _create_workspace,
    "load_workspace": _load_workspace,
    "read_workspace_config": _read_workspace_config,
    "write_workspace_config": _write_workspace_config,
    "list_runs": _list_runs,
    "list_works": _list_works,
    "create_work": _create_work,
    "open_product_golden_example": _open_product_golden_example,
    "start_live_product_example": _start_live_product_example,
    "create_product_design": _create_product_design,
    "create_golden_example": _create_golden_example,
    "read_work": _read_work,
    "create_work_requirement_run": _create_work_requirement_run,
    "create_work_part_runs": _create_work_part_runs,
    "create_work_part_attempt": _create_work_part_attempt,
    "run_work_part_design_episode": _run_work_part_design_episode,
    "answer_work_part_design_question": _answer_work_part_design_question,
    "accept_work_reviewable_result": _accept_work_reviewable_result,
    "revise_work_reviewable_result": _revise_work_reviewable_result,
    "read_provider_config": _read_provider_config,
    "configure_provider": _configure_provider,
    "test_provider_connection": _test_provider_connection,
    "save_and_verify_provider": _save_and_verify_provider,
    "read_product_readiness": _read_product_readiness,
    "read_run_metadata": _read_run_metadata,
    "run_stage": _run_stage,
    "run_revision": _run_revision,
    "list_artifacts": _list_artifacts,
    "read_artifact": _read_artifact,
    "write_artifact": _write_artifact,
    "list_downloadables": _list_downloadables,
    "record_gate_decision": _record_gate_decision,
    "apply_requirement_clarification": _apply_requirement_clarification,
    "action_part_request": _action_part_request,
    "action_part_review": _action_part_review,
    "action_reviewed_handoff": _action_reviewed_handoff,
    "action_reviewed_part_create": _action_reviewed_part_create,
    "action_part_result_review": _action_part_result_review,
    "action_save_stage_review": _action_save_stage_review,
    "action_create_workflow_review": _action_create_workflow_review,
    "action_run_rework": _action_run_rework,
}


def _success_status_code(route_name: str) -> int:
    if route_name in {
        "create_run",
        "create_workspace",
        "load_workspace",
        "write_workspace_config",
        "save_and_verify_provider",
        "create_work",
        "open_product_golden_example",
        "start_live_product_example",
        "create_product_design",
        "create_golden_example",
        "create_work_requirement_run",
        "create_work_part_runs",
        "create_work_part_attempt",
        "run_work_part_design_episode",
        "answer_work_part_design_question",
        "accept_work_reviewable_result",
        "revise_work_reviewable_result",
        "run_revision",
        "record_gate_decision",
        "apply_requirement_clarification",
        "action_part_request",
        "action_part_review",
        "action_reviewed_handoff",
        "action_reviewed_part_create",
        "action_part_result_review",
        "action_save_stage_review",
        "action_create_workflow_review",
        "action_run_rework",
    }:
        return 201
    return 200


def _require_dict(value: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"workflow console route {label} must be a dictionary")
    return value


def _require_value(values: dict[str, Any], key: str) -> Any:
    value = values.get(key)
    if value is None:
        raise ValueError(f"workflow console route is missing required value: {key}")
    return value


def _require_string(values: dict[str, Any], key: str) -> str:
    value = _require_value(values, key)
    if not isinstance(value, str):
        raise ValueError(f"workflow console route value must be a string: {key}")
    return value


def _optional_int(values: dict[str, Any], key: str, default: int) -> int:
    value = values.get(key, default)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError(f"workflow console route value must be an integer: {key}")


def _optional_bool(values: dict[str, Any], key: str, default: bool) -> bool:
    value = values.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"1", "true", "yes", "on"}:
        return True
    if isinstance(value, str) and value.lower() in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"workflow console route value must be a boolean: {key}")


def _reject_secret_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("password", "secret", "token", "api_key", "apikey", "bearer")):
                raise ValueError("workflow console provider config must not include secrets")
            _reject_secret_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_secret_fields(item)


def _public_route_data(value: Any) -> Any:
    if isinstance(value, list):
        return [_public_route_data(item) for item in value]
    if isinstance(value, str):
        return _public_string(value)
    if not isinstance(value, dict):
        return value

    public = {}
    for key, item in value.items():
        if key in {"path", "run_dir", "root", "output_dir", "payload"}:
            continue
        if key == "display_path" and isinstance(item, str):
            public[key] = item
            continue
        if key == "files" and isinstance(item, dict):
            public[key] = _public_file_refs(item)
            continue
        if key == "content":
            public[key] = _public_artifact_content(item)
            continue
        public[key] = _public_route_data(item)
    return public


def _public_file_refs(files: dict[str, Any]) -> dict[str, str]:
    public = {}
    for label, value in files.items():
        if not isinstance(value, str):
            continue
        normalized = value.replace("\\", "/").rstrip("/")
        public[str(label)] = normalized.rsplit("/", 1)[-1]
    return public


def _public_string(value: str) -> str:
    try:
        if Path(value).is_absolute():
            return Path(value).name
    except (OSError, ValueError):
        pass
    return value


def _public_artifact_content(value: Any) -> Any:
    if isinstance(value, list):
        public_items = [_public_artifact_content(item) for item in value]
        return [item for item in public_items if item is not None]
    if isinstance(value, str):
        if _unsafe_public_content_string(value):
            return None
        return _public_string(value)
    if not isinstance(value, dict):
        return value
    public = {}
    for key, item in value.items():
        if _unsafe_public_content_key(key):
            continue
        public_item = _public_artifact_content(item)
        if public_item is not None:
            public[key] = public_item
    return public


def _unsafe_public_content_key(key: Any) -> bool:
    lowered = str(key).lower()
    blocked = (
        "api_key",
        "apikey",
        "password",
        "secret",
        "token",
        "bearer",
        "raw_response",
        "raw_provider",
        "provider_messages",
        "provider_response",
        "transcript",
        "request_payload",
        "response_payload",
    )
    return any(marker in lowered for marker in blocked)


def _unsafe_public_content_string(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("api_key", "apikey", "password", "secret", "token", "bearer "))
