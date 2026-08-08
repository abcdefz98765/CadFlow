"""Current-host acceptance for reviewable publication and explicit authority.

Set CADFLOW_MODEL_PROGRAM_SANDBOX=1 in the invoking process. This creates only
a temporary Workspace and uses a scripted action provider. Provider source is
executed solely by the attested CadFlow WSL2 Tool Broker.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from ai_native_cad.workflow_console.backend import WorkflowConsoleBackend
from ai_native_cad.workflow_console.routes import dispatch_route


SOURCE = """import cadquery as cq

def build_model(parameters):
    body = cq.Workplane("XY").polygon(6, float(parameters["diameter"])).extrude(
        float(parameters["height"])
    )
    return body.faces(">Z").workplane().hole(float(parameters["bore"]))
"""


class ScriptedProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.actions = iter(
            [
                {
                    "action": "create_model_program",
                    "model_program": {
                        "api_id": "cadquery_v1",
                        "source": SOURCE,
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cadflow-m2-publication-") as value:
        root = Path(value).resolve()
        backend = WorkflowConsoleBackend(project_root=root)
        backend.create_work("Hex bore", work_id="acceptance_work")
        backend.create_work_part_attempt(
            "acceptance_work",
            "hex_bore",
            run_id="acceptance_attempt_1",
        )
        provider = ScriptedProvider()
        backend.stage_runner.agent_adapter = provider
        before = backend._read_work_manifest("acceptance_work")

        published = backend.run_work_part_design_episode(
            "acceptance_work",
            "hex_bore",
            request_id="acceptance_request_1",
        )
        after_publication = backend._read_work_manifest("acceptance_work")
        summary = published["reviewable_result"]
        if not isinstance(summary, dict):
            diagnostics = list(
                backend._work_runs_root("acceptance_work").rglob(
                    "publication_diagnostic.json"
                )
            )
            detail = (
                json.loads(diagnostics[0].read_text(encoding="utf-8"))
                if diagnostics
                else {"code": "publication_result_missing"}
            )
            detail["episode"] = published.get("episode")
            print(json.dumps(detail, indent=2, sort_keys=True))
            raise SystemExit(1)
        reviewable_id = summary["reviewable_result_id"]
        episode_root = (
            backend._work_runs_root("acceptance_work")
            / "acceptance_attempt_1"
            / "episodes"
            / "design_part"
            / "acceptance_request_1"
        )
        reviewable_record = json.loads(
            (episode_root / "reviewable_result.json").read_text(encoding="utf-8")
        )
        step_path = episode_root / Path(reviewable_record["step"]["relative_path"])
        manifest_bytes = backend._work_manifest_path("acceptance_work").read_bytes()

        replay = backend.run_work_part_design_episode(
            "acceptance_work",
            "hex_bore",
            request_id="acceptance_request_1",
        )
        after_replay_bytes = backend._work_manifest_path("acceptance_work").read_bytes()
        pre_accept_assertions = {
            "reviewable_published": reviewable_record["reviewable"] is True,
            "reviewable_not_accepted": reviewable_record["accepted"] is False,
            "reviewable_not_deliverable": reviewable_record["deliverable"] is False,
            "step_hash_matches": _sha256(step_path) == reviewable_record["step"]["sha256"],
            "step_size_matches": step_path.stat().st_size == reviewable_record["step"]["size"],
            "accepted_pointer_unchanged": after_publication["accepted_part_results"] == before["accepted_part_results"],
            "deliverables_unchanged": after_publication["deliverable_packages"] == before["deliverable_packages"],
            "active_lineage_unchanged": after_publication["active_lineage"] == before["active_lineage"],
            "replay_did_not_call_provider": provider.calls == 4,
            "replay_did_not_rewrite_work": after_replay_bytes == manifest_bytes,
            "replay_marked_idempotent": replay["episode"]["idempotent_replay"] is True,
        }

        accepted = dispatch_route(
            backend,
            "accept_work_reviewable_result",
            path_params={
                "work_id": "acceptance_work",
                "part_job_id": "hex_bore",
                "reviewable_result_id": reviewable_id,
            },
            body={},
        )
        pointer = accepted["data"]["accepted_part_result"]
        revised = dispatch_route(
            backend,
            "revise_work_reviewable_result",
            path_params={
                "work_id": "acceptance_work",
                "part_job_id": "hex_bore",
                "reviewable_result_id": reviewable_id,
            },
            body={
                "revision_prompt": "Increase the bore by 0.5 mm.",
                "run_id": "acceptance_attempt_2",
            },
        )
        final = backend._read_work_manifest("acceptance_work")
        authority_assertions = {
            "explicit_accept_route_changed_pointer": (
                accepted["ok"] is True and pointer["result_id"] == reviewable_id
            ),
            "revision_route_created_attempt": revised["ok"] is True,
            "revision_preserved_accepted_pointer": (
                final["accepted_part_results"]["hex_bore"] == pointer
            ),
            "revision_created_no_deliverable": final["deliverable_packages"] == [],
        }
        assertions = {**pre_accept_assertions, **authority_assertions}
        observation = json.loads(
            (episode_root / "execution_observations" / "observation_001.json")
            .read_text(encoding="utf-8")
        )
        result = {
            "schema_version": 1,
            "passed": all(assertions.values()),
            "assertions": assertions,
            "capability_mode": summary["capability_mode"],
            "reviewable_result_id": reviewable_id,
            "provider": {"provider": "scripted", "model": "fixture"},
            "assumptions": summary["assumptions"],
            "attestation_digest": reviewable_record["attestation_digest"],
            "profile_digest": reviewable_record["profile_digest"],
            "toolchain_digest": reviewable_record["toolchain_digest"],
            "source_hash": reviewable_record["source_hash"],
            "parameters_hash": reviewable_record["parameters_hash"],
            "step": {
                "sha256": reviewable_record["step"]["sha256"],
                "size": reviewable_record["step"]["size"],
            },
            "geometry": reviewable_record["geometry"],
            "step_reimport": reviewable_record["step_reimport"],
            "limits": observation["limits"],
            "recommended_action": summary["recommended_action"],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        if not result["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
