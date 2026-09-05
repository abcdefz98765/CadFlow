"""Bounded browser action lifecycle for the workflow console.

This module owns transient command execution state and verification. Durable
Work, Run, Part Job, result, and acceptance truth remain backend-owned.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.i18n import action_label
from ai_native_cad.workflow_console.ui_performance import ui_trace_event, ui_trace_start


def _dict_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


@dataclass
class ActionExecutionState:
    """Browser-visible lifecycle for every mutating Workflow action.

    This is presentation state only.  The backend remains the source of truth;
    success is recorded only after it has been refreshed and verified.
    """

    action_key: str
    status: str = "idle"
    target_work_id: str | None = None
    target_part_job_id: str | None = None
    target_run_id: str | None = None
    target_stage_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    message: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    postcondition_verified: bool = False
    command_acknowledged: bool = False
    runtime_outcome: str | None = None

    @classmethod
    def from_action(cls, action: dict[str, Any], *, status: str = "pending", message: str | None = None) -> "ActionExecutionState":
        return cls(
            action_key=str(action.get("key") or "workflow_action"),
            status=status,
            target_work_id=action.get("target_work_id") if isinstance(action.get("target_work_id"), str) else None,
            target_part_job_id=action.get("part_job_id") if isinstance(action.get("part_job_id"), str) else None,
            target_run_id=action.get("target_run_id") if isinstance(action.get("target_run_id"), str) else None,
            target_stage_id=action.get("target_stage_id") if isinstance(action.get("target_stage_id"), str) else None,
            started_at=datetime.now(timezone.utc).isoformat(),
            message=message,
        )


def _action_identity(action: dict[str, Any]) -> tuple[Any, ...]:
    return (
        action.get("key"),
        action.get("target_work_id"),
        action.get("target_run_id"),
        action.get("target_stage_id"),
        action.get("part_id") or action.get("part_job_id"),
        action.get("reviewable_result_id"),
    )


def _action_identity_key(action: dict[str, Any]) -> str:
    """Stable map key for transient, independently-rendered command state."""
    return json.dumps(_action_identity(action), separators=(",", ":"), default=str)


def action_executions(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the scoped execution map, migrating the historical latest alias."""
    executions = state.get("action_executions_by_identity")
    if not isinstance(executions, dict):
        executions = {}
        legacy = state.get("action_execution")
        if isinstance(legacy, dict) and isinstance(legacy.get("identity"), (list, tuple)):
            executions[json.dumps(tuple(legacy["identity"]), separators=(",", ":"), default=str)] = legacy
        state["action_executions_by_identity"] = executions
    return executions


def active_execution_for(state: dict[str, Any], action: dict[str, Any]) -> dict[str, Any] | None:
    """Find a pending/confirming execution for this exact semantic target."""
    execution = action_executions(state).get(_action_identity_key(action))
    if isinstance(execution, dict) and execution.get("status") in {"confirming", "pending"}:
        return execution
    return None


def active_executions_for_work(state: dict[str, Any], work_id: str | None) -> list[dict[str, Any]]:
    """All active UI executions in a Work; actions for sibling Parts coexist."""
    return [
        execution
        for execution in action_executions(state).values()
        if isinstance(execution, dict)
        and execution.get("target_work_id") == work_id
        and execution.get("status") in {"confirming", "pending"}
    ]


def _pending_action_matches(state: dict[str, Any], action: dict[str, Any]) -> bool:
    if action.get("key") == "design_runnable_parts":
        targets = {
            (item.get("part_job_id"), item.get("target_run_id"))
            for item in action.get("part_targets", [])
            if isinstance(item, dict)
        }
        return any(
            execution.get("status") in {"confirming", "pending"}
            and (
                execution.get("target_part_job_id"),
                execution.get("target_run_id"),
            )
            in targets
            for execution in action_executions(state).values()
            if isinstance(execution, dict)
        )
    return active_execution_for(state, action) is not None


def _set_action_execution(state: dict[str, Any], execution: ActionExecutionState, action: dict[str, Any]) -> None:
    value = {**asdict(execution), "identity": _action_identity(action)}
    action_executions(state)[_action_identity_key(action)] = value
    # Compatibility alias for existing renderers and clients.  It is never the
    # authority for duplicate detection now that independent Part actions run.
    state["action_execution"] = value


def _schedule_action(coroutine: Any) -> Any:
    """Schedule browser work, while allowing renderer-free unit tests to run it."""
    try:
        return asyncio.get_running_loop().create_task(coroutine)
    except RuntimeError:
        return asyncio.run(coroutine)


def _runtime_message(action: dict[str, Any], language: str, phase: str, *, error: str | None = None) -> str:
    part_id = str(action.get("part_id") or action.get("part_job_id") or "")
    scope_label = str(
        action.get("scope_label")
        or (part_id.replace("_", " ").title() if part_id else "Work Design")
    )
    key = str(action.get("key") or action.get("backend_action") or "")
    product_messages = {
        "open_product_example": {
            "pending": ("Preparing the Product Example…", "正在准备产品示例……"),
            "success": ("Product Example ready", "产品示例已就绪"),
            "failed": ("Could not open the Product Example", "未能打开产品示例"),
        },
        "accept_reviewable_result": {
            "pending": ("Accepting result…", "正在接受结果……"),
            "success": ("Result accepted", "结果已接受"),
            "failed": ("Could not accept the result", "未能接受结果"),
        },
        "revise_reviewable_result": {
            "pending": ("Creating a new design attempt…", "正在创建新的设计尝试……"),
            "success": ("New design attempt created", "已创建新的设计尝试"),
            "failed": ("Could not create the revision", "未能创建设计修改"),
        },
        "continue_agent": {
            "pending": (f"Starting {scope_label} design…", f"正在启动 {scope_label} 设计……"),
            "success": (f"{scope_label} design completed", f"{scope_label} 设计已完成"),
            "failed": (f"{scope_label} design failed", f"{scope_label} 设计失败"),
        },
        "retry_agent": {
            "pending": (f"Restarting {scope_label} design…", f"正在重新启动 {scope_label} 设计……"),
            "success": (f"{scope_label} design progressed", f"{scope_label} 设计已有进展"),
            "failed": (f"{scope_label} design stopped", f"{scope_label} 设计已停止"),
        },
        "continue_work_design": {
            "pending": ("Starting Work Design…", "正在启动 Work 设计……"),
            "success": ("Work Design activity completed", "Work 设计活动已完成"),
            "failed": ("Work Design could not complete", "Work 设计未能完成"),
        },
        "start_design": {
            "pending": ("Starting the design…", "正在开始设计……"),
            "success": ("Design started", "设计已开始"),
            "failed": ("Could not start the design", "未能开始设计"),
        },
    }
    if key in product_messages and phase in product_messages[key]:
        pair = product_messages[key][phase]
        return pair[1] if language == "zh" else pair[0]
    if phase == "pending" and key == "select_candidate_part":
        return f"正在将后续零件切换为 {part_id}……" if language == "zh" else f"Switching the next part to {part_id}…"
    if phase == "success" and key == "select_candidate_part":
        return f"已切换到 {part_id}" if language == "zh" else f"Switched to {part_id}"
    if phase == "failed" and key == "select_candidate_part":
        return "未能切换后续零件" if language == "zh" else "Could not switch the next part"
    label = action_label(language, action.get("label"), key)
    if phase == "pending":
        return f"正在执行：{label}" if language == "zh" else f"Running: {label}"
    if phase == "success":
        return f"已完成：{label}" if language == "zh" else f"Completed: {label}"
    return f"操作失败：{label}" if language == "zh" else f"Action failed: {label}"

async def _execute_action_lifecycle(
    action: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
    execute: Callable[[], dict[str, Any]],
    *,
    language: str,
    verify: Callable[[dict[str, Any]], tuple[bool, str | None]] | None = None,
    terminal: Callable[[dict[str, Any]], tuple[str, str, str]] | None = None,
    already_pending: bool = False,
) -> dict[str, Any] | None:
    """Execute one write once, surface pending, then verify its persisted effect."""
    if _pending_action_matches(state, action) and not already_pending:
        return None
    if not already_pending:
        pending = ActionExecutionState.from_action(action, message=_runtime_message(action, language, "pending"))
        pending.command_acknowledged = True
        pending.runtime_outcome = "running"
        _set_action_execution(state, pending, action)
    # NiceGUI supplies a cached content-only pending refresh. Other callers keep
    # the original callable contract and receive the full refresh fallback.
    pending_refresh = getattr(refresh, "pending", None)
    pending_started = ui_trace_start()
    (pending_refresh if callable(pending_refresh) else refresh)()
    ui_trace_event(
        "action_pending_render",
        pending_started,
        action_key=str(action.get("key") or ""),
    )
    # Yield after the render so browser users observe pending state before a
    # synchronous local backend operation starts.
    await asyncio.sleep(0.05)
    try:
        backend_started = ui_trace_start()
        result = await asyncio.to_thread(execute)
        ui_trace_event(
            "action_backend",
            backend_started,
            action_key=str(action.get("key") or ""),
        )
        verified, detail = await asyncio.to_thread(verify, result) if verify else (True, None)
        if not verified:
            raise RuntimeError(detail or "backend result did not satisfy its postcondition")
        state["surface_action_result"] = result
        terminal_status, terminal_message, runtime_outcome = (
            terminal(result)
            if terminal
            else (
                "succeeded",
                _runtime_message(action, language, "success"),
                "completed",
            )
        )
        completed = ActionExecutionState.from_action(
            action,
            status=terminal_status,
            message=terminal_message,
        )
        completed.completed_at = datetime.now(timezone.utc).isoformat()
        completed.postcondition_verified = True
        completed.command_acknowledged = True
        completed.runtime_outcome = runtime_outcome
        _set_action_execution(state, completed, action)
        return result
    except Exception as exc:
        failed = ActionExecutionState.from_action(action, status="failed", message=_runtime_message(action, language, "failed"))
        failed.completed_at = datetime.now(timezone.utc).isoformat()
        failed.error_code = type(exc).__name__
        failed.error_detail = str(exc)
        failed.command_acknowledged = True
        failed.runtime_outcome = "environment_runtime_failure"
        _set_action_execution(state, failed, action)
        state["surface_action_result"] = {"ok": False, "error": str(exc)}
        return None
    finally:
        terminal_started = ui_trace_start()
        refresh()
        ui_trace_event(
            "action_terminal_refresh",
            terminal_started,
            action_key=str(action.get("key") or ""),
        )

async def _start_work_intent_async(
    backend: WorkflowConsoleBackend | None,
    work_id: str | None,
    prompt: str | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> dict[str, Any] | None:
    action = {
        "key": "start_design",
        "label": "Start design",
        "target_work_id": work_id,
    }
    if backend is None or not work_id or not isinstance(prompt, str) or not prompt.strip():
        failed = ActionExecutionState.from_action(action, status="failed", message=_runtime_message(action, language, "failed"))
        failed.error_detail = "Describe the design objective first." if language != "zh" else "请先描述设计目标。"
        _set_action_execution(state, failed, action)
        refresh()
        return None

    def execute() -> dict[str, Any]:
        return backend.create_work_requirement_run(work_id, prompt.strip())

    def verify(_result: dict[str, Any]) -> tuple[bool, str | None]:
        manifest = backend._read_work_manifest(work_id)
        ok = isinstance(manifest.get("root_run_id"), str)
        return ok, None if ok else "Intent Run was not persisted."

    result = await _execute_action_lifecycle(
        action, state, refresh, execute, language=language, verify=verify
    )
    if result is not None:
        state["intent_draft"] = ""
    return result


async def _accept_reviewable_result_async(
    backend: WorkflowConsoleBackend,
    action: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> dict[str, Any] | None:
    work_id = str(action["target_work_id"])
    part_id = str(action["part_job_id"])
    result_id = str(action["reviewable_result_id"])

    def execute() -> dict[str, Any]:
        return backend.accept_work_reviewable_result(work_id, part_id, result_id)

    def verify(_result: dict[str, Any]) -> tuple[bool, str | None]:
        pointer = _dict_get(
            _dict_get(backend._read_work_manifest(work_id), "accepted_part_results"),
            part_id,
        )
        ok = isinstance(pointer, dict) and pointer.get("result_id") == result_id and pointer.get("status") == "approved"
        return ok, None if ok else "Accepted-result pointer did not change to the reviewed result."

    return await _execute_action_lifecycle(
        action, state, refresh, execute, language=language, verify=verify
    )


async def _revise_reviewable_result_async(
    backend: WorkflowConsoleBackend,
    action: dict[str, Any],
    revision_prompt: str | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> dict[str, Any] | None:
    work_id = str(action["target_work_id"])
    part_id = str(action["part_job_id"])
    result_id = str(action["reviewable_result_id"])
    if not isinstance(revision_prompt, str) or not revision_prompt.strip():
        failed = ActionExecutionState.from_action(
            action,
            status="failed",
            message=_runtime_message(action, language, "failed"),
        )
        failed.error_detail = "Describe the requested change first." if language != "zh" else "请先描述要修改的内容。"
        _set_action_execution(state, failed, action)
        refresh()
        return None
    before = backend._read_work_manifest(work_id)
    accepted_before = deepcopy(_dict_get(before, "accepted_part_results"))
    job_before = next(
        (item for item in before.get("part_jobs", []) if isinstance(item, dict) and item.get("part_job_id") == part_id),
        {},
    )
    attempt_count = len(job_before.get("attempts", []))

    def execute() -> dict[str, Any]:
        return backend.revise_work_reviewable_result(
            work_id,
            part_id,
            result_id,
            revision_prompt=revision_prompt.strip(),
        )

    def verify(_result: dict[str, Any]) -> tuple[bool, str | None]:
        after = backend._read_work_manifest(work_id)
        job_after = next(
            (item for item in after.get("part_jobs", []) if isinstance(item, dict) and item.get("part_job_id") == part_id),
            {},
        )
        ok = (
            after.get("accepted_part_results") == accepted_before
            and len(job_after.get("attempts", [])) == attempt_count + 1
        )
        return ok, None if ok else "Revision did not add exactly one attempt while preserving acceptance."

    result = await _execute_action_lifecycle(
        action, state, refresh, execute, language=language, verify=verify
    )
    if result is not None:
        state["revision_draft"] = ""
    return result


async def _continue_work_design_async(
    backend: WorkflowConsoleBackend,
    action: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> dict[str, Any] | None:
    from uuid import uuid4

    work_id = str(action["target_work_id"])
    before = backend._read_work_manifest(work_id)
    accepted_before = deepcopy(before.get("accepted_part_results"))
    reference_count = len(before.get("artifact_references", []))
    part_count = len(before.get("part_jobs", []))

    def execute() -> dict[str, Any]:
        return backend.run_work_design_episode(
            work_id,
            request_id=f"work_design_{uuid4().hex}",
        )

    def verify(result: dict[str, Any]) -> tuple[bool, str | None]:
        after = backend._read_work_manifest(work_id)
        episode = result.get("episode") if isinstance(result.get("episode"), dict) else {}
        evidence_persisted = len(after.get("artifact_references", [])) > reference_count
        parts_valid = (
            len(after.get("part_jobs", [])) > part_count
            if episode.get("status") == "completed"
            else len(after.get("part_jobs", [])) == part_count
        )
        ok = (
            after.get("accepted_part_results") == accepted_before
            and evidence_persisted
            and parts_valid
        )
        return ok, None if ok else "Work Design evidence or Part Job transition was not persisted as expected."

    result = await _execute_action_lifecycle(
        action,
        state,
        refresh,
        execute,
        language=language,
        verify=verify,
        terminal=lambda value: _agent_terminal_outcome(action, value, language),
    )
    return result


def _agent_terminal_outcome(
    action: dict[str, Any],
    result: dict[str, Any],
    language: str,
) -> tuple[str, str, str]:
    """Map persisted typed Episode evidence to a user-visible terminal state."""

    container = result.get("episode") if isinstance(result, dict) else None
    if isinstance(container, dict) and isinstance(container.get("episode"), dict):
        container = container["episode"]
    episode = container if isinstance(container, dict) else {}
    scope = str(action.get("scope_label") or "Work Design")
    status = str(episode.get("status") or "")
    stop_reason = str(episode.get("stop_reason") or "")
    reviewable = bool(
        episode.get("reviewable_result_id")
        or (isinstance(result, dict) and result.get("reviewable_result_id"))
    )
    if status == "completed" or stop_reason in {"completed", "completed_with_reviewable_result"}:
        if reviewable:
            return (
                "succeeded",
                f"{scope}：结果已可供审查。" if language == "zh" else f"{scope}: a result is ready for review.",
                "reviewable_result_ready",
            )
        return (
            "succeeded",
            f"{scope}：设计活动已完成。" if language == "zh" else f"{scope}: design activity completed.",
            "completed",
        )
    messages = {
        "user_input_required": (
            "warning",
            f"{scope}：需要你的输入才能继续。" if language == "zh" else f"{scope}: your input is needed to continue.",
            "user_input_required",
        ),
        "provider_failure": (
            "failed",
            f"{scope}：Provider 请求失败。" if language == "zh" else f"{scope}: the provider request failed.",
            "provider_failure",
        ),
        "validation_exhausted": (
            "failed",
            f"{scope}：设计已停止，几何验证次数已用尽。" if language == "zh" else f"{scope}: design stopped after validation was exhausted.",
            "validation_exhausted",
        ),
        "execution_exhausted": (
            "failed",
            f"{scope}：设计已停止，执行次数已用尽。" if language == "zh" else f"{scope}: design stopped after execution was exhausted.",
            "execution_exhausted",
        ),
        "unsupported_capability": (
            "warning",
            f"{scope}：当前能力不支持此设计路径。" if language == "zh" else f"{scope}: this design path is not currently supported.",
            "unsupported_capability",
        ),
        "sandbox_unavailable": (
            "failed",
            f"{scope}：本地 CAD 执行环境不可用。" if language == "zh" else f"{scope}: the local CAD runtime is unavailable.",
            "environment_runtime_failure",
        ),
        "policy_blocked": (
            "failed",
            f"{scope} 已停止。" if language == "zh" else f"{scope} stopped.",
            "policy_block",
        ),
        "budget_exhausted": (
            "warning",
            f"{scope}：本次 Agent 预算已用尽。" if language == "zh" else f"{scope}: this Agent attempt exhausted its budget.",
            "budget_exhausted",
        ),
        "insufficient_context": (
            "warning",
            f"{scope}：仍需要更多设计信息。" if language == "zh" else f"{scope}: more design context is required.",
            "user_input_required",
        ),
    }
    if stop_reason in messages:
        return messages[stop_reason]
    return (
        "failed",
        f"{scope}：设计已停止（{stop_reason or status or 'unknown'}）。"
        if language == "zh"
        else f"{scope}: design stopped ({stop_reason or status or 'unknown'}).",
        stop_reason or status or "unknown_failure",
    )


async def _continue_agent_async(
    backend: WorkflowConsoleBackend,
    action: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> dict[str, Any] | None:
    from uuid import uuid4

    work_id = str(action["target_work_id"])
    part_id = str(action["part_job_id"])
    before = backend._read_work_manifest(work_id)
    accepted_before = deepcopy(before.get("accepted_part_results"))
    reference_count = len(before.get("artifact_references", []))
    job_before = next(
        (
            item
            for item in before.get("part_jobs", [])
            if isinstance(item, dict) and item.get("part_job_id") == part_id
        ),
        {},
    )
    attempt_count = len(job_before.get("attempts", []))
    parent_run_id = action.get("target_run_id")
    if not isinstance(parent_run_id, str):
        parent_run_id = job_before.get("active_attempt_run_id")
    recovery_new_attempt = action.get("recovery_mode") == "new_attempt"
    created_run_id: str | None = None
    original_action = action

    if recovery_new_attempt and _pending_action_matches(state, original_action):
        return None

    # A retry is deliberately two phase.  The child Run is durable and visible
    # before the provider episode starts, so a refresh cannot leave a parent
    # attempt looking as if it were being mutated.
    if recovery_new_attempt:
        if not isinstance(parent_run_id, str):
            raise ValueError("A recovery attempt requires its parent Run.")
        try:
            created = backend.create_work_part_attempt(
                work_id,
                part_id,
                role=(str(job_before["role"]) if isinstance(job_before.get("role"), str) else None),
                parent_run_id=parent_run_id,
            )
        except Exception as exc:
            failed = ActionExecutionState.from_action(
                original_action,
                status="failed",
                message=_runtime_message(original_action, language, "failed"),
            )
            failed.completed_at = datetime.now(timezone.utc).isoformat()
            failed.command_acknowledged = True
            failed.error_code = type(exc).__name__
            failed.error_detail = str(exc)
            failed.runtime_outcome = "environment_runtime_failure"
            _set_action_execution(state, failed, original_action)
            refresh()
            return None
        created_job = created.get("part_job") if isinstance(created, dict) and isinstance(created.get("part_job"), dict) else {}
        created_run_id = created_job.get("active_attempt_run_id")
        if not isinstance(created_run_id, str) or created_run_id == parent_run_id:
            raise RuntimeError("Recovery did not create a distinct Part attempt Run.")
        # The runtime target follows the child.  This refresh is intentionally
        # before _execute_action_lifecycle yields/runs the long provider call.
        action = {
            **action,
            "target_run_id": created_run_id,
            "target_stage_id": f"attempt:{part_id}:{created_run_id}",
        }
        pending = ActionExecutionState.from_action(action, message=_runtime_message(action, language, "pending"))
        pending.command_acknowledged = True
        pending.runtime_outcome = "running"
        _set_action_execution(state, pending, action)
        action_executions(state)[_action_identity_key(original_action)] = state[
            "action_execution"
        ]
        refresh()

    def execute() -> dict[str, Any]:
        if recovery_new_attempt:
            episode = _run_part_episode_coalesced(
                backend,
                work_id,
                part_id,
                request_id=f"workbench_{uuid4().hex}",
                attempt_run_id=created_run_id,
            )
            return {"attempt": created, **episode}
        return _run_part_episode_coalesced(
            backend,
            work_id,
            part_id,
            request_id=f"workbench_{uuid4().hex}",
            attempt_run_id=(
                action.get("target_run_id")
                if isinstance(action.get("target_run_id"), str)
                else None
            ),
        )

    def verify(_result: dict[str, Any]) -> tuple[bool, str | None]:
        after = backend._read_work_manifest(work_id)
        job_after = next(
            (
                item
                for item in after.get("part_jobs", [])
                if isinstance(item, dict) and item.get("part_job_id") == part_id
            ),
            {},
        )
        if recovery_new_attempt:
            created_attempt = next(
                (
                    item
                    for item in job_after.get("attempts", [])
                    if isinstance(item, dict) and item.get("run_id") == created_run_id
                ),
                {},
            )
            ok = (
                after.get("accepted_part_results") == accepted_before
                and len(after.get("artifact_references", [])) > reference_count
                and len(job_after.get("attempts", [])) == attempt_count + 1
                and isinstance(created_run_id, str)
                and created_run_id != parent_run_id
                and created_attempt.get("parent_run_id") == parent_run_id
            )
            return (
                ok,
                None
                if ok
                else "Recovery did not append one child attempt with preserved acceptance and new evidence.",
            )
        ok = (
            after.get("accepted_part_results") == accepted_before
            and len(after.get("artifact_references", [])) > reference_count
        )
        return ok, None if ok else "Agent activity did not persist new evidence or changed acceptance."

    try:
        return await _execute_action_lifecycle(
            action,
            state,
            refresh,
            execute,
            language=language,
            verify=verify,
            terminal=lambda value: _agent_terminal_outcome(action, value, language),
            already_pending=recovery_new_attempt,
        )
    finally:
        if recovery_new_attempt:
            action_executions(state).pop(
                _action_identity_key(original_action),
                None,
            )


# In-process coalescing is intentionally small: durable Work state remains the
# product authority, while this prevents two browser surfaces from starting the
# same active Part/Attempt request concurrently.
_INFLIGHT_PART_EPISODES: dict[tuple[str, str, str], asyncio.Task[dict[str, Any]]] = {}
_INFLIGHT_PART_CALLS: dict[tuple[str, str, str], Future[dict[str, Any]]] = {}
_INFLIGHT_PART_CALLS_GUARD = threading.Lock()
_PART_EPISODE_SLOTS = threading.BoundedSemaphore(2)


def _run_part_episode_coalesced(
    backend: WorkflowConsoleBackend,
    work_id: str,
    part_id: str,
    *,
    request_id: str,
    attempt_run_id: str | None,
) -> dict[str, Any]:
    """Share one concurrent provider call for the same durable Part attempt."""

    run_id = str(attempt_run_id or "")
    key = (work_id, part_id, run_id)
    with _INFLIGHT_PART_CALLS_GUARD:
        future = _INFLIGHT_PART_CALLS.get(key)
        owner = future is None
        if future is None:
            future = Future()
            _INFLIGHT_PART_CALLS[key] = future
    if owner:
        try:
            with _PART_EPISODE_SLOTS:
                result = backend.run_work_part_design_episode(
                    work_id,
                    part_id,
                    request_id=request_id,
                    attempt_run_id=attempt_run_id,
                )
            future.set_result(result)
        except BaseException as exc:
            future.set_exception(exc)
        finally:
            with _INFLIGHT_PART_CALLS_GUARD:
                if _INFLIGHT_PART_CALLS.get(key) is future:
                    _INFLIGHT_PART_CALLS.pop(key, None)
    return future.result()


def _frontier_request_fingerprint(work_id: str, targets: list[dict[str, Any]]) -> str:
    payload = {
        "work_id": work_id,
        "parts": sorted([
            {
                "part_job_id": str(item.get("part_job_id") or ""),
                "attempt_run_id": str(item.get("target_run_id") or ""),
            }
            for item in targets
        ], key=lambda item: (item["part_job_id"], item["attempt_run_id"])),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


async def _design_runnable_parts_async(
    backend: WorkflowConsoleBackend,
    action: dict[str, Any],
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> dict[str, Any]:
    """Run a durable multi-Part frontier with a bounded local concurrency of two."""
    from uuid import uuid4

    work_id = str(action["target_work_id"])
    targets = [item for item in action.get("part_targets", []) if isinstance(item, dict)]
    targets = [item for item in targets if isinstance(item.get("part_job_id"), str) and isinstance(item.get("target_run_id"), str)]
    fingerprint = str(action.get("request_fingerprint") or _frontier_request_fingerprint(work_id, targets))
    if not targets:
        raise ValueError("No runnable Part attempts were selected.")

    scoped_actions = [
        {
            "key": "continue_agent",
            "label": item.get("label") or "Continue Agent",
            "scope_label": item.get("scope_label"),
            "target_work_id": work_id,
            "part_job_id": item["part_job_id"],
            "target_run_id": item["target_run_id"],
            "target_stage_id": f"attempt:{item['part_job_id']}:{item['target_run_id']}",
            "request_fingerprint": fingerprint,
        }
        for item in targets
    ]
    for scoped in scoped_actions:
        if active_execution_for(state, scoped) is None:
            pending = ActionExecutionState.from_action(scoped, message=_runtime_message(scoped, language, "pending"))
            pending.command_acknowledged = True
            pending.runtime_outcome = "running"
            _set_action_execution(state, pending, scoped)
    pending_refresh = getattr(refresh, "pending", None)
    (pending_refresh if callable(pending_refresh) else refresh)()

    async def run_one(scoped: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        part_id = str(scoped["part_job_id"])
        run_id = str(scoped["target_run_id"])
        key = (work_id, part_id, run_id)

        async def invoke() -> dict[str, Any]:
            def invoke_bounded() -> dict[str, Any]:
                return _run_part_episode_coalesced(
                    backend,
                    work_id,
                    part_id,
                    request_id=f"frontier_{fingerprint[:12]}_{uuid4().hex}",
                    attempt_run_id=run_id,
                )

            return await asyncio.to_thread(invoke_bounded)

        task = _INFLIGHT_PART_EPISODES.get(key)
        if task is None:
            task = asyncio.create_task(invoke())
            _INFLIGHT_PART_EPISODES[key] = task
        try:
            result = await task
            terminal_status, message, outcome = _agent_terminal_outcome(scoped, result, language)
            execution = ActionExecutionState.from_action(scoped, status=terminal_status, message=message)
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            execution.command_acknowledged = True
            execution.postcondition_verified = True
            execution.runtime_outcome = outcome
            _set_action_execution(state, execution, scoped)
            return part_id, {"ok": terminal_status != "failed", "result": result}
        except Exception as exc:
            failed = ActionExecutionState.from_action(scoped, status="failed", message=_runtime_message(scoped, language, "failed"))
            failed.completed_at = datetime.now(timezone.utc).isoformat()
            failed.command_acknowledged = True
            failed.error_code = type(exc).__name__
            failed.error_detail = str(exc)
            failed.runtime_outcome = "environment_runtime_failure"
            _set_action_execution(state, failed, scoped)
            return part_id, {"ok": False, "error": str(exc)}
        finally:
            if task.done():
                _INFLIGHT_PART_EPISODES.pop(key, None)
            # Each terminal result gets an independent canonical re-projection;
            # one failing Part does not hide sibling progress.
            refresh()

    outcomes = await asyncio.gather(*(run_one(scoped) for scoped in scoped_actions))
    result = {"ok": all(item["ok"] for _, item in outcomes), "request_fingerprint": fingerprint, "parts": dict(outcomes)}
    state["surface_action_result"] = result
    return result


async def _answer_and_continue_agent_async(
    backend: WorkflowConsoleBackend,
    recovery: dict[str, Any],
    question: dict[str, Any],
    answer: str | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
    *,
    source_action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from uuid import uuid4

    work_id = str(_dict_get(_dict_get(state.get("_last_page_data"), "selected_work"), "work_id") or state.get("selected_work_id") or "")
    part_id = str(recovery.get("part_job_id") or "")
    action = {
        **(dict(source_action) if isinstance(source_action, dict) else {}),
        "key": (
            str(source_action.get("key"))
            if isinstance(source_action, dict) and source_action.get("key")
            else ("continue_agent" if part_id else "continue_work_design")
        ),
        "label": "Answer and continue",
        "target_work_id": (
            source_action.get("target_work_id")
            if isinstance(source_action, dict)
            else work_id
        ),
        "part_job_id": part_id or None,
        "target_run_id": recovery.get("run_id"),
    }
    work_id = str(action["target_work_id"])
    if not answer or not answer.strip():
        failed = ActionExecutionState.from_action(action, status="failed", message=_runtime_message(action, language, "failed"))
        failed.error_detail = "请先回答问题。" if language == "zh" else "Answer the question first."
        _set_action_execution(state, failed, action)
        refresh()
        return None
    before = backend._read_work_manifest(work_id)
    reference_count = len(before.get("artifact_references", []))
    accepted_before = deepcopy(before.get("accepted_part_results"))

    def execute() -> dict[str, Any]:
        common = {
            "run_id": str(recovery.get("run_id")),
            "answer_id": f"answer_{uuid4().hex}",
            "question_artifact_id": str(recovery.get("question_artifact_id")),
            "field": str(question.get("field") or "clarification"),
            "question": str(question.get("question") or recovery.get("summary") or "Clarification"),
            "answer": answer.strip(),
        }
        objective = (
            "Continue the design using this user clarification: "
            f"{question.get('field') or 'clarification'} = {answer.strip()}"
        )
        if part_id:
            answer_result = backend.answer_work_part_design_question(work_id, part_id, **common)
            episode = backend.run_work_part_design_episode(
                work_id,
                part_id,
                request_id=f"answer_continue_{uuid4().hex}",
                attempt_run_id=str(recovery.get("run_id")),
                objective=objective,
            )
        else:
            answer_result = backend.answer_work_design_question(work_id, **common)
            episode = backend.run_work_design_episode(
                work_id,
                request_id=f"answer_continue_{uuid4().hex}",
                objective=objective,
            )
        return {"answer": answer_result, "episode": episode}

    def verify(_result: dict[str, Any]) -> tuple[bool, str | None]:
        after = backend._read_work_manifest(work_id)
        ok = after.get("accepted_part_results") == accepted_before and len(after.get("artifact_references", [])) >= reference_count + 2
        return ok, None if ok else "Clarification evidence or resumed Agent evidence was not persisted."

    return await _execute_action_lifecycle(
        action,
        state,
        refresh,
        execute,
        language=language,
        verify=verify,
        terminal=lambda value: _agent_terminal_outcome(action, value, language),
    )


async def _revise_blocked_request_async(
    backend: WorkflowConsoleBackend,
    overview: dict[str, Any],
    revision: str | None,
    state: dict[str, Any],
    refresh: Callable[[], None],
    language: str,
) -> dict[str, Any] | None:
    from uuid import uuid4

    work = overview.get("work") if isinstance(overview.get("work"), dict) else {}
    advanced = overview.get("advanced") if isinstance(overview.get("advanced"), dict) else {}
    work_id = str(advanced.get("work_id") or state.get("selected_work_id") or "")
    part_id = str(work.get("active_part") or "")
    action = {"key": "revise_result", "label": "Revise design request", "target_work_id": work_id, "part_job_id": part_id}
    if not revision or not revision.strip():
        failed = ActionExecutionState.from_action(action, status="failed", message=_runtime_message(action, language, "failed"))
        failed.error_detail = "请先描述修改后的要求。" if language == "zh" else "Describe the revised request first."
        _set_action_execution(state, failed, action)
        refresh()
        return None
    before = backend._read_work_manifest(work_id)
    accepted_before = deepcopy(before.get("accepted_part_results"))

    def execute() -> dict[str, Any]:
        attempt = backend.create_work_part_attempt(work_id, part_id, prompt=revision.strip(), role="Revised primary design part")
        run_id = attempt["part_job"]["active_attempt_run_id"]
        episode = backend.run_work_part_design_episode(work_id, part_id, request_id=f"revision_{uuid4().hex}", attempt_run_id=run_id, objective=revision.strip())
        return {"attempt": attempt, "episode": episode}

    def verify(_result: dict[str, Any]) -> tuple[bool, str | None]:
        after = backend._read_work_manifest(work_id)
        return (after.get("accepted_part_results") == accepted_before, "Revision changed an accepted-result pointer." if after.get("accepted_part_results") != accepted_before else None)

    return await _execute_action_lifecycle(action, state, refresh, execute, language=language, verify=verify)
