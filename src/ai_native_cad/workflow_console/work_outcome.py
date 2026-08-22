"""Read-only user outcome projection for one Work or Part attempt."""

from __future__ import annotations

from typing import Any


def project_stopped_attempt(
    *,
    stop_reason: str,
    episode: dict[str, Any] | None,
    agent_items: list[dict[str, Any]] | None,
    scope_label: str,
    language: str,
    failure_diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Explain a typed stop from persisted boundary facts, never payload inference."""

    language = "zh" if language == "zh" else "en"
    episode = episode if isinstance(episode, dict) else {}
    _ = agent_items  # Compatibility input: Agent payload shape is not causality evidence.
    diagnostic = (
        failure_diagnostic
        if isinstance(failure_diagnostic, dict)
        else episode.get("failure_diagnostic")
        if isinstance(episode.get("failure_diagnostic"), dict)
        else None
    )
    if isinstance(diagnostic, dict) and episode.get("contract_repair_exhausted") is True:
        # Older persisted diagnostics may predate the two repair fields while
        # the immutable episode summary already records them.
        repair_turn_count = diagnostic.get("contract_repair_turn_count")
        if not isinstance(repair_turn_count, int):
            repair_turn_count = episode.get("contract_repair_turn_count")
        diagnostic = {
            **diagnostic,
            "contract_repair_exhausted": True,
            "contract_repair_turn_count": repair_turn_count,
        }
    geometry_generated = episode.get("execution_succeeded") is True
    result_published = bool(episode.get("reviewable_result_id"))

    if stop_reason == "policy_blocked" and diagnostic is not None:
        return _project_policy_diagnostic(
            diagnostic,
            scope_label=scope_label,
            language=language,
            geometry_generated=geometry_generated,
            result_published=result_published,
        )

    if stop_reason == "policy_blocked":
        return {
            "title": _title(scope_label, language),
            "state": "blocked",
            "cause_category": "historical_policy_block",
            "resolution_owner": "unknown_historical",
            "what_happened": (
                "这是一次历史策略阻止的尝试；结果未发布。"
                if language == "zh"
                else "This is a historical policy-blocked attempt; its result was not published."
            ),
            "why": (
                "当时保存的证据只记录了类型化停止原因，没有保存被拒绝的动作或更具体的本地原因。"
                if language == "zh"
                else "The evidence saved at the time records the typed stop, but not the rejected action or a more specific local cause."
            ),
            "impact": _impact(
                language,
                geometry_generated=geometry_generated,
                result_published=result_published,
            ),
            "next_action": (
                f"开始新的 {scope_label} 尝试"
                if language == "zh"
                else f"Start a new {scope_label} attempt"
            ),
            "recovery_action_key": "start_new_attempt",
            "user_input_required": False,
            "retryable": False,
            "retry_reason": (
                "历史证据不足，无法承诺重复相同动作会解决问题。"
                if language == "zh"
                else "Historical evidence is insufficient to promise that repeating the same action will help."
            ),
            "code_executed": geometry_generated,
            "geometry_generated": geometry_generated,
            "result_published": result_published,
            "technical_reason": "policy_blocked_historical_unspecified",
            "typed_stop_reason": stop_reason,
            "historical_diagnostic_missing": True,
        }

    return {
        "title": _title(scope_label, language),
        "state": "stopped",
        "cause_category": str(stop_reason),
        "resolution_owner": "cadflow",
        "what_happened": (
            "本次有界设计尝试已停止。"
            if language == "zh"
            else "This bounded design attempt stopped."
        ),
        "why": str(stop_reason).replace("_", " "),
        "impact": _impact(
            language,
            geometry_generated=geometry_generated,
            result_published=result_published,
        ),
        "next_action": "查看当前建议" if language == "zh" else "Follow the current recommendation",
        "recovery_action_key": "view_details",
        "user_input_required": stop_reason == "user_input_required",
        "retryable": False,
        "code_executed": geometry_generated,
        "geometry_generated": geometry_generated,
        "result_published": result_published,
        "technical_reason": stop_reason,
        "typed_stop_reason": stop_reason,
    }


def _project_policy_diagnostic(
    diagnostic: dict[str, Any],
    *,
    scope_label: str,
    language: str,
    geometry_generated: bool,
    result_published: bool,
) -> dict[str, Any]:
    stage = str(diagnostic.get("rejection_stage") or "unknown_policy_boundary")
    reason_code = str(diagnostic.get("reason_code") or "policy_blocked_unspecified")
    rejected_action = diagnostic.get("rejected_action")
    requested = diagnostic.get("requested_capability_or_context")
    side_effect_started = diagnostic.get("side_effect_started") is True
    contract_repair_exhausted = diagnostic.get("contract_repair_exhausted") is True
    raw_repair_turn_count = diagnostic.get("contract_repair_turn_count")
    contract_repair_turn_count = (
        raw_repair_turn_count
        if isinstance(raw_repair_turn_count, int) and raw_repair_turn_count >= 0
        else 0
    )
    category, owner, retryable, action_key = _diagnostic_policy(stage, reason_code)
    action_text = str(rejected_action or ("Agent action" if language != "zh" else "Agent 动作"))
    requested_text = str(requested) if requested else None

    if contract_repair_exhausted:
        what = (
            "Agent 连续提交了不符合要求的动作。"
            if language == "zh"
            else "The Agent repeatedly submitted actions that did not meet the required contract."
        )
        if contract_repair_turn_count:
            why = (
                f"CadFlow 在 {contract_repair_turn_count} 次纠正后停止了本次尝试。"
                + (f"最后一个无效字段：{requested_text}。" if requested_text else "")
                if language == "zh"
                else f"CadFlow stopped this attempt after {contract_repair_turn_count} correction attempts."
                + (f" Last invalid field: {requested_text}." if requested_text else "")
            )
        else:
            why = (
                "CadFlow 在允许的纠正次数用尽后停止了本次尝试。"
                + (f"最后一个无效字段：{requested_text}。" if requested_text else "")
                if language == "zh"
                else "CadFlow stopped this attempt after the allowed correction attempts were used."
                + (f" Last invalid field: {requested_text}." if requested_text else "")
            )
    elif category == "agent_action_problem":
        what = (
            f"Agent 返回的 {action_text} 动作未通过 CadFlow 的有界动作校验。"
            if language == "zh"
            else f"The Agent's {action_text} action did not pass CadFlow's bounded action validation."
        )
        why = (
            f"该动作请求了不属于当前合约或 Skill 的内容：{requested_text}。"
            if language == "zh" and requested_text
            else "该动作不符合当前动作合约或 Skill 权限。"
            if language == "zh"
            else f"The action requested content outside its contract or Skill authority: {requested_text}."
            if requested_text
            else "The action did not match its current contract or Skill authority."
        )
    elif category == "context_permission_problem":
        what = (
            f"Agent 的 {action_text} 请求未获得所需上下文。"
            if language == "zh"
            else f"The Agent's {action_text} request could not receive the requested context."
        )
        why = (
            f"上下文 {requested_text} 不在当前 Skill 或 Work 范围内。"
            if language == "zh" and requested_text
            else "请求的上下文不在当前 Skill 或 Work 范围内。"
            if language == "zh"
            else f"Context {requested_text} is outside the active Skill or Work scope."
            if requested_text
            else "The requested context is outside the active Skill or Work scope."
        )
    elif category == "generated_code_policy_problem":
        what = (
            "Agent 生成的 CAD 程序未通过本地源码策略。"
            if language == "zh"
            else "The Agent-generated CAD program did not pass the local source policy."
        )
        why = (
            f"CadFlow 在隔离执行前拒绝了策略代码 {reason_code}。"
            if language == "zh"
            else f"CadFlow rejected policy code {reason_code} before isolated execution."
        )
    elif category == "publication_integrity_problem":
        what = (
            "本地评估完成，但 CadFlow 未能发布可审查结果。"
            if language == "zh"
            else "Local evaluation completed, but CadFlow could not publish a reviewable result."
        )
        why = (
            f"发布完整性检查记录了代码 {reason_code}。"
            if language == "zh"
            else f"The publication-integrity check recorded code {reason_code}."
        )
    elif category == "environment_problem":
        what = (
            "本地 CAD 执行或发布边界未能完成。"
            if language == "zh"
            else "The local CAD execution or publication boundary could not complete."
        )
        why = (
            f"CadFlow 记录了本地失败代码 {reason_code}。"
            if language == "zh"
            else f"CadFlow recorded local failure code {reason_code}."
        )
    else:
        what = (
            "Agent 报告了策略阻止，但 CadFlow 没有记录本地拒绝动作。"
            if language == "zh"
            else "The Agent reported a policy block, but CadFlow recorded no local rejected action."
        )
        why = (
            "持久证据保留了类型化报告；它不能证明 CadFlow 的某条本地策略拒绝了请求。"
            if language == "zh"
            else "The durable evidence preserves the typed report; it does not prove that a particular CadFlow policy rejected the request."
        )

    return {
        "title": _title(scope_label, language),
        "state": "blocked",
        "cause_category": category,
        "resolution_owner": owner,
        "what_happened": what,
        "why": why,
        "impact": _impact(
            language,
            geometry_generated=geometry_generated,
            result_published=result_published,
        ),
        "next_action": _next_action_label(
            action_key,
            scope_label=scope_label,
            language=language,
        ),
        "recovery_action_key": action_key,
        "user_input_required": action_key == "modify_request",
        "retryable": retryable,
        "retry_reason": (
            "新的有界尝试可以让 Agent 选择符合当前边界的动作。"
            if language == "zh" and retryable
            else "A new bounded attempt can let the Agent choose an action within the current boundary."
            if retryable
            else "重复相同动作不会解决已记录的本地边界问题。"
            if language == "zh"
            else "Repeating the same action will not resolve the recorded local boundary problem."
        ),
        "code_executed": side_effect_started or geometry_generated,
        "geometry_generated": geometry_generated,
        "result_published": result_published,
        "technical_reason": reason_code,
        "rejection_stage": stage,
        "rejected_action": rejected_action,
        "requested_capability_or_context": requested,
        "human_safe_detail": diagnostic.get("human_safe_detail"),
        "side_effect_started": side_effect_started,
        "typed_stop_reason": "policy_blocked",
        "historical_diagnostic_missing": False,
        "contract_repair_exhausted": contract_repair_exhausted,
        "contract_repair_turn_count": contract_repair_turn_count,
    }


def _diagnostic_policy(stage: str, reason_code: str) -> tuple[str, str, bool, str]:
    if stage.startswith("context_"):
        if reason_code == "context_not_available":
            return "context_permission_problem", "user", False, "modify_request"
        return "context_permission_problem", "agent", True, "start_new_attempt"
    if stage in {
        "action_contract_validation",
        "skill_action_authorization",
        "episode_action_ordering",
        "work_design_authority",
        "tool_input_validation",
        "tool_authorization",
    }:
        return "agent_action_problem", "agent", True, "start_new_attempt"
    if stage == "generated_code_policy":
        return "generated_code_policy_problem", "agent", True, "start_new_attempt"
    if stage in {
        "local_execution_environment",
        "local_execution_runtime",
        "tool_execution",
    }:
        return "environment_problem", "environment", False, "check_environment"
    if stage == "reviewable_publication":
        return "publication_integrity_problem", "cadflow", False, "no_user_action"
    return "agent_reported_policy_block", "agent", False, "start_new_attempt"


def _title(scope_label: str, language: str) -> str:
    return f"{scope_label} 设计已停止" if language == "zh" else f"{scope_label} design stopped"


def _impact(
    language: str,
    *,
    geometry_generated: bool,
    result_published: bool,
) -> str:
    if result_published:
        return "已存在可审查结果。" if language == "zh" else "A reviewable result exists."
    if geometry_generated:
        return (
            "已生成局部几何证据，但没有发布可审查 CAD 结果。"
            if language == "zh"
            else "Local geometry evidence was generated, but no reviewable CAD result was published."
        )
    return (
        "没有执行成功的 CAD 几何，也没有发布结果。"
        if language == "zh"
        else "No CAD geometry completed successfully and no result was published."
    )


def _next_action_label(action_key: str, *, scope_label: str, language: str) -> str:
    labels = {
        "start_new_attempt": (
            f"开始新的 {scope_label} 尝试"
            if language == "zh"
            else f"Start a new {scope_label} attempt"
        ),
        "modify_request": "补充设计要求" if language == "zh" else "Add design context",
        "check_environment": "检查本地执行环境" if language == "zh" else "Check local execution",
        "no_user_action": "当前无需你操作" if language == "zh" else "No user action is currently available",
    }
    return labels.get(
        action_key,
        "查看当前建议" if language == "zh" else "Follow the current recommendation",
    )
