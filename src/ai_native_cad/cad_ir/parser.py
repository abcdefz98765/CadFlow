"""Parse text or files into CAD IR.

The natural-language path is deterministic for now: text is parsed by the
existing requirement agent and normalized into the IR contract. JSON files are
accepted directly. YAML is intentionally limited to JSON-compatible YAML unless
PyYAML is installed in the caller's environment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_native_cad.cad_ir.schema import CADIR
from ai_native_cad.generator import merge_params
from ai_native_cad.requirements import RequirementAgent


def ir_from_text(text: str, overrides: dict[str, Any] | None = None) -> CADIR:
    """Convert natural language to CAD IR through the deterministic parser."""
    requirement = RequirementAgent().parse(text, overrides)
    return CADIR.from_dict(requirement)


def ir_from_file(path: str | Path, overrides: dict[str, Any] | None = None) -> CADIR:
    """Load CAD IR from a JSON/YAML file."""
    path = Path(path)
    data = _load_structured_file(path)
    if overrides:
        data = merge_params(data, overrides)
    return CADIR.from_dict(data)


def _load_structured_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml  # type: ignore
    except ImportError:
        return json.loads(text)
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected object at top level in {path}")
    return loaded
