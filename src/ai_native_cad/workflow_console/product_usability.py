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
    scope_kind: str | None = None,
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
        elif checkpoint in {"product_design_routing", "work_design_routing"}:
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
        "empty_message": (
            "此零件尝试尚无 Agent 输出。"
            if language == "zh" and scope_kind == "part"
            else "No Part Agent output yet."
            if scope_kind == "part"
            else "Work 设计尚无 Agent 输出。"
            if language == "zh" and scope_kind == "work_design"
            else "No Work Design Agent output yet."
            if scope_kind == "work_design"
            else "Agent 输出将在首次外部响应后显示。"
            if language == "zh"
            else "Agent Output will appear after the first external response."
        ),
        "scope_kind": scope_kind or "work",
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
    backend: Any,
    work_id: str,
    work: dict[str, Any],
    overview: dict[str, Any],
    *,
    selected_node_id: str | None = None,
    language: str,
) -> dict[str, Any]:
    """Project one current Work into a small, evidence-backed state graph.

    The graph is presentation data only.  Work, Part Job, Run, artifact, and
    accepted-result records remain the source of truth; selection is supplied
    by the caller and is never persisted here.
    """

    language = "zh" if language == "zh" else "en"
    entity = _dict(work.get("entity_state"))
    references = [
        dict(item)
        for item in entity.get("artifact_references", [])
        if isinstance(item, dict)
    ]
    overview_parts = {
        str(item.get("part_job_id")): item
        for item in overview.get("part_jobs", [])
        if isinstance(item, dict) and item.get("part_job_id")
    }
    recovery = overview.get("recovery") if isinstance(overview.get("recovery"), dict) else None
    phase_groups = [
        {"id": "intent", "label": "意图" if language == "zh" else "Intent", "order": 0},
        {"id": "design", "label": "设计" if language == "zh" else "Design", "order": 1},
        {"id": "build_evaluate", "label": "构建与评估" if language == "zh" else "Build & Evaluate", "order": 2},
        {"id": "accept_deliver", "label": "接受与交付" if language == "zh" else "Accept & Deliver", "order": 3},
    ]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    edge_keys: set[tuple[str, str, str]] = set()

    def scoped_references(
        part_job_id: str | None,
        run_id: str | None,
    ) -> list[dict[str, Any]]:
        """Return only evidence owned by one durable Work/Part Run scope."""

        return [
            item
            for item in references
            if item.get("part_job_id") == part_job_id
            and (run_id is None or item.get("run_id") == run_id)
        ]

    def scoped_agent_output(
        part_job_id: str | None,
        run_id: str | None,
    ) -> dict[str, Any]:
        return build_agent_output_projection(
            backend,
            work_id,
            scoped_references(part_job_id, run_id),
            language=language,
            scope_kind="part" if part_job_id else "work_design",
        )

    def scoped_recovery(
        part_job_id: str | None,
        run_id: str | None,
        output: dict[str, Any],
    ) -> dict[str, Any] | None:
        scoped = scoped_references(part_job_id, run_id)
        # Provider readiness is Work-level capability context, but it is not
        # evidence for every Part attempt.  A selected attempt receives a
        # recovery projection only from its own durable question/route record.
        if not any(
            item.get("checkpoint")
            in {"clarification_decision", "product_design_routing", "work_design_routing"}
            for item in scoped
        ):
            return None
        projected = build_recovery_projection(
            backend,
            work_id,
            entity,
            scoped,
            language=language,
            agent_output=output,
        )
        if not isinstance(projected, dict):
            return None
        route = next(
            (
                item
                for item in reversed(scoped)
                if item.get("checkpoint")
                in {"clarification_decision", "product_design_routing", "work_design_routing"}
            ),
            {},
        )
        return {
            **projected,
            "work_id": work_id,
            "part_job_id": part_job_id,
            "run_id": run_id or route.get("run_id"),
            "artifact_id": route.get("artifact_id"),
        }

    def design_evidence(
        part_job_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        reference = next(
            (
                item
                for item in reversed(scoped_references(part_job_id, run_id))
                if item.get("checkpoint") == "design_brief"
            ),
            None,
        )
        payload = _read_reference(backend, work_id, reference)
        content = _dict(payload.get("content"))
        return content or payload

    def add_node(node: dict[str, Any]) -> str:
        node_id = str(node["id"])
        if node_id not in node_ids:
            node_ids.add(node_id)
            nodes.append({
                "clickable": True,
                "selected": node_id == selected_node_id,
                **node,
            })
        return node_id

    def add_edge(source: str | None, target: str | None, edge_type: str) -> None:
        if not source or not target or source == target:
            return
        key = (source, target, edge_type)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({
            "id": f"edge:{len(edges) + 1}",
            "source": source,
            "target": target,
            "type": edge_type,
            "label": _workflow_edge_label(edge_type, language),
        })

    request_id = add_node({
        "id": "work:request",
        "label": "用户请求" if language == "zh" else "User request",
        "kind": "request",
        "status": "completed" if _dict(overview.get("user_input")).get("durable") else "not_started",
        "group": "intent",
        "summary": (
            _dict(overview.get("user_input")).get("original_request")
            or _dict(overview.get("objective")).get("summary")
        ),
        "detail": {
            "type": "request",
            "user_input": _dict(overview.get("user_input")),
            "objective": _dict(overview.get("objective")),
        },
    })

    accepted = _dict(entity.get("accepted_part_results"))
    raw_jobs = [item for item in entity.get("part_jobs", []) if isinstance(item, dict)]
    work_design = _dict(entity.get("work_design"))
    work_design_status = str(work_design.get("status") or "not_started")
    work_design_node_id: str | None = None
    decomposition_node_id: str | None = None
    work_path_node_ids: list[str] = []
    if work_design_status != "not_started" or not raw_jobs:
        work_design_run_id = (
            str(work_design.get("run_id"))
            if isinstance(work_design.get("run_id"), str)
            else None
        )
        work_design_output = scoped_agent_output(None, work_design_run_id)
        work_design_recovery = scoped_recovery(
            None, work_design_run_id, work_design_output
        )
        work_design_node_id = add_node({
            "id": "work:design",
            "label": "Work 设计" if language == "zh" else "Work Design",
            "kind": "work_design",
            "status": (
                "completed" if work_design_status == "completed"
                else "blocked" if work_design_status in {"user_input_required", "blocked"}
                else "not_started" if work_design_status == "not_started"
                else "in_progress"
            ),
            "group": "design",
            "run_id": work_design.get("run_id"),
            "summary": (
                _dict(overview.get("work_design")).get("concept_summary")
                or ("理解整个目标并决定零件边界。" if language == "zh" else "Understand the whole objective and decide Part boundaries.")
            ),
            "detail": {
                "type": "work_design",
                "work_design": _dict(overview.get("work_design")),
                "agent_output": work_design_output,
                "recovery": work_design_recovery or {},
            },
        })
        work_path_node_ids.append(work_design_node_id)
        add_edge(request_id, work_design_node_id, "designed")

        work_artifact_nodes: dict[str, str] = {}
        work_tail_id = work_design_node_id
        for reference in references:
            if reference.get("part_job_id") is not None:
                continue
            if reference.get("checkpoint") not in {"clarification_decision", "work_design_routing"}:
                continue
            projected = _workflow_reference_node(
                backend,
                work_id,
                reference,
                overview,
                {},
                language,
                all_references=references,
            )
            if projected is None:
                continue
            node_id = add_node(projected["node"])
            work_path_node_ids.append(node_id)
            linked = False
            for source_artifact_id in reference.get("source_artifact_ids", []):
                source_node_id = work_artifact_nodes.get(str(source_artifact_id))
                if source_node_id:
                    add_edge(source_node_id, node_id, projected["edge_type"])
                    linked = True
            if not linked:
                add_edge(work_tail_id, node_id, projected["edge_type"])
            artifact_id = reference.get("artifact_id")
            if isinstance(artifact_id, str):
                work_artifact_nodes[artifact_id] = node_id
            work_tail_id = node_id

        if work_design_status == "completed":
            decomposition_node_id = add_node({
                "id": "work:decomposition",
                "label": "零件分解" if language == "zh" else "Part decomposition",
                "kind": "decomposition",
                "status": "completed",
                "group": "design",
                "run_id": work_design.get("run_id"),
                "summary": (
                    f"{len(raw_jobs)} 个生成零件任务" if language == "zh"
                    else f"{len(raw_jobs)} generated Part Job{'s' if len(raw_jobs) != 1 else ''}"
                ),
                "detail": {
                    "type": "decomposition",
                    "work_design": _dict(overview.get("work_design")),
                    "agent_output": work_design_output,
                },
            })
            work_path_node_ids.append(decomposition_node_id)
            add_edge(work_design_node_id, decomposition_node_id, "decomposed")
    compatibility_sources = {
        str(item.get("source") or "")
        for item in raw_jobs
        if isinstance(item, dict)
    }
    compatibility_mode = bool(
        compatibility_sources
        & {"assembly_plan", "legacy", "legacy_acceptance", "manifest"}
    )
    for raw_job in raw_jobs:
        part_job_id = raw_job.get("part_job_id") or raw_job.get("part_id")
        if not isinstance(part_job_id, str) or not part_job_id:
            continue
        part = _dict(overview_parts.get(part_job_id))
        attempts = [item for item in raw_job.get("attempts", []) if isinstance(item, dict)]
        active_run_id = raw_job.get("active_attempt_run_id") or (attempts[-1].get("run_id") if attempts else None)
        active_output = scoped_agent_output(part_job_id, active_run_id)
        active_recovery = scoped_recovery(
            part_job_id, active_run_id, active_output
        )
        part_status = _workflow_part_status(part, active_recovery, part_job_id)
        part_node_id = add_node({
            "id": f"part:{part_job_id}",
            "label": part.get("name") or part_job_id.replace("_", " ").title(),
            "kind": "part",
            "status": part_status,
            "group": "design",
            "part_job_id": part_job_id,
            "run_id": active_run_id,
            "summary": part.get("role") or raw_job.get("role") or ("零件任务" if language == "zh" else "Part Job"),
            "detail": {
                "type": "part_job",
                "part": part or raw_job,
                "prompt": (
                    _read_run_prompt(backend, work_id, str(active_run_id))
                    if isinstance(active_run_id, str)
                    else None
                ),
                "agent_design": (
                    design_evidence(part_job_id, str(active_run_id))
                    if isinstance(active_run_id, str)
                    else {}
                ),
                "agent_output": active_output,
                "recovery": active_recovery or {},
            },
        })
        add_edge(
            decomposition_node_id or work_design_node_id or request_id,
            part_node_id,
            "imported" if compatibility_mode else ("decomposed" if len(raw_jobs) > 1 else "created"),
        )
        branch = {
            "part_job_id": part_job_id,
            "label": part.get("name") or part_job_id.replace("_", " ").title(),
            "role": part.get("role") or raw_job.get("role"),
            "part_node_id": part_node_id,
            "attempts": [],
        }
        for index, attempt in enumerate(attempts, start=1):
            run_id = attempt.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                continue
            run_references = [item for item in references if item.get("part_job_id") == part_job_id and item.get("run_id") == run_id]
            prompt = _read_run_prompt(backend, work_id, run_id)
            parent_run_id = attempt.get("parent_run_id")
            source_result_id = attempt.get("source_result_id")
            revision_provenance = isinstance(parent_run_id, str) and bool(parent_run_id)
            attempt_output = scoped_agent_output(part_job_id, run_id)
            attempt_recovery = scoped_recovery(
                part_job_id, run_id, attempt_output
            )
            attempt_status = _workflow_attempt_status(
                run_id,
                active_run_id,
                run_references,
                accepted.get(part_job_id),
                attempt_recovery,
            )
            attempt_node_id = add_node({
                "id": f"attempt:{part_job_id}:{run_id}",
                "label": (f"设计尝试 #{index}" if language == "zh" else f"Design attempt #{index}"),
                "kind": "attempt",
                "status": attempt_status,
                "group": "design",
                "part_job_id": part_job_id,
                "run_id": run_id,
                "summary": (
                    ("从较早结果开始的修订" if language == "zh" else "Revision from an earlier result")
                    if revision_provenance
                    else ("当前设计尝试" if run_id == active_run_id and language == "zh" else "Current design attempt" if run_id == active_run_id else "较早尝试" if language == "zh" else "Earlier attempt")
                ),
                "detail": {
                    "type": "attempt",
                    "attempt": dict(attempt),
                    "attempt_index": index,
                    "prompt": prompt,
                    "parent_run_id": parent_run_id,
                    "source_result_id": source_result_id,
                    "snapshot_run_id": run_id,
                    "part": part or raw_job,
                    "agent_design": design_evidence(part_job_id, run_id),
                    "agent_output": attempt_output,
                    "recovery": attempt_recovery or {},
                },
            })
            result_source_node = (
                f"result:{source_result_id}"
                if isinstance(source_result_id, str) and f"result:{source_result_id}" in node_ids
                else None
            )
            parent_attempt_node = (
                f"attempt:{part_job_id}:{parent_run_id}"
                if isinstance(parent_run_id, str) and f"attempt:{part_job_id}:{parent_run_id}" in node_ids
                else None
            )
            add_edge(
                result_source_node or parent_attempt_node or part_node_id,
                attempt_node_id,
                "revised" if revision_provenance else "attempted",
            )
            attempt_node_ids = [attempt_node_id]
            artifact_nodes: dict[str, str] = {}
            for reference in run_references:
                projected = _workflow_reference_node(
                    backend,
                    work_id,
                    reference,
                    overview,
                    part,
                    language,
                    all_references=references,
                )
                if projected is None:
                    continue
                node = projected["node"]
                node_id = add_node(node)
                artifact_id = reference.get("artifact_id")
                if isinstance(artifact_id, str):
                    artifact_nodes[artifact_id] = node_id
                linked = False
                for source_artifact_id in reference.get("source_artifact_ids", []):
                    source_node = artifact_nodes.get(source_artifact_id)
                    if source_node:
                        add_edge(source_node, node_id, projected["edge_type"])
                        linked = True
                if not linked:
                    add_edge(attempt_node_id, node_id, projected["edge_type"])
                attempt_node_ids.append(node_id)

            pointer = _dict(accepted.get(part_job_id))
            accepted_result_id = pointer.get("result_id")
            if pointer.get("status") == "approved" and pointer.get("attempt_run_id") == run_id and isinstance(accepted_result_id, str):
                result_node_id = artifact_nodes.get(accepted_result_id) or f"result:{accepted_result_id}"
                source_result_node = next(
                    (item for item in nodes if item.get("id") == result_node_id),
                    {},
                )
                source_result_detail = _dict(source_result_node.get("detail"))
                accepted_node_id = add_node({
                    "id": f"accepted:{part_job_id}:{accepted_result_id}",
                    "label": "已接受" if language == "zh" else "Accepted",
                    "kind": "accepted",
                    "status": "accepted",
                    "group": "accept_deliver",
                    "part_job_id": part_job_id,
                    "run_id": run_id,
                    "result_id": accepted_result_id,
                    "summary": (
                        "用户明确接受的结果；可能不是当前活动尝试。"
                        if language == "zh"
                        else "Explicitly accepted result; it may differ from the active attempt."
                    ),
                    "detail": {
                        "type": "accepted_result",
                        "accepted_pointer": pointer,
                        "result": _dict(source_result_detail.get("result"))
                        or _result_detail_for_node(
                            overview, part_job_id, accepted_result_id
                        ),
                        "preview": _dict(source_result_detail.get("preview")),
                        "agent_output": attempt_output,
                        "can_start_revision": result_node_id in node_ids,
                    },
                })
                add_edge(result_node_id if result_node_id in node_ids else attempt_node_id, accepted_node_id, "accepted")
                attempt_node_ids.append(accepted_node_id)
            branch["attempts"].append({
                "run_id": run_id,
                "attempt_index": index,
                "attempt_node_id": attempt_node_id,
                "node_ids": attempt_node_ids,
                "active": run_id == active_run_id,
                "revision": revision_provenance,
            })

        if not attempts:
            # A real Part Job can exist before its first Run.  The Part node is
            # sufficient; no future attempt/result node is fabricated.
            branch["attempts"] = []
        branches.append(branch)

    jobs_by_id = {
        str(item.get("part_job_id") or item.get("part_id")): item
        for item in raw_jobs
        if item.get("part_job_id") or item.get("part_id")
    }
    for node in nodes:
        node["work_id"] = work_id
        node["scope"] = {
            key: node.get(key)
            for key in (
                "work_id",
                "part_job_id",
                "run_id",
                "artifact_id",
                "result_id",
            )
            if node.get(key) is not None
        }
        node["interaction"] = _workflow_node_interaction(
            node,
            work_id=work_id,
            jobs_by_id=jobs_by_id,
            overview_parts=overview_parts,
            references=references,
            accepted=accepted,
            command_authority=_dict(overview.get("command_authority")),
            language=language,
        )
        node["user_state"] = _workflow_user_state(node)
        node["user_state_label"] = _workflow_user_state_label(
            node["user_state"], language
        )
        node["attention"] = "none"
    current_attention = _workflow_current_attention(nodes, branches)
    attention_ids = [str(item["node_id"]) for item in current_attention]
    for item in current_attention:
        attention_node = next(
            (node for node in nodes if node.get("id") == item.get("node_id")),
            None,
        )
        if attention_node is not None:
            attention_node["attention"] = item["kind"]

    selected = _select_workflow_node(nodes, selected_node_id, attention_ids)
    selected_id = selected.get("id") if selected else None
    for node in nodes:
        node["selected"] = node.get("id") == selected_id
    conclusion = {
        "title": recovery.get("title") if recovery else _dict(overview.get("recommendation")).get("label"),
        "summary": recovery.get("summary") if recovery else _dict(overview.get("recommendation")).get("summary"),
        "rationale": recovery.get("why_it_stopped") if recovery else None,
    }
    graph = {
        "topology": "dynamic_work_graph",
        "phase_groups": phase_groups,
        "nodes": nodes,
        "edges": edges,
        "root_node_ids": [request_id],
        "work_path_node_ids": work_path_node_ids,
        "branches": branches,
        "current_attention": current_attention,
        "selection_is_presentation_only": True,
        "state_source": "work_manifest_runs_part_jobs_artifact_references",
        "compatibility_mode": compatibility_mode,
    }
    return {
        "projection_mode": "agent_first",
        "phase_groups": phase_groups,
        "nodes": nodes,
        "edges": edges,
        # Retained as a compatibility alias for view-model consumers.  These
        # are real graph nodes, not the four phase groups.
        "stages": nodes,
        "selected_node": selected,
        "selected_stage": selected,
        "current_attention": current_attention,
        "workflow_graph": graph,
        "current_conclusion": conclusion,
        "overview_consistency": {
            "phase": _dict(overview.get("phase")).get("key"),
            "recovery_category": recovery.get("category") if recovery else None,
            "current_result_status": _dict(overview.get("current_result")).get("status"),
            "accepted": _dict(overview.get("current_result")).get("accepted") is True,
        },
    }


def _workflow_node_interaction(
    node: dict[str, Any],
    *,
    work_id: str,
    jobs_by_id: dict[str, dict[str, Any]],
    overview_parts: dict[str, dict[str, Any]],
    references: list[dict[str, Any]],
    accepted: dict[str, Any],
    command_authority: dict[str, Any],
    language: str,
) -> dict[str, Any]:
    """Derive task-oriented UI actions from existing durable Work state."""

    part_job_id = str(node.get("part_job_id") or "")
    run_id = node.get("run_id")
    raw_job = _dict(jobs_by_id.get(part_job_id))
    part = _dict(overview_parts.get(part_job_id))
    active_run_id = raw_job.get("active_attempt_run_id")
    is_active_attempt = bool(run_id and run_id == active_run_id)
    detail = _dict(node.get("detail"))
    detail_type = str(detail.get("type") or "evidence")
    node_recovery = _dict(detail.get("recovery"))
    primary: dict[str, Any] | None = None
    secondary: list[dict[str, Any]] = []
    unavailable_reason: str | None = None

    def action(
        key: str,
        en: str,
        zh: str,
        *,
        category: str = "workflow_command",
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "label": zh if language == "zh" else en,
            "enabled": True,
            "category": category,
            "target_work_id": work_id,
            "target_stage_id": node.get("id"),
            "part_job_id": part_job_id or None,
            "scope_label": (
                part.get("name")
                or (part_job_id.replace("_", " ").title() if part_job_id else None)
                or ("Work 设计" if language == "zh" else "Work Design")
            ),
            "target_run_id": run_id if isinstance(run_id, str) else None,
            **extra,
        }

    recovery_applies = bool(
        node_recovery
        and node_recovery.get("part_job_id") in {None, part_job_id}
        and (
            (
                detail_type == "recovery"
                and node_recovery.get("artifact_id") == node.get("artifact_id")
            )
            or (
                detail_type == "clarification"
                and not detail.get("answered")
                and node_recovery.get("question_artifact_id") == node.get("artifact_id")
            )
            or (detail_type in {"part_job", "attempt"} and (detail_type == "part_job" or is_active_attempt))
        )
    )
    recommended = _dict(node_recovery.get("recommended_action")) if recovery_applies else {}
    recovery_key = str(recommended.get("key") or "")
    if recovery_key == "answer_question" and detail_type == "clarification" and not detail.get("answered"):
        primary = action("answer_question", "Answer and continue", "回答并继续")
    elif recovery_key == "retry_agent" and node_recovery.get("retryable") is True:
        part_label = str(part.get("name") or part_job_id.replace("_", " ").title())
        primary = action(
            "retry_agent",
            f"Retry {part_label}" if part_job_id else "Retry Work Design",
            f"重试 {part_label}" if part_job_id else "重试 Work 设计",
        )
    elif recovery_key in {"open_settings", "check_environment"}:
        primary = action("open_settings", "Open Settings", "打开设置", category="navigation")
    elif recovery_key == "modify_request":
        primary = action("modify_request", "Modify request", "修改设计要求")

    if detail_type == "request":
        attempts = [
            attempt
            for job in jobs_by_id.values()
            for attempt in job.get("attempts", [])
            if isinstance(attempt, dict)
        ]
        has_design_progress = any(
            item.get("checkpoint")
            in {
                "clarification_decision",
                "design_brief",
                "model_program_candidate",
                "geometry_candidate",
                "cad_ir_draft",
                "execution_observation",
                "product_design_routing",
                "reviewable_result",
            }
            for item in references
        )
        if len(jobs_by_id) == 1 and attempts and not has_design_progress:
            only_job_id, only_job = next(iter(jobs_by_id.items()))
            target_run_id = only_job.get("active_attempt_run_id") or attempts[-1].get("run_id")
            only_part = _dict(overview_parts.get(only_job_id))
            part_label = str(
                only_part.get("name") or only_job_id.replace("_", " ").title()
            )
            primary = action(
                "continue_agent",
                f"Start {part_label} design",
                f"开始 {part_label} 设计",
                part_job_id=only_job_id,
                scope_label=part_label,
                target_run_id=target_run_id,
            )
        elif not attempts:
            primary = action(
                "continue_work_design",
                "Continue Work Design",
                "继续 Work 设计",
                target_stage_id="work:design",
                target_run_id=node.get("run_id"),
            )
    elif detail_type == "work_design":
        if node.get("status") not in {"completed"}:
            primary = action(
                "continue_work_design",
                "Continue Work Design",
                "继续 Work 设计",
            )
    elif detail_type in {"part_job", "attempt"}:
        if primary is None and not recovery_applies and active_run_id and (detail_type == "part_job" or is_active_attempt):
            run_references = [item for item in references if item.get("run_id") == active_run_id]
            active_run_has_reviewable_result = any(
                item.get("checkpoint") == "reviewable_result"
                or item.get("trust_role") == "reviewable"
                for item in run_references
            )
            active_run_has_agent_progress = any(
                item.get("checkpoint")
                in {
                    "agent_output",
                    "agent_activity",
                    "design_brief",
                    "model_program_candidate",
                    "geometry_candidate",
                    "cad_ir_draft",
                    "execution_observation",
                    "product_design_routing",
                    "reviewable_result",
                }
                for item in run_references
            )
            if part.get("state") == "design" and not active_run_has_reviewable_result:
                part_label = str(
                    part.get("name") or part_job_id.replace("_", " ").title()
                )
                primary = action(
                    "continue_agent",
                    f"Continue {part_label}"
                    if active_run_has_agent_progress
                    else f"Start {part_label} design",
                    f"继续 {part_label}"
                    if active_run_has_agent_progress
                    else f"开始 {part_label} 设计",
                    target_run_id=active_run_id,
                )
        if isinstance(run_id, str):
            secondary.append(action("open_run", "Open historical Run", "打开历史 Run", category="navigation"))
        if detail_type == "attempt" and not is_active_attempt and primary is None:
            unavailable_reason = (
                "Historical attempts are inspection-only; branch from a reviewable or accepted result."
                if language != "zh"
                else "历史尝试仅供查看；请从可审查或已接受结果创建新版本。"
            )
    elif detail_type == "clarification":
        if detail.get("answered"):
            unavailable_reason = (
                "This answer is historical. Changing it requires a new supported attempt."
                if language != "zh"
                else "该回答已成为历史证据；更改它需要创建受支持的新尝试。"
            )
    elif detail_type == "answer":
        unavailable_reason = (
            "Persisted answers are immutable evidence."
            if language != "zh"
            else "已保存的回答是不可变证据。"
        )
    elif detail_type == "recovery":
        if primary is None:
            unavailable_reason = (
                "This stop is historical or has no safe automatic recovery command."
                if language != "zh"
                else "该停止状态是历史证据，或当前没有安全的自动恢复命令。"
            )
        if recovery_applies:
            secondary.append(action("technical_details", "Technical details", "技术详情", category="presentation"))
    elif detail_type == "reviewable_result":
        result_id = node.get("result_id")
        pointer = _dict(accepted.get(part_job_id))
        if isinstance(result_id, str) and pointer.get("result_id") != result_id:
            primary = action(
                "accept_reviewable_result",
                "Accept result",
                "接受结果",
                reviewable_result_id=result_id,
            )
        if isinstance(result_id, str) and detail.get("can_start_revision"):
            secondary.append(action(
                "revise_reviewable_result",
                "Start new version from this result",
                "从此结果创建新版本",
                reviewable_result_id=result_id,
            ))
    elif detail_type == "accepted_result":
        result_id = node.get("result_id")
        if isinstance(result_id, str) and detail.get("can_start_revision"):
            secondary.append(action(
                "revise_reviewable_result",
                "Start new version from this accepted result",
                "从此已接受结果创建新版本",
                reviewable_result_id=result_id,
            ))
        else:
            unavailable_reason = (
                "The source reviewable result is unavailable, so this accepted pointer is inspection-only."
                if language != "zh"
                else "源可审查结果不可用，因此该接受指针仅供查看。"
            )
    elif isinstance(run_id, str):
        secondary.append(action("open_run", "Open historical Run", "打开历史 Run", category="navigation"))

    work_authority = _dict(command_authority.get("work"))
    part_authority = _dict(_dict(command_authority.get("parts")).get(part_job_id))
    work_primary = _dict(work_authority.get("primary_action"))
    authority_scope = (
        work_authority
        if detail_type in {"clarification", "recovery"}
        and primary is not None
        and primary.get("key") == work_primary.get("key")
        else part_authority
        if part_job_id
        else work_authority
    )
    authority_command = _dict(authority_scope.get("primary_action"))
    authority_secondary = [
        _dict(item)
        for item in authority_scope.get("secondary_actions", [])
        if isinstance(item, dict)
    ]
    authority_result_id = authority_command.get("reviewable_result_id")
    selected_result_id = node.get("result_id")
    authority_applies = bool(
        authority_command
        and (
            (
                not part_job_id
                and detail_type in {"request", "work_design", "recovery"}
            )
            or (
                part_job_id
                and detail_type == "part_job"
            )
            or (
                part_job_id
                and detail_type == "attempt"
                and is_active_attempt
            )
            or (
                part_job_id
                and detail_type in {"reviewable_result", "accepted_result"}
                and isinstance(selected_result_id, str)
                and selected_result_id == authority_result_id
            )
            or (
                detail_type in {"clarification", "recovery"}
                and primary is not None
                and primary.get("key") == authority_command.get("key")
            )
        )
    )
    state_changing_keys = {
        "accept_reviewable_result",
        "answer_question",
        "continue_agent",
        "continue_work_design",
        "modify_request",
        "open_settings",
        "retry_agent",
        "revise_reviewable_result",
    }
    if authority_applies:
        page_context = {
            "category": "workflow_command",
            "target_stage_id": node.get("id"),
            "scope_label": (
                part.get("name")
                or (part_job_id.replace("_", " ").title() if part_job_id else None)
                or ("Work 设计" if language == "zh" else "Work Design")
            ),
        }
        primary = {**authority_command, **page_context}
        navigation = [
            item
            for item in secondary
            if item.get("key") not in state_changing_keys
        ]
        secondary = [
            {**item, **page_context}
            for item in authority_secondary
        ] + navigation
    elif primary and primary.get("key") in state_changing_keys:
        # Selected historical evidence is inspectable, but it cannot invent a
        # state-changing command outside the shared Work command inventory.
        unavailable_reason = unavailable_reason or (
            "This evidence is inspection-only in the current Work state."
            if language != "zh"
            else "该证据在当前 Work 状态中仅供查看。"
        )
        primary = None
        secondary = [
            item
            for item in secondary
            if item.get("key") not in state_changing_keys
        ]
    requires_user_action = bool(
        primary
        and primary.get("key")
        in {"answer_question", "retry_agent", "open_settings", "modify_request", "accept_reviewable_result"}
    )
    return {
        "state": node.get("status"),
        "why_it_matters": node.get("summary"),
        "requires_user_action": requires_user_action,
        "primary_action": primary,
        "secondary_actions": secondary,
        "unavailable_reason": unavailable_reason,
        "revision_supported": any(item.get("key") == "revise_reviewable_result" for item in secondary),
        "business_state_owner": "domain",
        "command_authority_key": authority_command.get("key"),
        "selection_mutates_business_state": False,
    }


def _workflow_user_state(node: dict[str, Any]) -> str:
    """Translate graph status/actions into a small normal-user attention state."""

    interaction = _dict(node.get("interaction"))
    primary = _dict(interaction.get("primary_action"))
    action_key = str(primary.get("key") or "")
    status = str(node.get("status") or "not_started")
    detail_type = str(_dict(node.get("detail")).get("type") or "")
    if action_key == "answer_question":
        return "needs_you"
    if action_key == "accept_reviewable_result" or status == "reviewable":
        return "review"
    if status in {"blocked", "failed"} or action_key in {
        "retry_agent", "open_settings", "modify_request"
    }:
        return "blocked"
    if action_key == "continue_agent":
        return "ready"
    if status == "running":
        return "running"
    if status == "accepted" or detail_type == "accepted_result":
        return "accepted"
    return "complete" if status in {"completed", "contract_complete"} else "ready"


def _workflow_user_state_label(
    state: str,
    language: str,
) -> str:
    labels = {
        "needs_you": ("Needs you", "需要你"),
        "ready": ("Ready", "就绪"),
        "running": ("Running", "运行中"),
        "review": ("Review", "待审查"),
        "blocked": ("Blocked", "受阻"),
        "accepted": ("Accepted", "已接受"),
        "complete": ("Complete", "已完成"),
    }
    pair = labels.get(state, labels["ready"])
    return pair[1] if language == "zh" else pair[0]


def _workflow_current_attention(
    nodes: list[dict[str, Any]],
    branches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Choose one derived attention point per parallel Part branch."""

    by_id = {str(node.get("id")): node for node in nodes}
    attention: list[dict[str, Any]] = []
    priority = {"clarification": 0, "recovery": 1, "reviewable_result": 2, "attempt": 3, "accepted_result": 4}
    for branch in branches:
        attempts = [item for item in branch.get("attempts", []) if isinstance(item, dict)]
        active_attempt = next((item for item in reversed(attempts) if item.get("active")), None)
        candidates: list[dict[str, Any]] = []
        if active_attempt:
            candidates = [by_id[node_id] for node_id in active_attempt.get("node_ids", []) if node_id in by_id]
        elif attempts:
            candidates = [by_id[node_id] for node_id in attempts[-1].get("node_ids", []) if node_id in by_id]
        if not candidates:
            part_node = by_id.get(str(branch.get("part_node_id")))
            candidates = [part_node] if part_node else []
        actionable = [
            node
            for node in candidates
            if _dict(node.get("interaction")).get("requires_user_action")
            or node.get("kind") == "accepted"
            or (
                node.get("kind") == "reviewable"
                and _dict(_dict(node.get("interaction")).get("primary_action")).get("key")
                == "accept_reviewable_result"
            )
        ]
        pool = actionable or candidates
        if not pool:
            continue
        chosen = sorted(
            pool,
            key=lambda node: (
                priority.get(str(_dict(node.get("detail")).get("type") or node.get("kind")), 9),
                0 if _dict(node.get("interaction")).get("requires_user_action") else 1,
            ),
        )[0]
        interaction = _dict(chosen.get("interaction"))
        user_state = str(chosen.get("user_state") or "ready")
        kind = {
            "needs_you": "user_action",
            "review": "review",
            "blocked": "blocked",
            "running": "running",
        }.get(user_state, "active")
        attention.append({
            "node_id": chosen.get("id"),
            "part_job_id": branch.get("part_job_id"),
            "part_label": branch.get("label") or branch.get("part_job_id"),
            "kind": kind,
            "state": user_state,
            "state_label": chosen.get("user_state_label"),
            "label": chosen.get("label"),
            "summary": chosen.get("summary"),
            "requires_user_action": interaction.get("requires_user_action") is True,
            "primary_action": interaction.get("primary_action"),
        })
    if not attention:
        candidates = [
            node
            for node in nodes
            if node.get("kind") in {"decision", "recovery", "work_design"}
            and node.get("part_job_id") is None
        ]
        if candidates:
            chosen = sorted(
                candidates,
                key=lambda node: (
                    0 if _dict(node.get("interaction")).get("requires_user_action") else 1,
                    0 if node.get("kind") in {"decision", "recovery"} else 1,
                    0 if node.get("status") in {"blocked", "in_progress", "not_started"} else 1,
                ),
            )[0]
            interaction = _dict(chosen.get("interaction"))
            user_state = str(chosen.get("user_state") or "ready")
            attention.append({
                "node_id": chosen.get("id"),
                "part_job_id": None,
                "part_label": "Work Design",
                "kind": "user_action" if interaction.get("requires_user_action") else "active",
                "state": user_state,
                "state_label": chosen.get("user_state_label"),
                "label": chosen.get("label"),
                "summary": chosen.get("summary"),
                "requires_user_action": interaction.get("requires_user_action") is True,
                "primary_action": interaction.get("primary_action"),
            })
    return attention


def _workflow_reference_node(
    backend: Any,
    work_id: str,
    reference: dict[str, Any],
    overview: dict[str, Any],
    part: dict[str, Any],
    language: str,
    *,
    all_references: list[dict[str, Any]],
) -> dict[str, Any] | None:
    checkpoint = str(reference.get("checkpoint") or "")
    trust_role = str(reference.get("trust_role") or "")
    artifact_id = str(reference.get("artifact_id") or "")
    payload = _read_reference(backend, work_id, reference)
    scope_references = [
        item
        for item in all_references
        if item.get("part_job_id") == reference.get("part_job_id")
        and item.get("run_id") == reference.get("run_id")
    ]
    scope_output = build_agent_output_projection(
        backend,
        work_id,
        scope_references,
        language=language,
        scope_kind="part" if reference.get("part_job_id") else "work_design",
    )
    common = {
        "part_job_id": reference.get("part_job_id"),
        "run_id": reference.get("run_id"),
        "artifact_id": artifact_id,
        "group": _workflow_group(reference.get("phase"), checkpoint, trust_role),
    }
    if checkpoint == "clarification_decision" and trust_role == "diagnostic":
        questions = [item for item in payload.get("questions", []) if isinstance(item, dict)]
        answered = any(
            artifact_id in item.get("source_artifact_ids", [])
            for item in _dict(overview.get("advanced")).get("artifact_references", [])
            if isinstance(item, dict) and item.get("trust_role") == "accepted_input"
        )
        question = questions[0] if questions else {}
        question_recovery = build_recovery_projection(
            backend,
            work_id,
            {},
            scope_references,
            language=language,
            agent_output=scope_output,
        )
        return {
            "edge_type": "asked",
            "node": {
                **common,
                "id": f"question:{artifact_id}",
                "label": "Agent 提问" if language == "zh" else "Agent needs information",
                "kind": "decision",
                "status": "completed" if answered else "blocked",
                "summary": question.get("question") or payload.get("why_it_matters"),
                "detail": {
                    "type": "clarification",
                    "questions": questions,
                    "evidence": payload,
                    "answered": answered,
                    "agent_output": scope_output,
                    "recovery": {
                        **_dict(question_recovery),
                        "work_id": work_id,
                        "part_job_id": reference.get("part_job_id"),
                        "run_id": reference.get("run_id"),
                        "artifact_id": artifact_id,
                    }
                    if not answered
                    else {},
                },
            },
        }
    if checkpoint == "clarification_decision" and trust_role == "accepted_input":
        return {
            "edge_type": "answered",
            "node": {
                **common,
                "id": f"answer:{artifact_id}",
                "label": "用户已回答" if language == "zh" else "User answered",
                "kind": "decision",
                "status": "completed",
                "summary": payload.get("answer"),
                "detail": {"type": "answer", "question": payload.get("question"), "answer": payload.get("answer"), "evidence": payload},
            },
        }
    if checkpoint == "design_brief":
        design_content = _dict(payload.get("content")) or payload
        return {
            "edge_type": "designed",
            "node": {
                **common,
                "id": f"design:{artifact_id}",
                "label": "Agent 设计" if language == "zh" else "Agent design",
                "kind": "design",
                "status": "completed",
                "summary": design_content.get("concept") or ("已保存设计摘要" if language == "zh" else "Persisted design summary"),
                "detail": {
                    "type": "agent_design",
                    "agent_design": design_content,
                    "agent_output": scope_output,
                    "evidence": payload,
                },
            },
        }
    if trust_role == "candidate" and checkpoint in {"model_program_candidate", "geometry_candidate", "cad_ir_draft"}:
        return {
            "edge_type": "generated",
            "node": {
                **common,
                "id": f"candidate:{artifact_id}",
                "label": "设计候选" if language == "zh" else "Design candidate",
                "kind": "candidate",
                "status": "completed",
                "summary": "候选已保存，尚未接受。" if language == "zh" else "Candidate persisted; not accepted.",
                "detail": {"type": "candidate", "evidence": payload, "reference": reference},
            },
        }
    if checkpoint == "execution_observation":
        passed = reference.get("validation_status") in {"passed", "completed", "valid"}
        codes = payload.get("codes") if isinstance(payload.get("codes"), list) else []
        return {
            "edge_type": "validated" if passed else "failed",
            "node": {
                **common,
                "id": f"build:{artifact_id}",
                "label": "构建与检查" if language == "zh" else "Build and inspect",
                "kind": "build",
                "status": "completed" if passed else "failed",
                "summary": (
                    "本地构建与几何检查通过。" if passed and language == "zh"
                    else "Local build and geometry inspection passed." if passed
                    else ("验证失败：" if language == "zh" else "Validation failed: ") + ", ".join(str(item) for item in codes[:3])
                ),
                "detail": {"type": "build", "evidence": payload, "reference": reference},
            },
        }
    if checkpoint in {"product_design_routing", "work_design_routing"}:
        episode = _dict(payload.get("episode"))
        stop_reason = episode.get("stop_reason")
        if not stop_reason or episode.get("status") == "completed":
            return None
        current_recovery = build_recovery_projection(
            backend,
            work_id,
            _dict(_dict(overview.get("advanced")).get("entity_state")),
            scope_references,
            language=language,
            agent_output=scope_output,
        )
        references = all_references
        accepted_input_ids = {
            str(item.get("artifact_id"))
            for item in references
            if item.get("trust_role") == "accepted_input" and item.get("artifact_id")
        }
        resumed = any(
            source_id in accepted_input_ids
            for source_id in reference.get("source_artifact_ids", [])
        )
        if stop_reason == "user_input_required":
            stop_label = "需要信息" if language == "zh" else "Need information"
        elif stop_reason in {"provider_auth_failed", "provider_failure", "policy_blocked"}:
            stop_label = "设计受阻" if language == "zh" else "Design blocked"
        else:
            stop_label = "设计已停止" if language == "zh" else "Design stopped"
        return {
            "edge_type": "resumed" if resumed else "failed",
            "node": {
                **common,
                "id": f"recovery:{artifact_id}",
                "label": stop_label,
                "kind": "recovery",
                "status": "blocked",
                "summary": _stop_reason_text(stop_reason, language),
                "detail": {
                    "type": "recovery",
                    "stop_reason": stop_reason,
                    "episode": episode,
                    "recovery": {
                        **_dict(current_recovery),
                        "work_id": work_id,
                        "part_job_id": reference.get("part_job_id"),
                        "run_id": reference.get("run_id"),
                        "artifact_id": artifact_id,
                    }
                    if _dict(current_recovery).get("category") == stop_reason
                    else {},
                    "agent_output": scope_output,
                    "evidence": payload,
                },
            },
        }
    if checkpoint == "reviewable_result" and trust_role == "reviewable_result" and str(reference.get("relative_path") or "").endswith("/reviewable_result.json"):
        result_id = reference.get("artifact_id")
        result = _result_detail_from_record(
            payload,
            part,
            str(result_id or ""),
            language,
        )
        step_reference = next(
            (
                item
                for item in scope_references
                if item.get("checkpoint") == "reviewable_result"
                and item.get("trust_role") == "reviewable_result"
                and result_id in item.get("source_artifact_ids", [])
                and item.get("validation_status") == "passed"
            ),
            None,
        )
        preview = {
            "status": "reviewable",
            "label": "结果可供审查" if language == "zh" else "Result ready for review",
            "kind": "registered_step" if step_reference else "empty",
            "viewer_url": (
                f"/web-viewer/index.html?file=%2Fapi%2Fwork-artifacts%2F{work_id}%2F{step_reference.get('artifact_id')}%2Fpreview.stl"
                if step_reference
                else None
            ),
            "download_url": (
                f"/api/work-artifacts/{work_id}/{step_reference.get('artifact_id')}/download"
                if step_reference
                else None
            ),
            "geometry": _dict(payload.get("geometry")),
        }
        return {
            "edge_type": "reviewable",
            "node": {
                **common,
                "id": f"result:{result_id}",
                "label": "可审查结果" if language == "zh" else "Reviewable result",
                "kind": "reviewable",
                "status": "reviewable",
                "result_id": result_id,
                "summary": "已通过本地检查，尚未接受。" if language == "zh" else "Locally validated and ready for review; not accepted.",
                "detail": {
                    "type": "reviewable_result",
                    "result": result,
                    "record": payload,
                    "part_job_id": reference.get("part_job_id"),
                    "can_start_revision": True,
                    "preview": preview,
                    "agent_output": scope_output,
                },
            },
        }
    return None


def _workflow_part_status(part: dict[str, Any], recovery: dict[str, Any] | None, part_job_id: str) -> str:
    if recovery and recovery.get("part_job_id") in {None, part_job_id}:
        return "blocked"
    state = str(part.get("state") or "not_started")
    return {
        "design": "not_started",
        "reviewable": "reviewable",
        "accepted": "accepted",
        "not_started": "not_started",
        "stale": "stale",
        "blocked": "blocked",
    }.get(state, "not_started")


def _workflow_attempt_status(
    run_id: str,
    active_run_id: Any,
    references: list[dict[str, Any]],
    accepted_pointer: Any,
    recovery: dict[str, Any] | None,
) -> str:
    if run_id == active_run_id and recovery:
        return "blocked"
    if any(item.get("checkpoint") == "reviewable_result" and item.get("trust_role") == "reviewable_result" for item in references):
        return "completed"
    if run_id == active_run_id:
        # A current attempt is ready, not necessarily executing.  The NiceGUI
        # action lifecycle overlays Running only while the local command is
        # actually in flight; no durable active indicator exists here.
        return "not_started"
    pointer = _dict(accepted_pointer)
    if pointer.get("attempt_run_id") == run_id and pointer.get("status") == "approved":
        return "completed"
    if any(item.get("trust_role") == "diagnostic" for item in references):
        return "failed"
    return "stale"


def _workflow_group(phase: Any, checkpoint: str, trust_role: str) -> str:
    value = str(phase or "")
    if checkpoint == "clarification_decision":
        return "design"
    if checkpoint == "reviewable_result":
        return "accept_deliver"
    if value in {"intent", "design", "build_evaluate", "accept_deliver"}:
        return value
    return "design"


def _workflow_edge_label(edge_type: str, language: str) -> str:
    labels = {
        "created": ("创建", "created"),
        "decomposed": ("分解", "decomposed"),
        "attempted": ("尝试", "attempted"),
        "asked": ("提问", "asked"),
        "answered": ("回答", "answered"),
        "resumed": ("继续", "resumed"),
        "designed": ("设计", "designed"),
        "generated": ("生成", "generated"),
        "validated": ("验证", "validated"),
        "failed": ("失败", "failed"),
        "repaired": ("修复", "repaired"),
        "reviewable": ("可审查", "reviewable"),
        "accepted": ("接受", "accepted"),
        "revised": ("修订", "revised"),
        "imported": ("兼容导入", "compatibility import"),
    }
    zh, en = labels.get(edge_type, (edge_type, edge_type))
    return zh if language == "zh" else en


def _select_workflow_node(
    nodes: list[dict[str, Any]],
    requested: str | None,
    attention_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    if requested:
        selected = next((item for item in nodes if item.get("id") == requested), None)
        if selected:
            return selected
    for node_id in attention_ids or []:
        selected = next((item for item in nodes if item.get("id") == node_id), None)
        if selected:
            return selected
    for status in ("blocked", "running", "reviewable", "accepted", "failed", "stale"):
        selected = next((item for item in reversed(nodes) if item.get("status") == status), None)
        if selected:
            return selected
    return nodes[-1] if nodes else None


def _read_run_prompt(backend: Any, work_id: str, run_id: str) -> str | None:
    try:
        return backend.read_work_run_prompt(work_id, run_id)
    except (FileNotFoundError, ValueError):
        return None


def _result_detail_for_node(overview: dict[str, Any], part_job_id: str, result_id: str) -> dict[str, Any]:
    current = _dict(overview.get("current_result"))
    if current.get("reviewable_result_id") == result_id:
        return current
    part = next(
        (
            item
            for item in overview.get("part_jobs", [])
            if isinstance(item, dict) and item.get("part_job_id") == part_job_id
        ),
        {},
    )
    return {
        "status": "accepted" if part.get("accepted_result_id") == result_id else "reviewable",
        "title": "Accepted result" if part.get("accepted_result_id") == result_id else "Reviewable result",
        "part": part.get("name") or part_job_id,
        "role": part.get("role"),
        "reviewable_result_id": result_id,
        "accepted": part.get("accepted_result_id") == result_id,
        "verified": [],
        "assumptions": [],
        "limitations": [],
        "unverified": [],
        "unsupported": [],
        "not_requested": [],
        "geometry": {},
    }


def _result_detail_from_record(
    record: dict[str, Any],
    part: dict[str, Any],
    result_id: str,
    language: str,
) -> dict[str, Any]:
    """Project one exact reviewable record without an active-Part fallback."""

    geometry = _dict(record.get("geometry"))
    validation = _dict(record.get("validation"))
    verified: list[str] = []
    if geometry.get("valid") is True:
        verified.append("有效实体" if language == "zh" else "Valid solid")
    if isinstance(record.get("step"), dict):
        verified.append("STEP 导出成功" if language == "zh" else "STEP export passed")
    if validation.get("step_reimport_valid") is True:
        verified.append(
            "STEP 重新导入验证通过"
            if language == "zh"
            else "STEP re-import passed"
        )
    return {
        "status": "reviewable",
        "title": "可审查结果" if language == "zh" else "Reviewable result",
        "part": part.get("name") or part.get("part_job_id"),
        "role": part.get("role"),
        "reviewable_result_id": result_id,
        "accepted": part.get("accepted_result_id") == result_id,
        "geometry": geometry,
        "verified": verified,
        "assumptions": list(record.get("assumptions") or []),
        "limitations": list(record.get("limitations") or []),
        "unverified": list(record.get("unverified") or []),
        "unsupported": list(record.get("unsupported") or []),
        "not_requested": list(record.get("not_requested") or []),
        "validation": validation,
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
    work_design_status = str(_dict(entity.get("work_design")).get("status") or "not_started")
    if work_design_status in {"not_started", "in_progress"} and entity.get("description"):
        return (
            "意图" if work_design_status == "not_started" and language == "zh"
            else "Intent" if work_design_status == "not_started"
            else "设计" if language == "zh"
            else "Design",
            "Work 设计已就绪" if language == "zh" else "Work Design ready",
            "继续 Work 设计" if language == "zh" else "Continue Work Design",
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
        (
            item
            for item in reversed(references)
            if item.get("checkpoint") in {"product_design_routing", "work_design_routing"}
        ),
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
