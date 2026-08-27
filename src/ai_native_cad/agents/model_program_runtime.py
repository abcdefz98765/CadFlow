"""CadFlow-owned contracts for attested model-program execution.

The provider never constructs these runtime objects.  CadFlow validates the
provider payload, supplies lineage/evidence context, and requires an attested
sandbox executor before any model-program side effect can start.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


WSL_MODEL_PROGRAM_PROFILE = "wsl2_cadquery_v1"
WSL_MODEL_PROGRAM_DISTRO = "CadFlow-Sandbox-CQ-v1"

REQUIRED_MODEL_PROGRAM_CONTROLS = frozenset(
    {
        "dedicated_writable_candidate_directory",
        "read_only_declared_inputs",
        "environment_allowlist",
        "filesystem_boundary_enforced",
        "network_disabled",
        "subprocess_and_shell_blocked",
        "dynamic_dependency_installation_blocked",
        "cpu_limit",
        "memory_limit",
        "wall_clock_limit",
        "process_count_limit",
        "output_size_limit",
        "generated_file_allowlist",
    }
)

MODEL_PROGRAM_LIMITS = {
    "source_bytes": 65_536,
    "parameter_bytes": 16_384,
    "parameter_depth": 8,
    "wall_clock_seconds": 30,
    "cpu_seconds": 20,
    "memory_bytes": 1_073_741_824,
    "swap_bytes": 0,
    "task_count": 64,
    "output_bytes": 67_108_864,
    "stdout_bytes": 262_144,
    "stderr_bytes": 262_144,
}
MODEL_PROGRAM_PARAMETER_KEY_MAX_LENGTH = 64
MODEL_PROGRAM_REQUESTED_OUTPUTS = ("step",)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class ModelProgramExecutionRequest:
    api_id: str
    candidate_id: str
    source: str
    parameters: dict[str, Any]
    requested_outputs: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported model-program execution request schema")
        if not _SAFE_ID.fullmatch(self.candidate_id):
            raise ValueError("candidate_id must be a path-safe identifier")
        if self.requested_outputs != MODEL_PROGRAM_REQUESTED_OUTPUTS:
            raise ValueError("model-program execution supports exactly one STEP output")
        validate_model_program_parameters(self.parameters)

    def worker_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": "execute",
            "api_id": self.api_id,
            "candidate_id": self.candidate_id,
            "source": self.source,
            "parameters": self.parameters,
            "requested_outputs": list(self.requested_outputs),
        }


@dataclass(frozen=True)
class ToolInvocationContext:
    """Trusted Run context supplied by CadFlow, never by the provider payload."""

    work_id: str
    run_id: str
    part_job_id: str
    episode_id: str
    evidence_root: Path

    def __post_init__(self) -> None:
        for name, value in (
            ("work_id", self.work_id),
            ("run_id", self.run_id),
            ("part_job_id", self.part_job_id),
            ("episode_id", self.episode_id),
        ):
            if not _SAFE_ID.fullmatch(value):
                raise ValueError(f"{name} must be a path-safe identifier")
        root = Path(self.evidence_root)
        if not root.is_absolute():
            raise ValueError("evidence_root must be an absolute CadFlow-owned path")


@dataclass(frozen=True)
class SandboxAttestation:
    profile_id: str
    platform: str
    distro_id: str
    profile_digest: str
    toolchain_digest: str
    enforced_controls: frozenset[str]
    probe_results: tuple[tuple[str, bool], ...]
    issued_at: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported sandbox attestation schema")
        if self.profile_id != WSL_MODEL_PROGRAM_PROFILE:
            raise ValueError("sandbox attestation profile mismatch")
        if self.distro_id != WSL_MODEL_PROGRAM_DISTRO:
            raise ValueError("sandbox attestation distro mismatch")
        if self.enforced_controls != REQUIRED_MODEL_PROGRAM_CONTROLS:
            raise ValueError("sandbox attestation does not prove every required control")
        if not self.profile_digest or not self.toolchain_digest:
            raise ValueError("sandbox attestation requires profile and toolchain digests")
        if not self.probe_results or not all(result for _, result in self.probe_results):
            raise ValueError("sandbox attestation contains a failed probe")

    @property
    def digest(self) -> str:
        return sha256_hex(canonical_json_bytes(self._unsigned_manifest()))

    def _unsigned_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "platform": self.platform,
            "distro_id": self.distro_id,
            "profile_digest": self.profile_digest,
            "toolchain_digest": self.toolchain_digest,
            "enforced_controls": sorted(self.enforced_controls),
            "probe_results": {key: value for key, value in self.probe_results},
            "issued_at": self.issued_at,
        }

    def manifest(self) -> dict[str, Any]:
        return {**self._unsigned_manifest(), "attestation_digest": self.digest}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SandboxAttestation":
        probes = value.get("probe_results")
        if not isinstance(probes, dict):
            raise ValueError("sandbox attestation probe_results must be an object")
        attestation = cls(
            schema_version=value.get("schema_version", 0),
            profile_id=value.get("profile_id", ""),
            platform=value.get("platform", ""),
            distro_id=value.get("distro_id", ""),
            profile_digest=value.get("profile_digest", ""),
            toolchain_digest=value.get("toolchain_digest", ""),
            enforced_controls=frozenset(value.get("enforced_controls") or ()),
            probe_results=tuple(sorted((str(key), result is True) for key, result in probes.items())),
            issued_at=value.get("issued_at", ""),
        )
        claimed = value.get("attestation_digest")
        if claimed is not None and claimed != attestation.digest:
            raise ValueError("sandbox attestation digest mismatch")
        return attestation


@dataclass(frozen=True)
class SandboxExecutionResult:
    success: bool
    codes: tuple[str, ...]
    exit_state: str
    archive: bytes
    stderr: str = ""


class ModelProgramSandboxExecutor(Protocol):
    @property
    def attestation(self) -> SandboxAttestation: ...

    def execute(self, request: ModelProgramExecutionRequest) -> SandboxExecutionResult: ...


def validate_model_program_parameters(parameters: Any) -> None:
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be a JSON object")
    try:
        encoded = canonical_json_bytes(parameters)
    except (TypeError, ValueError) as exc:
        raise ValueError("parameters must contain finite JSON values") from exc
    if len(encoded) > MODEL_PROGRAM_LIMITS["parameter_bytes"]:
        raise ValueError("parameters exceed the byte limit")
    _validate_parameter_node(parameters, depth=1)


def _validate_parameter_node(value: Any, *, depth: int) -> None:
    if depth > MODEL_PROGRAM_LIMITS["parameter_depth"]:
        raise ValueError("parameters exceed the nesting-depth limit")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("parameters must contain finite numbers")
        return
    if isinstance(value, list):
        for child in value:
            _validate_parameter_node(child, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if (
                not isinstance(key, str)
                or not key
                or len(key) > MODEL_PROGRAM_PARAMETER_KEY_MAX_LENGTH
            ):
                raise ValueError(
                    "parameter keys must be non-empty strings up to "
                    f"{MODEL_PROGRAM_PARAMETER_KEY_MAX_LENGTH} characters"
                )
            _validate_parameter_node(child, depth=depth + 1)
        return
    raise ValueError("parameters contain a non-JSON value")


__all__ = [
    "MODEL_PROGRAM_LIMITS",
    "MODEL_PROGRAM_PARAMETER_KEY_MAX_LENGTH",
    "MODEL_PROGRAM_REQUESTED_OUTPUTS",
    "REQUIRED_MODEL_PROGRAM_CONTROLS",
    "ModelProgramExecutionRequest",
    "ModelProgramSandboxExecutor",
    "SandboxAttestation",
    "SandboxExecutionResult",
    "ToolInvocationContext",
    "WSL_MODEL_PROGRAM_DISTRO",
    "WSL_MODEL_PROGRAM_PROFILE",
    "canonical_json_bytes",
    "sha256_hex",
    "validate_model_program_parameters",
]
