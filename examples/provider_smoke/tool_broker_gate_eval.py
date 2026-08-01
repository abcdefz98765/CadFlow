"""Manual smoke acceptance for the M2 Tool Broker capability boundary."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_native_cad.agents import (
    MODEL_PROGRAM_TOOL,
    STRUCTURED_CONTRACT_TOOL,
    CadFlowToolBroker,
)


def main() -> None:
    broker = CadFlowToolBroker()
    validation = broker.invoke(
        STRUCTURED_CONTRACT_TOOL,
        skill_id="design_part",
        payload={
            "contract_type": "cad_ir_draft",
            "contract": {
                "part_type": "spacer",
                "part_name": "tool_broker_acceptance_spacer",
                "unit": "mm",
                "dimensions": {
                    "outer_diameter": 12,
                    "inner_diameter": 5,
                    "thickness": 8,
                },
                "features": {},
                "outputs": ["step", "stl"],
                "check_level": "L0",
            },
        },
    )

    with TemporaryDirectory(prefix="cadflow-tool-broker-") as temporary:
        candidate_dir = Path(temporary) / "candidate_must_not_exist"
        execution = broker.invoke(
            MODEL_PROGRAM_TOOL,
            skill_id="model_program",
            payload={
                "candidate_directory": str(candidate_dir),
                "source": "raise RuntimeError('must never execute')",
            },
        )
        candidate_directory_created = candidate_dir.exists()

    capability = broker.capability(MODEL_PROGRAM_TOOL)["capability"]
    passed = (
        validation.success
        and not capability["available"]
        and execution.codes == ("sandbox_unavailable",)
        and not execution.side_effect_started
        and not candidate_directory_created
    )
    result = {
        "schema_version": 1,
        "acceptance": "m2_tool_broker_fail_closed",
        "passed": passed,
        "platform": capability["platform"],
        "structured_validation": {
            "success": validation.success,
            "observation_type": validation.observation_type,
            "execution_profile": validation.execution_profile,
        },
        "model_program": {
            "available": capability["available"],
            "observation_type": execution.observation_type,
            "codes": list(execution.codes),
            "side_effect_started": execution.side_effect_started,
            "candidate_directory_created": candidate_directory_created,
        },
        "claim_boundary": (
            "This verifies Broker routing and fail-closed gating only; it does "
            "not verify or enable a model-program sandbox."
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
