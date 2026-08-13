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
) -> dict[str, Any]:
    """Explain a typed stop without inventing Agent reasoning or state."""

    language = "zh" if language == "zh" else "en"
    episode = episode if isinstance(episode, dict) else {}
    items = [item for item in (agent_items or []) if isinstance(item, dict)]
    last_agent = next(
        (item for item in reversed(items) if item.get("kind") == "agent_response"),
        {},
    )
    action = str(last_agent.get("action") or "")
    contract_fields = {
        str(value)
        for value in last_agent.get("contract_fields", [])
        if isinstance(value, str)
    }
    geometry_generated = bool(
        episode.get("execution_succeeded")
        or episode.get("candidate_id")
        or episode.get("observation_id")
    )
    result_published = bool(episode.get("reviewable_result_id"))

    if stop_reason == "policy_blocked" and action == "create_contract" and (
        "python_code" in contract_fields or "source" in contract_fields
    ):
        return {
            "title": (
                f"{scope_label} 设计已停止"
                if language == "zh"
                else f"{scope_label} design stopped"
            ),
            "state": "blocked",
            "what_happened": (
                "Agent 返回了结构化几何合约，但其中还包含可执行源码字段。"
                if language == "zh"
                else "The Agent returned a structured geometry contract that also contained an executable-source field."
            ),
            "why": (
                "该字段不属于本次 create_contract Skill 动作，CadFlow 因此在执行前拒绝了响应。"
                if language == "zh"
                else "That field is outside the create_contract Skill action, so CadFlow rejected the response before execution."
            ),
            "impact": (
                "未生成几何，也未发布 CAD 结果。"
                if language == "zh"
                else "No geometry was generated and no CAD result was published."
            ),
            "next_action": (
                f"重试 {scope_label}"
                if language == "zh"
                else f"Retry {scope_label}"
            ),
            "user_input_required": False,
            "retryable": True,
            "geometry_generated": False,
            "result_published": False,
            "technical_reason": "structured_contract_contains_execution_field",
            "typed_stop_reason": stop_reason,
        }

    if stop_reason == "policy_blocked":
        return {
            "title": (
                f"{scope_label} 设计已停止"
                if language == "zh"
                else f"{scope_label} design stopped"
            ),
            "state": "blocked",
            "what_happened": (
                "CadFlow 拒绝了 Agent 返回的动作。"
                if language == "zh"
                else "CadFlow rejected the action returned by the Agent."
            ),
            "why": (
                "现有持久证据无法更具体地区分动作合约校验或本地策略拒绝。"
                if language == "zh"
                else "The persisted evidence does not distinguish the action-contract rejection from a more specific local policy rejection."
            ),
            "impact": (
                ("未发布 CAD 结果。" if language == "zh" else "No CAD result was published.")
                if not result_published
                else ("已存在可审查结果。" if language == "zh" else "A reviewable result exists.")
            ),
            "next_action": "查看技术证据" if language == "zh" else "Inspect Technical Evidence",
            "user_input_required": False,
            "retryable": False,
            "geometry_generated": geometry_generated,
            "result_published": result_published,
            "technical_reason": "policy_blocked_unspecified",
            "typed_stop_reason": stop_reason,
        }

    return {
        "title": (
            f"{scope_label} 设计已停止"
            if language == "zh"
            else f"{scope_label} design stopped"
        ),
        "state": "stopped",
        "what_happened": (
            "本次有界设计尝试已停止。"
            if language == "zh"
            else "This bounded design attempt stopped."
        ),
        "why": str(stop_reason).replace("_", " "),
        "impact": (
            "没有发布 CAD 结果。"
            if language == "zh" and not result_published
            else "No CAD result was published."
            if not result_published
            else "A reviewable result exists."
        ),
        "next_action": "查看当前建议" if language == "zh" else "Follow the current recommendation",
        "user_input_required": stop_reason == "user_input_required",
        "retryable": False,
        "geometry_generated": geometry_generated,
        "result_published": result_published,
        "technical_reason": stop_reason,
        "typed_stop_reason": stop_reason,
    }
