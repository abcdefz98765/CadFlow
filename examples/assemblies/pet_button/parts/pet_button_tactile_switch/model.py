"""Reference envelope for a 6x6mm tactile switch with two exposed terminals."""

from pathlib import Path
import sys

import cadquery as cq

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(PROJECT_ROOT / "src"))

PARAMS = {
    "part_type": "pet_button_tactile_switch",
    "unit": "mm",
    "dimensions": {"body_length": 6.0, "body_width": 6.0, "body_height": 4.5, "stem_diameter": 3.0, "stem_height": 1.5},
    "features": {"terminals": {"length": 5.0, "width": 0.8, "thickness": 0.4, "pitch": 5.0}},
    "outputs": ["step", "stl"],
    "check_level": "L0",
    "assumptions": [
        "This is a reference envelope for assembly planning, not a manufactured printed part.",
        "Terminal bars show where switch contacts or soldered wires need clearance.",
    ],
}


def build_model(params: dict):
    dims = params["dimensions"]
    terminals = params["features"]["terminals"]
    body = cq.Workplane("XY").box(dims["body_length"], dims["body_width"], dims["body_height"])
    body = body.translate((0, 0, dims["body_height"] / 2))
    stem = (
        cq.Workplane("XY")
        .workplane(offset=dims["body_height"])
        .circle(dims["stem_diameter"] / 2)
        .extrude(dims["stem_height"])
    )

    model = body.union(stem)
    for y in (-terminals["pitch"] / 2, terminals["pitch"] / 2):
        terminal = (
            cq.Workplane("XY")
            .box(terminals["length"], terminals["width"], terminals["thickness"])
            .translate((0, y, terminals["thickness"] / 2))
        )
        model = model.union(terminal)
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
