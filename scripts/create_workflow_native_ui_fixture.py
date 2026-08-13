"""Create the isolated Workflow-native UI owner fixture.

The fixture uses the real Work, Part Job, Design Episode, policy, and evidence
paths.  It is developer-only catalog data and never appears with normal Works.
"""

from __future__ import annotations

import json

from ai_native_cad.agents import JsonContractAgentAdapter
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend


WORK_ID = "workflow_native_ui_owner_fixture"
REQUEST = (
    "Design a camera cradle that attaches to a 2020 extrusion through a "
    "separate adapter. Keep the camera cradle and extrusion adapter as "
    "independent generated Parts; the camera and extrusion are references."
)


class _BlockedCameraCradleClient:
    """Return one safely rejected provider response for the owner scenario."""

    provider_identity = {
        "provider": "scripted-owner-fixture",
        "model": "policy-contract-case",
    }

    def generate_json_contract(self, _request: dict[str, object]) -> dict[str, object]:
        return {
            "action": "create_contract",
            "contract_type": "cad_ir_draft",
            "summary": "Prepared the Camera Cradle geometry contract.",
            "contract": {
                "part_type": "simple_bracket",
                "part_name": "camera_cradle",
                "unit": "mm",
                "dimensions": {
                    "base_length": 72,
                    "base_width": 46,
                    "height": 38,
                    "thickness": 4,
                },
                "features": {},
                "outputs": ["step", "stl"],
                "check_level": "L0",
                # This provider-owned execution field is deliberately outside
                # the structured-contract Skill and must fail closed.
                "python_code": "open('../escape.txt', 'w').write('blocked')",
            },
        }


def create_fixture(backend: WorkflowConsoleBackend | None = None) -> dict[str, object]:
    backend = backend or WorkflowConsoleBackend()
    try:
        return {
            "work_id": WORK_ID,
            "created": False,
            "detail": backend.get_work_detail(WORK_ID),
        }
    except FileNotFoundError:
        pass

    backend.create_workspace()
    backend.create_work(
        "Camera Mount Workflow · Owner Fixture",
        description=REQUEST,
        work_id=WORK_ID,
        metadata={
            "product_entry": "new_design",
            "work_classification": "developer_fixture",
            "fixture_purpose": (
                "Workflow-native UI blocked-attempt, selected-scope, and "
                "lazy-evidence verification"
            ),
        },
    )
    backend.create_work_requirement_run(
        WORK_ID,
        REQUEST,
        run_id="work_design_attempt_1",
    )
    backend.create_work_part_attempt(
        WORK_ID,
        "camera_cradle",
        prompt=(
            "Part Job: Camera Cradle\n"
            "Role: Hold and protect the camera while exposing its optical and cable interfaces."
        ),
        role="Hold and protect the camera",
        run_id="camera_cradle_attempt_1",
    )
    backend.create_work_part_attempt(
        WORK_ID,
        "extrusion_adapter",
        prompt=(
            "Part Job: Extrusion Adapter\n"
            "Role: Connect the cradle interface to a 2020 extrusion slot."
        ),
        role="Connect the cradle to 2020 extrusion",
        run_id="extrusion_adapter_attempt_1",
    )

    manifest = backend._read_work_manifest(WORK_ID)
    manifest["work_design"].update(
        {
            "status": "completed",
            "run_id": "work_design_attempt_1",
            "current_design": {
                "concept_summary": (
                    "Use two generated Parts: a camera-specific cradle and a "
                    "separate extrusion adapter, joined by a simple planar interface."
                ),
                "generated_parts": [
                    {
                        "part_job_id": "camera_cradle",
                        "name": "Camera Cradle",
                        "role": "Hold and protect the camera",
                    },
                    {
                        "part_job_id": "extrusion_adapter",
                        "name": "Extrusion Adapter",
                        "role": "Connect the cradle to 2020 extrusion",
                    },
                ],
                "reference_components": [
                    {
                        "name": "Camera module",
                        "role": "Defines the cradle envelope, lens opening, and cable clearance",
                    },
                    {
                        "name": "2020 extrusion",
                        "role": "Defines the adapter slot interface",
                    },
                ],
                "interfaces": [
                    {
                        "name": "Cradle-to-adapter interface",
                        "description": "Two M4 fasteners on a shared planar datum",
                    }
                ],
                "dependencies": [
                    "Camera Cradle and Extrusion Adapter can be designed independently against the shared interface."
                ],
                "assumptions": [
                    "Prototype dimensions only; camera fit and structural strength are unverified."
                ],
                "unresolved_questions": [],
                "assembly_expected": False,
                "recommendation": "Design each generated Part independently, then review each result.",
            },
        }
    )
    backend._write_work_manifest(WORK_ID, manifest)
    backend.invalidate_work_index()

    backend.stage_runner.agent_adapter = JsonContractAgentAdapter(
        _BlockedCameraCradleClient(),
        provider="scripted-owner-fixture",
        model="policy-contract-case",
    )
    outcome = backend.run_work_part_design_episode(
        WORK_ID,
        "camera_cradle",
        request_id="camera_cradle_policy_block_1",
        attempt_run_id="camera_cradle_attempt_1",
    )
    if outcome["episode"]["stop_reason"] != "policy_blocked":
        raise RuntimeError("owner fixture did not reach the expected policy_blocked outcome")
    return {"work_id": WORK_ID, "created": True, "outcome": outcome}


if __name__ == "__main__":
    print(json.dumps(create_fixture(), ensure_ascii=False, indent=2))
