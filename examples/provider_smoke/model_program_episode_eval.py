"""Current-host acceptance for the provider-selected model-program Episode.

Set CADFLOW_MODEL_PROGRAM_SANDBOX=1 in the invoking process. The script uses a
scripted action provider so it tests CadFlow's Episode, Broker, attestation,
worker, STEP re-import, and evidence boundary without an external credential.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from ai_native_cad.agents import run_design_part_episode


SOURCE = """import cadquery as cq

def build_model(parameters):
    body = cq.Workplane("XY").polygon(6, float(parameters["diameter"])).extrude(
        float(parameters["height"])
    )
    return body.faces(">Z").workplane().hole(float(parameters["bore"]))
"""


class ScriptedProvider:
    def __init__(self) -> None:
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
                },
                {"action": "request_execution"},
                {"action": "inspect_observation"},
                {"action": "stop", "stop_reason": "completed"},
            ]
        )

    def choose_design_action(self, *, state, skill_manifest):
        return next(self.actions)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cadflow-m2-episode-") as value:
        root = Path(value).resolve()
        result = run_design_part_episode(
            adapter=ScriptedProvider(),
            handoff={
                "work_id": "acceptance_work",
                "part_id": "hex_bore",
                "status": "active_part_job_attempt",
                "part_brief": "Hexagonal boss with a central bore",
                "interface_constraints": [],
                "preserved_assembly_context": {},
            },
            artifact_dir=root,
            run_id="acceptance_run",
        )
        observation_path = (
            root / "execution_observations" / "observation_001.json"
        )
        observation = json.loads(observation_path.read_text(encoding="utf-8"))
        step_path = next(root.glob("candidates/*/exec_*/model.step"))
        source_path = step_path.parent / "source.py"
        events = (root / "agent_events.jsonl").read_text(encoding="utf-8")
        assertions = {
            "episode_completed": result.status == "completed",
            "output_validated": result.output_validated is True,
            "observation_inspected": result.observation_inspection_count == 1,
            "step_reimport_valid": observation["output"]["step_reimport"]["valid"] is True,
            "source_absent_from_events": SOURCE not in events,
            "source_retained_only_in_broker_evidence": (
                source_path.read_text(encoding="utf-8") == SOURCE
                and not list(
                    (root / "model_program_submissions").glob("*.py")
                )
            ),
            "reviewable_absent": not (root / "reviewable_result.json").exists(),
            "accepted_absent": not (root / "accepted_result.json").exists(),
            "deliverable_absent": not (root / "deliverable_package.json").exists(),
        }
        summary = {
            "schema_version": 1,
            "passed": all(assertions.values()),
            "assertions": assertions,
            "episode": {
                "skill_id": result.skill_id,
                "skill_version": result.skill_version,
                "capability_mode": result.capability_mode,
                "candidate_id": result.final_candidate_id,
                "observation_id": result.final_observation_id,
                "execution_count": result.execution_count,
                "inspection_count": result.observation_inspection_count,
            },
            "attestation_digest": observation["attestation_digest"],
            "profile_digest": observation["output"]["profile_digest"],
            "toolchain_digest": observation["output"]["toolchain_digest"],
            "source_hash": observation["output"]["source_hash"],
            "parameters_hash": observation["output"]["parameters_hash"],
            "step": {
                "sha256": _sha256(step_path),
                "size": step_path.stat().st_size,
            },
            "geometry": observation["output"]["geometry"],
            "step_reimport": observation["output"]["step_reimport"],
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        if not summary["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
