"""CadFlow-owned tool authority for bounded Agent Episodes.

This module implements local structured-contract validation, pure AST source
policy validation, and the internal attested WSL2 model-program execution
primitive. Execution evidence remains a non-reviewable candidate or diagnostic;
the provider-facing runtime skill and product publication path are not enabled.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import tarfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

from ai_native_cad.agents.model_program_policy import (
    CADQUERY_MODEL_PROGRAM_API,
    MODEL_PROGRAM_SOURCE_POLICY_CODES,
    cadquery_model_program_policy_manifest,
    validate_cadquery_model_program_source,
)
from ai_native_cad.agents.model_program_runtime import (
    MODEL_PROGRAM_LIMITS,
    REQUIRED_MODEL_PROGRAM_CONTROLS,
    ModelProgramExecutionRequest,
    ModelProgramSandboxExecutor,
    SandboxAttestation,
    SandboxExecutionResult,
    ToolInvocationContext,
    WSL_MODEL_PROGRAM_PROFILE,
    canonical_json_bytes,
    sha256_hex,
)


STRUCTURED_CONTRACT_TOOL = "validate_structured_contract"
MODEL_PROGRAM_SOURCE_TOOL = "validate_model_program_source"
MODEL_PROGRAM_TOOL = "execute_model_program"
WINDOWS_MODEL_PROGRAM_PROFILE = WSL_MODEL_PROGRAM_PROFILE


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
    attestation_digest: str | None = None
    profile_digest: str | None = None
    toolchain_digest: str | None = None
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
            if not self.attestation_digest or not self.profile_digest or not self.toolchain_digest:
                raise ValueError("available sandbox capability requires an attestation")
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
            "attestation_digest": self.attestation_digest,
            "profile_digest": self.profile_digest,
            "toolchain_digest": self.toolchain_digest,
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
    execution_id: str | None = None
    attestation_digest: str | None = None
    limits: dict[str, int] | None = None
    exit_state: str | None = None

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
            "execution_id": self.execution_id,
            "attestation_digest": self.attestation_digest,
            "limits": self.limits,
            "exit_state": self.exit_state,
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
            "sandbox_profile_mismatch",
            "sandbox_attestation_failed",
            "sandbox_policy_rejected",
            "sandbox_protocol_error",
            "sandbox_timeout",
            "sandbox_resource_limit",
            "sandbox_violation",
            "model_program_runtime_error",
            "model_program_output_invalid",
            "execution_evidence_conflict",
            "invalid_execution_context",
            "invalid_model_program_request",
            "source_validation_exception",
            "unsupported_model_program_api",
        }
        | MODEL_PROGRAM_SOURCE_POLICY_CODES
    ),
)

MODEL_PROGRAM_SOURCE_DEFINITION = ToolDefinition(
    tool_id=MODEL_PROGRAM_SOURCE_TOOL,
    allowed_skill_ids=frozenset({"model_program"}),
    execution_profile="local_pure_source_validation_v1",
    input_contract="model_program_source_validation_request_v1",
    output_contract="model_program_source_validation_observation_v1",
    filesystem_policy="no_filesystem_access",
    network_policy="no_network_access",
    process_policy="ast_parse_only_no_bytecode_import_or_execution",
    resource_limits=("source_bytes", "ast_nodes"),
    persisted_evidence=(
        "api id",
        "source hash",
        "static policy codes",
        "sanitized source metrics",
    ),
    failure_codes=(
        frozenset(
            {
                "invalid_source_contract",
                "source_validation_exception",
                "unsupported_model_program_api",
            }
        )
        | MODEL_PROGRAM_SOURCE_POLICY_CODES
    ),
)


def detect_model_program_sandbox_capability(
    executor: ModelProgramSandboxExecutor | None = None,
) -> SandboxCapability:
    """Return available only for a live executor carrying a verified attestation."""

    reason_codes: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    if executor is None:
        from ai_native_cad.agents.wsl_sandbox import load_configured_wsl_sandbox_executor

        executor, reason_codes, evidence = load_configured_wsl_sandbox_executor()
    if executor is not None:
        try:
            attestation = executor.attestation
            # Reconstructing the value proves the digest and complete-control
            # invariants rather than trusting a caller-supplied availability bit.
            verified = SandboxAttestation.from_dict(attestation.manifest())
        except (AttributeError, TypeError, ValueError):
            executor = None
            reason_codes = ("sandbox_unavailable", "sandbox_attestation_failed")
            evidence = ()
        else:
            return SandboxCapability(
                profile_id=verified.profile_id,
                platform=verified.platform,
                available=True,
                enforced_controls=verified.enforced_controls,
                missing_controls=frozenset(),
                reason_codes=(),
                evidence=(
                    f"attestation:{verified.digest}",
                    f"profile:{verified.profile_digest}",
                    f"toolchain:{verified.toolchain_digest}",
                ),
                attestation_digest=verified.digest,
                profile_digest=verified.profile_digest,
                toolchain_digest=verified.toolchain_digest,
            )
    return SandboxCapability(
        profile_id=WINDOWS_MODEL_PROGRAM_PROFILE,
        platform="Windows",
        available=False,
        enforced_controls=frozenset(),
        missing_controls=REQUIRED_MODEL_PROGRAM_CONTROLS,
        reason_codes=reason_codes or (
            "sandbox_unavailable",
            "sandbox_runtime_not_enabled",
        ),
        evidence=evidence or (
            "No attested CadFlow WSL2 worker is enabled for this process.",
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
        sandbox_executor: ModelProgramSandboxExecutor | None = None,
    ) -> None:
        self._definitions = MappingProxyType(
            {
                STRUCTURED_CONTRACT_TOOL: STRUCTURED_CONTRACT_DEFINITION,
                MODEL_PROGRAM_SOURCE_TOOL: MODEL_PROGRAM_SOURCE_DEFINITION,
                MODEL_PROGRAM_TOOL: MODEL_PROGRAM_DEFINITION,
            }
        )
        self._structured_contract_validator = (
            structured_contract_validator or _validate_cad_ir_contract
        )
        configured_executor = sandbox_executor
        configured_reasons: tuple[str, ...] = ()
        configured_evidence: tuple[str, ...] = ()
        if configured_executor is None:
            from ai_native_cad.agents.wsl_sandbox import load_configured_wsl_sandbox_executor

            configured_executor, configured_reasons, configured_evidence = (
                load_configured_wsl_sandbox_executor()
            )
        self._sandbox_executor = configured_executor
        if configured_executor is not None:
            detected = detect_model_program_sandbox_capability(configured_executor)
        else:
            detected = SandboxCapability(
                profile_id=WINDOWS_MODEL_PROGRAM_PROFILE,
                platform="Windows",
                available=False,
                enforced_controls=frozenset(),
                missing_controls=REQUIRED_MODEL_PROGRAM_CONTROLS,
                reason_codes=configured_reasons
                or ("sandbox_unavailable", "sandbox_runtime_not_enabled"),
                evidence=configured_evidence
                or ("No attested CadFlow WSL2 worker is enabled for this process.",),
            )
        # Compatibility callers may still inject an unavailable capability for
        # tests.  An injected available capability can never unlock execution.
        if sandbox_capability is not None and not sandbox_capability.available:
            detected = sandbox_capability
        self._sandbox_capability = detected

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
        context: ToolInvocationContext | None = None,
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
            return self._invoke_model_program_executor(definition, payload, context)
        if tool_id == MODEL_PROGRAM_SOURCE_TOOL:
            return self._invoke_model_program_source_validator(definition, payload)
        return self._invoke_structured_contract_validator(definition, payload)

    def _invoke_model_program_source_validator(
        self,
        definition: ToolDefinition,
        payload: dict[str, Any],
    ) -> ToolObservation:
        if (
            set(payload) != {"api_id", "source"}
            or not isinstance(payload.get("api_id"), str)
            or not isinstance(payload.get("source"), str)
        ):
            return _blocked_observation(
                definition.tool_id,
                execution_profile=definition.execution_profile,
                observation_type="source_validation_rejected",
                code="invalid_source_contract",
            )
        if payload.get("api_id") != CADQUERY_MODEL_PROGRAM_API:
            return _blocked_observation(
                definition.tool_id,
                execution_profile=definition.execution_profile,
                observation_type="source_validation_rejected",
                code="unsupported_model_program_api",
                output={
                    "valid": False,
                    "supported_api_ids": [CADQUERY_MODEL_PROGRAM_API],
                    "source_retained": False,
                },
            )
        try:
            result = validate_cadquery_model_program_source(payload["source"])
        except Exception:
            return _blocked_observation(
                definition.tool_id,
                execution_profile=definition.execution_profile,
                observation_type="source_validation_failed",
                code="source_validation_exception",
                output={
                    "valid": False,
                    "source_retained": False,
                },
            )
        success = result["valid"] is True
        return ToolObservation(
            tool_id=definition.tool_id,
            success=success,
            observation_type=(
                "source_validation_passed"
                if success
                else "source_validation_failed"
            ),
            codes=tuple(result["codes"]),
            output={
                **result,
                "policy": cadquery_model_program_policy_manifest(),
                "source_retained": False,
            },
            execution_profile=definition.execution_profile,
            side_effect_started=False,
        )

    def _invoke_model_program_executor(
        self,
        definition: ToolDefinition,
        payload: dict[str, Any],
        context: ToolInvocationContext | None,
    ) -> ToolObservation:
        if self._sandbox_executor is None:
            return _blocked_observation(
                definition.tool_id,
                execution_profile=definition.execution_profile,
                observation_type="sandbox_unavailable",
                code="sandbox_attestation_failed",
            )
        if not isinstance(context, ToolInvocationContext):
            return _blocked_observation(
                definition.tool_id,
                execution_profile=definition.execution_profile,
                observation_type="tool_input_rejected",
                code="invalid_execution_context",
            )
        expected = {
            "api_id",
            "candidate_id",
            "source",
            "parameters",
            "requested_outputs",
        }
        if set(payload) != expected:
            return _execution_rejected(definition, "invalid_model_program_request")
        try:
            request = ModelProgramExecutionRequest(
                api_id=payload["api_id"],
                candidate_id=payload["candidate_id"],
                source=payload["source"],
                parameters=payload["parameters"],
                requested_outputs=tuple(payload["requested_outputs"]),
            )
        except (KeyError, TypeError, ValueError):
            return _execution_rejected(definition, "invalid_model_program_request")
        if request.api_id != CADQUERY_MODEL_PROGRAM_API:
            return _execution_rejected(definition, "unsupported_model_program_api")
        try:
            source_result = validate_cadquery_model_program_source(request.source)
        except Exception:
            return _execution_rejected(definition, "source_validation_exception")
        if source_result.get("valid") is not True:
            return ToolObservation(
                tool_id=definition.tool_id,
                success=False,
                observation_type="sandbox_policy_rejected",
                codes=tuple(source_result.get("codes") or ("sandbox_policy_rejected",)),
                output={
                    "blocked": True,
                    "source_hash": source_result.get("source_hash"),
                    "source_retained": False,
                },
                execution_profile=definition.execution_profile,
                side_effect_started=False,
            )
        try:
            attestation = SandboxAttestation.from_dict(
                self._sandbox_executor.attestation.manifest()
            )
        except (AttributeError, TypeError, ValueError):
            return _execution_rejected(definition, "sandbox_attestation_failed")
        if attestation.digest != self._sandbox_capability.attestation_digest:
            return _execution_rejected(definition, "sandbox_attestation_failed")

        execution_id = f"exec_{uuid.uuid4().hex}"
        final_dir = _execution_evidence_dir(context, request.candidate_id, execution_id)
        if final_dir.exists():
            return _execution_rejected(definition, "execution_evidence_conflict")
        try:
            runtime_result = self._sandbox_executor.execute(request)
        except Exception:
            # The executor boundary is CadFlow-owned, but an adapter failure
            # must still become typed diagnostic evidence. Conservatively mark
            # side effects as started because the exception may have happened
            # after the launcher crossed the isolation boundary.
            runtime_result = SandboxExecutionResult(
                success=False,
                codes=("sandbox_protocol_error",),
                exit_state="executor_exception",
                archive=b"",
            )
        if not isinstance(runtime_result, SandboxExecutionResult):
            runtime_result = SandboxExecutionResult(
                success=False,
                codes=("sandbox_protocol_error",),
                exit_state="invalid_executor_result",
                archive=b"",
            )
        if not runtime_result.archive:
            code = runtime_result.codes[0] if runtime_result.codes else "sandbox_protocol_error"
            try:
                evidence = _persist_execution_evidence(
                    final_dir=final_dir,
                    context=context,
                    request=request,
                    execution_id=execution_id,
                    attestation=attestation,
                    worker_observation={
                        "schema_version": 1,
                        "success": False,
                        "observation_type": "model_program_execution_failed",
                        "codes": [code],
                        "exit_state": runtime_result.exit_state,
                    },
                    archive_files={},
                    launcher_stderr=runtime_result.stderr,
                )
            except (OSError, ValueError):
                evidence = {
                    "candidate_id": request.candidate_id,
                    "source_hash": source_result.get("source_hash"),
                    "parameters_hash": sha256_hex(canonical_json_bytes(request.parameters)),
                    "evidence_persisted": False,
                    "reviewable": False,
                    "accepted": False,
                    "deliverable": False,
                }
            return ToolObservation(
                tool_id=definition.tool_id,
                success=False,
                observation_type="model_program_execution_failed",
                codes=(code,),
                output=evidence,
                execution_profile=definition.execution_profile,
                side_effect_started=True,
                execution_id=execution_id,
                attestation_digest=attestation.digest,
                limits=dict(MODEL_PROGRAM_LIMITS),
                exit_state=runtime_result.exit_state,
            )
        try:
            files, worker_observation = _validate_worker_archive(runtime_result.archive)
            evidence = _persist_execution_evidence(
                final_dir=final_dir,
                context=context,
                request=request,
                execution_id=execution_id,
                attestation=attestation,
                worker_observation=worker_observation,
                archive_files=files,
                launcher_stderr=runtime_result.stderr,
            )
        except (OSError, ValueError, json.JSONDecodeError, tarfile.TarError):
            try:
                evidence = _persist_execution_evidence(
                    final_dir=final_dir,
                    context=context,
                    request=request,
                    execution_id=execution_id,
                    attestation=attestation,
                    worker_observation={
                        "schema_version": 1,
                        "success": False,
                        "observation_type": "sandbox_protocol_error",
                        "codes": ["sandbox_protocol_error"],
                        "exit_state": "invalid_archive",
                    },
                    archive_files={},
                    launcher_stderr=runtime_result.stderr,
                )
            except (OSError, ValueError):
                evidence = {
                    "candidate_id": request.candidate_id,
                    "source_hash": source_result.get("source_hash"),
                    "evidence_persisted": False,
                    "reviewable": False,
                    "accepted": False,
                    "deliverable": False,
                }
            return ToolObservation(
                tool_id=definition.tool_id,
                success=False,
                observation_type="sandbox_protocol_error",
                codes=("sandbox_protocol_error",),
                output=evidence,
                execution_profile=definition.execution_profile,
                side_effect_started=True,
                execution_id=execution_id,
                attestation_digest=attestation.digest,
                limits=dict(MODEL_PROGRAM_LIMITS),
                exit_state="invalid_archive",
            )
        success = worker_observation.get("success") is True
        codes = tuple(worker_observation.get("codes") or ())
        if not success and not codes:
            codes = ("model_program_runtime_error",)
        return ToolObservation(
            tool_id=definition.tool_id,
            success=success,
            observation_type=str(
                worker_observation.get("observation_type")
                or ("model_program_execution_completed" if success else "model_program_execution_failed")
            ),
            codes=codes,
            output=evidence,
            execution_profile=definition.execution_profile,
            side_effect_started=True,
            execution_id=execution_id,
            attestation_digest=attestation.digest,
            limits=dict(MODEL_PROGRAM_LIMITS),
            exit_state=str(worker_observation.get("exit_state") or runtime_result.exit_state),
        )

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


def _execution_evidence_dir(
    context: ToolInvocationContext,
    candidate_id: str,
    execution_id: str,
) -> Path:
    root = Path(context.evidence_root).resolve()
    candidate_root = (root / "candidates" / candidate_id).resolve()
    try:
        candidate_root.relative_to(root)
    except ValueError as exc:
        raise ValueError("candidate evidence escaped the trusted root") from exc
    return candidate_root / execution_id


def _validate_worker_archive(
    archive_bytes: bytes,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    if len(archive_bytes) > MODEL_PROGRAM_LIMITS["output_bytes"] + 1_048_576:
        raise ValueError("worker archive exceeds the output limit")
    allowed = {"observation.json", "stdout.txt", "stderr.txt", "model.step"}
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        for member in archive.getmembers():
            if member.name not in allowed or member.name in files:
                raise ValueError("worker archive contains an unexpected file")
            if not member.isfile() or member.issym() or member.islnk():
                raise ValueError("worker archive contains a non-regular file")
            if member.size < 0 or member.size > MODEL_PROGRAM_LIMITS["output_bytes"]:
                raise ValueError("worker archive member exceeds the size limit")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError("worker archive member is unreadable")
            value = handle.read(member.size + 1)
            if len(value) != member.size:
                raise ValueError("worker archive member size mismatch")
            files[member.name] = value
    if "observation.json" not in files:
        raise ValueError("worker archive has no observation")
    observation = json.loads(files["observation.json"].decode("utf-8"))
    if not isinstance(observation, dict) or observation.get("schema_version") != 1:
        raise ValueError("worker observation is invalid")
    if not isinstance(observation.get("success"), bool):
        raise ValueError("worker observation has no success state")
    if observation["success"]:
        step = files.get("model.step")
        if not step or len(step) > MODEL_PROGRAM_LIMITS["output_bytes"]:
            raise ValueError("successful worker archive has no valid STEP")
    elif "model.step" in files:
        raise ValueError("failed worker archive contains a product-looking output")
    if len(files.get("stdout.txt", b"")) > MODEL_PROGRAM_LIMITS["stdout_bytes"]:
        raise ValueError("worker stdout exceeds the limit")
    if len(files.get("stderr.txt", b"")) > MODEL_PROGRAM_LIMITS["stderr_bytes"]:
        raise ValueError("worker stderr exceeds the limit")
    return files, observation


def _persist_execution_evidence(
    *,
    final_dir: Path,
    context: ToolInvocationContext,
    request: ModelProgramExecutionRequest,
    execution_id: str,
    attestation: SandboxAttestation,
    worker_observation: dict[str, Any],
    archive_files: dict[str, bytes],
    launcher_stderr: str,
) -> dict[str, Any]:
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = final_dir.parent / f".{execution_id}.staging"
    if staging.exists() or final_dir.exists():
        raise ValueError("execution evidence already exists")
    staging.mkdir()
    try:
        source_hash = sha256_hex(request.source.encode("utf-8"))
        parameters_bytes = canonical_json_bytes(request.parameters)
        _write_exclusive(staging / "source.py", request.source.encode("utf-8"))
        _write_exclusive(staging / "parameters.json", parameters_bytes + b"\n")
        sanitized_worker = _sanitize_observation(worker_observation)
        _write_exclusive(
            staging / "observation.json",
            json.dumps(sanitized_worker, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        )
        output_entries: list[dict[str, Any]] = []
        for name in ("stdout.txt", "stderr.txt", "model.step"):
            value = archive_files.get(name)
            if value is None:
                continue
            if name.endswith(".txt"):
                value = _sanitize_text(value.decode("utf-8", errors="replace")).encode("utf-8")
            _write_exclusive(staging / name, value)
            output_entries.append(
                {
                    "name": name,
                    "sha256": sha256_hex(value),
                    "size": len(value),
                }
            )
        if launcher_stderr:
            value = _sanitize_text(launcher_stderr)[: MODEL_PROGRAM_LIMITS["stderr_bytes"]].encode("utf-8")
            _write_exclusive(staging / "launcher_stderr.txt", value)
            output_entries.append(
                {
                    "name": "launcher_stderr.txt",
                    "sha256": sha256_hex(value),
                    "size": len(value),
                }
            )
        relative_root = Path("candidates") / request.candidate_id / execution_id
        evidence_manifest = {
            "schema_version": 1,
            "owner": "cadflow_tool_broker",
            "trust_role": "candidate" if worker_observation.get("success") is True else "diagnostic",
            "reviewable": False,
            "accepted": False,
            "deliverable": False,
            "work_id": context.work_id,
            "run_id": context.run_id,
            "part_job_id": context.part_job_id,
            "episode_id": context.episode_id,
            "candidate_id": request.candidate_id,
            "execution_id": execution_id,
            "api_id": request.api_id,
            "source_hash": source_hash,
            "parameters_hash": sha256_hex(parameters_bytes),
            "attestation_digest": attestation.digest,
            "profile_digest": attestation.profile_digest,
            "toolchain_digest": attestation.toolchain_digest,
            "limits": dict(MODEL_PROGRAM_LIMITS),
            "worker_observation": sanitized_worker,
            "files": output_entries,
        }
        _write_exclusive(
            staging / "evidence_manifest.json",
            json.dumps(evidence_manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        )
        staging.rename(final_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {
        "candidate_id": request.candidate_id,
        "execution_id": execution_id,
        "source_hash": source_hash,
        "parameters_hash": sha256_hex(parameters_bytes),
        "profile_digest": attestation.profile_digest,
        "toolchain_digest": attestation.toolchain_digest,
        "geometry": _sanitize_observation(worker_observation).get("geometry", {}),
        "evidence_manifest": str(relative_root / "evidence_manifest.json").replace("\\", "/"),
        "outputs": [
            {
                **item,
                "relative_path": str(relative_root / item["name"]).replace("\\", "/"),
            }
            for item in output_entries
            if item["name"] == "model.step"
        ],
        "reviewable": False,
        "accepted": False,
        "deliverable": False,
    }


def _sanitize_observation(value: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return json.loads(_sanitize_text(encoded))


def _sanitize_text(value: str) -> str:
    sanitized = re.sub(r"(?i)[A-Z]:\\[^\s\"']+", "<redacted-windows-path>", value)
    sanitized = re.sub(r"/(?:mnt|home|root|run|var|tmp)/[^\s\"']+", "<redacted-local-path>", sanitized)
    return sanitized


def _write_exclusive(path: Path, value: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(value)


def _execution_rejected(definition: ToolDefinition, code: str) -> ToolObservation:
    return ToolObservation(
        tool_id=definition.tool_id,
        success=False,
        observation_type="tool_input_rejected",
        codes=(code,),
        output={"blocked": True, "code": code},
        execution_profile=definition.execution_profile,
        side_effect_started=False,
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
    "MODEL_PROGRAM_SOURCE_TOOL",
    "MODEL_PROGRAM_SOURCE_DEFINITION",
    "REQUIRED_MODEL_PROGRAM_CONTROLS",
    "ModelProgramExecutionRequest",
    "SandboxAttestation",
    "STRUCTURED_CONTRACT_TOOL",
    "STRUCTURED_CONTRACT_DEFINITION",
    "SandboxCapability",
    "ToolDefinition",
    "ToolObservation",
    "ToolInvocationContext",
    "WINDOWS_MODEL_PROGRAM_PROFILE",
    "detect_model_program_sandbox_capability",
]
