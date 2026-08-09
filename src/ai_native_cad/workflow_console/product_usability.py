"""Product-language Home, recovery, and Agent-first Workflow projections."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_home_view_model(
    backend: Any,
    works: list[dict[str, Any]],
    *,
    language: str = "en",
) -> dict[str, Any]:
    language = "zh" if language == "zh" else "en"
    readiness = backend.read_product_readiness()
    recent = []
    for item in works:
        work_id = item.get("work_id")
        if not isinstance(work_id, str):
            continue
        try:
            detail = backend.get_work_detail(work_id)
        except (FileNotFoundError, ValueError):
            continue
        entity = _dict(detail.get("entity_state"))
        references = [value for value in entity.get("artifact_references", []) if isinstance(value, dict)]
        recovery = build_recovery_projection(
            backend,
            work_id,
            entity,
            references,
            language=language,
        )
        phase, state, action = _compact_work_state(entity, references, recovery, language)
        recent.append(
            {
                "work_id": work_id,
                "title": item.get("title") or work_id,
                "phase": phase,
                "state": state,
                "needs_user_action": recovery is not None or state in {"ready_for_review", "ready_to_design"},
                "next_action": recovery.get("recommended_action", {}).get("label") if recovery else action,
                "updated": _relative_time(item.get("updated_at"), language),
                "work_classification": item.get("work_classification") or "user",
                "example_classification": item.get("example_classification"),
            }
        )
    live = next((item for item in works if item.get("example_classification") == "live_agent_example"), None)
    golden = next((item for item in works if item.get("example_classification") == "product_golden"), None)
    return {
        "start": {
            "new_design": "新建设计" if language == "zh" else "New Design",
            "live_example": "开始产品示例" if language == "zh" else "Start Product Example",
            "live_example_label": "Live Agent · Experimental",
            "completed_example": "打开已完成示例" if language == "zh" else "Open Completed Example",
            "completed_example_label": "可复现脚本快照" if language == "zh" else "Reproducible scripted snapshot",
        },
        "environment": readiness,
        "product_examples": [
            {
                "key": "live_agent",
                "work_id": live.get("work_id") if live else None,
                "title": "真实 Agent 示例" if language == "zh" else "Real Agent example",
                "badge": "实验性 · 结果可变" if language == "zh" else "Experimental · variable",
                "demonstrates": "观察已配置 Provider 如何选择动作、提问、修复或诚实停止。" if language == "zh" else "See the configured provider choose actions, ask questions, repair, or stop honestly.",
                "will_see": "Agent 输出、受控执行、验证证据和恢复建议" if language == "zh" else "Agent Output, controlled execution, validation evidence, and recovery guidance",
                "can_try": "从真实请求开始并继续同一个 Work" if language == "zh" else "Start from a real request and continue the same Work",
                "requirements": "需要已验证的 Provider；生成几何还需要本地 CAD 执行环境。" if language == "zh" else "Requires a verified provider; geometry also needs local CAD execution.",
                "action": "打开示例" if live and language == "zh" else "Open example" if live else "开始产品示例" if language == "zh" else "Start Product Example",
            },
            {
                "key": "completed_golden",
                "work_id": golden.get("work_id") if golden else None,
                "title": "已完成产品示例" if language == "zh" else "Completed product example",
                "badge": "可复现 · 无需 Provider" if language == "zh" else "Reproducible · no provider",
                "demonstrates": "检查一个已知几何结果，并理解可审查、接受和修订的区别。" if language == "zh" else "Inspect known geometry and understand reviewable, accepted, and revised states.",
                "will_see": "几何预览、测量证据、验证状态和明确接受操作" if language == "zh" else "Geometry preview, measured evidence, validation state, and explicit acceptance",
                "can_try": "检查模型、接受结果或创建带谱系的修订" if language == "zh" else "Inspect the model, accept it, or create a traced revision",
                "requirements": "无需外部 Provider 凭据。" if language == "zh" else "No external provider credential required.",
                "action": "打开示例" if golden and language == "zh" else "Open example" if golden else "创建示例" if language == "zh" else "Create example",
            },
        ],
        "recent_works": recent,
    }


def build_agent_output_projection(
    backend: Any,
    work_id: str,
    references: list[dict[str, Any]],
    *,
    language: str,
) -> dict[str, Any]:
    """Project durable Agent responses, observations, and user recovery turns."""

    language = "zh" if language == "zh" else "en"
    items: list[dict[str, Any]] = []
    provider: dict[str, Any] = {}
    for reference in references:
        checkpoint = reference.get("checkpoint")
        payload = _read_reference(backend, work_id, reference)
        if checkpoint == "agent_output":
            for record in payload.get("records", []):
                if not isinstance(record, dict):
                    continue
                identity = _dict(record.get("provider_identity"))
                if identity:
                    provider = identity
                action = str(record.get("action") or "invalid_response")
                items.append({
                    "kind": "agent_response",
                    "sequence": record.get("sequence"),
                    "title": _agent_action_label(action, language),
                    "action": action,
                    "summary": record.get("summary") or record.get("reason"),
                    "questions": record.get("questions") if isinstance(record.get("questions"), list) else [],
                    "assumptions": record.get("assumptions") if isinstance(record.get("assumptions"), list) else [],
                    "stop_reason": record.get("stop_reason"),
                    "structured": record,
                })
        elif checkpoint == "agent_activity":
            for record in payload.get("records", []):
                if not isinstance(record, dict):
                    continue
                observation = record.get("observation")
                if observation:
                    items.append({
                        "kind": "system_observation",
                        "sequence": record.get("step"),
                        "title": "系统观察" if language == "zh" else "System observation",
                        "summary": str(observation).replace("_", " "),
                        "codes": record.get("codes") if isinstance(record.get("codes"), list) else [],
                        "structured": record,
                    })
        elif reference.get("trust_role") == "accepted_input":
            items.append({
                "kind": "user_answer",
                "title": "你的回答" if language == "zh" else "Your answer",
                "summary": payload.get("answer"),
                "question": payload.get("question"),
                "field": payload.get("field"),
                "structured": payload,
            })
        elif checkpoint == "product_design_routing":
            episode = _dict(payload.get("episode"))
            if episode:
                items.append({
                    "kind": "attempt_result",
                    "title": "尝试结果" if language == "zh" else "Attempt result",
                    "summary": _stop_reason_text(episode.get("stop_reason"), language),
                    "stop_reason": episode.get("stop_reason"),
                    "status": episode.get("status"),
                    "structured": episode,
                })
    # Older episodes did not register the exchange file. Retain an honest
    # result-level history and avoid inventing an Agent transcript.
    last_action = next((item.get("action") for item in reversed(items) if item.get("kind") == "agent_response"), None)
    last_agent_summary = next((item.get("summary") for item in reversed(items) if item.get("kind") == "agent_response" and item.get("summary")), None)
    last_observation = next((item.get("summary") for item in reversed(items) if item.get("kind") == "system_observation"), None)
    return {
        "title": "Agent 输出" if language == "zh" else "Agent Output",
        "description": "按发生顺序显示 Agent 的外部动作、系统观察和恢复输入。" if language == "zh" else "External Agent actions, system observations, and recovery input in order.",
        "items": items,
        "provider_identity": provider,
        "last_action": last_action,
        "last_agent_summary": last_agent_summary,
        "last_observation": last_observation,
        "private_reasoning_exposed": False,
        "credential_material_exposed": False,
        "has_external_responses": any(item.get("kind") == "agent_response" for item in items),
    }


def build_recovery_projection(
    backend: Any,
    work_id: str,
    entity: dict[str, Any],
    references: list[dict[str, Any]],
    *,
    language: str,
    agent_output: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    language = "zh" if language == "zh" else "en"
    question_reference = _unanswered_question_reference(references)
    if question_reference is not None:
        question_payload = _read_reference(backend, work_id, question_reference)
        questions = question_payload.get("questions") if isinstance(question_payload.get("questions"), list) else []
        question = questions[0] if questions and isinstance(questions[0], dict) else {}
        return _recovery(
            category="missing_information",
            owner="user",
            title=("需要你的输入" if language == "zh" else "Need your input"),
            summary=str(question.get("question") or ("CadFlow 需要一个设计细节才能继续。" if language == "zh" else "CadFlow needs one design detail before continuing.")),
            why=str(question_payload.get("why_it_matters") or ("这个信息会实质影响设计。" if language == "zh" else "This detail materially affects the design.")),
            action_key="answer_question",
            action_label=("回答问题" if language == "zh" else "Answer question"),
            destination="workbench_clarification",
            retryable=False,
            language=language,
            extra={
                "question_artifact_id": question_reference.get("artifact_id"),
                "run_id": question_reference.get("run_id"),
                "part_job_id": question_reference.get("part_job_id"),
                "questions": questions,
                "technical_reason": "user_input_required",
                "last_agent_action": (agent_output or {}).get("last_action"),
                "last_observation": (agent_output or {}).get("last_observation"),
                "history": (agent_output or {}).get("items", []),
                "provider_identity": (agent_output or {}).get("provider_identity", {}),
            },
        )

    has_reviewable = any(
        item.get("trust_role") == "reviewable_result"
        and item.get("checkpoint") == "reviewable_result"
        for item in references
    )
    metadata = _dict(entity.get("metadata"))
    product_agent_route = metadata.get("example_classification") == "live_agent_example" or metadata.get("product_entry") == "new_design"
    route = _latest_route_outcome(backend, work_id, references)
    readiness = backend.read_provider_readiness() if product_agent_route else {"ready": True}
    if product_agent_route and not has_reviewable and not readiness.get("ready") and not route.get("stop_reason"):
        auth_failed = readiness.get("last_error_category") == "auth_failed"
        return _recovery(
            category="provider_auth_failed" if auth_failed else "provider_not_configured",
            owner="configuration",
            title=(
                "AI Provider 身份验证失败" if language == "zh" and auth_failed
                else "AI Provider 设置不可用" if language == "zh"
                else "AI Provider authentication failed" if auth_failed
                else "AI Provider setup required"
            ),
            summary=(
                "请检查 API Key 并重新测试连接。" if language == "zh" and auth_failed
                else "连接 AI Provider 后即可继续此设计。" if language == "zh"
                else "Check the API key and test the connection." if auth_failed
                else "Connect an AI provider to continue this design."
            ),
            why=("当前 Provider 设置尚未通过有效连接验证。" if language == "zh" else "The current provider settings do not have successful saved connection evidence."),
            action_key="open_settings",
            action_label=("打开设置" if language == "zh" else "Open Settings"),
            destination="config",
            retryable=False,
            language=language,
        )

    stop_reason = route.get("stop_reason")
    if not stop_reason or route.get("status") == "completed":
        return None
    sandbox_codes = _latest_execution_codes(backend, work_id, references)
    if "sandbox_unavailable" in sandbox_codes or stop_reason == "sandbox_unavailable":
        return _recovery(
            category="environment_unavailable",
            owner="environment",
            title=("本机暂时无法执行 Agent 生成的 CAD" if language == "zh" else "Agent-generated CAD cannot run on this machine yet"),
            summary=("请检查本地 CAD 执行环境。" if language == "zh" else "Check the local CAD execution environment."),
            why=("隔离执行环境不可用或未通过验证。" if language == "zh" else "The isolated execution environment is unavailable or not verified."),
            action_key="check_environment",
            action_label=("检查本地执行环境" if language == "zh" else "Check local execution"),
            destination="config#local-execution",
            retryable=False,
            language=language,
        )
    if stop_reason == "unsupported_capability":
        return _recovery(
            category="unsupported_capability",
            owner="unsupported",
            title=("当前设计超出 CadFlow 支持范围" if language == "zh" else "This design requires a capability CadFlow does not currently support"),
            summary=("重复同一操作无法解决；请修改设计要求。" if language == "zh" else "Repeating the same action will not solve it. Modify the request."),
            why=("当前产品能力无法完成此设计路径。" if language == "zh" else "The current product capability cannot complete this design path."),
            action_key="modify_request",
            action_label=("修改设计" if language == "zh" else "Modify request"),
            destination="workbench_revision",
            retryable=False,
            language=language,
        )
    if stop_reason in {"validation_exhausted", "execution_exhausted"}:
        return _recovery(
            category=stop_reason,
            owner="cadflow",
            title=("模型未通过几何验证" if language == "zh" else "The model did not pass geometry validation"),
            summary=("Agent 已尝试修复，但仍未达到可审查状态。" if language == "zh" else "The Agent tried to repair the model but it is still not reviewable."),
            why=("本次尝试已用尽允许的验证或执行次数。" if language == "zh" else "This attempt exhausted its validation or execution allowance."),
            action_key="modify_request",
            action_label=("修改设计" if language == "zh" else "Revise design request"),
            destination="workbench_revision",
            retryable=False,
            language=language,
        )
    if stop_reason == "provider_failure":
        return _recovery(
            category="provider_failure",
            owner="cadflow",
            title=("AI Provider 请求暂时失败" if language == "zh" else "The AI provider request failed temporarily"),
            summary=("你的设计和现有证据已保留，可以重试。" if language == "zh" else "Your design and existing evidence were preserved; you can retry."),
            why=("Provider 请求未完成，CadFlow 没有伪造结果。" if language == "zh" else "The provider request did not complete and CadFlow did not fabricate a result."),
            action_key="retry_agent",
            action_label=("重试" if language == "zh" else "Retry"),
            destination="workbench",
            retryable=True,
            language=language,
        )
    if stop_reason == "budget_exhausted":
        return _recovery(
            category="budget_exhausted",
            owner="cadflow",
            title=("本次 Agent 尝试已达到预算上限" if language == "zh" else "This Agent attempt reached its budget"),
            summary=("现有证据已保留；可以开始一个新的有界尝试。" if language == "zh" else "Existing evidence was preserved; you can start another bounded attempt."),
            why=("CadFlow 按既定资源预算安全停止。" if language == "zh" else "CadFlow stopped safely at the declared resource budget."),
            action_key="retry_agent",
            action_label=("重试" if language == "zh" else "Retry"),
            destination="workbench",
            retryable=True,
            language=language,
        )
    if stop_reason == "insufficient_context":
        output = agent_output or {}
        return _recovery(
            category="insufficient_context",
            owner="user",
            title=("仍需要补充设计信息" if language == "zh" else "More design context is still needed"),
            summary=str(output.get("last_agent_summary") or ("请补充剩余约束后继续。" if language == "zh" else "Add the remaining constraint before continuing.")),
            why=("Agent 已明确停止，因为当前输入仍不足以安全完成设计。" if language == "zh" else "The Agent explicitly stopped because the current input was still insufficient to complete the design safely."),
            action_key="modify_request",
            action_label=("补充设计要求" if language == "zh" else "Add design context"),
            destination="workbench_revision",
            retryable=False,
            language=language,
            extra={
                "technical_reason": stop_reason,
                "last_agent_action": output.get("last_action"),
                "last_observation": output.get("last_observation"),
                "history": output.get("items", []),
                "provider_identity": output.get("provider_identity", {}),
            },
        )
    technical_reason = _stop_reason_text(stop_reason, language)
    output = agent_output or {}
    return _recovery(
        category=str(stop_reason),
        owner="cadflow",
        title=(f"设计已停止：{technical_reason}" if language == "zh" else f"Design stopped: {technical_reason}"),
        summary=("本次尝试已保留真实 Agent 输出和系统证据。" if language == "zh" else "The actual Agent output and system evidence from this attempt were preserved."),
        why=(f"停止原因是 {technical_reason}；未通过本地检查的结果不会发布。" if language == "zh" else f"The typed stop reason was {technical_reason}; output that did not pass local checks was not published."),
        action_key="view_details",
        action_label=("查看技术详情" if language == "zh" else "View technical details"),
        destination="advanced",
        retryable=False,
        language=language,
        extra={
            "technical_reason": stop_reason,
            "last_agent_action": output.get("last_action"),
            "last_observation": output.get("last_observation"),
            "history": output.get("items", []),
            "provider_identity": output.get("provider_identity", {}),
        },
    )


def build_agent_first_workflow_projection(
    overview: dict[str, Any],
    *,
    language: str,
) -> dict[str, Any]:
    language = "zh" if language == "zh" else "en"
    events = [item for item in _dict(overview.get("transformation")).get("events", []) if isinstance(item, dict)]
    by_key = {item.get("key"): item for item in events}
    recovery = overview.get("recovery") if isinstance(overview.get("recovery"), dict) else None
    reviewable = _dict(overview.get("current_result")).get("status") in {"reviewable", "accepted"}
    accepted = _dict(overview.get("current_result")).get("accepted") is True
    stages = [
        _stage("intent", "INTENT", "意图" if language == "zh" else "Intent", by_key.get("request_received"), language),
        _stage("design", "DESIGN", "设计" if language == "zh" else "Design", by_key.get("design_candidate"), language),
        _stage("build_evaluate", "BUILD & EVALUATE", "构建与评估" if language == "zh" else "Build & Evaluate", by_key.get("geometry_built"), language),
        {
            **_stage("accept_deliver", "ACCEPT & DELIVER", "接受与交付" if language == "zh" else "Accept & Deliver", by_key.get("ready_review"), language),
            "status": "completed" if accepted else "needs_review" if reviewable else "not_started",
        },
    ]
    if recovery:
        active = next((stage for stage in stages if stage["status"] != "completed"), stages[-1])
        active["status"] = "blocked"
        active["short_summary"] = recovery.get("summary")
    selected = next((stage for stage in stages if stage["status"] in {"blocked", "needs_review", "running"}), stages[-1])
    return {
        "projection_mode": "agent_first",
        "stages": stages,
        "selected_stage": selected,
        "workflow_graph": {"main": stages, "parts": [], "review": []},
        "current_conclusion": {
            "title": recovery.get("title") if recovery else _dict(overview.get("recommendation")).get("label"),
            "summary": recovery.get("summary") if recovery else _dict(overview.get("recommendation")).get("summary"),
            "rationale": recovery.get("why_it_stopped") if recovery else None,
        },
    }


def _compact_work_state(
    entity: dict[str, Any],
    references: list[dict[str, Any]],
    recovery: dict[str, Any] | None,
    language: str,
) -> tuple[str, str, str]:
    if recovery:
        phase = "设计" if language == "zh" else "Design"
        return phase, recovery["title"], recovery["recommended_action"]["label"]
    if any(item.get("trust_role") == "reviewable_result" for item in references):
        return (
            "接受与交付" if language == "zh" else "Accept & Deliver",
            "可审查" if language == "zh" else "Ready for review",
            "审查生成结果" if language == "zh" else "Review the generated result",
        )
    if entity.get("part_jobs"):
        return (
            "设计" if language == "zh" else "Design",
            "准备设计" if language == "zh" else "Ready to design",
            "开始设计" if language == "zh" else "Start design",
        )
    return (
        "意图" if language == "zh" else "Intent",
        "等待要求" if language == "zh" else "Needs a request",
        "描述要创建的内容" if language == "zh" else "Describe what you want to create",
    )


def _unanswered_question_reference(references: list[dict[str, Any]]) -> dict[str, Any] | None:
    answers = {
        source
        for item in references
        if item.get("trust_role") == "accepted_input"
        for source in item.get("source_artifact_ids", [])
        if isinstance(source, str)
    }
    return next(
        (
            item
            for item in reversed(references)
            if item.get("checkpoint") == "clarification_decision"
            and item.get("validation_status") == "user_input_required"
            and item.get("artifact_id") not in answers
        ),
        None,
    )


def _latest_route_outcome(backend: Any, work_id: str, references: list[dict[str, Any]]) -> dict[str, Any]:
    reference = next(
        (item for item in reversed(references) if item.get("checkpoint") == "product_design_routing"),
        None,
    )
    payload = _read_reference(backend, work_id, reference)
    return _dict(payload.get("episode"))


def _latest_execution_codes(backend: Any, work_id: str, references: list[dict[str, Any]]) -> set[str]:
    reference = next(
        (item for item in reversed(references) if item.get("checkpoint") == "execution_observation"),
        None,
    )
    payload = _read_reference(backend, work_id, reference)
    return {str(item) for item in payload.get("codes", []) if isinstance(item, str)}


def _read_reference(backend: Any, work_id: str, reference: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(reference, dict) or not isinstance(reference.get("artifact_id"), str):
        return {}
    try:
        payload = backend.read_work_artifact_reference(work_id, reference["artifact_id"])
    except (FileNotFoundError, ValueError):
        return {}
    return _dict(payload.get("content"))


def _recovery(
    *,
    category: str,
    owner: str,
    title: str,
    summary: str,
    why: str,
    action_key: str,
    action_label: str,
    destination: str,
    retryable: bool,
    language: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "resolution_owner": owner,
        "title": title,
        "summary": summary,
        "why_it_stopped": why,
        "recommended_action": {"key": action_key, "label": action_label, "destination": destination},
        "secondary_actions": [
            {"key": "view_details", "label": "查看技术详情" if language == "zh" else "View technical details", "destination": "advanced"}
        ],
        "retryable": retryable,
        "destination": destination,
        "technical_details_available": True,
        **(extra or {}),
    }


def _stage(key: str, group: str, label: str, event: dict[str, Any] | None, language: str) -> dict[str, Any]:
    complete = isinstance(event, dict) and event.get("status") == "completed"
    return {
        "stage_id": key,
        "stage_name": label,
        "label": label,
        "group": group,
        "kind": "stage",
        "status": "completed" if complete else "not_started",
        "short_summary": event.get("label") if isinstance(event, dict) else label,
        "inputs": [],
        "outputs": [],
        "available_actions": [],
        "guidance": {},
    }


def _relative_time(value: Any, language: str) -> str:
    if not isinstance(value, str):
        return "—"
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        seconds = max(0, int((datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()))
    except (ValueError, TypeError):
        return value
    if seconds < 60:
        return "刚刚" if language == "zh" else "just now"
    if seconds < 3600:
        count = seconds // 60
        return f"{count} 分钟前" if language == "zh" else f"{count} min ago"
    if seconds < 86400:
        count = seconds // 3600
        return f"{count} 小时前" if language == "zh" else f"{count} hr ago"
    count = seconds // 86400
    return f"{count} 天前" if language == "zh" else f"{count} days ago"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _agent_action_label(action: str, language: str) -> str:
    labels = {
        "request_context": ("请求上下文", "Requested context"),
        "ask_user": ("提出问题", "Asked a question"),
        "create_contract": ("创建结构化设计", "Created a structured design"),
        "patch_contract": ("修改结构化设计", "Revised the structured design"),
        "submit_contract": ("提交结构化设计", "Submitted the structured design"),
        "request_validation": ("请求验证", "Requested validation"),
        "create_model_program": ("准备模型程序", "Prepared a model program"),
        "patch_model_program": ("修复模型程序", "Repaired the model program"),
        "request_execution": ("请求受控执行", "Requested controlled execution"),
        "inspect_observation": ("检查执行结果", "Inspected the execution result"),
        "stop": ("停止", "Stopped"),
        "invalid_response": ("响应未通过动作合约", "Response failed the action contract"),
    }
    zh, en = labels.get(action, (action.replace("_", " "), action.replace("_", " ").title()))
    return zh if language == "zh" else en


def _stop_reason_text(reason: Any, language: str) -> str:
    key = str(reason or "unknown_stop")
    labels = {
        "user_input_required": ("等待用户输入", "waiting for user input"),
        "unsupported_capability": ("能力暂不支持", "unsupported capability"),
        "provider_failure": ("Provider 请求失败", "provider request failure"),
        "policy_blocked": ("动作合约或安全策略阻止", "action contract or safety policy block"),
        "validation_exhausted": ("验证尝试已用尽", "validation attempts exhausted"),
        "execution_exhausted": ("执行尝试已用尽", "execution attempts exhausted"),
        "budget_exhausted": ("有界预算已用尽", "bounded budget exhausted"),
        "sandbox_unavailable": ("隔离执行环境不可用", "isolated execution unavailable"),
        "completed": ("已完成", "completed"),
    }
    zh, en = labels.get(key, (key.replace("_", " "), key.replace("_", " ")))
    return zh if language == "zh" else en
