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
) -> dict[str, Any]:
    """Build a user-facing stage review surface for one selected run."""
    run = run if isinstance(run, dict) else {}
    artifact_names = _artifact_names(run)
    overrides = run.get("artifact_override_summary") if isinstance(run.get("artifact_override_summary"), dict) else {}
    if run_id:
        artifact_contents = {
            name: _read_artifact_content(backend, run_id, name, root=root)
            for name in REVIEW_SURFACE_ARTIFACTS
            if name in artifact_names
        }
    else:
        artifact_contents = {}
    summary_context = _summary_context(run, artifact_contents)
    stages = [
        _stage_card(definition, run, artifact_names, artifact_contents, summary_context, overrides, bool(run_id))
        for definition in STAGE_DEFINITIONS
    ]
    return {
        "title": "Workflow Stage Review",
        "primary_concept": "Workflow / Stage / Review",
        "debug_graph_label": "Debug / Raw Workflow Graph",
        "stages": stages,
        "artifact_viewer": _artifact_viewer(artifact_names, artifact_contents, overrides),
        "actions": _global_actions(artifact_names, bool(run_id)),
    }


def _stage_card(
    definition: dict[str, Any],
    run: dict[str, Any],
    artifact_names: set[str],
    contents: dict[str, Any],
    context: dict[str, Any],
    overrides: dict[str, Any],
    has_run: bool,
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
    return {
        "key": key,
        "stage_name": definition["name"],
        "status": status,
        "input_artifacts": input_artifacts,
        "output_artifacts": output_artifacts,
        "agent_identity": _agent_identity(run),
        "gate_decision": _gate_decision(key, run, contents),
        "diagnostic_codes": _diagnostic_codes(key, run, contents),
        "blocked_reasons": _blocked_reasons(key, run, contents),
        "report_summary": _report_summary(key, context),
        "available_actions": actions,
        "raw_artifacts": raw_artifacts,
        "override_present": any(_canonical_name(item["name"]) in overrides for item in (*input_artifacts, *output_artifacts)),
    }


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
        "assembly": reviewed.get("assembly_plan") if isinstance(reviewed.get("assembly_plan"), dict) else {},
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
        return {
            "requirement_source": context.get("requirement_source"),
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
