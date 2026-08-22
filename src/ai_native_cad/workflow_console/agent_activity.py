"""Concise Agent activity and lazy technical-evidence helpers."""

from __future__ import annotations

from collections import Counter
from typing import Any


def significant_activity(
    items: list[dict[str, Any]] | None,
    *,
    language: str,
) -> list[dict[str, Any]]:
    """Collapse protocol repetition into product-language activity rows."""

    language = "zh" if language == "zh" else "en"
    source = [item for item in (items or []) if isinstance(item, dict)]
    keys: list[str] = []
    summaries: dict[str, str] = {}
    for item in source:
        action = str(item.get("action") or "")
        kind = str(item.get("kind") or "")
        if kind == "user_answer":
            key = "user_answer"
        elif kind == "system_observation":
            key = "observation"
        elif kind == "attempt_result":
            key = "attempt_result"
        elif action in {"propose_work_design", "create_part_jobs"}:
            key = action
        elif action == "request_context":
            key = "request_context"
        elif action in {"create_contract", "create_model_program"}:
            key = "prepared_candidate"
        elif action in {"patch_contract", "patch_model_program"}:
            key = "repaired_candidate"
        elif action in {"request_validation", "request_execution"}:
            key = "checked_candidate"
        elif action == "ask_user":
            key = "asked_user"
        elif action == "stop":
            key = "stopped"
        elif action:
            key = action
        else:
            continue
        keys.append(key)
        if item.get("summary"):
            summaries[key] = str(item["summary"])

    counts = Counter(keys)
    ordered = list(dict.fromkeys(keys))
    labels = {
        "propose_work_design": ("提出整体设计", "Proposed the overall design"),
        "create_part_jobs": ("创建生成零件", "Created the generated Parts"),
        "request_context": ("读取设计上下文", "Read design context"),
        "prepared_candidate": ("准备设计候选", "Prepared a design candidate"),
        "repaired_candidate": ("修复设计候选", "Repaired the design candidate"),
        "checked_candidate": ("检查设计候选", "Checked the design candidate"),
        "asked_user": ("向用户提问", "Asked the user"),
        "user_answer": ("记录用户回答", "Recorded the user answer"),
        "observation": ("检查系统观察", "Inspected a system observation"),
        "attempt_result": ("记录尝试结果", "Recorded the attempt outcome"),
        "stopped": ("停止设计尝试", "Stopped the design attempt"),
    }
    rows: list[dict[str, Any]] = []
    for key in ordered:
        zh, en = labels.get(key, (key.replace("_", " "), key.replace("_", " ").title()))
        label = zh if language == "zh" else en
        count = counts[key]
        if count > 1:
            label = f"{label} × {count}"
        rows.append({"key": key, "label": label, "summary": summaries.get(key), "count": count})
    return rows


def bounded_evidence(value: Any, *, max_items: int = 24) -> Any:
    """Bound browser rendering while preserving exact sanitized records."""

    if isinstance(value, list):
        values = [bounded_evidence(item, max_items=max_items) for item in value[:max_items]]
        if len(value) > max_items:
            values.append({"truncated": True, "remaining_items": len(value) - max_items})
        return values
    if isinstance(value, dict):
        return {
            str(key): bounded_evidence(item, max_items=max_items)
            for key, item in list(value.items())[:max_items]
        }
    if isinstance(value, str) and len(value) > 4000:
        return value[:4000] + "… [truncated for browser rendering]"
    return value
