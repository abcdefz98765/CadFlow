"""Provider-neutral payload sanitization shared by canonical and compatibility adapters."""

from __future__ import annotations

import re
from typing import Any

_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/][^\s\"'{}[\],]+|/[Uu]sers/[^\s\"'{}[\],]+|/home/[^\s\"'{}[\],]+)"
)
_API_ENV_VAR_RE = re.compile(
    r"\b[A-Z][A-Z0-9_]*(?:API[_-]?KEY|SECRET|TOKEN|PASSWORD|ACCESS[_-]?KEY)[A-Z0-9_]*\b"
)
_SECRET_VALUE_RE = re.compile(
    r"\b(?:sk|pk|pat|ghp|gho|ghu|ghs|xoxb|xoxp)-[A-Za-z0-9_-]{8,}\b"
)
_CONTRACT_FIELD_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,119}")
_CONTRACT_FIELD_PATH_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]{0,119}(?:\[\])?"
    r"(?:\.[A-Za-z_][A-Za-z0-9_]{0,119}(?:\[\])?)*"
)
_PRIVATE_KEY_TOKENS = (
    "api_key", "apikey", "access_key", "secret", "token", "password",
    "credential", "transcript", "chat_log", "chatlog", "runtime_log",
    "runtime_logs", "runtime", "log_text", "logs", "agent_trace", "provider_response",
)
_FILESYSTEM_KEYS = {
    "run_dir", "output_dir", "output_root", "project_root", "root_run_id",
    "workspace_root", "root",
}


def sanitize_provider_payload(value: Any, *, preserve_cad_paths: bool = False) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_provider_payload(item, preserve_cad_paths=preserve_cad_paths)
            for key, item in value.items()
            if not _private_key(str(key), item, preserve_cad_paths)
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_provider_payload(item, preserve_cad_paths=preserve_cad_paths) for item in value]
    if isinstance(value, str):
        return sanitize_provider_string(value)
    return value


def sanitize_provider_string(value: str) -> str:
    value = _ABSOLUTE_PATH_RE.sub("[redacted-local-path]", value)
    value = _API_ENV_VAR_RE.sub("[redacted-api-env-var]", value)
    return _SECRET_VALUE_RE.sub("[redacted-secret]", value)


def is_safe_contract_field_name(value: Any) -> bool:
    return isinstance(value, str) and bool(_CONTRACT_FIELD_NAME_RE.fullmatch(value))


def is_safe_contract_field_path(value: Any) -> bool:
    return isinstance(value, str) and bool(_CONTRACT_FIELD_PATH_RE.fullmatch(value))


def _private_key(key: str, value: Any, preserve_cad_paths: bool) -> bool:
    lowered = key.lower()
    if any(token in lowered for token in _PRIVATE_KEY_TOKENS):
        return True
    if lowered.endswith("_env_var") or lowered.endswith("_env"):
        return True
    if lowered == "path":
        return not (
            preserve_cad_paths
            and isinstance(value, str)
            and bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", value))
        )
    if lowered == "field_path":
        return not is_safe_contract_field_path(value)
    return (
        lowered in _FILESYSTEM_KEYS
        or lowered.endswith("_dir")
        or lowered.endswith("_root")
        or lowered.endswith("_path")
    )


__all__ = [
    "is_safe_contract_field_name",
    "is_safe_contract_field_path",
    "sanitize_provider_payload",
    "sanitize_provider_string",
]
