"""Focused canonical contract authority for registered Agent actions.

This deliberately describes only the bounded action objects CadFlow already
accepts.  It is not a general JSON-schema engine: validation, provider
disclosure, and repair feedback use this one small definition so their action
field sets cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from ai_native_cad.agents.model_program_policy import CADQUERY_MODEL_PROGRAM_API
from ai_native_cad.agents.model_program_runtime import (
    MODEL_PROGRAM_LIMITS,
    MODEL_PROGRAM_PARAMETER_KEY_MAX_LENGTH,
    MODEL_PROGRAM_REQUESTED_OUTPUTS,
)
from ai_native_cad.agents.work_design_contract import work_design_contract_description


@dataclass(frozen=True)
class AgentActionContract:
    action: str
    allowed_fields: frozenset[str]
    required_fields: frozenset[str]
    fields: Mapping[str, Mapping[str, Any]]


def _fields(**fields: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    return _freeze_description(fields)


def _freeze_description(value: Any) -> Any:
    """Freeze the small JSON-like action descriptions held by this authority."""

    if isinstance(value, Mapping):
        return MappingProxyType({
            key: _freeze_description(item)
            for key, item in value.items()
        })
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_description(item) for item in value)
    return value


def _thaw_description(value: Any) -> Any:
    """Return an ordinary JSON-compatible copy for a provider request."""

    if isinstance(value, Mapping):
        return {key: _thaw_description(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_description(item) for item in value]
    return value


_ACTION_FIELD = {"type": "string"}
_TEXT_FIELD = {"type": "string"}
_OBJECT_FIELD = {"type": "object"}
_STRING_LIST_FIELD = {"type": "list", "items": {"type": "string"}}
_QUESTION_LIST_FIELD = {
    "type": "list",
    "min_items": 1,
    "items": {
        "type": "object",
        "required_fields": ["field", "question"],
        "fields": {
            "field": {"type": "string", "non_empty": True},
            "question": {"type": "string", "non_empty": True},
        },
    },
}

MODEL_PROGRAM_SUBMISSION_FIELDS = frozenset(
    {"api_id", "source", "parameters", "requested_outputs"}
)
MODEL_PROGRAM_SUBMISSION_API_ID = CADQUERY_MODEL_PROGRAM_API
MODEL_PROGRAM_SUBMISSION_REQUESTED_OUTPUTS = MODEL_PROGRAM_REQUESTED_OUTPUTS


def model_program_submission_contract_description() -> dict[str, Any]:
    """Describe the exact provider submission CadFlow already validates."""

    return {
        "type": "object",
        "required_fields": sorted(MODEL_PROGRAM_SUBMISSION_FIELDS),
        "allowed_fields": sorted(MODEL_PROGRAM_SUBMISSION_FIELDS),
        "fields": {
            "api_id": {"type": "string", "const": MODEL_PROGRAM_SUBMISSION_API_ID},
            "source": {"type": "string", "non_empty": True},
            "parameters": {
                "type": "object",
                "finite_json": True,
                "max_bytes": MODEL_PROGRAM_LIMITS["parameter_bytes"],
                "max_depth": MODEL_PROGRAM_LIMITS["parameter_depth"],
                "property_names": {
                    "type": "string",
                    "non_empty": True,
                    "max_length": MODEL_PROGRAM_PARAMETER_KEY_MAX_LENGTH,
                },
            },
            "requested_outputs": {
                "type": "list",
                "const": list(MODEL_PROGRAM_SUBMISSION_REQUESTED_OUTPUTS),
            },
        },
        "additional_fields": False,
    }


def _contract(
    action: str,
    *,
    required: Iterable[str],
    fields: Mapping[str, Mapping[str, Any]],
) -> AgentActionContract:
    descriptions = {"action": {**_ACTION_FIELD, "const": action}, **fields}
    return AgentActionContract(
        action=action,
        allowed_fields=frozenset(descriptions),
        required_fields=frozenset(required),
        fields=_fields(**descriptions),
    )


_ACTION_CONTRACTS = (
    _contract("request_context", required=("action", "context_key"), fields={
        "context_key": _TEXT_FIELD,
        "reason": _TEXT_FIELD,
    }),
    _contract("create_contract", required=("action", "contract_type", "contract"), fields={
        "contract_type": _TEXT_FIELD,
        "contract": _OBJECT_FIELD,
        "assumptions": _STRING_LIST_FIELD,
        "summary": _TEXT_FIELD,
    }),
    _contract("patch_contract", required=("action", "contract_type", "contract"), fields={
        "contract_type": _TEXT_FIELD,
        "contract": _OBJECT_FIELD,
        "assumptions": _STRING_LIST_FIELD,
        "summary": _TEXT_FIELD,
    }),
    _contract("submit_contract", required=("action", "contract_type", "contract"), fields={
        "contract_type": _TEXT_FIELD,
        "contract": _OBJECT_FIELD,
        "assumptions": _STRING_LIST_FIELD,
        "summary": _TEXT_FIELD,
    }),
    _contract("repair_contract", required=("action", "contract_type", "contract"), fields={
        "contract_type": _TEXT_FIELD,
        "contract": _OBJECT_FIELD,
        "assumptions": _STRING_LIST_FIELD,
        "summary": _TEXT_FIELD,
    }),
    _contract("request_validation", required=("action",), fields={"reason": _TEXT_FIELD}),
    _contract("create_model_program", required=("action", "model_program"), fields={
        "model_program": _OBJECT_FIELD,
        "assumptions": _STRING_LIST_FIELD,
        "summary": _TEXT_FIELD,
    }),
    _contract("patch_model_program", required=("action", "model_program"), fields={
        "model_program": _OBJECT_FIELD,
        "assumptions": _STRING_LIST_FIELD,
        "summary": _TEXT_FIELD,
    }),
    _contract("request_execution", required=("action",), fields={}),
    _contract("inspect_observation", required=("action",), fields={}),
    _contract("propose_work_design", required=("action", "work_design"), fields={
        "work_design": work_design_contract_description(),
        "assumptions": _STRING_LIST_FIELD,
        "summary": _TEXT_FIELD,
    }),
    _contract("create_part_jobs", required=("action",), fields={}),
    _contract("ask_user", required=("action", "questions"), fields={
        "questions": _QUESTION_LIST_FIELD,
        "reason": _TEXT_FIELD,
    }),
    _contract("stop", required=("action", "stop_reason"), fields={
        "stop_reason": _TEXT_FIELD,
        "reason": _TEXT_FIELD,
    }),
)

ACTION_CONTRACTS: Mapping[str, AgentActionContract] = MappingProxyType(
    {contract.action: contract for contract in _ACTION_CONTRACTS}
)
ACTION_ALLOWED_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {action: contract.allowed_fields for action, contract in ACTION_CONTRACTS.items()}
)
ACTION_REQUIRED_FIELDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {action: contract.required_fields for action, contract in ACTION_CONTRACTS.items()}
)


def action_contract(action: str) -> AgentActionContract:
    return ACTION_CONTRACTS[action]


def action_discriminator_description(allowed_actions: Iterable[str]) -> dict[str, Any]:
    """Describe the one string discriminator shared by every action variant."""

    active_actions = frozenset(allowed_actions)
    unknown = active_actions - set(ACTION_CONTRACTS)
    if unknown:
        raise ValueError("agent action contract references an unknown action")
    return {
        "expected_type": _ACTION_FIELD["type"],
        "allowed_values": sorted(active_actions),
    }


def agent_action_contract_description(
    allowed_actions: Iterable[str],
    *,
    allowed_context_keys: Iterable[str] = (),
    allowed_stop_reasons: Iterable[str] = (),
) -> dict[str, Any]:
    """Return the active registered-Skill variants for a provider request."""

    discriminator = action_discriminator_description(allowed_actions)
    active_actions = frozenset(discriminator["allowed_values"])
    context_keys = sorted(set(allowed_context_keys))
    stop_reasons = sorted(set(allowed_stop_reasons))
    variants: list[dict[str, Any]] = []
    for action in sorted(active_actions):
        contract = ACTION_CONTRACTS[action]
        fields = _thaw_description(contract.fields)
        if action == "request_context":
            fields["context_key"]["allowed_values"] = context_keys
        if action == "stop":
            fields["stop_reason"]["allowed_values"] = stop_reasons
        variants.append({
            "type": "object",
            "required_fields": sorted(contract.required_fields),
            "allowed_fields": sorted(contract.allowed_fields),
            "fields": fields,
            "additional_fields": False,
        })
    return {"type": "one_of", "variants": variants}


__all__ = [
    "ACTION_CONTRACTS",
    "ACTION_ALLOWED_FIELDS",
    "ACTION_REQUIRED_FIELDS",
    "AgentActionContract",
    "action_contract",
    "action_discriminator_description",
    "agent_action_contract_description",
    "MODEL_PROGRAM_SUBMISSION_FIELDS",
    "MODEL_PROGRAM_SUBMISSION_API_ID",
    "MODEL_PROGRAM_SUBMISSION_REQUESTED_OUTPUTS",
    "model_program_submission_contract_description",
]
