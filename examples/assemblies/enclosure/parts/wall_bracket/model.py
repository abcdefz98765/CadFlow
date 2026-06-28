"""Wall Bracket — L-shaped wall mount ear for enclosure side attachment.

Set flange_direction to +1 for right side (flange +X), -1 for left side (flange -X).
"""

from pathlib import Path

import cadquery as cq

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
PARAMS_R = {
    "part_type": "wall_bracket",
    "unit": "mm",
    "dimensions": {
        "base_width": 30.0,
        "base_depth": 20.0,
        "wall_height": 20.0,
        "material_thickness": 4.0,
        "flange_direction": +1,
    },
    "features": {
        "base_holes": {"diameter": 3.5, "count": 2},
        "wall_hole": {"diameter": 4.5},
        "fillet": {"radius": 2.0},
    },
    "outputs": ["step", "stl"],
    "assumptions": [
        "flange_direction=+1: flange extends +X (right side, envelope +X face)",
        "flange_direction=-1: flange extends -X (left side, envelope -X face)",
        "Back face at X=0 mounts to enclosure outer side wall",
        "Bottom at Z=0, two parts share Y center",
        "M3 screws for enclosure, M4 for wall anchor",
        "All units in mm",
    ],
}


def build_model(params: dict):
    dims = params["dimensions"]
    bw = dims["base_width"]
    bd = dims["base_depth"]
    wh = dims["wall_height"]
    t = dims["material_thickness"]
    direction = dims.get("flange_direction", 1)

    base_holes = params["features"]["base_holes"]
    wall_hole = params["features"]["wall_hole"]
    fillet = params["features"]["fillet"]

    # Vertical arm: back face at X=0, extends outward along direction*X.
    arm = cq.Workplane("XY").box(t, bw, wh)
    arm = arm.translate((direction * t / 2, 0, wh / 2))

    hd = base_holes["diameter"]
    hc = base_holes["count"]
    spacing = wh / (hc + 1)
    face_selector = ">X" if direction > 0 else "<X"
    for i in range(hc):
        z_local = spacing * (i + 1) - wh / 2
        arm = arm.faces(face_selector).workplane().center(0, z_local).hole(hd, t)

    # Horizontal flange: bottom at Z=0, extends outward from the arm.
    if direction > 0:
        flange = cq.Workplane("XY").box(bd, bw, t)
        flange = flange.translate((t + bd / 2, 0, t / 2))
    else:
        flange = cq.Workplane("XY").box(bd, bw, t)
        flange = flange.translate((-t - bd / 2, 0, t / 2))

    flange = flange.faces(">Z").workplane().center(0, 0).hole(wall_hole["diameter"], t)

    bracket = arm.union(flange)

    try:
        bracket = bracket.edges("|Y").fillet(fillet["radius"])
    except Exception:
        pass

    return bracket


def main():
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

    from ai_native_cad.runner import run_part

    variants = [
        ("wall_bracket_right", +1),
        ("wall_bracket_left", -1),
    ]
    for instance_name, direction in variants:
        params = dict(PARAMS_R, instance_name=instance_name)
        params["dimensions"] = dict(PARAMS_R["dimensions"], flange_direction=direction)
        result = run_part(PARAMS_R["part_type"], params)

        output_dir = Path(result["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "model.py").write_text(Path(__file__).read_text())

        print(f"{'PASS' if result['status']=='success' else 'FAIL'} in {result.get('elapsed', '?')}s -> {output_dir}")


if __name__ == "__main__":
    main()
