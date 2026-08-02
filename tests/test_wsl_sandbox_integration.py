from __future__ import annotations

import io
import json
import os
import platform
import tarfile
import time

import pytest

from ai_native_cad.agents.model_program_runtime import ModelProgramExecutionRequest
from ai_native_cad.agents.wsl_sandbox import load_configured_wsl_sandbox_executor


pytestmark = pytest.mark.skipif(
    platform.system() != "Windows"
    or os.environ.get("CADFLOW_MODEL_PROGRAM_SANDBOX", "").lower() not in {"1", "true", "enabled"},
    reason="requires the explicitly enabled, attested CadFlow WSL2 sandbox",
)


VALID_NON_TEMPLATE_SOURCE = """import cadquery as cq

def build_model(parameters):
    body = cq.Workplane("XY").polygon(6, float(parameters["diameter"])).extrude(
        float(parameters["height"])
    )
    return body.faces(">Z").workplane().hole(float(parameters["bore"]))
"""


def _executor():
    executor, reasons, _ = load_configured_wsl_sandbox_executor()
    assert executor is not None, reasons
    return executor


def _observation(archive_bytes: bytes) -> tuple[dict, dict[str, bytes]]:
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        for member in archive.getmembers():
            handle = archive.extractfile(member)
            assert handle is not None
            files[member.name] = handle.read()
    return json.loads(files["observation.json"]), files


def test_attested_profile_and_non_template_step_execution() -> None:
    executor = _executor()

    assert all(value for _, value in executor.attestation.probe_results)
    result = executor.execute(
        ModelProgramExecutionRequest(
            api_id="cadquery_v1",
            candidate_id="integration_hex_bore",
            source=VALID_NON_TEMPLATE_SOURCE,
            parameters={"diameter": 42.0, "height": 8.0, "bore": 9.0},
            requested_outputs=("step",),
        )
    )
    assert result.archive, (result.codes, result.exit_state, result.stderr)
    observation, files = _observation(result.archive)

    assert result.success is True
    assert observation["success"] is True
    assert observation["geometry"]["solid_count"] >= 1
    assert observation["geometry"]["volume"] > 0
    assert observation["step_reimport"]["valid"] is True
    assert observation["step_reimport"]["geometry"]["solid_count"] == observation["geometry"]["solid_count"]
    for axis in ("x", "y", "z"):
        assert abs(
            observation["step_reimport"]["geometry"]["bounding_box"][axis]
            - observation["geometry"]["bounding_box"][axis]
        ) <= 0.01
    assert files["model.step"].startswith(b"ISO-10303-21")
    assert len(files["model.step"]) < 67_108_864


def test_worker_defense_in_depth_rejects_non_allowlisted_import() -> None:
    result = _executor().execute(
        ModelProgramExecutionRequest(
            api_id="cadquery_v1",
            candidate_id="integration_import_attack",
            source=(
                "def build_model(parameters):\n"
                "    import os\n"
                "    return os.listdir('/')\n"
            ),
            parameters={},
            requested_outputs=("step",),
        )
    )
    observation, files = _observation(result.archive)

    assert observation["success"] is False
    assert observation["codes"] == ["model_program_runtime_error"]
    assert "model.step" not in files


@pytest.mark.parametrize(
    ("candidate_id", "source"),
    [
        (
            "integration_cpu_limit",
            "def build_model(parameters):\n    while True:\n        pass\n",
        ),
        (
            "integration_memory_limit",
            "def build_model(parameters):\n"
            "    values = [0] * int(parameters['count'])\n"
            "    return values\n",
        ),
    ],
)
def test_cpu_and_memory_exhaustion_fail_closed(candidate_id: str, source: str) -> None:
    started = time.monotonic()
    result = _executor().execute(
        ModelProgramExecutionRequest(
            api_id="cadquery_v1",
            candidate_id=candidate_id,
            source=source,
            parameters={"count": 300_000_000},
            requested_outputs=("step",),
        )
    )
    elapsed = time.monotonic() - started

    if result.archive:
        observation, files = _observation(result.archive)
        codes = observation["codes"]
        assert observation["success"] is False
        assert "model.step" not in files
    else:
        codes = list(result.codes)
    assert set(codes) & {"sandbox_timeout", "sandbox_resource_limit"}
    assert elapsed < 40
