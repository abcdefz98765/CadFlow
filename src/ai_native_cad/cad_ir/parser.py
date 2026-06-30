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
from ai_native_cad.planning import resolved_part_decision
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


def ir_from_planning_artifact(planning_artifact: dict[str, Any], part_name: str | None = None) -> CADIR:
    """Convert resolved Planning decisions into CAD IR.

    This function intentionally consumes only
    ``selected_parts[].resolved_decisions``. Free-form planning notes, design
    analysis, risks, and review text are gate inputs or trace metadata, not
    geometry authority.
    """

    decisions = resolved_part_decision(planning_artifact, part_name=part_name)
    source = dict(decisions.get("source", {}))
    source["planning_handoff"] = {
        "artifact_version": planning_artifact.get("version"),
        "route": planning_artifact.get("route", {}).get("selected"),
        "part_name": decisions.get("part_name"),
        "consumed_fields": [
            "part_type",
            "part_name",
            "unit",
            "dimensions",
            "features",
            "outputs",
            "check_level",
        ],
        "ignored_planning_fields": [
            "risk_notes",
            "review_targets",
            "design_analysis",
            "open_analysis_notes",
        ],
    }
    decisions["source"] = source
    return CADIR.from_dict(decisions)


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
