"""IR-first CAD pipeline runner."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from ai_native_cad.cad_ir.parser import ir_from_text
from ai_native_cad.cad_ir.schema import CADIR
from ai_native_cad.cad_ir.validator import validate_ir
from ai_native_cad.cadquery.executor import execute_model
from ai_native_cad.cadquery.generator import generate_cadquery_code
from ai_native_cad.pipeline.report import write_pipeline_report
from ai_native_cad.validator import validate_output

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def run_text_pipeline(text: str, output_root: str | Path | None = None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run Text -> CAD IR -> CadQuery -> STEP/STL -> validation -> report."""
    return run_ir_pipeline(ir_from_text(text, overrides), output_root=output_root)


def run_ir_pipeline(ir: CADIR | dict[str, Any], output_root: str | Path | None = None) -> dict[str, Any]:
    """Run a complete deterministic generation from CAD IR."""
    cad_ir = CADIR.from_dict(ir) if isinstance(ir, dict) else ir
    ir_data = cad_ir.to_dict()
    part_name = ir_data.get("part_name") or ir_data["part_type"]
    root = Path(output_root) if output_root is not None else PROJECT_ROOT / "outputs"
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    output_dir = root / part_name
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "input_ir.json").write_text(json.dumps(ir_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ir_validation = validate_ir(cad_ir)
    if not ir_validation["valid"]:
        files = _collect_files(output_dir)
        report = write_pipeline_report(output_dir, ir_data, {"status": "not_run"}, ir_validation, files)
        return {"status": "failed", "ir": ir_data, "output_dir": str(output_dir), "validation": ir_validation, "files": files, **report}

    code = generate_cadquery_code(cad_ir)
    execution = execute_model(code, output_dir)
    model = _load_generated_model(output_dir / "model.py", ir_data) if execution["status"] == "success" else None
    validation = validate_output(model, output_dir, ir_data) if model is not None else _execution_failed_validation(execution)
    files = _collect_files(output_dir)
    report = write_pipeline_report(output_dir, ir_data, execution, validation, files)
    files = _collect_files(output_dir)
    status = "success" if execution["status"] == "success" and validation.get("valid") else "failed"
    return {
        "status": status,
        "ir": ir_data,
        "output_dir": str(output_dir),
        "execution": execution,
        "validation": validation,
        "files": files,
        **report,
    }


def _load_generated_model(model_path: Path, ir_data: dict[str, Any]) -> Any:
    spec = importlib.util.spec_from_file_location(f"generated_{ir_data['part_name']}", model_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load generated model: {model_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_model(ir_data)


def _collect_files(output_dir: Path) -> dict[str, str]:
    files = {}
    labels = {
        "model.py": "model_py",
        "model.step": "step",
        "model.stl": "stl",
        "preview.png": "preview",
        "report.json": "report_json",
        "report.md": "report_md",
    }
    for name, label in labels.items():
        path = output_dir / name
        if path.exists():
            files[label] = str(path)
    return files


def _execution_failed_validation(execution: dict[str, Any]) -> dict[str, Any]:
    return {
        "valid": False,
        "checks": [{"check": "cadquery_execution_success", "pass": False}],
        "warnings": [],
        "errors": [{"code": "cadquery_execution_failed", "message": execution.get("stderr") or "CadQuery execution failed"}],
    }
