"""Candidate scoring for CAD agent loop validation results."""

from __future__ import annotations

from typing import Any


def score_candidate(candidate: str, validation: dict[str, Any], execution: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a normalized validation score for a candidate implementation."""
    execution = execution or {}
    score = 0.0
    if execution.get("status") == "success":
        score += 0.2
    if validation.get("valid"):
        score += 0.45
    if validation.get("step_generated") and validation.get("stl_generated"):
        score += 0.1
    if validation.get("volume", 0) > 0:
        score += 0.1

    checks = validation.get("checks", [])
    if checks:
        passed = sum(1 for check in checks if check.get("pass"))
        score += 0.1 * (passed / len(checks))

    error_codes = {error.get("code") for error in validation.get("errors", []) if isinstance(error, dict)}
    if not {"boolean_failure_artifact", "invalid_solid", "execution_failed"} & error_codes:
        score += 0.03
    if _symmetry_checks_pass(checks):
        score += 0.02

    return {"candidate": candidate, "score": round(min(score, 1.0), 3)}


def _symmetry_checks_pass(checks: list[dict[str, Any]]) -> bool:
    symmetry_checks = [check for check in checks if check.get("check") == "symmetry_correctness"]
    return not symmetry_checks or all(check.get("pass") for check in symmetry_checks)
