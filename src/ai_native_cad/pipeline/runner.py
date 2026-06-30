"""IR-first CAD pipeline runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_native_cad.cad_ir.parser import ir_from_text
from ai_native_cad.cad_ir.schema import CADIR
from ai_native_cad.cad_ir.validator import validate_ir
from ai_native_cad.pipeline.agent_loop import run_agent_loop
from ai_native_cad.pipeline.report import write_pipeline_report

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def run_text_pipeline(
    text: str,
    output_root: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run Text -> CAD IR -> CAD agent loop -> STEP/STL -> validation -> report."""
    return run_ir_pipeline(ir_from_text(text, overrides), output_root=output_root, output_dir=output_dir)


def run_ir_pipeline(
    ir: CADIR | dict[str, Any],
    output_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run a complete CAD agent generation from CAD IR."""
    cad_ir = CADIR.from_dict(ir) if isinstance(ir, dict) else ir
    ir_data = cad_ir.to_dict()
    part_name = ir_data.get("part_name") or ir_data["part_type"]
    output_dir = _resolve_output_dir(part_name, output_root, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "input_ir.json").write_text(json.dumps(ir_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ir_validation = validate_ir(cad_ir)
    if not ir_validation["valid"]:
        files = _collect_files(output_dir)
        validation = {
            "valid": False,
            "execution_success": False,
            "step_generated": False,
            "stl_generated": False,
            "report_generated": False,
            "bounding_box": {},
            "volume": 0.0,
            "checks": [],
            "warnings": [],
            "errors": [{"code": "ir_invalid", "message": "CAD IR validation failed"}],
        }
        (output_dir / "agent_trace.json").write_text(json.dumps({
            "total_attempts": 0,
            "steps": [{"attempt": 0, "status": "failed", "reason": "ir_invalid"}],
            "final_selected_candidate": None,
        }, indent=2) + "\n", encoding="utf-8")
        report = write_pipeline_report(output_dir, ir_data, {"status": "not_run"}, validation, files, ir_validation=ir_validation)
        files = _collect_files(output_dir)
        return {"status": "failed", "ir": ir_data, "output_dir": str(output_dir), "validation": ir_validation, "files": files, **report}

    loop_result = run_agent_loop(cad_ir, output_dir)
    execution = loop_result["execution"]
    validation = loop_result["validation"]
    final_ir = loop_result.get("ir", ir_data)
    files = _collect_files(output_dir)
    report = write_pipeline_report(output_dir, final_ir, execution, validation, files, ir_validation=ir_validation)
    files = _collect_files(output_dir)
    status = "success" if execution["status"] == "success" and validation.get("valid") else "failed"
    return {
        "status": status,
        "ir": final_ir,
        "output_dir": str(output_dir),
        "execution": execution,
        "validation": validation,
        "agent_trace": loop_result["agent_trace"],
        "files": files,
        **report,
    }


def _collect_files(output_dir: Path) -> dict[str, str]:
    files = {}
    labels = {
        "model.py": "model_py",
        "model.step": "step",
        "model.stl": "stl",
        "preview.png": "preview",
        "report.json": "report_json",
        "report.md": "report_md",
        "agent_trace.json": "agent_trace",
    }
    for name, label in labels.items():
        path = output_dir / name
        if path.exists():
            files[label] = str(path)
    return files


def _resolve_output_dir(part_name: str, output_root: str | Path | None, output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        resolved = Path(output_dir)
        if not resolved.is_absolute():
            resolved = PROJECT_ROOT / resolved
        return _require_repo_path(resolved.resolve())

    root = Path(output_root) if output_root is not None else PROJECT_ROOT / "outputs"
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    return _require_repo_path((root / part_name).resolve())


def _require_repo_path(path: Path) -> Path:
    repo_root = PROJECT_ROOT.resolve()
    try:
        path.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(f"pipeline outputs must be written inside project root: {repo_root}") from exc
    return path
