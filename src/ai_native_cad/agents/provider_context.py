"""Static provider context assembly for CadFlow JSON-contract calls."""

from __future__ import annotations

import json
import re
from typing import Any


__all__ = [
    "contract_guide_for",
    "knowledge_summary_for",
    "provider_messages_for",
    "sanitize_provider_payload",
    "sanitize_provider_string",
    "system_prompt_for",
]


GLOBAL_MINIMAL_RULES = (
    "- Return JSON only.\n"
    "- Do not include markdown, prose outside JSON, CAD code, Python code, shell commands, or local paths.\n"
    "- Do not include secrets, credential values, API keys, environment variable names, transcripts, runtime logs, or provider responses.\n"
    "- CadFlow executes CAD only through validated artifacts.\n"
    "- Agent output is advisory until local validation passes.\n"
    "- STEP is the primary CAD artifact; STL is derived."
)

_STAGE_SKILL_GUIDES = {
    "requirement": (
        "Stage skill: requirement. Convert user intent into requirement.json. "
        "Preserve uncertainty as assumptions, missing_information, follow_up_questions, "
        "and requirement_status instead of inventing safety-critical details."
    ),
    "planning": (
        "Stage skill: planning. Convert a validated requirement into a planning_artifact.json "
        "handoff with selected parts, resolved decisions, gate status, and no direct CAD execution."
    ),
    "revision": (
        "Stage skill: revision. Convert user revision intent and parent model context into "
        "field-level structured changes or a revision plan. Use explicit CAD field paths only "
        "inside revision artifacts."
    ),
    "repair / part_modeling": (
        "Stage skill: repair / part_modeling. Suggest constrained repairs to validated CAD IR "
        "after local validation or execution failures. Do not generate CAD code or shell commands."
    ),
    "review": (
        "Stage skill: review. Summarize report and trace outcomes as a compact review explanation "
        "for a local gate. Do not expose logs, transcripts, provider responses, or paths."
    ),
}

_OPERATION_STAGE = {
    "parse_requirement": "requirement",
    "create_plan": "planning",
    "parse_revision_request": "revision",
    "create_revision_plan": "revision",
    "suggest_repair": "repair / part_modeling",
    "explain_review": "review",
}

_CONTRACT_GUIDES = {
    "parse_requirement": (
        "Operation contract: parse_requirement. Return a requirement.json object with part_type "
        "and dimensions. Optional fields include unit, features, assumptions, missing_information, "
        "follow_up_questions, follow_up_requests, and requirement_status. Use requirement_status "
        "to show whether generation can proceed or user input is needed."
    ),
    "create_plan": (
        "Operation contract: create_plan. Return planning_artifact.json with artifact_type='planning', "
        "route, selected_parts, and flow_gate_status. Each selected part includes part_name, "
        "generation_order, resolved, and resolved_decisions with part_type, unit, dimensions, "
        "features, outputs, and check_level."
    ),
    "parse_revision_request": (
        "Operation contract: parse_revision_request. Return revision_intent JSON describing the "
        "requested change and structured changes when supported. Use op, path, value, and reason "
        "for field-level changes. Mark uncertainty instead of making unsupported edits."
    ),
    "create_revision_plan": (
        "Operation contract: create_revision_plan. Return revision_plan.json with artifact_type, "
        "version, status, planned_operations, and notes. Use patch operations with op, path, value, "
        "and reason. If no safe structured patch exists, return blocked/no_structured_changes with "
        "a concise reason."
    ),
    "suggest_repair": (
        "Operation contract: suggest_repair. Return an object with analysis and repair. Repair may "
        "include a constrained repaired_ir that still satisfies the CadFlow CAD IR schema. Do not "
        "return code, commands, or file paths."
    ),
    "explain_review": (
        "Operation contract: explain_review. Return an object with status and summary. Optional "
        "errors and warnings must be compact arrays. Summarize outcomes without raw logs, paths, "
        "provider messages, or transcripts."
    ),
}

_KNOWLEDGE = {
    "parse_requirement": [
        {
            "id": "requirement_check_level_missing_information",
            "source": "skills/requirement/knowledge/",
            "summary": (
                "Requirement parsing records missing manufacturing, fit, material, tolerance, or load "
                "details instead of inventing them; check level can remain default/minimal unless the "
                "prompt requires stronger validation."
            ),
        }
    ],
    "create_plan": [
        {
            "id": "planning_supported_part_families",
            "source": "skills/planning/knowledge/",
            "summary": (
                "Planning MVP supports simple deterministic part families such as spacer, mounting_plate, "
                "and simple_bracket, and hands off resolved dimensions/features through selected_parts."
            ),
        }
    ],
    "parse_revision_request": [
        {
            "id": "revision_supported_changes",
            "source": "skills/revision/knowledge/",
            "summary": (
                "Revision MVP supports field-level CAD IR changes such as dimensions.thickness, metric "
                "fastener hole diameter, explicit hole diameter, and chamfer removal."
            ),
        },
        {
            "id": "revision_cad_field_paths",
            "source": "skills/revision/knowledge/",
            "summary": (
                "Allowed structured CAD field paths include dimensions.thickness, "
                "features.holes.diameter, and features.chamfer when the revision contract needs paths."
            ),
        },
    ],
    "create_revision_plan": [
        {
            "id": "revision_patch_contract",
            "source": "skills/revision/knowledge/",
            "summary": (
                "Revision plans use explicit patch operations and should return blocked or "
                "no_structured_changes when the requested edit cannot be represented safely."
            ),
        },
        {
            "id": "revision_supported_changes",
            "source": "skills/revision/knowledge/",
            "summary": (
                "Revision MVP supports field-level CAD IR changes such as dimensions.thickness, metric "
                "fastener hole diameter, explicit hole diameter, and chamfer removal."
            ),
        },
    ],
    "suggest_repair": [
        {
            "id": "constrained_ir_repair",
            "source": "skills/part_modeling/knowledge/",
            "summary": (
                "Repair suggestions are constrained CAD IR edits after validation/execution failures; "
                "they must preserve schema validity and avoid generated CAD code."
            ),
        }
    ],
    "explain_review": [
        {
            "id": "review_summary_behavior",
            "source": "skills/review/knowledge/",
            "summary": (
                "Review explanations summarize report status, errors, warnings, and gate meaning in "
                "compact user-facing JSON without raw runtime logs or provider responses."
            ),
        }
    ],
}


def system_prompt_for(operation: str) -> str:
    """Return global rules plus the stage skill guide for a supported operation."""

    stage = _stage_for(operation)
    return f"{GLOBAL_MINIMAL_RULES}\n\n{_STAGE_SKILL_GUIDES[stage]}"


def contract_guide_for(operation: str) -> str:
    """Return the compact operation-specific JSON contract guide."""

    _stage_for(operation)
    return _CONTRACT_GUIDES[operation]


def knowledge_summary_for(operation: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the selected compact static knowledge summary for an operation."""

    stage = _stage_for(operation)
    return {
        "operation": operation,
        "stage": stage,
        "selected": [_sanitize_provider_payload(item, preserve_cad_paths=True) for item in _KNOWLEDGE[operation]],
    }


def provider_messages_for(
    *,
    operation: str,
    contract_instruction: str,
    user_payload: dict[str, Any] | str,
    context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build provider-visible messages with deterministic context and sanitized payload."""

    knowledge = knowledge_summary_for(operation, context)
    payload = _sanitize_provider_payload(
        user_payload,
        preserve_cad_paths=operation in {"parse_revision_request", "create_revision_plan"},
    )
    if isinstance(payload, str):
        payload_content = payload
    else:
        payload_content = json.dumps(payload, sort_keys=True)
    return [
        {"role": "system", "content": system_prompt_for(operation)},
        {"role": "system", "content": contract_instruction or contract_guide_for(operation)},
        {
            "role": "system",
            "content": "Selected compact knowledge: " + json.dumps(knowledge, sort_keys=True),
        },
        {"role": "user", "content": payload_content},
    ]


def sanitize_provider_payload(value: Any, *, preserve_cad_paths: bool = False) -> Any:
    """Remove provider-private fields and redact private string content."""

    return _sanitize_provider_payload(value, preserve_cad_paths=preserve_cad_paths)


def sanitize_provider_string(value: str) -> str:
    """Redact provider-private content from a string."""

    return _sanitize_provider_string(value)


def _stage_for(operation: str) -> str:
    try:
        return _OPERATION_STAGE[operation]
    except KeyError as exc:
        raise ValueError(f"unsupported provider context operation: {operation}") from exc


_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/][^\s\"'{}[\],]+|/[Uu]sers/[^\s\"'{}[\],]+|/home/[^\s\"'{}[\],]+)"
)
_API_ENV_VAR_RE = re.compile(
    r"\b[A-Z][A-Z0-9_]*(?:API[_-]?KEY|SECRET|TOKEN|PASSWORD|ACCESS[_-]?KEY)[A-Z0-9_]*\b"
)
_SECRET_VALUE_RE = re.compile(r"\b(?:sk|pk|pat|ghp|gho|ghu|ghs|xoxb|xoxp)-[A-Za-z0-9_-]{8,}\b")
_SENSITIVE_KEY_TOKENS = (
    "api_key",
    "apikey",
    "access_key",
    "secret",
    "token",
    "password",
    "credential",
)
_RUNTIME_KEY_TOKENS = (
    "transcript",
    "chat_log",
    "chatlog",
    "runtime_log",
    "runtime_logs",
    "runtime",
    "log_text",
    "logs",
    "agent_trace",
    "provider_response",
)
_FILESYSTEM_KEY_NAMES = {
    "run_dir",
    "output_dir",
    "output_root",
    "project_root",
    "root_run_id",
    "workspace_root",
    "root",
}


def _sanitize_provider_payload(value: Any, *, preserve_cad_paths: bool = False) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _provider_payload_key_is_private(key_text, item, preserve_cad_paths=preserve_cad_paths):
                continue
            sanitized[key] = _sanitize_provider_payload(item, preserve_cad_paths=preserve_cad_paths)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_provider_payload(item, preserve_cad_paths=preserve_cad_paths) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_provider_payload(item, preserve_cad_paths=preserve_cad_paths) for item in value]
    if isinstance(value, str):
        return _sanitize_provider_string(value)
    return value


def _provider_payload_key_is_private(key: str, value: Any, *, preserve_cad_paths: bool) -> bool:
    lowered = key.lower()
    if any(token in lowered for token in _SENSITIVE_KEY_TOKENS):
        return True
    if any(token in lowered for token in _RUNTIME_KEY_TOKENS):
        return True
    if lowered.endswith("_env_var") or lowered.endswith("_env"):
        return True
    if lowered == "path":
        return not (preserve_cad_paths and isinstance(value, str) and _looks_like_cad_field_path(value))
    if lowered in _FILESYSTEM_KEY_NAMES or lowered.endswith("_dir") or lowered.endswith("_root"):
        return True
    if lowered.endswith("_path"):
        return True
    return False


def _looks_like_cad_field_path(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", value))


def _sanitize_provider_string(value: str) -> str:
    value = _ABSOLUTE_PATH_RE.sub("[redacted-local-path]", value)
    value = _API_ENV_VAR_RE.sub("[redacted-api-env-var]", value)
    value = _SECRET_VALUE_RE.sub("[redacted-secret]", value)
    return value
