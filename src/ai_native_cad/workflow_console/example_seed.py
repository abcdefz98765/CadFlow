"""Static example Work seeding for the local Workflow Console."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_native_cad.workflow_console.backend import WORKSPACE_SCHEMA_VERSION, _write_json

EXAMPLE_TEMPLATE = Path("examples") / "workflow_console" / "example_works.json"


def seed_example_works(backend: Any) -> dict[str, Any]:
    """Copy path-independent example Works into the active workspace."""
    template = _load_template(backend)
    examples = template.get("examples") if isinstance(template.get("examples"), list) else []
    if not examples:
        raise ValueError("workflow console example template has no examples")

    works_root = backend._resolve_workspace_path("works")
    runs_root = backend._resolve_workspace_path("runs")
    planned = [_validate_example(example) for example in examples]
    conflicts = [
        work["work_id"]
        for work, _runs in planned
        if backend._require_child_path(works_root, work["work_id"]).exists()
    ]
    if conflicts:
        raise FileExistsError(f"workflow console example Work already exists: {', '.join(conflicts)}")

    seeded = []
    for manifest, runs in planned:
        work_dir = backend._require_child_path(works_root, manifest["work_id"])
        work_dir.mkdir(parents=True, exist_ok=False)
        _write_json(backend._require_child_path(work_dir, "work_manifest.json"), manifest)
        for run in runs:
            run_dir = backend._require_child_path(runs_root, run["run_id"])
            run_dir.mkdir(parents=True, exist_ok=False)
            for file_spec in run["files"]:
                target = _safe_file_path(backend, run_dir, file_spec["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                if "json" in file_spec:
                    _write_json(target, file_spec["json"])
                else:
                    target.write_text(str(file_spec.get("text") or ""), encoding="utf-8")
        seeded.append(manifest["work_id"])
    backend.invalidate_work_index()
    return {
        "examples": {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "seeded_work_ids": seeded,
            "count": len(seeded),
        }
    }


def _load_template(backend: Any) -> dict[str, Any]:
    path = _template_path(backend)
    if path is None:
        raise FileNotFoundError("workflow console example template not found")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("workflow console example template must be a JSON object")
    return value


def _template_path(backend: Any) -> Path | None:
    candidates = [
        backend.project_root / EXAMPLE_TEMPLATE,
        Path(__file__).resolve().parents[3] / EXAMPLE_TEMPLATE,
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _validate_example(example: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(example, dict):
        raise ValueError("workflow console example entry must be a JSON object")
    manifest = example.get("work_manifest")
    runs = example.get("runs")
    if not isinstance(manifest, dict) or not isinstance(runs, list):
        raise ValueError("workflow console example entry requires work_manifest and runs")
    work_id = manifest.get("work_id")
    if not isinstance(work_id, str) or not work_id:
        raise ValueError("workflow console example work_id is required")
    if manifest.get("schema_version") != 1:
        raise ValueError(f"workflow console example manifest schema is unsupported: {work_id}")
    safe_runs = []
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("run_id"), str):
            raise ValueError(f"workflow console example run_id is required: {work_id}")
        files = run.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError(f"workflow console example run has no files: {run.get('run_id')}")
        for file_spec in files:
            if not isinstance(file_spec, dict) or not isinstance(file_spec.get("path"), str):
                raise ValueError(f"workflow console example file path is required: {run.get('run_id')}")
            if ("json" in file_spec) == ("text" in file_spec):
                raise ValueError(f"workflow console example file must contain exactly one content field: {file_spec.get('path')}")
        safe_runs.append(run)
    return manifest, safe_runs


def _safe_file_path(backend: Any, run_dir: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"workflow console example file path is unsafe: {relative_path}")
    return backend._require_child_path(run_dir, path)
