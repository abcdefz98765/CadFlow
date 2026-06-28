"""Backend-neutral CAD interfaces.

Workflow code should depend on these contracts instead of importing CadQuery,
FreeCAD, build123d, or any future modeling backend directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ModelArtifact:
    """A generated model plus backend metadata."""

    model: Any
    backend: str
    source_part_type: str


class CADBackend(Protocol):
    """Minimal contract implemented by CAD modeling backends."""

    name: str

    def build_model(self, requirement: dict[str, Any]) -> ModelArtifact:
        """Build a backend-native model from structured requirements."""

    def export_model(self, artifact: ModelArtifact, output_dir: Path, formats: list[str]) -> dict[str, str]:
        """Export a backend-native model to exchange formats."""

    def validate_model(self, artifact: ModelArtifact, output_dir: Path, requirement: dict[str, Any]) -> dict[str, Any]:
        """Run backend-aware model validation."""
