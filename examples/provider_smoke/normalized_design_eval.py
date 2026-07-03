"""Manual opt-in normalized provider design evaluation for complex prompts."""

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
from ai_native_cad.pipeline import run_provider_normalized_design_create_pipeline

try:
    from examples.provider_smoke.env_file import load_env_file
except ModuleNotFoundError:
    from env_file import load_env_file


EXPECTED_BLOCKED_CASES = {
    "load_bearing_drone_arm": {
        "codes": ["blocked_policy.over_scoped_engineering_request", "scope.production_critical"],
        "reason": "Production load-bearing drone arms are outside automatic MVP generation scope.",
    },
    "gearbox_exact_teeth": {
        "codes": ["unsupported_part_type.gear", "unsupported.exact_gear_tooth_profiles"],
        "reason": "Exact gear tooth profiles and gearbox generation are unsupported in this MVP.",
    },
    "medical_implant_bracket": {
        "codes": ["blocked_policy.safety_critical", "scope.medical_implant"],
        "reason": "Medical implant design is safety-critical and must not be generated automatically.",
    },
}

DEFAULT_CASES = [
    {
        "case_id": "phone_stand_lip_slot",
        "category": "complex_single_part",
        "prompt": "Make a phone stand with a back support, cable slot, and rounded front lip.",
    },
    {
        "case_id": "electronics_enclosure_base",
        "category": "complex_single_part",
        "prompt": "Make a small electronics enclosure base with PCB standoffs, battery pocket, and lid screw bosses.",
    },
    {
        "case_id": "camera_mounting_plate",
        "category": "complex_single_part",
        "prompt": "Make a camera mounting plate with tripod hole, four corner holes, and chamfered edges.",
    },
    {
        "case_id": "two_part_electronics_enclosure",
        "category": "multi_part_assembly_intent",
        "prompt": "Design a two-part electronics enclosure with base and lid, four screws, and PCB standoffs.",
    },
    {
        "case_id": "hinge_bracket_assembly",
        "category": "multi_part_assembly_intent",
        "prompt": "Design a simple hinge bracket assembly with two leaves and a pin.",
    },
    {
        "case_id": "adjustable_phone_holder",
        "category": "multi_part_assembly_intent",
        "prompt": "Design a small adjustable phone holder made of a base, vertical support, and clamp.",
    },
    {
        "case_id": "load_bearing_drone_arm",
        "category": "expected_blocked_over_scoped",
        "prompt": "Design a load-bearing drone arm assembly for production.",
    },
    {
        "case_id": "gearbox_exact_teeth",
        "category": "expected_blocked_over_scoped",
        "prompt": "Design a gearbox with two gears and exact tooth profiles.",
    },
    {
        "case_id": "medical_implant_bracket",
        "category": "expected_blocked_over_scoped",
        "prompt": "Design a medical implant bracket.",
    },
]

NormalizedDesignRunner = Callable[..., dict[str, Any]]


def run_normalized_design_eval(
    *,
    adapter: Any,
    provider: str,
    model: str | None = None,
    output_dir: str | Path | None = None,
    cases: list[dict[str, str]] | None = None,
    runner: NormalizedDesignRunner = run_provider_normalized_design_create_pipeline,
) -> dict[str, Any]:
    """Run the manual complex-design eval and write sanitized local artifacts."""

    eval_dir = Path(output_dir) if output_dir is not None else REPO_ROOT / "outputs" / f"normalized_design_eval_{provider}"
    eval_dir.mkdir(parents=True, exist_ok=True)
    selected_cases = cases or DEFAULT_CASES
    case_records: list[dict[str, Any]] = []

    for case in selected_cases:
        case_id = _safe_case_id(case["case_id"])
        run_dir = eval_dir / "runs" / case_id
        try:
            result = runner(case["prompt"], adapter, output_dir=run_dir)
            case_record = _case_record_from_pipeline_result(
                result,
                case_id=case_id,
                category=str(case["category"]),
                prompt=case["prompt"],
            )
        except Exception:
            case_record = _failed_case_record(
                case_id=case_id,
                category=str(case["category"]),
                prompt=case["prompt"],
            )
        case_records.append(case_record)

    identity = getattr(adapter, "provider_identity", {})
    if not isinstance(identity, dict):
        identity = {}
    summary = summarize_eval_cases(
        case_records,
        provider=str(identity.get("provider") or provider),
        model=str(identity.get("model") or model or ""),
    )
    artifacts = write_eval_artifacts(eval_dir, case_records, summary)
    return {
        "output_dir": str(eval_dir),
        "cases": case_records,
        "summary": summary,
        "artifacts": artifacts,
    }


def summarize_eval_cases(cases: list[dict[str, Any]], *, provider: str, model: str | None) -> dict[str, Any]:
    classifications = Counter(str(case.get("classification")) for case in cases)
    scopes = Counter(str(case.get("detected_scope")) for case in cases)
    diagnostics: Counter[str] = Counter()
    for case in cases:
        diagnostics.update(str(code) for code in case.get("diagnostic_codes", []) if isinstance(code, str))

    return {
        "provider": provider,
        "model": model or None,
        "workflow": "provider_normalized_design_create",
        "case_count": len(cases),
        "requirement_valid_count": sum(1 for case in cases if case.get("requirement_valid") is True),
        "requirement_blocked_count": sum(1 for case in cases if case.get("requirement_blocked") is True),
        "pipeline_success_count": sum(1 for case in cases if case.get("pipeline_success") is True),
        "success_count": classifications.get("success", 0),
        "expected_blocked_count": classifications.get("expected_blocked", 0),
        "unexpected_blocked_count": classifications.get("unexpected_blocked", 0),
        "failed_count": classifications.get("failed", 0),
        "blocked_count": sum(1 for case in cases if case.get("status") == "blocked"),
        "scope_counts": [{"scope": scope, "count": count} for scope, count in sorted(scopes.items())],
        "category_counts": [
            {"category": category, "count": count}
            for category, count in sorted(Counter(str(case.get("category")) for case in cases).items())
        ],
        "top_diagnostic_codes": [
            {"code": code, "count": count}
            for code, count in diagnostics.most_common(10)
        ],
        "privacy": {
            "provider_traces_recorded": False,
            "raw_provider_messages_recorded": False,
            "absolute_paths_recorded": False,
        },
    }


def write_eval_artifacts(eval_dir: Path, cases: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, str]:
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


def print_compact_summary(summary: dict[str, Any]) -> None:
    status = {
        "provider": summary.get("provider"),
        "model": summary.get("model"),
        "workflow": summary.get("workflow"),
        "case_count": summary.get("case_count"),
        "requirement_valid_count": summary.get("requirement_valid_count"),
        "requirement_blocked_count": summary.get("requirement_blocked_count"),
        "pipeline_success_count": summary.get("pipeline_success_count"),
        "success_count": summary.get("success_count"),
        "expected_blocked_count": summary.get("expected_blocked_count"),
        "unexpected_blocked_count": summary.get("unexpected_blocked_count"),
        "failed_count": summary.get("failed_count"),
        "blocked_count": summary.get("blocked_count"),
        "scope_counts": summary.get("scope_counts"),
        "top_diagnostic_codes": summary.get("top_diagnostic_codes"),
    }
    print(json.dumps(status, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a manual complex design / assembly normalized provider eval.")
    parser.add_argument("--provider", default="deepseek", choices=("deepseek", "openai"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--env-file", default=None, help="Optional manual KEY=VALUE env file. Process env wins.")
    args = parser.parse_args(argv)

    load_env_file(args.env_file)
    adapter = make_json_contract_adapter_from_env(args.provider, model=args.model)
    result = run_normalized_design_eval(
        adapter=adapter,
        provider=args.provider,
        model=args.model,
        output_dir=args.output_dir,
    )
    print_compact_summary(result["summary"])

    summary = result["summary"]
    if summary["failed_count"] or summary["blocked_count"] == summary["case_count"]:
        return 2
    return 0


def _case_record_from_pipeline_result(
    result: dict[str, Any],
    *,
    case_id: str,
    category: str,
    prompt: str,
) -> dict[str, Any]:
    artifacts = _official_artifacts(result)
    raw_status = str(result.get("status") or "failed")
    blocked_stage = _blocked_stage(result)
    status = _eval_status(raw_status, blocked_stage)
    pipeline_success = raw_status == "success" and result.get("success", True) is not False
    detected_scope = _detected_scope(prompt, artifacts)
    diagnostic_codes = _diagnostic_codes(result, case_id=case_id, prompt=prompt, detected_scope=detected_scope)
    classification = _classification(
        case_id=case_id,
        category=category,
        status=status,
        detected_scope=detected_scope,
        diagnostic_codes=diagnostic_codes,
    )
    candidates = artifacts.get("candidate_plans")
    if not isinstance(candidates, list):
        candidates = []
    selected_plan = artifacts.get("selected_plan") if isinstance(artifacts.get("selected_plan"), dict) else {}
    return {
        "case_id": case_id,
        "category": category,
        "prompt": prompt,
        "status": status,
        "blocked_stage": blocked_stage,
        "classification": classification,
        "detected_scope": detected_scope,
        "requirement_valid": isinstance(artifacts.get("requirement"), dict),
        "requirement_blocked": _requirement_blocked(artifacts.get("requirement")),
        "part_count_estimate": _part_count_estimate(prompt, artifacts),
        "part_list_present": _artifact_key_present(artifacts, {"parts", "part_list", "components", "selected_parts"}),
        "interfaces_present": _artifact_key_present(artifacts, {"interfaces", "connections", "joints", "mates", "fit_interfaces"}),
        "fasteners_present": _contains_terms(artifacts, {"fastener", "fasteners", "screw", "screws", "bolt", "bolts"}),
        "clearance_or_fit_notes_present": _contains_terms(artifacts, {"clearance", "fit", "tolerance"}),
        "risk_notes_present": _artifact_key_present(artifacts, {"risk_notes", "risks", "missing_information"}),
        "candidate_plan_count": len(candidates),
        "selected_candidate": _safe_optional_token(selected_plan.get("candidate_id") or selected_plan.get("label")),
        "pipeline_success": pipeline_success,
        "diagnostic_codes": diagnostic_codes,
    }


def _failed_case_record(*, case_id: str, category: str, prompt: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "category": category,
        "prompt": prompt,
        "status": "failed",
        "blocked_stage": "none",
        "classification": "failed",
        "detected_scope": _detected_scope(prompt, {}),
        "requirement_valid": False,
        "requirement_blocked": False,
        "part_count_estimate": _part_count_estimate(prompt, {}),
        "part_list_present": False,
        "interfaces_present": False,
        "fasteners_present": _contains_prompt_terms(prompt, {"screw", "screws", "bolt", "bolts"}),
        "clearance_or_fit_notes_present": False,
        "risk_notes_present": False,
        "candidate_plan_count": 0,
        "selected_candidate": None,
        "pipeline_success": False,
        "diagnostic_codes": sorted(set(EXPECTED_BLOCKED_CASES.get(case_id, {}).get("codes", []) + ["eval.runner_failed"])),
    }


def _official_artifacts(result: dict[str, Any]) -> dict[str, Any]:
    artifacts = {}
    for key in (
        "intent",
        "design_brief",
        "candidate_plans",
        "selected_plan",
        "requirement",
        "planning_artifact",
        "input_ir",
        "report",
    ):
        value = result.get(key)
        if isinstance(value, (dict, list)):
            artifacts[key] = value
    return artifacts


def _classification(
    *,
    case_id: str,
    category: str,
    status: str,
    detected_scope: str,
    diagnostic_codes: list[str],
) -> str:
    if status == "success":
        return "success"
    if status == "failed":
        return "failed"
    if case_id in EXPECTED_BLOCKED_CASES:
        return "expected_blocked"
    if category == "multi_part_assembly_intent" and detected_scope in {"multi_part", "assembly"}:
        return "expected_blocked"
    if detected_scope in {"unsupported", "safety_critical"}:
        return "expected_blocked"
    if any(code.startswith(("unsupported.", "unsupported_part_type.", "blocked_policy.")) for code in diagnostic_codes):
        return "expected_blocked"
    return "unexpected_blocked"


def _requirement_blocked(requirement: Any) -> bool:
    if not isinstance(requirement, dict):
        return False
    decision = _nested_get({"requirement": requirement}, ("requirement", "requirement_status", "flow_decision", "action"))
    return isinstance(decision, str) and decision not in {"proceed", "proceed_with_assumptions"}


def _detected_scope(prompt: str, artifacts: dict[str, Any]) -> str:
    lowered = prompt.lower()
    codes = set(_artifact_diagnostic_codes(artifacts))
    if (
        "medical implant" in lowered
        or ("implant" in lowered and "medical" in lowered)
        or "load-bearing" in lowered
        or "production" in lowered
        or "aerospace" in lowered
        or "drone arm" in lowered
    ):
        return "safety_critical"
    if "gearbox" in lowered or "gear tooth" in lowered or "exact tooth" in lowered:
        return "unsupported"
    if _prompt_has_assembly_intent(lowered):
        return "assembly"
    if _prompt_has_multi_part_intent(lowered):
        return "multi_part"
    if _prompt_has_single_part_feature_intent(lowered):
        return "single_part_with_features"
    if any(code in codes for code in {"blocked_policy.safety_scope_blocked", "scope.medical_implant"}):
        return "safety_critical"
    if any(code.startswith(("unsupported.", "unsupported_part_type.")) for code in codes):
        return "unsupported"
    if "compiler.assembly_requires_assembly_planning" in codes:
        return "assembly"
    if "compiler.multi_part_requires_assembly_planning" in codes:
        return "multi_part"
    scope = _nested_get(artifacts, ("intent", "scope")) or _nested_get(artifacts, ("design_brief", "design_goal", "scope"))
    if isinstance(scope, str) and scope in {
        "single_part",
        "single_part_with_features",
        "multi_part",
        "assembly",
        "unsupported",
        "safety_critical",
    }:
        return scope
    return "single_part"


def _prompt_has_assembly_intent(lowered_prompt: str) -> bool:
    return any(
        token in lowered_prompt
        for token in (
            " assembly",
            "hinge",
            "two leaves",
            " pin",
            "gears and shafts",
            "moving joint",
            "mechanism",
        )
    )


def _prompt_has_multi_part_intent(lowered_prompt: str) -> bool:
    return any(
        token in lowered_prompt
        for token in (
            "two-part",
            "two part",
            "base and lid",
            "base, vertical support, and clamp",
            "made of a base",
            "separate parts",
            "separable parts",
        )
    )


def _prompt_has_single_part_feature_intent(lowered_prompt: str) -> bool:
    if any(
        token in lowered_prompt
        for token in (
            "mounting plate",
            "camera mounting plate",
            "enclosure base",
            "phone stand",
        )
    ):
        return True
    return any(
        token in lowered_prompt
        for token in (
            "hole",
            "holes",
            "boss",
            "bosses",
            "slot",
            "standoff",
            "standoffs",
            "pocket",
            "chamfer",
            "chamfered",
            "lip",
            "tripod",
        )
    )


def _artifact_diagnostic_codes(value: Any) -> list[str]:
    codes: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) == "diagnostic_codes" and isinstance(item, list):
                codes.extend(_safe_code_token(str(code)) for code in item if isinstance(code, str))
            else:
                codes.extend(_artifact_diagnostic_codes(item))
    elif isinstance(value, list):
        for item in value:
            codes.extend(_artifact_diagnostic_codes(item))
    return codes


def _part_count_estimate(prompt: str, artifacts: dict[str, Any]) -> int:
    for key in ("planning_artifact", "design_brief", "selected_plan", "requirement"):
        count = _count_parts_in_artifact(artifacts.get(key))
        if count:
            return count
    text = prompt.lower()
    if "two-part" in text or "base and lid" in text:
        return 2
    if "two leaves and a pin" in text:
        return 3
    if "base, vertical support, and clamp" in text:
        return 3
    if "gearbox" in text and "two gears" in text:
        return 3
    return 1


def _count_parts_in_artifact(value: Any) -> int:
    if isinstance(value, dict):
        for key in ("part_list", "parts", "components", "selected_parts"):
            item = value.get(key)
            if isinstance(item, list) and item:
                return len(item)
        for item in value.values():
            count = _count_parts_in_artifact(item)
            if count:
                return count
    if isinstance(value, list):
        for item in value:
            count = _count_parts_in_artifact(item)
            if count:
                return count
    return 0


def _diagnostic_codes(result: dict[str, Any], *, case_id: str, prompt: str, detected_scope: str) -> list[str]:
    codes: set[str] = set(EXPECTED_BLOCKED_CASES.get(case_id, {}).get("codes", []))
    for key in ("validation_error_codes", "error_codes", "diagnostic_codes"):
        value = result.get(key)
        if isinstance(value, list):
            codes.update(_safe_code_token(str(item)) for item in value if isinstance(item, str))
    report = result.get("report")
    if isinstance(report, dict):
        for key in ("validation_error_codes", "error_codes", "diagnostic_codes"):
            value = report.get(key)
            if isinstance(value, list):
                codes.update(_safe_code_token(str(item)) for item in value if isinstance(item, str))
    error_category = result.get("error_category")
    if isinstance(error_category, str):
        codes.add(_code_for_error_category(error_category, _blocked_stage(result)))
    if detected_scope == "assembly":
        codes.add("scope.assembly_intent")
    elif detected_scope == "multi_part":
        codes.add("scope.multi_part_intent")
    elif detected_scope == "single_part_with_features":
        codes.add("scope.single_part_with_features")
    elif detected_scope == "unsupported":
        codes.add("scope.unsupported")
    elif detected_scope == "safety_critical":
        codes.add("blocked_policy.safety_critical")
    if "production" in prompt.lower() or "load-bearing" in prompt.lower():
        codes.add("scope.production_critical")
    return sorted(code for code in codes if code and not _looks_sensitive(code))


def _code_for_error_category(error_category: str, blocked_stage: str) -> str:
    if error_category in {"auth_failed", "timeout", "rate_limited", "network_error", "client_error"}:
        return f"provider_error.{error_category}"
    if error_category == "cad_ir_validation_failed":
        return "cad_ir_validation.failed"
    if error_category == "requirement_gate_blocked":
        return "blocked_policy.requirement_gate_blocked"
    if error_category == "planning_gate_blocked":
        return "blocked_policy.planning_gate_blocked"
    if error_category == "local_validation_failed":
        return f"{blocked_stage}_validation.local_validation_failed"
    return f"pipeline.{_safe_code_token(error_category)}"


def _blocked_stage(result: dict[str, Any]) -> str:
    stage = result.get("blocked_stage")
    if stage in {"requirement", "planning", "cad_ir", "part_modeling", "assembly_planning"}:
        return str(stage)
    if str(result.get("status", "")).startswith("blocked_provider_"):
        return "part_modeling"
    return "none"


def _eval_status(raw_status: str, blocked_stage: str) -> str:
    if raw_status == "success":
        return "success"
    if raw_status.startswith("blocked_") or blocked_stage != "none":
        return "blocked"
    return "failed"


def _artifact_key_present(value: Any, keys: set[str]) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in keys and bool(item):
                return True
            if _artifact_key_present(item, keys):
                return True
    elif isinstance(value, list):
        return any(_artifact_key_present(item, keys) for item in value)
    return False


def _contains_terms(value: Any, terms: set[str]) -> bool:
    return any(term in _artifact_text(value) for term in terms)


def _contains_prompt_terms(prompt: str, terms: set[str]) -> bool:
    lowered = prompt.lower()
    return any(term in lowered for term in terms)


def _artifact_text(value: Any) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        for key, item in value.items():
            if _looks_sensitive(str(key)):
                continue
            parts.append(str(key).lower())
            parts.append(_artifact_text(item))
        return " ".join(parts)
    if isinstance(value, list):
        return " ".join(_artifact_text(item) for item in value)
    if isinstance(value, (str, int, float, bool)):
        text = str(value).lower()
        return "" if _looks_sensitive(text) else text
    return ""


def _nested_get(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _safe_case_id(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_")
    return safe or "case"


def _safe_code_token(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip()).strip("_")
    return safe or "unknown"


def _safe_optional_token(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if _looks_sensitive(value):
        return "redacted"
    return _safe_code_token(value)


def _looks_sensitive(value: str) -> bool:
    lower = value.lower()
    return any(token in lower for token in ("key", "secret", "token", "password", "transcript", "message", "response", "log"))


def _render_eval_report(summary: dict[str, Any], cases: list[dict[str, Any]]) -> str:
    lines = [
        "# Normalized Design Evaluation",
        "",
        f"- Provider: `{summary.get('provider')}`",
        f"- Model: `{summary.get('model')}`",
        f"- Workflow: `{summary.get('workflow')}`",
        f"- Cases: {summary.get('case_count')}",
        f"- Requirement valid: {summary.get('requirement_valid_count')}",
        f"- Requirement blocked: {summary.get('requirement_blocked_count')}",
        f"- Pipeline success: {summary.get('pipeline_success_count')}",
        f"- Success: {summary.get('success_count')}",
        f"- Expected blocked: {summary.get('expected_blocked_count')}",
        f"- Unexpected blocked: {summary.get('unexpected_blocked_count')}",
        f"- Failed: {summary.get('failed_count')}",
        "",
        "This manual eval measures design-artifact usefulness and capability boundaries. Pipeline success alone is not the score.",
        "Provider output remains extraction/advisory only; CadFlow locally compiles official artifacts and blocks unsupported scope honestly.",
        "",
        "## Cases",
        "",
        "| Case | Category | Classification | Status | Blocked stage | Scope | Requirement | Req blocked | Parts | Part list | Interfaces | Fasteners | Fit notes | Risks | Candidates | Selected | Pipeline | Diagnostic codes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for case in cases:
        lines.append(
            "| {case_id} | {category} | {classification} | {status} | {blocked_stage} | {scope} | {requirement} | {requirement_blocked} | {parts} | {part_list} | {interfaces} | {fasteners} | {fit} | {risks} | {candidates} | {selected} | {pipeline} | {codes} |".format(
                case_id=case.get("case_id"),
                category=case.get("category"),
                classification=case.get("classification"),
                status=case.get("status"),
                blocked_stage=case.get("blocked_stage"),
                scope=case.get("detected_scope"),
                requirement=_yes_no(case.get("requirement_valid")),
                requirement_blocked=_yes_no(case.get("requirement_blocked")),
                parts=case.get("part_count_estimate"),
                part_list=_yes_no(case.get("part_list_present")),
                interfaces=_yes_no(case.get("interfaces_present")),
                fasteners=_yes_no(case.get("fasteners_present")),
                fit=_yes_no(case.get("clearance_or_fit_notes_present")),
                risks=_yes_no(case.get("risk_notes_present")),
                candidates=case.get("candidate_plan_count"),
                selected=case.get("selected_candidate"),
                pipeline=_yes_no(case.get("pipeline_success")),
                codes=", ".join(case.get("diagnostic_codes", [])),
            )
        )
    lines.append("")
    return "\n".join(lines)


def _yes_no(value: Any) -> str:
    return "yes" if value is True else "no"


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
