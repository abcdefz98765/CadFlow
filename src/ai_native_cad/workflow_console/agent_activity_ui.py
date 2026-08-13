"""NiceGUI presentation for concise Activity and lazy Technical Evidence."""

from __future__ import annotations

import json
from typing import Any

from ai_native_cad.workflow_console.agent_activity import (
    bounded_evidence,
    significant_activity,
)


def render_agent_activity(
    ui: Any,
    projection: dict[str, Any],
    language: str,
    *,
    backend: Any | None = None,
) -> None:
    """Render meaningful activity first and load exact evidence on demand."""

    items = projection.get("items") if isinstance(projection.get("items"), list) else []
    references = (
        projection.get("technical_evidence_references")
        if isinstance(projection.get("technical_evidence_references"), list)
        else []
    )
    if not items and not references:
        return
    rows = significant_activity(items, language=language)
    with ui.element("section").classes("workbench-panel workbench-agent-context w-full"):
        activity_body = None
        activity_loaded = False

        def open_activity(event: Any) -> None:
            nonlocal activity_loaded
            if activity_loaded or not bool(getattr(event, "value", False)):
                return
            activity_loaded = True
            if activity_body is None:
                return
            with activity_body:
                for row in rows:
                    with ui.row().classes("w-full items-start gap-2"):
                        ui.icon("check_circle", size="xs").classes("text-blue-600 mt-1")
                        with ui.column().classes("gap-0 flex-1"):
                            ui.label(str(row.get("label") or "")).classes("text-sm font-medium")
                            if row.get("summary"):
                                ui.label(str(row["summary"])).classes("text-xs text-gray-600")

        activity = ui.expansion(
            (f"活动 · {len(rows)}" if language == "zh" else f"Activity · {len(rows)}"),
            icon="timeline",
            on_value_change=open_activity,
        ).classes("w-full")
        with activity:
            activity_body = ui.column().classes("w-full gap-2")

        evidence_body = None
        evidence_loaded = False

        def open_evidence(event: Any) -> None:
            nonlocal evidence_loaded
            if evidence_loaded or not bool(getattr(event, "value", False)):
                return
            evidence_loaded = True
            if evidence_body is None:
                return
            loaded: list[dict[str, Any]] = []
            work_id = projection.get("work_id")
            if backend is not None and isinstance(work_id, str):
                for reference in references[:24]:
                    if not isinstance(reference, dict) or not isinstance(reference.get("artifact_id"), str):
                        continue
                    try:
                        payload = backend.read_work_artifact_reference(
                            work_id, reference["artifact_id"]
                        )
                    except (FileNotFoundError, ValueError):
                        payload = {"content": {"unavailable": True}}
                    loaded.append(
                        {
                            "reference": reference,
                            "content": payload.get("content")
                            if isinstance(payload, dict)
                            else {},
                        }
                    )
            with evidence_body:
                if not loaded:
                    ui.label(
                        "此范围没有技术证据。"
                        if language == "zh"
                        else "No Technical Evidence is available for this scope."
                    ).classes("text-sm text-gray-500")
                    return
                ui.label(
                    "精确的已净化协议与运行记录。浏览器显示已限制；完整证据仍保存在 Work 中。"
                    if language == "zh"
                    else "Exact sanitized protocol and runtime records. Browser rendering is bounded; complete evidence remains in the Work."
                ).classes("text-xs text-gray-600")
                ui.markdown(
                    "```json\n"
                    + json.dumps(
                        bounded_evidence(loaded),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n```"
                ).classes("w-full mono technical-evidence-json")

        evidence = ui.expansion(
            "技术证据" if language == "zh" else "Technical Evidence",
            icon="data_object",
            on_value_change=open_evidence,
        ).classes("w-full")
        with evidence:
            evidence_body = ui.column().classes("w-full gap-2")
