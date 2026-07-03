"""IR-first CAD pipeline runner."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ai_native_cad.agents.base import AgentAdapter
from ai_native_cad.agents.json_contract import JsonContractProviderError
from ai_native_cad.agents.validation import validate_input_ir_draft
from ai_native_cad.cad_ir.parser import ir_from_planning_artifact
from ai_native_cad.cad_ir.schema import CADIR
from ai_native_cad.cad_ir.validator import validate_ir
from ai_native_cad.pipeline.agent_loop import run_agent_loop
from ai_native_cad.pipeline.report import write_pipeline_report
from ai_native_cad.planning import PlanningHandoffBlocked, create_planning_artifact
from ai_native_cad.requirements import RequirementAgent
from ai_native_cad.workflow_control import cad_ir_to_part_modeling_decision, is_proceed_action

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def run_provider_create_pipeline(
    prompt: str,
    adapter: AgentAdapter,
    output_dir: str | Path | None = None,
    output_root: str | Path | None = None,
    fallback_mode: str = "none",
    provider_contract_mode: str = "strict",
) -> dict[str, Any]:
    """Run provider Requirement + Planning into deterministic CAD generation.

    The provider participates only in parse_requirement and create_plan. CAD IR
    conversion and CAD execution stay local and validated. The default
    ``strict`` mode is a provider contract compliance path: provider outputs
    must already satisfy CadFlow contracts and are not silently compiled.
    """

    if fallback_mode not in {"none", "explicit"}:
        raise ValueError("fallback_mode must be 'none' or 'explicit'")
    if provider_contract_mode not in {"strict", "extract_then_compile"}:
        raise ValueError("provider_contract_mode must be 'strict' or 'extract_then_compile'")

    output_path = _resolve_output_dir(_agent_create_dir_name(prompt), output_root, output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "prompt.txt").write_text(prompt.strip() + "\n", encoding="utf-8")
    context = {
        "workflow_stage": "provider_create",
        "target_contract": "provider_requirement_planning_create_v0.1",
        "output_dir": str(output_path),
    }
    if provider_contract_mode == "extract_then_compile":
        context["provider_contract_mode"] = provider_contract_mode
    provider_traces: list[dict[str, Any]] = []

    try:
        requirement = adapter.parse_requirement(prompt, context=context)
    except JsonContractProviderError as exc:
        trace = _provider_stage_trace(adapter, "parse_requirement", validation_status="not_run", error_category=exc.category)
        provider_traces.append(trace)
        return _write_blocked_provider_create_result(
            output_path=output_path,
            status="blocked_provider_requirement",
            blocked_stage="requirement",
            adapter=adapter,
            provider_traces=provider_traces,
            error_category=exc.category,
            provider_contract_mode=provider_contract_mode,
        )
    except Exception:
        trace = _provider_stage_trace(
            adapter,
            "parse_requirement",
            validation_status="failed",
            error_category="local_validation_failed",
        )
        provider_traces.append(trace)
        return _write_blocked_provider_create_result(
            output_path=output_path,
            status="blocked_provider_validation",
            blocked_stage="requirement",
            adapter=adapter,
            provider_traces=provider_traces,
            error_category="local_validation_failed",
            provider_contract_mode=provider_contract_mode,
        )

    _write_json(output_path / "requirement.json", requirement)
    requirement_decision = requirement.get("requirement_status", {}).get("flow_decision", {})
    requirement_trace = _provider_stage_trace(adapter, "parse_requirement", validation_status="passed")
    provider_traces.append(requirement_trace)
    if not is_proceed_action(requirement_decision.get("action")):
        return _write_blocked_provider_create_result(
            output_path=output_path,
            status="blocked_provider_requirement",
            blocked_stage="requirement",
            adapter=adapter,
            provider_traces=provider_traces,
            requirement=requirement,
            error_category="requirement_gate_blocked",
            provider_contract_mode=provider_contract_mode,
        )

    try:
        planning_artifact = adapter.create_plan(requirement, context=context)
    except JsonContractProviderError as exc:
        trace = _provider_stage_trace(adapter, "create_plan", validation_status="not_run", error_category=exc.category)
        provider_traces.append(trace)
        return _write_blocked_provider_create_result(
            output_path=output_path,
            status="blocked_provider_planning",
            blocked_stage="planning",
            adapter=adapter,
            provider_traces=provider_traces,
            requirement=requirement,
            error_category=exc.category,
            provider_contract_mode=provider_contract_mode,
        )
    except Exception:
        trace = _provider_stage_trace(
            adapter,
            "create_plan",
            validation_status="failed",
            error_category="local_validation_failed",
        )
        provider_traces.append(trace)
        return _write_blocked_provider_create_result(
            output_path=output_path,
            status="blocked_provider_validation",
            blocked_stage="planning",
            adapter=adapter,
            provider_traces=provider_traces,
            requirement=requirement,
            error_category="local_validation_failed",
            provider_contract_mode=provider_contract_mode,
        )

    _write_json(output_path / "planning_artifact.json", planning_artifact)
    planning_trace = _provider_stage_trace(adapter, "create_plan", validation_status="passed")
    provider_traces.append(planning_trace)
    planning_decision = planning_artifact.get("flow_gate_status", {}).get("rework_decision", {})
    if not is_proceed_action(planning_decision.get("action")):
        return _write_blocked_provider_create_result(
            output_path=output_path,
            status="blocked_provider_planning",
            blocked_stage="planning",
            adapter=adapter,
            provider_traces=provider_traces,
            requirement=requirement,
            planning_artifact=planning_artifact,
            error_category="planning_gate_blocked",
            provider_contract_mode=provider_contract_mode,
        )

    try:
        ir = ir_from_planning_artifact(planning_artifact)
        input_ir = ir.to_dict()
        validate_input_ir_draft(input_ir)
    except Exception:
        return _write_blocked_provider_create_result(
            output_path=output_path,
            status="blocked_provider_validation",
            blocked_stage="cad_ir",
            adapter=adapter,
            provider_traces=provider_traces,
            requirement=requirement,
            planning_artifact=planning_artifact,
            error_category="cad_ir_validation_failed",
            provider_contract_mode=provider_contract_mode,
        )

    _write_json(output_path / "input_ir.json", input_ir)
    result = run_ir_pipeline(input_ir, output_dir=output_path)
    metadata = _provider_create_metadata(
        adapter=adapter,
        provider_traces=provider_traces,
        status=result.get("status", "unknown"),
        provider_contract_mode=provider_contract_mode,
        requirement_status="passed",
        planning_status="passed",
        ir_validation_status="passed",
        pipeline_status=result.get("status", "unknown"),
    )
    _merge_provider_create_metadata(output_path, metadata)
    _write_provider_create_runtime(output_path, metadata, status=result.get("status", "unknown"))
    files = _collect_files(output_path)
    result.update({
        "requirement": requirement,
        "planning_artifact": planning_artifact,
        "input_ir": input_ir,
        "provider_create": metadata,
        "files": files,
    })
    trace_path = output_path / "agent_trace.json"
    if trace_path.exists():
        result["agent_trace"] = json.loads(trace_path.read_text(encoding="utf-8"))
    return result


def run_provider_normalized_create_pipeline(
    prompt: str,
    adapter: AgentAdapter,
    output_dir: str | Path | None = None,
    output_root: str | Path | None = None,
    fallback_mode: str = "none",
) -> dict[str, Any]:
    """Run the recommended provider-backed normalized create workflow.

    Workflow:
    prompt -> provider extraction -> local requirement/planning compiler ->
    deterministic CAD IR conversion -> run_ir_pipeline.

    Provider output is treated as extracted intent/fields/constraints. CadFlow
    owns the internal requirement/planning contracts, CAD IR conversion, and CAD
    execution. This entry point never accepts provider-generated CAD IR or code.
    """

    return run_provider_create_pipeline(
        prompt,
        adapter,
        output_dir=output_dir,
        output_root=output_root,
        fallback_mode=fallback_mode,
        provider_contract_mode="extract_then_compile",
    )


def run_agent_create_pipeline(
    prompt: str,
    adapter: AgentAdapter,
    output_dir: str | Path | None = None,
    selected_candidate: str | None = None,
) -> dict[str, Any]:
    """Run the LLM-shaped create workflow into the existing IR pipeline."""

    output_path = _resolve_output_dir(_agent_create_dir_name(prompt), None, output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "prompt.txt").write_text(prompt.strip() + "\n", encoding="utf-8")

    context = {
        "workflow_stage": "agent_create",
        "target_contract": "llm_shaped_create_v0.5",
        "output_dir": str(output_path),
    }
    intent = adapter.interpret_user_intent(prompt, context=context)
    _write_json(output_path / "intent.json", intent)

    design_brief = adapter.propose_design_brief(intent, context=context)
    _write_json(output_path / "design_brief.json", design_brief)

    candidate_plans = adapter.generate_candidate_plans(design_brief, context=context)
    if not isinstance(candidate_plans, list) or not candidate_plans:
        raise ValueError("generate_candidate_plans must return a non-empty list")
    _write_json(output_path / "candidate_plans.json", candidate_plans)

    selected_plan = _select_candidate_plan(candidate_plans, selected_candidate)
    _write_json(output_path / "selected_plan.json", selected_plan)

    input_ir = adapter.convert_plan_to_ir(selected_plan, context=context)
    validate_input_ir_draft(input_ir)
    _write_json(output_path / "input_ir.json", input_ir)

    result = run_ir_pipeline(input_ir, output_dir=output_path)
    planning_metadata = {
        "workflow": "agent_create",
        "version": "llm-shaped-create-v0.5",
        "adapter": _safe_provider_identity(adapter),
        "stages": [
            "prompt",
            "interpret_user_intent",
            "propose_design_brief",
            "generate_candidate_plans",
            "select_candidate",
            "convert_plan_to_ir",
            "run_ir_pipeline",
        ],
        "artifacts": {
            "prompt": "prompt.txt",
            "intent": "intent.json",
            "design_brief": "design_brief.json",
            "candidate_plans": "candidate_plans.json",
            "selected_plan": "selected_plan.json",
            "input_ir": "input_ir.json",
        },
        "selected_candidate": selected_plan.get("candidate_id") or selected_plan.get("label"),
        "candidate_count": len(candidate_plans),
    }
    _merge_agent_create_metadata(output_path, planning_metadata)
    files = _collect_files(output_path)
    result.update({
        "intent": intent,
        "design_brief": design_brief,
        "candidate_plans": candidate_plans,
        "selected_plan": selected_plan,
        "input_ir": input_ir,
        "agent_create": planning_metadata,
        "files": files,
    })
    trace_path = output_path / "agent_trace.json"
    if trace_path.exists():
        result["agent_trace"] = json.loads(trace_path.read_text(encoding="utf-8"))
    return result


def run_agent_revision_pipeline(
    parent_run_dir: str | Path,
    revision_prompt: str,
    adapter: AgentAdapter,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run a CadFlow-native parent-run revision through CAD IR patching."""

    parent_path = _require_repo_path(Path(parent_run_dir).resolve())
    parent_ir_path = parent_path / "input_ir.json"
    if not parent_ir_path.exists():
        raise FileNotFoundError(f"parent run is missing input_ir.json: {parent_ir_path}")
    parent_ir = json.loads(parent_ir_path.read_text(encoding="utf-8"))
    parent_report = _read_json_if_present(parent_path / "report.json")
    parent_trace = _read_json_if_present(parent_path / "agent_trace.json")
    parent_lineage = _read_json_if_present(parent_path / "lineage.json")
    root_run_id = parent_lineage.get("root_run_id") or parent_path.name
    revision_index = int(parent_lineage.get("revision_index", 0)) + 1

    output_path = _resolve_output_dir(f"{parent_path.name}_revision_{revision_index}", None, output_dir)
    if output_path == parent_path:
        raise ValueError("revision child output_dir must not overwrite the parent run")
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "parent_run_id.txt").write_text(parent_path.name + "\n", encoding="utf-8")
    (output_path / "revision_prompt.txt").write_text(revision_prompt.strip() + "\n", encoding="utf-8")
    _write_json(output_path / "parent_input_ir.json", parent_ir)
    if parent_report:
        _write_json(output_path / "parent_report_snapshot.json", parent_report)
    if parent_trace:
        _write_json(output_path / "parent_agent_trace_snapshot.json", parent_trace)
    revision_request = {
        "artifact_type": "revision_request",
        "version": "revision-request-v0.1",
        "prompt": revision_prompt,
        "prompt_artifact": "revision_prompt.txt",
        "root_run_id": root_run_id,
        "parent_run_id": parent_path.name,
        "parent_run_dir": _repo_relative_string(parent_path),
        "child_run_id": output_path.name,
        "revision_index": revision_index,
        "parent_artifacts": {
            "input_ir": _repo_relative_string(parent_ir_path),
            "report": _repo_relative_string(parent_path / "report.json") if (parent_path / "report.json").exists() else None,
            "agent_trace": _repo_relative_string(parent_path / "agent_trace.json")
            if (parent_path / "agent_trace.json").exists()
            else None,
        },
        "child_parent_snapshots": {
            "input_ir": "parent_input_ir.json",
            "report": "parent_report_snapshot.json" if parent_report else None,
            "agent_trace": "parent_agent_trace_snapshot.json" if parent_trace else None,
        },
    }
    _write_json(output_path / "revision_request.json", revision_request)

    model_context = {
        "parent_run_id": parent_path.name,
        "parent_run_dir": str(parent_path),
        "input_ir": parent_ir,
        "report": parent_report,
        "agent_trace": parent_trace,
    }
    context = {
        "workflow_stage": "agent_revision",
        "target_contract": "cadflow_native_revision_v0.6",
        "output_dir": str(output_path),
        "root_run_id": root_run_id,
        "revision_index": revision_index,
    }
    change_intent = adapter.parse_revision_request(revision_prompt, model_context, context=context)
    _write_json(output_path / "change_intent.json", change_intent)

    revision_plan = adapter.create_revision_plan(change_intent, model_context, context=context)
    _write_json(output_path / "revision_plan.json", revision_plan)

    patch = _build_cad_ir_patch(parent_ir, revision_plan)
    _write_json(output_path / "patch.json", patch)
    if revision_plan.get("status") != "ready_for_patch" or not patch.get("changes"):
        return _write_blocked_revision_result(
            output_path=output_path,
            parent_path=parent_path,
            parent_ir=parent_ir,
            parent_report=parent_report,
            parent_trace=parent_trace,
            revision_request=revision_request,
            change_intent=change_intent,
            revision_plan=revision_plan,
            patch=patch,
            revision_prompt=revision_prompt,
            adapter=adapter,
            root_run_id=root_run_id,
            revision_index=revision_index,
        )

    child_ir = _apply_cad_ir_patch(parent_ir, patch)
    validate_input_ir_draft(child_ir)
    _write_json(output_path / "input_ir.json", child_ir)

    result = run_ir_pipeline(child_ir, output_dir=output_path)
    child_report = _read_json_if_present(output_path / "report.json")
    child_trace = _read_json_if_present(output_path / "agent_trace.json")
    comparison = _compare_revision(
        parent_ir,
        child_ir,
        parent_report,
        child_report,
        parent_trace,
        child_trace,
        parent_path,
        output_path,
        patch,
    )
    _write_json(output_path / "comparison.json", comparison)
    lineage = {
        "artifact_type": "lineage",
        "version": "lineage-v0.1",
        "relationship": "revision_child",
        "root_run_id": root_run_id,
        "parent_run_id": parent_path.name,
        "parent_run_dir": _repo_relative_string(parent_path),
        "child_run_id": output_path.name,
        "child_run_dir": _repo_relative_string(output_path),
        "revision_index": revision_index,
        "revision_prompt": revision_prompt,
        "revision_request_artifact": "revision_request.json",
        "patch_artifact": "patch.json",
        "comparison_artifact": "comparison.json",
    }
    _write_json(output_path / "lineage.json", lineage)
    _write_revision_report(output_path, revision_request, comparison, lineage)
    _merge_agent_revision_metadata(output_path, {
        "workflow": "agent_revision",
        "version": "cadflow-native-revision-v0.6",
        "adapter": _safe_provider_identity(adapter),
        "root_run_id": root_run_id,
        "parent_run_id": parent_path.name,
        "child_run_id": output_path.name,
        "revision_index": revision_index,
        "stages": [
            "parent_run",
            "parse_revision_request",
            "create_revision_plan",
            "patch_input_ir",
            "run_ir_pipeline",
            "compare_parent_child",
            "record_lineage",
        ],
        "artifacts": {
            "revision_prompt": "revision_prompt.txt",
            "revision_request": "revision_request.json",
            "change_intent": "change_intent.json",
            "revision_plan": "revision_plan.json",
            "patch": "patch.json",
            "child_input_ir": "input_ir.json",
            "comparison": "comparison.json",
            "lineage": "lineage.json",
            "revision_report": "revision_report.md",
            "parent_input_ir_snapshot": "parent_input_ir.json",
        },
    })
    files = _collect_files(output_path)
    result.update({
        "revision_request": revision_request,
        "change_intent": change_intent,
        "revision_plan": revision_plan,
        "patch": patch,
        "comparison": comparison,
        "lineage": lineage,
        "input_ir": child_ir,
        "files": files,
    })
    trace_path = output_path / "agent_trace.json"
    if trace_path.exists():
        result["agent_trace"] = json.loads(trace_path.read_text(encoding="utf-8"))
    return result


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
        "revision_prompt.txt": "revision_prompt",
        "intent.json": "intent",
        "design_brief.json": "design_brief",
        "candidate_plans.json": "candidate_plans",
        "selected_plan.json": "selected_plan",
        "revision_request.json": "revision_request",
        "change_intent.json": "change_intent",
        "revision_plan.json": "revision_plan",
        "patch.json": "patch",
        "comparison.json": "comparison",
        "revision_report.md": "revision_report",
        "lineage.json": "lineage",
        "parent_input_ir.json": "parent_input_ir",
        "parent_report_snapshot.json": "parent_report_snapshot",
        "parent_agent_trace_snapshot.json": "parent_agent_trace_snapshot",
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


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_blocked_revision_result(
    *,
    output_path: Path,
    parent_path: Path,
    parent_ir: dict[str, Any],
    parent_report: dict[str, Any],
    parent_trace: dict[str, Any],
    revision_request: dict[str, Any],
    change_intent: dict[str, Any],
    revision_plan: dict[str, Any],
    patch: dict[str, Any],
    revision_prompt: str,
    adapter: AgentAdapter,
    root_run_id: str,
    revision_index: int,
) -> dict[str, Any]:
    comparison = _compare_blocked_revision(
        parent_ir,
        parent_report,
        parent_trace,
        parent_path,
        output_path,
        patch,
        revision_plan,
    )
    _write_json(output_path / "comparison.json", comparison)
    lineage = {
        "artifact_type": "lineage",
        "version": "lineage-v0.1",
        "relationship": "revision_blocked",
        "root_run_id": root_run_id,
        "parent_run_id": parent_path.name,
        "parent_run_dir": _repo_relative_string(parent_path),
        "child_run_id": output_path.name,
        "child_run_dir": _repo_relative_string(output_path),
        "revision_index": revision_index,
        "revision_prompt": revision_prompt,
        "revision_request_artifact": "revision_request.json",
        "patch_artifact": "patch.json",
        "comparison_artifact": "comparison.json",
        "blocked_reason": comparison["blocked_reason"],
    }
    _write_json(output_path / "lineage.json", lineage)
    _write_revision_report(output_path, revision_request, comparison, lineage)

    revision_metadata = {
        "workflow": "agent_revision",
        "version": "cadflow-native-revision-v0.6",
        "adapter": _safe_provider_identity(adapter),
        "root_run_id": root_run_id,
        "parent_run_id": parent_path.name,
        "child_run_id": output_path.name,
        "revision_index": revision_index,
        "status": "blocked",
        "blocked_reason": comparison["blocked_reason"],
        "stages": [
            "parent_run",
            "parse_revision_request",
            "create_revision_plan",
            "patch_input_ir",
            "block_no_structured_changes",
            "compare_parent_child",
            "record_lineage",
        ],
        "artifacts": {
            "revision_prompt": "revision_prompt.txt",
            "revision_request": "revision_request.json",
            "change_intent": "change_intent.json",
            "revision_plan": "revision_plan.json",
            "patch": "patch.json",
            "comparison": "comparison.json",
            "lineage": "lineage.json",
            "revision_report": "revision_report.md",
            "parent_input_ir_snapshot": "parent_input_ir.json",
        },
    }
    files = _collect_files(output_path)
    report = {
        "success": False,
        "status": "blocked",
        "blocked_reason": comparison["blocked_reason"],
        "part_type": parent_ir.get("part_type"),
        "part_name": parent_ir.get("part_name", parent_ir.get("part_type")),
        "revision_request": revision_request,
        "change_intent": change_intent,
        "revision_plan": revision_plan,
        "patch": patch,
        "comparison": comparison,
        "lineage": lineage,
        "agent_revision": revision_metadata,
        "files": files,
    }
    _write_json(output_path / "report.json", report)
    _write_blocked_revision_report_md(output_path, report)
    _merge_agent_revision_metadata(output_path, revision_metadata)
    files = _collect_files(output_path)
    report["files"] = files
    _write_json(output_path / "report.json", report)
    return {
        "status": "blocked",
        "success": False,
        "output_dir": str(output_path),
        "blocked_reason": comparison["blocked_reason"],
        "revision_request": revision_request,
        "change_intent": change_intent,
        "revision_plan": revision_plan,
        "patch": patch,
        "comparison": comparison,
        "lineage": lineage,
        "files": files,
        "agent_trace": json.loads((output_path / "agent_trace.json").read_text(encoding="utf-8")),
    }


def _compare_blocked_revision(
    parent_ir: dict[str, Any],
    parent_report: dict[str, Any],
    parent_trace: dict[str, Any],
    parent_path: Path,
    child_path: Path,
    patch: dict[str, Any],
    revision_plan: dict[str, Any],
) -> dict[str, Any]:
    blocked_reason = _revision_blocked_reason(revision_plan, patch)
    return {
        "artifact_type": "revision_comparison",
        "version": "revision-comparison-v0.1",
        "status": "blocked",
        "blocked_reason": blocked_reason,
        "parent_run_id": parent_path.name,
        "child_run_id": child_path.name,
        "parent_artifacts": {
            "input_ir": _repo_relative_string(parent_path / "input_ir.json"),
            "report": _repo_relative_string(parent_path / "report.json") if parent_report else None,
        },
        "child_artifacts": {
            "report": "report.json",
            "revision_report": "revision_report.md",
        },
        "requested_changes": [
            {
                "path": change.get("path"),
                "op": change.get("op"),
                "before": change.get("before"),
                "after": change.get("after"),
                "reason": change.get("reason"),
            }
            for change in patch.get("changes", [])
        ],
        "actual_ir_changes": [],
        "validation_changes": [],
        "system_repair_changes": [],
        "summary": {
            "requested_change_count": len(patch.get("changes", [])),
            "actual_ir_change_count": 0,
            "validation_change_count": 0,
            "system_repair_change_count": 0,
        },
        "dimension_changes": [],
        "feature_changes": [],
        "status_detail": {
            "parent": parent_report.get("status") if parent_report else None,
            "child": "blocked",
            "child_success": False,
            "parent_attempts": parent_trace.get("total_attempts") if parent_trace else None,
            "child_attempts": 0,
        },
    }


def _revision_blocked_reason(revision_plan: dict[str, Any], patch: dict[str, Any]) -> str:
    if revision_plan.get("status") != "ready_for_patch":
        return f"revision_plan.status={revision_plan.get('status', 'unknown')}"
    return "patch.changes is empty"


def _write_revision_report(
    output_path: Path,
    revision_request: dict[str, Any],
    comparison: dict[str, Any],
    lineage: dict[str, Any],
) -> None:
    requested = comparison.get("requested_changes", [])
    actual = comparison.get("actual_ir_changes", [])
    validation = comparison.get("validation_changes", [])
    repairs = comparison.get("system_repair_changes", [])
    status_value = comparison.get("status")
    if isinstance(status_value, dict):
        status = status_value.get("child") or "success"
    else:
        status = status_value or comparison.get("status_detail", {}).get("child") or "success"
    lines = [
        "# Revision Report",
        "",
        f"- Parent run: `{lineage.get('parent_run_id')}`",
        f"- Child run: `{lineage.get('child_run_id')}`",
        f"- Revision index: {lineage.get('revision_index')}",
        f"- Status: `{status}`",
        f"- Requested prompt: {revision_request.get('prompt', '').strip()}",
        f"- Requested structured changes: {len(requested)}",
        f"- Actual IR changes: {len(actual)}",
        f"- Validation changes: {len(validation)}",
        f"- System repair changes: {len(repairs)}",
    ]
    if comparison.get("blocked_reason"):
        lines.append(f"- Blocked reason: `{comparison['blocked_reason']}`")
    if requested:
        lines.extend(["", "## Requested Changes", ""])
        for change in requested:
            lines.append(
                f"- `{change.get('op')}` `{change.get('path')}`: "
                f"`{change.get('before')}` -> `{change.get('after')}`"
            )
    if actual:
        lines.extend(["", "## Actual IR Changes", ""])
        for change in actual:
            lines.append(f"- `{change.get('path')}`: `{change.get('before')}` -> `{change.get('after')}`")
    if validation:
        lines.extend(["", "## Validation Changes", ""])
        for change in validation:
            lines.append(f"- `{change.get('path')}`: `{change.get('before')}` -> `{change.get('after')}`")
    if repairs:
        lines.extend(["", "## System Repair Changes", ""])
        for change in repairs:
            lines.append(f"- {change}")
    (output_path / "revision_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_blocked_revision_report_md(output_path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Blocked Revision Report",
        "",
        "**Status:** blocked",
        f"**Part type:** {report.get('part_type')}",
        f"**Part name:** {report.get('part_name')}",
        f"**Blocked reason:** `{report.get('blocked_reason')}`",
        "",
        "No child CAD model was generated because the revision request produced no structured CAD IR changes.",
        "",
        "## Files",
        "",
    ]
    for label, path in report.get("files", {}).items():
        lines.append(f"- {label}: `{path}`")
    (output_path / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _agent_create_dir_name(prompt: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", prompt.lower()).strip("_")
    return f"agent_create_{slug[:48] or 'prompt'}"


def _select_candidate_plan(candidate_plans: list[dict[str, Any]], selected_candidate: str | None) -> dict[str, Any]:
    if selected_candidate:
        for plan in candidate_plans:
            candidate_id = str(plan.get("candidate_id", ""))
            label = str(plan.get("label", ""))
            if selected_candidate in {candidate_id, label}:
                return plan
        raise ValueError(f"selected candidate not found: {selected_candidate}")
    for plan in candidate_plans:
        if plan.get("selected_by_default"):
            return plan
    return candidate_plans[0]


def _build_cad_ir_patch(parent_ir: dict[str, Any], revision_plan: dict[str, Any]) -> dict[str, Any]:
    operations = []
    for operation in revision_plan.get("planned_operations", []):
        dotted_path = operation.get("path")
        op = operation.get("op", "replace")
        if not dotted_path or op not in {"replace", "remove"}:
            continue
        operations.append({
            "op": op,
            "path": dotted_path,
            "before": _get_dotted_path(parent_ir, dotted_path),
            "after": None if op == "remove" else operation.get("after"),
            "reason": operation.get("reason", "revision plan operation"),
        })
    return {
        "artifact_type": "cad_ir_patch",
        "version": "cad-ir-patch-v0.1",
        "target_artifact": "input_ir.json",
        "changes": operations,
    }


def _apply_cad_ir_patch(parent_ir: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    child_ir = json.loads(json.dumps(parent_ir))
    part_name = child_ir.get("part_name") or child_ir.get("part_type", "part")
    child_ir["part_name"] = f"{part_name}_revision"
    source = dict(child_ir.get("source", {}))
    source["revision"] = {
        "patch_version": patch.get("version"),
        "change_count": len(patch.get("changes", [])),
    }
    child_ir["source"] = source
    for change in patch.get("changes", []):
        if change.get("op") == "remove":
            _remove_dotted_path(child_ir, change["path"])
        else:
            _set_dotted_path(child_ir, change["path"], change.get("after"))
    return child_ir


def _compare_revision(
    parent_ir: dict[str, Any],
    child_ir: dict[str, Any],
    parent_report: dict[str, Any],
    child_report: dict[str, Any],
    parent_trace: dict[str, Any],
    child_trace: dict[str, Any],
    parent_path: Path,
    child_path: Path,
    patch: dict[str, Any],
) -> dict[str, Any]:
    actual_ir_changes = _diff_values(parent_ir, child_ir)
    validation_changes = _validation_changes(parent_report, child_report)
    system_repair_changes = _system_repair_changes(child_trace)
    return {
        "artifact_type": "revision_comparison",
        "version": "revision-comparison-v0.1",
        "parent_run_id": parent_path.name,
        "child_run_id": child_path.name,
        "parent_artifacts": {
            "input_ir": _repo_relative_string(parent_path / "input_ir.json"),
            "report": _repo_relative_string(parent_path / "report.json") if parent_report else None,
        },
        "child_artifacts": {
            "input_ir": _repo_relative_string(child_path / "input_ir.json"),
            "report": _repo_relative_string(child_path / "report.json") if child_report else None,
        },
        "requested_changes": [
            {
                "path": change.get("path"),
                "op": change.get("op"),
                "before": change.get("before"),
                "after": change.get("after"),
                "reason": change.get("reason"),
            }
            for change in patch.get("changes", [])
        ],
        "actual_ir_changes": actual_ir_changes,
        "validation_changes": validation_changes,
        "system_repair_changes": system_repair_changes,
        "summary": {
            "requested_change_count": len(patch.get("changes", [])),
            "actual_ir_change_count": len(actual_ir_changes),
            "validation_change_count": len(validation_changes),
            "system_repair_change_count": len(system_repair_changes),
        },
        "dimension_changes": _diff_dict(parent_ir.get("dimensions", {}), child_ir.get("dimensions", {}), "dimensions"),
        "feature_changes": _diff_dict(parent_ir.get("features", {}), child_ir.get("features", {}), "features"),
        "status": {
            "parent": parent_report.get("status") if parent_report else None,
            "child": child_report.get("status") if child_report else None,
            "child_success": child_report.get("success") if child_report else None,
            "parent_attempts": parent_trace.get("total_attempts") if parent_trace else None,
            "child_attempts": child_trace.get("total_attempts") if child_trace else None,
        },
    }


def _diff_values(before: Any, after: Any, prefix: str = "") -> list[dict[str, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(set(before) | set(after)):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            if key not in before:
                changes.append({"path": child_prefix, "before": None, "after": after[key]})
            elif key not in after:
                changes.append({"path": child_prefix, "before": before[key], "after": None})
            else:
                changes.extend(_diff_values(before[key], after[key], child_prefix))
        return changes
    if before != after:
        return [{"path": prefix, "before": before, "after": after}]
    return []


def _validation_changes(parent_report: dict[str, Any], child_report: dict[str, Any]) -> list[dict[str, Any]]:
    fields = (
        "status",
        "success",
        "ir_valid",
        "execution_success",
        "step_generated",
        "stl_generated",
        "bounding_box",
        "volume",
        "warnings",
        "errors",
        "measured_validation_targets",
    )
    changes = []
    for field in fields:
        before = parent_report.get(field)
        after = child_report.get(field)
        if before != after:
            changes.append({"path": field, "before": before, "after": after})
    return changes


def _system_repair_changes(child_trace: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for step in child_trace.get("steps", []):
        repair = step.get("repair") or step.get("repair_suggestion") or step.get("applied_repair")
        if repair:
            changes.append({
                "attempt": step.get("attempt"),
                "status": step.get("status"),
                "repair": repair,
            })
    final_ir = child_trace.get("final_ir")
    if final_ir:
        changes.append({"path": "final_ir", "after": final_ir})
    return changes


def _diff_dict(before: dict[str, Any], after: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    changes = []
    keys = sorted(set(before) | set(after))
    for key in keys:
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value != after_value:
            changes.append({
                "path": f"{prefix}.{key}",
                "before": before_value,
                "after": after_value,
            })
    return changes


def _get_dotted_path(data: dict[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_dotted_path(data: dict[str, Any], dotted_path: str, value: Any) -> None:
    current = data
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise ValueError(f"cannot patch through non-object field: {part}")
        current = child
    current[parts[-1]] = value


def _remove_dotted_path(data: dict[str, Any], dotted_path: str) -> None:
    current: Any = data
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def _read_json_if_present(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_provider_identity(adapter: AgentAdapter) -> dict[str, Any]:
    identity = getattr(adapter, "provider_identity", {})
    if not isinstance(identity, dict):
        return {}
    blocked_tokens = ("key", "secret", "token", "password", "prompt", "transcript", "path", "env")
    safe: dict[str, Any] = {}
    for key, value in identity.items():
        if any(token in str(key).lower() for token in blocked_tokens):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    return safe


def _provider_stage_trace(
    adapter: AgentAdapter,
    operation: str,
    *,
    validation_status: str,
    error_category: str | None = None,
) -> dict[str, Any]:
    trace = getattr(adapter, "last_provider_request_trace", None)
    if isinstance(trace, dict):
        safe_trace = json.loads(json.dumps(trace))
    else:
        safe_trace = {
            "operation": operation,
            "stage": "requirement" if operation == "parse_requirement" else "planning",
            "provider_identity": _safe_provider_identity(adapter),
            "message_count": 0,
            "context_shape": {},
            "knowledge_ids": [],
            "payload_shape": {},
        }
    safe_trace["validation_status"] = validation_status
    if error_category:
        safe_trace["error_category"] = error_category
    return safe_trace


def _provider_create_metadata(
    *,
    adapter: AgentAdapter,
    provider_traces: list[dict[str, Any]],
    status: str,
    provider_contract_mode: str,
    requirement_status: str,
    planning_status: str,
    ir_validation_status: str,
    pipeline_status: str,
    error_category: str | None = None,
    blocked_stage: str | None = None,
) -> dict[str, Any]:
    metadata = {
        "workflow": "provider_create",
        "version": "provider-requirement-planning-create-v0.1",
        "provider_contract_mode": provider_contract_mode,
        "workflow_mode": "normalized_provider_create"
        if provider_contract_mode == "extract_then_compile"
        else "provider_contract_compliance",
        "status": status,
        "adapter": _safe_provider_identity(adapter),
        "stages": [
            "prompt",
            "parse_requirement",
            "create_plan",
            "planning_to_cad_ir",
            "run_ir_pipeline",
        ],
        "artifacts": {
            "prompt": "prompt.txt",
            "requirement": "requirement.json",
            "planning_artifact": "planning_artifact.json",
            "input_ir": "input_ir.json",
        },
        "requirement_status": requirement_status,
        "planning_status": planning_status,
        "ir_validation_status": ir_validation_status,
        "pipeline_status": pipeline_status,
        "provider_request_traces": provider_traces,
    }
    if error_category:
        metadata["error_category"] = error_category
    if blocked_stage:
        metadata["blocked_stage"] = blocked_stage
    return metadata


def _merge_provider_create_metadata(output_dir: Path, metadata: dict[str, Any]) -> None:
    trace_path = output_dir / "agent_trace.json"
    if trace_path.exists():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    else:
        trace = {}
    trace["provider_create"] = metadata
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    report_path = output_dir / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["provider_create"] = metadata
        report["files"] = _collect_files(output_dir)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    report_md_path = output_dir / "report.md"
    if report_md_path.exists():
        report_md = report_md_path.read_text(encoding="utf-8")
        report_md += (
            "\n## Provider Create Workflow\n\n"
            f"- Requirement status: `{metadata.get('requirement_status')}`\n"
            f"- Planning status: `{metadata.get('planning_status')}`\n"
            f"- IR validation status: `{metadata.get('ir_validation_status')}`\n"
            f"- Pipeline status: `{metadata.get('pipeline_status')}`\n"
        )
        report_md_path.write_text(report_md, encoding="utf-8")


def _write_blocked_provider_create_result(
    *,
    output_path: Path,
    status: str,
    blocked_stage: str,
    adapter: AgentAdapter,
    provider_traces: list[dict[str, Any]],
    error_category: str,
    provider_contract_mode: str,
    requirement: dict[str, Any] | None = None,
    planning_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requirement_status = "passed" if requirement is not None else "not_run"
    planning_status = "passed" if planning_artifact is not None else "not_run"
    if blocked_stage == "requirement":
        requirement_status = "failed"
    elif blocked_stage == "planning":
        planning_status = "failed"
    metadata = _provider_create_metadata(
        adapter=adapter,
        provider_traces=provider_traces,
        status=status,
        provider_contract_mode=provider_contract_mode,
        requirement_status=requirement_status,
        planning_status=planning_status,
        ir_validation_status="not_run" if blocked_stage != "cad_ir" else "failed",
        pipeline_status="not_run",
        error_category=error_category,
        blocked_stage=blocked_stage,
    )
    trace = {
        "total_attempts": 0,
        "steps": [{
            "attempt": 0,
            "status": "blocked",
            "stage": blocked_stage,
            "error_category": error_category,
        }],
        "final_selected_candidate": None,
        "provider_create": metadata,
    }
    _write_json(output_path / "agent_trace.json", trace)
    report = {
        "success": False,
        "status": status,
        "blocked_stage": blocked_stage,
        "error_category": error_category,
        "cad_ir_created": (output_path / "input_ir.json").exists(),
        "part_modeling_started": False,
        "provider_create": metadata,
        "files": _collect_files(output_path),
    }
    if requirement is not None:
        report["requirement_status"] = requirement.get("requirement_status", {})
        report["part_type"] = requirement.get("part_type")
        report["part_name"] = requirement.get("instance_name") or requirement.get("part_name") or requirement.get("part_type")
    if planning_artifact is not None:
        report["planning_gate_status"] = planning_artifact.get("flow_gate_status")
    _write_json(output_path / "report.json", report)
    _write_blocked_provider_create_report_md(output_path, report)
    files = _collect_files(output_path)
    report["files"] = files
    _write_json(output_path / "report.json", report)
    _write_provider_create_runtime(output_path, metadata, status=status)
    return {
        "status": status,
        "success": False,
        "blocked_stage": blocked_stage,
        "error_category": error_category,
        "output_dir": str(output_path),
        "requirement": requirement,
        "planning_artifact": planning_artifact,
        "provider_create": metadata,
        "agent_trace": trace,
        "files": files,
        "report_json": str(output_path / "report.json"),
        "report_md": str(output_path / "report.md"),
    }


def _write_blocked_provider_create_report_md(output_path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Provider Create Report",
        "",
        f"**Status:** {report.get('status')}",
        f"**Blocked stage:** {report.get('blocked_stage')}",
        f"**Error category:** `{report.get('error_category')}`",
        "",
        "Provider-backed create stopped before CAD execution.",
    ]
    (output_path / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_provider_create_runtime(output_dir: Path, metadata: dict[str, Any], *, status: str) -> None:
    runtime_path = output_dir / "logs" / "runtime.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime = _read_json_if_present(runtime_path)
    runtime["provider_create"] = metadata
    runtime["workflow_console"] = {
        "latest_stage": {
            "stage": "provider_create",
            "status": status,
            "adapter_activity": {
                "operation": "provider_create",
                "provider_identity": metadata.get("adapter", {}),
                "request_trace_summaries": metadata.get("provider_request_traces", []),
            },
        },
        "stage_count": 1,
    }
    _write_json(runtime_path, runtime)


def _merge_agent_create_metadata(output_dir: Path, planning_metadata: dict[str, Any]) -> None:
    trace_path = output_dir / "agent_trace.json"
    if trace_path.exists():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    else:
        trace = {}
    trace["agent_create"] = planning_metadata
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    report_path = output_dir / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["agent_create"] = planning_metadata
        report["files"] = _collect_files(output_dir)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    report_md_path = output_dir / "report.md"
    if report_md_path.exists():
        report_md = report_md_path.read_text(encoding="utf-8")
        report_md += (
            "\n## Agent Create Workflow\n\n"
            f"- Selected candidate: `{planning_metadata.get('selected_candidate')}`\n"
            f"- Candidate count: {planning_metadata.get('candidate_count')}\n"
            "- Planning artifacts: `intent.json`, `design_brief.json`, "
            "`candidate_plans.json`, `selected_plan.json`\n"
        )
        report_md_path.write_text(report_md, encoding="utf-8")


def _merge_agent_revision_metadata(output_dir: Path, revision_metadata: dict[str, Any]) -> None:
    trace_path = output_dir / "agent_trace.json"
    if trace_path.exists():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    else:
        trace = {}
    trace["agent_revision"] = revision_metadata
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    report_path = output_dir / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["agent_revision"] = revision_metadata
        report["files"] = _collect_files(output_dir)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    report_md_path = output_dir / "report.md"
    if report_md_path.exists():
        report_md = report_md_path.read_text(encoding="utf-8")
        report_md += (
            "\n## Agent Revision Workflow\n\n"
            f"- Parent run: `{revision_metadata.get('parent_run_id')}`\n"
            f"- Child run: `{revision_metadata.get('child_run_id')}`\n"
            "- Revision artifacts: `change_intent.json`, `revision_plan.json`, "
            "`patch.json`, `comparison.json`, `lineage.json`\n"
        )
        report_md_path.write_text(report_md, encoding="utf-8")


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


def _repo_relative_string(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


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
