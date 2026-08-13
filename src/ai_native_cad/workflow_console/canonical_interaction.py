"""Small canonical Work state and command authority for normal UI surfaces."""

from __future__ import annotations

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
    if recovery:
        recommended = recovery.get("recommended_action") if isinstance(recovery.get("recommended_action"), dict) else {}
        key = str(recommended.get("key") or "")
        if key:
            recovery_command = _command(
                key,
                str(recommended.get("label") or key.replace("_", " ").title()),
                work_id,
                part_job_id=recovery.get("part_job_id"),
                target_run_id=recovery.get("run_id"),
            )
            primary = recovery_command
            recovery_part_id = recovery.get("part_job_id")
            if isinstance(recovery_part_id, str) and recovery_part_id in part_commands:
                part_commands[recovery_part_id] = {
                    **part_commands[recovery_part_id],
                    "primary_action": recovery_command,
                }
        attention = "needs_you" if key == "answer_question" else "blocked"
    elif not parts and work_design.get("status") != "completed":
        primary = _command(
            "continue_work_design",
            "继续 Work 设计" if language == "zh" else "Continue Work Design",
            work_id,
            target_run_id=work_design.get("run_id"),
        )
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


def _command(key: str, label: str, work_id: str, **targets: Any) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "enabled": True,
        "target_work_id": work_id,
        **{name: value for name, value in targets.items() if value is not None},
    }


__all__ = ["project_canonical_interaction"]
