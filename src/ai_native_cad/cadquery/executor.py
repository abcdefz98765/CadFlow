"""Safe-ish CadQuery execution in a project output workspace."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def execute_model(code: str, output_dir: str | Path, timeout_seconds: int = 60) -> dict[str, Any]:
    """Save generated code, execute it from output_dir, and capture logs."""
    output_path = _safe_output_dir(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    logs_dir = output_path / "logs"
    logs_dir.mkdir(exist_ok=True)
    model_path = output_path / "model.py"
    model_path.write_text(code, encoding="utf-8")

    start = time.perf_counter()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(model_path)],
        cwd=output_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    elapsed = round(time.perf_counter() - start, 3)
    log = {
        "status": "success" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
        "elapsed_seconds": elapsed,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "model_path": str(model_path),
    }
    (logs_dir / "runtime.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    if proc.returncode != 0:
        (logs_dir / "error.log").write_text(proc.stderr or proc.stdout, encoding="utf-8")
    return log


def _safe_output_dir(output_dir: str | Path) -> Path:
    output_path = Path(output_dir).resolve()
    root = PROJECT_ROOT.resolve()
    try:
        output_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"output_dir must be inside project root: {root}") from exc
    return output_path
