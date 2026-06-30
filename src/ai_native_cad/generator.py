"""Model generation — maps part spec to CadQuery model builder."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_PART_TYPES = (
    "mounting_plate",
    "circular_button",
    "pet_button_base",
    "pet_button_cap",
    "pet_button_switch_plate",
    "pet_button_tactile_switch",
    "enclosure_base",
    "enclosure_lid",
    "spacer",
    "simple_bracket",
    "wall_bracket",
)


def get_part_spec(part_type: str) -> dict:
    """Return the default parameter spec for a given part type."""
    specs = {
        "mounting_plate": {
            "part_type": "mounting_plate",
            "unit": "mm",
            "dimensions": {"length": 80.0, "width": 40.0, "thickness": 5.0},
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
                "chamfer": {"size": 1.0},
            },
            "outputs": ["step", "stl"],
            "check_level": "L0",
        },
        "circular_button": {
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
                "Switch pocket targets common 6x6mm tactile switch bodies with clearance.",
                "A central actuator post transfers the large button press to the small tactile switch.",
                "Two underside slots leave access for switch terminals or solder joints.",
                "Side exit is a simple wire harness outlet, not a sealed strain relief.",
                "Mechanical keyboard switches are treated as a future variant with a larger square cutout.",
            ],
        },
        "pet_button_base": {
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
        },
        "pet_button_cap": {
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
        },
        "pet_button_switch_plate": {
            "part_type": "pet_button_switch_plate",
            "unit": "mm",
            "dimensions": {"length": 38.0, "width": 26.0, "thickness": 2.0},
            "features": {
                "switch_pocket": {"length": 7.4, "width": 7.4, "depth": 1.2},
                "terminal_slots": {"slot_length": 20.0, "slot_width": 1.8, "pitch": 5.2},
                "mount_holes": {
                    "diameter": 2.6,
                    "positions": [(-14.0, -9.0), (14.0, -9.0), (-14.0, 9.0), (14.0, 9.0)],
                },
            },
            "outputs": ["step", "stl"],
            "check_level": "L0",
        },
        "pet_button_tactile_switch": {
            "part_type": "pet_button_tactile_switch",
            "unit": "mm",
            "dimensions": {
                "body_length": 6.0,
                "body_width": 6.0,
                "body_height": 4.5,
                "stem_diameter": 3.0,
                "stem_height": 1.5,
            },
            "features": {"terminals": {"length": 5.0, "width": 0.8, "thickness": 0.4, "pitch": 5.0}},
            "outputs": ["step", "stl"],
            "check_level": "L0",
        },
        "enclosure_base": {
            "part_type": "enclosure_base",
            "dimensions": {
                "outer_length": 100.0,
                "outer_width": 60.0,
                "outer_height": 25.0,
                "wall_thickness": 2.0,
            },
            "features": {
                "bosses": {
                    "diameter": 6.0,
                    "hole_diameter": 2.5,
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
        },
        "enclosure_lid": {
            "part_type": "enclosure_lid",
            "dimensions": {"length": 100.0, "width": 60.0, "thickness": 3.0},
            "features": {
                "holes": {"diameter": 2.8, "count": 4, "offset_from_edge": 10.0},
                "chamfer": {"size": 0.5},
            },
            "outputs": ["step", "stl"],
        },
        "spacer": {
            "part_type": "spacer",
            "dimensions": {"outer_diameter": 12.0, "inner_diameter": 6.5, "thickness": 20.0},
            "features": {},
            "outputs": ["step", "stl"],
        },
        "simple_bracket": {
            "part_type": "simple_bracket",
            "dimensions": {"base_length": 60.0, "base_width": 30.0, "height": 40.0, "thickness": 4.0},
            "features": {
                "base_holes": {"diameter": 4.0, "count": 2, "offset_from_edge": 15.0},
                "fillet": {"radius": 1.5},
            },
            "outputs": ["step", "stl"],
        },
        "wall_bracket": {
            "part_type": "wall_bracket",
            "dimensions": {
                "base_width": 30.0,
                "base_depth": 20.0,
                "wall_height": 20.0,
                "material_thickness": 4.0,
            },
            "features": {
                "base_holes": {"diameter": 3.5, "count": 2},
                "wall_hole": {"diameter": 4.5},
                "fillet": {"radius": 2.0},
            },
            "outputs": ["step", "stl"],
        },
    }
    if part_type not in specs:
        raise ValueError(f"Unknown part_type: {part_type}. Known: {list(specs)}")
    return specs[part_type]


def list_parts() -> list[str]:
    """Return a list of all available part types."""
    return list(_PART_TYPES)


def merge_params(defaults: dict, overrides: dict) -> dict:
    """Deep merge override params into defaults."""
    result = dict(defaults)
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_params(result[key], value)
        else:
            result[key] = value
    return result
