"""Provider clients for JSON-contract agent adapters.

These clients are intentionally thin. They translate CadFlow JSON-contract
requests into provider API payloads, read credentials from environment variables
at call time, and return the raw provider response for JsonContractAgentAdapter
to validate locally.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from typing import Any, Callable
from urllib import error, request


UrlOpen = Callable[..., Any]


@dataclass(frozen=True)
class JsonProviderEndpoint:
    provider: str
    model: str
    api_key_env_var: str
    base_url: str
    endpoint: str
    api_shape: str
    timeout_seconds: int = 30
    max_retries: int = 0

    @property
    def url(self) -> str:
        return self.base_url.rstrip("/") + "/" + self.endpoint.strip("/")


class OpenAICompatibleJsonContractClient:
    """OpenAI-compatible `/chat/completions` client.

    This is suitable for providers such as DeepSeek that expose an
    OpenAI-compatible chat completions API with JSON object mode.
    """

    def __init__(self, endpoint: JsonProviderEndpoint, *, urlopen: UrlOpen | None = None) -> None:
        if endpoint.api_shape != "chat_completions":
            raise ValueError("OpenAICompatibleJsonContractClient requires chat_completions api_shape")
        self._endpoint = endpoint
        self._urlopen = urlopen or request.urlopen

    @property
    def provider_identity(self) -> dict[str, Any]:
        return {
            "provider": self._endpoint.provider,
            "model": self._endpoint.model,
            "adapter": "json_contract",
            "network": "client_injected",
            "api_shape": self._endpoint.api_shape,
            "api_key_required": True,
            "api_key_config": "env_var_name_configured",
        }

    def generate_json_contract(self, contract_request: dict[str, Any]) -> Any:
        payload = {
            "model": self._endpoint.model,
            "messages": contract_request["messages"],
            "response_format": contract_request.get("response_format", {"type": "json_object"}),
            "temperature": 0,
        }
        return _post_json_with_bearer_auth(
            endpoint=self._endpoint,
            payload=payload,
            urlopen=self._urlopen,
            timeout_seconds=_request_timeout(contract_request, self._endpoint.timeout_seconds),
            max_retries=_request_retries(contract_request, self._endpoint.max_retries),
        )


class OpenAIResponsesJsonContractClient:
    """OpenAI Responses API client for JSON-contract generation."""

    def __init__(self, endpoint: JsonProviderEndpoint, *, urlopen: UrlOpen | None = None) -> None:
        if endpoint.api_shape != "responses":
            raise ValueError("OpenAIResponsesJsonContractClient requires responses api_shape")
        self._endpoint = endpoint
        self._urlopen = urlopen or request.urlopen

    @property
    def provider_identity(self) -> dict[str, Any]:
        return {
            "provider": self._endpoint.provider,
            "model": self._endpoint.model,
            "adapter": "json_contract",
            "network": "client_injected",
            "api_shape": self._endpoint.api_shape,
            "api_key_required": True,
            "api_key_config": "env_var_name_configured",
        }

    def generate_json_contract(self, contract_request: dict[str, Any]) -> Any:
        payload = {
            "model": self._endpoint.model,
            "input": [
                {"role": message["role"], "content": message["content"]}
                for message in contract_request["messages"]
            ],
            "text": {
                "format": contract_request.get("response_format", {"type": "json_object"}),
            },
        }
        return _post_json_with_bearer_auth(
            endpoint=self._endpoint,
            payload=payload,
            urlopen=self._urlopen,
            timeout_seconds=_request_timeout(contract_request, self._endpoint.timeout_seconds),
            max_retries=_request_retries(contract_request, self._endpoint.max_retries),
        )


def make_json_contract_adapter_from_env(
    provider: str,
    *,
    model: str | None = None,
    timeout_seconds: int | None = None,
    max_retries: int | None = None,
    urlopen: UrlOpen | None = None,
) -> JsonContractAgentAdapter:
    """Create an opt-in provider-backed JsonContractAgentAdapter.

    Supported providers:
    - `deepseek`: OpenAI-compatible chat completions.
    - `openai`: OpenAI Responses API, suitable for Codex-family model testing.
    """

    from ai_native_cad.agents.json_contract import JsonContractAgentAdapter, JsonContractProviderConfig

    normalized = provider.lower().strip()
    if normalized == "deepseek":
        endpoint = _deepseek_endpoint(model, timeout_seconds, max_retries)
        client = OpenAICompatibleJsonContractClient(endpoint, urlopen=urlopen)
    elif normalized in {"openai", "oai"}:
        endpoint = _openai_responses_endpoint(model, timeout_seconds, max_retries)
        client = OpenAIResponsesJsonContractClient(endpoint, urlopen=urlopen)
    else:
        raise ValueError(f"unsupported JSON contract provider: {provider}")

    config = JsonContractProviderConfig(
        provider=endpoint.provider,
        model=endpoint.model,
        enabled=True,
        timeout_seconds=endpoint.timeout_seconds,
        max_retries=endpoint.max_retries,
        api_key_env_var=endpoint.api_key_env_var,
    )
    return JsonContractAgentAdapter(client, config=config)


def _deepseek_endpoint(
    model: str | None,
    timeout_seconds: int | None,
    max_retries: int | None,
) -> JsonProviderEndpoint:
    return JsonProviderEndpoint(
        provider="deepseek",
        model=model or os.environ.get("CADFLOW_DEEPSEEK_MODEL", "deepseek-chat"),
        api_key_env_var="DEEPSEEK_API_KEY",
        base_url=os.environ.get("CADFLOW_DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        endpoint=os.environ.get("CADFLOW_DEEPSEEK_ENDPOINT", "/v1/chat/completions"),
        api_shape="chat_completions",
        timeout_seconds=_env_int("CADFLOW_PROVIDER_TIMEOUT_SECONDS", timeout_seconds, 30),
        max_retries=_env_int("CADFLOW_PROVIDER_MAX_RETRIES", max_retries, 0),
    )


def _openai_responses_endpoint(
    model: str | None,
    timeout_seconds: int | None,
    max_retries: int | None,
) -> JsonProviderEndpoint:
    return JsonProviderEndpoint(
        provider="openai",
        model=model or os.environ.get("CADFLOW_OPENAI_MODEL", "gpt-5.1-codex"),
        api_key_env_var="OPENAI_API_KEY",
        base_url=os.environ.get("CADFLOW_OPENAI_BASE_URL", "https://api.openai.com"),
        endpoint=os.environ.get("CADFLOW_OPENAI_ENDPOINT", "/v1/responses"),
        api_shape="responses",
        timeout_seconds=_env_int("CADFLOW_PROVIDER_TIMEOUT_SECONDS", timeout_seconds, 30),
        max_retries=_env_int("CADFLOW_PROVIDER_MAX_RETRIES", max_retries, 0),
    )


def _post_json_with_bearer_auth(
    *,
    endpoint: JsonProviderEndpoint,
    payload: dict[str, Any],
    urlopen: UrlOpen,
    timeout_seconds: int,
    max_retries: int,
) -> Any:
    api_key = os.environ.get(endpoint.api_key_env_var)
    if not api_key:
        raise RuntimeError("provider credential is not configured")

    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    attempts = max_retries + 1
    for attempt in range(attempts):
        http_request = request.Request(endpoint.url, data=body, headers=headers, method="POST")
        try:
            with urlopen(http_request, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
                parsed = json.loads(response_body)
                if not isinstance(parsed, dict):
                    raise RuntimeError("provider returned a non-object JSON response")
                return parsed
        except error.HTTPError as exc:
            if exc.code in {408, 409, 425, 429, 500, 502, 503, 504} and attempt + 1 < attempts:
                _backoff(attempt)
                continue
            raise RuntimeError(f"provider http {exc.code}") from None
        except error.URLError as exc:
            if attempt + 1 < attempts:
                _backoff(attempt)
                continue
            reason = str(getattr(exc, "reason", "")).lower()
            if "timed out" in reason or "timeout" in reason:
                raise TimeoutError("provider request timed out") from None
            raise RuntimeError("provider network error") from None
        except TimeoutError:
            if attempt + 1 < attempts:
                _backoff(attempt)
                continue
            raise
        except json.JSONDecodeError:
            raise RuntimeError("provider returned invalid JSON") from None

    raise RuntimeError("provider request failed")


def _request_timeout(contract_request: dict[str, Any], fallback: int) -> int:
    options = contract_request.get("provider_options")
    if isinstance(options, dict) and isinstance(options.get("timeout_seconds"), int):
        return options["timeout_seconds"]
    return fallback


def _request_retries(contract_request: dict[str, Any], fallback: int) -> int:
    options = contract_request.get("provider_options")
    if isinstance(options, dict) and isinstance(options.get("max_retries"), int):
        return options["max_retries"]
    return fallback


def _env_int(name: str, override: int | None, default: int) -> int:
    if override is not None:
        return override
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _backoff(attempt: int) -> None:
    time.sleep(min(0.25 * (2 ** attempt), 2.0))
