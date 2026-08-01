"""CadFlow-owned tool authority for bounded Agent Episodes.

This module intentionally implements only the local structured-contract
validation tool.  The model-program tool is represented so its execution
profile can be inspected, but it fails closed before any source is written or
process is started because this repository has no enforceable Windows sandbox.
"""

from __future__ import annotations

import platform
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, Callable


STRUCTURED_CONTRACT_TOOL = "validate_structured_contract"
MODEL_PROGRAM_TOOL = "execute_model_program"
WINDOWS_MODEL_PROGRAM_PROFILE = "windows_model_program_v0"

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


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    allowed_skill_ids: frozenset[str]
    execution_profile: str
    input_contract: str
    output_contract: str
    filesystem_policy: str
    network_policy: str
    process_policy: str
    resource_limits: tuple[str, ...]
    persisted_evidence: tuple[str, ...]
    failure_codes: frozenset[str]

    def manifest(self) -> dict[str, Any]:
        value = asdict(self)
        value["allowed_skill_ids"] = sorted(self.allowed_skill_ids)
        value["failure_codes"] = sorted(self.failure_codes)
        return value


@dataclass(frozen=True)
class SandboxCapability:
    profile_id: str
    platform: str
    available: bool
    enforced_controls: frozenset[str]
    missing_controls: frozenset[str]
    reason_codes: tuple[str, ...]
    evidence: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        expected_missing = REQUIRED_MODEL_PROGRAM_CONTROLS - self.enforced_controls
        if self.missing_controls != expected_missing:
            raise ValueError(
                "sandbox missing controls must match the required control set"
            )
        if self.available:
            if not self.evidence:
                raise ValueError("available sandbox capability requires enforcement evidence")
        elif not self.reason_codes:
            raise ValueError("unavailable sandbox capability requires a typed reason")

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "platform": self.platform,
            "available": self.available,
            "enforced_controls": sorted(self.enforced_controls),
            "missing_controls": sorted(self.missing_controls),
            "reason_codes": list(self.reason_codes),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ToolObservation:
    tool_id: str
    success: bool
    observation_type: str
    codes: tuple[str, ...]
    output: dict[str, Any]
    execution_profile: str
    side_effect_started: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "owner": "cadflow_tool_broker",
            "tool_id": self.tool_id,
            "success": self.success,
            "observation_type": self.observation_type,
            "codes": list(self.codes),
            "execution_profile": self.execution_profile,
            "side_effect_started": self.side_effect_started,
            "output": self.output,
        }


STRUCTURED_CONTRACT_DEFINITION = ToolDefinition(
    tool_id=STRUCTURED_CONTRACT_TOOL,
    allowed_skill_ids=frozenset({"design_part", "legacy_create_part_ir"}),
    execution_profile="local_pure_validation_v1",
    input_contract="structured_contract_validation_request_v1",
    output_contract="structured_contract_validation_observation_v1",
    filesystem_policy="no_filesystem_access",
    network_policy="no_network_access",
    process_policy="in_process_local_validator_only",
    resource_limits=("episode_wall_clock_budget",),
    persisted_evidence=("tool id", "validation codes", "sanitized validator output"),
    failure_codes=frozenset(
        {
            "forbidden_execution_field",
            "invalid_contract_shape",
            "unsupported_contract_type",
            "validation_exception",
        }
    ),
)

MODEL_PROGRAM_DEFINITION = ToolDefinition(
    tool_id=MODEL_PROGRAM_TOOL,
    allowed_skill_ids=frozenset({"model_program"}),
    execution_profile=WINDOWS_MODEL_PROGRAM_PROFILE,
    input_contract="model_program_execution_request_v1",
    output_contract="model_program_execution_observation_v1",
    filesystem_policy="dedicated_candidate_directory_only",
    network_policy="network_disabled",
    process_policy="isolated_worker_without_child_process_authority",
    resource_limits=(
        "cpu",
        "memory",
        "wall_clock",
        "process_count",
        "output_size",
    ),
    persisted_evidence=(
        "source hash",
        "parameters",
        "sanitized stdout and stderr",
        "exit state",
        "allowlisted outputs",
    ),
    failure_codes=frozenset(
        {
            "sandbox_unavailable",
            "sandbox_policy_rejected",
            "tool_not_implemented",
        }
    ),
)


def detect_model_program_sandbox_capability() -> SandboxCapability:
    """Report the real current capability; never infer safety from a subprocess.

    The existing deterministic CadQuery executor inherits the host environment
    and uses the host Python process boundary.  It is intentionally not probed
    or promoted here because those mechanics do not enforce the required
    provider-source isolation controls.
    """

    platform_name = platform.system() or "Unknown"
    platform_code = platform_name.lower().replace(" ", "_")
    return SandboxCapability(
        profile_id=WINDOWS_MODEL_PROGRAM_PROFILE,
        platform=platform_name,
        available=False,
        enforced_controls=frozenset(),
        missing_controls=REQUIRED_MODEL_PROGRAM_CONTROLS,
        reason_codes=(
            "sandbox_unavailable",
            f"{platform_code}_enforceable_profile_not_implemented",
        ),
        evidence=(
            "No CadFlow worker currently proves the required OS-enforced isolation controls.",
            "The deterministic CadQuery host subprocess is excluded from this capability gate.",
        ),
    )


class CadFlowToolBroker:
    """Authorize and invoke every tool exposed to the active Agent skill."""

    def __init__(
        self,
        *,
        structured_contract_validator: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        sandbox_capability: SandboxCapability | None = None,
    ) -> None:
        self._definitions = MappingProxyType(
            {
                STRUCTURED_CONTRACT_TOOL: STRUCTURED_CONTRACT_DEFINITION,
                MODEL_PROGRAM_TOOL: MODEL_PROGRAM_DEFINITION,
            }
        )
        self._structured_contract_validator = (
            structured_contract_validator or _validate_cad_ir_contract
        )
        self._sandbox_capability = (
            sandbox_capability or detect_model_program_sandbox_capability()
        )

    def definition(self, tool_id: str) -> ToolDefinition:
        try:
            return self._definitions[tool_id]
        except KeyError as exc:
            raise ValueError(f"unknown CadFlow tool: {tool_id}") from exc

    def capability(self, tool_id: str) -> dict[str, Any]:
        definition = self.definition(tool_id)
        if tool_id == MODEL_PROGRAM_TOOL:
            return {
                "tool": definition.manifest(),
                "capability": self._sandbox_capability.manifest(),
            }
        return {
            "tool": definition.manifest(),
            "capability": {
                "schema_version": 1,
                "available": True,
                "profile_id": definition.execution_profile,
            },
        }

    def manifest(self, *, active_skill_id: str) -> dict[str, Any]:
        allowed = [
            definition.manifest()
            for definition in self._definitions.values()
            if active_skill_id in definition.allowed_skill_ids
        ]
        return {
            "schema_version": 1,
            "broker": "cadflow_tool_broker",
            "active_skill_id": active_skill_id,
            "allowed_tools": allowed,
            "model_program_capability": self._sandbox_capability.manifest(),
        }

    def invoke(
        self,
        tool_id: str,
        *,
        skill_id: str,
        payload: dict[str, Any],
    ) -> ToolObservation:
        try:
            definition = self.definition(tool_id)
        except ValueError:
            return _blocked_observation(
                tool_id,
                execution_profile="none",
                observation_type="policy_blocked",
                code="tool_not_registered",
            )
        if skill_id not in definition.allowed_skill_ids:
            return _blocked_observation(
                tool_id,
                execution_profile=definition.execution_profile,
                observation_type="policy_blocked",
                code="tool_not_allowed_for_skill",
            )
        if not isinstance(payload, dict):
            return _blocked_observation(
                tool_id,
                execution_profile=definition.execution_profile,
                observation_type="tool_input_rejected",
                code="tool_input_invalid",
            )
        if tool_id == MODEL_PROGRAM_TOOL:
            if not self._sandbox_capability.available:
                return _blocked_observation(
                    tool_id,
                    execution_profile=definition.execution_profile,
                    observation_type="sandbox_unavailable",
                    code="sandbox_unavailable",
                    output={
                        "capability": self._sandbox_capability.manifest(),
                        "recovery_action": (
                            "Install and verify an OS-enforced CadFlow sandbox profile "
                            "before enabling model-program execution."
                        ),
                    },
                )
            return _blocked_observation(
                tool_id,
                execution_profile=definition.execution_profile,
                observation_type="unsupported_capability",
                code="tool_not_implemented",
            )
        return self._invoke_structured_contract_validator(definition, payload)

    def _invoke_structured_contract_validator(
        self,
        definition: ToolDefinition,
        payload: dict[str, Any],
    ) -> ToolObservation:
        if set(payload) != {"contract_type", "contract"}:
            return _validation_rejected(
                definition,
                "invalid_contract_shape",
            )
        if payload.get("contract_type") != "cad_ir_draft":
            return _validation_rejected(
                definition,
                "unsupported_contract_type",
            )
        contract = payload.get("contract")
        if not isinstance(contract, dict):
            return _validation_rejected(
                definition,
                "invalid_contract_shape",
            )
        forbidden = _find_forbidden_execution_field(contract)
        if forbidden is not None:
            return _validation_rejected(
                definition,
                "forbidden_execution_field",
            )
        try:
            feedback = self._structured_contract_validator(contract)
        except Exception:
            feedback = {
                "valid": False,
                "errors": [{"code": "validation_exception"}],
                "warnings": [],
                "checks": [],
            }
        if not isinstance(feedback, dict) or not isinstance(feedback.get("valid"), bool):
            feedback = {
                "valid": False,
                "errors": [{"code": "validation_exception"}],
                "warnings": [],
                "checks": [],
            }
        codes = _feedback_codes(feedback)
        success = feedback["valid"]
        return ToolObservation(
            tool_id=definition.tool_id,
            success=success,
            observation_type=(
                "contract_validation_passed"
                if success
                else "contract_validation_failed"
            ),
            codes=codes,
            output=feedback,
            execution_profile=definition.execution_profile,
        )


def _validate_cad_ir_contract(contract: dict[str, Any]) -> dict[str, Any]:
    from ai_native_cad.agents.validation import validate_input_ir_draft
    from ai_native_cad.cad_ir.validator import validate_ir

    feedback = validate_ir(contract)
    if not feedback["valid"]:
        return feedback
    validate_input_ir_draft(contract)
    return feedback


def _find_forbidden_execution_field(value: Any, path: str = "") -> str | None:
    from ai_native_cad.agents.validation import FORBIDDEN_BYPASS_KEYS

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key).lower() in FORBIDDEN_BYPASS_KEYS:
                return child_path
            found = _find_forbidden_execution_field(child, child_path)
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_forbidden_execution_field(child, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _feedback_codes(feedback: dict[str, Any]) -> tuple[str, ...]:
    errors = feedback.get("errors")
    if not isinstance(errors, list):
        return ()
    return tuple(
        item["code"]
        for item in errors
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    )


def _validation_rejected(
    definition: ToolDefinition,
    code: str,
) -> ToolObservation:
    feedback = {
        "valid": False,
        "errors": [{"code": code}],
        "warnings": [],
        "checks": [],
    }
    return ToolObservation(
        tool_id=definition.tool_id,
        success=False,
        observation_type="contract_validation_failed",
        codes=(code,),
        output=feedback,
        execution_profile=definition.execution_profile,
    )


def _blocked_observation(
    tool_id: str,
    *,
    execution_profile: str,
    observation_type: str,
    code: str,
    output: dict[str, Any] | None = None,
) -> ToolObservation:
    return ToolObservation(
        tool_id=tool_id,
        success=False,
        observation_type=observation_type,
        codes=(code,),
        output=output or {"blocked": True, "code": code},
        execution_profile=execution_profile,
        side_effect_started=False,
    )


__all__ = [
    "CadFlowToolBroker",
    "MODEL_PROGRAM_TOOL",
    "MODEL_PROGRAM_DEFINITION",
    "REQUIRED_MODEL_PROGRAM_CONTROLS",
    "STRUCTURED_CONTRACT_TOOL",
    "STRUCTURED_CONTRACT_DEFINITION",
    "SandboxCapability",
    "ToolDefinition",
    "ToolObservation",
    "WINDOWS_MODEL_PROGRAM_PROFILE",
    "detect_model_program_sandbox_capability",
]
