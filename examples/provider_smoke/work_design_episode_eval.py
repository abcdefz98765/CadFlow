"""Manual acceptance for WorkOrchestrator-routed validation-only design."""

from __future__ import annotations

import json
from copy import deepcopy
from tempfile import TemporaryDirectory

from ai_native_cad.agents import JsonContractAgentAdapter
from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend


class ScriptedClient:
    def __init__(self) -> None:
        self.requests = []
        self.responses = [
            {"action": "request_context", "context_key": "part_job"},
            {
                "action": "create_contract",
                "contract_type": "cad_ir_draft",
                "contract": {
                    "part_type": "simple_bracket",
                    "part_name": "work_routed_acceptance_clamp",
                    "unit": "mm",
                    "dimensions": {
                        "base_length": 50,
                        "base_width": 30,
                        "height": 35,
                        "thickness": 5,
                    },
                    "features": {},
                    "outputs": ["step", "stl"],
                    "check_level": "L0",
                },
            },
            {"action": "request_validation"},
        ]

    @property
    def provider_identity(self):
        return {"provider": "scripted-product-design", "model": "acceptance"}

    def generate_json_contract(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def main() -> None:
    with TemporaryDirectory(prefix="cadflow-work-design-") as temporary:
        backend = WorkflowConsoleBackend(project_root=temporary)
        backend.create_work(
            "Clamp",
            description="Design a compact printable clamp jaw.",
            work_id="clamp_work",
        )
        backend.create_work_part_attempt(
            "clamp_work",
            "clamp",
            role="moving jaw",
            run_id="clamp_attempt_1",
        )
        before = backend._read_work_manifest("clamp_work")
        protected_before = deepcopy(
            {
                "active_lineage": before["active_lineage"],
                "accepted_part_results": before["accepted_part_results"],
                "part_jobs": before["part_jobs"],
                "deliverable_packages": before["deliverable_packages"],
            }
        )
        run_dir = backend._work_runs_root("clamp_work") / "clamp_attempt_1"
        prompt_before = (run_dir / "prompt.txt").read_bytes()
        client = ScriptedClient()
        backend.stage_runner.agent_adapter = JsonContractAgentAdapter(
            client,
            provider="scripted",
            model="acceptance",
        )

        first = backend.run_work_part_design_episode(
            "clamp_work",
            "clamp",
            request_id="acceptance_request_001",
        )
        manifest_after_first = backend._work_manifest_path(
            "clamp_work"
        ).read_bytes()
        replay = backend.run_work_part_design_episode(
            "clamp_work",
            "clamp",
            request_id="acceptance_request_001",
        )
        after = backend._read_work_manifest("clamp_work")
        protected_after = {
            "active_lineage": after["active_lineage"],
            "accepted_part_results": after["accepted_part_results"],
            "part_jobs": after["part_jobs"],
            "deliverable_packages": after["deliverable_packages"],
        }
        model_products = [
            name
            for name in ("model.py", "model.step", "model.stl", "preview.png")
            if any(run_dir.rglob(name))
        ]
        passed = (
            first["episode"]["validated"] is True
            and replay["episode"]["idempotent_replay"] is True
            and len(client.requests) == 3
            and protected_after == protected_before
            and backend._work_manifest_path("clamp_work").read_bytes()
            == manifest_after_first
            and (run_dir / "prompt.txt").read_bytes() == prompt_before
            and not model_products
            and first["product_state"]["accepted_artifacts"] == []
            and first["product_state"]["deliverable_artifacts"] == []
        )
        result = {
            "schema_version": 1,
            "acceptance": "m2_work_orchestrator_design_episode",
            "passed": passed,
            "episode": {
                "validated": first["episode"]["validated"],
                "stop_reason": first["episode"]["stop_reason"],
                "artifact_reference_count": len(first["artifact_references"]),
                "provider_call_count": len(client.requests),
            },
            "idempotency": {
                "replay": replay["episode"]["idempotent_replay"],
                "work_manifest_unchanged_on_replay": (
                    backend._work_manifest_path("clamp_work").read_bytes()
                    == manifest_after_first
                ),
            },
            "trust_boundary": {
                "protected_work_state_unchanged": protected_after == protected_before,
                "original_run_prompt_unchanged": (
                    (run_dir / "prompt.txt").read_bytes() == prompt_before
                ),
                "model_products": model_products,
                "accepted_artifact_count": len(
                    first["product_state"]["accepted_artifacts"]
                ),
                "deliverable_artifact_count": len(
                    first["product_state"]["deliverable_artifacts"]
                ),
            },
            "claim_boundary": (
                "This verifies product routing of validation-only candidate "
                "evidence; it does not execute CAD or produce a reviewable result."
            ),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        if not passed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
