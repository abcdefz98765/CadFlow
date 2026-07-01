"""Local backend scaffolding for the future Web Workflow Console."""

from ai_native_cad.workflow_console.backend import (
    EDITABLE_ARTIFACTS,
    GATE_DECISION_ACTIONS,
    GATE_DECISION_STAGES,
    WorkflowConsoleBackend,
)
from ai_native_cad.workflow_console.routes import (
    ROUTE_SPECS,
    ROUTE_SPECS_BY_NAME,
    RouteSpec,
    error_response,
    status_code_for_exception,
    success_response,
)
from ai_native_cad.workflow_console.stage_runner import (
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_CREATED,
    STATUS_FAILED,
    STATUS_RUNNING_OR_INCOMPLETE,
    STATUS_SUCCESS,
    STATUS_UNKNOWN,
    WORKFLOW_STATUS_VALUES,
    StageRunner,
)

__all__ = [
    "STATUS_BLOCKED",
    "STATUS_COMPLETED",
    "STATUS_CREATED",
    "STATUS_FAILED",
    "STATUS_RUNNING_OR_INCOMPLETE",
    "STATUS_SUCCESS",
    "STATUS_UNKNOWN",
    "WORKFLOW_STATUS_VALUES",
    "EDITABLE_ARTIFACTS",
    "GATE_DECISION_ACTIONS",
    "GATE_DECISION_STAGES",
    "ROUTE_SPECS",
    "ROUTE_SPECS_BY_NAME",
    "StageRunner",
    "RouteSpec",
    "WorkflowConsoleBackend",
    "error_response",
    "status_code_for_exception",
    "success_response",
]
