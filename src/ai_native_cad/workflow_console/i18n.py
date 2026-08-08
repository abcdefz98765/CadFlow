"""Small, explicit presentation catalog for the Workflow cockpit.

Workflow contracts and artifacts deliberately retain their stable English keys.
This module translates only browser-visible copy, so changing the selected
language never changes a Work, a Run, or an action target.
"""

from __future__ import annotations

from typing import Any


_COPY: dict[str, tuple[str, str]] = {
    "overview_design": ("Overview / Design", "概览 / 设计"),
    "phase_intent": ("Intent", "意图"),
    "phase_design": ("Design", "设计"),
    "phase_build_evaluate": ("Build & Evaluate", "构建与评估"),
    "phase_accept_deliver": ("Accept & Deliver", "接受与交付"),
    "current_objective": ("Current objective", "当前目标"),
    "current_recommendation": ("Current recommendation", "当前建议"),
    "agent_activity": ("Agent activity", "Agent 动态"),
    "agent_activity_details": ("Agent activity details", "Agent 动态详情"),
    "geometry_preview": ("Geometry preview", "几何预览"),
    "current_result": ("Current result", "当前结果"),
    "result_ready_review": ("Result ready for review", "结果已准备好审查"),
    "result_accepted": ("Result accepted", "结果已接受"),
    "model_ready": ("Model ready", "模型已就绪"),
    "no_candidate": ("No candidate yet", "尚无候选设计"),
    "preview_unavailable": ("Preview unavailable", "预览暂不可用"),
    "validation": ("Validation", "验证"),
    "verified": ("Verified", "已验证"),
    "not_verified": ("Not verified", "未验证"),
    "assumptions": ("Assumptions", "假设"),
    "accept_result": ("Accept result", "接受结果"),
    "revise": ("Revise", "修改设计"),
    "revision_request": ("Describe the change", "描述要修改的内容"),
    "revision_preserves_acceptance": (
        "The currently accepted result will not be deleted. CadFlow will create a new design attempt.",
        "当前已接受结果不会被删除。CadFlow 会创建一个新的设计尝试。",
    ),
    "accept_consequence": (
        "This will make the result the current accepted result for this part. Earlier attempts remain available.",
        "这会将该结果设为此零件当前已接受结果。之前的设计尝试仍会保留。",
    ),
    "accept_success_detail": (
        "This result is now the current accepted result for the part. Earlier attempts and history are preserved.",
        "该结果现在是此零件的当前已接受结果。之前的设计尝试和历史结果仍然保留。",
    ),
    "revise_success_detail": (
        "A new design attempt was created. The previously accepted result remains available.",
        "已创建新的设计尝试。之前的已接受结果仍然保留。",
    ),
    "deterministic_compatibility": ("Deterministic compatibility", "确定性兼容模式"),
    "agentic_experimental": ("Agentic experimental", "Agentic 实验模式"),
    "isolated_execution_verified": ("Isolated execution: verified", "隔离执行：已验证"),
    "agent_execution_unavailable": ("Agent model execution is unavailable", "Agent 模型执行当前不可用"),
    "part_jobs": ("Part Jobs", "零件任务"),
    "history": ("History", "历史"),
    "attempts": ("Attempts", "设计尝试"),
    "accepted_result": ("Accepted result", "已接受结果"),
    "reviewable_result": ("Reviewable result", "可审查结果"),
    "detailed_workflow": ("Detailed Workflow", "详细工作流"),
    "advanced_evidence": ("Advanced / Evidence", "高级 / 证据"),
    "understanding_interfaces": ("Understanding interfaces", "正在理解零件接口"),
    "preparing_candidate": ("Preparing a candidate", "正在准备候选设计"),
    "building_geometry": ("Building geometry", "正在生成几何"),
    "inspecting_step": ("Inspecting STEP", "正在检查 STEP"),
    "repairing_candidate": ("Repairing the candidate", "检查发现问题，Agent 正在修复"),
    "waiting_user": ("Waiting for your input", "等待你的输入"),
    "ready_review": ("Ready for review", "结果已准备好审查"),
    "accepted_state": ("Accepted", "已接受"),
    "start_design": ("Start design", "开始设计"),
    "continue_agent": ("Continue Agent", "继续 Agent 设计"),
    "current_work": ("Current Work", "当前 Work"),
    "run_snapshot": ("Historical Run Snapshot · Read-only", "历史 Run 快照 · 只读"),
    "return_current_work": ("Return to Current Work", "返回当前 Work"),
    "workflow_graph": ("Workflow", "工作流"),
    "selected_stage": ("Selected stage conclusion", "所选阶段结论"),
    "user_input": ("User input", "用户输入"),
    "agent_decision": ("Agent interpretation / decision", "Agent 解读 / 决策"),
    "agent_output": ("Agent output", "Agent 输出"),
    "agent_review": ("Agent review", "Agent 评审"),
    "stage_review": ("Stage review", "阶段评审"),
    "evidence": ("Evidence", "证据"),
    "secondary_actions": ("Secondary actions", "其他操作"),
    "unavailable_actions": ("Unavailable actions", "当前不可用的操作"),
    "advanced": ("Advanced", "高级"),
    "action_details": ("Action Details", "操作详情"),
    "stage_purpose": ("Stage purpose", "阶段目的"),
    "decision_required": ("User decision", "是否需要用户决定"),
    "recommended_action": ("Recommended action", "推荐操作"),
    "expected_result": ("Expected result", "预期结果"),
    "limitations": ("Limitations", "限制"),
    "not_available": ("Not available", "暂无数据"),
    "available": ("Available", "可用"),
    "pending": ("Running", "正在执行"),
    "completed": ("Operation complete", "操作完成"),
    "failed": ("Operation failed", "操作失败"),
    "close": ("Close", "关闭"),
    "cancel": ("Cancel", "取消"),
    "confirm_selection": ("Confirm selection", "确认选择"),
    "candidate_detail": ("Candidate Detail", "候选零件详情"),
    "use_this_part_next": ("Use This Part Next", "将此零件用于下一步"),
    "save_stage_review": ("Save Stage Review", "保存阶段评审"),
    "quick_approve": ("Quick Approve", "快速批准"),
    "retry": ("Retry", "重试"),
    "details": ("View details", "查看详细信息"),
    "review_status": ("Review status", "评审状态"),
    "notes": ("Notes / blocked reason", "备注 / 阻断原因"),
    "requested_changes": ("Requested changes (required for Needs Revision)", "请求修改（“需要修改”时必填）"),
    "target_rework_stage": ("Target rework stage", "返工目标阶段"),
    "read_only": ("Read-only", "只读"),
    "source_run": ("Source Run", "来源 Run"),
    "assembly_plan": ("Assembly Plan", "装配计划"),
    "next_create_part_request": ("Next step: Create Part Request", "下一步：创建零件请求"),
}

_ACTION_LABELS: dict[str, str] = {
    "Accept result": "接受结果",
    "Revise": "修改设计",
    "Start design": "开始设计",
    "Continue Agent": "继续 Agent 设计",
    "Create Part Request": "创建零件请求",
    "Review Part Request": "评审零件请求",
    "Create Reviewed Handoff": "创建已评审交接",
    "Create Reviewed Part": "创建经评审零件",
    "Review Part Result": "评审零件结果",
    "Approve Single Part Result": "批准单零件结果",
    "Create / Refresh Workflow Review": "创建 / 刷新工作流评审",
    "Refresh agent workflow review": "刷新 Agent 工作流评审",
    "Request agent review": "请求 Agent 评审",
    "Request agent result review": "请求 Agent 结果评审",
    "Edit Assembly Plan": "编辑装配计划",
    "View CAD IR Draft": "查看 CAD IR 草稿",
    "Open CAD IR Draft": "打开 CAD IR 草稿",
    "Mark Blocked": "标记为阻断",
    "Mark Needs Revision": "标记需要修改",
    "Save Stage Review": "保存阶段评审",
    "Quick Approve": "快速批准",
    "Run Rework": "执行返工",
    "Open Candidate Detail": "打开候选零件详情",
    "Use This Part Next": "将此零件用于下一步",
}
_REVERSE_ACTION_LABELS = {value: key for key, value in _ACTION_LABELS.items()}

_STAGE_LABELS: dict[str, tuple[str, str]] = {
    "requirement": ("Requirement", "需求"),
    "clarification": ("Clarification", "澄清"),
    "planning": ("Planning", "规划"),
    "assembly_plan": ("Assembly Plan", "装配计划"),
    "part_request": ("Part Request", "零件请求"),
    "part_review": ("Part Review", "零件评审"),
    "reviewed_handoff": ("Reviewed Handoff", "已评审交接"),
    "cad_ir_draft": ("CAD IR Draft", "CAD IR 草稿"),
    "part_modeling": ("Part Modeling", "零件建模"),
    "part_result_review": ("Part Result Review", "零件结果评审"),
    "workflow_review": ("Workflow Review", "工作流评审"),
    "rework": ("Rework", "返工"),
}

_STATUS_LABELS: dict[str, tuple[str, str]] = {
    "completed": ("Completed", "已完成"),
    "contract_complete": ("Contract complete", "合同已完成"),
    "execution_skipped": ("Execution skipped", "已跳过执行"),
    "skipped": ("Skipped", "已跳过"),
    "unavailable": ("Unavailable", "不可用"),
    "not_started": ("Not started", "未开始"),
    "ready": ("Ready", "已就绪"),
    "running": ("Running", "进行中"),
    "needs_review": ("Needs review", "需要评审"),
    "blocked": ("Blocked", "受阻"),
    "failed": ("Failed", "失败"),
    "stale": ("Stale", "已过期"),
    "candidate": ("Candidate", "候选"),
    "reference_only": ("Reference only", "仅参考"),
    "selected": ("Selected", "已选定"),
    "generated": ("Generated", "已生成"),
    "accepted": ("Accepted", "已批准"),
    "reviewable": ("Reviewable", "可审查"),
    "design": ("Design", "设计中"),
    "building": ("Building", "生成中"),
    "experimental": ("Experimental", "实验性"),
}


def copy(language: str, key: str, default: str | None = None) -> str:
    """Return localized copy without exposing internal keys as UI fallback."""
    pair = _COPY.get(key)
    if pair is None:
        return default or key.replace("_", " ")
    return pair[1] if language == "zh" else pair[0]


def action_label(language: str, label: Any, key: Any = None) -> str:
    """Localize all known workflow action labels from either catalog direction."""
    value = str(label or key or "")
    english = _REVERSE_ACTION_LABELS.get(value, value)
    if language == "zh":
        return _ACTION_LABELS.get(english, value)
    return english


def action_labels(label: Any, key: Any = None) -> dict[str, str]:
    return {"en": action_label("en", label, key), "zh": action_label("zh", label, key)}


def stage_label(language: str, stage_id: Any, fallback: Any = None) -> str:
    value = str(stage_id or "")
    pair = _STAGE_LABELS.get(value)
    if pair is None:
        return str(fallback or value.replace("_", " ").title() or "Workflow")
    return pair[1] if language == "zh" else pair[0]


def status_label(language: str, status: Any) -> str:
    value = str(status or "unavailable")
    pair = _STATUS_LABELS.get(value)
    if pair is None:
        return value.replace("_", " ")
    return pair[1] if language == "zh" else pair[0]


def localize_action(action: dict[str, Any], language: str) -> dict[str, Any]:
    """Attach both language variants and select one presentation label."""
    result = dict(action)
    labels = action_labels(result.get("label"), result.get("key"))
    result["label_i18n"] = labels
    result["label"] = labels["zh" if language == "zh" else "en"]
    return result
