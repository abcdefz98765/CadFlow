"""State-specific NiceGUI surface for a stopped Part design attempt."""

from __future__ import annotations

from typing import Any


def render_stopped_attempt(ui: Any, recovery: dict[str, Any], language: str) -> None:
    """Answer the owner blocked-case questions without requiring JSON."""

    if not recovery:
        return
    with ui.element("section").classes("attempt-outcome w-full mt-3"):
        ui.label(str(recovery.get("title") or "Design stopped")).classes(
            "text-lg font-semibold"
        )
        what_happened = recovery.get("what_happened") or recovery.get("summary")
        why = recovery.get("why") or recovery.get("why_it_stopped")
        if what_happened:
            ui.label("发生了什么" if language == "zh" else "What happened").classes(
                "workflow-eyebrow mt-2"
            )
            ui.label(str(what_happened)).classes("text-sm")
        if why:
            ui.label("停止原因" if language == "zh" else "Why it stopped").classes(
                "workflow-eyebrow mt-2"
            )
            ui.label(str(why)).classes("text-sm text-gray-700")
        facts = (
            (
                "已生成几何" if language == "zh" else "Geometry generated",
                recovery.get("geometry_generated") is True,
            ),
            (
                "已发布 CAD 结果" if language == "zh" else "CAD result published",
                recovery.get("result_published") is True,
            ),
            (
                "需要你的输入" if language == "zh" else "Needs your input",
                recovery.get("user_input_required") is True,
            ),
            (
                "重试有用" if language == "zh" else "Retry is useful",
                recovery.get("retryable") is True,
            ),
        )
        with ui.element("div").classes("attempt-fact-grid w-full mt-3"):
            for label, value in facts:
                with ui.element("div").classes("attempt-fact"):
                    ui.label(label).classes("text-xs text-gray-500")
                    ui.label(
                        ("是" if language == "zh" else "Yes")
                        if value
                        else ("否" if language == "zh" else "No")
                    ).classes(
                        "text-sm font-semibold "
                        + ("text-green-700" if value else "text-gray-700")
                    )
        if recovery.get("impact"):
            ui.label(str(recovery["impact"])).classes("text-sm font-medium mt-3")
        if recovery.get("next_action"):
            ui.label("下一步" if language == "zh" else "Next").classes(
                "workflow-eyebrow mt-3"
            )
            ui.label(str(recovery["next_action"])).classes(
                "text-sm font-semibold text-blue-700"
            )
