"""Run the current-host acceptance for the internal WSL2 execution primitive."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ai_native_cad.agents import (
    MODEL_PROGRAM_TOOL,
    CadFlowToolBroker,
    ToolInvocationContext,
)
from ai_native_cad.agents.wsl_sandbox import load_configured_wsl_sandbox_executor


SOURCE = """import cadquery as cq

def build_model(parameters):
    body = cq.Workplane("XY").polygon(6, float(parameters["diameter"])).extrude(
        float(parameters["height"])
    )
    return body.faces(">Z").workplane().hole(float(parameters["bore"]))
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_version() -> str:
    completed = subprocess.run(
        ["wsl.exe", "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )
    raw = completed.stdout
    encoding = "utf-16-le" if b"\x00" in raw else "utf-8"
    return " ".join(raw.decode(encoding, errors="replace").split())


def main() -> int:
    executor, reasons, _ = load_configured_wsl_sandbox_executor()
    if executor is None:
        raise RuntimeError(f"attested sandbox unavailable: {','.join(reasons)}")
    with tempfile.TemporaryDirectory(prefix="cadflow-wsl-acceptance-") as temporary:
        root = Path(temporary).resolve()
        accepted_pointer = root / "accepted-result.json"
        deliverable = root / "deliverable-package.json"
        accepted_pointer.write_text('{"accepted":"prior"}\n', encoding="utf-8")
        deliverable.write_text('{"source":"accepted-only"}\n', encoding="utf-8")
        prior_hashes = (sha256(accepted_pointer), sha256(deliverable))
        observation = CadFlowToolBroker(sandbox_executor=executor).invoke(
            MODEL_PROGRAM_TOOL,
            skill_id="model_program",
            payload={
                "api_id": "cadquery_v1",
                "candidate_id": "acceptance_hex_bore",
                "source": SOURCE,
                "parameters": {"diameter": 42.0, "height": 8.0, "bore": 9.0},
                "requested_outputs": ["step"],
            },
            context=ToolInvocationContext(
                work_id="work_acceptance",
                run_id="run_acceptance",
                part_job_id="part_acceptance",
                episode_id="episode_acceptance",
                evidence_root=root,
            ),
        )
        if not observation.success:
            raise RuntimeError(f"execution failed: {observation.codes}/{observation.exit_state}")
        evidence_path = root / observation.output["evidence_manifest"]
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        step_path = root / observation.output["outputs"][0]["relative_path"]
        result = {
            "schema_version": 1,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "host": {
                "platform": platform.platform(),
                "wsl": wsl_version(),
            },
            "profile": {
                "profile_id": executor.attestation.profile_id,
                "distro_id": executor.attestation.distro_id,
                "profile_digest": executor.attestation.profile_digest,
                "toolchain_digest": executor.attestation.toolchain_digest,
                "attestation_digest": executor.attestation.digest,
            },
            "attack_probes": dict(executor.attestation.probe_results),
            "execution": {
                "execution_id": observation.execution_id,
                "source_hash": observation.output["source_hash"],
                "parameters_hash": observation.output["parameters_hash"],
                "step_sha256": sha256(step_path),
                "step_size": step_path.stat().st_size,
                "geometry": observation.output["geometry"],
            },
            "lineage": {
                key: evidence[key]
                for key in ("work_id", "run_id", "part_job_id", "episode_id", "candidate_id")
            },
            "trust_invariants": {
                "reviewable": observation.output["reviewable"],
                "accepted": observation.output["accepted"],
                "deliverable": observation.output["deliverable"],
                "accepted_pointer_unchanged": sha256(accepted_pointer) == prior_hashes[0],
                "deliverable_package_unchanged": sha256(deliverable) == prior_hashes[1],
            },
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
