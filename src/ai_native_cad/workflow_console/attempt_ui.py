"""State-specific NiceGUI surface for a stopped Part design attempt."""

from __future__ import annotations

from typing import Any


_ACTION_FORMAT_REASON_CODES = frozenset({
    "action_contract_extra_fields",
    "invalid_action_payload",
    "invalid_work_design_contract",
    "missing_context_key",
    "invalid_question_contract",
    "work_design_proposal_missing",
    "work_design_questions_unresolved",
    "work_design_completion_action_required",
})


def _is_action_format_recovery(recovery: dict[str, Any]) -> bool:
    return (
        recovery.get("contract_repair_exhausted") is True
        or str(recovery.get("technical_reason") or "") in _ACTION_FORMAT_REASON_CODES
    )


def stopped_attempt_copy(recovery: dict[str, Any], language: str) -> tuple[str, list[str]]:
    """Return a short owner-facing explanation for persisted stop evidence."""

    title = str(
        recovery.get("title")
        or ("设计已停止" if language == "zh" else "Design stopped")
    )
    messages: list[str] = []
    for value in (
        recovery.get("what_happened") or recovery.get("summary"),
        recovery.get("why") or recovery.get("why_it_stopped"),
    ):
        text = str(value or "").strip()
        if text and text not in messages:
            messages.append(text)

    owner = str(recovery.get("resolution_owner") or "cadflow")
    needs_input = recovery.get("user_input_required") is True or owner == "user"
    if needs_input:
        resolution = "需要你的输入后才能继续。" if language == "zh" else "Your input is needed before this can continue."
    elif owner == "environment":
        resolution = "本地 CAD 环境需要处理后才能重试。" if language == "zh" else "The local CAD environment needs attention before retrying."
    elif recovery.get("contract_repair_exhausted") is True:
        resolution = (
            "这是 Agent 的动作格式问题，不需要你补充设计要求。"
            if language == "zh"
            else "This is an Agent action-format issue; no additional design input is needed."
        )
    elif owner == "agent" and _is_action_format_recovery(recovery):
        resolution = (
            "Agent 需要以有效的动作格式重新提交后才能继续。"
            if language == "zh"
            else "The Agent needs to submit a valid action format before this can continue."
        )
    elif owner == "agent" and recovery.get("retryable") is True:
        resolution = (
            "可以开始新的尝试，让 Agent 选择其他允许的动作。"
            if language == "zh"
            else "A new attempt can let the Agent choose another allowed action."
        )
    elif recovery.get("retryable") is True:
        resolution = "CadFlow 可以从这里开始新的设计尝试。" if language == "zh" else "CadFlow can start a new design attempt from here."
    elif owner == "cadflow":
        resolution = "当前无需你处理；CadFlow 会保留此停止记录。" if language == "zh" else "No action is needed from you; CadFlow will retain this stopped record."
    else:
        resolution = "此尝试已停止；请查看下一步建议。" if language == "zh" else "This attempt stopped; review the recommended next step."
    messages.append(resolution)

    impact = str(recovery.get("impact") or "").strip()
    if impact and impact not in messages:
        messages.append(impact)
    elif recovery.get("geometry_generated") is True:
        messages.append(
            "已生成几何，但尚未成为可审查结果。"
            if language == "zh"
            else "Geometry was generated, but no reviewable result is available."
        )
    elif recovery.get("result_published") is False:
        messages.append(
            "未发布可审查的 CAD 结果。"
            if language == "zh"
            else "No reviewable CAD result was published."
        )
    # Keep the diagnosis legible: the reason, owner resolution, and at most one
    # outcome fact. Full audit facts remain in Technical Evidence.
    return title, messages[:4]


def render_stopped_attempt(ui: Any, recovery: dict[str, Any], language: str) -> None:
    """Answer the owner blocked-case questions without requiring JSON."""

    if not recovery:
        return
    title, messages = stopped_attempt_copy(recovery, language)
    with ui.element("section").classes("attempt-outcome w-full mt-3"):
        ui.label(title).classes("text-lg font-semibold")
        for message in messages:
            ui.label(message).classes("text-sm text-gray-700 mt-2")
