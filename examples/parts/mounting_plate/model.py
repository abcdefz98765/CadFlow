"""Mounting plate — rectangular plate with four corner clearance holes."""

from pathlib import Path
import sys

import cadquery as cq

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_native_cad.features import apply_edge_finish, cut_through_holes, rectangular_corner_points

PARAMS = {
    "part_type": "mounting_plate",
    "unit": "mm",
    "dimensions": {
        "length": 80.0,
        "width": 40.0,
        "thickness": 5.0,
    },
    "features": {
        "mounting_holes": {
            "type": "through_hole",
            "diameter": 4.5,
            "count": 4,
            "offset_from_edge": 8.0,
            "positions": [(-32.0, -12.0), (-32.0, 12.0), (32.0, -12.0), (32.0, 12.0)],
            "fastener": "M4",
            "purpose": "corner clearance holes for mounting",
        },
        "chamfer": {
            "size": 1.0,
        },
    },
    "outputs": ["step", "stl"],
    "check_level": "L0",
    "assumptions": [
        "M4 clearance hole diameter is 4.5mm",
        "Four holes are placed symmetrically from the plate edges",
        "All units are mm",
    ],
}


def build_model(params: dict):
    dims = params["dimensions"]
    holes = params["features"]["mounting_holes"]
    chamfer = params["features"].get("chamfer", {})

    length = dims["length"]
    width = dims["width"]
    thickness = dims["thickness"]

    plate = cq.Workplane("XY").box(length, width, thickness)
    plate = plate.translate((0, 0, thickness / 2))

    points = holes.get("positions") or rectangular_corner_points(length, width, holes["offset_from_edge"])
    plate = cut_through_holes(plate, points, holes["diameter"], thickness)
    plate = apply_edge_finish(plate, "|Z", chamfer.get("size", 0), "chamfer")
    return plate


def main():
    from ai_native_cad.runner import run_part

    params = dict(PARAMS)
    result = run_part(PARAMS["part_type"], params)

    output_dir = Path(result["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model.py").write_text(Path(__file__).read_text(), encoding="utf-8")

    print(f"{'PASS' if result['status']=='success' else 'FAIL'} in {result.get('elapsed', '?')}s -> {output_dir}")


if __name__ == "__main__":
    main()
