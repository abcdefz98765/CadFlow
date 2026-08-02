#!/opt/cadflow/venv/bin/python
"""Trusted worker executed only inside the CadFlow WSL2 sandbox profile."""

from __future__ import annotations

import builtins
import errno as errno_module
import io
import json
import math
import os
import resource
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
import traceback
from pathlib import Path

import cadquery as cq
import seccomp


MAX_REQUEST_BYTES = 98_304
MAX_LOG_BYTES = 262_144
MAX_OUTPUT_BYTES = 67_108_864
ALLOWED_BUILTINS = {
    name: getattr(builtins, name)
    for name in (
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "float",
        "int",
        "len",
        "list",
        "max",
        "min",
        "range",
        "round",
        "set",
        "sorted",
        "sum",
        "tuple",
        "zip",
    )
}


class CappedText(io.TextIOBase):
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._parts: list[str] = []
        self._size = 0

    def write(self, value: str) -> int:
        text = str(value)
        encoded = text.encode("utf-8", errors="replace")
        remaining = max(0, self.limit - self._size)
        if remaining:
            self._parts.append(encoded[:remaining].decode("utf-8", errors="replace"))
            self._size += min(len(encoded), remaining)
        return len(text)

    def getvalue(self) -> str:
        return "".join(self._parts)


class ModelProgramOutputError(ValueError):
    """The candidate returned or produced an invalid model output."""


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        return emit_failure("sandbox_protocol_error", "request_too_large")
    try:
        request = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return emit_failure("sandbox_protocol_error", "invalid_request_json")
    if not isinstance(request, dict):
        return emit_failure("sandbox_protocol_error", "invalid_request_shape")
    try:
        install_seccomp()
    except Exception:
        return emit_failure("sandbox_violation", "seccomp_install_failed")
    if request.get("mode") == "probe":
        return run_probe()
    return run_model(request)


def install_seccomp() -> None:
    policy = seccomp.SyscallFilter(defaction=seccomp.ALLOW)
    errno = seccomp.ERRNO(1)
    for name in (
        "bpf",
        "connect",
        "execve",
        "execveat",
        "fork",
        "keyctl",
        "listen",
        "mount",
        "open_by_handle_at",
        "perf_event_open",
        "pivot_root",
        "ptrace",
        "reboot",
        "setns",
        "socket",
        "socketpair",
        "swapoff",
        "swapon",
        "umount2",
        "unshare",
        "userfaultfd",
        "vfork",
    ):
        try:
            policy.add_rule(errno, name)
        except RuntimeError:
            pass
    # Modern glibc probes clone3 for pthreads and falls back to clone only when
    # the kernel reports ENOSYS.  Report that syscall as unavailable rather
    # than permitted; the fallback remains filtered to CLONE_THREAD below.
    policy.add_rule(seccomp.ERRNO(errno_module.ENOSYS), "clone3")
    # CadQuery/OCCT may use in-process worker threads.  Permit only clone(2)
    # calls carrying CLONE_THREAD; process-style clone, fork, vfork, and
    # clone3 remain denied, and TasksMax independently caps total threads.
    policy.add_rule(
        errno,
        "clone",
        seccomp.Arg(0, seccomp.MASKED_EQ, 0x00010000, 0),
    )
    policy.load()


def run_model(request: dict) -> int:
    expected = {
        "schema_version",
        "mode",
        "api_id",
        "candidate_id",
        "source",
        "parameters",
        "requested_outputs",
    }
    if set(request) != expected or request.get("schema_version") != 1:
        return emit_failure("sandbox_protocol_error", "invalid_request_shape")
    if request.get("api_id") != "cadquery_v1" or request.get("requested_outputs") != ["step"]:
        return emit_failure("sandbox_policy_rejected", "unsupported_execution_contract")
    source = request.get("source")
    parameters = request.get("parameters")
    if not isinstance(source, str) or not isinstance(parameters, dict):
        return emit_failure("sandbox_protocol_error", "invalid_request_shape")

    captured_out = CappedText(MAX_LOG_BYTES)
    captured_err = CappedText(MAX_LOG_BYTES)
    old_out, old_err = sys.stdout, sys.stderr
    observation: dict
    output_path: Path | None = None
    try:
        trusted_progress("candidate_start")
        sys.stdout, sys.stderr = captured_out, captured_err
        namespace = {
            "__builtins__": {**ALLOWED_BUILTINS, "__import__": safe_import},
            "__name__": "cadflow_candidate",
        }
        code = compile(source, "<cadflow-model-program>", "exec", dont_inherit=True)
        exec(code, namespace, namespace)
        trusted_progress("candidate_compiled")
        build_model = namespace.get("build_model")
        if not callable(build_model):
            raise ModelProgramOutputError("missing build_model entrypoint")
        model = build_model(json.loads(json.dumps(parameters)))
        trusted_progress("candidate_returned")
        shape = model.val() if isinstance(model, cq.Workplane) else model
        if not isinstance(shape, cq.Shape):
            raise ModelProgramOutputError("build_model returned an unsupported result")
        solids = shape.Solids()
        if not shape.isValid() or not solids:
            raise ModelProgramOutputError("build_model returned invalid or non-solid geometry")
        bounds = shape.BoundingBox()
        trusted_progress("geometry_validated")
        candidate_dir = Path(os.environ["CADFLOW_CANDIDATE_DIR"])
        output_path = candidate_dir / "model.step"
        cq.exporters.export(model, str(output_path))
        trusted_progress("step_exported")
        output_size = output_path.stat().st_size
        if output_size <= 0 or output_size > MAX_OUTPUT_BYTES:
            raise ModelProgramOutputError("STEP output violates the size contract")
        observation = {
            "schema_version": 1,
            "success": True,
            "observation_type": "model_program_execution_completed",
            "codes": [],
            "exit_state": "completed",
            "geometry": {
                "valid": True,
                "solid_count": len(solids),
                "bounding_box": {
                    "x": bounds.xlen,
                    "y": bounds.ylen,
                    "z": bounds.zlen,
                },
            },
        }
    except MemoryError as exc:
        observation = failure_observation("sandbox_resource_limit", type(exc).__name__)
    except PermissionError as exc:
        observation = failure_observation("sandbox_violation", type(exc).__name__)
    except ModelProgramOutputError as exc:
        observation = failure_observation("model_program_output_invalid", type(exc).__name__)
    except Exception as exc:
        observation = failure_observation("model_program_runtime_error", type(exc).__name__)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return emit_archive(observation, captured_out.getvalue(), captured_err.getvalue(), output_path)


def run_probe() -> int:
    results: dict[str, bool] = {}
    candidate_dir = Path(os.environ["CADFLOW_CANDIDATE_DIR"])
    protected_paths = ("/mnt/c", "/mnt/d", "/run/WSL", "/run/desktop")
    allowed_environment = {
        "CADFLOW_CANDIDATE_DIR",
        "HOME",
        "LANG",
        "PATH",
        "SYSTEMD_EXEC_PID",
        "INVOCATION_ID",
        "LOGNAME",
        "USER",
    }
    results["candidate_directory_writable"] = _can_write(candidate_dir / "probe.txt")
    results["directory_escape_denied"] = not _can_write(
        candidate_dir.parent / "cadflow-provider-escape"
    )
    results["symlink_escape_denied"] = _symlink_escape_denied(candidate_dir)
    results["root_filesystem_read_only"] = not _can_write(Path("/etc/cadflow-provider-write"))
    visible_host_paths = [path for path in protected_paths if not _path_is_hidden(Path(path))]
    unexpected_environment = sorted(set(os.environ) - allowed_environment)
    results["windows_mounts_hidden"] = not visible_host_paths
    results["environment_allowlisted"] = (
        not unexpected_environment and _environment_values_are_controlled()
    )
    results["network_socket_denied"] = _raises_permission(lambda: socket.socket())
    results["subprocess_denied"] = _raises_permission(
        lambda: subprocess.run(["/bin/true"], check=False)
    )
    results["shell_denied"] = _raises_permission(
        lambda: subprocess.run("true", shell=True, check=False)
    )
    results["dynamic_install_denied"] = _raises_permission(
        lambda: subprocess.run(
            ["/opt/cadflow/venv/bin/python", "-m", "pip", "--version"],
            check=False,
        )
    )
    results["fork_denied"] = _raises_permission(os.fork)
    results["no_new_privileges"] = _status_value("NoNewPrivs") == "1"
    results["cpu_limit"] = resource.getrlimit(resource.RLIMIT_CPU)[0] <= 20
    results["output_limit"] = resource.getrlimit(resource.RLIMIT_FSIZE)[0] <= MAX_OUTPUT_BYTES
    results["memory_limit"] = _cgroup_number("memory.max") <= 1_073_741_824
    results["swap_disabled"] = _cgroup_number("memory.swap.max") == 0
    results["process_limit"] = _cgroup_number("pids.max") <= 64
    results["private_network"] = not _has_default_route()
    observation = {
        "schema_version": 1,
        "success": all(results.values()),
        "observation_type": "sandbox_profile_probe",
        "codes": [] if all(results.values()) else ["sandbox_attestation_failed"],
        "exit_state": "completed",
        "probe_results": results,
        "probe_diagnostics": {
            "visible_host_paths": visible_host_paths,
            "unexpected_environment_names": unexpected_environment,
        },
    }
    return emit_archive(observation, "", "", None)


def safe_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
    if level != 0 or name not in {"cadquery", "math"}:
        raise ImportError("module is not available in cadquery_v1")
    return cq if name == "cadquery" else math


def trusted_progress(stage: str) -> None:
    os.write(2, f"cadflow-worker-stage:{stage}\n".encode("ascii"))


def emit_failure(code: str, detail: str) -> int:
    return emit_archive(failure_observation(code, detail), "", "", None)


def failure_observation(code: str, detail: str) -> dict:
    return {
        "schema_version": 1,
        "success": False,
        "observation_type": "model_program_execution_failed",
        "codes": [code],
        "exit_state": "failed",
        "sanitized_detail": detail[:80],
    }


def emit_archive(observation: dict, stdout: str, stderr: str, output_path: Path | None) -> int:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        _add_bytes(archive, "observation.json", json.dumps(observation, sort_keys=True).encode("utf-8"))
        _add_bytes(archive, "stdout.txt", stdout.encode("utf-8", errors="replace")[:MAX_LOG_BYTES])
        _add_bytes(archive, "stderr.txt", stderr.encode("utf-8", errors="replace")[:MAX_LOG_BYTES])
        if output_path is not None and output_path.is_file() and observation.get("success") is True:
            info = tarfile.TarInfo("model.step")
            info.size = output_path.stat().st_size
            info.mode = 0o600
            with output_path.open("rb") as handle:
                archive.addfile(info, handle)
    sys.stdout.buffer.write(stream.getvalue())
    sys.stdout.buffer.flush()
    return 0


def _add_bytes(archive: tarfile.TarFile, name: str, value: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(value)
    info.mode = 0o600
    archive.addfile(info, io.BytesIO(value))


def _can_write(path: Path) -> bool:
    try:
        path.write_bytes(b"probe")
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _raises_permission(action) -> bool:
    try:
        action()
    except (OSError, PermissionError):
        return True
    return False


def _symlink_escape_denied(candidate_dir: Path) -> bool:
    link = candidate_dir / "escape-link"
    target = Path("/etc/cadflow-provider-write")
    try:
        link.symlink_to(target)
        escaped = _can_write(link)
        if escaped:
            target.unlink(missing_ok=True)
        return not escaped
    except OSError:
        return True
    finally:
        link.unlink(missing_ok=True)


def _path_is_hidden(path: Path) -> bool:
    try:
        if not path.exists():
            return True
        if path.is_dir():
            return not any(path.iterdir())
        return False
    except OSError:
        return True


def _environment_values_are_controlled() -> bool:
    invocation_id = os.environ.get("INVOCATION_ID", "")
    systemd_pid = os.environ.get("SYSTEMD_EXEC_PID", "")
    return (
        os.environ.get("USER") == "cadflow-worker"
        and os.environ.get("LOGNAME") == "cadflow-worker"
        and os.environ.get("HOME") == os.environ.get("CADFLOW_CANDIDATE_DIR")
        and os.environ.get("LANG") == "C.UTF-8"
        and os.environ.get("PATH") == "/opt/cadflow/venv/bin:/usr/bin"
        and re.fullmatch(r"[0-9a-f]{32}", invocation_id) is not None
        and systemd_pid.isdigit()
    )


def _status_value(name: str) -> str:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}:"):
            return line.split(":", 1)[1].strip()
    return ""


def _cgroup_number(name: str) -> int:
    relative = ""
    for line in Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines():
        if line.startswith("0::"):
            relative = line.split("::", 1)[1].lstrip("/")
            break
    value = (Path("/sys/fs/cgroup") / relative / name).read_text(encoding="utf-8").strip()
    return 2**63 - 1 if value == "max" else int(value)


def _has_default_route() -> bool:
    lines = Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]
    return any(line.split()[1] == "00000000" for line in lines if line.split())


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        raise
    raise SystemExit(exit_code)
