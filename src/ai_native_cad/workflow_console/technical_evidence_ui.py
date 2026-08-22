"""Lazy, bounded NiceGUI rendering for advanced technical evidence."""

from __future__ import annotations

import json
from typing import Any

from ai_native_cad.workflow_console.agent_activity import bounded_evidence


def render_lazy_technical_evidence(
    ui: Any,
    *,
    title: str,
    language: str,
    metadata: dict[str, Any] | None = None,
    evidence: Any = None,
    icon: str = "data_object",
    classes: str = "w-full mt-3",
) -> None:
    """Create no evidence DOM until the user explicitly expands the section."""

    body = None
    loaded = False

    def open_evidence(event: Any) -> None:
        nonlocal loaded
        if loaded or not bool(getattr(event, "value", False)):
            return
        loaded = True
        if body is None:
            return
        with body:
            for label, value in (metadata or {}).items():
                with ui.row().classes("w-full items-start justify-between gap-3"):
                    ui.label(str(label)).classes("text-xs text-gray-500")
                    ui.label(str(value if value is not None and value != "" else "—")).classes(
                        "text-xs text-right break-all"
                    )
            if evidence not in (None, {}, []):
                ui.label(
                    "浏览器显示已限制；完整的已净化证据仍保存在 Work 中。"
                    if language == "zh"
                    else "Browser rendering is bounded; complete sanitized evidence remains in the Work."
                ).classes("text-xs text-gray-500 mt-2")
                ui.markdown(
                    "```json\n"
                    + json.dumps(
                        bounded_evidence(evidence),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n```"
                ).classes("w-full mono technical-evidence-json")

    expansion = ui.expansion(
        title,
        icon=icon,
        value=False,
        on_value_change=open_evidence,
    ).classes(classes)
    with expansion:
        body = ui.column().classes("w-full gap-2")
