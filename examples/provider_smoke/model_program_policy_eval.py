"""File-level acceptance for the CadQuery v1 static source policy boundary."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_native_cad.agents import (
    CADQUERY_MODEL_PROGRAM_API,
    MODEL_PROGRAM_SOURCE_TOOL,
    MODEL_PROGRAM_TOOL,
    CadFlowToolBroker,
    cadquery_model_program_policy_manifest,
)


VALID_SOURCE = """\
import cadquery as cq

def build_model(parameters):
    width = float(parameters["width"])
    depth = float(parameters["depth"])
    return cq.Workplane("XY").box(width, depth, 5.0).faces(">Z").hole(4.0)
"""

FORBIDDEN_SOURCE = """\
import socket

def build_model(parameters):
    return open("../escape.txt", "w")
"""


def main() -> int:
    broker = CadFlowToolBroker()
    policy = cadquery_model_program_policy_manifest()
    with TemporaryDirectory(prefix="cadflow_model_policy_") as temporary:
        candidate_directory = Path(temporary) / "must_not_be_created"
        valid = broker.invoke(
            MODEL_PROGRAM_SOURCE_TOOL,
            skill_id="model_program",
            payload={
                "api_id": CADQUERY_MODEL_PROGRAM_API,
                "source": VALID_SOURCE,
            },
        )
        rejected = broker.invoke(
            MODEL_PROGRAM_SOURCE_TOOL,
            skill_id="model_program",
            payload={
                "api_id": CADQUERY_MODEL_PROGRAM_API,
                "source": FORBIDDEN_SOURCE,
            },
        )
        execution = broker.invoke(
            MODEL_PROGRAM_TOOL,
            skill_id="model_program",
            payload={
                "candidate_directory": str(candidate_directory),
                "source": VALID_SOURCE,
            },
        )
        serialized_observations = json.dumps(
            {
                "valid": valid.as_dict(),
                "rejected": rejected.as_dict(),
                "execution": execution.as_dict(),
            }
        )
        passed = all(
            (
                valid.success is True,
                valid.output.get("executed") is False,
                valid.output.get("source_retained") is False,
                rejected.success is False,
                "import_not_allowed" in rejected.codes,
                "dangerous_call_not_allowed" in rejected.codes,
                execution.observation_type == "sandbox_unavailable",
                execution.side_effect_started is False,
                not candidate_directory.exists(),
                VALID_SOURCE not in serialized_observations,
                FORBIDDEN_SOURCE not in serialized_observations,
                all(value is False for value in policy["authority"].values()),
            )
        )
        summary = {
            "schema_version": 1,
            "acceptance": "m2_cadquery_v1_static_source_policy",
            "passed": passed,
            "static_validation": {
                "api_id": policy["api_id"],
                "entrypoint": policy["entrypoint"]["signature"],
                "valid_source_accepted": valid.success,
                "forbidden_source_codes": list(rejected.codes),
                "source_retained": valid.output.get("source_retained"),
                "side_effect_started": valid.side_effect_started,
            },
            "execution_gate": {
                "observation_type": execution.observation_type,
                "side_effect_started": execution.side_effect_started,
                "candidate_directory_created": candidate_directory.exists(),
            },
            "claim_boundary": (
                "Static AST policy validation passed; no model program was "
                "executed and the Windows sandbox remains unavailable."
            ),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
