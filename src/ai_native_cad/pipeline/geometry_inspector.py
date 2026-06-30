"""Geometry and artifact inspection for STEP-first pipeline validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cadquery as cq

from ai_native_cad.cad_ir.schema import CADIR


def inspect_geometry(
    model: cq.Workplane | None,
    output_dir: str | Path,
    ir: CADIR | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return structured facts about generated CAD artifacts and geometry."""
    cad_ir = CADIR.from_dict(ir) if isinstance(ir, dict) else ir
    output_path = Path(output_dir)
    inspection: dict[str, Any] = {
        "artifact_roles": {
            "primary": "model.step",
            "derived": ["model.stl"],
        },
        "solid_count": None,
        "bounding_box": {},
        "volume": 0.0,
        "step_file": _file_fact(output_path / "model.step", role="primary_cad_artifact"),
        "stl_file": _file_fact(output_path / "model.stl", role="derived_mesh_output"),
        "features": _feature_scaffold(cad_ir),
        "errors": [],
    }

    if model is None:
        inspection["errors"].append({"code": "model_missing", "message": "No model object was available for inspection"})
        return inspection

    try:
        shape = model.val()
        bbox = shape.BoundingBox()
        volume = shape.Volume()
        solids = shape.Solids()
    except Exception as exc:
        inspection["errors"].append({"code": "geometry_measurement_failed", "message": str(exc)})
        return inspection

    inspection["solid_count"] = len(solids)
    inspection["bounding_box"] = {
        "x": round(bbox.xlen, 3),
        "y": round(bbox.ylen, 3),
        "z": round(bbox.zlen, 3),
    }
    inspection["volume"] = round(volume, 3)
    return inspection


def _file_fact(path: Path, role: str) -> dict[str, Any]:
    present = path.exists() and path.stat().st_size > 0
    return {
        "path": str(path),
        "present": present,
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "role": role,
    }


def _feature_scaffold(cad_ir: CADIR | None) -> dict[str, Any]:
    features = cad_ir.features if cad_ir else {}
    return {
        "holes": {
            "status": "scaffold",
            "expected": _expected_feature(features, "holes", aliases=("mounting_holes", "base_holes")),
            "measured": None,
            "note": "Hole count/diameter measurement from STEP topology is planned for a later Phase 1.8 increment.",
        },
        "chamfers": {
            "status": "scaffold",
            "expected": _expected_feature(features, "chamfer"),
            "measured": None,
            "note": "Chamfer measurement is not inferred yet.",
        },
        "fillets": {
            "status": "scaffold",
            "expected": _expected_feature(features, "fillet"),
            "measured": None,
            "note": "Fillet measurement is not inferred yet.",
        },
    }


def _expected_feature(features: dict[str, Any], key: str, aliases: tuple[str, ...] = ()) -> Any:
    for name in (key, *aliases):
        if name in features:
            return features[name]
    return None
