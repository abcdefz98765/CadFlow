from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_native_cad.agents.model_program_runtime import canonical_json_bytes, sha256_hex
from ai_native_cad.agents.wsl_sandbox import (
    _classify_launcher_failure,
    _load_runtime_manifest,
)


MANIFEST = Path(__file__).resolve().parents[1] / "sandbox" / "wsl2" / "runtime_manifest.json"


def test_repository_runtime_manifest_has_a_valid_content_digest() -> None:
    manifest = _load_runtime_manifest(MANIFEST)

    assert manifest["profile_id"] == "wsl2_cadquery_v1"
    assert manifest["distro_id"] == "CadFlow-Sandbox-CQ-v1"
    assert manifest["toolchain"]["python"].startswith("3.10.12-")
    assert manifest["toolchain"]["cadquery"] == "2.7.0"
    assert manifest["toolchain"]["cadquery_ocp"] == "7.8.1.1.post1"


def test_runtime_manifest_tamper_is_rejected(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["limits"]["memory_bytes"] += 1
    tampered = tmp_path / "runtime_manifest.json"
    tampered.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="profile digest mismatch"):
        _load_runtime_manifest(tampered)


def test_toolchain_tamper_cannot_be_hidden_by_rehashing_only_the_profile(
    tmp_path: Path,
) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["toolchain"]["cadquery"] = "99.0.0"
    unsigned = {key: value for key, value in manifest.items() if key != "profile_digest"}
    manifest["profile_digest"] = sha256_hex(canonical_json_bytes(unsigned))
    tampered = tmp_path / "runtime_manifest.json"
    tampered.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="toolchain digest mismatch"):
        _load_runtime_manifest(tampered)


@pytest.mark.parametrize(
    ("returncode", "stderr", "expected"),
    [
        (124, "", ("sandbox_timeout", "wall_clock_limit")),
        (1, "Result: timeout", ("sandbox_timeout", "wall_clock_limit")),
        (137, "", ("sandbox_resource_limit", "resource_limit")),
        (1, "OOM killed", ("sandbox_resource_limit", "resource_limit")),
        (1, "cadflow-sandbox-unit-result:timeout;code:1;status:15", ("sandbox_timeout", "wall_clock_limit")),
        (1, "cadflow-sandbox-unit-result:oom-kill;code:2;status:9", ("sandbox_resource_limit", "resource_limit")),
        (1, "Operation not permitted", ("sandbox_violation", "sandbox_violation")),
        (7, "unexpected", ("sandbox_protocol_error", "exit_7")),
    ],
)
def test_launcher_failures_are_typed(
    returncode: int,
    stderr: str,
    expected: tuple[str, str],
) -> None:
    assert _classify_launcher_failure(returncode, stderr) == expected
