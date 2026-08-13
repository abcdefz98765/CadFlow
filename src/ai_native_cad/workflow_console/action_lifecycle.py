"""Bounded browser action lifecycle for the workflow console.

This module owns transient command execution state and verification. Durable
Work, Run, Part Job, result, and acceptance truth remain backend-owned.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.i18n import action_label


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


def _pending_action_matches(state: dict[str, Any], action: dict[str, Any]) -> bool:
    runtime = state.get("action_execution")
    if not isinstance(runtime, dict) or runtime.get("status") not in {"confirming", "pending"}:
        return False
    return tuple(runtime.get("identity") or ()) == _action_identity(action)


def _set_action_execution(state: dict[str, Any], execution: ActionExecutionState, action: dict[str, Any]) -> None:
    state["action_execution"] = {**asdict(execution), "identity": _action_identity(action)}


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
) -> dict[str, Any] | None:
    """Execute one write once, surface pending, then verify its persisted effect."""
    if _pending_action_matches(state, action):
        return None
    pending = ActionExecutionState.from_action(action, message=_runtime_message(action, language, "pending"))
    pending.command_acknowledged = True
    pending.runtime_outcome = "running"
    _set_action_execution(state, pending, action)
    refresh()
    # Yield after the render so browser users observe pending state before a
    # synchronous local backend operation starts.
    await asyncio.sleep(0.05)
    try:
        result = await asyncio.to_thread(execute)
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
        refresh()

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
        state["action_execution"] = {
            **asdict(ActionExecutionState.from_action(action, status="failed", message=_runtime_message(action, language, "failed"))),
            "identity": _action_identity(action),
            "error_detail": "Describe the design objective first." if language != "zh" else "请先描述设计目标。",
        }
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
            f"{scope}：设计被策略或动作契约阻止。" if language == "zh" else f"{scope}: design was blocked by policy or the action contract.",
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

    def execute() -> dict[str, Any]:
        return backend.run_work_part_design_episode(
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
        ok = (
            after.get("accepted_part_results") == accepted_before
            and len(after.get("artifact_references", [])) > reference_count
        )
        return ok, None if ok else "Agent activity did not persist new evidence or changed acceptance."

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
