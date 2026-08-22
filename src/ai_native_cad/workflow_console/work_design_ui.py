"""State-specific Work Design presentation for the Workflow inspector."""

from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(
            value.get("description")
            or value.get("summary")
            or value.get("name")
            or value.get("id")
            or value
        )
    return str(value)


def _section(ui: Any, title: str, values: list[Any]) -> None:
    if not values:
        return
    ui.label(title).classes("workflow-eyebrow mt-3")
    with ui.column().classes("gap-1"):
        for value in values:
            ui.label(f"• {_text(value)}").classes("text-sm")


def render_work_design(ui: Any, work_design: dict[str, Any], language: str) -> None:
    """Render the complete persisted Work Design proposal without technical payloads."""
    if work_design.get("concept_summary"):
        ui.label("Agent 设计" if language == "zh" else "Agent Design").classes("workflow-eyebrow mt-3")
        ui.label(str(work_design["concept_summary"])).classes("text-sm")

    generated = [item for item in work_design.get("generated_parts", []) if isinstance(item, dict)]
    if generated:
        ui.label("生成的零件" if language == "zh" else "Generated Parts").classes("workflow-eyebrow mt-3")
        with ui.column().classes("gap-1"):
            for part in generated:
                name = str(part.get("name") or part.get("part_job_id") or part.get("part_id") or "Part")
                role = str(part.get("role") or part.get("purpose") or "")
                ui.label(f"• {name}" + (f" — {role}" if role else "")).classes("text-sm")

    references = [item for item in work_design.get("reference_components", []) if isinstance(item, dict)]
    if references:
        ui.label("参考组件" if language == "zh" else "Reference Components").classes("workflow-eyebrow mt-3")
        with ui.column().classes("gap-1"):
            for component in references:
                name = str(component.get("name") or component.get("component_id") or "Reference")
                role = str(component.get("role") or component.get("purpose") or "reference-only")
                ui.label(f"• {name} — {role}").classes("text-sm")

    _section(ui, "接口" if language == "zh" else "Interfaces", list(work_design.get("interfaces") or []))
    _section(ui, "依赖" if language == "zh" else "Dependencies", list(work_design.get("dependencies") or []))
    _section(ui, "假设" if language == "zh" else "Assumptions", list(work_design.get("assumptions") or []))
    _section(ui, "未解决问题" if language == "zh" else "Unresolved Questions", list(work_design.get("unresolved_questions") or []))
    if work_design.get("recommendation"):
        ui.label("建议" if language == "zh" else "Recommendation").classes("workflow-eyebrow mt-3")
        ui.label(_text(work_design["recommendation"])).classes("text-sm font-medium")
