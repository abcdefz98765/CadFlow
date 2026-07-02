"""Optional JSON-contract adapter scaffold for future LLM providers."""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol, runtime_checkable

from ai_native_cad.agents.base import AgentAdapter
from ai_native_cad.agents.validation import validate_requirement_draft


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
    JSON requirement contract.
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
        raise NotImplementedError("JsonContractAgentAdapter currently supports parse_requirement only")

    def suggest_repair(
        self,
        failure: dict[str, Any],
        ir: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("JsonContractAgentAdapter currently supports parse_requirement only")

    def explain_review(
        self,
        report: dict[str, Any],
        trace: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("JsonContractAgentAdapter currently supports parse_requirement only")


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
