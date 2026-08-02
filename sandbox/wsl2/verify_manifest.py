"""Verify the repository-owned WSL2 runtime manifest without modifying it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INSTALLED_SOURCE = {
    "/opt/cadflow/worker.py": ROOT / "worker.py",
    "/opt/cadflow/probe.py": ROOT / "probe.py",
    "/opt/cadflow/bin/cadflow-sandbox-launch": ROOT / "cadflow-sandbox-launch",
    "/opt/cadflow/requirements-cp310.lock": ROOT / "requirements-cp310.lock",
    "/etc/wsl.conf": ROOT / "wsl.conf",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    manifest = json.loads((ROOT / "runtime_manifest.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    for installed_path, source_path in INSTALLED_SOURCE.items():
        actual = sha256(source_path)
        if manifest["installed_files"].get(installed_path) != actual:
            failures.append(f"installed file hash mismatch: {installed_path} expected {actual}")
    lock_hash = sha256(ROOT / "requirements-cp310.lock")
    if manifest["toolchain"].get("wheel_lock_sha256") != lock_hash:
        failures.append(f"wheel lock hash mismatch: expected {lock_hash}")
    toolchain_digest = canonical_digest(manifest["toolchain"])
    if manifest.get("toolchain_digest") != toolchain_digest:
        failures.append(f"toolchain digest mismatch: expected {toolchain_digest}")
    unsigned = {key: value for key, value in manifest.items() if key != "profile_digest"}
    profile_digest = canonical_digest(unsigned)
    if manifest.get("profile_digest") != profile_digest:
        failures.append(f"profile digest mismatch: expected {profile_digest}")
    if failures:
        print("\n".join(failures))
        return 1
    print(f"profile_digest={profile_digest}")
    print(f"toolchain_digest={toolchain_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
