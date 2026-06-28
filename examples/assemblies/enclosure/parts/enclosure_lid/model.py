"""Enclosure Lid — 100×60×3mm cover plate with corner screw holes.

Mates with enclosure_base boss holes. Spacer standoffs sit between base and lid.
"""

from pathlib import Path
import sys

import cadquery as cq

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_native_cad.features import apply_edge_finish, cut_through_holes, rectangular_corner_points

PARAMS = {
    "part_type": "enclosure_lid",
    "unit": "mm",
    "dimensions": {
        "length": 100.0,
        "width": 60.0,
        "thickness": 3.0,
    },
    "features": {
        "holes": {
            "type": "through_hole",
            "diameter": 2.8,
            "count": 4,
            "offset_from_edge": 10.0,
            "positions": [(-40.0, -20.0), (-40.0, 20.0), (40.0, -20.0), (40.0, 20.0)],
            "depth": 3.0,
            "fastener": "M2.5",
            "purpose": "clearance holes aligned to enclosure_base bosses",
        },
        "chamfer": {
            "size": 0.5,
        },
    },
    "outputs": ["step", "stl"],
    "assumptions": [
        "Hole positions match enclosure_base boss centers (±40, ±20)",
        "Hole diameter 2.8mm is M2.5 clearance fit",
        "Bottom face at Z=0 for stacking on spacers in assembly",
        "All units in mm",
    ],
}


def build_model(params: dict):
    dims = params["dimensions"]
    holes = params["features"]["holes"]
    chamfer = params["features"]["chamfer"]

    length = dims["length"]
    width = dims["width"]
    thickness = dims["thickness"]
    hole_d = holes["diameter"]
    off = holes["offset_from_edge"]

    lid = cq.Workplane("XY").box(length, width, thickness)
    lid = lid.translate((0, 0, thickness / 2))

    points = holes.get("positions") or rectangular_corner_points(length, width, off)
    lid = cut_through_holes(lid, points, hole_d, thickness)

    lid = apply_edge_finish(lid, ">Z", chamfer["size"], "chamfer")
    lid = apply_edge_finish(lid, "<Z", chamfer["size"], "chamfer")

    return lid


def main():
    from ai_native_cad.runner import run_part

    params = dict(PARAMS)
    result = run_part(PARAMS["part_type"], params)

    output_dir = Path(result["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model.py").write_text(Path(__file__).read_text())

    print(f"{'PASS' if result['status']=='success' else 'FAIL'} in {result.get('elapsed', '?')}s -> {output_dir}")


if __name__ == "__main__":
    main()
