"""Windows host adapter for the dedicated CadFlow WSL2 sandbox distro."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from ai_native_cad.agents.model_program_runtime import (
    MODEL_PROGRAM_LIMITS,
    ModelProgramExecutionRequest,
    SandboxAttestation,
    SandboxExecutionResult,
    WSL_MODEL_PROGRAM_DISTRO,
    WSL_MODEL_PROGRAM_PROFILE,
    canonical_json_bytes,
    sha256_hex,
)


SANDBOX_ENABLE_ENV = "CADFLOW_MODEL_PROGRAM_SANDBOX"
SANDBOX_MANIFEST_ENV = "CADFLOW_MODEL_PROGRAM_SANDBOX_MANIFEST"
_PROBE_PATH = "/opt/cadflow/bin/cadflow-sandbox-probe"
_LAUNCH_PATH = "/opt/cadflow/bin/cadflow-sandbox-launch"
_WSL_EXE = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wsl.exe"


class WslSandboxError(RuntimeError):
    pass


class WslSandboxExecutor:
    def __init__(
        self,
        *,
        manifest: dict[str, Any],
        manifest_path: Path,
        attestation: SandboxAttestation,
    ) -> None:
        self._manifest = manifest
        self._manifest_path = manifest_path
        self._attestation = attestation

    @property
    def attestation(self) -> SandboxAttestation:
        return self._attestation

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    def execute(self, request: ModelProgramExecutionRequest) -> SandboxExecutionResult:
        command = [
            str(_WSL_EXE),
            "--distribution",
            WSL_MODEL_PROGRAM_DISTRO,
            "--user",
            "root",
            "--exec",
            _LAUNCH_PATH,
        ]
        try:
            completed = subprocess.run(
                command,
                input=canonical_json_bytes(request.worker_payload()),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=MODEL_PROGRAM_LIMITS["wall_clock_seconds"] + 5,
                check=False,
                env=_minimal_windows_environment(),
            )
        except subprocess.TimeoutExpired:
            return SandboxExecutionResult(
                success=False,
                codes=("sandbox_timeout",),
                exit_state="timeout",
                archive=b"",
            )
        except OSError:
            return SandboxExecutionResult(
                success=False,
                codes=("sandbox_protocol_error",),
                exit_state="launcher_error",
                archive=b"",
            )
        stderr = _decode_capped(completed.stderr, MODEL_PROGRAM_LIMITS["stderr_bytes"])
        if len(completed.stdout) > MODEL_PROGRAM_LIMITS["output_bytes"] + 1_048_576:
            return SandboxExecutionResult(
                success=False,
                codes=("sandbox_resource_limit",),
                exit_state="output_limit",
                archive=b"",
                stderr=stderr,
            )
        if completed.returncode != 0 or not completed.stdout:
            code, exit_state = _classify_launcher_failure(
                completed.returncode,
                stderr,
            )
            return SandboxExecutionResult(
                success=False,
                codes=(code,),
                exit_state=exit_state,
                archive=b"",
                stderr=stderr,
            )
        return SandboxExecutionResult(
            success=True,
            codes=(),
            exit_state="archive_returned",
            archive=completed.stdout,
            stderr=stderr,
        )


def load_configured_wsl_sandbox_executor(
    *,
    manifest_path: Path | None = None,
) -> tuple[WslSandboxExecutor | None, tuple[str, ...], tuple[str, ...]]:
    """Probe the sealed runtime only after explicit local enablement."""

    if platform.system() != "Windows":
        return None, ("sandbox_unavailable", "windows_host_required"), ()
    if os.environ.get(SANDBOX_ENABLE_ENV, "").strip().lower() not in {
        "1",
        "true",
        "enabled",
    }:
        return (
            None,
            ("sandbox_unavailable", "sandbox_runtime_not_enabled"),
            (f"Set {SANDBOX_ENABLE_ENV}=1 only after provisioning and acceptance.",),
        )
    path = manifest_path or _configured_manifest_path()
    try:
        manifest = _load_runtime_manifest(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None, ("sandbox_unavailable", "sandbox_profile_mismatch"), ()
    if not _WSL_EXE.is_file():
        return None, ("sandbox_unavailable", "wsl_not_installed"), ()
    command = [
        str(_WSL_EXE),
        "--distribution",
        WSL_MODEL_PROGRAM_DISTRO,
        "--user",
        "root",
        "--exec",
        _PROBE_PATH,
        "--json",
    ]
    try:
        completed = subprocess.run(
            command,
            input=canonical_json_bytes(
                {
                    "schema_version": 1,
                    "profile_digest": manifest["profile_digest"],
                    "toolchain_digest": manifest["toolchain_digest"],
                }
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
            env=_minimal_windows_environment(),
        )
        if completed.returncode != 0:
            raise WslSandboxError("sandbox probe returned non-zero")
        value = json.loads(completed.stdout.decode("utf-8"))
        if not isinstance(value, dict):
            raise WslSandboxError("sandbox probe did not return an object")
        attestation = SandboxAttestation.from_dict(value)
        if attestation.profile_digest != manifest["profile_digest"]:
            raise WslSandboxError("profile digest mismatch")
        if attestation.toolchain_digest != manifest["toolchain_digest"]:
            raise WslSandboxError("toolchain digest mismatch")
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired, WslSandboxError):
        return None, ("sandbox_unavailable", "sandbox_attestation_failed"), ()
    return (
        WslSandboxExecutor(
            manifest=manifest,
            manifest_path=path,
            attestation=attestation,
        ),
        (),
        (
            f"attestation:{attestation.digest}",
            f"profile:{attestation.profile_digest}",
            f"toolchain:{attestation.toolchain_digest}",
        ),
    )


def _configured_manifest_path() -> Path:
    override = os.environ.get(SANDBOX_MANIFEST_ENV)
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[3] / "sandbox" / "wsl2" / "runtime_manifest.json"


def _load_runtime_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runtime manifest must be an object")
    required = {
        "schema_version",
        "profile_id",
        "distro_id",
        "profile_digest",
        "toolchain_digest",
        "toolchain",
        "limits",
        "required_controls",
    }
    if set(value) < required:
        raise ValueError("runtime manifest is incomplete")
    if value["schema_version"] != 1:
        raise ValueError("unsupported runtime manifest schema")
    if value["profile_id"] != WSL_MODEL_PROGRAM_PROFILE:
        raise ValueError("runtime profile id mismatch")
    if value["distro_id"] != WSL_MODEL_PROGRAM_DISTRO:
        raise ValueError("runtime distro id mismatch")
    if sha256_hex(canonical_json_bytes(value["toolchain"])) != value["toolchain_digest"]:
        raise ValueError("runtime toolchain digest mismatch")
    unsigned = {key: item for key, item in value.items() if key != "profile_digest"}
    if sha256_hex(canonical_json_bytes(unsigned)) != value["profile_digest"]:
        raise ValueError("runtime profile digest mismatch")
    return value


def _minimal_windows_environment() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in ("SystemRoot", "WINDIR"):
        value = os.environ.get(name)
        if value:
            result[name] = value
    return result


def _decode_capped(value: bytes, limit: int) -> str:
    return value[:limit].decode("utf-8", errors="replace")


def _classify_launcher_failure(returncode: int, stderr: str) -> tuple[str, str]:
    detail = stderr.lower()
    if (
        "unit-result:timeout" in detail
        or "result: timeout" in detail
        or "timed out" in detail
        or returncode == 124
    ):
        return "sandbox_timeout", "wall_clock_limit"
    if (
        "out of memory" in detail
        or "oom" in detail
        or "signal=kill" in detail
        or "unit-result:oom-kill" in detail
        or "unit-result:resources" in detail
        or ";status:9" in detail
        or ";status:24" in detail
        or returncode in {137, 152, -9}
    ):
        return "sandbox_resource_limit", "resource_limit"
    if "operation not permitted" in detail or "permission denied" in detail:
        return "sandbox_violation", "sandbox_violation"
    return "sandbox_protocol_error", f"exit_{returncode}"


__all__ = [
    "SANDBOX_ENABLE_ENV",
    "SANDBOX_MANIFEST_ENV",
    "WslSandboxExecutor",
    "load_configured_wsl_sandbox_executor",
]
