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
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory. Defaults under ignored outputs/provider_smoke/.",
    )
    args = parser.parse_args(argv)

    output_root = Path(args.output_dir) if args.output_dir else REPO_ROOT / "outputs" / "provider_smoke" / "reviewed_part_single_create"
    try:
        load_env_file(args.env_file)
        adapter = make_json_contract_adapter_from_env(args.provider, model=args.model)
        summary = run_reviewed_part_single_create_smoke(adapter, args.provider, output_root)
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


def run_reviewed_part_single_create_smoke(adapter: Any, provider: str, output_root: Path) -> dict[str, Any]:
    identity = _safe_identity(getattr(adapter, "provider_identity", {"provider": provider}))
    design_dir = output_root / "01_design"
    part_request_dir = output_root / "02_part_request"
    review_dir = output_root / "03_review"
    handoff_dir = output_root / "04_handoff"
    bridge_dir = output_root / "05_single_create"

    design_result = run_provider_normalized_design_create_pipeline(SMOKE_PROMPT, adapter, output_dir=design_dir)
    assembly_plan_path = design_dir / "assembly_plan.json"
    if not assembly_plan_path.exists():
        return _summary_from_results(identity, design_result=design_result)

    assembly_plan = json.loads(assembly_plan_path.read_text(encoding="utf-8"))
    selected_part_id = select_one_candidate_part_id(assembly_plan)
    if selected_part_id is None:
        return _summary_from_results(identity, design_result=design_result, assembly_plan=assembly_plan)

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
    return _summary_from_results(
        identity,
        design_result=design_result,
        assembly_plan=assembly_plan,
        selected_part_id=selected_part_id,
        part_request_result=part_request_result,
        review_result=review_result,
        handoff_result=handoff_result,
        bridge_result=bridge_result,
        bridge_dir=bridge_dir,
    )


def select_one_candidate_part_id(assembly_plan: dict[str, Any]) -> str | None:
    parts = assembly_plan.get("parts") if isinstance(assembly_plan.get("parts"), list) else []
    selected: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_id = _safe_artifact_id(part.get("part_id"))
        if part_id in {"screw", "screws", "bolt", "bolts", "nut", "nuts", "washer", "washers", "fastener", "fasteners"}:
            continue
        if part.get("supported_candidate") is True and part.get("part_status") == "candidate_for_single_part_generation":
            selected.append(part_id)
    return selected[0] if selected else None


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
    selected_part_id: str | None = None,
    part_request_result: dict[str, Any] | None = None,
    review_result: dict[str, Any] | None = None,
    handoff_result: dict[str, Any] | None = None,
    bridge_result: dict[str, Any] | None = None,
    bridge_dir: Path | None = None,
) -> dict[str, Any]:
    summary = _base_summary(identity)
    assembly_plan_created = isinstance(assembly_plan, dict)
    child_run_name = _safe_child_run_name(bridge_result)
    child_dir = bridge_dir / child_run_name if bridge_dir is not None and child_run_name else None
    summary.update({
        "assembly_plan_created": assembly_plan_created,
        "selected_part_id": selected_part_id,
        "part_request_status": _safe_status((part_request_result or {}).get("status")),
        "review_status": _safe_status((review_result or {}).get("status")),
        "handoff_status": _safe_status((handoff_result or {}).get("status")),
        "bridge_status": _safe_status((bridge_result or design_result or {}).get("status")),
        "child_run_created": bool(child_dir and child_dir.exists()),
        "child_run_name": child_run_name,
        "step_created": bool(child_dir and (child_dir / "model.step").exists()),
        "stl_created": bool(child_dir and (child_dir / "model.stl").exists()),
        "no_batch_generation": _count_child_run_dirs(bridge_dir) <= 1,
        "no_assembly_generation": _no_assembly_generation(bridge_dir),
        "no_assembly_constraints_solved": _no_assembly_constraints_solved(bridge_dir),
        "diagnostic_codes": _collect_diagnostic_codes(
            design_result,
            part_request_result,
            review_result,
            handoff_result,
            bridge_result,
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
        "selected_part_id": None,
        "part_request_status": None,
        "review_status": None,
        "handoff_status": None,
        "bridge_status": "not_run",
        "child_run_created": False,
        "child_run_name": None,
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


if __name__ == "__main__":
    raise SystemExit(main())
