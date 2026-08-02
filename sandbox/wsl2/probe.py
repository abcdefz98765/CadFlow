#!/opt/cadflow/venv/bin/python
"""Return an attestation only after the sealed profile passes active probes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import platform
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_CONTROLS = {
    "dedicated_writable_candidate_directory",
    "read_only_declared_inputs",
    "environment_allowlist",
    "filesystem_boundary_enforced",
    "network_disabled",
    "subprocess_and_shell_blocked",
    "dynamic_dependency_installation_blocked",
    "cpu_limit",
    "memory_limit",
    "wall_clock_limit",
    "process_count_limit",
    "output_size_limit",
    "generated_file_allowlist",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", required=True)
    parser.parse_args()
    expected = json.loads(sys.stdin.buffer.read(4096).decode("utf-8"))
    manifest = json.loads(Path("/opt/cadflow/runtime_manifest.json").read_text(encoding="utf-8"))
    if expected.get("profile_digest") != manifest.get("profile_digest"):
        return 20
    if expected.get("toolchain_digest") != manifest.get("toolchain_digest"):
        return 21
    if not verify_files(manifest):
        return 22
    if not verify_toolchain(manifest):
        return 27
    if not verify_wsl_configuration():
        return 23
    completed = subprocess.run(
        ["/opt/cadflow/bin/cadflow-sandbox-launch"],
        input=json.dumps({"schema_version": 1, "mode": "probe"}).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
    )
    if completed.returncode != 0:
        return 24
    observation = read_observation(completed.stdout)
    probes = observation.get("probe_results")
    if observation.get("success") is not True or not isinstance(probes, dict):
        return 25
    if not all(value is True for value in probes.values()):
        return 26
    attestation = {
        "schema_version": 1,
        "profile_id": manifest["profile_id"],
        "platform": "Windows/WSL2",
        "distro_id": manifest["distro_id"],
        "profile_digest": manifest["profile_digest"],
        "toolchain_digest": manifest["toolchain_digest"],
        "enforced_controls": sorted(REQUIRED_CONTROLS),
        "probe_results": probes,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    attestation["attestation_digest"] = sha256_json(attestation)
    sys.stdout.write(json.dumps(attestation, sort_keys=True))
    return 0


def verify_files(manifest: dict) -> bool:
    for path, expected in manifest.get("installed_files", {}).items():
        candidate = Path(path)
        if not candidate.is_file():
            return False
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            return False
    return True


def verify_wsl_configuration() -> bool:
    text = Path("/etc/wsl.conf").read_text(encoding="utf-8").replace(" ", "").lower()
    return (
        "[automount]" in text
        and "enabled=false" in text
        and "[interop]" in text
        and text.count("enabled=false") >= 2
        and "appendwindowspath=false" in text
        and "systemd=true" in text
        and host_drive_mounts_absent()
    )


def verify_toolchain(manifest: dict) -> bool:
    toolchain = manifest.get("toolchain")
    if not isinstance(toolchain, dict):
        return False
    if sha256_json(toolchain) != manifest.get("toolchain_digest"):
        return False
    if platform.python_version() != "3.10.12":
        return False
    package_versions = {
        "python3.10": toolchain.get("python"),
        "python3-seccomp": toolchain.get("python3_seccomp"),
        "systemd": toolchain.get("systemd"),
        "libgl1": toolchain.get("libgl1"),
        "libxrender1": toolchain.get("libxrender1"),
        "libsm6": toolchain.get("libsm6"),
    }
    for package, expected in package_versions.items():
        completed = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", package],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        )
        if completed.returncode != 0 or completed.stdout.decode("utf-8") != expected:
            return False
    lock = Path("/opt/cadflow/requirements-cp310.lock").read_text(encoding="utf-8")
    for line in lock.splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s]+)", line)
        if match and importlib.metadata.version(match.group(1)) != match.group(2):
            return False
    return True


def host_drive_mounts_absent() -> bool:
    mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    for path in (Path("/mnt/c"), Path("/mnt/d")):
        if f" {path} " in mountinfo or path.is_symlink():
            return False
        try:
            if path.exists() and (not path.is_dir() or any(path.iterdir())):
                return False
        except OSError:
            return False
    return True


def read_observation(archive_bytes: bytes) -> dict:
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        member = archive.getmember("observation.json")
        handle = archive.extractfile(member)
        if handle is None:
            raise ValueError("probe observation missing")
        value = json.loads(handle.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("probe observation invalid")
    return value


def sha256_json(value: dict) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
