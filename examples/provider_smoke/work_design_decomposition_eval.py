"""Deterministic acceptance for canonical Work Design before Part Jobs."""

from __future__ import annotations

import json
from tempfile import TemporaryDirectory

from ai_native_cad.agents import JsonContractAgentAdapter
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend


class ScriptedClient:
    provider_identity = {"provider": "scripted", "model": "work-design-decomposition"}

    def __init__(self) -> None:
        self.responses = [
            {"action": "request_context", "context_key": "work_request"},
            {
                "action": "propose_work_design",
                "work_design": {
                    "objective": "Mount a camera to a 2020 extrusion with an adjustable tilt joint.",
                    "concept_summary": "Generate a camera cradle and rail adapter; treat the rail and camera as references.",
                    "generated_parts": [
                        {
                            "key": "cradle",
                            "name": "Camera cradle",
                            "role": "Hold the reference camera and provide a tilt interface.",
                            "interfaces": ["camera envelope", "M4 tilt pivot"],
                            "dependencies": [],
                        },
                        {
                            "key": "adapter",
                            "name": "Extrusion adapter",
                            "role": "Connect the cradle pivot to the reference extrusion.",
                            "interfaces": ["M4 tilt pivot", "M5 T-nut slot"],
                            "dependencies": ["cradle"],
                        },
                    ],
                    "reference_components": [
                        {"name": "2020 extrusion", "role": "Existing rail", "interfaces": ["M5 T-nut slot"]},
                        {"name": "Camera", "role": "Existing payload", "interfaces": ["camera envelope"]},
                    ],
                    "interfaces": [
                        {"from": "cradle", "to": "adapter", "description": "M4 pivot with clamp friction"}
                    ],
                    "dependencies": [],
                    "assumptions": ["Prototype loads only"],
                    "unresolved_questions": [],
                    "assembly_expected": True,
                    "recommendation": "Create two Part Jobs; do not create an Assembly Job in this milestone.",
                },
            },
            {"action": "create_part_jobs"},
        ]

    def generate_json_contract(self, request: dict) -> dict:
        return self.responses.pop(0)


def main() -> None:
    with TemporaryDirectory(prefix="cadflow-work-design-decomposition-") as temporary:
        backend = WorkflowConsoleBackend(project_root=temporary)
        created = backend.create_product_design(
            "Mount a camera to a 2020 extrusion with an adjustable tilt joint.",
            title="Adjustable Camera Mount",
        )
        work_id = created["work_id"]
        before = backend._read_work_manifest(work_id)
        backend.stage_runner.agent_adapter = JsonContractAgentAdapter(
            ScriptedClient(), provider="scripted", model="work-design-decomposition"
        )
        result = backend.run_work_design_episode(work_id, request_id="deterministic_multi_part")
        after = backend._read_work_manifest(work_id)
        passed = (
            before["part_jobs"] == []
            and result["episode"]["status"] == "completed"
            and len(after["part_jobs"]) == 2
            and len(after["work_design"]["current_design"]["reference_components"]) == 2
            and after["assembly_job"] is None
            and after["accepted_part_results"] == {}
        )
        print(json.dumps({
            "schema_version": 1,
            "acceptance": "m2_9_work_design_decomposition",
            "passed": passed,
            "work_design_status": after["work_design"]["status"],
            "part_job_ids": [item["part_job_id"] for item in after["part_jobs"]],
            "reference_component_count": 2,
            "assembly_created": after["assembly_job"] is not None,
        }, indent=2, sort_keys=True))
        if not passed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
