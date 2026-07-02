"""Optional JSON-contract adapter scaffold for future LLM providers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Protocol, runtime_checkable

from ai_native_cad.agents.base import AgentAdapter
from ai_native_cad.agents.validation import (
    validate_adapter_result,
    validate_planning_draft,
    validate_repair_suggestion,
    validate_requirement_draft,
    validate_review_explanation,
)


JsonContractCallable = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class JsonContractProviderConfig:
    """Secret-free provider configuration for injected JSON-contract clients."""

    provider: str = "json-contract"
    model: str | None = None
    enabled: bool = False
    timeout_seconds: int = 30
    max_retries: int = 0
    api_key_env_var: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("JSON contract provider must be a non-empty string")
        if not isinstance(self.enabled, bool):
            raise ValueError("JSON contract provider enabled flag must be boolean")
        if not isinstance(self.timeout_seconds, int) or not 1 <= self.timeout_seconds <= 300:
            raise ValueError("JSON contract provider timeout_seconds must be between 1 and 300")
        if not isinstance(self.max_retries, int) or not 0 <= self.max_retries <= 5:
            raise ValueError("JSON contract provider max_retries must be between 0 and 5")
        if self.model is not None and (not isinstance(self.model, str) or not self.model.strip()):
            raise ValueError("JSON contract provider model must be a non-empty string when set")
        if self.api_key_env_var is not None:
            if not isinstance(self.api_key_env_var, str) or not self.api_key_env_var.strip():
                raise ValueError("JSON contract provider api_key_env_var must be a non-empty string when set")
            if any(part in self.api_key_env_var for part in ("/", "\\", ":", " ")):
                raise ValueError("JSON contract provider api_key_env_var must be an environment variable name")

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "JsonContractProviderConfig":
        """Create config from plain data without reading provider secrets."""
        if not isinstance(value, dict):
            raise ValueError("JSON contract provider config must be a dictionary")
        allowed = {"provider", "model", "enabled", "timeout_seconds", "max_retries", "api_key_env_var"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unsupported JSON contract provider config fields: {', '.join(unknown)}")
        return cls(**{key: value[key] for key in allowed if key in value})

    def provider_identity(self) -> dict[str, Any]:
        """Return secret-free identity metadata for logs and traces."""
        identity: dict[str, Any] = {
            "provider": self.provider,
            "adapter": "json_contract",
            "network": "client_injected",
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "api_key_required": self.api_key_env_var is not None,
            "api_key_config": "env_var_name_configured" if self.api_key_env_var else "not_configured",
        }
        if self.model:
            identity["model"] = self.model
        return identity

    def request_options(self) -> dict[str, Any]:
        """Return non-secret options that an injected client may honor."""
        return {
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }


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
        config: JsonContractProviderConfig | dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        if config is None:
            self._config = JsonContractProviderConfig(provider=provider, model=model)
        elif isinstance(config, JsonContractProviderConfig):
            self._config = config
        else:
            self._config = JsonContractProviderConfig.from_mapping(config)

    @property
    def provider_identity(self) -> dict[str, Any]:
        identity = self._config.provider_identity()
        client_identity = getattr(self.client, "provider_identity", None)
        if isinstance(client_identity, dict):
            identity.update(_sanitize_provider_identity(client_identity))
        return identity

    def parse_requirement(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        request = self._with_provider_options(_requirement_contract_request(prompt, context or {}))
        raw_response = _call_json_client(self.client, request)
        requirement = _extract_json_object(raw_response)
        validate_requirement_draft(requirement)
        return requirement

    def create_plan(self, requirement: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        validate_requirement_draft(requirement)
        request = self._with_provider_options(_planning_contract_request(requirement, context or {}))
        raw_response = _call_json_client(self.client, request)
        planning_artifact = _extract_json_object(raw_response)
        validate_planning_draft(planning_artifact)
        return planning_artifact

    def parse_revision_request(
        self,
        prompt: str,
        model_context: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._with_provider_options(_revision_intent_contract_request(prompt, model_context, context or {}))
        raw_response = _call_json_client(self.client, request)
        change_intent = _extract_json_object(raw_response)
        validate_adapter_result("parse_revision_request", change_intent)
        return change_intent

    def create_revision_plan(
        self,
        change_intent: dict[str, Any],
        model_context: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        validate_adapter_result("parse_revision_request", change_intent)
        request = self._with_provider_options(_revision_plan_contract_request(change_intent, model_context, context or {}))
        raw_response = _call_json_client(self.client, request)
        revision_plan = _extract_json_object(raw_response)
        validate_adapter_result("create_revision_plan", revision_plan)
        return revision_plan

    def suggest_repair(
        self,
        failure: dict[str, Any],
        ir: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._with_provider_options(_repair_contract_request(failure, ir, context or {}))
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
        request = self._with_provider_options(_review_contract_request(report, trace, context or {}))
        raw_response = _call_json_client(self.client, request)
        review_explanation = _extract_json_object(raw_response)
        validate_review_explanation(review_explanation)
        return review_explanation

    def _with_provider_options(self, request: dict[str, Any]) -> dict[str, Any]:
        request = dict(request)
        request["provider_options"] = self._config.request_options()
        return request


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


def _revision_intent_contract_request(
    prompt: str,
    model_context: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "operation": "parse_revision_request",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only a JSON object matching CadFlow revision change intent. "
                    "Do not include markdown, prose, CAD code, Python code, shell commands, or paths."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"prompt": prompt, "model_context": model_context}, sort_keys=True),
            },
        ],
        "context": _contract_context(context),
    }


def _revision_plan_contract_request(
    change_intent: dict[str, Any],
    model_context: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "operation": "create_revision_plan",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only a JSON object matching CadFlow revision_plan.json. "
                    "Do not include markdown, prose, CAD code, Python code, shell commands, or paths."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"change_intent": change_intent, "model_context": model_context},
                    sort_keys=True,
                ),
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
