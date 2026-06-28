"""Enclosure Base — rectangular box shell with mounting bosses.

Part of enclosure assembly: base → spacers → lid, with wall_brackets on sides.
"""

from pathlib import Path

import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
PARAMS = {
    "part_type": "enclosure_base",
    "unit": "mm",
    "dimensions": {
        "outer_length": 100.0,
        "outer_width": 60.0,
        "outer_height": 25.0,
        "wall_thickness": 2.0,
    },
    "features": {
        "bosses": {
            "diameter": 6.0,
            "hole_diameter": 2.5,  # M2.5 clearance
            "height": 5.0,
            "offset_from_edge": 10.0,
        },
        "bottom_cutout": {
            "length": 60.0,
            "width": 40.0,
            "offset_from_wall": 10.0,
        },
        "fillet": {"radius": 1.0},
    },
    "outputs": ["step", "stl"],
    "assumptions": [
        "Bottom face at Z=0 for assembly stacking",
        "Boss holes are M2.5 clearance (2.5mm)",
        "Boss centers at ±40, ±20 (offset=10 from outer edge)",
        "Bottom cutout centered, extending to -Z",
        "All units in mm",
    ],
}


def build_model(params: dict):
    dims = params["dimensions"]
    bosses = params["features"]["bosses"]
    cutout = params["features"]["bottom_cutout"]
    fillet = params["features"]["fillet"]

    ol = dims["outer_length"]
    ow = dims["outer_width"]
    oh = dims["outer_height"]
    wt = dims["wall_thickness"]

    # Outer shell — default centered, translate so bottom at Z=0
    outer = cq.Workplane("XY").box(ol, ow, oh)
    outer = outer.translate((0, 0, oh / 2))

    # Inner cavity — centered, translate so floor at Z=wt
    il = ol - 2 * wt
    iw = ow - 2 * wt
    ih = oh - wt
    inner = cq.Workplane("XY").box(il, iw, ih)
    inner = inner.translate((0, 0, ih / 2 + wt))

    shell = outer.cut(inner)

    # Bottom cutout
    bc = cutout
    cut = cq.Workplane("XY").box(bc["length"], bc["width"], wt * 3)
    cut = cut.translate((0, 0, -(wt * 3) / 2))
    shell = shell.cut(cut)

    # Corner bosses — OCCT fuse ensures single solid
    bo = bosses["offset_from_edge"]
    bx = ol / 2 - bo
    by = ow / 2 - bo
    boss_d = bosses["diameter"]
    boss_h = bosses["height"]
    hole_d = bosses["hole_diameter"]

    shape = shell.val().wrapped

    for x_sign in [+1, -1]:
        for y_sign in [+1, -1]:
            boss = (
                cq.Workplane("XY")
                .circle(boss_d / 2)
                .extrude(boss_h + 0.5)
                .translate((x_sign * bx, y_sign * by, -0.5))
            )
            hole = (
                cq.Workplane("XY")
                .circle(hole_d / 2)
                .extrude(boss_h + 0.5)
                .translate((x_sign * bx, y_sign * by, -0.5))
            )
            boss = boss.cut(hole)
            algo = BRepAlgoAPI_Fuse(shape, boss.val().wrapped)
            algo.Build()
            if algo.IsDone():
                shape = algo.Shape()

    shell = cq.Workplane("XY").newObject([cq.Shape.cast(shape)])

    # Fillet outer edges
    try:
        shell = shell.edges("|Z").fillet(fillet["radius"])
    except Exception:
        pass

    return shell


def main():
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

    from ai_native_cad.runner import run_part

    params = dict(PARAMS)
    result = run_part(PARAMS["part_type"], params)

    output_dir = Path(result["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model.py").write_text(Path(__file__).read_text())

    print(f"{'PASS' if result['status']=='success' else 'FAIL'} in {result.get('elapsed', '?')}s -> {output_dir}")


if __name__ == "__main__":
    main()
