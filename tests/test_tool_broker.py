from __future__ import annotations

import json

import pytest

from ai_native_cad.agents import (
    MODEL_PROGRAM_TOOL,
    REQUIRED_MODEL_PROGRAM_CONTROLS,
    STRUCTURED_CONTRACT_TOOL,
    CadFlowToolBroker,
    SandboxCapability,
    detect_model_program_sandbox_capability,
)


def _valid_contract() -> dict:
    return {
        "part_type": "spacer",
        "part_name": "broker_spacer",
        "unit": "mm",
        "dimensions": {
            "outer_diameter": 12,
            "inner_diameter": 5,
            "thickness": 8,
        },
        "features": {},
        "outputs": ["step", "stl"],
        "check_level": "L0",
    }


def test_tool_broker_owns_structured_contract_validation() -> None:
    broker = CadFlowToolBroker()

    observation = broker.invoke(
        STRUCTURED_CONTRACT_TOOL,
        skill_id="design_part",
        payload={
            "contract_type": "cad_ir_draft",
            "contract": _valid_contract(),
        },
    )

    assert observation.success is True
    assert observation.observation_type == "contract_validation_passed"
    assert observation.execution_profile == "local_pure_validation_v1"
    assert observation.side_effect_started is False
    assert observation.output["valid"] is True


def test_tool_broker_rejects_skill_input_and_execution_bypass() -> None:
    broker = CadFlowToolBroker()

    unauthorized = broker.invoke(
        STRUCTURED_CONTRACT_TOOL,
        skill_id="model_program",
        payload={
            "contract_type": "cad_ir_draft",
            "contract": _valid_contract(),
        },
    )
    assert unauthorized.codes == ("tool_not_allowed_for_skill",)
    assert unauthorized.side_effect_started is False

    malformed = broker.invoke(
        STRUCTURED_CONTRACT_TOOL,
        skill_id="design_part",
        payload={"contract": _valid_contract()},
    )
    assert malformed.codes == ("invalid_contract_shape",)

    forbidden_contract = {**_valid_contract(), "python_code": "open('x', 'w')"}
    forbidden = broker.invoke(
        STRUCTURED_CONTRACT_TOOL,
        skill_id="design_part",
        payload={
            "contract_type": "cad_ir_draft",
            "contract": forbidden_contract,
        },
    )
    assert forbidden.codes == ("forbidden_execution_field",)
    assert "open('x', 'w')" not in json.dumps(forbidden.as_dict())


def test_validator_exception_is_redacted_and_typed() -> None:
    def broken_validator(contract):
        raise RuntimeError("secret validator detail")

    broker = CadFlowToolBroker(structured_contract_validator=broken_validator)
    observation = broker.invoke(
        STRUCTURED_CONTRACT_TOOL,
        skill_id="design_part",
        payload={
            "contract_type": "cad_ir_draft",
            "contract": _valid_contract(),
        },
    )

    serialized = json.dumps(observation.as_dict())
    assert observation.success is False
    assert observation.codes == ("validation_exception",)
    assert "secret validator detail" not in serialized


def test_windows_model_program_capability_is_explicitly_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "ai_native_cad.agents.wsl_sandbox.platform.system",
        lambda: "Windows",
    )
    monkeypatch.delenv("CADFLOW_MODEL_PROGRAM_SANDBOX", raising=False)

    capability = detect_model_program_sandbox_capability()

    assert capability.platform == "Windows"
    assert capability.available is False
    assert capability.enforced_controls == frozenset()
    assert capability.missing_controls == REQUIRED_MODEL_PROGRAM_CONTROLS
    assert capability.reason_codes == (
        "sandbox_unavailable",
        "sandbox_runtime_not_enabled",
    )


def test_model_program_request_fails_before_source_or_process_side_effect(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("CADFLOW_MODEL_PROGRAM_SANDBOX", raising=False)
    broker = CadFlowToolBroker()
    candidate_dir = tmp_path / "must_not_be_created"
    source = "import socket\nopen('../escape.txt', 'w').write('bad')"

    observation = broker.invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload={
            "candidate_directory": str(candidate_dir),
            "source": source,
        },
    )

    assert observation.success is False
    assert observation.observation_type == "sandbox_unavailable"
    assert observation.codes == ("sandbox_unavailable",)
    assert observation.side_effect_started is False
    assert not candidate_dir.exists()
    assert source not in json.dumps(observation.as_dict())


def test_available_sandbox_claim_requires_all_controls_and_evidence() -> None:
    with pytest.raises(ValueError, match="missing controls"):
        SandboxCapability(
            profile_id="unsafe_fixture",
            platform="Windows",
            available=True,
            enforced_controls=frozenset({"network_disabled"}),
            missing_controls=frozenset(),
            reason_codes=(),
            evidence=("fixture",),
        )
    with pytest.raises(ValueError, match="typed reason"):
        SandboxCapability(
            profile_id="untyped_unavailable_fixture",
            platform="Windows",
            available=False,
            enforced_controls=frozenset(),
            missing_controls=REQUIRED_MODEL_PROGRAM_CONTROLS,
            reason_codes=(),
        )

    with pytest.raises(ValueError, match="enforcement evidence"):
        SandboxCapability(
            profile_id="unevidenced_fixture",
            platform="Windows",
            available=True,
            enforced_controls=REQUIRED_MODEL_PROGRAM_CONTROLS,
            missing_controls=frozenset(),
            reason_codes=(),
        )

    with pytest.raises(ValueError, match="attestation"):
        SandboxCapability(
            profile_id="unattested_fixture",
            platform="Windows",
            available=True,
            enforced_controls=REQUIRED_MODEL_PROGRAM_CONTROLS,
            missing_controls=frozenset(),
            reason_codes=(),
            evidence=("fixture",),
        )


def test_injected_available_capability_cannot_unlock_execution(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CADFLOW_MODEL_PROGRAM_SANDBOX", raising=False)
    injected = SandboxCapability(
        profile_id="wsl2_cadquery_v1",
        platform="Windows/WSL2",
        available=True,
        enforced_controls=REQUIRED_MODEL_PROGRAM_CONTROLS,
        missing_controls=frozenset(),
        reason_codes=(),
        evidence=("caller-claim",),
        attestation_digest="caller-attestation",
        profile_digest="caller-profile",
        toolchain_digest="caller-toolchain",
    )
    broker = CadFlowToolBroker(sandbox_capability=injected)

    capability = broker.capability(MODEL_PROGRAM_TOOL)["capability"]
    observation = broker.invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload={"source": "provider text"},
    )

    assert capability["available"] is False
    assert observation.codes == ("sandbox_unavailable",)
    assert observation.side_effect_started is False
    assert not list(tmp_path.iterdir())


def test_design_part_manifest_exposes_only_validation_tool(monkeypatch) -> None:
    monkeypatch.delenv("CADFLOW_MODEL_PROGRAM_SANDBOX", raising=False)
    manifest = CadFlowToolBroker().manifest(active_skill_id="design_part")

    assert manifest["broker"] == "cadflow_tool_broker"
    assert [item["tool_id"] for item in manifest["allowed_tools"]] == [
        STRUCTURED_CONTRACT_TOOL
    ]
    assert manifest["model_program_capability"]["available"] is False
