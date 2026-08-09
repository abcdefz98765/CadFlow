"""Allowlisted local provider credential discovery without environment mutation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_PROVIDER_VARIABLES = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "oai": "OPENAI_API_KEY",
}
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class CredentialResolution:
    value: str | None
    source: str
    variable: str | None

    def public(self) -> dict[str, str | bool | None]:
        """Describe availability without returning the credential value."""

        return {
            "available": bool(self.value),
            "source": self.source,
            "variable": self.variable,
            "secret_exposed": False,
        }


def resolve_provider_credential(
    provider: str,
    *,
    project_root: str | Path,
    session_value: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> CredentialResolution:
    """Resolve session, process, then project-root ``.env`` credentials."""

    normalized = provider.lower().strip()
    variable = _PROVIDER_VARIABLES.get(normalized)
    if variable is None:
        return CredentialResolution(None, "unavailable", None)
    if isinstance(session_value, str) and session_value.strip():
        return CredentialResolution(session_value.strip(), "session", variable)
    environment = os.environ if environ is None else environ
    process_value = environment.get(variable)
    if isinstance(process_value, str) and process_value.strip():
        return CredentialResolution(process_value.strip(), "process_environment", variable)
    env_value = read_allowlisted_env(Path(project_root) / ".env").get(variable)
    if isinstance(env_value, str) and env_value.strip():
        return CredentialResolution(env_value.strip(), "project_env", variable)
    return CredentialResolution(None, "unavailable", variable)


def read_allowlisted_env(path: str | Path) -> dict[str, str]:
    """Parse only supported credential variables from one local env file.

    This is deliberately not a shell parser: it performs no interpolation,
    command substitution, escape processing, includes, or environment writes.
    """

    env_path = Path(path)
    if not env_path.is_file() or env_path.is_symlink():
        return {}
    try:
        text = env_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return {}
    allowed = set(_PROVIDER_VARIABLES.values())
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        name = name.strip()
        if name not in allowed or _ENV_NAME.fullmatch(name) is None:
            continue
        value = _literal_env_value(raw_value.strip())
        if value:
            values[name] = value
    return values


def _literal_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    # An unquoted comment starts only after whitespace; hashes in API keys stay
    # literal when adjacent to the value.
    for marker in (" #", "\t#"):
        if marker in value:
            value = value.split(marker, 1)[0].rstrip()
    return value
