"""IR-first CAD pipeline runner."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ai_native_cad.agents.base import AgentAdapter
from ai_native_cad.agents.json_contract import JsonContractProviderError, ProviderRequirementCompilerError
from ai_native_cad.agents.validation import validate_adapter_result, validate_input_ir_draft
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
    except ProviderRequirementCompilerError as exc:
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
            diagnostic_codes=exc.diagnostic_codes,
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
            diagnostic_codes=_requirement_diagnostic_codes(requirement),
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


def run_provider_normalized_design_create_pipeline(
    prompt: str,
    adapter: AgentAdapter,
    output_dir: str | Path | None = None,
    output_root: str | Path | None = None,
    selected_candidate: str | None = None,
) -> dict[str, Any]:
    """Run provider-backed normalized design planning into deterministic CAD.

    The provider extracts requirement-level design signals only. CadFlow locally
    compiles intent, design brief, candidate plans, selected plan, requirement,
    planning artifact, CAD IR, and CAD execution artifacts.
    """

    provider_contract_mode = "extract_then_compile"
    output_path = _resolve_output_dir(_agent_create_dir_name(prompt), output_root, output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "prompt.txt").write_text(prompt.strip() + "\n", encoding="utf-8")
    context = {
        "workflow_stage": "provider_normalized_design_create",
        "target_contract": "provider_normalized_design_create_v0.1",
        "provider_contract_mode": provider_contract_mode,
        "output_dir": str(output_path),
    }
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
    except ProviderRequirementCompilerError as exc:
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
            diagnostic_codes=exc.diagnostic_codes,
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
    provider_traces.append(_provider_stage_trace(adapter, "parse_requirement", validation_status="passed"))
    requirement_decision = requirement.get("requirement_status", {}).get("flow_decision", {})
    if not is_proceed_action(requirement_decision.get("action")):
        if _requirement_requires_assembly_planning(requirement):
            intent = _compile_normalized_design_intent(prompt, requirement)
            validate_adapter_result("interpret_user_intent", intent)
            _write_json(output_path / "intent.json", intent)

            design_brief = _compile_normalized_design_brief(intent, requirement)
            validate_adapter_result("propose_design_brief", design_brief)
            _write_json(output_path / "design_brief.json", design_brief)

            candidate_plans = _compile_normalized_candidate_plans(design_brief, requirement)
            if not candidate_plans:
                raise ValueError("normalized design compiler must produce candidate plans")
            _write_json(output_path / "candidate_plans.json", candidate_plans)

            selected_plan = _select_candidate_plan(candidate_plans, selected_candidate)
            _write_json(output_path / "selected_plan.json", selected_plan)

            assembly_plan = _compile_assembly_plan(prompt, requirement, design_brief, selected_plan)
            _write_json(output_path / "assembly_plan.json", assembly_plan)
            return _write_blocked_normalized_design_assembly_result(
                output_path=output_path,
                adapter=adapter,
                provider_traces=provider_traces,
                requirement=requirement,
                intent=intent,
                design_brief=design_brief,
                candidate_plans=candidate_plans,
                selected_plan=selected_plan,
                assembly_plan=assembly_plan,
            )
        return _write_blocked_provider_create_result(
            output_path=output_path,
            status="blocked_provider_requirement",
            blocked_stage="requirement",
            adapter=adapter,
            provider_traces=provider_traces,
            requirement=requirement,
            error_category="requirement_gate_blocked",
            provider_contract_mode=provider_contract_mode,
            diagnostic_codes=_requirement_diagnostic_codes(requirement),
        )

    intent = _compile_normalized_design_intent(prompt, requirement)
    validate_adapter_result("interpret_user_intent", intent)
    _write_json(output_path / "intent.json", intent)

    design_brief = _compile_normalized_design_brief(intent, requirement)
    validate_adapter_result("propose_design_brief", design_brief)
    _write_json(output_path / "design_brief.json", design_brief)

    candidate_plans = _compile_normalized_candidate_plans(design_brief, requirement)
    if not candidate_plans:
        raise ValueError("normalized design compiler must produce candidate plans")
    _write_json(output_path / "candidate_plans.json", candidate_plans)

    selected_plan = _select_candidate_plan(candidate_plans, selected_candidate)
    _write_json(output_path / "selected_plan.json", selected_plan)

    try:
        planning_artifact = create_planning_artifact(requirement)
        validate_adapter_result("create_plan", planning_artifact)
    except Exception:
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
    metadata = _provider_normalized_design_create_metadata(
        adapter=adapter,
        provider_traces=provider_traces,
        status=result.get("status", "unknown"),
        selected_candidate=selected_plan.get("candidate_id") or selected_plan.get("label"),
        candidate_count=len(candidate_plans),
    )
    _merge_provider_normalized_design_create_metadata(output_path, metadata)
    files = _collect_files(output_path)
    result.update({
        "intent": intent,
        "design_brief": design_brief,
        "candidate_plans": candidate_plans,
        "selected_plan": selected_plan,
        "requirement": requirement,
        "planning_artifact": planning_artifact,
        "input_ir": input_ir,
        "provider_normalized_design_create": metadata,
        "files": files,
    })
    trace_path = output_path / "agent_trace.json"
    if trace_path.exists():
        result["agent_trace"] = json.loads(trace_path.read_text(encoding="utf-8"))
    return result


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


def _collect_files(output_dir: Path, *, repo_relative: bool = False) -> dict[str, str]:
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
        "assembly_plan.json": "assembly_plan",
        "part_create_request.json": "part_create_request",
        "part_request_review.json": "part_request_review",
        "reviewed_part_handoff.json": "reviewed_part_handoff",
        "part_execution_request.json": "part_execution_request",
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
            files[label] = _repo_relative_string(path) if repo_relative else str(path)
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


def _compile_normalized_design_intent(prompt: str, requirement: dict[str, Any]) -> dict[str, Any]:
    intent = requirement.get("intent", {})
    return {
        "artifact_type": "intent",
        "version": "intent-v0.1",
        "prompt_summary": " ".join(prompt.strip().split())[:240],
        "object_goal": intent.get("object_goal", requirement.get("part_type")),
        "scope": intent.get("scope", "part"),
        "use_case": intent.get("use_case", "unspecified"),
        "recognized_part_type": requirement["part_type"],
        "unit": requirement.get("unit", "mm"),
        "requested_outputs": list(requirement.get("outputs", ["step", "stl"])),
        "interpreted_constraints": {
            "dimensions": json.loads(json.dumps(requirement.get("dimensions", {}))),
            "features": json.loads(json.dumps(requirement.get("features", {}))),
            "check_level": requirement.get("check_level", "L0"),
        },
        "assumptions": list(requirement.get("assumptions", [])),
        "open_questions": list(requirement.get("follow_up_questions", [])),
        "source": {
            "compiler": "cadflow_normalized_design_v0.1",
            "provider_role": "extraction_only",
            "requirement_artifact": "requirement.json",
        },
    }


def _compile_normalized_design_brief(intent: dict[str, Any], requirement: dict[str, Any]) -> dict[str, Any]:
    cad_brief = requirement.get("cad_brief", {})
    interpreted = intent.get("interpreted_constraints", {})
    return {
        "artifact_type": "design_brief",
        "version": "design-brief-v0.1",
        "part_type": requirement["part_type"],
        "design_goal": {
            "object_goal": intent.get("object_goal", requirement["part_type"]),
            "scope": intent.get("scope", "part"),
            "use_case": intent.get("use_case", "unspecified"),
        },
        "functional_requirements": _normalized_functional_requirements(requirement),
        "geometry_constraints": {
            "unit": requirement.get("unit", "mm"),
            "dimensions": json.loads(json.dumps(interpreted.get("dimensions", {}))),
            "features": json.loads(json.dumps(interpreted.get("features", {}))),
        },
        "validation_targets": json.loads(json.dumps(cad_brief.get("validation_targets", []))),
        "assumptions": list(requirement.get("assumptions", [])),
        "risk_notes": _normalized_design_risk_notes(requirement),
        "candidate_strategy": "generate template-backed local candidates and select deterministically",
        "source": {
            "compiler": "cadflow_normalized_design_v0.1",
            "intent_artifact": "intent.json",
            "requirement_artifact": "requirement.json",
        },
    }


def _compile_normalized_candidate_plans(
    design_brief: dict[str, Any],
    requirement: dict[str, Any],
) -> list[dict[str, Any]]:
    base_decisions = {
        "part_type": requirement["part_type"],
        "part_name": requirement.get("instance_name") or requirement.get("part_name") or requirement["part_type"],
        "unit": requirement.get("unit", "mm"),
        "dimensions": json.loads(json.dumps(requirement.get("dimensions", {}))),
        "features": json.loads(json.dumps(requirement.get("features", {}))),
        "outputs": list(requirement.get("outputs", ["step", "stl"])),
        "check_level": requirement.get("check_level", "L0"),
    }
    candidates = [
        {
            "candidate_id": "A",
            "label": "local_template_resolved",
            "summary": "Use the supported CadFlow template matching the normalized requirement.",
            "selected_by_default": True,
            "part_type": requirement["part_type"],
            "resolved_decisions": json.loads(json.dumps(base_decisions)),
            "design_rationale": [
                "Provider output is treated as extraction only.",
                "CadFlow local planning and CAD IR conversion remain execution authority.",
            ],
            "risk_notes": list(design_brief.get("risk_notes", [])),
            "tradeoffs": ["Template-backed topology is intentionally conservative for this MVP."],
            "source": {
                "compiler": "cadflow_normalized_design_v0.1",
                "design_brief_artifact": "design_brief.json",
            },
        }
    ]
    alternate = _alternate_normalized_candidate(base_decisions)
    if alternate:
        candidates.append(alternate)
    return candidates


def _alternate_normalized_candidate(base_decisions: dict[str, Any]) -> dict[str, Any] | None:
    part_type = base_decisions.get("part_type")
    if part_type not in {"mounting_plate", "spacer", "simple_bracket"}:
        return None
    resolved = json.loads(json.dumps(base_decisions))
    resolved["part_name"] = f"{resolved.get('part_name', part_type)}_alternate"
    risk_notes = ["Alternate candidate records a conservative local design option; it is not selected by default."]
    if part_type == "mounting_plate":
        features = resolved.setdefault("features", {})
        features.setdefault("chamfer", {"size": 0.5})
    elif part_type == "spacer":
        dimensions = resolved.setdefault("dimensions", {})
        if isinstance(dimensions.get("outer_diameter"), (int, float)):
            dimensions["outer_diameter"] = round(float(dimensions["outer_diameter"]) + 2.0, 3)
    return {
        "candidate_id": "B",
        "label": "local_conservative_alternate",
        "summary": "Keep the same part family and dimensions authority while recording a conservative option.",
        "selected_by_default": False,
        "part_type": part_type,
        "resolved_decisions": resolved,
        "design_rationale": [
            "Shows design-level alternatives without granting provider CAD IR authority.",
            "Selection remains deterministic and local.",
        ],
        "risk_notes": risk_notes,
        "tradeoffs": ["Not selected by default in the MVP."],
        "source": {
            "compiler": "cadflow_normalized_design_v0.1",
            "design_brief_artifact": "design_brief.json",
        },
    }


def _normalized_functional_requirements(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    requirements = [{
        "kind": "primary_shape",
        "part_type": requirement["part_type"],
        "reason": "normalized to a supported CadFlow part family",
    }]
    for name, value in sorted(requirement.get("features", {}).items()):
        requirements.append({
            "kind": "feature",
            "feature": name,
            "value": json.loads(json.dumps(value)),
            "reason": "compiled from normalized requirement features",
        })
    return requirements


def _normalized_design_risk_notes(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    notes = []
    for item in requirement.get("missing_information", []):
        if isinstance(item, dict):
            notes.append({
                "kind": "missing_information",
                "field": item.get("field"),
                "severity": item.get("severity", "unknown"),
            })
    for item in requirement.get("assumptions", []):
        if isinstance(item, str):
            notes.append({"kind": "assumption", "note": item})
    return notes


def _requirement_requires_assembly_planning(requirement: dict[str, Any]) -> bool:
    scope = requirement.get("intent", {}).get("scope")
    codes = set(_requirement_diagnostic_codes(requirement))
    return scope in {"multi_part", "assembly"} or bool(
        codes
        & {
            "compiler.multi_part_requires_assembly_planning",
            "compiler.assembly_requires_assembly_planning",
        }
    )


def _compile_assembly_plan(
    prompt: str,
    requirement: dict[str, Any],
    design_brief: dict[str, Any],
    selected_plan: dict[str, Any],
) -> dict[str, Any]:
    scope = requirement.get("intent", {}).get("scope")
    if scope not in {"multi_part", "assembly"}:
        scope = "multi_part"
    parts = _normalize_assembly_plan_parts(_assembly_plan_parts(prompt, requirement), prompt=prompt)
    interfaces = _normalize_assembly_plan_interfaces(_assembly_plan_interfaces(prompt, scope), parts)
    fasteners = _normalize_assembly_plan_fasteners(_assembly_plan_fasteners(prompt))
    blocked_reasons = [
        {
            "code": "assembly_generation_not_supported_yet",
            "message": "CadFlow can plan this assembly but cannot generate multi-part CAD yet.",
        }
    ]
    diagnostic_codes = _safe_diagnostic_codes(
        _requirement_diagnostic_codes(requirement)
        + [
            "assembly.plan_created",
            "assembly.generation_not_supported_yet",
            "scope.assembly_intent" if scope == "assembly" else "scope.multi_part_intent",
        ]
        + (["assembly.parts_detected"] if parts else [])
        + (["assembly.interfaces_detected"] if interfaces else [])
    )
    quality = _assembly_plan_quality(
        parts=parts,
        interfaces=interfaces,
        fasteners=fasteners,
        risk_notes=_assembly_plan_risk_notes(design_brief),
        blocked_reasons=blocked_reasons,
    )
    return {
        "artifact_type": "assembly_plan",
        "schema_version": "0.1",
        "scope": scope,
        "status": "blocked_before_part_generation",
        "parts": parts,
        "interfaces": interfaces,
        "fasteners": fasteners,
        "clearance_notes": _assembly_plan_clearance_notes(prompt, interfaces),
        "risk_notes": quality["risk_notes"],
        "blocked_reasons": blocked_reasons,
        "diagnostic_codes": diagnostic_codes,
        "quality": {key: value for key, value in quality.items() if key != "risk_notes"},
        "source": {
            "compiler": "cadflow_assembly_plan_v0.1",
            "provider_role": "extraction_only",
            "requirement_artifact": "requirement.json",
            "design_brief_artifact": "design_brief.json",
            "selected_plan_artifact": "selected_plan.json",
            "selected_candidate": selected_plan.get("candidate_id") or selected_plan.get("label"),
        },
    }


def _assembly_plan_parts(prompt: str, requirement: dict[str, Any]) -> list[dict[str, Any]]:
    lowered = prompt.lower()
    if "base and lid" in lowered or "two-part" in lowered or "two part" in lowered:
        names = [("base", "main enclosure component"), ("lid", "cover component")]
    elif "hinge" in lowered or "two leaves" in lowered:
        names = [("leaf_a", "hinge leaf"), ("leaf_b", "hinge leaf"), ("pin", "hinge pin")]
    elif "vertical support" in lowered and "clamp" in lowered:
        names = [("base", "support base"), ("vertical_support", "upright support"), ("clamp", "phone clamp")]
    else:
        part_type = requirement.get("part_type") if isinstance(requirement.get("part_type"), str) else "component"
        names = [(part_type, "assembly component")]
    return [
        {
            "part_id": part_id,
            "role": role,
            "generation_strategy": "future_part_pipeline",
        }
        for part_id, role in names
    ]


def _assembly_plan_interfaces(prompt: str, scope: str) -> list[dict[str, Any]]:
    lowered = prompt.lower()
    if "base and lid" in lowered or "two-part" in lowered or "two part" in lowered:
        return [{"from": "lid", "to": "base", "kind": "screw_fastened", "notes": "four corner screws"}]
    if "hinge" in lowered or "two leaves" in lowered:
        return [
            {"from": "leaf_a", "to": "pin", "kind": "pinned_joint", "notes": "rotating hinge interface"},
            {"from": "leaf_b", "to": "pin", "kind": "pinned_joint", "notes": "rotating hinge interface"},
        ]
    if "vertical support" in lowered and "clamp" in lowered:
        return [
            {"from": "vertical_support", "to": "base", "kind": "stacked", "notes": "upright attaches to base"},
            {"from": "clamp", "to": "vertical_support", "kind": "sliding_fit", "notes": "clamp position is not solved"},
        ]
    return [{"from": "component_a", "to": "component_b", "kind": "unknown", "notes": "relationship requires future assembly planning"}]


def _assembly_plan_fasteners(prompt: str) -> list[dict[str, Any]]:
    lowered = prompt.lower()
    fasteners: list[dict[str, Any]] = []
    if "screw" in lowered:
        fasteners.append({"kind": "screw", "quantity": 4 if "four" in lowered or "4" in lowered else None})
    if "pin" in lowered and "hinge" not in lowered:
        fasteners.append({"kind": "pin", "quantity": 1})
    return fasteners


def _assembly_plan_clearance_notes(prompt: str, interfaces: list[dict[str, Any]]) -> list[str]:
    lowered = prompt.lower()
    notes: list[str] = []
    if "clearance" in lowered or "fit" in lowered:
        notes.append("Clearance or fit requirements must be resolved before assembly CAD generation.")
    if any(interface.get("kind") == "pinned_joint" for interface in interfaces):
        notes.append("Pin joint clearance is recorded but not solved in this MVP.")
    if any(interface.get("kind") == "sliding_fit" for interface in interfaces):
        notes.append("Adjustable clamp range is recorded but not solved in this MVP.")
    return notes


def _assembly_plan_risk_notes(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    notes = [
        {
            "kind": "capability_boundary",
            "note": "Assembly plan is advisory planning only; CAD assembly generation is not implemented.",
        }
    ]
    for item in design_brief.get("risk_notes", []):
        if isinstance(item, dict):
            safe_item = {
                key: value
                for key, value in item.items()
                if isinstance(key, str)
                and key in {"kind", "field", "severity", "note"}
                and isinstance(value, (str, int, float, bool))
            }
            if safe_item:
                notes.append(safe_item)
    return notes


_ASSEMBLY_GENERATION_STRATEGIES = {"future_part_pipeline", "reference_only", "blocked"}
_ASSEMBLY_PART_STATUSES = {
    "planned_only",
    "candidate_for_single_part_generation",
    "reference_only",
    "blocked",
}
_ASSEMBLY_INTERFACE_KINDS = {"screw_fastened", "pinned_joint", "sliding_fit", "snap_fit", "stacked", "unknown"}
_ASSEMBLY_INTERFACE_KIND_ALIASES = {
    "pin_joint": "pinned_joint",
    "fixed_support": "stacked",
    "adjustable_contact": "sliding_fit",
    "assembly": "unknown",
    "multi_part": "unknown",
}


def _normalize_assembly_plan_parts(parts: list[dict[str, Any]], *, prompt: str = "") -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, part in enumerate(parts, start=1):
        if not isinstance(part, dict):
            continue
        part_id = _stable_unique_artifact_id(part.get("part_id") or part.get("name") or f"component_{index}", used_ids)
        role = _safe_short_text(part.get("role") or "assembly component", fallback="assembly component")
        classification = _classify_assembly_plan_part(part_id=part_id, role=role, prompt=prompt)
        normalized.append({
            "part_id": part_id,
            "role": role,
            "generation_strategy": classification["generation_strategy"],
            "part_status": classification["part_status"],
            "supported_candidate": classification["supported_candidate"],
            "part_brief": classification["part_brief"],
            "blocked_reasons": classification["blocked_reasons"],
        })
    if normalized:
        return normalized
    return [{
        "part_id": "component",
        "role": "assembly component",
        "generation_strategy": "future_part_pipeline",
        "part_status": "planned_only",
        "supported_candidate": False,
        "part_brief": "Assembly component recorded for future decomposition.",
        "blocked_reasons": [],
    }]


def _classify_assembly_plan_part(*, part_id: str, role: str, prompt: str) -> dict[str, Any]:
    text = f"{prompt} {part_id} {role}".lower()
    prompt_text = prompt.lower()
    part_text = f"{part_id} {role}".lower()
    if any(token in prompt_text for token in ("medical", "implant", "aerospace", "load-bearing", "load bearing", "production")):
        return _assembly_part_classification(
            generation_strategy="blocked",
            part_status="blocked",
            supported_candidate=False,
            part_brief=f"{role.capitalize()} is blocked for safety-critical or production-critical scope.",
            blocked_reasons=["safety_or_production_critical_scope"],
        )
    if any(token in part_text for token in ("gear", "tooth", "teeth", "gearbox")):
        return _assembly_part_classification(
            generation_strategy="blocked",
            part_status="blocked",
            supported_candidate=False,
            part_brief=f"{role.capitalize()} is unsupported by the current single-part pipeline.",
            blocked_reasons=["unsupported_part_family"],
        )
    if part_id in {"pin", "pins", "screw", "screws", "bolt", "bolts", "nut", "nuts", "washer", "washers", "fastener", "fasteners"} or any(
        token in part_text for token in ("hinge pin", "screw", "bolt", "fastener")
    ):
        return _assembly_part_classification(
            generation_strategy="reference_only",
            part_status="reference_only",
            supported_candidate=False,
            part_brief=f"{role.capitalize()} is recorded as reference hardware, not a primary generated CAD part.",
            blocked_reasons=[],
        )
    if any(token in text for token in ("base", "lid", "leaf", "plate", "bracket", "support", "clamp", "housing", "enclosure")):
        return _assembly_part_classification(
            generation_strategy="future_part_pipeline",
            part_status="candidate_for_single_part_generation",
            supported_candidate=True,
            part_brief=_assembly_part_brief(part_id, role),
            blocked_reasons=[],
        )
    return _assembly_part_classification(
        generation_strategy="future_part_pipeline",
        part_status="planned_only",
        supported_candidate=False,
        part_brief=f"{role.capitalize()} recorded for future part decomposition.",
        blocked_reasons=[],
    )


def _assembly_part_classification(
    *,
    generation_strategy: str,
    part_status: str,
    supported_candidate: bool,
    part_brief: str,
    blocked_reasons: list[str],
) -> dict[str, Any]:
    if generation_strategy not in _ASSEMBLY_GENERATION_STRATEGIES:
        generation_strategy = "future_part_pipeline"
    if part_status not in _ASSEMBLY_PART_STATUSES:
        part_status = "planned_only"
    return {
        "generation_strategy": generation_strategy,
        "part_status": part_status,
        "supported_candidate": bool(supported_candidate),
        "part_brief": _safe_short_text(part_brief, fallback="Assembly part recorded for future decomposition.", max_length=140),
        "blocked_reasons": [
            {"code": code}
            for code in _safe_diagnostic_codes(blocked_reasons)
        ],
    }


def _assembly_part_brief(part_id: str, role: str) -> str:
    if part_id == "base":
        return "Base component with assembly interfaces preserved for future single-part generation."
    if part_id == "lid":
        return "Lid or cover component with fastening interfaces preserved for future single-part generation."
    if "leaf" in part_id:
        return "Hinge leaf component with pin interface preserved for future single-part generation."
    if "support" in part_id:
        return "Support component with attachment interfaces preserved for future single-part generation."
    if "clamp" in part_id:
        return "Clamp component with sliding or contact interface preserved for future single-part generation."
    return f"{role.capitalize()} with assembly interfaces preserved for future single-part generation."


def _normalize_assembly_plan_interfaces(
    interfaces: list[dict[str, Any]],
    parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    part_ids = {part["part_id"] for part in parts if isinstance(part, dict) and isinstance(part.get("part_id"), str)}
    normalized: list[dict[str, Any]] = []
    for interface in interfaces:
        if not isinstance(interface, dict):
            continue
        from_id = _safe_artifact_id(interface.get("from"))
        to_id = _safe_artifact_id(interface.get("to"))
        if from_id not in part_ids and part_ids:
            from_id = sorted(part_ids)[0]
        if to_id not in part_ids and part_ids:
            candidates = [part_id for part_id in sorted(part_ids) if part_id != from_id]
            to_id = candidates[0] if candidates else from_id
        kind = _normalized_assembly_interface_kind(interface.get("kind"))
        normalized.append({
            "from": from_id,
            "to": to_id,
            "kind": kind,
            "notes": _safe_short_text(interface.get("notes"), fallback="interface requires future assembly planning"),
        })
    return normalized


def _normalize_assembly_plan_fasteners(fasteners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for fastener in fasteners:
        if not isinstance(fastener, dict):
            continue
        quantity = fastener.get("quantity")
        if not isinstance(quantity, int) or quantity < 1:
            quantity = None
        normalized.append({
            "kind": _safe_artifact_id(fastener.get("kind") or "fastener"),
            "quantity": quantity,
        })
    return normalized


def _normalized_assembly_interface_kind(value: Any) -> str:
    kind = _safe_artifact_id(value or "unknown")
    kind = _ASSEMBLY_INTERFACE_KIND_ALIASES.get(kind, kind)
    return kind if kind in _ASSEMBLY_INTERFACE_KINDS else "unknown"


def _assembly_plan_quality(
    *,
    parts: list[dict[str, Any]],
    interfaces: list[dict[str, Any]],
    fasteners: list[dict[str, Any]],
    risk_notes: list[dict[str, Any]],
    blocked_reasons: list[dict[str, Any]],
) -> dict[str, Any]:
    blocked_reason_codes = _safe_diagnostic_codes([
        str(reason.get("code"))
        for reason in blocked_reasons
        if isinstance(reason, dict) and isinstance(reason.get("code"), str)
    ])
    return {
        "assembly_plan_count": 1,
        "part_count": len(parts),
        "interface_count": len(interfaces),
        "fastener_count": len(fasteners),
        "risk_note_count": len(risk_notes),
        "part_candidate_count": sum(1 for part in parts if part.get("supported_candidate") is True),
        "part_reference_only_count": sum(1 for part in parts if part.get("part_status") == "reference_only"),
        "part_blocked_count": sum(1 for part in parts if part.get("part_status") == "blocked"),
        "part_generation_strategy_counts": _count_assembly_part_field(parts, "generation_strategy"),
        "part_status_counts": _count_assembly_part_field(parts, "part_status"),
        "blocked_reason_codes": blocked_reason_codes,
        "risk_notes": risk_notes,
    }


def _assembly_plan_quality_metadata(assembly_plan: dict[str, Any]) -> dict[str, Any]:
    quality = assembly_plan.get("quality") if isinstance(assembly_plan.get("quality"), dict) else {}
    return {
        "assembly_plan_count": _safe_nonnegative_int(quality.get("assembly_plan_count"), fallback=1),
        "part_count": _safe_nonnegative_int(quality.get("part_count"), fallback=len(assembly_plan.get("parts", []))),
        "interface_count": _safe_nonnegative_int(quality.get("interface_count"), fallback=len(assembly_plan.get("interfaces", []))),
        "fastener_count": _safe_nonnegative_int(quality.get("fastener_count"), fallback=len(assembly_plan.get("fasteners", []))),
        "risk_note_count": _safe_nonnegative_int(quality.get("risk_note_count"), fallback=len(assembly_plan.get("risk_notes", []))),
        "part_candidate_count": _safe_nonnegative_int(
            quality.get("part_candidate_count"),
            fallback=sum(1 for part in assembly_plan.get("parts", []) if isinstance(part, dict) and part.get("supported_candidate") is True),
        ),
        "part_reference_only_count": _safe_nonnegative_int(
            quality.get("part_reference_only_count"),
            fallback=sum(1 for part in assembly_plan.get("parts", []) if isinstance(part, dict) and part.get("part_status") == "reference_only"),
        ),
        "part_blocked_count": _safe_nonnegative_int(
            quality.get("part_blocked_count"),
            fallback=sum(1 for part in assembly_plan.get("parts", []) if isinstance(part, dict) and part.get("part_status") == "blocked"),
        ),
        "part_generation_strategy_counts": _safe_count_map(
            quality.get("part_generation_strategy_counts"),
            allowed=_ASSEMBLY_GENERATION_STRATEGIES,
            fallback=_count_assembly_part_field(assembly_plan.get("parts", []), "generation_strategy"),
        ),
        "part_status_counts": _safe_count_map(
            quality.get("part_status_counts"),
            allowed=_ASSEMBLY_PART_STATUSES,
            fallback=_count_assembly_part_field(assembly_plan.get("parts", []), "part_status"),
        ),
        "blocked_reason_codes": _safe_diagnostic_codes(
            list(quality.get("blocked_reason_codes", []))
            if isinstance(quality.get("blocked_reason_codes"), list)
            else []
        ),
    }


def _count_assembly_part_field(parts: Any, field: str) -> dict[str, int]:
    if not isinstance(parts, list):
        return {}
    counts: dict[str, int] = {}
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get(field), str):
            continue
        value = part[field]
        if field == "generation_strategy" and value not in _ASSEMBLY_GENERATION_STRATEGIES:
            continue
        if field == "part_status" and value not in _ASSEMBLY_PART_STATUSES:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def create_part_request_from_assembly_plan(
    assembly_plan: dict[str, Any],
    *,
    part_id: str | None = None,
    source_artifact: str = "assembly_plan.json",
) -> dict[str, Any]:
    """Compile a sanitized planning request for one assembly candidate part."""

    parts = assembly_plan.get("parts") if isinstance(assembly_plan.get("parts"), list) else []
    requested_part_id = _safe_artifact_id(part_id) if part_id else None
    selected_part: dict[str, Any] | None = None
    blocked_code: str | None = None

    if requested_part_id:
        requested_part = next(
            (
                part
                for part in parts
                if isinstance(part, dict) and _safe_artifact_id(part.get("part_id")) == requested_part_id
            ),
            None,
        )
        if requested_part and _is_selectable_assembly_part(requested_part):
            selected_part = requested_part
        elif requested_part and requested_part.get("part_status") == "reference_only":
            blocked_code = "part_request.reference_only_not_selectable"
        elif requested_part and requested_part.get("part_status") == "blocked":
            blocked_code = "part_request.blocked_part_not_selectable"
        else:
            blocked_code = "part_request.no_candidate_part"
    else:
        for part in parts:
            if isinstance(part, dict) and _is_selectable_assembly_part(part):
                selected_part = part
                break
        if selected_part is None:
            blocked_code = "part_request.no_candidate_part"

    if selected_part is None:
        return _blocked_part_create_request(
            assembly_plan,
            requested_part_id=requested_part_id,
            source_artifact=source_artifact,
            diagnostic_code=blocked_code or "part_request.no_candidate_part",
        )

    selected_part_id = _safe_artifact_id(selected_part.get("part_id"))
    interface_constraints = _part_request_interface_constraints(assembly_plan, selected_part_id)
    diagnostic_codes = ["part_request.created"]
    if interface_constraints:
        diagnostic_codes.append("part_request.interface_constraints_preserved")
    return {
        "artifact_type": "part_create_request",
        "schema_version": "0.1",
        "source_artifact": _safe_source_artifact_name(source_artifact),
        "part_id": selected_part_id,
        "part_role": _safe_short_text(selected_part.get("role"), fallback="assembly component"),
        "part_brief": _safe_short_text(
            selected_part.get("part_brief"),
            fallback="Assembly candidate part prepared for review.",
            max_length=180,
        ),
        "generation_mode": "single_part_candidate",
        "status": "ready_for_review",
        "interface_constraints": interface_constraints,
        "preserved_assembly_context": _part_request_assembly_context(assembly_plan, selected_part_id),
        "blocked_reasons": [],
        "diagnostic_codes": diagnostic_codes,
    }


def run_assembly_part_request_pipeline(
    assembly_plan: dict[str, Any] | str | Path,
    *,
    output_dir: str | Path | None = None,
    output_root: str | Path | None = None,
    part_id: str | None = None,
) -> dict[str, Any]:
    """Write a planning-only part create request from an assembly plan."""

    loaded_plan, source_artifact, default_output = _load_assembly_plan_input(assembly_plan)
    output_path = _resolve_output_dir("part_create_request", output_root, output_dir or default_output)
    output_path.mkdir(parents=True, exist_ok=True)
    request = create_part_request_from_assembly_plan(
        loaded_plan,
        part_id=part_id,
        source_artifact=source_artifact,
    )
    _write_json(output_path / "part_create_request.json", request)
    status = request.get("status") if isinstance(request.get("status"), str) else "blocked_no_candidate_part"
    success = status == "ready_for_review"
    trace = {
        "total_attempts": 0,
        "steps": [
            {
                "attempt": 0,
                "status": "ready_for_review" if success else "blocked",
                "stage": "assembly_part_request",
                "diagnostic_codes": request.get("diagnostic_codes", []),
            }
        ],
        "final_selected_candidate": request.get("part_id") if success else None,
        "assembly_part_request": {
            "workflow": "assembly_part_request",
            "version": "part-create-request-v0.1",
            "status": status,
            "local_authority": ["assembly_plan.json", "part_create_request.json"],
            "stages": ["load_assembly_plan", "select_candidate_part", "compile_part_create_request"],
            "artifacts": {"source": source_artifact, "part_create_request": "part_create_request.json"},
            "cad_ir_created": False,
            "part_modeling_started": False,
            "diagnostic_codes": request.get("diagnostic_codes", []),
        },
    }
    _write_json(output_path / "agent_trace.json", trace)
    report = {
        "success": success,
        "status": status,
        "blocked_stage": None if success else "assembly_part_request",
        "diagnostic_codes": request.get("diagnostic_codes", []),
        "source_artifact": request.get("source_artifact"),
        "part_id": request.get("part_id"),
        "part_request_status": status,
        "interface_constraint_count": len(request.get("interface_constraints", [])),
        "cad_ir_created": False,
        "part_modeling_started": False,
        "part_create_request": request,
        "files": _collect_files(output_path, repo_relative=True),
    }
    _write_json(output_path / "report.json", report)
    _write_part_request_report_md(output_path, report, request)
    files = _collect_files(output_path, repo_relative=True)
    report["files"] = files
    _write_json(output_path / "report.json", report)
    return {
        "status": status,
        "success": success,
        "output_dir": str(output_path),
        "part_create_request": request,
        "agent_trace": trace,
        "files": files,
        "report_json": str(output_path / "report.json"),
        "report_md": str(output_path / "report.md"),
    }


def review_part_create_request(part_create_request: dict[str, Any], *, source_artifact: str = "part_create_request.json") -> dict[str, Any]:
    """Review a planning-only part create request before future generation."""

    part_id = _safe_artifact_id(part_create_request.get("part_id")) if part_create_request.get("part_id") else None
    blocked_reason_codes = _part_request_blocked_reason_codes(part_create_request)
    checks = {
        "has_part_brief": _has_reviewable_part_brief(part_create_request),
        "has_interface_constraints": _has_part_request_interface_constraints(part_create_request),
        "is_reference_only": (
            "part_request.reference_only_not_selectable" in blocked_reason_codes
            or part_create_request.get("part_status") == "reference_only"
            or part_create_request.get("generation_strategy") == "reference_only"
        ),
        "is_blocked": (
            bool(blocked_reason_codes)
            or str(part_create_request.get("status", "")).startswith("blocked")
            or part_create_request.get("part_status") == "blocked"
            or part_create_request.get("generation_strategy") == "blocked"
        ),
        "has_provider_generated_code": _contains_provider_generated_code(part_create_request),
        "has_provider_generated_cad_ir": _contains_provider_generated_cad_ir(part_create_request),
        "has_arbitrary_provider_fields": _contains_arbitrary_provider_fields(part_create_request),
        "has_clear_related_parts": _has_clear_related_parts(part_create_request),
    }

    diagnostic_codes = ["part_request.review_created"]
    blocked_reasons: list[dict[str, str]] = []
    revision_notes: list[str] = []
    status = "approved"
    review_result = "approved_for_single_part_planning"

    if checks["is_reference_only"]:
        status = "blocked"
        review_result = "blocked_reference_only"
        diagnostic_codes.append("part_request.blocked_reference_only")
        blocked_reasons.append({"code": "part_request.blocked_reference_only"})
    elif checks["is_blocked"] or _has_unsupported_blocked_reason(blocked_reason_codes):
        status = "blocked"
        review_result = "blocked_unsupported_part"
        diagnostic_codes.append("part_request.blocked_unsupported_part")
        blocked_reasons.append({"code": "part_request.blocked_unsupported_part"})

    if checks["has_provider_generated_code"] or checks["has_arbitrary_provider_fields"]:
        status = "blocked"
        review_result = "blocked_provider_generated_code"
        diagnostic_codes.append("part_request.blocked_provider_generated_code")
        blocked_reasons.append({"code": "part_request.blocked_provider_generated_code"})
    if checks["has_provider_generated_cad_ir"]:
        status = "blocked"
        review_result = "blocked_provider_generated_cad_ir"
        diagnostic_codes.append("part_request.blocked_provider_generated_cad_ir")
        blocked_reasons.append({"code": "part_request.blocked_provider_generated_cad_ir"})

    if status != "blocked":
        if not checks["has_part_brief"]:
            status = "needs_revision"
            review_result = "needs_revision_missing_part_brief"
            diagnostic_codes.append("part_request.needs_revision_missing_part_brief")
            revision_notes.append("Part brief is missing or too vague for review.")
        if not checks["has_interface_constraints"] and _is_assembly_derived_part_request(part_create_request):
            status = "needs_revision"
            review_result = "needs_revision_missing_interface_constraints"
            diagnostic_codes.append("part_request.needs_revision_missing_interface_constraints")
            revision_notes.append("Assembly-derived part request needs interface constraints or an explicit no-interface context.")
        if not checks["has_clear_related_parts"] and _is_assembly_derived_part_request(part_create_request):
            status = "needs_revision"
            review_result = "needs_revision_missing_interface_constraints"
            diagnostic_codes.append("part_request.needs_revision_missing_interface_constraints")
            revision_notes.append("Related assembly parts are unclear.")
        if status == "approved":
            diagnostic_codes.append("part_request.approved_for_single_part_planning")

    return {
        "artifact_type": "part_request_review",
        "schema_version": "0.1",
        "source_artifact": _safe_part_request_source_artifact_name(source_artifact),
        "part_id": part_id,
        "status": status,
        "review_result": review_result,
        "checks": checks,
        "diagnostic_codes": _safe_diagnostic_codes(diagnostic_codes),
        "blocked_reasons": _dedupe_reason_codes(blocked_reasons),
        "revision_notes": [_safe_short_text(note, fallback="Review note.") for note in revision_notes],
    }


def run_part_request_review_pipeline(
    part_create_request: dict[str, Any] | str | Path,
    *,
    output_dir: str | Path | None = None,
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    """Write a planning-only review artifact for a part create request."""

    loaded_request, source_artifact, default_output = _load_part_create_request_input(part_create_request)
    output_path = _resolve_output_dir("part_request_review", output_root, output_dir or default_output)
    output_path.mkdir(parents=True, exist_ok=True)
    review = review_part_create_request(loaded_request, source_artifact=source_artifact)
    _write_json(output_path / "part_request_review.json", review)
    status = review["status"]
    trace = {
        "total_attempts": 0,
        "steps": [
            {
                "attempt": 0,
                "status": status,
                "stage": "part_request_review",
                "diagnostic_codes": review.get("diagnostic_codes", []),
            }
        ],
        "final_selected_candidate": review.get("part_id") if status == "approved" else None,
        "part_request_review": {
            "workflow": "part_request_review",
            "version": "part-request-review-v0.1",
            "status": status,
            "local_authority": ["part_create_request.json", "part_request_review.json"],
            "stages": ["load_part_create_request", "review_part_create_request"],
            "artifacts": {"source": source_artifact, "part_request_review": "part_request_review.json"},
            "cad_ir_created": False,
            "part_modeling_started": False,
            "diagnostic_codes": review.get("diagnostic_codes", []),
        },
    }
    _write_json(output_path / "agent_trace.json", trace)
    report = {
        "success": status == "approved",
        "status": status,
        "blocked_stage": "part_request_review" if status == "blocked" else None,
        "diagnostic_codes": review.get("diagnostic_codes", []),
        "source_artifact": review.get("source_artifact"),
        "part_id": review.get("part_id"),
        "review_result": review.get("review_result"),
        "cad_ir_created": False,
        "part_modeling_started": False,
        "part_request_review": review,
        "files": _collect_files(output_path, repo_relative=True),
    }
    _write_json(output_path / "report.json", report)
    _write_part_request_review_report_md(output_path, report, review)
    files = _collect_files(output_path, repo_relative=True)
    report["files"] = files
    _write_json(output_path / "report.json", report)
    return {
        "status": status,
        "success": status == "approved",
        "output_dir": str(output_path),
        "part_request_review": review,
        "agent_trace": trace,
        "files": files,
        "report_json": str(output_path / "report.json"),
        "report_md": str(output_path / "report.md"),
    }


def create_reviewed_part_handoff(
    part_create_request: dict[str, Any],
    part_request_review: dict[str, Any],
    *,
    source_part_request: str = "part_create_request.json",
    source_review: str = "part_request_review.json",
) -> dict[str, Any]:
    """Compile a sanitized handoff for future explicit single-part planning."""

    part_id = _safe_artifact_id(part_create_request.get("part_id")) if part_create_request.get("part_id") else None
    checks = part_request_review.get("checks") if isinstance(part_request_review.get("checks"), dict) else {}
    blocked_reason_codes = _part_request_blocked_reason_codes(part_create_request)
    review_status = part_request_review.get("status")
    status = "ready_for_single_part_planning"
    diagnostic_codes = ["part_handoff.created"]
    blocked_reasons: list[dict[str, str]] = []

    is_reference_only = (
        checks.get("is_reference_only") is True
        or "part_request.reference_only_not_selectable" in blocked_reason_codes
        or part_create_request.get("part_status") == "reference_only"
        or part_create_request.get("generation_strategy") == "reference_only"
    )
    is_blocked = (
        checks.get("is_blocked") is True
        or bool(blocked_reason_codes)
        or str(part_create_request.get("status", "")).startswith("blocked")
        or part_create_request.get("part_status") == "blocked"
        or part_create_request.get("generation_strategy") == "blocked"
        or _has_unsupported_blocked_reason(blocked_reason_codes)
    )
    has_provider_code = checks.get("has_provider_generated_code") is True or _contains_provider_generated_code(part_create_request)
    has_provider_cad_ir = checks.get("has_provider_generated_cad_ir") is True or _contains_provider_generated_cad_ir(part_create_request)
    has_arbitrary_provider_fields = (
        checks.get("has_arbitrary_provider_fields") is True or _contains_arbitrary_provider_fields(part_create_request)
    )
    missing_part_brief = not _has_reviewable_part_brief(part_create_request)
    missing_interfaces = (
        _is_assembly_derived_part_request(part_create_request)
        and (
            not _has_part_request_interface_constraints(part_create_request)
            or not _has_clear_related_parts(part_create_request)
        )
    )

    if review_status != "approved":
        if (
            review_status == "needs_revision"
            and part_request_review.get("review_result") == "needs_revision_missing_interface_constraints"
        ):
            status = "needs_revision_missing_interface_constraints"
            diagnostic_codes.append("part_handoff.needs_revision_missing_interface_constraints")
            blocked_reasons.append({"code": "part_handoff.needs_revision_missing_interface_constraints"})
        else:
            status = "blocked_review_not_approved"
            diagnostic_codes.append("part_handoff.blocked_review_not_approved")
            blocked_reasons.append({"code": "part_handoff.blocked_review_not_approved"})
    elif is_reference_only:
        status = "blocked_reference_only_part"
        diagnostic_codes.append("part_handoff.blocked_reference_only_part")
        blocked_reasons.append({"code": "part_handoff.blocked_reference_only_part"})
    elif is_blocked or missing_part_brief:
        status = "blocked_unsupported_part"
        diagnostic_codes.append("part_handoff.blocked_unsupported_part")
        blocked_reasons.append({"code": "part_handoff.blocked_unsupported_part"})
    elif missing_interfaces:
        status = "needs_revision_missing_interface_constraints"
        diagnostic_codes.append("part_handoff.needs_revision_missing_interface_constraints")
        blocked_reasons.append({"code": "part_handoff.needs_revision_missing_interface_constraints"})

    if has_provider_code or has_arbitrary_provider_fields:
        if status == "ready_for_single_part_planning":
            status = "blocked_unsupported_part"
            diagnostic_codes.append("part_handoff.blocked_unsupported_part")
            blocked_reasons.append({"code": "part_handoff.blocked_unsupported_part"})
        diagnostic_codes.append("part_handoff.provider_code_rejected")
        blocked_reasons.append({"code": "part_handoff.provider_code_rejected"})
    if has_provider_cad_ir:
        if status == "ready_for_single_part_planning":
            status = "blocked_unsupported_part"
            diagnostic_codes.append("part_handoff.blocked_unsupported_part")
            blocked_reasons.append({"code": "part_handoff.blocked_unsupported_part"})
        diagnostic_codes.append("part_handoff.provider_cad_ir_rejected")
        blocked_reasons.append({"code": "part_handoff.provider_cad_ir_rejected"})

    if status == "ready_for_single_part_planning":
        diagnostic_codes.append("part_handoff.ready_for_single_part_planning")

    return {
        "artifact_type": "reviewed_part_handoff",
        "schema_version": "0.1",
        "source_part_request": _safe_part_request_source_artifact_name(source_part_request),
        "source_review": _safe_part_request_review_source_artifact_name(source_review),
        "part_id": part_id,
        "status": status,
        "single_part_prompt": _single_part_handoff_prompt(part_create_request),
        "part_brief": _safe_short_text(part_create_request.get("part_brief"), fallback="", max_length=180),
        "interface_constraints": _reviewed_part_handoff_interface_constraints(part_create_request),
        "preserved_assembly_context": _reviewed_part_handoff_assembly_context(part_create_request),
        "diagnostic_codes": _safe_diagnostic_codes(diagnostic_codes),
        "blocked_reasons": _dedupe_reason_codes(blocked_reasons),
    }


def run_reviewed_part_handoff_pipeline(
    part_create_request: dict[str, Any] | str | Path,
    part_request_review: dict[str, Any] | str | Path,
    *,
    output_dir: str | Path | None = None,
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    """Write a planning-only handoff after part request review approval."""

    loaded_request, source_part_request, request_default_output = _load_part_create_request_input(part_create_request)
    loaded_review, source_review, review_default_output = _load_part_request_review_input(part_request_review)
    output_path = _resolve_output_dir(
        "reviewed_part_handoff",
        output_root,
        output_dir or review_default_output or request_default_output,
    )
    output_path.mkdir(parents=True, exist_ok=True)
    handoff = create_reviewed_part_handoff(
        loaded_request,
        loaded_review,
        source_part_request=source_part_request,
        source_review=source_review,
    )
    _write_json(output_path / "reviewed_part_handoff.json", handoff)
    status = handoff["status"]
    success = status == "ready_for_single_part_planning"
    trace = {
        "total_attempts": 0,
        "steps": [
            {
                "attempt": 0,
                "status": status,
                "stage": "reviewed_part_handoff",
                "diagnostic_codes": handoff.get("diagnostic_codes", []),
            }
        ],
        "final_selected_candidate": handoff.get("part_id") if success else None,
        "reviewed_part_handoff": {
            "workflow": "reviewed_part_handoff",
            "version": "reviewed-part-handoff-v0.1",
            "status": status,
            "local_authority": [
                "part_create_request.json",
                "part_request_review.json",
                "reviewed_part_handoff.json",
            ],
            "stages": [
                "load_part_create_request",
                "load_part_request_review",
                "compile_reviewed_part_handoff",
            ],
            "artifacts": {
                "source_part_request": source_part_request,
                "source_review": source_review,
                "reviewed_part_handoff": "reviewed_part_handoff.json",
            },
            "cad_ir_created": False,
            "part_modeling_started": False,
            "diagnostic_codes": handoff.get("diagnostic_codes", []),
        },
    }
    _write_json(output_path / "agent_trace.json", trace)
    report = {
        "success": success,
        "status": status,
        "blocked_stage": None if success else "reviewed_part_handoff",
        "diagnostic_codes": handoff.get("diagnostic_codes", []),
        "source_part_request": handoff.get("source_part_request"),
        "source_review": handoff.get("source_review"),
        "part_id": handoff.get("part_id"),
        "interface_constraint_count": len(handoff.get("interface_constraints", [])),
        "cad_ir_created": False,
        "part_modeling_started": False,
        "reviewed_part_handoff": handoff,
        "files": _collect_files(output_path, repo_relative=True),
    }
    _write_json(output_path / "report.json", report)
    _write_reviewed_part_handoff_report_md(output_path, report, handoff)
    files = _collect_files(output_path, repo_relative=True)
    report["files"] = files
    _write_json(output_path / "report.json", report)
    return {
        "status": status,
        "success": success,
        "output_dir": str(output_path),
        "reviewed_part_handoff": handoff,
        "agent_trace": trace,
        "files": files,
        "report_json": str(output_path / "report.json"),
        "report_md": str(output_path / "report.md"),
    }


def run_reviewed_part_single_create_pipeline(
    reviewed_part_handoff: dict[str, Any] | str | Path,
    adapter: AgentAdapter,
    *,
    output_dir: str | Path | None = None,
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    """Explicitly execute one reviewed part handoff through normalized create."""

    handoff, source_handoff, default_output = _load_reviewed_part_handoff_input(reviewed_part_handoff)
    output_path = _resolve_output_dir("reviewed_part_single_create", output_root, output_dir or default_output)
    output_path.mkdir(parents=True, exist_ok=True)
    sanitized_handoff = _sanitize_reviewed_part_handoff(handoff, source_handoff=source_handoff)
    _write_json(output_path / "reviewed_part_handoff.json", sanitized_handoff)

    safety = _reviewed_part_single_create_safety(sanitized_handoff, handoff)
    if safety["status"] != "ready":
        return _write_blocked_reviewed_part_single_create_result(
            output_path=output_path,
            handoff=sanitized_handoff,
            source_handoff=source_handoff,
            status=safety["status"],
            diagnostic_codes=safety["diagnostic_codes"],
            blocked_reasons=safety["blocked_reasons"],
        )

    execution_request = _compile_part_execution_request(sanitized_handoff, source_handoff=source_handoff)
    _write_json(output_path / "part_execution_request.json", execution_request)
    child_output_dir = output_path / execution_request["child_run_id"]
    child_result = run_provider_normalized_create_pipeline(
        execution_request["prompt"],
        adapter,
        output_dir=child_output_dir,
    )
    lineage = _reviewed_part_single_create_lineage(
        output_path=output_path,
        child_output_dir=child_output_dir,
        handoff=sanitized_handoff,
        source_handoff=source_handoff,
    )
    _write_json(output_path / "lineage.json", lineage)

    metadata = {
        "workflow": "reviewed_part_single_create",
        "version": "reviewed-part-single-create-v0.1",
        "status": child_result.get("status", "unknown"),
        "part_id": sanitized_handoff.get("part_id"),
        "local_authority": [
            "reviewed_part_handoff.json",
            "part_execution_request.json",
            "run_provider_normalized_create_pipeline",
            "lineage.json",
        ],
        "stages": [
            "load_reviewed_part_handoff",
            "validate_review_gate",
            "compile_single_part_execution_request",
            "run_provider_normalized_create_pipeline",
            "record_lineage",
        ],
        "artifacts": {
            "reviewed_part_handoff": "reviewed_part_handoff.json",
            "part_execution_request": "part_execution_request.json",
            "child_run_dir": _repo_relative_string(child_output_dir),
            "lineage": "lineage.json",
        },
        "cad_ir_created": (child_output_dir / "input_ir.json").exists(),
        "part_modeling_started": child_result.get("status") == "success",
        "diagnostic_codes": ["reviewed_part_single_create.started"],
    }
    trace = {
        "total_attempts": 1,
        "steps": [
            {
                "attempt": 0,
                "status": child_result.get("status", "unknown"),
                "stage": "reviewed_part_single_create",
                "diagnostic_codes": metadata["diagnostic_codes"],
            }
        ],
        "final_selected_candidate": sanitized_handoff.get("part_id"),
        "reviewed_part_single_create": metadata,
    }
    _write_json(output_path / "agent_trace.json", trace)
    report = {
        "success": child_result.get("status") == "success",
        "status": child_result.get("status", "unknown"),
        "blocked_stage": None if child_result.get("status") == "success" else "single_part_create",
        "diagnostic_codes": metadata["diagnostic_codes"],
        "part_id": sanitized_handoff.get("part_id"),
        "source_handoff": "reviewed_part_handoff.json",
        "child_run_dir": _repo_relative_string(child_output_dir),
        "cad_ir_created": metadata["cad_ir_created"],
        "part_modeling_started": metadata["part_modeling_started"],
        "reviewed_part_single_create": metadata,
        "lineage": lineage,
        "files": _collect_files(output_path, repo_relative=True),
    }
    _write_json(output_path / "report.json", report)
    _write_reviewed_part_single_create_report_md(output_path, report)
    files = _collect_files(output_path, repo_relative=True)
    report["files"] = files
    _write_json(output_path / "report.json", report)
    return {
        "status": child_result.get("status", "unknown"),
        "success": child_result.get("status") == "success",
        "output_dir": str(output_path),
        "child_output_dir": str(child_output_dir),
        "reviewed_part_handoff": sanitized_handoff,
        "part_execution_request": execution_request,
        "child_result": child_result,
        "lineage": lineage,
        "agent_trace": trace,
        "files": files,
        "report_json": str(output_path / "report.json"),
        "report_md": str(output_path / "report.md"),
    }


def _is_selectable_assembly_part(part: dict[str, Any]) -> bool:
    part_id = _safe_artifact_id(part.get("part_id"))
    if part_id in {"pin", "screw", "bolt", "nut", "washer", "fastener"}:
        return False
    return (
        part.get("supported_candidate") is True
        and part.get("part_status") == "candidate_for_single_part_generation"
        and part.get("generation_strategy") != "blocked"
    )


def _blocked_part_create_request(
    assembly_plan: dict[str, Any],
    *,
    requested_part_id: str | None,
    source_artifact: str,
    diagnostic_code: str,
) -> dict[str, Any]:
    safe_code = _safe_diagnostic_codes([diagnostic_code])[0]
    return {
        "artifact_type": "part_create_request",
        "schema_version": "0.1",
        "source_artifact": _safe_source_artifact_name(source_artifact),
        "part_id": requested_part_id,
        "part_role": "",
        "part_brief": "",
        "generation_mode": "single_part_candidate",
        "status": "blocked_no_candidate_part",
        "interface_constraints": [],
        "preserved_assembly_context": _part_request_assembly_context(assembly_plan, requested_part_id),
        "blocked_reasons": [{"code": safe_code}],
        "diagnostic_codes": [safe_code],
    }


def _part_request_interface_constraints(assembly_plan: dict[str, Any], selected_part_id: str) -> list[dict[str, str]]:
    constraints: list[dict[str, str]] = []
    interfaces = assembly_plan.get("interfaces") if isinstance(assembly_plan.get("interfaces"), list) else []
    for interface in interfaces:
        if not isinstance(interface, dict):
            continue
        from_id = _safe_artifact_id(interface.get("from"))
        to_id = _safe_artifact_id(interface.get("to"))
        if selected_part_id not in {from_id, to_id}:
            continue
        related_part_id = to_id if selected_part_id == from_id else from_id
        constraints.append({
            "kind": _part_request_constraint_kind(interface.get("kind")),
            "related_part_id": related_part_id,
            "notes": _safe_short_text(interface.get("notes"), fallback="Assembly interface preserved for review."),
        })
    return constraints


def _part_request_constraint_kind(value: Any) -> str:
    kind = _normalized_assembly_interface_kind(value)
    return {
        "screw_fastened": "screw_alignment",
        "pinned_joint": "pin_alignment",
        "sliding_fit": "sliding_fit",
        "snap_fit": "snap_fit",
        "stacked": "contact_alignment",
        "unknown": "assembly_interface",
    }[kind]


def _part_request_assembly_context(assembly_plan: dict[str, Any], selected_part_id: str | None) -> dict[str, Any]:
    scope = assembly_plan.get("scope") if assembly_plan.get("scope") in {"multi_part", "assembly"} else "multi_part"
    related_parts: list[str] = []
    parts = assembly_plan.get("parts") if isinstance(assembly_plan.get("parts"), list) else []
    for part in parts:
        if not isinstance(part, dict):
            continue
        candidate = _safe_artifact_id(part.get("part_id"))
        if candidate != selected_part_id and candidate not in related_parts:
            related_parts.append(candidate)
    fasteners = assembly_plan.get("fasteners") if isinstance(assembly_plan.get("fasteners"), list) else []
    for fastener in fasteners:
        if not isinstance(fastener, dict):
            continue
        kind = _safe_artifact_id(fastener.get("kind") or "fastener")
        label = f"{kind}s" if not kind.endswith("s") else kind
        if label not in related_parts:
            related_parts.append(label)
    return {
        "assembly_scope": scope,
        "related_parts": related_parts,
    }


def _load_assembly_plan_input(assembly_plan: dict[str, Any] | str | Path) -> tuple[dict[str, Any], str, Path | None]:
    if isinstance(assembly_plan, dict):
        return assembly_plan, "assembly_plan.json", None
    path = Path(assembly_plan)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = _require_repo_path(path.resolve())
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("assembly_plan must be a JSON object")
    return loaded, path.name, path.parent


def _safe_source_artifact_name(value: Any) -> str:
    name = Path(str(value or "assembly_plan.json")).name
    if name != "assembly_plan.json":
        return "assembly_plan.json"
    return name


def _load_part_create_request_input(part_create_request: dict[str, Any] | str | Path) -> tuple[dict[str, Any], str, Path | None]:
    if isinstance(part_create_request, dict):
        return part_create_request, "part_create_request.json", None
    path = Path(part_create_request)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = _require_repo_path(path.resolve())
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("part_create_request must be a JSON object")
    return loaded, path.name, path.parent


def _load_part_request_review_input(part_request_review: dict[str, Any] | str | Path) -> tuple[dict[str, Any], str, Path | None]:
    if isinstance(part_request_review, dict):
        return part_request_review, "part_request_review.json", None
    path = Path(part_request_review)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = _require_repo_path(path.resolve())
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("part_request_review must be a JSON object")
    return loaded, path.name, path.parent


def _load_reviewed_part_handoff_input(reviewed_part_handoff: dict[str, Any] | str | Path) -> tuple[dict[str, Any], str, Path | None]:
    if isinstance(reviewed_part_handoff, dict):
        return reviewed_part_handoff, "reviewed_part_handoff.json", None
    path = Path(reviewed_part_handoff)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = _require_repo_path(path.resolve())
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("reviewed_part_handoff must be a JSON object")
    return loaded, path.name, path.parent


def _safe_part_request_source_artifact_name(value: Any) -> str:
    name = Path(str(value or "part_create_request.json")).name
    if name != "part_create_request.json":
        return "part_create_request.json"
    return name


def _safe_part_request_review_source_artifact_name(value: Any) -> str:
    name = Path(str(value or "part_request_review.json")).name
    if name != "part_request_review.json":
        return "part_request_review.json"
    return name


def _safe_reviewed_part_handoff_source_artifact_name(value: Any) -> str:
    name = Path(str(value or "reviewed_part_handoff.json")).name
    if name != "reviewed_part_handoff.json":
        return "reviewed_part_handoff.json"
    return name


def _single_part_handoff_prompt(part_create_request: dict[str, Any]) -> str:
    part_id = _safe_artifact_id(part_create_request.get("part_id")) if part_create_request.get("part_id") else "component"
    constraints = _reviewed_part_handoff_interface_constraints(part_create_request)
    if constraints:
        phrases = [
            f"{constraint['kind'].replace('_', ' ')} with {constraint['related_part_id']}"
            for constraint in constraints[:3]
        ]
        return f"Create the {part_id} component as a single CAD part. Preserve {' and '.join(phrases)}."
    return f"Create the {part_id} component as a single CAD part."


def _reviewed_part_handoff_interface_constraints(part_create_request: dict[str, Any]) -> list[dict[str, str]]:
    constraints = part_create_request.get("interface_constraints")
    if not isinstance(constraints, list):
        return []
    allowed_kinds = {
        "assembly_interface",
        "contact_alignment",
        "pin_alignment",
        "screw_alignment",
        "sliding_fit",
        "snap_fit",
    }
    sanitized: list[dict[str, str]] = []
    for constraint in constraints:
        if not isinstance(constraint, dict):
            continue
        related_part_id = _safe_artifact_id(constraint.get("related_part_id"))
        kind = _safe_artifact_id(constraint.get("kind"))
        if not kind or not related_part_id:
            continue
        if kind not in allowed_kinds:
            kind = _part_request_constraint_kind(kind)
        sanitized.append({
            "kind": kind,
            "related_part_id": related_part_id,
            "notes": _safe_short_text(constraint.get("notes"), fallback="Assembly interface preserved for planning."),
        })
    return sanitized


def _reviewed_part_handoff_assembly_context(part_create_request: dict[str, Any]) -> dict[str, Any]:
    context = part_create_request.get("preserved_assembly_context")
    if not isinstance(context, dict):
        return {"assembly_scope": "multi_part", "related_parts": []}
    scope = context.get("assembly_scope") if context.get("assembly_scope") in {"multi_part", "assembly"} else "multi_part"
    related_parts: list[str] = []
    source_related_parts = context.get("related_parts") if isinstance(context.get("related_parts"), list) else []
    for related_part in source_related_parts:
        safe_part = _safe_artifact_id(related_part)
        if safe_part and safe_part not in related_parts:
            related_parts.append(safe_part)
    return {"assembly_scope": scope, "related_parts": related_parts}


def _sanitize_reviewed_part_handoff(handoff: dict[str, Any], *, source_handoff: str) -> dict[str, Any]:
    return {
        "artifact_type": "reviewed_part_handoff",
        "schema_version": "0.1",
        "source_part_request": _safe_part_request_source_artifact_name(handoff.get("source_part_request")),
        "source_review": _safe_part_request_review_source_artifact_name(handoff.get("source_review")),
        "source_handoff": _safe_reviewed_part_handoff_source_artifact_name(source_handoff),
        "part_id": _safe_artifact_id(handoff.get("part_id")) if handoff.get("part_id") else None,
        "status": handoff.get("status") if isinstance(handoff.get("status"), str) else "blocked_review_not_approved",
        "single_part_prompt": _safe_short_text(handoff.get("single_part_prompt"), fallback="", max_length=240),
        "part_brief": _safe_short_text(handoff.get("part_brief"), fallback="", max_length=180),
        "interface_constraints": _reviewed_part_handoff_interface_constraints(handoff),
        "preserved_assembly_context": _reviewed_part_handoff_assembly_context(handoff),
        "diagnostic_codes": _safe_diagnostic_codes([
            code for code in handoff.get("diagnostic_codes", []) if isinstance(code, str)
        ]),
        "blocked_reasons": _dedupe_reason_codes([
            reason for reason in handoff.get("blocked_reasons", []) if isinstance(reason, dict)
        ]),
    }


def _reviewed_part_single_create_safety(sanitized_handoff: dict[str, Any], raw_handoff: dict[str, Any]) -> dict[str, Any]:
    diagnostic_codes: list[str] = []
    blocked_reasons: list[dict[str, str]] = []
    status = "ready"

    def block(next_status: str, code: str) -> None:
        nonlocal status
        if status == "ready":
            status = next_status
        diagnostic_codes.append(code)
        blocked_reasons.append({"code": code})

    if sanitized_handoff.get("status") != "ready_for_single_part_planning":
        block("blocked_handoff_not_ready", "reviewed_part_single_create.blocked_handoff_not_ready")
    if not _has_reviewable_part_brief(sanitized_handoff):
        block("blocked_missing_part_brief", "reviewed_part_single_create.blocked_missing_part_brief")
    if _is_assembly_derived_part_request(sanitized_handoff) and (
        not _has_part_request_interface_constraints(sanitized_handoff)
        or not _has_clear_related_parts(sanitized_handoff)
    ):
        block("needs_revision_missing_interface_constraints", "reviewed_part_single_create.needs_revision_missing_interface_constraints")
    if sanitized_handoff.get("part_id") in {"screw", "screws", "bolt", "bolts", "nut", "nuts", "washer", "washers", "fastener", "fasteners"}:
        block("blocked_reference_only_part", "reviewed_part_single_create.blocked_reference_only_part")
    if sanitized_handoff.get("blocked_reasons"):
        block("blocked_unsupported_part", "reviewed_part_single_create.blocked_unsupported_part")
    if _contains_provider_generated_code(raw_handoff):
        block("blocked_provider_generated_code", "reviewed_part_single_create.provider_code_rejected")
    if _contains_provider_generated_cad_ir(raw_handoff):
        block("blocked_provider_generated_cad_ir", "reviewed_part_single_create.provider_cad_ir_rejected")
    if _contains_arbitrary_provider_fields(raw_handoff):
        block("blocked_arbitrary_provider_fields", "reviewed_part_single_create.provider_code_rejected")
    if _handoff_requests_multi_part_or_assembly_generation(sanitized_handoff):
        block("blocked_multi_part_or_assembly_request", "reviewed_part_single_create.blocked_multi_part_or_assembly_request")
    if _handoff_requests_safety_critical_scope(sanitized_handoff):
        block("blocked_safety_critical_scope", "reviewed_part_single_create.blocked_safety_critical_scope")

    if status == "ready":
        diagnostic_codes.append("reviewed_part_single_create.ready")
    return {
        "status": status,
        "diagnostic_codes": _safe_diagnostic_codes(diagnostic_codes),
        "blocked_reasons": _dedupe_reason_codes(blocked_reasons),
    }


def _compile_part_execution_request(handoff: dict[str, Any], *, source_handoff: str) -> dict[str, Any]:
    part_id = _safe_artifact_id(handoff.get("part_id"))
    return {
        "artifact_type": "part_execution_request",
        "schema_version": "0.1",
        "source_handoff": _safe_reviewed_part_handoff_source_artifact_name(source_handoff),
        "part_id": part_id,
        "execution_mode": "single_part_only",
        "child_run_id": f"single_part_{part_id}",
        "prompt": _reviewed_part_single_create_prompt(handoff),
        "diagnostic_codes": ["reviewed_part_single_create.execution_request_created"],
    }


def _reviewed_part_single_create_prompt(handoff: dict[str, Any]) -> str:
    part_id = _safe_artifact_id(handoff.get("part_id"))
    lines = [
        f'Create a single CAD part for part_id "{part_id}".',
        "",
        "Part brief:",
        _safe_short_text(handoff.get("part_brief"), fallback="Single reviewed CAD part.", max_length=180),
        "",
        "External interface constraints to preserve:",
    ]
    constraints = handoff.get("interface_constraints") if isinstance(handoff.get("interface_constraints"), list) else []
    if constraints:
        for constraint in constraints:
            if isinstance(constraint, dict):
                note = _safe_short_text(
                    constraint.get("notes"),
                    fallback=f"Preserve {constraint.get('kind', 'assembly interface')} with {constraint.get('related_part_id', 'related part')}.",
                    max_length=160,
                )
                lines.append(f"- {note}")
    else:
        lines.append("- No assembly interfaces were supplied.")
    lines.extend([
        "",
        "This is a single-part generation request derived from reviewed planning context.",
        "Do not generate other parts or a combined model.",
    ])
    return "\n".join(lines)


def _reviewed_part_single_create_lineage(
    *,
    output_path: Path,
    child_output_dir: Path,
    handoff: dict[str, Any],
    source_handoff: str,
) -> dict[str, Any]:
    return {
        "artifact_type": "lineage",
        "version": "lineage-v0.1",
        "relationship": "reviewed_part_single_create_child",
        "part_id": handoff.get("part_id"),
        "assembly_plan_artifact": "assembly_plan.json",
        "part_create_request_artifact": handoff.get("source_part_request") or "part_create_request.json",
        "part_request_review_artifact": handoff.get("source_review") or "part_request_review.json",
        "reviewed_part_handoff_artifact": _safe_reviewed_part_handoff_source_artifact_name(source_handoff),
        "execution_request_artifact": "part_execution_request.json",
        "parent_run_id": output_path.name,
        "parent_run_dir": _repo_relative_string(output_path),
        "child_run_id": child_output_dir.name,
        "child_run_dir": _repo_relative_string(child_output_dir),
    }


def _handoff_requests_multi_part_or_assembly_generation(handoff: dict[str, Any]) -> bool:
    text = " ".join([
        str(handoff.get("single_part_prompt") or ""),
        str(handoff.get("part_brief") or ""),
    ]).lower()
    blocked_phrases = [
        "generate an assembly",
        "generate assembly",
        "create an assembly",
        "create assembly",
        "generate all parts",
        "all assembly parts",
        "batch generate",
        "multi-part cad",
        "multipart cad",
        "step assembly",
    ]
    return any(phrase in text for phrase in blocked_phrases)


def _handoff_requests_safety_critical_scope(handoff: dict[str, Any]) -> bool:
    text = " ".join([
        str(handoff.get("single_part_prompt") or ""),
        str(handoff.get("part_brief") or ""),
    ]).lower()
    return any(phrase in text for phrase in ("safety-critical", "load-bearing aerospace", "life support", "medical implant"))


def _part_request_blocked_reason_codes(part_create_request: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for reason in part_create_request.get("blocked_reasons", []):
        if isinstance(reason, dict) and isinstance(reason.get("code"), str):
            codes.append(reason["code"])
    for code in part_create_request.get("diagnostic_codes", []):
        if isinstance(code, str) and ("blocked" in code or "reference_only" in code):
            codes.append(code)
    return _safe_diagnostic_codes(codes)


def _has_reviewable_part_brief(part_create_request: dict[str, Any]) -> bool:
    brief = part_create_request.get("part_brief")
    if not isinstance(brief, str):
        return False
    normalized = _safe_short_text(brief, fallback="", max_length=180).lower()
    vague = {
        "",
        "part",
        "component",
        "assembly component",
        "assembly candidate part prepared for review.",
    }
    return len(normalized) >= 16 and normalized not in vague


def _has_part_request_interface_constraints(part_create_request: dict[str, Any]) -> bool:
    constraints = part_create_request.get("interface_constraints")
    if not isinstance(constraints, list) or not constraints:
        return False
    for constraint in constraints:
        if not isinstance(constraint, dict):
            continue
        if constraint.get("kind") and constraint.get("related_part_id"):
            return True
    return False


def _is_assembly_derived_part_request(part_create_request: dict[str, Any]) -> bool:
    context = part_create_request.get("preserved_assembly_context")
    if not isinstance(context, dict):
        return True
    scope = context.get("assembly_scope")
    related_parts = context.get("related_parts")
    return scope in {"multi_part", "assembly"} or (isinstance(related_parts, list) and bool(related_parts))


def _has_clear_related_parts(part_create_request: dict[str, Any]) -> bool:
    context = part_create_request.get("preserved_assembly_context")
    if not isinstance(context, dict):
        return False
    related_parts = context.get("related_parts")
    if not isinstance(related_parts, list):
        return False
    return all(isinstance(part, str) and bool(_safe_artifact_id(part)) for part in related_parts)


def _has_unsupported_blocked_reason(codes: list[str]) -> bool:
    return any("unsupported" in code or "blocked_part" in code or "safety" in code for code in codes)


def _contains_provider_generated_code(value: Any) -> bool:
    code_keys = {"python_code", "cadquery_code", "model_py", "model.py", "shell_command"}
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in code_keys or "cadquery" in key_text or "python_code" in key_text:
                return True
            if _contains_provider_generated_code(item):
                return True
    elif isinstance(value, list):
        return any(_contains_provider_generated_code(item) for item in value)
    elif isinstance(value, str):
        lowered = value.lower()
        return "import cadquery" in lowered or "cq." in lowered or "python model.py" in lowered
    return False


def _contains_provider_generated_cad_ir(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in {"cad_ir", "input_ir", "provider_cad_ir"}:
                return True
            if _contains_provider_generated_cad_ir(item):
                return True
    elif isinstance(value, list):
        return any(_contains_provider_generated_cad_ir(item) for item in value)
    return False


def _contains_arbitrary_provider_fields(value: Any) -> bool:
    allowed_provider_keys = set()
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text.startswith("provider") and key_text not in allowed_provider_keys:
                return True
            if key_text in {"raw_response", "raw_transcript", "messages", "transcript"}:
                return True
            if _contains_arbitrary_provider_fields(item):
                return True
    elif isinstance(value, list):
        return any(_contains_arbitrary_provider_fields(item) for item in value)
    return False


def _dedupe_reason_codes(reasons: list[dict[str, str]]) -> list[dict[str, str]]:
    codes = _safe_diagnostic_codes([
        reason["code"]
        for reason in reasons
        if isinstance(reason, dict) and isinstance(reason.get("code"), str)
    ])
    return [{"code": code} for code in codes]


def _write_part_request_review_report_md(
    output_path: Path,
    report: dict[str, Any],
    review: dict[str, Any],
) -> None:
    lines = [
        "# Part Request Review Report",
        "",
        f"**Status:** {report.get('status')}",
        f"**Review result:** `{review.get('review_result')}`",
        "",
        "`part_request_review.json` is a planning/review artifact only. CadFlow did not generate CAD IR, "
        "`input_ir.json`, STEP, STL, or CadQuery/Python code.",
        "",
        "## Diagnostics",
        "",
    ]
    for code in review.get("diagnostic_codes", []):
        lines.append(f"- `{code}`")
    (output_path / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_reviewed_part_handoff_report_md(
    output_path: Path,
    report: dict[str, Any],
    handoff: dict[str, Any],
) -> None:
    lines = [
        "# Reviewed Part Handoff Report",
        "",
        f"**Status:** {report.get('status')}",
        f"**Part ID:** `{handoff.get('part_id')}`",
        "",
        "`reviewed_part_handoff.json` is a planning handoff artifact only. CadFlow did not generate CAD IR, "
        "`input_ir.json`, STEP, STL, or CadQuery/Python code.",
        "",
        "## Diagnostics",
        "",
    ]
    for code in handoff.get("diagnostic_codes", []):
        lines.append(f"- `{code}`")
    (output_path / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_blocked_reviewed_part_single_create_result(
    *,
    output_path: Path,
    handoff: dict[str, Any],
    source_handoff: str,
    status: str,
    diagnostic_codes: list[str],
    blocked_reasons: list[dict[str, str]],
) -> dict[str, Any]:
    trace = {
        "total_attempts": 0,
        "steps": [
            {
                "attempt": 0,
                "status": "blocked" if not status.startswith("needs_revision") else "needs_revision",
                "stage": "reviewed_part_single_create",
                "diagnostic_codes": diagnostic_codes,
            }
        ],
        "final_selected_candidate": None,
        "reviewed_part_single_create": {
            "workflow": "reviewed_part_single_create",
            "version": "reviewed-part-single-create-v0.1",
            "status": status,
            "part_id": handoff.get("part_id"),
            "local_authority": ["reviewed_part_handoff.json"],
            "stages": ["load_reviewed_part_handoff", "validate_review_gate"],
            "artifacts": {"reviewed_part_handoff": _safe_reviewed_part_handoff_source_artifact_name(source_handoff)},
            "cad_ir_created": False,
            "part_modeling_started": False,
            "diagnostic_codes": diagnostic_codes,
        },
    }
    _write_json(output_path / "agent_trace.json", trace)
    report = {
        "success": False,
        "status": status,
        "blocked_stage": "reviewed_part_single_create",
        "diagnostic_codes": diagnostic_codes,
        "blocked_reasons": blocked_reasons,
        "part_id": handoff.get("part_id"),
        "source_handoff": "reviewed_part_handoff.json",
        "cad_ir_created": False,
        "part_modeling_started": False,
        "reviewed_part_handoff": handoff,
        "files": _collect_files(output_path, repo_relative=True),
    }
    _write_json(output_path / "report.json", report)
    _write_reviewed_part_single_create_report_md(output_path, report)
    files = _collect_files(output_path, repo_relative=True)
    report["files"] = files
    _write_json(output_path / "report.json", report)
    return {
        "status": status,
        "success": False,
        "blocked_stage": "reviewed_part_single_create",
        "diagnostic_codes": diagnostic_codes,
        "blocked_reasons": blocked_reasons,
        "output_dir": str(output_path),
        "reviewed_part_handoff": handoff,
        "agent_trace": trace,
        "files": files,
        "report_json": str(output_path / "report.json"),
        "report_md": str(output_path / "report.md"),
    }


def _write_reviewed_part_single_create_report_md(output_path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Reviewed Part Single Create Report",
        "",
        f"**Status:** {report.get('status')}",
        f"**Part ID:** `{report.get('part_id')}`",
        "",
        "This bridge executes exactly one reviewed single-part handoff through the normalized provider create pipeline.",
        "It does not generate an assembly, generate all parts, solve assembly constraints, or export a STEP assembly.",
        "",
        "## Diagnostics",
        "",
    ]
    for code in report.get("diagnostic_codes", []):
        lines.append(f"- `{code}`")
    (output_path / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_part_request_report_md(
    output_path: Path,
    report: dict[str, Any],
    request: dict[str, Any],
) -> None:
    lines = [
        "# Assembly Part Request Report",
        "",
        f"**Status:** {report.get('status')}",
        "",
        "`part_create_request.json` is a review/planning artifact only. CadFlow did not generate CAD IR, "
        "per-part `input_ir.json`, STEP, STL, or CadQuery/Python code.",
        "",
        "## Part Request",
        "",
        f"- Part ID: `{request.get('part_id')}`",
        f"- Generation mode: `{request.get('generation_mode')}`",
        f"- Interface constraints: {len(request.get('interface_constraints', []))}",
        "",
        "## Diagnostics",
        "",
    ]
    for code in request.get("diagnostic_codes", []):
        lines.append(f"- `{code}`")
    (output_path / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _safe_count_map(value: Any, *, allowed: set[str], fallback: dict[str, int]) -> dict[str, int]:
    if not isinstance(value, dict):
        return fallback
    counts: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or key not in allowed:
            continue
        counts[key] = _safe_nonnegative_int(count, fallback=0)
    return dict(sorted(counts.items()))


def _safe_nonnegative_int(value: Any, *, fallback: int) -> int:
    if isinstance(value, int) and value >= 0:
        return value
    return fallback if fallback >= 0 else 0


def _stable_unique_artifact_id(value: Any, used_ids: set[str]) -> str:
    base = _safe_artifact_id(value)
    candidate = base
    suffix = 2
    while candidate in used_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used_ids.add(candidate)
    return candidate


def _safe_short_text(value: Any, *, fallback: str, max_length: int = 96) -> str:
    text = str(value or fallback).strip()
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"[^a-zA-Z0-9 .,;:_/()#-]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        text = fallback
    return text[:max_length].rstrip()


def _safe_artifact_id(value: Any) -> str:
    text = str(value or "component").strip().lower()
    safe = re.sub(r"[^a-z0-9_]+", "_", text).strip("_")
    return safe or "component"


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


def _safe_diagnostic_codes(codes: list[str]) -> list[str]:
    safe_codes = []
    for code in codes:
        if not isinstance(code, str):
            continue
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", code.strip()).strip("_")
        if not safe:
            continue
        lower = safe.lower()
        if any(token in lower for token in ("key", "secret", "token", "password", "transcript", "message", "response", "log", "path", "env")):
            continue
        safe_codes.append(safe)
    return sorted(set(safe_codes))


def _requirement_diagnostic_codes(requirement: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    status = requirement.get("requirement_status")
    if isinstance(status, dict):
        value = status.get("diagnostic_codes")
        if isinstance(value, list):
            codes.extend(str(item) for item in value if isinstance(item, str))
        decision = status.get("flow_decision")
        if isinstance(decision, dict):
            for reason in decision.get("reasons", []):
                if isinstance(reason, dict) and isinstance(reason.get("code"), str):
                    codes.append(reason["code"])
    for item in requirement.get("missing_information", []):
        if isinstance(item, dict) and isinstance(item.get("code"), str):
            codes.append(item["code"])
    source = requirement.get("source")
    if isinstance(source, dict):
        compiler = source.get("provider_compiler")
        if isinstance(compiler, dict) and isinstance(compiler.get("diagnostic_codes"), list):
            codes.extend(str(item) for item in compiler["diagnostic_codes"] if isinstance(item, str))
    return _safe_diagnostic_codes(codes)


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
    diagnostic_codes: list[str] | None = None,
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
    if diagnostic_codes:
        metadata["diagnostic_codes"] = _safe_diagnostic_codes(diagnostic_codes)
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
    diagnostic_codes: list[str] | None = None,
) -> dict[str, Any]:
    diagnostic_codes = _safe_diagnostic_codes(diagnostic_codes or [])
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
        diagnostic_codes=diagnostic_codes,
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
        "diagnostic_codes": diagnostic_codes,
        "cad_ir_created": (output_path / "input_ir.json").exists(),
        "part_modeling_started": False,
        "provider_create": metadata,
        "files": _collect_files(output_path, repo_relative=True),
    }
    if requirement is not None:
        report["requirement_status"] = requirement.get("requirement_status", {})
        report["part_type"] = requirement.get("part_type")
        report["part_name"] = requirement.get("instance_name") or requirement.get("part_name") or requirement.get("part_type")
    if planning_artifact is not None:
        report["planning_gate_status"] = planning_artifact.get("flow_gate_status")
    _write_json(output_path / "report.json", report)
    _write_blocked_provider_create_report_md(output_path, report)
    files = _collect_files(output_path, repo_relative=True)
    report["files"] = files
    _write_json(output_path / "report.json", report)
    _write_provider_create_runtime(output_path, metadata, status=status)
    return {
        "status": status,
        "success": False,
        "blocked_stage": blocked_stage,
        "error_category": error_category,
        "diagnostic_codes": diagnostic_codes,
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


def _provider_normalized_design_create_metadata(
    *,
    adapter: AgentAdapter,
    provider_traces: list[dict[str, Any]],
    status: str,
    selected_candidate: str | None,
    candidate_count: int,
    assembly_plan_created: bool = False,
    assembly_plan_quality: dict[str, Any] | None = None,
    blocked_stage: str | None = None,
    diagnostic_codes: list[str] | None = None,
) -> dict[str, Any]:
    local_authority = [
        "intent.json",
        "design_brief.json",
        "candidate_plans.json",
        "selected_plan.json",
        "requirement.json",
    ]
    stages = [
        "prompt",
        "provider_extraction",
        "compile_intent",
        "compile_design_brief",
        "compile_candidate_plans",
        "select_candidate",
    ]
    artifacts = {
        "prompt": "prompt.txt",
        "intent": "intent.json",
        "design_brief": "design_brief.json",
        "candidate_plans": "candidate_plans.json",
        "selected_plan": "selected_plan.json",
        "requirement": "requirement.json",
    }
    if assembly_plan_created:
        local_authority.append("assembly_plan.json")
        stages.append("compile_assembly_plan")
        artifacts["assembly_plan"] = "assembly_plan.json"
    else:
        local_authority.extend(["planning_artifact.json", "input_ir.json", "run_ir_pipeline"])
        stages.extend(["local_requirement_planning", "planning_to_cad_ir", "run_ir_pipeline"])
        artifacts["planning_artifact"] = "planning_artifact.json"
        artifacts["input_ir"] = "input_ir.json"
    metadata = {
        "workflow": "provider_normalized_design_create",
        "version": "provider-normalized-design-create-v0.1",
        "provider_contract_mode": "extract_then_compile",
        "workflow_mode": "normalized_design_create",
        "status": status,
        "adapter": _safe_provider_identity(adapter),
        "provider_role": "extract_design_signals_only",
        "local_authority": local_authority,
        "stages": stages,
        "artifacts": artifacts,
        "selected_candidate": selected_candidate,
        "candidate_count": candidate_count,
        "assembly_plan_created": assembly_plan_created,
        "provider_request_traces": provider_traces,
    }
    if assembly_plan_quality:
        metadata["assembly_plan_quality"] = assembly_plan_quality
    if blocked_stage:
        metadata["blocked_stage"] = blocked_stage
    if diagnostic_codes:
        metadata["diagnostic_codes"] = _safe_diagnostic_codes(diagnostic_codes)
    return metadata


def _write_blocked_normalized_design_assembly_result(
    *,
    output_path: Path,
    adapter: AgentAdapter,
    provider_traces: list[dict[str, Any]],
    requirement: dict[str, Any],
    intent: dict[str, Any],
    design_brief: dict[str, Any],
    candidate_plans: list[dict[str, Any]],
    selected_plan: dict[str, Any],
    assembly_plan: dict[str, Any],
) -> dict[str, Any]:
    scope = assembly_plan.get("scope") if assembly_plan.get("scope") in {"multi_part", "assembly"} else "multi_part"
    status = (
        "blocked_assembly_generation_not_supported"
        if scope == "assembly"
        else "blocked_multi_part_generation_not_supported"
    )
    diagnostic_codes = _safe_diagnostic_codes(
        list(assembly_plan.get("diagnostic_codes", [])) + ["assembly.generation_not_supported_yet"]
    )
    assembly_plan_quality = _assembly_plan_quality_metadata(assembly_plan)
    metadata = _provider_normalized_design_create_metadata(
        adapter=adapter,
        provider_traces=provider_traces,
        status=status,
        selected_candidate=selected_plan.get("candidate_id") or selected_plan.get("label"),
        candidate_count=len(candidate_plans),
        assembly_plan_created=True,
        assembly_plan_quality=assembly_plan_quality,
        blocked_stage="assembly_planning",
        diagnostic_codes=diagnostic_codes,
    )
    trace = {
        "total_attempts": 0,
        "steps": [
            {
                "attempt": 0,
                "status": "blocked",
                "stage": "assembly_planning",
                "error_category": "assembly_generation_not_supported_yet",
            }
        ],
        "final_selected_candidate": None,
        "provider_normalized_design_create": metadata,
    }
    _write_json(output_path / "agent_trace.json", trace)
    report = {
        "success": False,
        "status": status,
        "blocked_stage": "assembly_planning",
        "error_category": "assembly_generation_not_supported_yet",
        "diagnostic_codes": diagnostic_codes,
        "part_type": requirement.get("part_type"),
        "part_name": requirement.get("instance_name") or requirement.get("part_name") or requirement.get("part_type"),
        "scope": scope,
        "requirement_status": requirement.get("requirement_status", {}),
        "assembly_plan_status": assembly_plan.get("status"),
        "assembly_plan_quality": assembly_plan_quality,
        "assembly_plan_count": assembly_plan_quality["assembly_plan_count"],
        "part_count": assembly_plan_quality["part_count"],
        "interface_count": assembly_plan_quality["interface_count"],
        "fastener_count": assembly_plan_quality["fastener_count"],
        "risk_note_count": assembly_plan_quality["risk_note_count"],
        "part_candidate_count": assembly_plan_quality["part_candidate_count"],
        "part_reference_only_count": assembly_plan_quality["part_reference_only_count"],
        "part_blocked_count": assembly_plan_quality["part_blocked_count"],
        "part_generation_strategy_counts": assembly_plan_quality["part_generation_strategy_counts"],
        "part_status_counts": assembly_plan_quality["part_status_counts"],
        "blocked_reason_codes": assembly_plan_quality["blocked_reason_codes"],
        "cad_ir_created": False,
        "part_modeling_started": False,
        "provider_normalized_design_create": metadata,
        "files": _collect_files(output_path, repo_relative=True),
    }
    _write_json(output_path / "report.json", report)
    _write_blocked_normalized_design_assembly_report_md(output_path, report, assembly_plan)
    files = _collect_files(output_path, repo_relative=True)
    report["files"] = files
    _write_json(output_path / "report.json", report)
    runtime_path = output_path / "logs" / "runtime.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime = _read_json_if_present(runtime_path)
    runtime["provider_normalized_design_create"] = metadata
    _write_json(runtime_path, runtime)
    return {
        "status": status,
        "success": False,
        "blocked_stage": "assembly_planning",
        "error_category": "assembly_generation_not_supported_yet",
        "diagnostic_codes": diagnostic_codes,
        "output_dir": str(output_path),
        "intent": intent,
        "design_brief": design_brief,
        "candidate_plans": candidate_plans,
        "selected_plan": selected_plan,
        "requirement": requirement,
        "assembly_plan": assembly_plan,
        "provider_normalized_design_create": metadata,
        "agent_trace": trace,
        "files": files,
        "report_json": str(output_path / "report.json"),
        "report_md": str(output_path / "report.md"),
    }


def _write_blocked_normalized_design_assembly_report_md(
    output_path: Path,
    report: dict[str, Any],
    assembly_plan: dict[str, Any],
) -> None:
    lines = [
        "# Provider Normalized Design Create Report",
        "",
        f"**Status:** {report.get('status')}",
        f"**Blocked stage:** {report.get('blocked_stage')}",
        f"**Scope:** `{report.get('scope')}`",
        f"**Error category:** `{report.get('error_category')}`",
        "",
        "`assembly_plan.json` is a planning artifact only. CadFlow did not generate CAD IR, "
        "multi-part CAD, assembly constraints, or STEP assembly output.",
        "",
        "## Assembly Plan",
        "",
        f"- Parts: {len(assembly_plan.get('parts', []))}",
        f"- Interfaces: {len(assembly_plan.get('interfaces', []))}",
        f"- Fasteners: {len(assembly_plan.get('fasteners', []))}",
        f"- Risk notes: {len(assembly_plan.get('risk_notes', []))}",
        f"- Candidate parts: {report.get('part_candidate_count', 0)}",
        f"- Reference-only parts: {report.get('part_reference_only_count', 0)}",
        f"- Blocked parts: {report.get('part_blocked_count', 0)}",
        "",
        "## Blocked Reasons",
        "",
    ]
    for reason in assembly_plan.get("blocked_reasons", []):
        if isinstance(reason, dict):
            lines.append(f"- `{reason.get('code', 'blocked')}`: {reason.get('message', '')}")
    (output_path / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _merge_provider_normalized_design_create_metadata(output_dir: Path, metadata: dict[str, Any]) -> None:
    trace_path = output_dir / "agent_trace.json"
    if trace_path.exists():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    else:
        trace = {}
    trace["provider_normalized_design_create"] = metadata
    trace_path.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")

    report_path = output_dir / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["provider_normalized_design_create"] = metadata
        report["files"] = _collect_files(output_dir, repo_relative=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    report_md_path = output_dir / "report.md"
    if report_md_path.exists():
        report_md = report_md_path.read_text(encoding="utf-8")
        report_md += (
            "\n## Provider Normalized Design Create\n\n"
            f"- Provider contract mode: `{metadata.get('provider_contract_mode')}`\n"
            f"- Workflow mode: `{metadata.get('workflow_mode')}`\n"
            f"- Selected candidate: `{metadata.get('selected_candidate')}`\n"
            f"- Candidate count: {metadata.get('candidate_count')}\n"
            "- Provider role: extraction/advisory only; CadFlow compiles and validates official artifacts locally.\n"
        )
        report_md_path.write_text(report_md, encoding="utf-8")
        _rewrite_report_md_files_section(output_dir)

    runtime_path = output_dir / "logs" / "runtime.json"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime = _read_json_if_present(runtime_path)
    runtime["provider_normalized_design_create"] = metadata
    _write_json(runtime_path, runtime)


def _rewrite_report_md_files_section(output_dir: Path) -> None:
    report_md_path = output_dir / "report.md"
    if not report_md_path.exists():
        return
    lines = report_md_path.read_text(encoding="utf-8").splitlines()
    files = _collect_files(output_dir, repo_relative=True)
    rewritten: list[str] = []
    index = 0
    replaced = False
    while index < len(lines):
        line = lines[index]
        rewritten.append(line)
        if line == "## Files":
            replaced = True
            index += 1
            while index < len(lines) and lines[index] == "":
                index += 1
            for label, path in files.items():
                rewritten.append(f"- {label}: `{path}`")
            while index < len(lines) and lines[index].startswith("- "):
                index += 1
            continue
        index += 1
    if replaced:
        report_md_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


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
