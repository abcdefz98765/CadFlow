"""Large pet button cap with underside actuator stem."""

from pathlib import Path
import sys

import cadquery as cq

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_native_cad.features import apply_edge_finish

PARAMS = {
    "part_type": "pet_button_cap",
    "unit": "mm",
    "dimensions": {
        "press_diameter": 72.0,
        "press_height": 8.0,
        "skirt_diameter": 64.0,
        "skirt_height": 2.4,
        "actuator_diameter": 4.0,
        "actuator_length": 6.0,
    },
    "features": {"edge_finish": {"radius": 1.4}},
    "outputs": ["step", "stl"],
    "check_level": "L0",
    "assumptions": [
        "Large cap is intended for paw presses.",
        "Central actuator stem reaches toward a small tactile switch below.",
        "Skirt helps guide the cap inside the base recess but does not define a spring return.",
    ],
}


def build_model(params: dict):
    dims = params["dimensions"]
    cap = cq.Workplane("XY").circle(dims["press_diameter"] / 2).extrude(dims["press_height"])
    skirt = (
        cq.Workplane("XY")
        .circle(dims["skirt_diameter"] / 2)
        .extrude(dims["skirt_height"])
        .translate((0, 0, -dims["skirt_height"]))
    )
    actuator = (
        cq.Workplane("XY")
        .circle(dims["actuator_diameter"] / 2)
        .extrude(dims["actuator_length"])
        .translate((0, 0, -dims["actuator_length"]))
    )
    model = cap.union(skirt).union(actuator)

    radius = params["features"]["edge_finish"]["radius"]
    model = apply_edge_finish(model, ">Z", radius, "fillet")
    model = apply_edge_finish(model, "|Z", radius / 2, "fillet")
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
