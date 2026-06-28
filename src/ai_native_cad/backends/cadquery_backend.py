"""CadQuery backend adapter.

This keeps the workflow layer backend-agnostic while reusing the existing MVP
runner/exporter/validator implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_native_cad.exporter import export_model
from ai_native_cad.runner import load_builder
from ai_native_cad.validator import validate_output

from .base import ModelArtifact


class CadQueryBackend:
    """Build, validate, and export models with the current CadQuery examples."""

    name = "cadquery"

    def build_model(self, requirement: dict[str, Any]) -> ModelArtifact:
        part_type = requirement["part_type"]
        builder = load_builder(part_type)
        return ModelArtifact(model=builder(requirement), backend=self.name, source_part_type=part_type)

    def export_model(self, artifact: ModelArtifact, output_dir: Path, formats: list[str]) -> dict[str, str]:
        return export_model(artifact.model, output_dir, formats)

    def validate_model(self, artifact: ModelArtifact, output_dir: Path, requirement: dict[str, Any]) -> dict[str, Any]:
        return validate_output(artifact.model, output_dir, requirement)
