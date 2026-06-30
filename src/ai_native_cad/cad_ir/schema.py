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
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "part_type": self.part_type,
            "part_name": self.part_name or self.part_type,
            "unit": self.unit,
            "dimensions": dict(self.dimensions),
            "features": dict(self.features),
            "outputs": list(self.outputs),
            "check_level": self.check_level,
            "source": dict(self.source),
        }
