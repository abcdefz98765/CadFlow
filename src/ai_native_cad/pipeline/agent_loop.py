"""Stateful CAD agent loop controller."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from ai_native_cad.cad_ir.repair import repair_ir
from ai_native_cad.cad_ir.schema import CADIR
from ai_native_cad.cadquery.executor import execute_model
from ai_native_cad.cadquery.generator import generate_cadquery_candidates
from ai_native_cad.pipeline.failure_analyzer import analyze_failure
from ai_native_cad.pipeline.scorer import score_candidate
from ai_native_cad.pipeline.validator import validate_pipeline_outputs
from ai_native_cad.workflow_control import part_modeling_final_decision, part_modeling_retry_decision

MAX_ATTEMPTS = 3


def run_agent_loop(ir: CADIR | dict[str, Any], output_dir: str | Path, max_attempts: int = MAX_ATTEMPTS) -> dict[str, Any]:
    """Run IR -> candidate code -> execution -> validation -> repair retries."""
    current_ir = CADIR.from_dict(ir) if isinstance(ir, dict) else ir
    output_path = Path(output_dir)
    trace: dict[str, Any] = {
        "total_attempts": 0,
        "steps": [],
        "final_selected_candidate": None,
        "max_attempts": max_attempts,
        "part_modeling_contract": {
            "geometry_source": "cad_ir",
            "allowed_knowledge": ["template_candidates", "feature_library", "backend_capabilities"],
            "planning_context": _planning_context(current_ir),
            "does_not_own": [
                "product_requirement_changes",
                "part_structure_redesign",
                "assembly_placement_decisions",
            ],
        },
    }
    last_execution: dict[str, Any] = {"status": "not_run"}
    last_validation: dict[str, Any] = {"valid": False, "errors": []}
    selected_code: str | None = None
    selected_ir = current_ir

    for attempt in range(1, max_attempts + 1):
        trace["total_attempts"] = attempt
        candidates = generate_cadquery_candidates(current_ir, max_candidates=3)
        attempt_results = []

        for candidate in candidates:
            execution = execute_model(candidate["code"], output_path)
            model = _load_generated_model(output_path / "model.py", current_ir.to_dict()) if execution["status"] == "success" else None
            (output_path / "report.json").write_text("{}\n", encoding="utf-8")
            validation = validate_pipeline_outputs(model, output_path, current_ir, execution)
            score = score_candidate(candidate["candidate"], validation, execution)
            attempt_results.append({
                "candidate": candidate["candidate"],
                "strategy": candidate["strategy"],
                "score": score["score"],
                "execution": execution,
                "validation": validation,
                "code": candidate["code"],
            })

        best = _select_best(attempt_results)
        last_execution = best["execution"]
        last_validation = best["validation"]
        selected_code = best["code"]
        selected_ir = current_ir

        step = {
            "attempt": attempt,
            "status": "success" if best["validation"].get("valid") and best["execution"].get("status") == "success" else "failed",
            "candidate_scores": [
                {"candidate": item["candidate"], "strategy": item["strategy"], "score": item["score"]}
                for item in attempt_results
            ],
            "selected_candidate": best["candidate"],
            "measured_validation_targets": best["validation"].get("measured_validation_targets", []),
            "inspection_summary": _inspection_summary(best["validation"].get("inspection", {})),
        }

        if step["status"] == "success":
            trace["final_selected_candidate"] = best["candidate"]
            trace["steps"].append(step)
            final_execution, final_validation = _materialize_selected(output_path, selected_code, selected_ir)
            trace["final_execution_status"] = final_execution.get("status")
            trace["final_measured_validation_targets"] = final_validation.get("measured_validation_targets", [])
            trace["final_inspection_summary"] = _inspection_summary(final_validation.get("inspection", {}))
            trace["final_flow_decision"] = part_modeling_final_decision(
                status="success" if final_execution.get("status") == "success" and final_validation.get("valid") else "failed",
                validation=final_validation,
            )
            _write_trace(output_path, trace)
            return {
                "status": "success" if final_execution.get("status") == "success" and final_validation.get("valid") else "failed",
                "ir": selected_ir.to_dict(),
                "execution": final_execution,
                "validation": final_validation,
                "agent_trace": trace,
            }

        failure = analyze_failure(best["execution"], best["validation"])
        repaired = repair_ir(current_ir, failure)
        step["reason"] = failure["root_cause"]
        step["failure_analysis"] = failure
        step["ir_repair"] = {
            "changes": repaired["changes"],
            "diff": repaired.get("diff", []),
            "repaired_ir": repaired["repaired_ir"],
        }
        step["rework_decision"] = part_modeling_retry_decision(failure, repaired)
        trace["steps"].append(step)
        current_ir = CADIR.from_dict(repaired["repaired_ir"])

    trace["final_selected_candidate"] = best["candidate"] if selected_code else None
    trace["final_measured_validation_targets"] = last_validation.get("measured_validation_targets", [])
    trace["final_inspection_summary"] = _inspection_summary(last_validation.get("inspection", {}))
    trace["final_flow_decision"] = part_modeling_final_decision(status="failed", validation=last_validation)
    _write_trace(output_path, trace)
    return {
        "status": "failed",
        "ir": selected_ir.to_dict(),
        "execution": last_execution,
        "validation": last_validation,
        "agent_trace": trace,
    }


def _select_best(attempt_results: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(attempt_results, key=lambda item: (item["validation"].get("valid", False), item["score"]), reverse=True)[0]


def _materialize_selected(output_path: Path, code: str, cad_ir: CADIR) -> tuple[dict[str, Any], dict[str, Any]]:
    execution = execute_model(code, output_path)
    model = _load_generated_model(output_path / "model.py", cad_ir.to_dict()) if execution["status"] == "success" else None
    (output_path / "report.json").write_text("{}\n", encoding="utf-8")
    validation = validate_pipeline_outputs(model, output_path, cad_ir, execution)
    return execution, validation


def _load_generated_model(model_path: Path, ir_data: dict[str, Any]) -> Any:
    spec = importlib.util.spec_from_file_location(f"generated_{ir_data['part_name']}", model_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load generated model: {model_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_model(ir_data)


def _write_trace(output_path: Path, trace: dict[str, Any]) -> None:
    (output_path / "agent_trace.json").write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")


def _planning_context(cad_ir: CADIR) -> dict[str, Any]:
    handoff = cad_ir.source.get("planning_handoff", {})
    context = handoff.get("part_modeling_context", {})
    if not isinstance(context, dict):
        return {}
    part_name = cad_ir.part_name or cad_ir.part_type
    parts = context.get("parts", [])
    if isinstance(parts, list):
        matched = [part for part in parts if isinstance(part, dict) and part.get("part_name") == part_name]
        if matched:
            return {
                "geometry_authority": context.get("geometry_authority"),
                "allowed_context_fields": context.get("allowed_context_fields", []),
                "part": matched[0],
            }
    return {
        "geometry_authority": context.get("geometry_authority"),
        "allowed_context_fields": context.get("allowed_context_fields", []),
    }


def _inspection_summary(inspection: dict[str, Any]) -> dict[str, Any]:
    step_file = inspection.get("step_file", {})
    stl_file = inspection.get("stl_file", {})
    holes = inspection.get("features", {}).get("holes", {})
    spacing = holes.get("spacing", {}) if isinstance(holes, dict) else {}
    return {
        "primary_artifact": inspection.get("artifact_roles", {}).get("primary", "model.step"),
        "solid_count": inspection.get("solid_count"),
        "bounding_box": inspection.get("bounding_box", {}),
        "volume": inspection.get("volume", 0.0),
        "step_file": {
            "present": bool(step_file.get("present")),
            "size_bytes": int(step_file.get("size_bytes", 0) or 0),
        },
        "stl_file": {
            "present": bool(stl_file.get("present")),
            "size_bytes": int(stl_file.get("size_bytes", 0) or 0),
        },
        "hole_spacing_status": spacing.get("status"),
        "features": inspection.get("features", {}),
    }
