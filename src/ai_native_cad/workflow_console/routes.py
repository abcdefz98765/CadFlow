"""Dependency-free route contract for future workflow-console HTTP layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
