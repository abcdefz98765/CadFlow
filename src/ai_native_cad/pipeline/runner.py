"""IR-first CAD pipeline runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_native_cad.cad_ir.parser import ir_from_planning_artifact
from ai_native_cad.cad_ir.schema import CADIR
from ai_native_cad.cad_ir.validator import validate_ir
from ai_native_cad.pipeline.agent_loop import run_agent_loop
from ai_native_cad.pipeline.report import write_pipeline_report
from ai_native_cad.planning import PlanningHandoffBlocked, create_planning_artifact
from ai_native_cad.requirements import RequirementAgent
from ai_native_cad.workflow_control import cad_ir_to_part_modeling_decision, is_proceed_action

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def run_text_pipeline(
    text: str,
    output_root: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run Text -> Requirement -> Planning -> CAD IR -> Part Modeling.

    This is the formal natural-language path. CAD IR is created only from
    ``planning_artifact.selected_parts[].resolved_decisions`` after both
    handoff gates have allowed the flow to proceed.
    """

    requirement = RequirementAgent().parse(text, overrides)
    part_name = requirement.get("instance_name") or requirement.get("part_name") or requirement.get("part_type", "prompt")
    output_dir = _resolve_output_dir(part_name, output_root, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "prompt.txt").write_text(text.strip() + "\n", encoding="utf-8")
    (output_dir / "requirement.json").write_text(
        json.dumps(requirement, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    requirement_decision = requirement.get("requirement_status", {}).get("flow_decision", {})
    if not is_proceed_action(requirement_decision.get("action")):
        return _write_blocked_text_pipeline_result(
            output_dir=output_dir,
            stage="requirement",
            requirement=requirement,
            planning_artifact=None,
            flow_decision=requirement_decision,
            reasons=requirement_decision.get("reasons", []),
        )

    planning_artifact = create_planning_artifact(requirement)
    (output_dir / "planning_artifact.json").write_text(
        json.dumps(planning_artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    planning_decision = planning_artifact.get("flow_gate_status", {}).get("rework_decision", {})
    if not is_proceed_action(planning_decision.get("action")):
        return _write_blocked_text_pipeline_result(
            output_dir=output_dir,
            stage="planning",
            requirement=requirement,
            planning_artifact=planning_artifact,
            flow_decision=planning_decision,
            reasons=planning_decision.get("reasons", []),
        )

    try:
        ir = ir_from_planning_artifact(planning_artifact)
    except PlanningHandoffBlocked as exc:
        return _write_blocked_text_pipeline_result(
            output_dir=output_dir,
            stage="planning",
            requirement=requirement,
            planning_artifact=planning_artifact,
            flow_decision=planning_decision,
            reasons=exc.reasons,
        )

    result = run_ir_pipeline(ir, output_dir=output_dir)
    result["requirement"] = requirement
    result["planning_artifact"] = planning_artifact
    result["text_pipeline"] = {
        "path": "prompt_to_requirement_to_planning_to_cad_ir_to_part_modeling",
        "requirement_decision": requirement_decision,
        "planning_decision": planning_decision,
    }
    result["files"] = _collect_files(output_dir)
    return result


def run_ir_pipeline(
    ir: CADIR | dict[str, Any],
    output_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run a complete CAD agent generation from CAD IR."""
    cad_ir = CADIR.from_dict(ir) if isinstance(ir, dict) else ir
    ir_data = cad_ir.to_dict()
    part_name = ir_data.get("part_name") or ir_data["part_type"]
    output_dir = _resolve_output_dir(part_name, output_root, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "input_ir.json").write_text(json.dumps(ir_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ir_validation = validate_ir(cad_ir)
    flow_decision = cad_ir_to_part_modeling_decision(ir_validation)
    if not ir_validation["valid"]:
        files = _collect_files(output_dir)
        reasons = flow_decision.get("reasons", [])
        validation = {
            "valid": False,
            "execution_success": False,
            "step_generated": False,
            "stl_generated": False,
            "report_generated": False,
            "bounding_box": {},
            "volume": 0.0,
            "inspection": {},
            "measured_validation_targets": [],
            "checks": [],
            "warnings": [],
            "errors": reasons or [{"code": "ir_invalid", "message": "CAD IR validation failed"}],
        }
        (output_dir / "agent_trace.json").write_text(json.dumps({
            "total_attempts": 0,
            "steps": [{
                "attempt": 0,
                "status": "blocked",
                "reason": "cad_ir_not_implementable_by_part_modeling",
                "rework_decision": flow_decision,
            }],
            "final_selected_candidate": None,
            "flow_decision": flow_decision,
            "rework_decision": flow_decision,
            "final_flow_decision": flow_decision,
            "part_modeling_contract": {
                "geometry_source": "cad_ir",
                "allowed_knowledge": ["template_candidates", "feature_library", "backend_capabilities"],
                "planning_context": _planning_context(cad_ir),
                "does_not_own": [
                    "product_requirement_changes",
                    "part_structure_redesign",
                    "assembly_placement_decisions",
                ],
            },
        }, indent=2) + "\n", encoding="utf-8")
        report = write_pipeline_report(
            output_dir,
            ir_data,
            {"status": "not_run"},
            validation,
            files,
            ir_validation=ir_validation,
            rework_decision=flow_decision,
        )
        files = _collect_files(output_dir)
        return {
            "status": "failed",
            "ir": ir_data,
            "output_dir": str(output_dir),
            "validation": ir_validation,
            "flow_decision": flow_decision,
            "files": files,
            **report,
        }

    loop_result = run_agent_loop(cad_ir, output_dir)
    execution = loop_result["execution"]
    validation = loop_result["validation"]
    final_ir = loop_result.get("ir", ir_data)
    files = _collect_files(output_dir)
    rework_decision = loop_result["agent_trace"].get("rework_decision")
    report = write_pipeline_report(
        output_dir,
        final_ir,
        execution,
        validation,
        files,
        ir_validation=ir_validation,
        rework_decision=rework_decision,
    )
    files = _collect_files(output_dir)
    status = "success" if execution["status"] == "success" and validation.get("valid") else "failed"
    return {
        "status": status,
        "ir": final_ir,
        "output_dir": str(output_dir),
        "execution": execution,
        "validation": validation,
        "agent_trace": loop_result["agent_trace"],
        "flow_decision": flow_decision,
        "files": files,
        **report,
    }


def _collect_files(output_dir: Path) -> dict[str, str]:
    files = {}
    labels = {
        "prompt.txt": "prompt",
        "requirement.json": "requirement",
        "planning_artifact.json": "planning_artifact",
        "input_ir.json": "input_ir",
        "model.py": "model_py",
        "model.step": "step",
        "model.stl": "stl",
        "preview.png": "preview",
        "report.json": "report_json",
        "report.md": "report_md",
        "agent_trace.json": "agent_trace",
    }
    for name, label in labels.items():
        path = output_dir / name
        if path.exists():
            files[label] = str(path)
    return files


def _resolve_output_dir(part_name: str, output_root: str | Path | None, output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        resolved = Path(output_dir)
        if not resolved.is_absolute():
            resolved = PROJECT_ROOT / resolved
        return _require_repo_path(resolved.resolve())

    root = Path(output_root) if output_root is not None else PROJECT_ROOT / "outputs"
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    return _require_repo_path((root / part_name).resolve())


def _require_repo_path(path: Path) -> Path:
    repo_root = PROJECT_ROOT.resolve()
    try:
        path.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"pipeline outputs must be written inside project root: {repo_root}") from exc
    return path


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


def _write_blocked_text_pipeline_result(
    *,
    output_dir: Path,
    stage: str,
    requirement: dict[str, Any],
    planning_artifact: dict[str, Any] | None,
    flow_decision: dict[str, Any],
    reasons: list[dict[str, Any]],
) -> dict[str, Any]:
    trace = {
        "total_attempts": 0,
        "steps": [{"attempt": 0, "status": "blocked", "stage": stage, "reasons": reasons}],
        "final_selected_candidate": None,
        "flow_decision": flow_decision,
        "rework_decision": flow_decision,
        "text_pipeline": {
            "blocked_stage": stage,
            "cad_ir_created": False,
            "part_modeling_started": False,
        },
    }
    (output_dir / "agent_trace.json").write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    report = {
        "success": False,
        "status": "blocked",
        "blocked_stage": stage,
        "flow_decision": flow_decision,
        "rework_decision": flow_decision,
        "reasons": reasons,
        "part_type": requirement.get("part_type"),
        "part_name": requirement.get("instance_name") or requirement.get("part_name") or requirement.get("part_type"),
        "requirement_status": requirement.get("requirement_status", {}),
        "planning_gate_status": (planning_artifact or {}).get("flow_gate_status"),
        "cad_ir_created": False,
        "part_modeling_started": False,
        "files": _collect_files(output_dir),
    }
    lines = [
        "# Text Pipeline Report",
        "",
        "**Status:** blocked",
        f"**Blocked stage:** {stage}",
        f"**Flow action:** {flow_decision.get('action')}",
        f"**Return to:** {flow_decision.get('to_stage')}",
        "",
        "## Reasons",
        "",
    ]
    if reasons:
        lines.extend(f"- {reason.get('code', 'blocked')}: {reason.get('message', reason)}" for reason in reasons)
    else:
        lines.append("- Flow gate returned a non-proceed decision.")
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    files = _collect_files(output_dir)
    report["files"] = files
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {
        "status": "blocked",
        "blocked_stage": stage,
        "requirement": requirement,
        "planning_artifact": planning_artifact,
        "output_dir": str(output_dir),
        "flow_decision": flow_decision,
        "rework_decision": flow_decision,
        "agent_trace": trace,
        "files": files,
        "report_json": str(output_dir / "report.json"),
        "report_md": str(output_dir / "report.md"),
    }
