"""Local backend scaffolding for the future Web Workflow Console."""

from ai_native_cad.workflow_console.backend import (
    EDITABLE_ARTIFACTS,
    GATE_DECISION_ACTIONS,
    GATE_DECISION_STAGES,
    WorkflowConsoleBackend,
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
    "StageRunner",
    "WorkflowConsoleBackend",
]
