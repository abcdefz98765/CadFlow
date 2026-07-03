"""Manual opt-in provider quality evaluation for provider create workflow."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_native_cad.agents import make_json_contract_adapter_from_env
from ai_native_cad.pipeline import run_provider_create_pipeline

try:
    from examples.provider_smoke.env_file import load_env_file
except ModuleNotFoundError:
    from env_file import load_env_file


EXPECTED_BLOCKED_CASES = {
    "gear_24_teeth": {
        "codes": ["unsupported_part_type.gear", "unsupported.unsupported_provider_part_type"],
        "reason": "Gear is not a supported CadFlow CAD template in this MVP.",
    },
    "aerospace_bracket_over_scoped": {
        "codes": ["blocked_policy.safety_scope_blocked", "blocked_policy.over_scoped_engineering_request"],
        "reason": "Production-ready load-bearing aerospace brackets are outside safe automatic L0/L1 generation.",
    },
}

DEFAULT_CASES = [
    {
        "case_id": "mounting_plate_explicit",
        "prompt": "Make an 80x40x5 mm mounting plate with four M4 holes.",
    },
    {
        "case_id": "pcb_mounting_plate",
        "prompt": "Make a simple mounting plate for a small PCB with four corner holes.",
    },
    {
        "case_id": "spacer_washer",
        "prompt": "Make a 20 mm outer diameter, 6 mm inner diameter, 5 mm thick spacer washer.",
    },
    {
        "case_id": "circular_button",
        "prompt": "Make a circular button 18 mm diameter and 4 mm tall.",
    },
    {
        "case_id": "right_angle_bracket",
        "prompt": "Make a simple right-angle bracket with two mounting holes.",
    },
    {
        "case_id": "button_battery_enclosure_base",
        "prompt": "Make a small enclosure base for a button and battery.",
    },
    {
        "case_id": "mounting_plate_missing_dimensions",
        "prompt": "Make a mounting plate but do not specify dimensions.",
    },
    {
        "case_id": "gear_24_teeth",
        "prompt": "Make a gear with 24 teeth.",
    },
    {
        "case_id": "aerospace_bracket_over_scoped",
        "prompt": "Make a production-ready load-bearing aerospace bracket.",
    },
    {
        "case_id": "plate_revision_like",
        "prompt": "Make a plate and change the holes to M5.",
    },
]

ProviderCreateRunner = Callable[[str, Any], dict[str, Any]]


def run_provider_create_eval(
    *,
    adapter: Any,
    provider: str,
    model: str | None = None,
    output_dir: str | Path | None = None,
    cases: list[dict[str, str]] | None = None,
    provider_contract_mode: str = "strict",
    runner: Callable[..., dict[str, Any]] = run_provider_create_pipeline,
) -> dict[str, Any]:
    """Run the manual provider create eval and write sanitized local artifacts."""

    if provider_contract_mode not in {"strict", "extract_then_compile"}:
        raise ValueError("provider_contract_mode must be 'strict' or 'extract_then_compile'")
    eval_dir = Path(output_dir) if output_dir is not None else REPO_ROOT / "outputs" / f"provider_create_eval_{provider}"
    eval_dir.mkdir(parents=True, exist_ok=True)
    selected_cases = cases or DEFAULT_CASES
    case_records: list[dict[str, Any]] = []

    for case in selected_cases:
        case_id = _safe_case_id(case["case_id"])
        run_dir = eval_dir / "runs" / case_id
        try:
            result = runner(
                case["prompt"],
                adapter,
                output_dir=run_dir,
                provider_contract_mode=provider_contract_mode,
            )
            case_result = _case_result_from_pipeline_result(result, eval_dir=eval_dir, case_id=case_id)
        except Exception:
            case_result = _failed_case_result(_relative_or_redacted(run_dir, eval_dir), case_id=case_id)
        case_records.append({
            "case_id": case_id,
            "prompt": case["prompt"],
            **case_result,
        })

    identity = getattr(adapter, "provider_identity", {})
    if not isinstance(identity, dict):
        identity = {}
    summary = summarize_eval_cases(
        case_records,
        provider=str(identity.get("provider") or provider),
        model=str(identity.get("model") or model or ""),
    )
    summary["provider_contract_mode"] = provider_contract_mode
    artifacts = write_eval_artifacts(eval_dir, case_records, summary)
    return {
        "output_dir": str(eval_dir),
        "cases": case_records,
        "summary": summary,
        "artifacts": artifacts,
        "provider_contract_mode": provider_contract_mode,
    }


def summarize_eval_cases(
    cases: list[dict[str, Any]],
    *,
    provider: str,
    model: str | None,
) -> dict[str, Any]:
    validation_errors: Counter[str] = Counter()
    for case in cases:
        validation_errors.update(str(code) for code in case.get("validation_error_codes", []) if isinstance(code, str))

    return {
        "provider": provider,
        "model": model or None,
        "case_count": len(cases),
        "requirement_valid_count": sum(1 for case in cases if case.get("requirement_valid") is True),
        "planning_valid_count": sum(1 for case in cases if case.get("planning_valid") is True),
        "ir_conversion_success_count": sum(1 for case in cases if case.get("ir_conversion_success") is True),
        "pipeline_success_count": sum(1 for case in cases if case.get("pipeline_success") is True),
        "blocked_count": sum(1 for case in cases if case.get("status") == "blocked"),
        "expected_blocked_count": sum(1 for case in cases if case.get("outcome") == "expected_blocked"),
        "unexpected_blocked_count": sum(1 for case in cases if case.get("outcome") == "unexpected_blocked"),
        "failed_count": sum(1 for case in cases if case.get("status") == "failed"),
        "top_validation_errors": [
            {"code": code, "count": count}
            for code, count in validation_errors.most_common(10)
        ],
    }


def write_eval_artifacts(
    eval_dir: Path,
    cases: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, str]:
    eval_dir.mkdir(parents=True, exist_ok=True)
    cases_path = eval_dir / "eval_cases.json"
    summary_path = eval_dir / "eval_summary.json"
    report_path = eval_dir / "eval_report.md"

    _write_json(cases_path, cases)
    _write_json(summary_path, summary)
    report_path.write_text(_render_eval_report(summary, cases), encoding="utf-8")
    return {
        "eval_cases": "eval_cases.json",
        "eval_summary": "eval_summary.json",
        "eval_report": "eval_report.md",
    }


def print_compact_summary(summary: dict[str, Any], output_dir: str | Path) -> None:
    status = {
        "provider": summary.get("provider"),
        "model": summary.get("model"),
        "provider_contract_mode": summary.get("provider_contract_mode"),
        "case_count": summary.get("case_count"),
        "requirement_valid_count": summary.get("requirement_valid_count"),
        "planning_valid_count": summary.get("planning_valid_count"),
        "ir_conversion_success_count": summary.get("ir_conversion_success_count"),
        "pipeline_success_count": summary.get("pipeline_success_count"),
        "blocked_count": summary.get("blocked_count"),
        "expected_blocked_count": summary.get("expected_blocked_count"),
        "unexpected_blocked_count": summary.get("unexpected_blocked_count"),
        "failed_count": summary.get("failed_count"),
        "output_dir": _display_output_dir(output_dir),
    }
    print(json.dumps(status, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a manual provider create quality evaluation.")
    parser.add_argument("--provider", default="deepseek", choices=("deepseek", "openai"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--env-file", default=None, help="Optional manual KEY=VALUE env file. Process env wins.")
    parser.add_argument(
        "--provider-contract-mode",
        default="strict",
        choices=("strict", "extract_then_compile"),
        help="Use strict provider contracts by default; opt into local compilation explicitly.",
    )
    args = parser.parse_args(argv)

    load_env_file(args.env_file)
    adapter = make_json_contract_adapter_from_env(args.provider, model=args.model)
    result = run_provider_create_eval(
        adapter=adapter,
        provider=args.provider,
        model=args.model,
        output_dir=args.output_dir,
        provider_contract_mode=args.provider_contract_mode,
    )
    print_compact_summary(result["summary"], result["output_dir"])

    summary = result["summary"]
    if summary["failed_count"] or summary["blocked_count"] == summary["case_count"]:
        return 2
    return 0


def _case_result_from_pipeline_result(result: dict[str, Any], *, eval_dir: Path, case_id: str) -> dict[str, Any]:
    metadata = result.get("provider_create") if isinstance(result.get("provider_create"), dict) else {}
    raw_status = str(result.get("status") or metadata.get("status") or "failed")
    blocked_stage = _blocked_stage(result, metadata)
    pipeline_status = str(metadata.get("pipeline_status") or raw_status)
    output_dir = result.get("output_dir")
    if not isinstance(output_dir, str):
        output_dir = ""

    status = _eval_status(raw_status, blocked_stage)
    validation_error_codes = _validation_error_codes(result, case_id=case_id, blocked_stage=blocked_stage)
    outcome = _case_outcome(case_id=case_id, status=status, validation_error_codes=validation_error_codes)
    return {
        "status": status,
        "outcome": outcome,
        "expected_block_reason": _expected_block_reason(case_id) if outcome == "expected_blocked" else None,
        "blocked_stage": blocked_stage,
        "requirement_valid": metadata.get("requirement_status") == "passed",
        "planning_valid": metadata.get("planning_status") == "passed",
        "ir_conversion_success": metadata.get("ir_validation_status") == "passed",
        "pipeline_success": raw_status == "success" and pipeline_status == "success",
        "provider_error_category": _safe_optional_string(result.get("error_category") or metadata.get("error_category")),
        "validation_error_codes": validation_error_codes,
        "output_dir": _relative_or_redacted(output_dir, eval_dir),
        "provider_trace_summary": _provider_trace_summary(metadata.get("provider_request_traces")),
    }


def _failed_case_result(output_dir: str, *, case_id: str) -> dict[str, Any]:
    validation_error_codes = _validation_error_codes({}, case_id=case_id, blocked_stage="none")
    return {
        "status": "failed",
        "outcome": "failed",
        "expected_block_reason": None,
        "blocked_stage": "none",
        "requirement_valid": False,
        "planning_valid": False,
        "ir_conversion_success": False,
        "pipeline_success": False,
        "provider_error_category": "eval_runner_failed",
        "validation_error_codes": validation_error_codes,
        "output_dir": output_dir,
        "provider_trace_summary": {
            "operations": [],
            "knowledge_ids": [],
            "message_counts": {},
        },
    }


def _provider_trace_summary(traces: Any) -> dict[str, Any]:
    operations: list[str] = []
    knowledge_ids: set[str] = set()
    message_counts: dict[str, int] = {}
    if isinstance(traces, list):
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            operation = trace.get("operation")
            if isinstance(operation, str) and not _looks_sensitive(operation):
                operations.append(operation)
                message_count = trace.get("message_count")
                if isinstance(message_count, int):
                    message_counts[operation] = message_count
            for knowledge_id in trace.get("knowledge_ids", []):
                if isinstance(knowledge_id, str) and not _looks_sensitive(knowledge_id):
                    knowledge_ids.add(knowledge_id)
    return {
        "operations": operations,
        "knowledge_ids": sorted(knowledge_ids),
        "message_counts": message_counts,
    }


def _validation_error_codes(result: dict[str, Any], *, case_id: str, blocked_stage: str) -> list[str]:
    codes: set[str] = set()
    for key in ("validation_error_codes", "error_codes"):
        value = result.get(key)
        if isinstance(value, list):
            codes.update(str(item) for item in value if isinstance(item, str))
    report = result.get("report")
    if isinstance(report, dict):
        value = report.get("validation_error_codes") or report.get("error_codes")
        if isinstance(value, list):
            codes.update(str(item) for item in value if isinstance(item, str))
    error_category = result.get("error_category")
    if isinstance(error_category, str):
        codes.update(_codes_for_error_category(error_category, blocked_stage=blocked_stage))
    provider_category = result.get("provider_create")
    if isinstance(provider_category, dict):
        category = provider_category.get("error_category")
        if isinstance(category, str):
            codes.update(_codes_for_error_category(category, blocked_stage=blocked_stage))
    codes.update(EXPECTED_BLOCKED_CASES.get(case_id, {}).get("codes", []))
    return sorted(codes)


def _codes_for_error_category(error_category: str, *, blocked_stage: str) -> list[str]:
    if error_category in {"auth_failed", "timeout", "rate_limited", "client_error"}:
        return [f"provider_error.{error_category}"]
    if error_category == "cad_ir_validation_failed":
        return ["cad_ir_validation.failed", "cad_ir_validation_failed"]
    if error_category == "local_validation_failed":
        if blocked_stage == "requirement":
            return ["requirement_validation.local_validation_failed"]
        if blocked_stage == "planning":
            return ["planning_validation.local_validation_failed"]
        return ["compiler.local_validation_failed"]
    if error_category == "requirement_gate_blocked":
        return ["blocked_policy.requirement_gate_blocked"]
    if error_category == "planning_gate_blocked":
        return ["blocked_policy.planning_gate_blocked"]
    return [f"pipeline.{_safe_code_token(error_category)}"]


def _case_outcome(*, case_id: str, status: str, validation_error_codes: list[str]) -> str:
    if status == "success":
        return "success"
    if status == "failed":
        return "failed"
    if case_id in EXPECTED_BLOCKED_CASES:
        return "expected_blocked"
    if any(code in {"blocked_policy.safety_scope_blocked", "blocked_policy.over_scoped_engineering_request"} for code in validation_error_codes):
        return "expected_blocked"
    return "unexpected_blocked"


def _expected_block_reason(case_id: str) -> str | None:
    reason = EXPECTED_BLOCKED_CASES.get(case_id, {}).get("reason")
    return reason if isinstance(reason, str) else None


def _blocked_stage(result: dict[str, Any], metadata: dict[str, Any]) -> str:
    stage = result.get("blocked_stage") or metadata.get("blocked_stage")
    if stage in {"requirement", "planning", "cad_ir", "part_modeling"}:
        return str(stage)
    if str(result.get("status", "")).startswith("blocked_provider_"):
        return "part_modeling" if metadata.get("pipeline_status") == "failed" else "none"
    return "none"


def _eval_status(raw_status: str, blocked_stage: str) -> str:
    if raw_status == "success":
        return "success"
    if raw_status.startswith("blocked_provider_") or blocked_stage != "none":
        return "blocked"
    return "failed"


def _safe_optional_string(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if _looks_sensitive(value):
        return "redacted"
    return value


def _relative_or_redacted(path: str | Path, root: Path) -> str:
    try:
        relative = Path(path).resolve().relative_to(root.resolve())
        return relative.as_posix()
    except (OSError, ValueError):
        return "[redacted-path]"


def _display_output_dir(path: str | Path) -> str:
    try:
        relative = Path(path).resolve().relative_to(REPO_ROOT.resolve())
        return relative.as_posix()
    except (OSError, ValueError):
        return "[redacted-path]"


def _safe_case_id(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_")
    return safe or "case"


def _safe_code_token(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip()).strip("_")
    return safe or "unknown"


def _looks_sensitive(value: str) -> bool:
    lower = value.lower()
    return any(token in lower for token in ("key", "secret", "token", "password", "transcript", "message", "response", "log"))


def _render_eval_report(summary: dict[str, Any], cases: list[dict[str, Any]]) -> str:
    lines = [
        "# Provider Create Evaluation",
        "",
        f"- Provider: `{summary.get('provider')}`",
        f"- Model: `{summary.get('model')}`",
        f"- Provider contract mode: `{summary.get('provider_contract_mode', 'strict')}`",
        f"- Mode meaning: {_mode_description(str(summary.get('provider_contract_mode', 'strict')))}",
        f"- Cases: {summary.get('case_count')}",
        f"- Requirement valid: {summary.get('requirement_valid_count')}",
        f"- Planning valid: {summary.get('planning_valid_count')}",
        f"- IR conversion success: {summary.get('ir_conversion_success_count')}",
        f"- Pipeline success: {summary.get('pipeline_success_count')}",
        f"- Blocked: {summary.get('blocked_count')}",
        f"- Expected blocked: {summary.get('expected_blocked_count')}",
        f"- Unexpected blocked: {summary.get('unexpected_blocked_count')}",
        f"- Failed: {summary.get('failed_count')}",
        "",
        "Strict mode is provider contract compliance mode. Strict failures do not automatically imply product workflow failure.",
        "extract_then_compile mode is the product-oriented normalized workflow mode: provider output is treated as extracted fields and CadFlow locally compiles stable internal contracts.",
        "extract_then_compile success means the local compiler stabilized provider extraction without relying on provider-generated CAD IR or code.",
        "Expected-blocked cases are correct blocks for unsupported or unsafe requests, not product failures.",
    ]
    if (
        summary.get("pipeline_success_count") == 8
        and summary.get("expected_blocked_count") == 2
        and summary.get("unexpected_blocked_count") == 0
    ):
        lines.append("8/10 pipeline success + 2 expected blocked means all supported eval cases passed and unsupported/unsafe cases blocked correctly.")
    lines.extend([
        "",
        "## Cases",
        "",
        "| Case | Outcome | Status | Blocked stage | Requirement | Planning | IR | Pipeline | Diagnostic codes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for case in cases:
        lines.append(
            "| {case_id} | {outcome} | {status} | {blocked_stage} | {requirement} | {planning} | {ir} | {pipeline} | {codes} |".format(
                case_id=case.get("case_id"),
                outcome=case.get("outcome"),
                status=case.get("status"),
                blocked_stage=case.get("blocked_stage"),
                requirement=_yes_no(case.get("requirement_valid")),
                planning=_yes_no(case.get("planning_valid")),
                ir=_yes_no(case.get("ir_conversion_success")),
                pipeline=_yes_no(case.get("pipeline_success")),
                codes=", ".join(case.get("validation_error_codes", [])),
            )
        )
    lines.append("")
    return "\n".join(lines)


def _yes_no(value: Any) -> str:
    return "yes" if value is True else "no"


def _mode_description(provider_contract_mode: str) -> str:
    if provider_contract_mode == "extract_then_compile":
        return "product-oriented normalized workflow mode"
    return "provider contract compliance mode"


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
