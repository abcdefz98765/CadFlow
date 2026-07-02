"""Optional JSON-contract adapter scaffold for future LLM providers."""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol, runtime_checkable

from ai_native_cad.agents.base import AgentAdapter
from ai_native_cad.agents.validation import (
    validate_planning_draft,
    validate_repair_suggestion,
    validate_requirement_draft,
    validate_review_explanation,
)


JsonContractCallable = Callable[[dict[str, Any]], Any]


@runtime_checkable
class JsonContractClient(Protocol):
    """Provider-neutral boundary for JSON contract generation."""

    @property
    def provider_identity(self) -> dict[str, Any]:
        """Return a secret-free provider identity."""

    def generate_json_contract(self, request: dict[str, Any]) -> Any:
        """Return a JSON object, JSON string, or provider response wrapper."""


class JsonContractAgentAdapter(AgentAdapter):
    """Adapter scaffold for JSON-only LLM contract generation.

    The adapter does not import an LLM SDK and does not perform network I/O by
    itself. A caller must explicitly inject a client/callable that returns a
    JSON contract for one AgentAdapter operation.
    """

    def __init__(
        self,
        client: JsonContractClient | JsonContractCallable,
        *,
        provider: str = "json-contract",
        model: str | None = None,
    ) -> None:
        self.client = client
        self._provider = provider
        self._model = model

    @property
    def provider_identity(self) -> dict[str, Any]:
        identity = {
            "provider": self._provider,
            "adapter": "json_contract",
            "network": "client_injected",
            "api_key_required": "provider_dependent",
        }
        if self._model:
            identity["model"] = self._model
        client_identity = getattr(self.client, "provider_identity", None)
        if isinstance(client_identity, dict):
            identity.update(_sanitize_provider_identity(client_identity))
        return identity

    def parse_requirement(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        request = _requirement_contract_request(prompt, context or {})
        raw_response = _call_json_client(self.client, request)
        requirement = _extract_json_object(raw_response)
        validate_requirement_draft(requirement)
        return requirement

    def create_plan(self, requirement: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        validate_requirement_draft(requirement)
        request = _planning_contract_request(requirement, context or {})
        raw_response = _call_json_client(self.client, request)
        planning_artifact = _extract_json_object(raw_response)
        validate_planning_draft(planning_artifact)
        return planning_artifact

    def suggest_repair(
        self,
        failure: dict[str, Any],
        ir: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = _repair_contract_request(failure, ir, context or {})
        raw_response = _call_json_client(self.client, request)
        repair_suggestion = _extract_json_object(raw_response)
        validate_repair_suggestion(repair_suggestion)
        return repair_suggestion

    def explain_review(
        self,
        report: dict[str, Any],
        trace: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = _review_contract_request(report, trace, context or {})
        raw_response = _call_json_client(self.client, request)
        review_explanation = _extract_json_object(raw_response)
        validate_review_explanation(review_explanation)
        return review_explanation


def _requirement_contract_request(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "parse_requirement",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only a JSON object matching CadFlow requirement.json. "
                    "Do not include markdown, prose, CAD code, Python code, shell commands, or paths."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "context": _contract_context(context),
    }


def _planning_contract_request(requirement: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "create_plan",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only a JSON object matching CadFlow planning_artifact.json. "
                    "Do not include markdown, prose, CAD code, Python code, shell commands, or paths."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(requirement, sort_keys=True),
            },
        ],
        "context": _contract_context(context),
    }


def _repair_contract_request(failure: dict[str, Any], ir: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "suggest_repair",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only a JSON object matching the CadFlow repair suggestion contract. "
                    "It must contain analysis and repair objects. Do not include markdown, prose, "
                    "CAD code, Python code, shell commands, or paths."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"failure": failure, "ir": ir}, sort_keys=True),
            },
        ],
        "context": _contract_context(context),
    }


def _review_contract_request(report: dict[str, Any], trace: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": "explain_review",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only a JSON object matching the CadFlow review explanation contract. "
                    "It must contain status and summary fields. Do not include markdown, prose, "
                    "CAD code, Python code, shell commands, or paths."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"report": report, "trace": trace}, sort_keys=True),
            },
        ],
        "context": _contract_context(context),
    }


def _contract_context(context: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = ("overrides", "workflow_stage", "target_contract")
    return {key: context[key] for key in allowed_keys if key in context}


def _call_json_client(client: JsonContractClient | JsonContractCallable, request: dict[str, Any]) -> Any:
    generate = getattr(client, "generate_json_contract", None)
    if callable(generate):
        return generate(request)
    if callable(client):
        return client(request)
    raise TypeError("JSON contract client must be callable or implement generate_json_contract(request)")


def _extract_json_object(raw_response: Any) -> dict[str, Any]:
    provider_content = _extract_provider_content(raw_response)
    if provider_content is not raw_response:
        return _extract_json_object(provider_content)
    if isinstance(raw_response, dict) and "content" in raw_response and len(raw_response) <= 3:
        return _extract_json_object(raw_response["content"])
    if isinstance(raw_response, dict):
        return dict(raw_response)
    if isinstance(raw_response, bytes):
        raw_response = raw_response.decode("utf-8")
    if isinstance(raw_response, str):
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON contract client returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("JSON contract client output must be a JSON object")
        return parsed
    raise ValueError("JSON contract client output must be a JSON object")


def _extract_provider_content(raw_response: Any) -> Any:
    if not isinstance(raw_response, dict):
        return raw_response

    if "output_text" in raw_response:
        return raw_response["output_text"]

    choices = raw_response.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict) and "content" in message:
                return message["content"]
            if "text" in first_choice:
                return first_choice["text"]

    output = raw_response.get("output")
    if isinstance(output, list) and output:
        first_output = output[0]
        if isinstance(first_output, dict):
            content = first_output.get("content")
            if isinstance(content, list) and content:
                first_content = content[0]
                if isinstance(first_content, dict):
                    if "text" in first_content:
                        return first_content["text"]
                    if "json" in first_content:
                        return first_content["json"]

    return raw_response


def _sanitize_provider_identity(identity: dict[str, Any]) -> dict[str, Any]:
    blocked_tokens = ("key", "secret", "token", "password", "prompt", "transcript", "path")
    sanitized: dict[str, Any] = {}
    for key, value in identity.items():
        lowered = str(key).lower()
        if any(token in lowered for token in blocked_tokens):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
    return sanitized
