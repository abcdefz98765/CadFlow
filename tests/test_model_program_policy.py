from __future__ import annotations

import json

import pytest

from ai_native_cad.agents import (
    CADQUERY_MODEL_PROGRAM_API,
    CADQUERY_MODEL_PROGRAM_ENTRYPOINT,
    MODEL_PROGRAM_SOURCE_TOOL,
    MODEL_PROGRAM_TOOL,
    CadFlowToolBroker,
    cadquery_model_program_policy_manifest,
    validate_cadquery_model_program_source,
)


VALID_CADQUERY_SOURCE = """\
\"\"\"Allowlisted CadQuery model program.\"\"\"

import cadquery as cq
from math import radians

DEFAULT_HEIGHT = 8.0

def build_model(parameters):
    width = float(parameters["width"])
    depth = float(parameters["depth"])
    angle = radians(float(parameters["angle_degrees"]))
    base = cq.Workplane("XY").box(width, depth, DEFAULT_HEIGHT)
    return base.faces(">Z").workplane().circle(angle + 2.0).cutThruAll()
"""


def test_cadquery_v1_policy_accepts_allowlisted_program_without_execution() -> None:
    result = validate_cadquery_model_program_source(VALID_CADQUERY_SOURCE)

    assert result["valid"] is True
    assert result["api_id"] == CADQUERY_MODEL_PROGRAM_API
    assert result["entrypoint"] == CADQUERY_MODEL_PROGRAM_ENTRYPOINT
    assert result["codes"] == []
    assert result["imports"] == ["cadquery", "math.radians"]
    assert result["executed"] is False
    assert result["side_effect_started"] is False
    assert VALID_CADQUERY_SOURCE not in json.dumps(result)


@pytest.mark.parametrize(
    ("source", "expected_code"),
    [
        (
            "import os\ndef build_model(parameters):\n    return 1\n",
            "import_not_allowed",
        ),
        (
            "import socket\ndef build_model(parameters):\n    return 1\n",
            "import_not_allowed",
        ),
        (
            "def build_model(parameters):\n    return open('secret.txt')\n",
            "dangerous_call_not_allowed",
        ),
        (
            "def build_model(parameters):\n    return eval('1 + 1')\n",
            "dangerous_call_not_allowed",
        ),
        (
            "import cadquery as cq\ndef build_model(parameters):\n"
            "    return cq.exporters.export(None, 'model.step')\n",
            "cadquery_module_not_allowed",
        ),
        (
            "def build_model(parameters):\n    return parameters.get('width')\n",
            "method_call_not_allowlisted",
        ),
        (
            "def build_model(parameters):\n    return parameters.__class__\n",
            "private_attribute_not_allowed",
        ),
        (
            "def build_model(parameters):\n    return __builtins__\n",
            "private_name_not_allowed",
        ),
        (
            "def build_model():\n    return 1\n",
            "entrypoint_signature_invalid",
        ),
        (
            "def build_model(parameters):\n    return 1\nbuild_model({})\n",
            "top_level_execution_not_allowed",
        ),
        (
            "import math\ndef build_model(parameters):\n    return math.pi()\n",
            "math_call_not_allowlisted",
        ),
        (
            "from math import pi\ndef build_model(parameters):\n    return pi()\n",
            "call_not_allowlisted",
        ),
        (
            "import cadquery as cq\ncq.exporters = 1\n"
            "def build_model(parameters):\n    return cq.Workplane('XY')\n",
            "top_level_assignment_target_not_allowed",
        ),
        (
            "def helper(value=open('x')):\n    return value\n"
            "def build_model(parameters):\n    return helper()\n",
            "function_signature_not_allowed",
        ),
        (
            "def build_model(parameters):\n"
            "    def nested():\n        return 1\n"
            "    nested()\n",
            "entrypoint_return_missing",
        ),
    ],
)
def test_cadquery_v1_policy_rejects_non_allowlisted_authority(
    source,
    expected_code,
) -> None:
    result = validate_cadquery_model_program_source(source)

    assert result["valid"] is False
    assert expected_code in result["codes"]
    assert result["executed"] is False
    assert result["side_effect_started"] is False
    assert source not in json.dumps(result)


def test_source_limits_and_syntax_fail_without_echoing_source() -> None:
    malformed = "def build_model(parameters):\n    return (\n# private-marker"
    malformed_result = validate_cadquery_model_program_source(malformed)
    oversized = "x" * 65_537
    oversized_result = validate_cadquery_model_program_source(oversized)
    invalid_unicode = "\ud800"
    unicode_result = validate_cadquery_model_program_source(invalid_unicode)

    assert malformed_result["codes"] == ["source_syntax_error"]
    assert "private-marker" not in json.dumps(malformed_result)
    assert oversized_result["codes"] == ["source_too_large"]
    assert oversized not in json.dumps(oversized_result)
    assert unicode_result["codes"] == ["source_syntax_error"]


def test_tool_broker_owns_model_program_source_validation() -> None:
    broker = CadFlowToolBroker()

    passed = broker.invoke(
        MODEL_PROGRAM_SOURCE_TOOL,
        skill_id="model_program",
        payload={
            "api_id": CADQUERY_MODEL_PROGRAM_API,
            "source": VALID_CADQUERY_SOURCE,
        },
    )
    unauthorized = broker.invoke(
        MODEL_PROGRAM_SOURCE_TOOL,
        skill_id="design_part",
        payload={
            "api_id": CADQUERY_MODEL_PROGRAM_API,
            "source": VALID_CADQUERY_SOURCE,
        },
    )

    assert passed.success is True
    assert passed.observation_type == "source_validation_passed"
    assert passed.execution_profile == "local_pure_source_validation_v1"
    assert passed.side_effect_started is False
    assert passed.output["source_retained"] is False
    assert unauthorized.codes == ("tool_not_allowed_for_skill",)


def test_source_validator_exception_is_redacted_and_typed(monkeypatch) -> None:
    def broken_validator(source):
        raise RuntimeError("secret source validator detail")

    monkeypatch.setattr(
        "ai_native_cad.agents.tool_broker.validate_cadquery_model_program_source",
        broken_validator,
    )
    observation = CadFlowToolBroker().invoke(
        MODEL_PROGRAM_SOURCE_TOOL,
        skill_id="model_program",
        payload={
            "api_id": CADQUERY_MODEL_PROGRAM_API,
            "source": VALID_CADQUERY_SOURCE,
        },
    )

    serialized = json.dumps(observation.as_dict())
    assert observation.success is False
    assert observation.codes == ("source_validation_exception",)
    assert observation.side_effect_started is False
    assert observation.output["source_retained"] is False
    assert "secret source validator detail" not in serialized
    assert VALID_CADQUERY_SOURCE not in serialized


def test_unsupported_api_and_invalid_input_are_sanitized() -> None:
    source = "secret-source-that-must-not-be-echoed"
    unsupported_api = "secret-api-id-that-must-not-be-echoed"
    broker = CadFlowToolBroker()

    unsupported = broker.invoke(
        MODEL_PROGRAM_SOURCE_TOOL,
        skill_id="model_program",
        payload={"api_id": unsupported_api, "source": source},
    )
    malformed = broker.invoke(
        MODEL_PROGRAM_SOURCE_TOOL,
        skill_id="model_program",
        payload={"api_id": CADQUERY_MODEL_PROGRAM_API, "source": source, "path": "x"},
    )

    assert unsupported.codes == ("unsupported_model_program_api",)
    assert unsupported.side_effect_started is False
    assert source not in json.dumps(unsupported.as_dict())
    assert unsupported_api not in json.dumps(unsupported.as_dict())
    assert malformed.codes == ("invalid_source_contract",)
    assert source not in json.dumps(malformed.as_dict())


def test_static_pass_does_not_enable_model_program_execution(tmp_path) -> None:
    broker = CadFlowToolBroker()
    candidate_dir = tmp_path / "must_not_exist"

    static_result = broker.invoke(
        MODEL_PROGRAM_SOURCE_TOOL,
        skill_id="model_program",
        payload={
            "api_id": CADQUERY_MODEL_PROGRAM_API,
            "source": VALID_CADQUERY_SOURCE,
        },
    )
    execution_result = broker.invoke(
        MODEL_PROGRAM_TOOL,
        skill_id="model_program",
        payload={
            "candidate_directory": str(candidate_dir),
            "source": VALID_CADQUERY_SOURCE,
        },
    )

    assert static_result.success is True
    assert execution_result.observation_type == "sandbox_unavailable"
    assert execution_result.side_effect_started is False
    assert not candidate_dir.exists()


def test_model_program_manifest_separates_static_and_execution_capabilities() -> None:
    broker = CadFlowToolBroker()
    manifest = broker.manifest(active_skill_id="model_program")
    policy = cadquery_model_program_policy_manifest()

    assert [item["tool_id"] for item in manifest["allowed_tools"]] == [
        MODEL_PROGRAM_SOURCE_TOOL,
        MODEL_PROGRAM_TOOL,
    ]
    assert manifest["model_program_capability"]["available"] is False
    assert policy["api_id"] == CADQUERY_MODEL_PROGRAM_API
    assert policy["cad_library"] == {
        "name": "CadQuery",
        "package_version": None,
        "binding_status": "pending_enforceable_worker",
    }
    assert policy["entrypoint"]["signature"] == "build_model(parameters)"
    assert "Assembly" not in policy["allowed_imports"]["cadquery"]
    assert "Color" not in policy["allowed_imports"]["cadquery"]
    assert all(value is False for value in policy["authority"].values())
