"""Pet button base with electronics cavity, cap recess, and wire exit."""

from pathlib import Path
import sys

import cadquery as cq

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_native_cad.features import apply_edge_finish

PARAMS = {
    "part_type": "pet_button_base",
    "unit": "mm",
    "dimensions": {
        "body_diameter": 96.0,
        "body_height": 16.0,
        "cap_recess_diameter": 76.0,
        "cap_recess_depth": 3.2,
    },
    "features": {
        "electronics_cavity": {"length": 46.0, "width": 32.0, "depth": 10.0},
        "switch_window": {"length": 10.0, "width": 10.0, "depth": 6.0},
        "wire_exit": {"length": 48.0, "width": 9.0, "height": 5.0},
        "anti_slip_feet": {"diameter": 10.0, "depth": 0.8, "radius": 34.0},
        "edge_finish": {"radius": 1.2},
    },
    "outputs": ["step", "stl"],
    "check_level": "L0",
    "assumptions": [
        "Base is a low round floor housing for a pet communication button.",
        "Bottom cavity leaves room for a small switch PCB, solder joints, or sensor wiring.",
        "Side outlet is intentionally open for a two-wire harness.",
        "Cap recess guides the large moving button cap but is not a sealed bearing surface.",
    ],
}


def build_model(params: dict):
    dims = params["dimensions"]
    features = params["features"]
    radius = dims["body_diameter"] / 2
    height = dims["body_height"]

    model = cq.Workplane("XY").circle(radius).extrude(height)

    cap_recess_depth = dims["cap_recess_depth"]
    model = (
        model.faces(">Z")
        .workplane()
        .circle(dims["cap_recess_diameter"] / 2)
        .cutBlind(-cap_recess_depth)
    )

    cavity = features["electronics_cavity"]
    model = (
        model.faces("<Z")
        .workplane()
        .rect(cavity["length"], cavity["width"])
        .cutBlind(-cavity["depth"])
    )

    switch_window = features["switch_window"]
    model = (
        model.faces(">Z")
        .workplane()
        .rect(switch_window["length"], switch_window["width"])
        .cutBlind(-switch_window["depth"])
    )

    exit_feature = features["wire_exit"]
    exit_box = (
        cq.Workplane("XY")
        .box(exit_feature["length"], exit_feature["width"], exit_feature["height"])
        .translate((radius - exit_feature["length"] / 2 + 0.1, 0, exit_feature["height"] / 2 + 1.0))
    )
    model = model.cut(exit_box)

    feet = features["anti_slip_feet"]
    foot_points = [(feet["radius"], 0), (-feet["radius"], 0), (0, feet["radius"]), (0, -feet["radius"])]
    model = (
        model.faces("<Z")
        .workplane()
        .pushPoints(foot_points)
        .circle(feet["diameter"] / 2)
        .cutBlind(-feet["depth"])
    )

    edge_radius = features["edge_finish"]["radius"]
    model = apply_edge_finish(model, ">Z", edge_radius, "fillet")
    model = apply_edge_finish(model, "|Z", edge_radius / 2, "fillet")
    return model


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
