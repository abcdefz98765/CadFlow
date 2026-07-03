"""Optional JSON-contract adapter scaffold for future LLM providers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Protocol, runtime_checkable

from ai_native_cad.agents.base import AgentAdapter
from ai_native_cad.agents.provider_context import (
    contract_guide_for,
    provider_messages_for,
    provider_request_trace_summary,
    sanitize_provider_payload,
    sanitize_provider_string,
)
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


class JsonContractProviderError(RuntimeError):
    """Secret-safe wrapper for injected provider client failures."""

    def __init__(self, operation: str, category: str, *, retryable: bool = False) -> None:
        self.operation = operation
        self.category = category
        self.retryable = retryable
        super().__init__(f"JSON contract provider failed during {operation}: {category}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "json_contract_provider_error",
            "operation": self.operation,
            "category": self.category,
            "retryable": self.retryable,
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
        self._last_provider_request_trace: dict[str, Any] | None = None

    @property
    def provider_identity(self) -> dict[str, Any]:
        identity = self._config.provider_identity()
        client_identity = getattr(self.client, "provider_identity", None)
        if isinstance(client_identity, dict):
            identity.update(_sanitize_provider_identity(client_identity))
        return identity

    @property
    def last_provider_request_trace(self) -> dict[str, Any] | None:
        if self._last_provider_request_trace is None:
            return None
        return dict(self._last_provider_request_trace)

    def parse_requirement(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        request = self._with_provider_options(_requirement_contract_request(prompt, context))
        raw_response = _call_json_client(self.client, request, "parse_requirement")
        provider_requirement = _extract_json_object(raw_response)
        requirement = (
            _compile_provider_requirement(prompt, provider_requirement)
            if _uses_provider_contract_compiler(context)
            else provider_requirement
        )
        validate_requirement_draft(requirement)
        return requirement

    def create_plan(self, requirement: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        validate_requirement_draft(requirement)
        request = self._with_provider_options(_planning_contract_request(requirement, context))
        raw_response = _call_json_client(self.client, request, "create_plan")
        planning_artifact = _extract_json_object(raw_response)
        try:
            validate_planning_draft(planning_artifact)
        except Exception:
            if not _uses_provider_contract_compiler(context):
                raise
            planning_artifact = _compile_provider_planning(requirement)
            validate_planning_draft(planning_artifact)
        return planning_artifact

    def parse_revision_request(
        self,
        prompt: str,
        model_context: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = self._with_provider_options(_revision_intent_contract_request(prompt, model_context, context or {}))
        raw_response = _call_json_client(self.client, request, "parse_revision_request")
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
        raw_response = _call_json_client(self.client, request, "create_revision_plan")
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
        raw_response = _call_json_client(self.client, request, "suggest_repair")
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
        raw_response = _call_json_client(self.client, request, "explain_review")
        review_explanation = _extract_json_object(raw_response)
        validate_review_explanation(review_explanation)
        return review_explanation

    def _with_provider_options(self, request: dict[str, Any]) -> dict[str, Any]:
        request = dict(request)
        request["provider_options"] = self._config.request_options()
        request["request_trace_summary"] = provider_request_trace_summary(
            operation=str(request["operation"]),
            provider_identity=self.provider_identity,
            message_count=len(request.get("messages", [])),
            payload_shape=request.get("payload_shape", {}),
            context=request.get("context"),
        )
        self._last_provider_request_trace = dict(request["request_trace_summary"])
        return request


def _requirement_contract_request(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    sanitized_context = _contract_context(context)
    return {
        "operation": "parse_requirement",
        "response_format": {"type": "json_object"},
        "messages": provider_messages_for(
            operation="parse_requirement",
            contract_instruction=contract_guide_for("parse_requirement"),
            user_payload=prompt,
            context=sanitized_context,
        ),
        "context": sanitized_context,
        "payload_shape": {"kind": "prompt_payload", "top_level_keys": ["prompt"]},
    }


def _planning_contract_request(requirement: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    sanitized_context = _contract_context(context)
    sanitized_requirement = sanitize_provider_payload(requirement)
    return {
        "operation": "create_plan",
        "response_format": {"type": "json_object"},
        "messages": provider_messages_for(
            operation="create_plan",
            contract_instruction=contract_guide_for("create_plan"),
            user_payload=sanitized_requirement,
            context=sanitized_context,
        ),
        "context": sanitized_context,
        "payload_shape": _payload_shape_for("requirement_payload", sanitized_requirement),
    }


def _repair_contract_request(failure: dict[str, Any], ir: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    sanitized_context = _contract_context(context)
    sanitized_failure = sanitize_provider_payload(failure)
    sanitized_ir = sanitize_provider_payload(ir)
    return {
        "operation": "suggest_repair",
        "response_format": {"type": "json_object"},
        "messages": provider_messages_for(
            operation="suggest_repair",
            contract_instruction=contract_guide_for("suggest_repair"),
            user_payload={"failure": sanitized_failure, "ir": sanitized_ir},
            context=sanitized_context,
        ),
        "context": sanitized_context,
        "payload_shape": {"kind": "repair_payload", "top_level_keys": ["failure", "ir"]},
    }


def _revision_intent_contract_request(
    prompt: str,
    model_context: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    sanitized_context = _contract_context(context)
    sanitized_model_context = sanitize_provider_payload(model_context)
    return {
        "operation": "parse_revision_request",
        "response_format": {"type": "json_object"},
        "messages": provider_messages_for(
            operation="parse_revision_request",
            contract_instruction=contract_guide_for("parse_revision_request"),
            user_payload={"prompt": sanitize_provider_string(prompt), "model_context": sanitized_model_context},
            context=sanitized_context,
        ),
        "context": sanitized_context,
        "payload_shape": {"kind": "revision_intent_payload", "top_level_keys": ["model_context", "prompt"]},
    }


def _revision_plan_contract_request(
    change_intent: dict[str, Any],
    model_context: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    sanitized_context = _contract_context(context)
    sanitized_change_intent = sanitize_provider_payload(change_intent, preserve_cad_paths=True)
    sanitized_model_context = sanitize_provider_payload(model_context)
    return {
        "operation": "create_revision_plan",
        "response_format": {"type": "json_object"},
        "messages": provider_messages_for(
            operation="create_revision_plan",
            contract_instruction=contract_guide_for("create_revision_plan"),
            user_payload={"change_intent": sanitized_change_intent, "model_context": sanitized_model_context},
            context=sanitized_context,
        ),
        "context": sanitized_context,
        "payload_shape": {"kind": "revision_plan_payload", "top_level_keys": ["change_intent", "model_context"]},
    }


def _review_contract_request(report: dict[str, Any], trace: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    sanitized_context = _contract_context(context)
    sanitized_report = sanitize_provider_payload(report)
    sanitized_trace = sanitize_provider_payload(trace)
    return {
        "operation": "explain_review",
        "response_format": {"type": "json_object"},
        "messages": provider_messages_for(
            operation="explain_review",
            contract_instruction=contract_guide_for("explain_review"),
            user_payload={"report": sanitized_report, "trace": sanitized_trace},
            context=sanitized_context,
        ),
        "context": sanitized_context,
        "payload_shape": {"kind": "review_payload", "top_level_keys": ["report", "trace"]},
    }


def _contract_context(context: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = ("overrides", "workflow_stage", "target_contract", "provider_contract_mode")
    return {
        key: sanitize_provider_payload(context[key], preserve_cad_paths=True)
        for key in allowed_keys
        if key in context
    }


def _payload_shape_for(kind: str, payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return {"kind": kind, "top_level_keys": sorted(str(key) for key in payload)}
    return {"kind": kind, "top_level_keys": []}


def _call_json_client(client: JsonContractClient | JsonContractCallable, request: dict[str, Any], operation: str) -> Any:
    generate = getattr(client, "generate_json_contract", None)
    try:
        if callable(generate):
            return generate(request)
        if callable(client):
            return client(request)
    except JsonContractProviderError:
        raise
    except Exception as exc:
        raise JsonContractProviderError(
            operation,
            _provider_error_category(exc),
            retryable=_provider_error_retryable(exc),
        ) from None
    raise TypeError("JSON contract client must be callable or implement generate_json_contract(request)")


def _uses_provider_contract_compiler(context: dict[str, Any]) -> bool:
    return context.get("provider_contract_mode") == "extract_then_compile"


def _compile_provider_requirement(prompt: str, provider_requirement: dict[str, Any]) -> dict[str, Any]:
    """Compile provider-extracted fields into the local requirement contract."""

    from ai_native_cad.generator import list_parts
    from ai_native_cad.requirements import RequirementAgent

    if not isinstance(provider_requirement, dict):
        raise ValueError("provider requirement extraction must be a JSON object")

    overrides: dict[str, Any] = {}
    part_type = _normalized_part_type(provider_requirement.get("part_type"), prompt=prompt)
    if part_type is not None:
        if part_type not in set(list_parts()):
            raise ValueError(f"unsupported provider part_type: {part_type}")
        overrides["part_type"] = part_type
    dimensions = _normalized_dimensions(provider_requirement.get("dimensions"), part_type=part_type)
    if dimensions:
        overrides["dimensions"] = dimensions
    features = _normalized_features(provider_requirement.get("features"), part_type=part_type)
    if features:
        overrides["features"] = features
    unit = provider_requirement.get("unit")
    if isinstance(unit, str) and unit.strip().lower() in {"mm", "millimeter", "millimeters", "millimetre", "millimetres"}:
        overrides["unit"] = "mm"
    outputs = provider_requirement.get("outputs")
    if isinstance(outputs, list):
        safe_outputs = [item.lower() for item in outputs if isinstance(item, str) and item.lower() in {"step", "stl"}]
        if safe_outputs:
            overrides["outputs"] = sorted(set(safe_outputs))
    check_level = provider_requirement.get("check_level")
    if isinstance(check_level, str) and check_level.strip():
        overrides["check_level"] = check_level
    assumptions = provider_requirement.get("assumptions")
    if isinstance(assumptions, list):
        safe_assumptions = [item for item in assumptions if isinstance(item, str) and item.strip()]
        if safe_assumptions:
            overrides["assumptions"] = safe_assumptions

    return RequirementAgent().parse(prompt, overrides=overrides)


def _compile_provider_planning(requirement: dict[str, Any]) -> dict[str, Any]:
    """Compile a validated requirement into local planning when provider shape drifts."""

    from ai_native_cad.planning import create_planning_artifact

    return create_planning_artifact(requirement)


def _normalized_part_type(value: Any, *, prompt: str = "") -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "washer": "spacer",
        "spacer_washer": "spacer",
        "right_angle_bracket": "simple_bracket",
        "l_bracket": "simple_bracket",
        "angle_bracket": "simple_bracket",
        "button": "circular_button",
        "round_button": "circular_button",
        "plate": "mounting_plate",
        "pcb_plate": "mounting_plate",
    }
    if normalized == "bracket" and _looks_like_simple_bracket_prompt(prompt):
        return "simple_bracket"
    return aliases.get(normalized, normalized)


def _looks_like_simple_bracket_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    return (
        "simple" in lowered
        or "right-angle" in lowered
        or "right angle" in lowered
        or "l-bracket" in lowered
        or "l bracket" in lowered
    )


def _normalized_dimensions(value: Any, *, part_type: str | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    dimensions: dict[str, Any] = {}
    aliases = _dimension_aliases(part_type)
    supported = _supported_dimension_names(part_type)
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            continue
        key = raw_key.strip().lower().replace("-", "_").replace(" ", "_")
        key = aliases.get(key, key)
        number = _number_or_none(raw_value)
        if number is not None and (supported is None or key in supported):
            dimensions[key] = number
    if part_type == "circular_button":
        if "body_diameter" in dimensions and "button_diameter" not in dimensions:
            dimensions["button_diameter"] = dimensions["body_diameter"]
        if "body_height" in dimensions and "button_height" not in dimensions:
            dimensions["button_height"] = dimensions["body_height"]
    return dimensions


def _dimension_aliases(part_type: str | None) -> dict[str, str]:
    common = {
        "diameter": "body_diameter" if part_type == "circular_button" else "outer_diameter",
        "height": "body_height" if part_type == "circular_button" else "thickness",
        "thick": "thickness",
    }
    by_part = {
        "spacer": {"od": "outer_diameter", "id": "inner_diameter", "inner_dia": "inner_diameter", "outer_dia": "outer_diameter"},
        "circular_button": {"tall": "body_height", "button_dia": "button_diameter", "button_height": "button_height"},
        "simple_bracket": {"length": "base_length", "width": "base_width", "tall": "height"},
        "enclosure_base": {"length": "outer_length", "width": "outer_width", "depth": "outer_width", "height": "outer_height"},
    }
    aliases = dict(common)
    aliases.update(by_part.get(part_type or "", {}))
    return aliases


def _supported_dimension_names(part_type: str | None) -> set[str] | None:
    return {
        "mounting_plate": {"length", "width", "thickness"},
        "spacer": {"outer_diameter", "inner_diameter", "thickness"},
        "simple_bracket": {"base_length", "base_width", "height", "thickness"},
        "wall_bracket": {"base_width", "base_depth", "wall_height", "material_thickness"},
        "circular_button": {"body_diameter", "body_height", "button_diameter", "button_height"},
        "enclosure_base": {"outer_length", "outer_width", "outer_height", "wall_thickness"},
        "enclosure_lid": {"length", "width", "thickness"},
    }.get(part_type or "")


def _normalized_features(value: Any, *, part_type: str | None) -> dict[str, Any]:
    supported = _supported_feature_names(part_type)
    if isinstance(value, dict):
        return {
            str(key): _normalized_feature_value(item)
            for key, item in value.items()
            if isinstance(key, str) and isinstance(item, dict) and (supported is None or key in supported)
        }
    if not isinstance(value, list):
        return {}
    features: dict[str, Any] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or item.get("type") or item.get("name") or "").lower()
        if "hole" in kind or item.get("count") or item.get("diameter") or item.get("diameter_mm"):
            key = "base_holes" if part_type == "simple_bracket" else "holes"
            if supported is None or key in supported:
                features[key] = _normalized_feature_value(item)
    return features


def _supported_feature_names(part_type: str | None) -> set[str] | None:
    return {
        "mounting_plate": {"holes", "mounting_holes", "chamfer"},
        "spacer": set(),
        "simple_bracket": {"holes", "base_holes", "fillet"},
        "wall_bracket": {"base_holes", "wall_hole", "fillet"},
        "circular_button": {
            "switch_pocket",
            "actuator_post",
            "contact_slots",
            "wire_exit",
            "anti_slip_feet",
            "edge_finish",
        },
        "enclosure_base": {"bosses", "bottom_cutout", "fillet"},
        "enclosure_lid": {"holes", "chamfer"},
    }.get(part_type or "")


def _normalized_feature_value(value: dict[str, Any]) -> dict[str, Any]:
    feature: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip().lower().replace("-", "_").replace(" ", "_")
        if key in {"kind", "name"}:
            continue
        if key == "diameter_mm":
            key = "diameter"
        if key == "pattern" and isinstance(raw_value, str) and raw_value.lower() == "corner":
            feature["positions"] = "corner_4"
        number = _number_or_none(raw_value)
        if number is not None:
            feature[key] = number
        elif isinstance(raw_value, (str, bool)):
            feature[key] = raw_value
    return feature


def _number_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            number = float(text)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    return None


def _provider_error_category(exc: Exception) -> str:
    text = f"{type(exc).__name__} {exc}".lower()
    if "timeout" in text or isinstance(exc, TimeoutError):
        return "timeout"
    if "rate" in text or "429" in text or "limit" in text:
        return "rate_limited"
    if "auth" in text or "credential" in text or "permission" in text or "401" in text or "403" in text:
        return "auth_failed"
    if "network" in text or "connection" in text or "dns" in text:
        return "network_error"
    return "client_error"


def _provider_error_retryable(exc: Exception) -> bool:
    return _provider_error_category(exc) in {"timeout", "rate_limited", "network_error"}


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
