"""Small canonical Work state and command authority for normal UI surfaces."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def project_canonical_interaction(
    *,
    work_id: str,
    work_design: dict[str, Any],
    parts: list[dict[str, Any]],
    current_result: dict[str, Any] | None,
    recovery: dict[str, Any] | None,
    language: str,
) -> dict[str, Any]:
    """Return shared facts and valid commands, without page-specific fields."""

    part_commands = {
        str(part["part_job_id"]): _part_commands(work_id, part, language)
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("part_job_id"), str)
    }
    active = next(
        (
            part
            for state in ("reviewable", "design", "accepted", "not_started")
            for part in parts
            if part.get("state") == state
        ),
        parts[0] if parts else None,
    )
    primary = None
    secondary: list[dict[str, Any]] = []
    attention = "ready"
    runnable_frontier = _runnable_part_frontier(work_design, parts)
    if recovery:
        recommended = recovery.get("recommended_action") if isinstance(recovery.get("recommended_action"), dict) else {}
        key = str(recommended.get("key") or "")
        if key:
            recovery_part_id = recovery.get("part_job_id")
            part_job_id = (
                recovery_part_id
                if isinstance(recovery_part_id, str) and recovery_part_id
                else None
            )
            command_key = key
            if key == "start_new_attempt":
                command_key = "retry_agent" if part_job_id else "continue_work_design"
            recovery_command = _command(
                command_key,
                str(recommended.get("label") or key.replace("_", " ").title()),
                work_id,
                part_job_id=part_job_id,
                target_run_id=recovery.get("run_id"),
                **(
                    {"recovery_mode": "new_attempt"}
                    if key in {"start_new_attempt", "retry_agent"} and part_job_id
                    else {}
                ),
            )
            primary = recovery_command
            if part_job_id and part_job_id in part_commands:
                part_commands[part_job_id] = {
                    **part_commands[part_job_id],
                    "primary_action": recovery_command,
                }
        recovery_part_id = recovery.get("part_job_id")
        recovery_frontier = [
            item
            for item in runnable_frontier
            if item.get("part_job_id") != recovery_part_id
        ]
        if len(recovery_frontier) >= 2:
            secondary.append(
                _command(
                    "design_runnable_parts",
                    "设计可运行的零件" if language == "zh" else "Design runnable Parts",
                    work_id,
                    part_targets=recovery_frontier,
                    request_fingerprint=_frontier_fingerprint(work_id, recovery_frontier),
                )
            )
        attention = "needs_you" if key == "answer_question" else "blocked"
    elif not parts and work_design.get("status") != "completed":
        primary = _command(
            "continue_work_design",
            "继续 Work 设计" if language == "zh" else "Continue Work Design",
            work_id,
            target_run_id=work_design.get("run_id"),
        )
    elif runnable_frontier:
        primary = _command(
            "design_runnable_parts",
            "设计可运行的零件" if language == "zh" else "Design runnable Parts",
            work_id,
            part_targets=runnable_frontier,
            request_fingerprint=_frontier_fingerprint(work_id, runnable_frontier),
        )
        attention = "ready"
    elif isinstance(active, dict):
        commands = part_commands.get(str(active.get("part_job_id")), {})
        primary = commands.get("primary_action")
        secondary = list(commands.get("secondary_actions") or [])
        attention = {
            "reviewable": "review",
            "accepted": "accepted",
            "design": "ready",
            "not_started": "ready",
        }.get(str(active.get("state")), "ready")
    return {
        "state_source": "work_manifest_part_jobs_results",
        "work_state": {
            "work_design": work_design.get("status") or "not_started",
            "part_count": len(parts),
            "result": (current_result or {}).get("status") or "none",
            "attention": attention,
        },
        "work": {"primary_action": primary, "secondary_actions": secondary},
        "parts": part_commands,
    }


def _part_commands(work_id: str, part: dict[str, Any], language: str) -> dict[str, Any]:
    part_id = str(part["part_job_id"])
    run_id = part.get("latest_attempt_run_id")
    result_id = part.get("reviewable_result_id") or part.get("accepted_result_id")
    name = str(part.get("name") or part_id.replace("_", " ").title())
    state = str(part.get("state") or "not_started")
    primary = None
    secondary: list[dict[str, Any]] = []
    if state == "reviewable" and isinstance(result_id, str):
        primary = _command(
            "accept_reviewable_result",
            "接受结果" if language == "zh" else "Accept result",
            work_id,
            part_job_id=part_id,
            target_run_id=run_id,
            reviewable_result_id=result_id,
        )
        secondary.append(
            _command(
                "revise_reviewable_result",
                "从此结果创建新版本" if language == "zh" else "Start new version from this result",
                work_id,
                part_job_id=part_id,
                target_run_id=run_id,
                reviewable_result_id=result_id,
            )
        )
    elif state == "accepted" and isinstance(result_id, str):
        primary = _command(
            "revise_reviewable_result",
            "创建新版本" if language == "zh" else "Start a new version",
            work_id,
            part_job_id=part_id,
            target_run_id=run_id,
            reviewable_result_id=result_id,
        )
    else:
        has_progress = bool(part.get("has_agent_progress"))
        primary = _command(
            "continue_agent",
            (
                f"继续 {name}"
                if has_progress and language == "zh"
                else f"开始 {name} 设计"
                if language == "zh"
                else f"Continue {name}"
                if has_progress
                else f"Start {name} design"
            ),
            work_id,
            part_job_id=part_id,
            target_run_id=run_id,
        )
    return {"primary_action": primary, "secondary_actions": secondary}


def _runnable_part_frontier(work_design: dict[str, Any], parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return real, independent active attempts; descriptions never block them."""
    if str(work_design.get("status") or "") not in {"completed", "ready"}:
        return []
    frontier: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        # A reviewable/accepted result is a real terminal product state for the
        # Part.  Do not infer scheduling dependencies from prose/interfaces.
        if part.get("reviewable_result_id") or part.get("accepted_result_id"):
            continue
        if part.get("attempt_blocked") is True:
            continue
        run_id = part.get("active_attempt_run_id") or part.get("latest_attempt_run_id")
        state = str(part.get("state") or "")
        if not isinstance(run_id, str) or state not in {"design", "not_started", "ready", "incomplete", "running", "in_progress"}:
            continue
        frontier.append({
            "part_job_id": str(part.get("part_job_id")),
            "target_run_id": run_id,
            "scope_label": part.get("name") or str(part.get("part_job_id")),
            "label": "继续 Agent 设计" if state == "design" else "开始 Agent 设计",
        })
    return sorted(frontier, key=lambda item: (item["part_job_id"], item["target_run_id"])) if len(frontier) >= 2 else []


def _frontier_fingerprint(work_id: str, frontier: list[dict[str, Any]]) -> str:
    payload = {
        "work_id": work_id,
        "parts": [
            {"part_job_id": item["part_job_id"], "attempt_run_id": item["target_run_id"]}
            for item in frontier
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _command(key: str, label: str, work_id: str, **targets: Any) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "enabled": True,
        "target_work_id": work_id,
        **{name: value for name, value in targets.items() if value is not None},
    }


__all__ = ["project_canonical_interaction"]
