"""Script runner — loads and executes a model-building function."""

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"
PART_EXAMPLES_DIR = EXAMPLES_DIR / "parts"


def load_builder(part_type: str) -> Callable:
    """Load the build_model function from the example module for given part type."""
    module_path = _find_example_model(part_type)
    if not module_path.exists():
        raise FileNotFoundError(f"Example module not found: {module_path}")

    spec = importlib.util.spec_from_file_location(part_type, str(module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[part_type] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "build_model"):
        raise AttributeError(f"Module {part_type} has no build_model function")
    return module.build_model


def _find_example_model(part_type: str) -> Path:
    """Find a part example in standalone parts or assembly component folders."""
    candidates = [
        PART_EXAMPLES_DIR / part_type / "model.py",
        EXAMPLES_DIR / part_type / "model.py",
    ]
    candidates.extend(EXAMPLES_DIR.glob(f"assemblies/*/parts/{part_type}/model.py"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return PART_EXAMPLES_DIR / part_type / "model.py"


def run_part(part_type: str, params: dict) -> dict:
    """Run a part pipeline: build → export → report.

    Returns a dict with status, model, files, elapsed, and errors.
    """
    start = time.perf_counter()
    result = {"part_type": part_type, "params": params}

    try:
        module_path = _find_example_model(part_type)
        builder = load_builder(part_type)
        model = builder(params)
        result["model"] = model

        # Export
        from .exporter import export_model

        configured_output_root = params.get("output_dir")
        output_root = PROJECT_ROOT / configured_output_root if configured_output_root else None
        instance_name = params.get("instance_name", part_type)
        output_dir = _output_dir_for_example(module_path, output_root, instance_name)
        result["output_dir"] = str(output_dir)
        files = export_model(model, output_dir, params.get("outputs", ["step", "stl"]))
        result["files"] = files

        # Validate
        from .validator import validate_output

        validation = validate_output(model, output_dir, params)
        result["validation"] = validation

        # Report
        from .report import generate_report

        report = generate_report(model, params, files, validation, time.perf_counter() - start, output_dir)
        result["report"] = report["report_json"]
        result["report_md"] = report["report_md"]

        result["status"] = "success" if validation.get("valid") else "failed"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    result["elapsed"] = round(time.perf_counter() - start, 2)
    return result


def output_dir_for_part(part_type: str, output_root: str | Path | None = None, instance_name: str | None = None) -> Path:
    """Return the default output directory that mirrors the example path."""
    root = None if output_root is None else Path(output_root)
    module_path = _find_example_model(part_type)
    return _output_dir_for_example(module_path, root, instance_name or part_type)


def _output_dir_for_example(module_path: Path, output_root: Path | None, instance_name: str) -> Path:
    if output_root is None:
        if instance_name != module_path.parent.name:
            return module_path.parent.parent / instance_name
        return module_path.parent
    try:
        rel_dir = module_path.parent.relative_to(EXAMPLES_DIR)
    except ValueError:
        return output_root / instance_name
    if instance_name != module_path.parent.name:
        rel_dir = rel_dir.parent / instance_name
    return output_root / rel_dir
