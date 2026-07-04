"""Manual reviewed-part single-create smoke.

This opt-in script exercises the staged assembly-planning-to-one-part flow with
a real provider adapter. It prints a compact sanitized summary only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_native_cad.agents import JsonContractProviderError, make_json_contract_adapter_from_env
from ai_native_cad.pipeline import (
    run_assembly_part_request_pipeline,
    run_part_request_review_pipeline,
    run_part_result_review_pipeline,
    run_provider_normalized_design_create_pipeline,
    run_reviewed_part_handoff_pipeline,
    run_reviewed_part_single_create_pipeline,
)

try:
    from examples.provider_smoke.env_file import load_env_file
except ModuleNotFoundError:
    from env_file import load_env_file


SMOKE_PROMPT = "Design a two-part electronics enclosure with base and lid, four screws, and PCB standoffs."
SOURCE_PROMPT_CASE = "electronics_enclosure_base_lid"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a manual reviewed-part single-create smoke.")
    parser.add_argument("--provider", default="deepseek", choices=("deepseek", "openai"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--env-file", default=None, help="Optional manual KEY=VALUE env file. Process env wins.")
    parser.add_argument("--part-id", default=None, help="Optional explicit candidate part_id to review and generate.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory. Defaults under ignored outputs/provider_smoke/.",
    )
    args = parser.parse_args(argv)

    output_root = Path(args.output_dir) if args.output_dir else REPO_ROOT / "outputs" / "provider_smoke" / "reviewed_part_single_create"
    requested_part_id = _safe_artifact_id(args.part_id) if args.part_id else None
    if args.output_dir is None and requested_part_id:
        output_root = output_root / requested_part_id
    try:
        load_env_file(args.env_file)
        adapter = make_json_contract_adapter_from_env(args.provider, model=args.model)
        summary = run_reviewed_part_single_create_smoke(
            adapter,
            args.provider,
            output_root,
            requested_part_id=requested_part_id,
        )
    except JsonContractProviderError as exc:
        summary = _base_summary({"provider": args.provider}, error_category=exc.category)
    except Exception:
        summary = _base_summary({"provider": args.provider}, error_category="smoke_failed")

    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary.get("bridge_status") == "success":
        return 0
    if summary.get("error_category") == "auth_failed":
        return 2
    return 1


def run_reviewed_part_single_create_smoke(
    adapter: Any,
    provider: str,
    output_root: Path,
    *,
    requested_part_id: str | None = None,
) -> dict[str, Any]:
    identity = _safe_identity(getattr(adapter, "provider_identity", {"provider": provider}))
    design_dir = output_root / "01_design"
    part_request_dir = output_root / "02_part_request"
    review_dir = output_root / "03_review"
    handoff_dir = output_root / "04_handoff"
    bridge_dir = output_root / "05_single_create"
    part_result_review_dir = output_root / "06_part_result_review"

    design_result = run_provider_normalized_design_create_pipeline(SMOKE_PROMPT, adapter, output_dir=design_dir)
    assembly_plan_path = design_dir / "assembly_plan.json"
    if not assembly_plan_path.exists():
        return _summary_from_results(identity, design_result=design_result)

    assembly_plan = json.loads(assembly_plan_path.read_text(encoding="utf-8"))
    part_selection = select_candidate_part(assembly_plan, requested_part_id=requested_part_id)
    selected_part_id = part_selection["selected_part_id"]
    if selected_part_id is None:
        return _summary_from_results(
            identity,
            design_result=design_result,
            assembly_plan=assembly_plan,
            requested_part_id=requested_part_id,
            part_selection=part_selection,
        )

    part_request_result = run_assembly_part_request_pipeline(
        assembly_plan_path,
        output_dir=part_request_dir,
        part_id=selected_part_id,
    )
    review_result = run_part_request_review_pipeline(
        part_request_dir / "part_create_request.json",
        output_dir=review_dir,
    )
    handoff_result = run_reviewed_part_handoff_pipeline(
        part_request_dir / "part_create_request.json",
        review_dir / "part_request_review.json",
        output_dir=handoff_dir,
    )
    bridge_result = run_reviewed_part_single_create_pipeline(
        handoff_dir / "reviewed_part_handoff.json",
        adapter,
        output_dir=bridge_dir,
    )
    part_result_review_result = None
    child_run_name = _safe_child_run_name(bridge_result)
    child_dir = bridge_dir / child_run_name if child_run_name else None
    if child_dir is not None and child_dir.exists():
        part_result_review_result = run_part_result_review_pipeline(
            handoff_dir / "reviewed_part_handoff.json",
            child_dir,
            output_dir=part_result_review_dir,
        )
    return _summary_from_results(
        identity,
        design_result=design_result,
        assembly_plan=assembly_plan,
        requested_part_id=requested_part_id,
        part_selection=part_selection,
        selected_part_id=selected_part_id,
        part_request_result=part_request_result,
        review_result=review_result,
        handoff_result=handoff_result,
        bridge_result=bridge_result,
        bridge_dir=bridge_dir,
        part_result_review_result=part_result_review_result,
    )


def select_one_candidate_part_id(assembly_plan: dict[str, Any]) -> str | None:
    return select_candidate_part(assembly_plan)["selected_part_id"]


def select_candidate_part(assembly_plan: dict[str, Any], *, requested_part_id: str | None = None) -> dict[str, Any]:
    parts = assembly_plan.get("parts") if isinstance(assembly_plan.get("parts"), list) else []
    candidate_part_ids: list[str] = []
    reference_only_part_ids: list[str] = []
    blocked_part_ids: list[str] = []
    matches: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_id = _safe_artifact_id(part.get("part_id"))
        if not part_id:
            continue
        if _is_reference_hardware_part_id(part_id) or part.get("part_status") == "reference_only":
            reference_only_part_ids.append(part_id)
        if part.get("part_status") == "blocked" or part.get("generation_strategy") == "blocked":
            blocked_part_ids.append(part_id)
        if _is_candidate_part(part):
            candidate_part_ids.append(part_id)
        if requested_part_id and part_id == requested_part_id:
            matches.append(part)

    status = "selected"
    selected_part_id: str | None = None
    diagnostic_codes: list[str] = []

    if requested_part_id:
        if not matches:
            status = "blocked_requested_part_not_found"
            diagnostic_codes.append("part_selection.requested_part_not_found")
        elif len(matches) > 1:
            status = "blocked_ambiguous_part_id"
            diagnostic_codes.append("part_selection.ambiguous_part_id")
        else:
            selected_part = matches[0]
            selected_part_id = _safe_artifact_id(selected_part.get("part_id"))
            if _is_reference_hardware_part_id(selected_part_id) or selected_part.get("part_status") == "reference_only":
                status = "blocked_reference_only_part"
                selected_part_id = None
                diagnostic_codes.append("part_selection.reference_only_not_selectable")
            elif selected_part.get("part_status") == "blocked" or selected_part.get("generation_strategy") == "blocked":
                status = "blocked_part_not_selectable"
                selected_part_id = None
                diagnostic_codes.append("part_selection.blocked_part_not_selectable")
            elif not _is_candidate_part(selected_part):
                status = "blocked_requested_part_not_candidate"
                selected_part_id = None
                diagnostic_codes.append("part_selection.requested_part_not_candidate")
            else:
                diagnostic_codes.append("part_selection.requested_part_selected")
    elif candidate_part_ids:
        selected_part_id = candidate_part_ids[0]
        diagnostic_codes.append("part_selection.default_candidate_selected")
    else:
        status = "blocked_no_candidate_part"
        diagnostic_codes.append("part_selection.no_candidate_part")

    return {
        "requested_part_id": requested_part_id,
        "selected_part_id": selected_part_id,
        "status": status,
        "diagnostic_codes": _collect_diagnostic_codes({"diagnostic_codes": diagnostic_codes}),
        "candidate_part_ids": sorted(set(candidate_part_ids)),
        "reference_only_part_ids": sorted(set(reference_only_part_ids)),
        "blocked_part_ids": sorted(set(blocked_part_ids)),
    }


def _is_candidate_part(part: dict[str, Any]) -> bool:
    part_id = _safe_artifact_id(part.get("part_id"))
    return (
        bool(part_id)
        and not _is_reference_hardware_part_id(part_id)
        and part.get("supported_candidate") is True
        and part.get("part_status") == "candidate_for_single_part_generation"
        and part.get("generation_strategy") != "blocked"
    )


def _is_reference_hardware_part_id(part_id: str) -> bool:
    return part_id in {"pin", "pins", "screw", "screws", "bolt", "bolts", "nut", "nuts", "washer", "washers", "fastener", "fasteners"}


def selection_diagnostics(assembly_plan: dict[str, Any]) -> dict[str, Any]:
    parts = assembly_plan.get("parts") if isinstance(assembly_plan.get("parts"), list) else []
    part_status_counts: dict[str, int] = {}
    generation_strategy_counts: dict[str, int] = {}
    candidate_part_ids: list[str] = []
    blocked_reason_codes: set[str] = set()
    reference_only_count = 0
    blocked_part_count = 0
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_id = _safe_artifact_id(part.get("part_id"))
        status = _safe_status(part.get("part_status"))
        strategy = _safe_status(part.get("generation_strategy"))
        if status:
            part_status_counts[status] = part_status_counts.get(status, 0) + 1
        if strategy:
            generation_strategy_counts[strategy] = generation_strategy_counts.get(strategy, 0) + 1
        if status == "reference_only":
            reference_only_count += 1
        if status == "blocked":
            blocked_part_count += 1
        if part.get("supported_candidate") is True:
            candidate_part_ids.append(part_id)
        for reason in part.get("blocked_reasons", []):
            if not isinstance(reason, dict):
                continue
            code = _safe_status(reason.get("code"))
            if code:
                blocked_reason_codes.add(code)
    quality = assembly_plan.get("quality") if isinstance(assembly_plan.get("quality"), dict) else {}
    for code in quality.get("blocked_reason_codes", []):
        safe = _safe_status(code)
        if safe:
            blocked_reason_codes.add(safe)
    return {
        "part_count": len([part for part in parts if isinstance(part, dict)]),
        "candidate_part_count": len(candidate_part_ids),
        "reference_only_count": reference_only_count,
        "blocked_part_count": blocked_part_count,
        "part_status_counts": dict(sorted(part_status_counts.items())),
        "generation_strategy_counts": dict(sorted(generation_strategy_counts.items())),
        "candidate_part_ids": sorted(candidate_part_ids),
        "blocked_reason_codes": sorted(blocked_reason_codes),
    }


def _summary_from_results(
    identity: dict[str, Any],
    *,
    design_result: dict[str, Any] | None = None,
    assembly_plan: dict[str, Any] | None = None,
    requested_part_id: str | None = None,
    part_selection: dict[str, Any] | None = None,
    selected_part_id: str | None = None,
    part_request_result: dict[str, Any] | None = None,
    review_result: dict[str, Any] | None = None,
    handoff_result: dict[str, Any] | None = None,
    bridge_result: dict[str, Any] | None = None,
    bridge_dir: Path | None = None,
    part_result_review_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = _base_summary(identity)
    assembly_plan_created = isinstance(assembly_plan, dict)
    child_run_name = _safe_child_run_name(bridge_result)
    child_dir = bridge_dir / child_run_name if bridge_dir is not None and child_run_name else None
    summary.update({
        "assembly_plan_created": assembly_plan_created,
        "requested_part_id": _safe_artifact_id(requested_part_id) if requested_part_id else None,
        "selected_part_id": selected_part_id,
        "part_selection_status": _safe_status((part_selection or {}).get("status")),
        "part_selection_diagnostic_codes": _collect_diagnostic_codes(part_selection),
        "candidate_part_ids": _safe_part_id_list((part_selection or {}).get("candidate_part_ids")),
        "reference_only_part_ids": _safe_part_id_list((part_selection or {}).get("reference_only_part_ids")),
        "blocked_part_ids": _safe_part_id_list((part_selection or {}).get("blocked_part_ids")),
        "part_request_status": _safe_status((part_request_result or {}).get("status")),
        "review_status": _safe_status((review_result or {}).get("status")),
        "handoff_status": _safe_status((handoff_result or {}).get("status")),
        "bridge_status": _safe_status((bridge_result or design_result or {}).get("status")),
        "child_run_created": bool(child_dir and child_dir.exists()),
        "child_run_name": child_run_name,
        "child_diagnostic_codes": _collect_child_diagnostic_codes(bridge_result, child_dir),
        "part_result_review_created": isinstance((part_result_review_result or {}).get("part_result_review"), dict),
        "part_result_review_status": _safe_status((part_result_review_result or {}).get("status")),
        "part_result_diagnostic_codes": _safe_part_result_diagnostic_codes(part_result_review_result),
        "part_result_step_check": _safe_part_result_check(part_result_review_result, "step_created"),
        "part_result_stl_check": _safe_part_result_check(part_result_review_result, "stl_created"),
        "part_result_single_part_scope_check": _safe_part_result_scope_check(part_result_review_result),
        "part_result_lineage_check": _safe_part_result_check(part_result_review_result, "lineage_preserved"),
        "part_result_interface_metadata_check": _safe_part_result_check(
            part_result_review_result,
            "interface_constraints_preserved_in_metadata",
        ),
        "step_created": bool(child_dir and (child_dir / "model.step").exists()),
        "stl_created": bool(child_dir and (child_dir / "model.stl").exists()),
        "no_batch_generation": _count_child_run_dirs(bridge_dir) <= 1,
        "no_assembly_generation": _no_assembly_generation(bridge_dir),
        "no_assembly_constraints_solved": _no_assembly_constraints_solved(bridge_dir),
        "diagnostic_codes": _collect_diagnostic_codes(
            design_result,
            part_selection,
            part_request_result,
            review_result,
            handoff_result,
            bridge_result,
            {"diagnostic_codes": _collect_child_diagnostic_codes(bridge_result, child_dir)},
            {"diagnostic_codes": _safe_part_result_diagnostic_codes(part_result_review_result)},
        ),
    })
    if isinstance(assembly_plan, dict) and selected_part_id is None:
        summary["selection_diagnostics"] = selection_diagnostics(assembly_plan)
    error_category = (bridge_result or design_result or {}).get("error_category")
    if isinstance(error_category, str):
        summary["error_category"] = _safe_status(error_category)
    if summary.get("bridge_status") != "success" and error_category == "auth_failed":
        summary["message"] = "Provider credentials are missing or not accepted."
    return summary


def _base_summary(identity: dict[str, Any], *, error_category: str | None = None) -> dict[str, Any]:
    summary = {
        "provider": identity.get("provider"),
        "model": identity.get("model"),
        "source_prompt_case": SOURCE_PROMPT_CASE,
        "assembly_plan_created": False,
        "requested_part_id": None,
        "selected_part_id": None,
        "part_selection_status": None,
        "part_selection_diagnostic_codes": [],
        "candidate_part_ids": [],
        "reference_only_part_ids": [],
        "blocked_part_ids": [],
        "part_request_status": None,
        "review_status": None,
        "handoff_status": None,
        "bridge_status": "not_run",
        "child_run_created": False,
        "child_run_name": None,
        "child_diagnostic_codes": [],
        "part_result_review_created": False,
        "part_result_review_status": None,
        "part_result_diagnostic_codes": [],
        "part_result_step_check": None,
        "part_result_stl_check": None,
        "part_result_single_part_scope_check": None,
        "part_result_lineage_check": None,
        "part_result_interface_metadata_check": None,
        "step_created": False,
        "stl_created": False,
        "no_batch_generation": True,
        "no_assembly_generation": True,
        "no_assembly_constraints_solved": True,
        "diagnostic_codes": [],
    }
    if error_category:
        summary["bridge_status"] = "provider_error"
        summary["error_category"] = _safe_status(error_category)
        if error_category == "auth_failed":
            summary["message"] = "Provider credentials are missing or not accepted."
    return summary


def _safe_identity(identity: Any) -> dict[str, Any]:
    if not isinstance(identity, dict):
        return {}
    return {
        key: value
        for key, value in identity.items()
        if key in {"provider", "model"} and isinstance(value, (str, int, float, bool))
    }


def _safe_artifact_id(value: Any) -> str:
    text = str(value or "component").strip().lower()
    safe = "".join(char if char.isalnum() or char == "_" else "_" for char in text).strip("_")
    return safe or "component"


def _safe_status(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    safe = "".join(char if char.isalnum() or char in "_.-" else "_" for char in value.strip()).strip("_")
    return safe or None


def _safe_part_id_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({_safe_artifact_id(item) for item in value if _safe_artifact_id(item)})


def _safe_child_run_name(bridge_result: dict[str, Any] | None) -> str | None:
    if not isinstance(bridge_result, dict):
        return None
    child_dir = bridge_result.get("child_output_dir")
    if not isinstance(child_dir, str):
        return None
    return Path(child_dir).name


def _count_child_run_dirs(bridge_dir: Path | None) -> int:
    if bridge_dir is None or not bridge_dir.exists():
        return 0
    return sum(1 for path in bridge_dir.iterdir() if path.is_dir() and path.name.startswith("single_part_"))


def _no_assembly_generation(bridge_dir: Path | None) -> bool:
    if bridge_dir is None or not bridge_dir.exists():
        return True
    blocked_names = {"assembly.step", "assembly.stl", "assembly_constraints.json"}
    if (bridge_dir / "model.step").exists() or (bridge_dir / "model.stl").exists():
        return False
    return not any(path.name.lower() in blocked_names for path in bridge_dir.rglob("*"))


def _no_assembly_constraints_solved(bridge_dir: Path | None) -> bool:
    if bridge_dir is None or not bridge_dir.exists():
        return True
    blocked_names = {"assembly_constraints.json", "constraints.json", "joints.json"}
    return not any(path.name.lower() in blocked_names for path in bridge_dir.rglob("*"))


def _collect_diagnostic_codes(*results: dict[str, Any] | None) -> list[str]:
    codes: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        for code in result.get("diagnostic_codes", []):
            safe = _safe_status(code)
            if safe:
                codes.add(safe)
    return sorted(codes)


def _safe_part_result_review(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    review = result.get("part_result_review")
    return review if isinstance(review, dict) else {}


def _safe_part_result_diagnostic_codes(result: dict[str, Any] | None) -> list[str]:
    review = _safe_part_result_review(result)
    return _collect_diagnostic_codes(review)


def _safe_part_result_check(result: dict[str, Any] | None, key: str) -> bool | None:
    review = _safe_part_result_review(result)
    checks = review.get("checks") if isinstance(review.get("checks"), dict) else {}
    value = checks.get(key)
    return value if isinstance(value, bool) else None


def _safe_part_result_scope_check(result: dict[str, Any] | None) -> bool | None:
    values = [
        _safe_part_result_check(result, "single_part_only"),
        _safe_part_result_check(result, "no_batch_generation"),
        _safe_part_result_check(result, "no_assembly_generation"),
    ]
    if any(value is None for value in values):
        return None
    return all(values)


def _collect_child_diagnostic_codes(bridge_result: dict[str, Any] | None, child_dir: Path | None) -> list[str]:
    codes: set[str] = set()

    def add_from(value: Any) -> None:
        if isinstance(value, dict):
            for code in value.get("diagnostic_codes", []):
                safe = _safe_status(code)
                if safe:
                    codes.add(safe)
            for key in ("provider_create", "requirement_status", "child_result"):
                add_from(value.get(key))

    if isinstance(bridge_result, dict):
        add_from(bridge_result.get("child_result"))
    if child_dir is not None and child_dir.exists():
        report_path = child_dir / "report.json"
        if report_path.exists():
            try:
                add_from(json.loads(report_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass
    return sorted(codes)


if __name__ == "__main__":
    raise SystemExit(main())
