"""Schema objects for the JSON CAD intermediate representation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CADIR:
    """Small, JSON-serializable CAD IR used before CadQuery generation."""

    part_type: str
    unit: str = "mm"
    dimensions: dict[str, float] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=lambda: ["step", "stl"])
    check_level: str = "L0"
    part_name: str | None = None
    source: dict[str, Any] = field(default_factory=dict)
    geometry_family: str | None = None
    source_part_id: str | None = None
    source_intent: str | None = None
    manufacturing_context: dict[str, Any] = field(default_factory=dict)
    validation_metadata: dict[str, Any] = field(default_factory=dict)
    source_context_summary: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CADIR":
        return cls(
            part_type=str(data["part_type"]),
            unit=str(data.get("unit", "mm")),
            dimensions={key: float(value) for key, value in data.get("dimensions", {}).items()},
            features=dict(data.get("features", {})),
            outputs=[str(item).lower() for item in data.get("outputs", ["step", "stl"])],
            check_level=str(data.get("check_level", "L0")),
            part_name=data.get("part_name") or data.get("instance_name") or data["part_type"],
            source=dict(data.get("source", {})),
            geometry_family=data.get("geometry_family"),
            source_part_id=data.get("source_part_id"),
            source_intent=data.get("source_intent"),
            manufacturing_context=dict(data.get("manufacturing_context", {})),
            validation_metadata=dict(data.get("validation_metadata", {})),
            source_context_summary=dict(data.get("source_context_summary", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "part_type": self.part_type,
            "part_name": self.part_name or self.part_type,
            "unit": self.unit,
            "dimensions": dict(self.dimensions),
            "features": dict(self.features),
            "outputs": list(self.outputs),
            "check_level": self.check_level,
            "source": dict(self.source),
        }
        optional = {
            "geometry_family": self.geometry_family,
            "source_part_id": self.source_part_id,
            "source_intent": self.source_intent,
            "manufacturing_context": dict(self.manufacturing_context),
            "validation_metadata": dict(self.validation_metadata),
            "source_context_summary": dict(self.source_context_summary),
        }
        result.update({key: value for key, value in optional.items() if value not in (None, {}, [])})
        return result
