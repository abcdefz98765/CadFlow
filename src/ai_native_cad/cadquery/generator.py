"""Deterministic CadQuery source generation from CAD IR."""

from __future__ import annotations

import json
from typing import Any

from ai_native_cad.cad_ir.schema import CADIR


def generate_cadquery_code(ir: CADIR | dict[str, Any]) -> str:
    """Generate deterministic CadQuery Python source from CAD IR."""
    return generate_cadquery_candidates(ir, max_candidates=1)[0]["code"]


def generate_cadquery_candidates(ir: CADIR | dict[str, Any], max_candidates: int = 3) -> list[dict[str, str]]:
    """Generate deterministic CadQuery implementation candidates from CAD IR."""
    cad_ir = CADIR.from_dict(ir) if isinstance(ir, dict) else ir
    data = cad_ir.to_dict()
    builder = {
        "mounting_plate": _mounting_plate_builder,
        "spacer": _spacer_builder,
        "simple_bracket": _simple_bracket_builder,
        "wall_bracket": _wall_bracket_builder,
        "circular_button": _circular_button_builder,
        "enclosure_base": _enclosure_base_builder,
        "enclosure_lid": _enclosure_lid_builder,
        "link_like_part": _elongated_plate_with_end_holes_builder,
    }.get(cad_ir.part_type)
    if builder is None:
        raise ValueError(f"Unsupported part_type for CadQuery generation: {cad_ir.part_type}")

    profiles = _candidate_profiles(cad_ir, max_candidates)
    return [
        {
            "candidate": label,
            "strategy": strategy,
            "code": _render_source(data, builder, label, strategy),
        }
        for label, strategy in profiles
    ]


def _render_source(data: dict[str, Any], builder: Any, candidate: str, strategy: str) -> str:
    return "\n".join([
        f'"""Generated CadQuery model from CAD IR. Candidate {candidate}: {strategy}."""',
        "",
        "from __future__ import annotations",
        "",
        "import json",
        "from pathlib import Path",
        "",
        "import cadquery as cq",
        "",
        f"CAD_IR = json.loads({json.dumps(json.dumps(data, indent=2, sort_keys=True))})",
        f"CANDIDATE_ID = {candidate!r}",
        f"CANDIDATE_STRATEGY = {strategy!r}",
        "",
        _common_helpers(),
        "",
        builder(strategy),
        "",
        "def main() -> None:",
        "    model = build_model(CAD_IR)",
        "    cq.exporters.export(model, 'model.step')",
        "    cq.exporters.export(model, 'model.stl')",
        "    Path('preview.png').write_bytes(_preview_png_bytes())",
        "",
        "",
        "if __name__ == '__main__':",
        "    main()",
        "",
    ])


def _candidate_profiles(cad_ir: CADIR, max_candidates: int) -> list[tuple[str, str]]:
    profiles = [("A", "conservative")]
    if max_candidates <= 1 or not _needs_candidate_mode(cad_ir):
        return profiles[:max_candidates]
    profiles.extend([("B", "optimized"), ("C", "fallback_simplified")])
    return profiles[:max(1, min(max_candidates, 3))]


def _needs_candidate_mode(cad_ir: CADIR) -> bool:
    features = cad_ir.features
    if cad_ir.part_type in {"mounting_plate", "enclosure_lid"} and (features.get("holes") or features.get("mounting_holes")):
        return True
    if any(name in features for name in ("chamfer", "fillet")):
        return True
    source = cad_ir.source
    return bool(source.get("candidate_mode") or source.get("ambiguous"))


def _common_helpers() -> str:
    return """def _corner_points(length: float, width: float, offset: float) -> list[tuple[float, float]]:
    x = length / 2 - offset
    y = width / 2 - offset
    return [(-x, -y), (-x, y), (x, -y), (x, y)]


def _preview_png_bytes() -> bytes:
    # Placeholder only: the browser STL viewer is the live geometry preview.
    # Keep this PNG bright and recognizable so users do not mistake it for a
    # broken black render while real rendered snapshots remain deferred.
    import struct
    import zlib

    width, height = 640, 360
    bg = (248, 250, 247)
    grid = (224, 226, 220)
    axis = (105, 113, 116)
    teal = (15, 118, 110)
    amber = (161, 98, 7)
    ink = (31, 37, 40)
    pixels = [[bg for _ in range(width)] for _ in range(height)]

    def set_px(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            pixels[y][x] = color

    def line(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            set_px(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rect(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        line(x0, y0, x1, y0, color)
        line(x1, y0, x1, y1, color)
        line(x1, y1, x0, y1, color)
        line(x0, y1, x0, y0, color)

    for x in range(0, width, 40):
        line(x, 0, x, height - 1, grid)
    for y in range(0, height, 40):
        line(0, y, width - 1, y, grid)

    line(70, 280, 570, 280, axis)
    line(70, 280, 120, 80, axis)
    line(70, 280, 70, 95, axis)

    rect(190, 125, 450, 245, teal)
    rect(210, 145, 430, 225, teal)
    for offset in range(0, 70, 14):
        line(210 + offset, 225, 330 + offset, 145, teal)

    for cx, cy in ((235, 165), (405, 165), (235, 205), (405, 205)):
        for r in range(10, 14):
            for x in range(cx - r, cx + r + 1):
                for y in range(cy - r, cy + r + 1):
                    d = (x - cx) * (x - cx) + (y - cy) * (y - cy)
                    if r * r - 12 <= d <= r * r + 12:
                        set_px(x, y, amber)

    rect(36, 28, 604, 332, ink)

    raw = b''.join(b'\\x00' + bytes(channel for pixel in row for channel in pixel) for row in pixels)

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b'\\x89PNG\\r\\n\\x1a\\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + chunk(b'tEXt', b'Description\\x00CadFlow placeholder preview; use model.stl for live geometry preview')
        + chunk(b'IDAT', zlib.compress(raw, 9))
        + chunk(b'IEND', b'')
    )
"""


def _mounting_plate_builder(strategy: str = "conservative") -> str:
    return """def build_model(params: dict) -> cq.Workplane:
    dims = params['dimensions']
    features = params.get('features', {})
    length = dims['length']
    width = dims['width']
    thickness = dims['thickness']
    model = cq.Workplane('XY').box(length, width, thickness).translate((0, 0, thickness / 2))
    holes = features.get('holes') or features.get('mounting_holes')
    if holes:
        if isinstance(holes, list):
            holes = holes[0] if holes else {}
        diameter = holes.get('diameter', 5.0)
        positions = holes.get('positions', 'corner_4')
        pattern = holes.get('pattern')
        count = holes.get('count')
        if positions == 'corner_4' or (pattern == 'corner' and count == 4):
            offset = holes.get('offset_from_edge', max(diameter, min(length, width) * 0.2))
            points = _corner_points(length, width, offset)
        else:
            points = [tuple(point) for point in positions]
        model = model.faces('>Z').workplane().pushPoints(points).hole(diameter, thickness)
    chamfer = features.get('chamfer', 0)
    if isinstance(chamfer, dict):
        chamfer = chamfer.get('size', 0)
    if chamfer:
        model = model.edges('|Z').chamfer(float(chamfer))
    return model
"""


def _spacer_builder(strategy: str = "conservative") -> str:
    return """def build_model(params: dict) -> cq.Workplane:
    dims = params['dimensions']
    outer = cq.Workplane('XY').circle(dims['outer_diameter'] / 2).extrude(dims['thickness'])
    inner = cq.Workplane('XY').circle(dims['inner_diameter'] / 2).extrude(dims['thickness'])
    return outer.cut(inner)
"""


def _simple_bracket_builder(strategy: str = "conservative") -> str:
    fallback = strategy == "fallback_simplified"
    return """def build_model(params: dict) -> cq.Workplane:
    dims = params['dimensions']
    features = params.get('features', {})
    base_length = dims['base_length']
    base_width = dims['base_width']
    height = dims['height']
    thickness = dims['thickness']
    base = cq.Workplane('XY').box(base_length, base_width, thickness).translate((0, 0, thickness / 2))
    upright = cq.Workplane('XY').box(thickness, base_width, height).translate((-base_length / 2 + thickness / 2, 0, height / 2))
    model = base.union(upright)
    holes = features.get('holes') or features.get('base_holes')
    if holes:
        if isinstance(holes, list):
            holes = holes[0] if holes else {}
        diameter = holes.get('diameter', 4.0)
        offset = holes.get('offset_from_edge', base_length * 0.25)
        points = [(-base_length / 2 + offset, 0), (base_length / 2 - offset, 0)]
        model = model.faces('>Z').workplane().pushPoints(points).hole(diameter, thickness)
    fillet = features.get('fillet', 0)
    if isinstance(fillet, dict):
        fillet = fillet.get('radius', 0)
    if fillet and not """ + repr(fallback) + """:
        model = model.edges('|Y').fillet(float(fillet))
    return model
"""


def _wall_bracket_builder(strategy: str = "conservative") -> str:
    return """def build_model(params: dict) -> cq.Workplane:
    dims = params['dimensions']
    normalized = {
        'dimensions': {
            'base_length': dims['base_depth'],
            'base_width': dims['base_width'],
            'height': dims['wall_height'],
            'thickness': dims['material_thickness'],
        },
        'features': params.get('features', {}),
    }
    return _build_simple_bracket(normalized)


def _build_simple_bracket(params: dict) -> cq.Workplane:
    dims = params['dimensions']
    base = cq.Workplane('XY').box(dims['base_length'], dims['base_width'], dims['thickness']).translate((0, 0, dims['thickness'] / 2))
    upright = cq.Workplane('XY').box(dims['thickness'], dims['base_width'], dims['height']).translate((-dims['base_length'] / 2 + dims['thickness'] / 2, 0, dims['height'] / 2))
    return base.union(upright)
"""


def _circular_button_builder(strategy: str = "conservative") -> str:
    return """def build_model(params: dict) -> cq.Workplane:
    dims = params['dimensions']
    body = cq.Workplane('XY').circle(dims['body_diameter'] / 2).extrude(dims['body_height'])
    button = (
        cq.Workplane('XY')
        .circle(dims['button_diameter'] / 2)
        .extrude(dims['button_height'])
        .translate((0, 0, dims['body_height']))
    )
    return body.union(button)
"""


def _enclosure_base_builder(strategy: str = "conservative") -> str:
    return """def build_model(params: dict) -> cq.Workplane:
    dims = params['dimensions']
    length = dims['outer_length']
    width = dims['outer_width']
    height = dims['outer_height']
    wall = dims['wall_thickness']
    model = cq.Workplane('XY').box(length, width, height).translate((0, 0, height / 2))
    cavity = (
        cq.Workplane('XY')
        .box(length - 2 * wall, width - 2 * wall, height)
        .translate((0, 0, height / 2 + wall))
    )
    return model.cut(cavity)
"""


def _enclosure_lid_builder(strategy: str = "conservative") -> str:
    fallback = strategy == "fallback_simplified"
    return """def build_model(params: dict) -> cq.Workplane:
    dims = params['dimensions']
    features = params.get('features', {})
    length = dims['length']
    width = dims['width']
    thickness = dims['thickness']
    model = cq.Workplane('XY').box(length, width, thickness).translate((0, 0, thickness / 2))
    holes = features.get('holes')
    if holes:
        diameter = holes.get('diameter', 2.8)
        offset = holes.get('offset_from_edge', min(length, width) * 0.15)
        model = model.faces('>Z').workplane().pushPoints(_corner_points(length, width, offset)).hole(diameter, thickness)
    chamfer = features.get('chamfer', 0)
    if isinstance(chamfer, dict):
        chamfer = chamfer.get('size', 0)
    if chamfer and not """ + repr(fallback) + """:
        model = model.edges('|Z').chamfer(float(chamfer))
    return model
"""


def _elongated_plate_with_end_holes_builder(strategy: str = "conservative") -> str:
    """A generic two-ended link; it deliberately carries no robot-specific meaning."""
    return """def build_model(params: dict) -> cq.Workplane:
    dims = params['dimensions']
    features = params.get('features', {})
    length = dims['length']
    width = dims['width']
    thickness = dims['thickness']
    model = cq.Workplane('XY').box(length, width, thickness).translate((0, 0, thickness / 2))
    diameter = dims['hole_diameter']
    center_distance = dims['hole_center_distance']
    points = [(-center_distance / 2, 0), (center_distance / 2, 0)]
    model = model.faces('>Z').workplane().pushPoints(points).hole(diameter, thickness)
    fillet = features.get('fillet', 0)
    if isinstance(fillet, dict):
        fillet = fillet.get('radius', 0)
    if fillet:
        model = model.edges('|Z').fillet(float(fillet))
    return model
"""
