from __future__ import annotations

import io
import json
import os
import platform
import tarfile
import time

import pytest

from ai_native_cad.agents.model_program_runtime import ModelProgramExecutionRequest
from ai_native_cad.agents.episode import run_design_part_episode
from ai_native_cad.agents.wsl_sandbox import load_configured_wsl_sandbox_executor
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.routes import dispatch_route


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


def test_provider_selected_episode_consumes_attested_execution_observation(
    tmp_path,
) -> None:
    class ScriptedAdapter:
        def __init__(self):
            self.actions = iter(
                [
                    {
                        "action": "create_model_program",
                        "model_program": {
                            "api_id": "cadquery_v1",
                            "source": VALID_NON_TEMPLATE_SOURCE,
                            "parameters": {
                                "diameter": 42.0,
                                "height": 8.0,
                                "bore": 9.0,
                            },
                            "requested_outputs": ["step"],
                        },
                        "assumptions": ["Dimensions are in millimetres."],
                    },
                    {"action": "request_execution"},
                    {"action": "inspect_observation"},
                    {"action": "stop", "stop_reason": "completed"},
                ]
            )

        def choose_design_action(self, *, state, skill_manifest):
            return next(self.actions)

    result = run_design_part_episode(
        adapter=ScriptedAdapter(),
        handoff={
            "work_id": "integration_work",
            "part_id": "hex_bore",
            "status": "active_part_job_attempt",
            "part_brief": "Hexagonal boss with a central bore",
            "interface_constraints": [],
            "preserved_assembly_context": {},
        },
        artifact_dir=tmp_path,
        run_id="integration_run",
    )

    assert result.status == "completed"
    assert result.result_kind == "model_program"
    assert result.output_validated is True
    assert result.execution_succeeded is True
    assert result.validated is False
    assert result.final_candidate_id == "candidate_001"
    assert result.final_observation_id == "observation_001"
    persisted = json.loads(
        (tmp_path / "execution_observations" / "observation_001.json")
        .read_text(encoding="utf-8")
    )
    assert persisted["output"]["step_reimport"]["valid"] is True
    assert persisted["reviewable"] is False
    assert persisted["accepted"] is False
    assert persisted["deliverable"] is False


def test_work_product_route_publishes_then_requires_explicit_acceptance(
    tmp_path,
) -> None:
    class ScriptedAdapter:
        def __init__(self):
            self.calls = 0
            self.actions = iter(
                [
                    {
                        "action": "create_model_program",
                        "model_program": {
                            "api_id": "cadquery_v1",
                            "source": VALID_NON_TEMPLATE_SOURCE,
                            "parameters": {
                                "diameter": 42.0,
                                "height": 8.0,
                                "bore": 9.0,
                            },
                            "requested_outputs": ["step"],
                        },
                        "assumptions": ["Dimensions are in millimetres."],
                    },
                    {"action": "request_execution"},
                    {"action": "inspect_observation"},
                    {"action": "stop", "stop_reason": "completed"},
                ]
            )

        def choose_design_action(self, *, state, skill_manifest):
            self.calls += 1
            return next(self.actions)

    backend = WorkflowConsoleBackend(project_root=tmp_path)
    backend.create_work("Hex bore", work_id="integration_work")
    backend.create_work_part_attempt(
        "integration_work",
        "hex_bore",
        run_id="integration_attempt_1",
    )
    provider = ScriptedAdapter()
    backend.stage_runner.agent_adapter = provider
    before = backend._read_work_manifest("integration_work")

    response = dispatch_route(
        backend,
        "run_work_part_design_episode",
        path_params={
            "work_id": "integration_work",
            "part_job_id": "hex_bore",
        },
        body={"request_id": "integration_request_1"},
    )

    assert response["ok"] is True
    data = response["data"]
    reviewable_id = data["reviewable_result"]["reviewable_result_id"]
    assert data["orchestration"]["checkpoint"] == "reviewable_result"
    assert data["orchestration"]["phase"] == "build_evaluate"
    assert data["orchestration"]["next_action"] == "Accept or revise"
    assert data["reviewable_result"]["validation"] == {
        "execution_success": True,
        "step_reimport_valid": True,
        "solid_count": 1,
    }
    assert data["reviewable_result"]["recommended_action"] == "Accept or revise"
    assert data["reviewable_result"]["assumptions"] == [
        "Dimensions are in millimetres."
    ]
    assert {
        item["trust_role"] for item in data["artifact_references"]
    } >= {"candidate", "observation", "reviewable_result"}
    published = backend._read_work_manifest("integration_work")
    assert published["accepted_part_results"] == before["accepted_part_results"]
    assert published["deliverable_packages"] == before["deliverable_packages"]
    assert published["active_lineage"] == before["active_lineage"]
    manifest_path = backend._work_manifest_path("integration_work")
    after_publish_bytes = manifest_path.read_bytes()

    replay = backend.run_work_part_design_episode(
        "integration_work",
        "hex_bore",
        request_id="integration_request_1",
    )
    assert replay["episode"]["idempotent_replay"] is True
    assert replay["reviewable_result"]["reviewable_result_id"] == reviewable_id
    assert provider.calls == 4
    assert manifest_path.read_bytes() == after_publish_bytes

    accepted = dispatch_route(
        backend,
        "accept_work_reviewable_result",
        path_params={
            "work_id": "integration_work",
            "part_job_id": "hex_bore",
            "reviewable_result_id": reviewable_id,
        },
        body={},
    )
    assert accepted["ok"] is True
    accepted_pointer = accepted["data"]["accepted_part_result"]
    assert accepted_pointer["result_id"] == reviewable_id

    revised = dispatch_route(
        backend,
        "revise_work_reviewable_result",
        path_params={
            "work_id": "integration_work",
            "part_job_id": "hex_bore",
            "reviewable_result_id": reviewable_id,
        },
        body={
            "revision_prompt": "Increase the bore by 0.5 mm.",
            "run_id": "integration_attempt_2",
        },
    )
    assert revised["ok"] is True
    final = backend._read_work_manifest("integration_work")
    assert final["accepted_part_results"]["hex_bore"] == accepted_pointer
    assert final["deliverable_packages"] == []


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
