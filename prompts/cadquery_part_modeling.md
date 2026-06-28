# CadQuery Part Modeling Rules

## Script Structure

Every CadQuery part script must follow this structure:

```python
"""<part_name> — <brief description>"""

from pathlib import Path

import cadquery as cq

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "<part_name>"

# ── Parameters ──
PARAMS = {
    "part_type": "<part_name>",
    "unit": "mm",
    "dimensions": { ... },
    "features": { ... },
    "outputs": ["step", "stl"],
    "assumptions": [
        "...",
    ],
}

# ── Model ──
def build_model(params: dict):
    ...
    return model

# ── Main ──
def main():
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

    from ai_native_cad.runner import run_part

    params = dict(PARAMS, output_dir=str(PROJECT_ROOT / "outputs"))
    result = run_part(PARAMS["part_type"], params)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "model.py").write_text(Path(__file__).read_text())

    print(f"{'PASS' if result['status']=='success' else 'FAIL'} in {result.get('elapsed', '?')}s → {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
```

## User Input Expectations

Do not require the user to describe CadQuery operations. The user may only provide function, key dimensions, constraints, and priority. Convert that into parameters, assumptions, a modeling plan, and validation checks before coding.

## Parameter Rules

1. All linear dimensions in mm
2. Hole diameters: use clearance fit (e.g., M4 → 4.5mm)
3. Chamfer/fillet sizes: reasonable for the part scale
4. Include an "outputs" list specifying formats
5. Include an "assumptions" list documenting every inferred or rounded value
6. Include a "part_type" key matching the directory name
7. OUTPUT_DIR must use PROJECT_ROOT for path resolution (not cwd-relative paths)
8. For common features, include typed feature dictionaries whenever possible
9. For manufacturable parts, include `manufacturing` limits such as `min_wall_thickness` and `min_hole_edge_factor`
10. For assembly-facing parts, include `assembly_role` and `mating_faces`

## Core Library Imports

Parts MUST use the core library for execution, export, validation, and reporting. `main()` delegates the entire pipeline to `runner.run_part()`:

```python
from ai_native_cad.runner import run_part

params = dict(PARAMS, output_dir=str(PROJECT_ROOT / "outputs"))
result = run_part(PARAMS["part_type"], params)
```

If the part is run standalone (not via runner.py), add sys.path resolution before imports:

```python
import sys
sys.path.insert(0, str(PROJECT_ROOT / "src"))
```

Do NOT inline duplicate export, validation, or report functions. `run_part()` handles `export_model()`, `validate_output()`, and `generate_report()` internally.

Available part types (use `generator.list_parts()` to query):

- `enclosure_base` — rectangular shell with wall thickness, corner bosses, bottom cutout
- `enclosure_lid` — cover plate with corner screw holes aligned to base bosses
- `spacer` — cylindrical spacer with center through-hole (PCB standoff)
- `wall_bracket` — L-shaped wall mount ear for enclosure side attachment

## Agent Modeling Workflow

Before writing CadQuery operations, derive a modeling plan:

1. Identify the functional role of the part: plate, spacer, bracket, enclosure, fixture, adapter, or assembly member.
2. Select the primary datum:
   - Center-origin for symmetric standalone parts.
   - Mounting-face origin for fixtures or parts that mate with another component.
   - Bottom face at Z=0 for parts that will be stacked in FreeCAD assemblies.
3. Convert the request into named parameters. Do not bury magic numbers inside CadQuery chains.
4. Build the model in this order:
   - main envelope
   - additive functional features
   - subtractive features
   - repeated features
   - edge finishing
5. Validate the bounding box and volume after export (handled by `validate_output`).

## Feature Template Workflow

Before writing CadQuery chains, write a feature plan. Use existing helpers from `ai_native_cad.features` when the feature matches one of these templates:

- `rectangular_corner_points(length, width, offset_from_edge)`
- `cut_through_holes(model, points, diameter, depth, face=">Z")`
- `cut_counterbore_holes(model, points, diameter, counterbore_diameter, counterbore_depth, depth, face=">Z")`
- `cut_blind_holes(model, points, diameter, depth, face=">Z")`
- `cylindrical_spacer(outer_diameter, inner_diameter, height)`
- `boss_with_hole(outer_diameter, hole_diameter, height, center, z_base=0)`
- `rectangular_shell(outer_length, outer_width, outer_height, wall_thickness, floor_thickness=None)`
- `apply_edge_finish(model, selector, radius, kind="fillet")`

Preferred feature schema examples:

```python
"mount_holes": {
    "type": "through_hole",
    "diameter": 4.5,
    "fastener": "M4",
    "positions": [(-30, -15), (30, -15), (-30, 15), (30, 15)],
    "depth": 5.0,
    "purpose": "mounting clearance",
}
```

```python
"cover_screws": {
    "type": "counterbore_hole",
    "diameter": 3.4,
    "counterbore_diameter": 6.5,
    "counterbore_depth": 2.5,
    "positions": [(-40, -20), (40, -20), (-40, 20), (40, 20)],
    "fastener": "M3",
    "purpose": "flush cover screw",
}
```

Use custom CadQuery only when the feature cannot be represented by a template. Document the custom feature's purpose, datum, and failure fallback in `assumptions`.

## Export Rules

1. Always export STEP first (it's the reference format)
2. Export STL second (for 3D printing)
3. Use `export_model(model, OUTPUT_DIR, formats)` from the core library
4. OUTPUT_DIR must be absolute (resolved from PROJECT_ROOT)

## Report Rules

1. `report.json` and `report.md` are generated by `generate_report()` from the core library
2. All four file outputs (model.py, model.step, model.stl, report.json, report.md) go to OUTPUT_DIR
3. Declare all assumptions in PARAMS["assumptions"]
4. Validation results are included in the report automatically

## Complex Shape Rules

Use robust mechanical approximations before attempting fragile geometry.

1. Main body first, details later. Do not fillet or chamfer until all cuts and unions are complete.
2. Prefer workplanes on explicit faces such as `">Z"`, `"<Z"`, `">X"`, `"<Y"` and keep face selection simple.
3. Prefer symmetry, arrays, loops, and calculated feature positions over hand-written coordinate lists.
4. For shells and enclosures:
   - create the outer box
   - shell or cut the inner cavity
   - add bosses and ribs
   - cut ports, windows, and bottom reliefs
5. For brackets:
   - create the base plate and upright/flange as simple solids
   - union them
   - add holes and slots
   - add gussets only after the main L/T shape works
6. For slots, use rounded rectangles or two holes connected by a rectangular cut.
7. For ribs/gussets, use simple triangular or rectangular sections with explicit thickness.
8. For complex curves, use a small number of loft sections or a simplified profile; record the approximation in the report.
9. If a boolean, fillet, or chamfer fails, retry with a simpler operation and keep the functional geometry valid.

## Assembly-Aware Part Rules

When the part may be assembled:

1. Keep mating faces flat and aligned to simple axes.
2. Use consistent origins across related parts, preferably bottom face at Z=0 for stacked assemblies.
3. Name assumptions about offsets, clearances, and fastener sizes.
4. Export STEP before any FreeCAD assembly step.
5. Ensure `report.json` includes bbox min/max and `solid_count`; the assembly validator depends on these fields.
6. Do not create disconnected small bodies inside one part unless explicitly requested. If a subcomponent should move independently, model it as a separate part instance.

## Assembly Self-Check Rules

Before running FreeCAD assembly scripts, run:

```bash
python -m ai_native_cad.assembly_validator examples/<assembly>.json
```

Repair all self-check errors first:

1. Missing STEP/report: generate the part before assembling.
2. Multi-solid part: either union the solids or split them into separate part instances.
3. Floating part: add a real contact/support relationship or correct its placement.
4. Required contact failed: fix the placement, dimensions, or declared mate.
5. Possible bbox interference: either add a real clearance, or document it in `allowed_bbox_overlaps` when it is a cavity/container case.
6. Tolerance-level clearance warning: document it in `allowed_close_clearances` only when the nominal engineering clearance is intentional.

Assembly validation rules should carry intent:

- `required_contacts` should include `intent`.
- `allowed_bbox_overlaps` should include `reason`.
- `allowed_close_clearances` should include `reason`.
- Do not add broad wildcard exceptions unless the design truly requires them and the reason is specific.

## Common Pitfalls

1. **`box(centered=(True, True, False))` is unreliable** — CadQuery may treat the tuple as truthy and center all axes. Prefer `box(len, wid, ht)` with explicit `translate()` to set the desired origin.
2. **Face selectors post-union** — after union, faces from both bodies merge, making `.faces(">X")` ambiguous. Drill holes on individual parts BEFORE union.
3. **Assembly clearance** — leave >= 0.5mm gap between mating parts. FreeCAD's STEP-based interference checker is unreliable; validate clearance arithmetically (bounding box comparison) rather than relying on FreeCAD's `Shape.common()`.
4. **Standoff sizing** — verify that standoffs/spacers fit within the enclosure cavity. Check radial clearance from boss center to inner wall, not just XY centering.
5. **Lid placement** — if the enclosure has an open top (cavity goes to outer_height), place the lid at or above outer_height, not inside the cavity.
