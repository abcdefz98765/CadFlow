"""Workflow-stage review surface view models for the local console.

The surface is presentation-only. It reads allowlisted artifacts through the
public backend route contract and reports safe action availability; it does not
mutate workflow state.
"""

from __future__ import annotations

from typing import Any

from ai_native_cad.workflow_console.backend import EDITABLE_ARTIFACTS, WorkflowConsoleBackend
from ai_native_cad.workflow_console.routes import dispatch_route
from ai_native_cad.workflow_console.stage_runner import READABLE_ARTIFACTS

REVIEW_SURFACE_ARTIFACTS = (
    "prompt.txt",
    "requirement.json",
    "requirement_clarification.json",
    "requirement_v2.json",
    "planning_artifact.json",
    "assembly_plan.json",
    "part_create_request.json",
    "part_request_review.json",
    "reviewed_part_handoff.json",
    "part_execution_request.json",
    "cad_ir_draft.json",
    "lineage.json",
    "input_ir.json",
    "report.json",
    "report.md",
    "agent_trace.json",
    "stage_review.json",
    "workflow_review.json",
    "workflow_review.md",
    "rework_decision.json",
    "logs/runtime.json",
)

STAGE_DEFINITIONS = (
    {
        "key": "requirement",
        "name": "Requirement",
        "input_artifacts": ("prompt.txt",),
        "output_artifacts": ("requirement.json", "requirement_clarification.json", "requirement_v2.json"),
        "review_stage": "requirement",
    },
    {
        "key": "clarification",
        "name": "Clarification",
        "input_artifacts": ("requirement.json",),
        "output_artifacts": ("requirement_clarification.json", "requirement_v2.json"),
        "review_stage": "requirement",
    },
    {
        "key": "planning",
        "name": "Planning",
        "input_artifacts": ("requirement_v2.json", "requirement.json"),
        "output_artifacts": ("planning_artifact.json",),
        "review_stage": "assembly_plan",
    },
    {
        "key": "assembly_plan",
        "name": "Assembly Plan",
        "input_artifacts": ("planning_artifact.json",),
        "output_artifacts": ("assembly_plan.json",),
        "review_stage": "assembly_plan",
    },
    {
        "key": "part_request",
        "name": "Part Request",
        "input_artifacts": ("assembly_plan.json",),
        "output_artifacts": ("part_create_request.json",),
        "review_stage": "part_request",
    },
    {
        "key": "part_review",
        "name": "Part Review",
        "input_artifacts": ("part_create_request.json",),
        "output_artifacts": ("part_request_review.json",),
        "review_stage": "part_review",
    },
    {
        "key": "reviewed_handoff",
        "name": "Reviewed Handoff",
        "input_artifacts": ("part_create_request.json", "part_request_review.json"),
        "output_artifacts": ("reviewed_part_handoff.json",),
        "review_stage": "handoff",
    },
    {
        "key": "cad_ir_draft",
        "name": "CAD IR Draft",
        "input_artifacts": ("part_execution_request.json",),
        "output_artifacts": ("cad_ir_draft.json",),
        "review_stage": "single_part_result",
    },
    {
        "key": "part_modeling",
        "name": "Part Modeling / Reviewed Part Create",
        "input_artifacts": ("reviewed_part_handoff.json",),
        "output_artifacts": ("part_execution_request.json", "cad_ir_draft.json", "lineage.json", "input_ir.json", "model.step", "model.stl"),
        "review_stage": "single_part_result",
    },
    {
        "key": "part_result_review",
        "name": "Part Result Review",
        "input_artifacts": ("reviewed_part_handoff.json", "lineage.json"),
        "output_artifacts": ("part_result_review.json",),
        "review_stage": "single_part_result",
    },
    {
        "key": "workflow_review",
        "name": "Workflow Review",
        "input_artifacts": ("report.json", "stage_review.json"),
        "output_artifacts": ("workflow_review.json", "workflow_review.md"),
        "review_stage": "workflow_review",
    },
    {
        "key": "rework",
        "name": "Rework",
        "input_artifacts": ("stage_review.json",),
        "output_artifacts": ("rework_decision.json",),
        "review_stage": "workflow_review",
    },
)


def build_workflow_review_surface(
    backend: WorkflowConsoleBackend,
    run_id: str | None,
    run: dict[str, Any] | None,
    *,
    root: str | None = None,
    selected_stage_id: str | None = None,
    language: str = "en",
    projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a user-facing surface for one run or an aggregated Work projection."""
    run = run if isinstance(run, dict) else {}
    projection = projection if isinstance(projection, dict) else None
    projected_contents = projection.get("artifact_contents") if projection and isinstance(projection.get("artifact_contents"), dict) else {}
    projected_stages = projection.get("stages") if projection and isinstance(projection.get("stages"), dict) else {}
    if projection:
        root_run = projection.get("root_run")
        run = root_run if isinstance(root_run, dict) else run
    artifact_names = _artifact_names(run) | set(projected_contents)
    overrides = run.get("artifact_override_summary") if isinstance(run.get("artifact_override_summary"), dict) else {}
    if projection:
        artifact_contents = projected_contents
    elif run_id:
        artifact_contents = {
            name: _read_artifact_content(backend, run_id, name, root=root)
            for name in REVIEW_SURFACE_ARTIFACTS
            if name in artifact_names
        }
    else:
        artifact_contents = {}
    summary_context = _summary_context(run, artifact_contents)
    stages = [
        _stage_card(definition, run, artifact_names, artifact_contents, summary_context, overrides, bool(run_id), language)
        for definition in STAGE_DEFINITIONS
    ]
    if projection:
        stages = [_apply_projection_to_stage(stage, projected_stages.get(stage["key"]), language) for stage in stages]
    graph_nodes = [_graph_node(stage) for stage in stages]
    workflow_graph = _workflow_graph_v2(stages, summary_context)
    selected_stage = _select_stage(stages, selected_stage_id)
    workflow_context = _workflow_context(artifact_names, artifact_contents, selected_stage, language)
    decision_layer = _decision_layer(stages, summary_context, selected_stage, artifact_names, language)
    return {
        "title": "Workflow Graph",
        "primary_concept": "Workflow / Stage / Review",
        "layout": "workflow_graph_v2_selected_stage_detail",
        "debug_graph_label": "Debug / Raw Workflow Graph",
        "workflow_graph": workflow_graph,
        "graph_nodes": graph_nodes,
        "selected_stage_id": selected_stage["key"] if selected_stage else None,
        "selected_stage": selected_stage,
        "stages": stages,
        "workflow_context": workflow_context,
        # Stable, presentation-ready contract for the Workflow Cockpit.  The
        # existing stage cards remain the detailed source; this layer makes the
        # current decision and its evidence directly consumable by any UI.
        "decision_panel": decision_layer["decision_panel"],
        "task_state": decision_layer["task_state"],
        "evidence_chain": decision_layer["evidence_chain"],
        "candidate_part_detail": decision_layer["candidate_part_detail"],
        "copy_registry": decision_layer["copy_registry"],
        "artifact_viewer": _artifact_viewer(artifact_names, artifact_contents, overrides),
        "actions": _global_actions(artifact_names, bool(run_id)),
        "work_projection": projection,
    }


def _apply_projection_to_stage(stage: dict[str, Any], projected: Any, language: str) -> dict[str, Any]:
    """Make graph and selected-stage detail consume the identical Work status."""
    if not isinstance(projected, dict):
        stage["status"] = "not_started"
        stage["short_summary"] = "Stage data unavailable"
        return stage
    inputs = _projection_artifact_refs(projected.get("input_artifacts"))
    outputs = _projection_artifact_refs(projected.get("output_artifacts"))
    raw = [item for item in [*inputs, *outputs] if item.get("present")]
    status = str(projected.get("status") or "not_started")
    summary = str(projected.get("summary") or "Stage data unavailable")
    stage.update({
        "status": status,
        "short_summary": summary,
        "human_summary": summary,
        "current_status": status.replace("_", " ").title(),
        "current_block": None,
        "input_artifacts": inputs,
        "output_artifacts": outputs,
        "important_artifacts": raw,
        "raw_artifacts": raw,
        "source_run_id": projected.get("source_run_id"),
        "source_relative_path": projected.get("source_relative_path"),
        "selected_part_id": projected.get("selected_part_id"),
        "child_run_id": projected.get("child_run_id"),
        "diagnostic_codes": projected.get("diagnostics") or [],
        "blocked_reasons": projected.get("diagnostics") or [],
        "execution_mode": projected.get("execution_mode"),
        "execution_skipped": bool(projected.get("execution_skipped")),
        "status_banner": {
            "status": status,
            "title": _stage_label(stage["key"]),
            "summary": summary,
            "consequence": "Stage data is aggregated from the Work lineage.",
            "badges": [
                _banner_badge("Artifacts", str(len(raw)), status),
                *([_banner_badge("Selected", str(projected["selected_part_id"]), "selected")] if projected.get("selected_part_id") else []),
            ],
        },
        "status_explanation": {"what_happened": [summary], "why": None},
    })
    stage["advanced"] = {**(stage.get("advanced") if isinstance(stage.get("advanced"), dict) else {}), "projection": projected, "raw_artifacts": raw}
    return _localize_stage_display(stage, language)


def _projection_artifact_refs(items: Any) -> list[dict[str, Any]]:
    result = []
    for item in _safe_list(items):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "artifact")
        present = bool(item.get("present"))
        result.append({
            "name": name,
            "present": present,
            "summary": _artifact_summary(name, item.get("content")) if present else "missing",
            "source_run_id": item.get("source_run_id"),
            "source_relative_path": item.get("source_relative_path"),
        })
    return result


def _decision_layer(
    stages: list[dict[str, Any]],
    context: dict[str, Any],
    selected_stage: dict[str, Any] | None,
    artifact_names: set[str],
    language: str,
) -> dict[str, Any]:
    """Create a compact decision/evidence view without changing workflow state."""
    assembly = context.get("assembly") if isinstance(context.get("assembly"), dict) else {}
    reviewed = context.get("reviewed") if isinstance(context.get("reviewed"), dict) else {}
    selected_id = _first_present(
        _nested(context.get("report_summary"), "final_selected_candidate"),
        _nested(reviewed.get("part_request") if isinstance(reviewed.get("part_request"), dict) else {}, "part_id"),
        assembly.get("selected_part_id"),
    )
    parts = [part for part in _safe_list(assembly.get("parts")) if isinstance(part, dict)]
    selected_part = next((part for part in parts if part.get("part_id") == selected_id), {})
    current = selected_stage or next((stage for stage in stages if stage.get("status") in {"blocked", "running", "needs_review"}), None) or (stages[-1] if stages else {})
    status = str(current.get("status") or "not_started")
    blocked = current.get("blocked_reasons") if isinstance(current.get("blocked_reasons"), list) else []
    evidence = []
    for stage in stages:
        for artifact in stage.get("important_artifacts", []):
            if isinstance(artifact, dict) and artifact.get("present"):
                evidence.append({"stage": stage.get("key"), "artifact": artifact.get("name"), "role": "decision evidence"})
    evidence = evidence[:8]
    cad_ir = context.get("cad_ir_draft") if isinstance(context.get("cad_ir_draft"), dict) else {}
    generic = _nested(cad_ir, "source", "normalization")
    child_runs = context.get("child_runs") if isinstance(context.get("child_runs"), list) else []
    child = child_runs[0] if child_runs and isinstance(child_runs[0], dict) else {}
    generated_evidence = (
        ("cad_ir_draft.json", "cad_ir_draft.json" in artifact_names),
        ("input_ir.json", "input_ir.json" in child.get("artifacts", [])),
        ("model.step", "model.step" in child.get("downloadables", [])),
        ("model.stl", "model.stl" in child.get("downloadables", [])),
    )
    for name, present in generated_evidence:
        if present and not any(item.get("artifact") == name for item in evidence):
            evidence.append({"stage": "part_modeling", "artifact": name, "role": "generated single-part evidence"})
    is_generic_link = cad_ir.get("part_type") == "link_like_part" and cad_ir.get("geometry_family") == "elongated_plate_with_end_holes"
    return {
        "task_state": {"status": status, "current_stage": current.get("key"), "selected_part_id": selected_id, "blocked_reasons": blocked},
        "decision_panel": {
            "decision": ("Review the generated generic link-like concept part." if is_generic_link else current.get("next_recommended_action") or current.get("current_status") or "Review the selected stage."),
            "status": status,
            "owner_stage": current.get("key"),
            "selected_part_id": selected_id,
            "rationale": current.get("current_block") or current.get("why_it_matters") or "",
            "scope": "single_generic_concept_part" if is_generic_link else None,
            "assembly_generated": False if is_generic_link else None,
        },
        "evidence_chain": evidence,
        "candidate_part_detail": {
            "part_id": selected_id,
            "role": selected_part.get("role"),
            "status": selected_part.get("part_status") or selected_part.get("status"),
            "supported_candidate": selected_part.get("supported_candidate") is True,
            "reference_only": selected_part.get("reference_only") is True,
            "brief": selected_part.get("part_brief"),
            "generic_family_normalization": generic,
            "part_type": cad_ir.get("part_type"),
            "geometry_family": cad_ir.get("geometry_family"),
        },
        "copy_registry": _cockpit_copy_registry(language),
    }


def _cockpit_copy_registry(language: str) -> dict[str, str]:
    if language == "zh":
        return {"decision": "当前决策", "task_state": "任务状态", "evidence_chain": "证据链", "candidate_part": "候选零件详情", "no_fallback": "未回退到 mounting_plate"}
    return {"decision": "Current decision", "task_state": "Task state", "evidence_chain": "Evidence chain", "candidate_part": "Candidate part detail", "no_fallback": "No fallback to mounting_plate"}


def _stage_card(
    definition: dict[str, Any],
    run: dict[str, Any],
    artifact_names: set[str],
    contents: dict[str, Any],
    context: dict[str, Any],
    overrides: dict[str, Any],
    has_run: bool,
    language: str,
) -> dict[str, Any]:
    key = definition["key"]
    input_artifacts = [_artifact_ref(name, artifact_names, contents) for name in definition["input_artifacts"]]
    output_artifacts = [_artifact_ref(name, artifact_names, contents) for name in definition["output_artifacts"]]
    raw_artifacts = [
        item
        for item in (*input_artifacts, *output_artifacts)
        if item["present"] and item["name"] in REVIEW_SURFACE_ARTIFACTS
    ]
    status = _stage_status(key, input_artifacts + output_artifacts, run, contents, overrides)
    actions = _stage_actions(key, definition["review_stage"], artifact_names, has_run)
    report_summary = _report_summary(key, context)
    gate_decision = _gate_decision(key, run, contents)
    diagnostic_codes = _diagnostic_codes(key, run, contents)
    blocked_reasons = _blocked_reasons(key, run, contents)
    agent_identity = _agent_identity(run)
    action_groups = _action_groups(key, status, actions, report_summary, artifact_names, has_run)
    status_banner = _status_banner(key, status, report_summary, blocked_reasons, raw_artifacts)
    detail_cards = _detail_cards(key, status, report_summary, blocked_reasons, raw_artifacts, overrides, actions)
    card = {
        "key": key,
        "stage_id": key,
        "stage_name": definition["name"],
        "status": status,
        "short_summary": _short_stage_summary(key, status, report_summary, blocked_reasons),
        "human_summary": _human_stage_summary(key, status, report_summary, gate_decision, blocked_reasons),
        "why_it_matters": _why_it_matters(key, report_summary),
        "current_block": _current_block(key, status, report_summary, blocked_reasons),
        "current_status": _current_status_text(key, status, blocked_reasons),
        "key_decisions_human": _key_decisions_human(key, report_summary, gate_decision, overrides),
        "progress_summary": _progress_summary(key, status, report_summary),
        "limitations_summary": _limitations_summary(key, status, report_summary, blocked_reasons),
        "safety_summary": _safety_summary(key, status, overrides),
        "next_recommended_action": _next_recommended_action(key, status, actions, report_summary, blocked_reasons),
        "status_banner": status_banner,
        "status_explanation": {
            "what_happened": _what_happened(key, status, report_summary)[:2],
            "why": _current_block(key, status, report_summary, blocked_reasons),
        },
        "detail_cards": detail_cards,
        "action_groups": action_groups,
        # Kept only for Advanced / Debug compatibility. The selected-stage UI uses
        # the humanized fields above rather than these internal summaries.
        "key_decisions": _key_decisions(key, report_summary, gate_decision, input_artifacts, output_artifacts, overrides),
        "input_artifacts": input_artifacts,
        "output_artifacts": output_artifacts,
        "important_artifacts": _important_artifacts(input_artifacts + output_artifacts, overrides),
        "agent_identity": agent_identity,
        "gate_decision": gate_decision,
        "diagnostic_codes": diagnostic_codes,
        "blocked_reasons": blocked_reasons,
        "report_summary": report_summary,
        "available_actions": actions,
        "raw_artifacts": raw_artifacts,
        "advanced": {
            "summary_data": report_summary,
            "raw_artifacts": raw_artifacts,
        },
        "debug": {
            "gate_decision": gate_decision,
            "diagnostic_codes": diagnostic_codes,
            "blocked_reasons": blocked_reasons,
            "agent_identity": agent_identity,
        },
        "override_present": any(_canonical_name(item["name"]) in overrides for item in (*input_artifacts, *output_artifacts)),
    }
    return _localize_stage_display(card, language)


def _graph_node(stage: dict[str, Any]) -> dict[str, Any]:
    raw_artifacts = stage.get("raw_artifacts") if isinstance(stage.get("raw_artifacts"), list) else []
    actions = stage.get("available_actions") if isinstance(stage.get("available_actions"), list) else []
    primary_artifact = next((item.get("name") for item in raw_artifacts if isinstance(item, dict) and item.get("present")), None)
    primary_action = next((item.get("label") for item in actions if isinstance(item, dict) and item.get("enabled")), None)
    return {
        "stage_id": stage.get("key"),
        "label": stage.get("stage_name"),
        "status": stage.get("status") or "not_started",
        "short_summary": stage.get("short_summary") or "",
        "source_artifact_count": len(raw_artifacts),
        "selected_part_id": stage.get("selected_part_id"),
        "primary_artifact": primary_artifact,
        "primary_action": primary_action,
        "has_override": bool(stage.get("override_present")),
        "has_debug": bool(stage.get("debug")),
        "hover": {
            "title": _nested(stage.get("status_banner"), "title") or stage.get("stage_name"),
            "summary": stage.get("short_summary") or "",
            "reason": stage.get("current_block") or stage.get("why_it_matters") or "",
            "consequence": _nested(stage.get("status_banner"), "consequence") or "",
            "recommended_action": stage.get("next_recommended_action") or "",
        },
    }


def _localize_stage_display(card: dict[str, Any], language: str) -> dict[str, Any]:
    """Translate only presentation fields; artifacts and action contracts remain unchanged."""
    card["display_language"] = "zh" if language == "zh" else "en"
    if language != "zh":
        return card
    key = str(card.get("key") or "")
    summary = card.get("report_summary") if isinstance(card.get("report_summary"), dict) else {}
    part_id = _active_part_id(summary) or "当前零件"
    if key in {"cad_ir_draft", "part_modeling"} and summary.get("blocked_cad_ir_validation"):
        card["status_banner"] = {
            "status": "blocked",
            "title": "CAD IR 验证已阻断",
            "summary": f"CadFlow 已为 {part_id} 创建 CAD IR 草稿，但当前 CAD 后端尚不支持这一零件类型。",
            "consequence": "未创建子 input_ir.json、STEP 或 STL 文件。",
            "badges": [
                _banner_badge("零件", part_id, "selected"),
                _banner_badge("草稿", "已生成", "completed"),
                _banner_badge("CAD 输出", "无", "not_started"),
                _banner_badge("回退", "无", "needs_review"),
            ],
        }
        card["detail_cards"] = [
            {"title": "发生了什么", "items": [f"{part_id} 已从装配计划中选定。", "CadIrAgent 已生成 cad_ir_draft.json。", "验证在模型生成前停止。"]},
            {"title": "为什么停止", "items": ["草稿使用了当前后端尚不能执行的零件类型。", "这是能力限制，不是运行损坏。"]},
            {"title": "建议下一步", "items": ["打开 cad_ir_draft.json 检查或覆盖草稿。", "若该阻断符合预期，保存阶段评审。", "后续可增加通用连杆类 CAD IR 支持。"]},
            {"title": "产物状态", "items": [_status_item("cad_ir_draft.json", "已生成"), _status_item("子 input_ir.json", "未创建"), _status_item("model.step", "未创建"), _status_item("model.stl", "未创建")]},
            {"title": "评审状态", "items": ["没有可批准的 CAD 结果。", "可将此阶段标记为阻断，或记录为预期结果。"]},
            {"title": "安全保护", "items": ["CadFlow 没有导出未经验证的模型。", "没有回退到 mounting_plate。"]},
        ]
        card["status_explanation"] = {
            "what_happened": [f"{part_id} 已从装配计划中选定。", "CadIrAgent 已生成 cad_ir_draft.json。"],
            "why": "草稿使用了当前后端尚不能执行的零件类型。",
        }
    elif key in {"planning", "assembly_plan"}:
        selected = summary.get("selected_candidate") or "未选择"
        card["status_banner"] = {
            "status": card.get("status") or "completed",
            "title": "装配计划已完成",
            "summary": f"CadFlow 已将 {summary.get('object_goal') or '该需求'} 拆分为可打印零件候选和参考组件。",
            "consequence": "暂不支持完整装配 CAD，因此工作流继续处理一个选定零件。",
            "badges": [
                _banner_badge("候选", str(len(summary.get("candidate_parts") or [])), "completed"),
                _banner_badge("参考件", str(len(summary.get("reference_components") or [])), "reference_only"),
                _banner_badge("已选零件", str(selected), "selected" if selected != "未选择" else "not_started"),
                _banner_badge("下游", "CAD IR 已阻断" if _has_blocked_cad_ir(summary) else "等待结果", "blocked" if _has_blocked_cad_ir(summary) else "needs_review"),
            ],
        }
        card["detail_cards"] = [
            {"title": "发生了什么", "items": ["该需求按装配级任务处理。", "已识别可生成的零件候选。", "参考组件只用于装配上下文。"]},
            {"title": "为什么重要", "items": ["CadFlow 还不能生成完整装配 CAD。", "经评审的单零件流程可让一个选定零件安全继续。"]},
            {"title": "建议下一步", "items": ["打开 CAD IR 草稿查看当前阻断。", f"只有在 {selected} 不是首个测试零件时才编辑装配计划。", "仅在当前请求缺失或已过期时创建零件请求。"]},
            {"title": "关键决策", "items": [f"需求来源：{summary.get('requirement_source') or '原始需求'}。", "路径：装配拆分。", f"选定零件：{selected}。"]},
            {"title": "候选零件", "kind": "chips", "items": [_chip_item(part, "selected" if part == selected else "candidate") for part in summary.get("candidate_parts") or []]},
            {"title": "参考通道", "kind": "chips", "items": [_chip_item(part, "reference_only") for part in summary.get("reference_components") or []]},
        ]
        card["status_explanation"] = {
            "what_happened": ["该需求按装配级任务处理。", "已识别可生成的零件候选。"],
            "why": "CadFlow 还不能生成完整装配 CAD，因此只让一个选定零件继续。",
        }
    elif key == "requirement" and card.get("status") == "completed":
        source = summary.get("requirement_source")
        card["status_banner"] = {
            "status": "completed",
            "title": "需求澄清已完成" if source == "requirement_v2.json" else "需求已完成",
            "summary": f"CadFlow 已将需求理解为 {summary.get('object_goal') or summary.get('part_type') or '当前 CAD 工作'}。",
            "consequence": f"规划将使用 {source}。" if source else "规划可以使用这份需求。",
            "badges": [_banner_badge("范围", _human_scope(summary.get("intent_scope")), "completed"), _banner_badge("需求版本", "v2" if source == "requirement_v2.json" else "原始", "completed"), _banner_badge("假设", str(len(summary.get("assumptions") or [])), "needs_review")],
        }
        card["detail_cards"] = [
            {"title": "建议下一步", "items": ["查看规划结果。", "仅当范围或关键尺寸不正确时编辑 requirement_v2.json。"]},
        ]
        card["status_explanation"] = {
            "what_happened": ["CadFlow 已整理可供规划使用的需求。"],
            "why": "这份需求为后续的规划和零件决策提供统一依据。",
        }
    stage_names = {
        "Requirement": "需求", "Clarification": "澄清", "Planning": "规划", "Assembly Plan": "装配计划",
        "Part Request": "零件请求", "Part Review": "零件评审", "Reviewed Handoff": "已评审交接",
        "CAD IR Draft": "CAD IR 草稿", "Part Modeling / Reviewed Part Create": "零件建模 / 已评审零件创建",
        "Part Result Review": "零件结果评审", "Workflow Review": "工作流评审", "Rework": "返工",
    }
    card["stage_name"] = stage_names.get(card.get("stage_name"), card.get("stage_name"))
    _localize_action_groups(card.get("action_groups"))
    return card


def _localize_action_groups(groups: Any) -> None:
    if not isinstance(groups, dict):
        return
    labels = {
        "View CAD IR Draft": "查看 CAD IR 草稿", "Open CAD IR Draft": "打开 CAD IR 草稿", "Save Stage Review": "保存阶段评审",
        "Mark Blocked": "标记为阻断", "Create / Refresh Workflow Review": "创建 / 刷新工作流评审",
        "Edit Assembly Plan": "编辑装配计划", "Create Part Request": "创建零件请求", "Approve Single Part Result": "批准单零件结果",
        "Create Reviewed Part": "创建经评审的零件", "Mark Needs Revision": "标记需要修改", "View raw diagnostics": "查看原始诊断",
    }
    reasons = {
        "No STEP/STL was generated, so there is no part result to approve.": "未生成 STEP/STL，因此没有可批准的零件结果。",
        "This reviewed-part create already ran and blocked at CAD IR validation.": "该经评审的零件创建已执行，并在 CAD IR 验证处阻断。",
        "Use the Stage Review form to provide target rework stage and requested changes.": "请在阶段评审表单中指定返工目标阶段和修改要求。",
        "A part request already exists for the selected part.": "当前选定零件已存在零件请求。",
    }
    for group in groups.values():
        if not isinstance(group, list):
            continue
        for action in group:
            if isinstance(action, dict):
                action["label"] = labels.get(action.get("label"), action.get("label"))
                if action.get("disabled_reason") in reasons:
                    action["disabled_reason"] = reasons[action["disabled_reason"]]


def _workflow_graph_v2(stages: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
    """Build the user-facing assembly topology, separate from the raw stage order."""
    by_key = {str(stage.get("key")): stage for stage in stages}
    spine_keys = ("requirement", "clarification", "planning", "assembly_plan")
    pipeline_keys = (
        "part_request",
        "part_review",
        "reviewed_handoff",
        "cad_ir_draft",
        "part_modeling",
        "part_result_review",
    )
    tail_keys = ("workflow_review", "rework")
    assembly = context.get("assembly") if isinstance(context.get("assembly"), dict) else {}
    reviewed = context.get("reviewed") if isinstance(context.get("reviewed"), dict) else {}
    selected_part_id = _first_present(
        _nested(context.get("report_summary"), "final_selected_candidate"),
        _nested(reviewed.get("part_request"), "part_id"),
        _nested(reviewed.get("reviewed_part_handoff"), "part_id"),
        _nested(reviewed.get("lineage"), "part_id"),
    )
    candidates = [_part_candidate_node(part, selected_part_id) for part in _safe_list(assembly.get("parts")) if isinstance(part, dict)]
    generated_candidates = [item for item in candidates if not item["reference_only"]]
    reference_components = [item for item in candidates if item["reference_only"]]
    return {
        "topology": "stage_spine_part_branch",
        "stage_spine": [_graph_node(by_key[key]) for key in spine_keys if key in by_key],
        "part_candidates": generated_candidates,
        "reference_lane": reference_components,
        "selected_part_id": selected_part_id,
        "selected_part_pipeline": [_graph_node(by_key[key]) for key in pipeline_keys if key in by_key],
        "review_tail": [_graph_node(by_key[key]) for key in tail_keys if key in by_key],
    }


def _part_candidate_node(part: dict[str, Any], selected_part_id: Any) -> dict[str, Any]:
    part_id = str(part.get("part_id") or "unnamed part")
    reference_only = bool(part.get("reference_only")) or part.get("generation_strategy") == "reference_only" or part.get("part_status") == "reference_only"
    supported = bool(part.get("supported_candidate"))
    selected = bool(selected_part_id and str(selected_part_id) == part_id)
    raw_status = str(part.get("part_status") or "candidate")
    if reference_only:
        status = "reference_only"
    elif selected:
        status = "selected"
    elif raw_status == "blocked" or part.get("blocked_reasons"):
        status = "blocked"
    elif raw_status in {"generated", "failed"}:
        status = raw_status
    else:
        status = "candidate"
    role = str(part.get("role") or "assembly component")
    if status == "selected":
        summary = f"Selected for the reviewed-part pipeline as {role}."
    elif status == "reference_only":
        summary = f"Used as a reference component; CadFlow will not generate this part."
    elif status == "blocked":
        summary = f"{role.title()} needs design review before it can enter the part pipeline."
    elif supported:
        summary = f"{role.title()} is a supported candidate for part generation."
    else:
        summary = f"{role.title()} is listed in the assembly but is not ready for generation."
    return {
        "part_id": part_id,
        "role": role,
        "brief": str(part.get("brief") or part.get("description") or role),
        "status": status,
        "supported_candidate": supported,
        "selected": selected,
        "current": selected,
        "reference_only": reference_only,
        "short_summary": summary,
    }


def _select_stage(stages: list[dict[str, Any]], selected_stage_id: str | None) -> dict[str, Any] | None:
    if not stages:
        return None
    if selected_stage_id:
        for stage in stages:
            if stage.get("key") == selected_stage_id:
                return stage
    for stage in stages:
        if stage.get("status") in {"blocked", "failed", "needs_review", "user_modified", "stale"}:
            return stage
    completed = [stage for stage in stages if stage.get("status") != "not_started"]
    return completed[-1] if completed else stages[0]


def _short_stage_summary(key: str, status: str, summary: dict[str, Any], blocked_reasons: list[Any]) -> str:
    if key in {"cad_ir_draft", "part_modeling"} and summary.get("blocked_cad_ir_validation"):
        return "CAD IR draft was created, but validation stopped downstream model generation."
    if status == "blocked":
        return f"{_stage_label(key)} is blocked and needs review."
    if status == "user_modified":
        return f"{_stage_label(key)} uses an active user override."
    if status == "not_started":
        return f"{_stage_label(key)} has not started yet."
    if key in {"planning", "assembly_plan"} and summary.get("candidate_parts"):
        return "Planning identified generated candidates and reference components."
    if blocked_reasons:
        return f"{_stage_label(key)} has review notes or limitations."
    return f"{_stage_label(key)} is {status.replace('_', ' ')}."


def _human_stage_summary(
    key: str,
    status: str,
    summary: dict[str, Any],
    gate_decision: Any,
    blocked_reasons: list[Any],
) -> str:
    if key == "requirement":
        scope = summary.get("intent_scope") or "unspecified scope"
        goal = summary.get("object_goal") or summary.get("part_type") or "the requested CAD work"
        if _gate_action(gate_decision) == "proceed_with_assumptions":
            return f"Requirement completed with assumptions. CadFlow understood this as {scope} work for {goal}."
        if status == "blocked":
            return "Requirement needs user clarification before downstream planning can proceed."
        return f"CadFlow captured the requirement for {goal} with {scope}."
    if key == "clarification":
        if summary.get("requirement_source") == "requirement_v2.json":
            return "Clarification has been applied and downstream stages can use requirement_v2.json."
        return "No applied clarification artifact is present yet."
    if key in {"planning", "assembly_plan"}:
        count = len(summary.get("candidate_parts") or [])
        references = len(summary.get("reference_components") or [])
        selected = summary.get("selected_candidate")
        selection = f" {selected} is the part currently moving through review." if selected else ""
        return f"The assembly was broken into {count} part candidate{'s' if count != 1 else ''} and {references} reference component{'s' if references != 1 else ''}.{selection}"
    if key in {"part_request", "part_review", "reviewed_handoff"}:
        request = summary.get("part_create_request") if isinstance(summary.get("part_create_request"), dict) else {}
        part_id = request.get("part_id") or _nested(summary.get("reviewed_part_handoff"), "part_id") or "the selected part"
        return f"This stage prepares and reviews the single-part handoff for {part_id}."
    if key in {"cad_ir_draft", "part_modeling"} and summary.get("blocked_cad_ir_validation"):
        part_id = _nested(summary.get("part_create_request"), "part_id") or _nested(summary.get("reviewed_part_handoff"), "part_id") or "the selected part"
        return (
            f"Blocked at CAD IR validation. The agent produced a CAD IR draft for {part_id}, "
            "but the current CAD backend does not support this part type yet. No child input_ir.json, STEP, or STL was created."
        )
    if key == "part_result_review":
        return "Part result review checks whether reviewed part artifacts are present and acceptable."
    if key == "workflow_review":
        overall = summary.get("overall_status") or status
        return f"Workflow review summarizes readiness as {str(overall).replace('_', ' ')} and records remaining risks."
    if key == "rework":
        return "Rework is available only after a saved stage review requests revision."
    if blocked_reasons:
        return f"{_stage_label(key)} has limitations that need review."
    return f"{_stage_label(key)} is {status.replace('_', ' ')}."


def _current_status_text(key: str, status: str, blocked_reasons: list[Any]) -> str:
    if status == "blocked":
        reason = _human_block_summary(blocked_reasons)
        return f"Blocked at {_stage_label(key)}. {reason}" if reason else f"Blocked at {_stage_label(key)}."
    if status == "not_started":
        return "Not started."
    if status == "user_modified":
        return "Using a validated user override."
    return status.replace("_", " ").title()


def _why_it_matters(key: str, summary: dict[str, Any]) -> str:
    messages = {
        "requirement": "This gives every downstream decision a shared description of the requested work.",
        "clarification": "Clarification prevents the workflow from silently making important design choices for you.",
        "planning": "This determines whether the request is handled as one part or as an assembly with separate responsibilities.",
        "assembly_plan": "This separates parts CadFlow can work on from components that remain references or need design review.",
        "part_request": "This selects one assembly part and records the information needed to prepare it for review.",
        "part_review": "This is the checkpoint before the selected part is handed to the downstream modeling workflow.",
        "reviewed_handoff": "This makes the reviewed part definition the source for the downstream modeling workflow.",
        "cad_ir_draft": "This checks that the selected part can be expressed in the CAD representation used by the current backend.",
        "part_modeling": "This is where the reviewed part would produce CAD artifacts after validation succeeds.",
        "part_result_review": "This confirms whether the generated part artifacts are ready for inspection.",
        "workflow_review": "This combines part-level results into the current readiness picture for the work.",
        "rework": "This records and applies a requested revision without overwriting the prior run.",
    }
    return messages.get(key, "This stage records a workflow decision that affects the next stage.")


def _current_block(key: str, status: str, summary: dict[str, Any], blocked_reasons: list[Any]) -> str | None:
    if key in {"cad_ir_draft", "part_modeling"} and summary.get("blocked_cad_ir_validation"):
        return "The draft uses a part type the backend cannot execute yet. This is a capability limit, not a corrupted run."
    if status != "blocked":
        return None
    reason = _human_block_summary(blocked_reasons)
    if reason:
        return reason
    if key in {"planning", "assembly_plan"}:
        return "The assembly needs review before another candidate can enter the part pipeline."
    return "This stage needs review before the workflow can continue."


def _key_decisions_human(key: str, summary: dict[str, Any], gate_decision: Any, overrides: dict[str, Any]) -> list[str]:
    decisions: list[str] = []
    if key in {"requirement", "clarification"}:
        goal = summary.get("object_goal") or summary.get("part_type")
        if goal:
            decisions.append(f"CadFlow will work toward: {goal}.")
        if summary.get("assumptions"):
            decisions.append("The requirement includes visible working assumptions that can be reviewed before proceeding.")
    if key in {"planning", "assembly_plan"}:
        if summary.get("requirement_source"):
            decisions.append(f"Requirement source: {summary['requirement_source']}.")
        decisions.append("Route: assembly decomposition.")
        if summary.get("selected_candidate"):
            decisions.append(f"Selected part: {summary['selected_candidate']}.")
    if key in {"part_request", "part_review", "reviewed_handoff", "cad_ir_draft", "part_modeling", "part_result_review"}:
        part_id = _nested(summary.get("part_create_request"), "part_id") or _nested(summary.get("reviewed_part_handoff"), "part_id")
        if part_id:
            decisions.append(f"The active part is {part_id}.")
    if _gate_action(gate_decision) == "proceed_with_assumptions":
        decisions.append("CadFlow proceeded with the recorded assumptions rather than requesting more information.")
    if overrides:
        decisions.append("A validated user override is active; downstream decisions use that reviewed version.")
    return decisions[:4]


def _progress_summary(key: str, status: str, summary: dict[str, Any]) -> list[str]:
    if key in {"planning", "assembly_plan"}:
        selected = summary.get("selected_candidate")
        items = ["Assembly decomposition is available for review."]
        if selected:
            items.append(f"{selected} has entered the selected-part pipeline.")
        return items
    if key in {"cad_ir_draft", "part_modeling"}:
        items = ["A CAD IR draft is available."] if summary.get("blocked_cad_ir_validation") else []
        if summary.get("model_step_status") == "present":
            items.append("A STEP model is available for inspection.")
        if summary.get("model_stl_status") == "present":
            items.append("An STL model is available for inspection.")
        return items
    if status == "not_started":
        return ["This stage has not started yet."]
    return [f"{_stage_label(key)} has reached {status.replace('_', ' ')}."]


def _limitations_summary(key: str, status: str, summary: dict[str, Any], blocked_reasons: list[Any]) -> list[str]:
    if key in {"cad_ir_draft", "part_modeling"} and summary.get("blocked_cad_ir_validation"):
        return ["No downstream CAD model files were created because validation did not accept the draft."]
    if status == "blocked":
        reason = _human_block_summary(blocked_reasons)
        return [reason] if reason else ["This stage needs review before it can continue."]
    if key in {"planning", "assembly_plan"} and summary.get("reference_components"):
        return ["Reference components are tracked for fit and context, but are not generated by this workflow."]
    return []


def _safety_summary(key: str, status: str, overrides: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    if overrides:
        messages.append("Any user edits are stored as validated overrides; original agent artifacts remain unchanged.")
    if key in {"cad_ir_draft", "part_modeling"} and status == "blocked":
        messages.append("CadFlow did not export an unvalidated model.")
        messages.append("No fallback to mounting_plate occurred.")
    return messages


def _recommended_step_items(key: str, status: str, summary: dict[str, Any]) -> list[str]:
    if key in {"cad_ir_draft", "part_modeling"} and summary.get("blocked_cad_ir_validation"):
        return [
            "Open cad_ir_draft.json to inspect or override the draft.",
            "Save Stage Review if this block is expected.",
            "Future work: add a generic link-like CAD IR family.",
        ]
    if key in {"planning", "assembly_plan"} and summary.get("selected_candidate"):
        return [
            "Open CAD IR Draft to inspect the current block.",
            f"Edit Assembly Plan only if {summary['selected_candidate']} is not the part to test first.",
            "Create Part Request only if the current request is missing or stale.",
        ]
    if key == "requirement" and status == "completed":
        return ["Review Planning.", "Edit requirement_v2.json only if the scope or key dimensions are wrong."]
    return []


def _status_banner(
    key: str,
    status: str,
    summary: dict[str, Any],
    blocked_reasons: list[Any],
    raw_artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    part_id = _active_part_id(summary)
    artifact_names = {str(item.get("name")) for item in raw_artifacts if isinstance(item, dict) and item.get("present")}
    if key in {"cad_ir_draft", "part_modeling"} and summary.get("blocked_cad_ir_validation"):
        return {
            "status": "blocked",
            "title": "Blocked at CAD IR validation",
            "summary": f"CadFlow created a CAD IR draft for {part_id or 'the selected part'}, but this part family is not supported by the current CAD backend yet.",
            "consequence": "No child input_ir.json, STEP, or STL was created.",
            "badges": [
                _banner_badge("Part", part_id or "selected part", "selected"),
                _banner_badge("Draft", "present" if "cad_ir_draft.json" in artifact_names else "absent", "completed" if "cad_ir_draft.json" in artifact_names else "not_started"),
                _banner_badge("CAD output", "available" if _has_model_export(summary) else "none", "completed" if _has_model_export(summary) else "not_started"),
                _banner_badge("Fallback", "none" if summary.get("no_mounting_plate_fallback") else "not applicable", "needs_review"),
            ],
        }
    if key in {"planning", "assembly_plan"}:
        candidate_count = len(summary.get("candidate_parts") or [])
        reference_count = len(summary.get("reference_components") or [])
        selected = summary.get("selected_candidate")
        return {
            "status": status,
            "title": "Assembly plan completed",
            "summary": f"CadFlow decomposed {summary.get('object_goal') or 'the request'} into printable part candidates and reference components.",
            "consequence": (
                "Full assembly CAD is not supported yet, so the workflow continues with one selected part."
                if selected else "Choose a supported candidate before the reviewed-part pipeline can continue."
            ),
            "badges": [
                _banner_badge("Candidates", str(candidate_count), "completed"),
                _banner_badge("References", str(reference_count), "reference_only"),
                _banner_badge("Selected", str(selected or "not selected"), "selected" if selected else "not_started"),
                _banner_badge("Downstream", "CAD IR blocked" if _has_blocked_cad_ir(summary) else "awaiting part result", "blocked" if _has_blocked_cad_ir(summary) else "needs_review"),
            ],
        }
    if key == "requirement" and status == "completed":
        source = summary.get("requirement_source")
        return {
            "status": status,
            "title": "Requirement completed with clarification" if source == "requirement_v2.json" else "Requirement completed",
            "summary": f"CadFlow understood the request as {summary.get('object_goal') or summary.get('part_type') or 'the requested CAD work'}.",
            "consequence": f"Planning used {source}." if source else "Planning can use this requirement.",
            "badges": [
                _banner_badge("Scope", _human_scope(summary.get("intent_scope")), "completed"),
                _banner_badge("Requirement", "v2" if source == "requirement_v2.json" else "original", "completed"),
                _banner_badge("Assumptions", str(len(summary.get("assumptions") or [])), "needs_review"),
            ],
        }
    title = _banner_title(key, status)
    consequence = _current_block(key, status, summary, blocked_reasons) or "The workflow can use this stage as input for the next available step."
    return {
        "status": status,
        "title": title,
        "summary": _human_stage_summary(key, status, summary, None, blocked_reasons),
        "consequence": consequence,
        "badges": [_banner_badge("Stage", _stage_label(key), status)],
    }


def _detail_cards(
    key: str,
    status: str,
    summary: dict[str, Any],
    blocked_reasons: list[Any],
    raw_artifacts: list[dict[str, Any]],
    overrides: dict[str, Any],
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cards = [
        {"title": "What happened", "items": _what_happened(key, status, summary)},
        {"title": "Why it stopped" if _current_block(key, status, summary, blocked_reasons) else "Why it matters", "items": [_current_block(key, status, summary, blocked_reasons) or _why_it_matters(key, summary)]},
        {"title": "Recommended next step", "items": _recommended_step_items(key, status, summary)},
        {"title": "Artifact status", "items": _artifact_status_items(key, summary, raw_artifacts)},
        {"title": "Key decisions", "items": _key_decisions_human(key, summary, None, overrides)},
        {"title": "Review state", "items": _review_state_items(key, status, summary, blocked_reasons, overrides)},
    ]
    safety = _safety_summary(key, status, overrides)
    if safety:
        cards.append({"title": "Safety guardrails", "items": safety})
    if key in {"planning", "assembly_plan"}:
        cards.extend([
            {"title": "Candidate parts", "kind": "chips", "items": [_chip_item(part, "selected" if part == summary.get("selected_candidate") else "candidate") for part in summary.get("candidate_parts") or []]},
            {"title": "Reference lane", "kind": "chips", "items": [_chip_item(part, "reference_only") for part in summary.get("reference_components") or []]},
        ])
    return [card for card in cards if card.get("items")]


def _action_groups(
    key: str,
    status: str,
    actions: list[dict[str, Any]],
    summary: dict[str, Any],
    artifact_names: set[str],
    has_run: bool,
) -> dict[str, list[dict[str, Any]]]:
    prepared = [dict(action) for action in actions]
    blocked_cad_ir = key in {"cad_ir_draft", "part_modeling"} and bool(summary.get("blocked_cad_ir_validation"))
    if blocked_cad_ir:
        for action in prepared:
            if action.get("key") == "approve_stage":
                action["enabled"] = False
                action["disabled_reason"] = "No STEP/STL was generated, so there is no part result to approve."
            if action.get("key") == "reviewed_part_create":
                action["enabled"] = False
                action["label"] = "Create Reviewed Part"
                action["disabled_reason"] = "This reviewed-part create already ran and blocked at CAD IR validation."
        primary = []
        if "cad_ir_draft.json" in artifact_names:
            primary.append(_presentation_action("view_cad_ir_draft", "View CAD IR Draft", "cad_ir_draft.json"))
        primary.extend(action for action in prepared if action.get("key") == "save_stage_review")
        secondary = [action for action in prepared if action.get("key") == "mark_blocked"]
        secondary.append(_action("create_workflow_review", "Create / Refresh Workflow Review", has_run, None if has_run else "Select a run first.", {"backend_action": "create_workflow_review"}))
        disabled = [action for action in prepared if not action.get("enabled")]
        advanced = [_presentation_action("view_diagnostics", "View raw diagnostics", None)]
        return {"primary": primary, "secondary": secondary, "disabled": disabled, "advanced": advanced}
    if key in {"planning", "assembly_plan"} and summary.get("selected_candidate"):
        primary = []
        if "cad_ir_draft.json" in artifact_names:
            primary.append(_presentation_action("view_cad_ir_draft", "Open CAD IR Draft", "cad_ir_draft.json"))
        if "assembly_plan.json" in artifact_names:
            primary.append(_presentation_action("edit_assembly_plan", "Edit Assembly Plan", "assembly_plan.json"))
        secondary = [action for action in prepared if action.get("key") == "save_stage_review"]
        for action in prepared:
            if action.get("key") == "create_part_request" and action.get("enabled"):
                action["enabled"] = False
                action["disabled_reason"] = "A part request already exists for the selected part."
        disabled = [action for action in prepared if not action.get("enabled")]
        return {"primary": primary, "secondary": secondary, "disabled": disabled, "advanced": [_presentation_action("view_diagnostics", "View raw diagnostics", None)]}
    primary_keys = {"apply_requirement_clarification", "create_part_request", "part_request", "part_review", "reviewed_handoff", "reviewed_part_create", "part_result_review", "create_workflow_review", "run_rework"}
    primary = [action for action in prepared if action.get("enabled") and action.get("key") in primary_keys][:2]
    secondary = [action for action in prepared if action.get("enabled") and action not in primary]
    disabled = [action for action in prepared if not action.get("enabled")]
    return {"primary": primary, "secondary": secondary, "disabled": disabled, "advanced": [_presentation_action("view_diagnostics", "View raw diagnostics", None)]}


def _what_happened(key: str, status: str, summary: dict[str, Any]) -> list[str]:
    part_id = _active_part_id(summary)
    if key in {"cad_ir_draft", "part_modeling"} and summary.get("blocked_cad_ir_validation"):
        return [
            f"{part_id or 'The selected part'} was selected from the assembly plan.",
            "CadIrAgent produced cad_ir_draft.json.",
            "Validation stopped before model generation.",
        ]
    if key in {"planning", "assembly_plan"}:
        return [
            "CadFlow separated the assembly into generated candidates and reference components.",
            f"{len(summary.get('candidate_parts') or [])} candidate parts can be considered for generation.",
            f"{summary['selected_candidate']} is the current part in the reviewed-part pipeline." if summary.get("selected_candidate") else "No candidate has entered the reviewed-part pipeline yet.",
        ]
    return [_human_stage_summary(key, status, summary, None, [])]


def _artifact_status_items(key: str, summary: dict[str, Any], raw_artifacts: list[dict[str, Any]]) -> list[dict[str, str]]:
    present = {str(item.get("name")) for item in raw_artifacts if isinstance(item, dict) and item.get("present")}
    if key in {"cad_ir_draft", "part_modeling"}:
        return [
            _status_item("cad_ir_draft.json", "present" if "cad_ir_draft.json" in present else "not created"),
            _status_item("child input_ir.json", "present" if summary.get("child_input_ir_status") == "present" else "not created"),
            _status_item("model.step", "present" if summary.get("model_step_status") == "present" else "not created"),
            _status_item("model.stl", "present" if summary.get("model_stl_status") == "present" else "not created"),
        ]
    return [_status_item(str(item.get("name")), "present" if item.get("present") else "absent") for item in raw_artifacts[:5]]


def _review_state_items(key: str, status: str, summary: dict[str, Any], blocked_reasons: list[Any], overrides: dict[str, Any]) -> list[str]:
    if key in {"cad_ir_draft", "part_modeling"} and summary.get("blocked_cad_ir_validation"):
        items = ["No CAD result is available to approve.", "This stage can be marked blocked or reviewed as expected."]
    else:
        items = [f"Status: {status.replace('_', ' ')}."]
    if _current_block(key, status, summary, blocked_reasons) and not summary.get("blocked_cad_ir_validation"):
        items.append("A stage review can record whether this block is expected or needs revision.")
    if overrides:
        items.append("A validated user override is active for this stage.")
    return items


def _active_part_id(summary: dict[str, Any]) -> str | None:
    value = _first_present(
        summary.get("selected_candidate"),
        _nested(summary.get("part_create_request"), "part_id"),
        _nested(summary.get("reviewed_part_handoff"), "part_id"),
        _nested(summary.get("lineage"), "part_id"),
    )
    return str(value) if value else None


def _banner_title(key: str, status: str) -> str:
    if status == "blocked":
        return f"Blocked at {_stage_label(key)}"
    if status == "needs_review":
        return f"{_stage_label(key)} needs review"
    if status == "user_modified":
        return f"{_stage_label(key)} uses a validated user override"
    return f"{_stage_label(key)} {status.replace('_', ' ')}"


def _banner_badge(label: str, value: str, status: str) -> dict[str, str]:
    return {"label": label, "value": value, "status": status}


def _human_scope(scope: Any) -> str:
    values = {"multi_part": "assembly", "single_part": "single part"}
    return values.get(str(scope), str(scope or "unspecified"))


def _status_item(label: str, value: Any) -> dict[str, str]:
    text = str(value)
    return {"label": label, "value": text, "status": "completed" if text == "present" else "not_started"}


def _chip_item(label: Any, status: str) -> dict[str, str]:
    return {"label": str(label), "status": status}


def _has_model_export(summary: dict[str, Any]) -> bool:
    return summary.get("model_step_status") == "present" or summary.get("model_stl_status") == "present"


def _model_export_status(summary: dict[str, Any]) -> str:
    return "present" if _has_model_export(summary) else "absent"


def _has_blocked_cad_ir(summary: dict[str, Any]) -> bool:
    return bool(summary.get("blocked_cad_ir_validation"))


def _presentation_action(key: str, label: str, artifact_name: str | None) -> dict[str, Any]:
    action = {"key": key, "label": label, "enabled": True, "presentation_action": key}
    if artifact_name:
        action["artifact_name"] = artifact_name
    return action


def _key_decisions(
    key: str,
    summary: dict[str, Any],
    gate_decision: Any,
    input_artifacts: list[dict[str, Any]],
    output_artifacts: list[dict[str, Any]],
    overrides: dict[str, Any],
) -> list[dict[str, str]]:
    decisions: list[dict[str, str]] = []
    if summary.get("requirement_source"):
        decisions.append({"label": "Requirement source", "value": str(summary["requirement_source"])})
    if summary.get("intent_scope"):
        decisions.append({"label": "Scope", "value": str(summary["intent_scope"])})
    if _gate_action(gate_decision):
        decisions.append({"label": "Gate action", "value": str(_gate_action(gate_decision)).replace("_", " ")})
    if summary.get("route"):
        decisions.append({"label": "Route", "value": str(summary["route"])})
    if summary.get("selected_candidate"):
        decisions.append({"label": "Selected candidate", "value": str(summary["selected_candidate"])})
    if summary.get("candidate_parts"):
        decisions.append({"label": "Candidate parts", "value": ", ".join(str(item) for item in summary["candidate_parts"])})
    if summary.get("reference_components"):
        decisions.append({"label": "Reference components", "value": ", ".join(str(item) for item in summary["reference_components"])})
    if key in {"cad_ir_draft", "part_modeling"}:
        decisions.extend([
            {"label": "Child input_ir.json", "value": str(summary.get("child_input_ir_status") or "absent")},
            {"label": "STEP", "value": str(summary.get("model_step_status") or "absent")},
            {"label": "STL", "value": str(summary.get("model_stl_status") or "absent")},
        ])
    override_names = [
        item["name"]
        for item in (*input_artifacts, *output_artifacts)
        if _canonical_name(item.get("name") or "") in overrides
    ]
    if override_names:
        decisions.append({"label": "Override", "value": ", ".join(override_names)})
    return decisions[:8]


def _next_recommended_action(
    key: str,
    status: str,
    actions: list[dict[str, Any]],
    summary: dict[str, Any],
    blocked_reasons: list[Any],
) -> str:
    if key in {"cad_ir_draft", "part_modeling"} and summary.get("blocked_cad_ir_validation"):
        return "Review the part definition and record the required revision; the current backend cannot continue with this draft."
    if key in {"planning", "assembly_plan"} and summary.get("selected_candidate"):
        return f"Review {summary['selected_candidate']} as the current part, then continue its reviewed-part pipeline."
    if key in {"planning", "assembly_plan"} and summary.get("candidate_parts"):
        return "Choose a supported candidate to move into the reviewed-part pipeline."
    if status == "blocked":
        reason = _human_block_summary(blocked_reasons)
        return f"Resolve the recorded issue{' before continuing' if reason else ''}, then save a stage review."
    enabled = next((action for action in actions if action.get("enabled") and action.get("key") != "approve_stage"), None)
    if enabled:
        return _human_action_label(str(enabled.get("key") or ""), str(enabled.get("label") or ""))
    if key == "rework":
        return "Save a needs_revision stage review before running rework."
    return "No enabled action from this stage."


def _human_action_label(key: str, label: str) -> str:
    labels = {
        "apply_requirement_clarification": "Apply the clarification so downstream planning uses the updated requirement.",
        "create_part_request": "Start the reviewed-part pipeline for a supported candidate.",
        "part_request": "Prepare the selected part for review.",
        "part_review": "Review the selected part request before handing it to modeling.",
        "reviewed_handoff": "Create the reviewed handoff for the selected part.",
        "reviewed_part_create": "Create the selected part from its reviewed handoff.",
        "part_result_review": "Review the available result for the selected part.",
        "create_workflow_review": "Refresh the work-level review to see current readiness and risks.",
        "run_rework": "Run the saved revision request without changing the earlier run.",
    }
    return labels.get(key, label or "Review this stage and choose the appropriate next action.")


def _important_artifacts(artifacts: list[dict[str, Any]], overrides: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    editable = {_canonical_name(item) for item in EDITABLE_ARTIFACTS}
    for artifact in artifacts:
        name = artifact.get("name")
        canonical = _canonical_name(name or "")
        override = overrides.get(canonical) if isinstance(overrides.get(canonical), dict) else None
        result.append({
            "name": name,
            "present": bool(artifact.get("present")),
            "source": "user_override" if override else "original",
            "editable": canonical in editable,
            "validation_status": override.get("validation_status") if override else ("original" if artifact.get("present") else "missing"),
            "summary": artifact.get("summary") or "missing",
        })
    return result


def _human_block_summary(blocked_reasons: list[Any]) -> str:
    if not blocked_reasons:
        return ""
    first = blocked_reasons[0]
    if isinstance(first, dict):
        if first.get("blocked_stage") == "cad_ir_validation":
            return "CAD IR validation rejected the draft before child input_ir.json or model exports were created."
        return str(first.get("message") or first.get("code") or first.get("status") or "Review the debug details.")
    return str(first).replace("_", " ")


def _gate_action(gate_decision: Any) -> str | None:
    return gate_decision.get("action") if isinstance(gate_decision, dict) and isinstance(gate_decision.get("action"), str) else None


def _stage_label(key: str) -> str:
    for definition in STAGE_DEFINITIONS:
        if definition["key"] == key:
            return str(definition["name"])
    return key.replace("_", " ").title()


def _summary_context(run: dict[str, Any], contents: dict[str, Any]) -> dict[str, Any]:
    report_summary = run.get("report_summary") if isinstance(run.get("report_summary"), dict) else {}
    reviewed = run.get("reviewed_part_summary") if isinstance(run.get("reviewed_part_summary"), dict) else {}
    workflow_review = run.get("workflow_review_summary") if isinstance(run.get("workflow_review_summary"), dict) else {}
    return {
        "report_summary": report_summary,
        "report_artifact": contents.get("report.json") if isinstance(contents.get("report.json"), dict) else {},
        "requirement": contents.get("requirement_v2.json") if isinstance(contents.get("requirement_v2.json"), dict) else contents.get("requirement.json"),
        "requirement_source": "requirement_v2.json" if isinstance(contents.get("requirement_v2.json"), dict) else ("requirement.json" if isinstance(contents.get("requirement.json"), dict) else None),
        "planning": contents.get("planning_artifact.json"),
        "cad_ir_draft": contents.get("cad_ir_draft.json"),
        "assembly": (
            reviewed.get("assembly_plan")
            if isinstance(reviewed.get("assembly_plan"), dict)
            else (contents.get("assembly_plan.json") if isinstance(contents.get("assembly_plan.json"), dict) else {})
        ),
        "reviewed": reviewed,
        "workflow_review": workflow_review,
        "child_runs": run.get("child_runs") if isinstance(run.get("child_runs"), list) else [],
    }


def _report_summary(key: str, context: dict[str, Any]) -> dict[str, Any]:
    requirement = context.get("requirement") if isinstance(context.get("requirement"), dict) else {}
    planning = context.get("planning") if isinstance(context.get("planning"), dict) else {}
    reviewed = context.get("reviewed") if isinstance(context.get("reviewed"), dict) else {}
    if key in {"requirement", "clarification"}:
        intent = requirement.get("intent") if isinstance(requirement.get("intent"), dict) else {}
        status = requirement.get("requirement_status") if isinstance(requirement.get("requirement_status"), dict) else {}
        return {
            "requirement_source": context.get("requirement_source"),
            "part_type": requirement.get("part_type"),
            "part_family": requirement.get("part_family"),
            "intent_scope": intent.get("scope") or requirement.get("scope"),
            "object_goal": requirement.get("object_goal") or intent.get("object_goal"),
            "assumptions": _safe_list(requirement.get("assumptions")),
            "missing_information": _field_items(requirement.get("missing_information")),
            "follow_up_questions": _follow_up_questions(requirement),
            "flow_decision": status.get("flow_decision"),
        }
    if key in {"planning", "assembly_plan"}:
        assembly = context.get("assembly") if isinstance(context.get("assembly"), dict) else {}
        intent = requirement.get("intent") if isinstance(requirement.get("intent"), dict) else {}
        return {
            "requirement_source": context.get("requirement_source"),
            "intent_scope": intent.get("scope") or requirement.get("scope"),
            "object_goal": requirement.get("object_goal") or intent.get("object_goal"),
            "route": _nested(planning, "route", "selected"),
            "flow_gate_status": planning.get("flow_gate_status") if isinstance(planning, dict) else None,
            "part_count": assembly.get("part_count"),
            "candidate_parts": [part.get("part_id") for part in _safe_list(assembly.get("parts")) if isinstance(part, dict) and part.get("supported_candidate")],
            "reference_components": [part.get("part_id") for part in _safe_list(assembly.get("parts")) if isinstance(part, dict) and part.get("reference_only")],
            "selected_candidate": _first_present(
                _nested(context.get("report_summary"), "final_selected_candidate"),
                _nested(reviewed.get("part_request"), "part_id"),
            ),
            "supported_candidate": any(part.get("supported_candidate") for part in _safe_list(assembly.get("parts")) if isinstance(part, dict)),
            "blocked_cad_ir_validation": _blocked_cad_ir_validation(context),
        }
    if key in {"part_request", "part_review", "reviewed_handoff", "cad_ir_draft", "part_modeling", "part_result_review"}:
        child_runs = context.get("child_runs") if isinstance(context.get("child_runs"), list) else []
        child = child_runs[0] if child_runs and isinstance(child_runs[0], dict) else {}
        part_result = reviewed.get("part_result_review") if isinstance(reviewed.get("part_result_review"), dict) else {}
        return {
            "part_create_request": reviewed.get("part_request"),
            "part_request_review": reviewed.get("part_request_review"),
            "reviewed_part_handoff": reviewed.get("reviewed_part_handoff"),
            "lineage": reviewed.get("lineage"),
            "part_result_review": part_result,
            "child_input_ir_status": "present" if "input_ir.json" in child.get("artifacts", []) else "absent",
            "model_step_status": "present" if "model.step" in child.get("downloadables", []) else "absent",
            "model_stl_status": "present" if "model.stl" in child.get("downloadables", []) else "absent",
            "blocked_cad_ir_validation": _blocked_cad_ir_validation(context),
            "no_mounting_plate_fallback": _no_mounting_plate_fallback(context),
        }
    if key == "workflow_review":
        return context.get("workflow_review") if isinstance(context.get("workflow_review"), dict) else {}
    return {}


def _stage_actions(key: str, review_stage: str, artifacts: set[str], has_run: bool) -> list[dict[str, Any]]:
    actions = [
        _action("save_stage_review", "Save Stage Review", has_run, None if has_run else "Select a run first.", {"stage": review_stage}),
        _action("approve_stage", f"Approve {review_stage.replace('_', ' ').title()}", has_run, None if has_run else "Select a run first.", {"backend_action": "save_stage_review", "review_status": "approved", "stage": review_stage}),
        _action("mark_needs_revision", "Mark Needs Revision", False, "Use the Stage Review form to provide target rework stage and requested changes.", {"backend_action": "save_stage_review", "review_status": "needs_revision", "stage": review_stage}),
        _action("mark_blocked", "Mark Blocked", has_run, None if has_run else "Select a run first.", {"backend_action": "save_stage_review", "review_status": "blocked", "stage": review_stage}),
    ]
    if key == "requirement":
        actions.insert(0, _action("apply_requirement_clarification", "Apply Clarification", bool({"requirement.json", "requirement_v2.json"} & artifacts), "Requires requirement.json or requirement_v2.json.", {}))
        actions.append(_action("rerun_requirement", "Rerun Requirement", False, "NiceGUI MVP does not expose stage rerun from this card.", {"backend_route": "run_stage"}))
        actions.append(_action("return_to_requirement", "Return to Requirement", False, "Gate-return buttons are recorded outside this MVP card.", {"backend_route": "record_gate_decision"}))
    if key in {"planning", "assembly_plan"}:
        actions.append(_action("create_part_request", "Create Part Request", "assembly_plan.json" in artifacts, "Requires assembly_plan.json.", {"backend_action": "part_request"}))
        actions.append(_action("return_to_requirement", "Return to Requirement", False, "Gate-return buttons are recorded outside this MVP card.", {"backend_route": "record_gate_decision"}))
        actions.append(_action("rerun_planning", "Rerun Planning", False, "NiceGUI MVP does not expose stage rerun from this card.", {"backend_route": "run_stage"}))
    if key == "part_request":
        actions.append(_action("part_request", "Create Part Request", "assembly_plan.json" in artifacts, "Requires assembly_plan.json.", {"backend_action": "part_request"}))
    if key == "part_review":
        actions.append(_action("part_review", "Review Part Request", "part_create_request.json" in artifacts, "Requires part_create_request.json.", {"backend_action": "part_review"}))
    if key == "reviewed_handoff":
        ready = {"part_create_request.json", "part_request_review.json"} <= artifacts
        actions.append(_action("reviewed_handoff", "Create Reviewed Handoff", ready, "Requires part_create_request.json and part_request_review.json.", {"backend_action": "reviewed_handoff"}))
    if key in {"cad_ir_draft", "part_modeling"}:
        actions.append(_action("reviewed_part_create", "Create Reviewed Part", "reviewed_part_handoff.json" in artifacts, "Requires reviewed_part_handoff.json.", {"backend_action": "reviewed_part_create"}))
    if key == "part_result_review":
        ready = {"reviewed_part_handoff.json", "lineage.json"} <= artifacts
        actions.append(_action("part_result_review", "Review Part Result", ready, "Requires reviewed_part_handoff.json and lineage.json.", {"backend_action": "part_result_review"}))
    if key == "workflow_review":
        actions.append(_action("create_workflow_review", "Create / Refresh Workflow Review", has_run, None if has_run else "Select a run first.", {"backend_action": "create_workflow_review"}))
    if key == "rework":
        actions.append(_action("run_rework", "Run Rework", "stage_review.json" in artifacts, "Requires stage_review.json with needs_revision.", {"backend_action": "run_rework"}))
    return actions


def _global_actions(artifacts: set[str], has_run: bool) -> list[dict[str, Any]]:
    return [
        _action("create_workflow_review", "Create / Refresh Workflow Review", has_run, None if has_run else "Select a run first.", {"backend_action": "create_workflow_review"}),
        _action("run_rework", "Run Rework", "stage_review.json" in artifacts, "Requires stage_review.json with needs_revision.", {"backend_action": "run_rework"}),
    ]


def _action(key: str, label: str, enabled: bool, disabled_reason: str | None, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "enabled": bool(enabled),
        "disabled_reason": None if enabled else disabled_reason,
        **metadata,
    }


def _artifact_viewer(artifact_names: set[str], contents: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    artifacts = []
    for name in REVIEW_SURFACE_ARTIFACTS:
        if name not in artifact_names:
            continue
        content = contents.get(name)
        canonical = _canonical_name(name)
        override = overrides.get(canonical) if isinstance(overrides.get(canonical), dict) else None
        editable = canonical in {_canonical_name(item) for item in EDITABLE_ARTIFACTS}
        artifacts.append({
            "name": name,
            "canonical_name": canonical,
            "relative_path": name,
            "present": True,
            "source": "user_override" if override else "original",
            "override_present": override is not None,
            "last_edited_at": override.get("last_edited_at") if override else None,
            "validation_status": override.get("validation_status") if override else None,
            "downstream_stages_affected": override.get("downstream_stages_affected") if override else _downstream_for(canonical),
            "editable": editable,
            "edit_disabled_reason": None if editable else _non_editable_reason(name),
            "summary": _artifact_summary(name, content),
            "raw_json_available": isinstance(content, dict),
            "copyable": name,
        })
    return {
        "allowlist": [name for name in REVIEW_SURFACE_ARTIFACTS if name in READABLE_ARTIFACTS],
        "artifacts": artifacts,
        "arbitrary_browsing": False,
    }


def _workflow_context(
    artifact_names: set[str],
    contents: dict[str, Any],
    selected_stage: dict[str, Any] | None,
    language: str,
) -> dict[str, Any]:
    """Build the high-priority input/output presentation without exposing raw paths."""
    prompt = _artifact_presentation("prompt.txt", "workflow_input", artifact_names, contents, language)
    requirements = [
        _artifact_presentation(name, "workflow_input", artifact_names, contents, language)
        for name in ("requirement.json", "requirement_clarification.json", "requirement_v2.json")
        if name in artifact_names
    ]
    stage_artifacts: list[dict[str, Any]] = []
    if isinstance(selected_stage, dict):
        for direction, artifacts in (("input", selected_stage.get("input_artifacts")), ("output", selected_stage.get("output_artifacts"))):
            for artifact in _safe_list(artifacts):
                if isinstance(artifact, dict) and isinstance(artifact.get("name"), str):
                    item = _artifact_presentation(artifact["name"], direction, artifact_names, contents, language)
                    stage_artifacts.append(_selected_stage_artifact_status(item, selected_stage, language))
    return {
        "title": "工作流输入与输出" if language == "zh" else "Workflow inputs & outputs",
        "prompt": prompt,
        "requirements": requirements,
        "selected_stage_label": selected_stage.get("stage_name") if isinstance(selected_stage, dict) else None,
        "stage_artifacts": stage_artifacts,
        "empty_message": "选择一个阶段以查看其输入和输出。" if language == "zh" else "Select a stage to view its inputs and outputs.",
        "table_columns": (
            ["资料", "用途", "方向", "状态", "操作"]
            if language == "zh"
            else ["Artifact", "Purpose", "Direction", "Status", "Access"]
        ),
    }


def _selected_stage_artifact_status(item: dict[str, Any], selected_stage: dict[str, Any], language: str) -> dict[str, Any]:
    """Avoid treating a root export as the selected child part's output."""
    if selected_stage.get("key") not in {"cad_ir_draft", "part_modeling"}:
        return item
    summary = selected_stage.get("report_summary") if isinstance(selected_stage.get("report_summary"), dict) else {}
    name = item.get("name")
    child_status = {
        "input_ir.json": summary.get("child_input_ir_status"),
        "model.step": summary.get("model_step_status"),
        "model.stl": summary.get("model_stl_status"),
    }.get(name)
    if child_status not in {"present", "absent"}:
        return item
    present = child_status == "present"
    item["present"] = present
    item["status"] = "completed" if present else "not_started"
    item["status_label"] = "可用" if present and language == "zh" else "available" if present else "未创建" if language == "zh" else "not created"
    item["downloadable"] = bool(item.get("downloadable") and present)
    item["stl_previewable"] = bool(item.get("stl_previewable") and present)
    item["previewable"] = bool(item.get("previewable") and present)
    item["status_help"] = (
        f"此资料可用于：{item.get('purpose')}。" if present and language == "zh" else
        f"This artifact is available for: {item.get('purpose')}." if present else
        f"此资料尚未创建，因此无法用于：{item.get('purpose')}。" if language == "zh" else
        f"This artifact was not created, so it cannot yet support: {item.get('purpose')}."
    )
    return item


def _artifact_presentation(
    name: str,
    direction: str,
    artifact_names: set[str],
    contents: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    present = name in artifact_names
    downloadable = name in {"model.step", "model.stl", "preview.png", "model.py"} and present
    previewable = present and (name == "prompt.txt" or name.endswith(".json") or name == "model.stl")
    english_purpose = {
        "prompt.txt": "Original user request",
        "requirement.json": "Initial structured requirement",
        "requirement_clarification.json": "Clarification record",
        "requirement_v2.json": "Reviewed requirement used for planning",
        "planning_artifact.json": "Planning decision",
        "assembly_plan.json": "Part decomposition and selected candidate",
        "part_create_request.json": "Selected part definition",
        "part_request_review.json": "Part review decision",
        "reviewed_part_handoff.json": "Approved handoff to modeling",
        "part_execution_request.json": "Modeling execution request",
        "cad_ir_draft.json": "Draft CAD representation",
        "input_ir.json": "Validated CAD input",
        "model.step": "CAD exchange model",
        "model.stl": "Printable mesh model",
        "preview.png": "Model preview image",
        "model.py": "Generated modeling script",
    }
    chinese_purpose = {
        "prompt.txt": "原始用户需求", "requirement.json": "初始结构化需求", "requirement_clarification.json": "需求澄清记录",
        "requirement_v2.json": "供规划使用的已评审需求", "planning_artifact.json": "规划决策",
        "assembly_plan.json": "零件拆分与选定候选", "part_create_request.json": "选定零件定义",
        "part_request_review.json": "零件评审决策", "reviewed_part_handoff.json": "交给建模的已评审定义",
        "part_execution_request.json": "建模执行请求", "cad_ir_draft.json": "CAD 表达草稿",
        "input_ir.json": "已验证的 CAD 输入", "model.step": "CAD 交换模型", "model.stl": "可打印网格模型",
        "preview.png": "模型预览图", "model.py": "生成的建模脚本",
    }
    is_zh = language == "zh"
    purpose = (chinese_purpose if is_zh else english_purpose).get(name, "工作流资料" if is_zh else "Workflow record")
    status = "completed" if present else "not_started"
    direction_label = {"workflow_input": "工作流输入" if is_zh else "Workflow input", "input": "阶段输入" if is_zh else "Stage input", "output": "阶段输出" if is_zh else "Stage output"}[direction]
    availability = "可用" if is_zh else "available"
    unavailable = "未创建" if is_zh else "not created"
    state_help = (
        f"此资料可用于：{purpose}。" if present and is_zh else
        f"This artifact is available for: {purpose}." if present else
        f"此资料尚未创建，因此无法用于：{purpose}。" if is_zh else
        f"This artifact was not created, so it cannot yet support: {purpose}."
    )
    return {
        "name": name,
        "display_name": _artifact_display_name(name, language),
        "purpose": purpose,
        "direction": direction,
        "direction_label": direction_label,
        "present": present,
        "status": status,
        "status_label": availability if present else unavailable,
        "status_help": state_help,
        "summary": _artifact_summary(name, contents.get(name)) if present else unavailable,
        "preview": _artifact_human_preview(name, contents.get(name), language) if present else None,
        "previewable": previewable,
        "downloadable": downloadable,
        "stl_previewable": name == "model.stl" and present,
    }


def _artifact_display_name(name: str, language: str) -> str:
    english = {
        "prompt.txt": "Original request", "requirement.json": "Initial requirement",
        "requirement_clarification.json": "Clarification", "requirement_v2.json": "Reviewed requirement",
        "planning_artifact.json": "Planning decision", "assembly_plan.json": "Assembly plan",
        "part_create_request.json": "Part request", "part_request_review.json": "Part review",
        "reviewed_part_handoff.json": "Reviewed handoff", "part_execution_request.json": "Modeling request",
        "cad_ir_draft.json": "CAD draft", "input_ir.json": "Validated CAD input",
        "model.step": "STEP model", "model.stl": "STL model", "preview.png": "Model preview", "model.py": "Modeling script",
    }
    chinese = {
        "prompt.txt": "原始需求", "requirement.json": "初始需求", "requirement_clarification.json": "需求澄清",
        "requirement_v2.json": "已评审需求", "planning_artifact.json": "规划决策", "assembly_plan.json": "装配计划",
        "part_create_request.json": "零件请求", "part_request_review.json": "零件评审",
        "reviewed_part_handoff.json": "已评审交接", "part_execution_request.json": "建模请求",
        "cad_ir_draft.json": "CAD 草稿", "input_ir.json": "已验证 CAD 输入",
        "model.step": "STEP 模型", "model.stl": "STL 模型", "preview.png": "模型预览", "model.py": "建模脚本",
    }
    return (chinese if language == "zh" else english).get(name, name)


def _artifact_human_preview(name: str, content: Any, language: str) -> dict[str, Any]:
    """Return concise user-facing facts instead of exposing artifact JSON."""
    is_zh = language == "zh"
    data = content if isinstance(content, dict) else {}
    label = _artifact_display_name(name, language)
    items: list[dict[str, str]] = []
    fields = {
        "requirement.json": (("object_goal", "目标" if is_zh else "Goal"), ("part_type", "类型" if is_zh else "Type"), ("scope", "范围" if is_zh else "Scope")),
        "requirement_v2.json": (("object_goal", "目标" if is_zh else "Goal"), ("part_type", "类型" if is_zh else "Type"), ("requirement_status", "状态" if is_zh else "Status")),
        "planning_artifact.json": (("route", "路径" if is_zh else "Route"), ("part_count", "零件数" if is_zh else "Part count")),
        "assembly_plan.json": (("selected_candidate", "选定零件" if is_zh else "Selected part"), ("part_count", "零件数" if is_zh else "Part count")),
        "part_create_request.json": (("part_id", "零件" if is_zh else "Part"), ("role", "职责" if is_zh else "Role"), ("brief", "说明" if is_zh else "Brief")),
        "part_request_review.json": (("part_id", "零件" if is_zh else "Part"), ("status", "评审状态" if is_zh else "Review status")),
        "reviewed_part_handoff.json": (("part_id", "零件" if is_zh else "Part"), ("status", "交接状态" if is_zh else "Handoff status")),
        "cad_ir_draft.json": (("part_id", "零件" if is_zh else "Part"), ("part_type", "零件类型" if is_zh else "Part type"), ("status", "状态" if is_zh else "Status")),
    }.get(name, ())
    for key, field_label in fields:
        value = data.get(key)
        if value not in (None, "", [], {}):
            items.append({"label": field_label, "value": _preview_value(value)})
    if name == "assembly_plan.json":
        parts = [str(item.get("part_id")) for item in _safe_list(data.get("parts")) if isinstance(item, dict) and item.get("part_id")]
        if parts:
            items.append({"label": "候选零件" if is_zh else "Candidate parts", "value": ", ".join(parts[:6])})
    if not items:
        fallback = _artifact_summary(name, content)
        items.append({"label": "摘要" if is_zh else "Summary", "value": fallback})
    return {
        "title": label,
        "summary": ("这是当前工作流使用的记录。" if is_zh else "This record is used by the current workflow."),
        "items": items[:5],
    }


def _preview_value(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}: {item}" for key, item in list(value.items())[:3])
    if isinstance(value, list):
        return ", ".join(str(item) for item in value[:4])
    return str(value)


def _artifact_ref(name: str, artifact_names: set[str], contents: dict[str, Any]) -> dict[str, Any]:
    present = name in artifact_names
    return {
        "name": name,
        "present": present,
        "summary": _artifact_summary(name, contents.get(name)) if present else "missing",
    }


def _artifact_summary(name: str, content: Any) -> str:
    if name == "prompt.txt" and isinstance(content, str):
        return content.strip()[:160]
    if name == "logs/runtime.json" and isinstance(content, dict):
        console = content.get("workflow_console") if isinstance(content.get("workflow_console"), dict) else {}
        return f"stages={console.get('stage_count', 0)}, actions={_nested(console, 'action_count') or 0}"
    if isinstance(content, dict):
        status = content.get("status") or content.get("overall_status") or content.get("review_status")
        artifact_type = content.get("artifact_type")
        part_id = content.get("part_id")
        bits = [str(item) for item in (artifact_type, status, part_id) if item]
        return ", ".join(bits) if bits else f"{len(content)} top-level fields"
    if isinstance(content, str):
        return content.strip().splitlines()[0][:160] if content.strip() else "empty text"
    return "available"


def _stage_status(key: str, artifacts: list[dict[str, Any]], run: dict[str, Any], contents: dict[str, Any], overrides: dict[str, Any]) -> str:
    if any(_canonical_name(item["name"]) in overrides for item in artifacts):
        return "user_modified"
    if key == "requirement" and any(item["name"] in {"requirement.json", "requirement_v2.json"} and item["present"] for item in artifacts):
        decision = _nested(contents.get("requirement_v2.json") or contents.get("requirement.json") or {}, "requirement_status", "flow_decision", "action")
        return "blocked" if decision in {"ask_user", "return", "return_to_requirement", "blocked"} else "completed"
    if key == "part_modeling" and _blocked_cad_ir_validation(_summary_context(run, contents)):
        return "blocked"
    if any(item["present"] for item in artifacts):
        return "completed"
    if any(item["present"] for item in artifacts if item["name"] == "stage_review.json"):
        return "needs_review"
    return "not_started"


def _gate_decision(key: str, run: dict[str, Any], contents: dict[str, Any]) -> Any:
    if key in {"requirement", "clarification"}:
        return _nested(contents.get("requirement_v2.json") or contents.get("requirement.json") or {}, "requirement_status", "flow_decision")
    if key in {"planning", "assembly_plan"}:
        return _nested(contents.get("planning_artifact.json") or {}, "flow_gate_status", "rework_decision")
    status = run.get("status") if isinstance(run.get("status"), dict) else {}
    return status.get("gate_decision") or status.get("flow_decision")


def _diagnostic_codes(key: str, run: dict[str, Any], contents: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for value in contents.values():
        if isinstance(value, dict):
            codes.extend(_safe_list(value.get("diagnostic_codes")))
    reviewed = run.get("reviewed_part_summary") if isinstance(run.get("reviewed_part_summary"), dict) else {}
    for value in reviewed.values():
        if isinstance(value, dict):
            codes.extend(_safe_list(value.get("diagnostic_codes")))
    return _unique_strings(codes)


def _blocked_reasons(key: str, run: dict[str, Any], contents: dict[str, Any]) -> list[Any]:
    reasons = []
    requirement = contents.get("requirement_v2.json") or contents.get("requirement.json") or {}
    if key in {"requirement", "clarification"}:
        reasons.extend(_safe_list(requirement.get("missing_information")))
    planning = contents.get("planning_artifact.json") or {}
    reasons.extend(_safe_list(_nested(planning, "flow_gate_status", "blocking_reasons")))
    reviewed = run.get("reviewed_part_summary") if isinstance(run.get("reviewed_part_summary"), dict) else {}
    assembly = reviewed.get("assembly_plan") if isinstance(reviewed.get("assembly_plan"), dict) else {}
    reasons.extend(_safe_list(assembly.get("blocked_reason_codes")))
    blocked = _blocked_cad_ir_validation(_summary_context(run, contents))
    if blocked:
        reasons.append(blocked)
    return reasons[:12]


def _agent_identity(run: dict[str, Any]) -> dict[str, Any] | None:
    status = run.get("status") if isinstance(run.get("status"), dict) else {}
    activity = status.get("adapter_activity") if isinstance(status.get("adapter_activity"), dict) else None
    if activity is None:
        for stage in run.get("stage_history") or []:
            if isinstance(stage, dict) and isinstance(stage.get("adapter_activity"), dict):
                activity = stage["adapter_activity"]
    if not isinstance(activity, dict):
        return None
    return {
        "operation": activity.get("operation"),
        "provider_identity": activity.get("provider_identity") if isinstance(activity.get("provider_identity"), dict) else {},
    }


def _blocked_cad_ir_validation(context: dict[str, Any]) -> Any:
    report = context.get("report_summary") if isinstance(context.get("report_summary"), dict) else {}
    artifact_report = context.get("report_artifact") if isinstance(context.get("report_artifact"), dict) else {}
    if not report.get("status") and artifact_report:
        report = artifact_report
    if report.get("status") == "blocked_cad_ir_validation" or report.get("blocked_stage") == "cad_ir_validation":
        return {
            "status": report.get("status") or "blocked_cad_ir_validation",
            "blocked_stage": report.get("blocked_stage") or "cad_ir_validation",
            "errors": report.get("errors") or [],
        }
    return None


def _no_mounting_plate_fallback(context: dict[str, Any]) -> bool | None:
    reviewed = context.get("reviewed") if isinstance(context.get("reviewed"), dict) else {}
    request = reviewed.get("part_request") if isinstance(reviewed.get("part_request"), dict) else {}
    handoff = reviewed.get("reviewed_part_handoff") if isinstance(reviewed.get("reviewed_part_handoff"), dict) else {}
    part_ids = {request.get("part_id"), handoff.get("part_id")}
    if not any(part_ids):
        return None
    return "mounting_plate" not in part_ids


def _follow_up_questions(requirement: dict[str, Any]) -> list[Any]:
    return _safe_list(requirement.get("follow_up_questions")) or _safe_list(requirement.get("clarification_questions")) or _field_items(requirement.get("follow_up_requests"))


def _field_items(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            result.append({key: item.get(key) for key in ("code", "field", "message", "question", "ask_user") if key in item})
        else:
            result.append(item)
    return result


def _read_artifact_content(
    backend: WorkflowConsoleBackend,
    run_id: str,
    artifact: str,
    *,
    root: str | None = None,
) -> Any:
    if artifact not in READABLE_ARTIFACTS or artifact not in REVIEW_SURFACE_ARTIFACTS:
        return None
    response = dispatch_route(backend, "read_artifact", path_params={"run_id": run_id, "artifact": artifact}, query=_query(root))
    if not response["ok"]:
        return None
    artifact_data = response["data"]
    if isinstance(artifact_data, dict) and isinstance(artifact_data.get("artifact"), dict):
        artifact_data = artifact_data["artifact"]
    return artifact_data.get("content") if isinstance(artifact_data, dict) else None


def _artifact_names(run: dict[str, Any]) -> set[str]:
    names = {
        item["name"]
        for item in _safe_list(run.get("artifacts"))
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    for item in _safe_list(run.get("downloadables")):
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.add(item["name"])
    return names


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unique_strings(values: list[Any]) -> list[str]:
    result = []
    for value in values:
        if isinstance(value, str) and value not in result:
            result.append(value)
    return result[:20]


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _query(root: str | None) -> dict[str, Any] | None:
    return {"root": root} if root else None


def _canonical_name(name: str) -> str:
    aliases = {
        "02_part_request/part_create_request.json": "part_create_request.json",
        "03_review/part_request_review.json": "part_request_review.json",
        "04_handoff/reviewed_part_handoff.json": "reviewed_part_handoff.json",
        "05_single_create/cad_ir_draft.json": "cad_ir_draft.json",
    }
    return aliases.get(name, name)


def _downstream_for(name: str) -> list[str]:
    mapping = {
        "requirement_v2.json": ["planning"],
        "planning_artifact.json": ["assembly_plan", "part_modeling"],
        "assembly_plan.json": ["part_request"],
        "part_create_request.json": ["part_review", "reviewed_handoff"],
        "part_request_review.json": ["reviewed_handoff"],
        "reviewed_part_handoff.json": ["reviewed_part_create"],
        "cad_ir_draft.json": ["cad_ir_validation", "part_modeling"],
        "input_ir.json": ["part_modeling"],
        "stage_review.json": ["workflow_review", "rework"],
    }
    return mapping.get(name, [])


def _non_editable_reason(name: str) -> str:
    if name in {"prompt.txt"}:
        return "Original user input is not edited through overrides."
    if name in {"model.py", "model.step", "model.stl"}:
        return "Generated code or binary/export output is not editable."
    if name in {"report.json", "report.md", "workflow_review.md"}:
        return "Generated report artifacts are not editable."
    if name in {"agent_trace.json"}:
        return "Trace artifacts are debug-only and not editable."
    if name == "logs/runtime.json":
        return "Runtime history is append-only and not editable."
    return "Artifact is not in the editable override allowlist."
