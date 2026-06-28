"""Reusable CadQuery feature templates.

These helpers are intentionally small and explicit. They give agents stable
building blocks for common mechanical features while keeping the generated
model script readable and parameter-driven.
"""

from __future__ import annotations

import cadquery as cq


def rectangular_corner_points(length: float, width: float, offset_from_edge: float) -> list[tuple[float, float]]:
    """Return four symmetric corner feature points for a rectangular part."""
    x = length / 2 - offset_from_edge
    y = width / 2 - offset_from_edge
    return [(-x, -y), (-x, y), (x, -y), (x, y)]


def cut_through_holes(
    model: cq.Workplane,
    points: list[tuple[float, float]],
    diameter: float,
    depth: float,
    face: str = ">Z",
) -> cq.Workplane:
    """Cut repeated through holes from a selected planar face."""
    return model.faces(face).workplane().pushPoints(points).hole(diameter, depth)


def cut_counterbore_holes(
    model: cq.Workplane,
    points: list[tuple[float, float]],
    diameter: float,
    counterbore_diameter: float,
    counterbore_depth: float,
    depth: float,
    face: str = ">Z",
) -> cq.Workplane:
    """Cut repeated counterbore holes from a selected planar face."""
    return (
        model.faces(face)
        .workplane()
        .pushPoints(points)
        .cboreHole(diameter, counterbore_diameter, counterbore_depth, depth)
    )


def cut_blind_holes(
    model: cq.Workplane,
    points: list[tuple[float, float]],
    diameter: float,
    depth: float,
    face: str = ">Z",
) -> cq.Workplane:
    """Cut repeated blind holes from a selected planar face."""
    return model.faces(face).workplane().pushPoints(points).hole(diameter, depth)


def cylindrical_spacer(outer_diameter: float, inner_diameter: float, height: float) -> cq.Workplane:
    """Create a cylindrical spacer or standoff with a concentric through-hole."""
    outer = cq.Workplane("XY").circle(outer_diameter / 2).extrude(height)
    inner = cq.Workplane("XY").circle(inner_diameter / 2).extrude(height)
    return outer.cut(inner)


def boss_with_hole(
    outer_diameter: float,
    hole_diameter: float,
    height: float,
    center: tuple[float, float],
    z_base: float = 0.0,
) -> cq.Workplane:
    """Create a cylindrical boss with a concentric through-hole."""
    x, y = center
    boss = cq.Workplane("XY").circle(outer_diameter / 2).extrude(height)
    hole = cq.Workplane("XY").circle(hole_diameter / 2).extrude(height)
    return boss.cut(hole).translate((x, y, z_base))


def rectangular_shell(
    outer_length: float,
    outer_width: float,
    outer_height: float,
    wall_thickness: float,
    floor_thickness: float | None = None,
) -> cq.Workplane:
    """Create an open-top rectangular shell with bottom face at Z=0."""
    floor = wall_thickness if floor_thickness is None else floor_thickness
    outer = cq.Workplane("XY").box(outer_length, outer_width, outer_height)
    outer = outer.translate((0, 0, outer_height / 2))

    inner = cq.Workplane("XY").box(
        outer_length - 2 * wall_thickness,
        outer_width - 2 * wall_thickness,
        outer_height - floor,
    )
    inner = inner.translate((0, 0, (outer_height - floor) / 2 + floor))
    return outer.cut(inner)


def apply_edge_finish(
    model: cq.Workplane,
    selector: str,
    radius: float,
    kind: str = "fillet",
) -> cq.Workplane:
    """Apply a best-effort fillet or chamfer while preserving functional geometry."""
    if radius <= 0:
        return model
    try:
        if kind == "chamfer":
            return model.edges(selector).chamfer(radius)
        return model.edges(selector).fillet(radius)
    except Exception:
        return model
