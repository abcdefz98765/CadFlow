"""Dependency-free route contract for future workflow-console HTTP layers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend


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
        name="list_runs",
        method="GET",
        path="/workflow/runs",
        backend_operation="list_runs",
        description="List workflow runs under configured run roots.",
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
        description="Run a minimal provider connectivity check without writing workflow artifacts.",
    ),
    RouteSpec(
        name="read_run_metadata",
        method="GET",
        path="/workflow/runs/{run_id}",
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
        path="/workflow/runs/{run_id}/artifacts/{artifact}",
        backend_operation="read_artifact_by_id",
        description="Read one whitelisted workflow artifact for a safe run id.",
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


def _list_runs(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> list[dict[str, Any]]:
    return backend.list_runs()


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
        timeout_seconds=body.get("timeout_seconds"),
        max_retries=body.get("max_retries"),
    )


def _test_provider_connection(
    backend: WorkflowConsoleBackend,
    path_params: dict[str, Any],
    body: dict[str, Any],
    query: dict[str, Any],
) -> dict[str, Any]:
    return backend.test_provider_connection()


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


RouteHandler = Callable[
    [WorkflowConsoleBackend, dict[str, Any], dict[str, Any], dict[str, Any]],
    Any,
]

_ROUTE_HANDLERS: dict[str, RouteHandler] = {
    "create_run": _create_run,
    "list_runs": _list_runs,
    "read_provider_config": _read_provider_config,
    "configure_provider": _configure_provider,
    "test_provider_connection": _test_provider_connection,
    "read_run_metadata": _read_run_metadata,
    "run_stage": _run_stage,
    "run_revision": _run_revision,
    "list_artifacts": _list_artifacts,
    "read_artifact": _read_artifact,
    "write_artifact": _write_artifact,
    "list_downloadables": _list_downloadables,
    "record_gate_decision": _record_gate_decision,
}


def _success_status_code(route_name: str) -> int:
    if route_name in {"create_run", "run_revision", "record_gate_decision"}:
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
        if key == "files" and isinstance(item, dict):
            public[key] = _public_file_refs(item)
            continue
        public[key] = _public_route_data(item)
    if "content" in value:
        public["content"] = value["content"]
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
