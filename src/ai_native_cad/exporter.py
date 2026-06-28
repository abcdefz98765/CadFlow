"""Model exporter — exports CadQuery model to STEP/STL formats."""

from pathlib import Path

import cadquery as cq


def export_model(model: cq.Workplane, output_dir: Path, formats: list[str]) -> dict[str, str]:
    """Export a CadQuery model to the specified formats."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = {}
    for fmt in formats:
        fmt = fmt.lower()
        if fmt == "step":
            path = output_dir / "model.step"
            cq.exporters.export(model, str(path))
            files["step"] = str(path)
        elif fmt == "stl":
            path = output_dir / "model.stl"
            cq.exporters.export(model, str(path))
            files["stl"] = str(path)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    return files
