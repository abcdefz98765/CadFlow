from __future__ import annotations

import json
import os
import platform
from pathlib import Path

import pytest

from ai_native_cad.agents import (
    MODEL_PROGRAM_TOOL,
    CadFlowToolBroker,
    ToolInvocationContext,
)


pytestmark = pytest.mark.skipif(
    platform.system() != "Windows"
    or os.environ.get("CADFLOW_MODEL_PROGRAM_SANDBOX", "").lower() not in {"1", "true", "enabled"},
    reason="requires the explicitly enabled, attested CadFlow WSL2 sandbox",
)


SOURCE = """import cadquery as cq

def build_model(parameters):
    body = cq.Workplane("XY").polygon(6, float(parameters["diameter"])).extrude(
        float(parameters["height"])
    )
    return body.faces(">Z").workplane().hole(float(parameters["bore"]))
"""


def test_broker_persists_only_candidate_evidence_and_preserves_trust_pointers(
    tmp_path: Path,
) -> None:
    accepted_pointer = tmp_path / "accepted-result.json"
    deliverable = tmp_path / "deliverable-package.json"
    accepted_pointer.write_text('{"accepted":"prior"}\n', encoding="utf-8")
    deliverable.write_text('{"source":"accepted-only"}\n', encoding="utf-8")
    before = (accepted_pointer.read_bytes(), deliverable.read_bytes())
    broker = CadFlowToolBroker()

    observation = broker.invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload={
            "api_id": "cadquery_v1",
            "candidate_id": "broker_hex_bore",
            "source": SOURCE,
            "parameters": {"diameter": 42.0, "height": 8.0, "bore": 9.0},
            "requested_outputs": ["step"],
        },
        context=ToolInvocationContext(
            work_id="work_integration",
            run_id="run_integration",
            part_job_id="part_integration",
            episode_id="episode_integration",
            evidence_root=tmp_path.resolve(),
        ),
    )

    assert observation.success is True
    assert observation.output["reviewable"] is False
    assert observation.output["accepted"] is False
    assert observation.output["deliverable"] is False
    assert before == (accepted_pointer.read_bytes(), deliverable.read_bytes())
    manifest = json.loads(
        (tmp_path / observation.output["evidence_manifest"]).read_text(encoding="utf-8")
    )
    assert manifest["work_id"] == "work_integration"
    assert manifest["run_id"] == "run_integration"
    assert manifest["part_job_id"] == "part_integration"
    assert manifest["episode_id"] == "episode_integration"
