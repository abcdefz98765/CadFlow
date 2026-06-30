"""Compatibility runner routed through the IR-first CAD pipeline."""

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
    """Run a part pipeline through CAD IR.

    Legacy callers still pass ``part_type`` and params, but generation is now:
    part spec -> CAD IR -> deterministic CadQuery code -> STEP/STL -> validation.
    """
    start = time.perf_counter()
    result = {"part_type": part_type, "params": params}

    try:
        from .cad_ir.schema import CADIR
        from .cad_ir.validator import SUPPORTED_PART_TYPES
        from .pipeline.runner import run_ir_pipeline

        if part_type not in SUPPORTED_PART_TYPES:
            raise ValueError(f"Unsupported IR part_type: {part_type}")

        ir = dict(params)
        ir["part_type"] = part_type
        ir.setdefault("part_name", params.get("instance_name", part_type))
        ir.setdefault("unit", "mm")
        ir.setdefault("features", {})
        ir.setdefault("outputs", ["step", "stl"])
        pipeline_result = run_ir_pipeline(CADIR.from_dict(ir), output_root=PROJECT_ROOT / "outputs")
        result.update(pipeline_result)

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    result["elapsed"] = round(time.perf_counter() - start, 2)
    return result


def output_dir_for_part(part_type: str, output_root: str | Path | None = None, instance_name: str | None = None) -> Path:
    """Return the IR pipeline output directory for a part."""
    root = PROJECT_ROOT / "outputs" if output_root is None else Path(output_root)
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    return root / (instance_name or part_type)


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
