"""Switch carrier plate for a 6x6mm tactile switch and terminal routing."""

from pathlib import Path
import sys

import cadquery as cq

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(PROJECT_ROOT / "src"))

PARAMS = {
    "part_type": "pet_button_switch_plate",
    "unit": "mm",
    "dimensions": {"length": 38.0, "width": 26.0, "thickness": 2.0},
    "features": {
        "switch_pocket": {"length": 7.4, "width": 7.4, "depth": 1.2},
        "terminal_slots": {"slot_length": 20.0, "slot_width": 1.8, "pitch": 5.2},
        "mount_holes": {"diameter": 2.6, "positions": [(-14.0, -9.0), (14.0, -9.0), (-14.0, 9.0), (14.0, 9.0)]},
    },
    "outputs": ["step", "stl"],
    "check_level": "L0",
    "assumptions": [
        "Carrier plate is a printable internal bracket, not the electrical switch itself.",
        "Central shallow pocket locates a 6x6mm tactile switch package.",
        "Terminal slots leave room for switch legs, solder, or small wires.",
    ],
}


def build_model(params: dict):
    dims = params["dimensions"]
    features = params["features"]
    model = cq.Workplane("XY").box(dims["length"], dims["width"], dims["thickness"])
    model = model.translate((0, 0, dims["thickness"] / 2))

    pocket = features["switch_pocket"]
    model = (
        model.faces(">Z")
        .workplane()
        .rect(pocket["length"], pocket["width"])
        .cutBlind(-pocket["depth"])
    )

    slots = features["terminal_slots"]
    for y in (-slots["pitch"] / 2, slots["pitch"] / 2):
        model = (
            model.faces(">Z")
            .workplane()
            .center(0, y)
            .rect(slots["slot_length"], slots["slot_width"])
            .cutBlind(-dims["thickness"])
        )

    holes = features["mount_holes"]
    model = model.faces(">Z").workplane().pushPoints(holes["positions"]).hole(holes["diameter"], dims["thickness"])
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
