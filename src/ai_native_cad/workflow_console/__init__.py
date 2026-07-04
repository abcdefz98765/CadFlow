"""Local backend scaffolding for the future Web Workflow Console."""

from ai_native_cad.workflow_console.backend import (
    EDITABLE_ARTIFACTS,
    GATE_DECISION_ACTIONS,
    GATE_DECISION_STAGES,
    WorkflowConsoleBackend,
)
from ai_native_cad.workflow_console.actions import (
    ACTION_NAMES,
    ACTION_STAGE_FOLDERS,
    STAGE_REVIEW_STATUSES,
    STAGE_REVIEW_STAGES,
    STAGE_REWORK_TARGETS,
    WorkflowConsoleActions,
)
from ai_native_cad.workflow_console.routes import (
    ROUTE_SPECS,
    ROUTE_SPECS_BY_NAME,
    RouteSpec,
    dispatch_route,
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
    "WorkflowConsoleActions",
    "ACTION_NAMES",
    "ACTION_STAGE_FOLDERS",
    "STAGE_REVIEW_STATUSES",
    "STAGE_REVIEW_STAGES",
    "STAGE_REWORK_TARGETS",
    "dispatch_route",
    "error_response",
    "status_code_for_exception",
    "success_response",
]
