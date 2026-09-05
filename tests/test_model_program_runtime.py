from __future__ import annotations

import io
import json
import tarfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import ai_native_cad.agents.tool_broker as tool_broker_module
from ai_native_cad.agents import (
    MODEL_PROGRAM_TOOL,
    REQUIRED_MODEL_PROGRAM_CONTROLS,
    CadFlowToolBroker,
    SandboxAttestation,
    ToolInvocationContext,
)
from ai_native_cad.agents.model_program_runtime import (
    MODEL_PROGRAM_PARAMETER_KEY_MAX_LENGTH,
    SandboxExecutionResult,
)


VALID_SOURCE = """import cadquery as cq

def build_model(parameters):
    return cq.Workplane("XY").box(
        float(parameters["length"]),
        float(parameters["width"]),
        float(parameters["height"]),
    )
"""


class FakeSandboxExecutor:
    def __init__(self, archive: bytes) -> None:
        self._archive = archive
        self.calls = 0
        self._attestation = SandboxAttestation(
            profile_id="wsl2_cadquery_v1",
            platform="Windows/WSL2",
            distro_id="CadFlow-Sandbox-CQ-v1",
            profile_digest="profile-digest",
            toolchain_digest="toolchain-digest",
            enforced_controls=REQUIRED_MODEL_PROGRAM_CONTROLS,
            probe_results=(("active_profile_probe", True),),
            issued_at=datetime.now(timezone.utc).isoformat(),
        )

    @property
    def attestation(self) -> SandboxAttestation:
        return self._attestation

    def execute(self, request) -> SandboxExecutionResult:
        self.calls += 1
        return SandboxExecutionResult(
            success=True,
            codes=(),
            exit_state="archive_returned",
            archive=self._archive,
            stderr="launcher ok",
        )


class NoArchiveSandboxExecutor(FakeSandboxExecutor):
    def execute(self, request) -> SandboxExecutionResult:
        self.calls += 1
        return SandboxExecutionResult(
            success=False,
            codes=("sandbox_timeout",),
            exit_state="wall_clock_limit",
            archive=b"",
            stderr="C:\\secret\\launcher.log timed out",
        )


class RaisingSandboxExecutor(FakeSandboxExecutor):
    def execute(self, request):
        self.calls += 1
        raise RuntimeError("C:\\secret\\executor details")


class ConcurrencyTrackingSandboxExecutor(FakeSandboxExecutor):
    def __init__(self, archive: bytes) -> None:
        super().__init__(archive)
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def execute(self, request) -> SandboxExecutionResult:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.03)
            return super().execute(request)
        finally:
            with self._lock:
                self.active -= 1


def _context(tmp_path: Path) -> ToolInvocationContext:
    return ToolInvocationContext(
        work_id="work_1",
        run_id="run_1",
        part_job_id="part_1",
        episode_id="episode_1",
        evidence_root=tmp_path.resolve(),
    )


def _payload(**overrides) -> dict:
    value = {
        "api_id": "cadquery_v1",
        "candidate_id": "candidate_001",
        "source": VALID_SOURCE,
        "parameters": {"length": 30, "width": 20, "height": 10},
        "requested_outputs": ["step"],
    }
    value.update(overrides)
    return value


def _archive(
    *,
    success: bool = True,
    extra_member: tarfile.TarInfo | None = None,
    valid_reimport: bool = True,
) -> bytes:
    observation = {
        "schema_version": 1,
        "success": success,
        "observation_type": (
            "model_program_execution_completed"
            if success
            else "model_program_execution_failed"
        ),
        "codes": [] if success else ["model_program_runtime_error"],
        "exit_state": "completed" if success else "failed",
        "geometry": {
            "valid": success,
            "solid_count": 1 if success else 0,
            "face_count": 6 if success else 0,
            "cylindrical_face_count": 0,
            "volume": 6000.0 if success else 0.0,
            "bounding_box": {"x": 30.0, "y": 20.0, "z": 10.0},
        },
    }
    if success:
        observation["step_reimport"] = {
            "valid": valid_reimport,
            "geometry": dict(observation["geometry"]),
            "bbox_tolerance_mm": 0.01,
            "volume_absolute_tolerance_mm3": 0.01,
            "volume_relative_tolerance": 1e-6,
        }
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        _add(archive, "observation.json", json.dumps(observation).encode())
        _add(archive, "stdout.txt", b"D:\\secret\\provider.txt\n")
        _add(archive, "stderr.txt", b"")
        if success:
            _add(archive, "model.step", b"ISO-10303-21;\nEND-ISO-10303-21;\n")
        if extra_member is not None:
            archive.addfile(extra_member, io.BytesIO(b"x") if extra_member.size else None)
    return stream.getvalue()


def _add(archive: tarfile.TarFile, name: str, value: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(value)
    info.mode = 0o600
    archive.addfile(info, io.BytesIO(value))


def test_attested_execution_persists_append_only_candidate_evidence(tmp_path, monkeypatch) -> None:
    monotonic = iter([10.0, 10.25])
    monkeypatch.setattr(tool_broker_module.time, "monotonic", lambda: next(monotonic))
    executor = FakeSandboxExecutor(_archive())
    broker = CadFlowToolBroker(sandbox_executor=executor)

    observation = broker.invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload=_payload(),
        context=_context(tmp_path),
    )

    assert observation.success is True
    assert observation.side_effect_started is True
    assert observation.execution_id
    assert observation.attestation_digest == executor.attestation.digest
    assert observation.cad_execution_ms == 250
    assert observation.as_dict()["cad_execution_ms"] == 250
    assert observation.output["reviewable"] is False
    assert observation.output["accepted"] is False
    assert observation.output["deliverable"] is False
    manifest_path = tmp_path / observation.output["evidence_manifest"]
    evidence = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert evidence["trust_role"] == "candidate"
    assert evidence["source_hash"] == observation.output["source_hash"]
    assert (manifest_path.parent / "source.py").read_text(encoding="utf-8") == VALID_SOURCE
    assert "D:\\secret" not in (manifest_path.parent / "stdout.txt").read_text(encoding="utf-8")
    assert executor.calls == 1


def test_cad_executor_is_single_flight_across_parallel_part_brokers(tmp_path) -> None:
    executor = ConcurrencyTrackingSandboxExecutor(_archive())
    brokers = [
        CadFlowToolBroker(sandbox_executor=executor),
        CadFlowToolBroker(sandbox_executor=executor),
    ]

    def invoke(index: int):
        return brokers[index].invoke(
            MODEL_PROGRAM_TOOL,
            skill_id="model_program",
            payload=_payload(candidate_id=f"candidate-{index}"),
            context=_context(tmp_path / str(index)),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        observations = list(pool.map(invoke, range(2)))

    assert all(item.success for item in observations)
    assert executor.calls == 2
    assert executor.max_active == 1


def test_static_policy_rejection_has_zero_runtime_or_file_side_effect(tmp_path) -> None:
    executor = FakeSandboxExecutor(_archive())
    broker = CadFlowToolBroker(sandbox_executor=executor)

    observation = broker.invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload=_payload(source="import os\ndef build_model(parameters):\n    return os.getcwd()\n"),
        context=_context(tmp_path),
    )

    assert observation.success is False
    assert observation.side_effect_started is False
    assert observation.cad_execution_ms == 0
    assert executor.calls == 0
    assert not (tmp_path / "candidates").exists()
    assert "import os" not in json.dumps(observation.as_dict())


def test_parameters_and_invocation_context_are_strict(tmp_path) -> None:
    executor = FakeSandboxExecutor(_archive())
    broker = CadFlowToolBroker(sandbox_executor=executor)

    invalid = [
        broker.invoke(
            MODEL_PROGRAM_TOOL,
            skill_id="model_program",
            payload=_payload(parameters=parameters),
            context=_context(tmp_path),
        )
        for parameters in (
            {"bad": float("nan")},
            {"": 1},
            {"x" * (MODEL_PROGRAM_PARAMETER_KEY_MAX_LENGTH + 1): 1},
        )
    ]
    missing_context = broker.invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload=_payload(),
    )

    assert all(
        item.codes == ("invalid_model_program_request",) for item in invalid
    )
    assert missing_context.codes == ("invalid_execution_context",)
    assert executor.calls == 0


def test_archive_path_traversal_and_symlink_fail_closed(tmp_path) -> None:
    traversal = tarfile.TarInfo("../escape.step")
    traversal.size = 1
    symlink = tarfile.TarInfo("model.step")
    symlink.type = tarfile.SYMTYPE
    symlink.linkname = "../../escape"

    for index, member in enumerate((traversal, symlink), start=1):
        executor = FakeSandboxExecutor(_archive(success=False, extra_member=member))
        broker = CadFlowToolBroker(sandbox_executor=executor)
        observation = broker.invoke(
            MODEL_PROGRAM_TOOL,
            skill_id="model_program",
            payload=_payload(candidate_id=f"candidate_{index}"),
            context=_context(tmp_path),
        )
        assert observation.success is False
        assert observation.codes == ("sandbox_protocol_error",)
        assert observation.side_effect_started is True
    assert not (tmp_path / "escape.step").exists()


def test_success_archive_without_valid_step_reimport_fails_closed(tmp_path) -> None:
    executor = FakeSandboxExecutor(_archive(valid_reimport=False))
    observation = CadFlowToolBroker(sandbox_executor=executor).invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload=_payload(),
        context=_context(tmp_path),
    )

    assert observation.success is False
    assert observation.codes == ("sandbox_protocol_error",)
    assert observation.output["reviewable"] is False
    assert observation.output["accepted"] is False
    assert observation.output["deliverable"] is False


def test_failed_worker_result_is_diagnostic_only(tmp_path) -> None:
    executor = FakeSandboxExecutor(_archive(success=False))
    observation = CadFlowToolBroker(sandbox_executor=executor).invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload=_payload(),
        context=_context(tmp_path),
    )

    assert observation.success is False
    assert observation.codes == ("model_program_runtime_error",)
    manifest = json.loads(
        (tmp_path / observation.output["evidence_manifest"]).read_text(encoding="utf-8")
    )
    assert manifest["trust_role"] == "diagnostic"
    assert manifest["reviewable"] is False
    assert not (tmp_path / "escape.step").exists()


def test_launcher_failure_after_start_persists_diagnostic_evidence(tmp_path) -> None:
    executor = NoArchiveSandboxExecutor(b"")
    observation = CadFlowToolBroker(sandbox_executor=executor).invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload=_payload(),
        context=_context(tmp_path),
    )

    assert observation.success is False
    assert observation.codes == ("sandbox_timeout",)
    assert observation.side_effect_started is True
    manifest_path = tmp_path / observation.output["evidence_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["trust_role"] == "diagnostic"
    assert manifest["reviewable"] is False
    assert manifest["accepted"] is False
    assert manifest["deliverable"] is False
    assert "C:\\secret" not in (manifest_path.parent / "launcher_stderr.txt").read_text(
        encoding="utf-8"
    )


def test_executor_exception_becomes_typed_diagnostic_evidence(tmp_path) -> None:
    executor = RaisingSandboxExecutor(b"")
    observation = CadFlowToolBroker(sandbox_executor=executor).invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload=_payload(),
        context=_context(tmp_path),
    )

    assert observation.success is False
    assert observation.codes == ("sandbox_protocol_error",)
    assert observation.side_effect_started is True
    assert observation.exit_state == "executor_exception"
    manifest = json.loads(
        (tmp_path / observation.output["evidence_manifest"]).read_text(encoding="utf-8")
    )
    assert manifest["trust_role"] == "diagnostic"
    assert manifest["reviewable"] is False
