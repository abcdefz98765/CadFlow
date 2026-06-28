"""Pet communication button with tactile-switch pocket and wire outlet."""

from pathlib import Path
import sys

import cadquery as cq

PROJECT_ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").exists())
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_native_cad.features import apply_edge_finish

PARAMS = {
    "part_type": "circular_button",
    "unit": "mm",
    "dimensions": {
        "body_diameter": 92.0,
        "body_height": 14.0,
        "button_diameter": 72.0,
        "button_height": 8.0,
    },
    "features": {
        "switch_pocket": {
            "type": "switch_pocket",
            "length": 7.4,
            "width": 7.4,
            "depth": 5.6,
            "purpose": "underside clearance for a common 6x6mm tactile switch body",
        },
        "actuator_post": {
            "type": "actuator_post",
            "diameter": 4.0,
            "height": 2.2,
            "purpose": "central post transfers the large pet button surface to the tactile switch",
        },
        "contact_slots": {
            "type": "wire_clearance",
            "slot_width": 1.8,
            "slot_length": 18.0,
            "slot_depth": 2.4,
            "count": 2,
            "pitch": 5.2,
            "purpose": "clearance for switch terminals or soldered leads",
        },
        "wire_exit": {
            "type": "wire_exit",
            "width": 8.0,
            "height": 4.0,
            "length": 46.0,
            "direction": "+X",
            "purpose": "side outlet for a small two-wire harness",
        },
        "anti_slip_feet": {
            "type": "foot_recesses",
            "diameter": 10.0,
            "depth": 0.8,
            "count": 4,
            "radius": 31.0,
            "purpose": "underside recesses for rubber feet or pads",
        },
        "edge_finish": {"radius": 1.2},
    },
    "outputs": ["step", "stl"],
    "check_level": "L0",
    "assumptions": [
        "Pet button uses a large 72mm press surface on a 92mm low round base.",
        "6x6mm tactile switch bodies are modeled with 0.7mm total XY clearance.",
        "A central actuator post transfers the large button press to the small tactile switch.",
        "The side outlet is intended for a two-wire harness after soldering.",
        "The contact slots expose switch terminals/solder joints for routing and inspection.",
        "Underside circular recesses are placeholders for rubber anti-slip pads.",
        "This is a printable pet-button concept, not a chew-proof or sealed product.",
    ],
}


def build_model(params: dict):
    dims = params["dimensions"]
    features = params["features"]
    body_radius = dims["body_diameter"] / 2
    body_height = dims["body_height"]
    button_radius = dims["button_diameter"] / 2
    button_height = dims["button_height"]

    body = cq.Workplane("XY").circle(body_radius).extrude(body_height)
    button = cq.Workplane("XY").workplane(offset=body_height).circle(button_radius).extrude(button_height)
    model = body.union(button)

    pocket = features["switch_pocket"]
    model = (
        model.faces("<Z")
        .workplane()
        .rect(pocket["length"], pocket["width"])
        .cutBlind(-pocket["depth"])
    )

    post = features["actuator_post"]
    post_z = pocket["depth"] - post["height"]
    actuator = (
        cq.Workplane("XY")
        .circle(post["diameter"] / 2)
        .extrude(post["height"])
        .translate((0, 0, post_z))
    )
    model = model.union(actuator)

    slots = features["contact_slots"]
    slot_y = slots["pitch"] / 2
    for y in (-slot_y, slot_y):
        model = (
            model.faces("<Z")
            .workplane()
            .center(0, y)
            .rect(slots["slot_length"], slots["slot_width"])
            .cutBlind(-slots["slot_depth"])
        )

    exit_feature = features["wire_exit"]
    exit_box = (
        cq.Workplane("XY")
        .box(exit_feature["length"], exit_feature["width"], exit_feature["height"])
        .translate((body_radius - exit_feature["length"] / 2 + 0.1, 0, exit_feature["height"] / 2))
    )
    model = model.cut(exit_box)

    feet = features["anti_slip_feet"]
    foot_points = [
        (feet["radius"], 0),
        (-feet["radius"], 0),
        (0, feet["radius"]),
        (0, -feet["radius"]),
    ]
    model = (
        model.faces("<Z")
        .workplane()
        .pushPoints(foot_points)
        .circle(feet["diameter"] / 2)
        .cutBlind(-feet["depth"])
    )

    radius = features.get("edge_finish", {}).get("radius", 0)
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
