"""Structured failure analysis for CAD agent loop attempts."""

from __future__ import annotations

from typing import Any


def analyze_failure(
    execution: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify execution and validation failures into an IR repair hint."""
    execution = execution or {}
    validation = validation or {}
    stderr = str(execution.get("stderr") or "")
    stdout = str(execution.get("stdout") or "")
    log_text = f"{stderr}\n{stdout}".lower()
    errors = validation.get("errors", [])
    error_codes = {error.get("code") for error in errors if isinstance(error, dict)}

    if execution.get("status") != "success":
        root_cause = _execution_root_cause(log_text)
        return _result(
            failure_type="execution_failure",
            root_cause=root_cause,
            affected_feature=_affected_feature(log_text, errors),
            severity="high",
            suggested_ir_fix=_suggested_fix(root_cause, log_text, errors),
        )

    if "required_output_missing" in error_codes:
        return _result(
            failure_type="export_failure",
            root_cause="missing_export_file",
            affected_feature="outputs",
            severity="high",
            suggested_ir_fix={"modify": "outputs", "strategy": "preserve_required_step_stl"},
        )

    if "missing_feature" in error_codes:
        return _result(
            failure_type="geometry_failure",
            root_cause="feature_not_realized",
            affected_feature=_first_error_field(errors, "feature", "features"),
            severity="high",
            suggested_ir_fix={"modify": "feature_parameters", "strategy": "repair_feature_clearance"},
        )

    if "extreme_dimension_deviation" in error_codes or "bounding_box_mismatch" in error_codes:
        return _result(
            failure_type="geometry_failure",
            root_cause="dimension_mismatch",
            affected_feature=_first_error_field(errors, "dimension", "dimensions"),
            severity="medium",
            suggested_ir_fix={"modify": "dimensions", "strategy": "restore_expected_dimension_constraints"},
        )

    if "invalid_solid" in error_codes or "boolean_failure_artifact" in error_codes:
        return _result(
            failure_type="geometry_failure",
            root_cause="boolean_operation_failed",
            affected_feature=_affected_feature(log_text, errors),
            severity="high",
            suggested_ir_fix={"modify": "feature_clearances", "strategy": "reduce_boolean_risk"},
        )

    return _result(
        failure_type="geometry_failure",
        root_cause="validation_failed",
        affected_feature=_affected_feature(log_text, errors),
        severity="medium",
        suggested_ir_fix={"modify": "feature_parameters", "strategy": "conservative_geometry"},
    )


def _execution_root_cause(log_text: str) -> str:
    if any(term in log_text for term in ("boolean", "cut", "fillet", "chamfer", "bopalgo")):
        return "boolean_operation_failed"
    if "no such file" in log_text or "not found" in log_text:
        return "missing_file"
    if "timeout" in log_text:
        return "execution_timeout"
    return "cadquery_execution_error"


def _affected_feature(log_text: str, errors: list[dict[str, Any]]) -> str:
    for feature in ("holes", "chamfer", "fillet", "outputs"):
        if feature in log_text:
            return feature
    return _first_error_field(errors, "feature", "geometry")


def _first_error_field(errors: list[dict[str, Any]], key: str, default: str) -> str:
    for error in errors:
        value = error.get(key)
        if value:
            return str(value)
    return default


def _suggested_fix(root_cause: str, log_text: str, errors: list[dict[str, Any]]) -> dict[str, str]:
    feature = _affected_feature(log_text, errors)
    if feature == "holes":
        return {"modify": "hole_positions", "strategy": "increase_spacing"}
    if feature in {"chamfer", "fillet"}:
        return {"modify": feature, "strategy": "reduce_size"}
    if root_cause == "missing_file":
        return {"modify": "outputs", "strategy": "ensure_step_stl"}
    return {"modify": "feature_parameters", "strategy": "conservative_geometry"}


def _result(
    failure_type: str,
    root_cause: str,
    affected_feature: str,
    severity: str,
    suggested_ir_fix: dict[str, str],
) -> dict[str, Any]:
    return {
        "failure_type": failure_type,
        "root_cause": root_cause,
        "affected_feature": affected_feature,
        "severity": severity,
        "suggested_ir_fix": suggested_ir_fix,
    }
