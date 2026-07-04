"""Deterministic human-readable workflow review generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WORKFLOW_REVIEW_STATUSES = {"ready_for_review", "accepted_for_preview", "needs_revision", "blocked", "incomplete"}
RISK_LEVELS = {"low", "medium", "high"}


def build_workflow_review(run_metadata: dict[str, Any]) -> dict[str, Any]:
    """Build a local deterministic workflow review from sanitized run metadata."""
    reviewed = _dict(run_metadata.get("reviewed_part_summary"))
    assembly = _dict(reviewed.get("assembly_plan"))
    part_result = _dict(reviewed.get("part_result_review"))
    stage_review = _dict(run_metadata.get("stage_review_summary"))
    status = _overall_status(run_metadata, assembly, part_result, stage_review)
    checks = _dict(part_result.get("checks"))
    downloadables = {item.get("name") for item in _list(run_metadata.get("downloadables")) if isinstance(item, dict)}
    step_present = "model.step" in downloadables or checks.get("step_created") is True
    stl_present = "model.stl" in downloadables or checks.get("stl_created") is True
    diagnostics = _diagnostic_codes(run_metadata, assembly, part_result, stage_review)
    risks = _risks(assembly, part_result, checks, step_present, stl_present)
    readiness_score = _readiness_score(status, step_present, stl_present, part_result, stage_review, risks)
    risk_level = _risk_level(status, risks, readiness_score)
    summary = _summary_lines(assembly, part_result, step_present, stl_present, stage_review)
    return {
        "schema_version": 1,
        "overall_status": status,
        "readiness_score": readiness_score,
        "confidence": {
            "requirement_understanding": _confidence_from_presence(_dict(run_metadata.get("report_summary")).get("requirement_summary")),
            "assembly_decomposition": "medium" if assembly.get("present") else "low",
            "selected_part_readiness": "high" if _dict(reviewed.get("reviewed_part_handoff")).get("present") else "medium" if _dict(reviewed.get("part_request")).get("present") else "low",
            "cad_result": "high" if step_present and stl_present else "low" if not step_present else "medium",
            "interface_correctness": "low",
        },
        "risk_level": risk_level,
        "summary": summary,
        "key_diagnostics": diagnostics[:20],
        "risks": risks,
        "recommended_next_actions": _recommended_next_actions(status, risks, step_present, stl_present, stage_review),
        "scoring_explanation": _scoring_explanation(status, step_present, stl_present, part_result, risks),
    }


def write_workflow_review_files(run_dir: Path, review: dict[str, Any]) -> dict[str, str]:
    """Write workflow_review.json and workflow_review.md into a selected run directory."""
    json_path = run_dir / "workflow_review.json"
    md_path = run_dir / "workflow_review.md"
    json_path.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_workflow_review_markdown(review), encoding="utf-8")
    return {"json": json_path.name, "markdown": md_path.name}


def render_workflow_review_markdown(review: dict[str, Any]) -> str:
    """Render a concise human-readable review report."""
    lines = [
        "# Workflow Review",
        "",
        f"- Overall status: `{review.get('overall_status')}`",
        f"- Readiness score: `{review.get('readiness_score')}`",
        f"- Risk level: `{review.get('risk_level')}`",
        "",
        "## Summary",
        *_bullets(review.get("summary")),
        "",
        "## Confidence",
    ]
    for key, value in _dict(review.get("confidence")).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Risks", *_bullets(review.get("risks")), "", "## Recommended Next Actions", *_bullets(review.get("recommended_next_actions")), "", "## Scoring Explanation", *_bullets(review.get("scoring_explanation"))])
    return "\n".join(lines).rstrip() + "\n"


def compact_workflow_review_summary(review: dict[str, Any] | None) -> dict[str, Any]:
    """Return path-free summary fields for run metadata."""
    review = review or {}
    return {
        "present": bool(review),
        "overall_status": _safe_text(review.get("overall_status")),
        "readiness_score": review.get("readiness_score") if isinstance(review.get("readiness_score"), int) else None,
        "risk_level": _safe_text(review.get("risk_level")),
        "recommended_next_action_count": len(_list(review.get("recommended_next_actions"))),
        "risk_count": len(_list(review.get("risks"))),
        "summary_preview": [_safe_text(item) for item in _list(review.get("summary"))[:3] if _safe_text(item) is not None],
        "artifact_availability": {"workflow_review_json": bool(review), "workflow_review_md": bool(review)},
    }


def _overall_status(run_metadata: dict[str, Any], assembly: dict[str, Any], part_result: dict[str, Any], stage_review: dict[str, Any]) -> str:
    if stage_review.get("review_status") == "blocked":
        return "blocked"
    if stage_review.get("review_status") == "needs_revision":
        return "needs_revision"
    result_status = part_result.get("status")
    if result_status == "accepted_for_preview":
        return "accepted_for_preview"
    if isinstance(result_status, str) and ("blocked" in result_status or result_status == "failed"):
        return "blocked"
    run_status = _dict(run_metadata.get("status")).get("status")
    if run_status in {"failed", "blocked"}:
        return "blocked"
    if assembly.get("present") or _dict(run_metadata.get("report_summary")).get("report_present"):
        return "ready_for_review"
    return "incomplete"


def _readiness_score(status: str, step_present: bool, stl_present: bool, part_result: dict[str, Any], stage_review: dict[str, Any], risks: list[str]) -> int:
    score = {"accepted_for_preview": 78, "ready_for_review": 58, "needs_revision": 42, "blocked": 18, "incomplete": 25}[status]
    if step_present:
        score += 10
    if stl_present:
        score += 6
    if _dict(part_result.get("checks")).get("single_part_only") is True:
        score += 4
    if _dict(part_result.get("checks")).get("lineage_preserved") is True:
        score += 3
    if stage_review.get("review_status") == "approved":
        score += 4
    score -= min(len(risks) * 3, 18)
    return max(0, min(100, score))


def _risk_level(status: str, risks: list[str], readiness_score: int) -> str:
    if status == "blocked" or readiness_score < 35:
        return "high"
    if len(risks) >= 2 or readiness_score < 75:
        return "medium"
    return "low"


def _summary_lines(assembly: dict[str, Any], part_result: dict[str, Any], step_present: bool, stl_present: bool, stage_review: dict[str, Any]) -> list[str]:
    lines = []
    part_id = part_result.get("part_id") or stage_review.get("stage")
    if part_id:
        lines.append(f"{part_id} is the current reviewed workflow focus.")
    if assembly.get("candidate_part_count"):
        lines.append(f"{assembly.get('candidate_part_count')} candidate part(s) are identified in the assembly plan.")
    if step_present and stl_present:
        lines.append("STEP and STL are available for preview/review.")
    elif step_present:
        lines.append("STEP is available; STL is missing or not expected.")
    else:
        lines.append("No generated STEP file is available yet.")
    if assembly.get("reference_only_count"):
        lines.append(f"{assembly.get('reference_only_count')} reference-only part(s) should not be treated as generated.")
    return lines[:6]


def _risks(assembly: dict[str, Any], part_result: dict[str, Any], checks: dict[str, Any], step_present: bool, stl_present: bool) -> list[str]:
    risks = ["No geometric fit validation with related assembly parts.", "Interface constraints are metadata-only in this pass."]
    if not step_present:
        risks.insert(0, "Primary STEP output is missing.")
    if checks.get("stl_created") is False or (step_present and not stl_present):
        risks.append("STL preview artifact is missing.")
    if assembly.get("blocked_part_count"):
        risks.append(f"{assembly.get('blocked_part_count')} assembly part(s) remain blocked or unsupported.")
    return risks[:8]


def _recommended_next_actions(status: str, risks: list[str], step_present: bool, stl_present: bool, stage_review: dict[str, Any]) -> list[str]:
    if status == "blocked":
        return ["Open the Workflow Review and Stage Review summaries.", "Resolve blocked diagnostics before attempting generation.", "Keep batch/all-part/assembly generation disabled."]
    if status == "needs_revision":
        return ["Review saved stage review notes.", "Revise the upstream artifact indicated by target_rework_stage.", "Regenerate only after explicit user approval."]
    actions = ["Review the generated STEP/STL for the selected part." if step_present or stl_present else "Run or inspect the required upstream stage before CAD review.", "Add stage review notes if the result is not acceptable."]
    if any("fit validation" in risk for risk in risks):
        actions.append("Do not assume assembly fit until geometric validation exists.")
    return actions[:5]


def _diagnostic_codes(run_metadata: dict[str, Any], assembly: dict[str, Any], part_result: dict[str, Any], stage_review: dict[str, Any]) -> list[str]:
    codes = []
    for source in (assembly, part_result, stage_review):
        for code in _list(source.get("diagnostic_codes")):
            safe = _safe_text(code)
            if safe and safe not in codes:
                codes.append(safe)
    for child in _list(run_metadata.get("child_runs")):
        status = _safe_text(_dict(child).get("status"))
        if status and status not in codes:
            codes.append(status)
    return codes


def _scoring_explanation(status: str, step_present: bool, stl_present: bool, part_result: dict[str, Any], risks: list[str]) -> list[str]:
    return [
        f"Base score derives from overall_status={status}.",
        "STEP availability adds readiness." if step_present else "Missing STEP lowers readiness.",
        "STL availability adds preview confidence." if stl_present else "Missing STL reduces preview confidence.",
        "Accepted part result checks add readiness when present." if part_result.get("present") else "No part result review limits readiness.",
        "Risk notes reduce readiness but do not automatically fail the run.",
    ]


def _confidence_from_presence(value: Any) -> str:
    return "medium" if isinstance(value, dict) and value.get("present") else "low"


def _bullets(items: Any) -> list[str]:
    values = _list(items)
    return [f"- {item}" for item in values] if values else ["- None"]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return str(value) if isinstance(value, (int, float, bool)) else None
    lowered = value.lower()
    if any(marker in lowered for marker in ("password", "secret", "token", "api_key", "apikey", "bearer ")):
        return None
    if ":\\" in value or "\\\\" in value:
        return None
    return value[:200]
