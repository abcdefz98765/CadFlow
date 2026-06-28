# Pet Button Assembly

This is the preferred pet communication button example. It is split into
separate parts so the switch/sensor, contacts, and wire outlet are visible in
the CAD workflow.

## Parts

- `pet_button_base`: low round floor housing with cap recess, electronics cavity, switch window, anti-slip pad recesses, and side wire exit.
- `pet_button_cap`: large paw-friendly press cap with underside skirt and central actuator stem.
- `pet_button_switch_plate`: internal carrier for the switch, terminal slots, and small mounting holes.
- `pet_button_tactile_switch`: reference envelope for a common 6x6mm tactile switch with visible terminal bars.

## Generate STEP Files

```bash
python examples/assemblies/pet_button/parts/pet_button_base/model.py
python examples/assemblies/pet_button/parts/pet_button_switch_plate/model.py
python examples/assemblies/pet_button/parts/pet_button_tactile_switch/model.py
python examples/assemblies/pet_button/parts/pet_button_cap/model.py
```

Expected outputs:

```text
examples/assemblies/pet_button/parts/pet_button_base/model.step
examples/assemblies/pet_button/parts/pet_button_switch_plate/model.step
examples/assemblies/pet_button/parts/pet_button_tactile_switch/model.step
examples/assemblies/pet_button/parts/pet_button_cap/model.step
```

## Review Assembly Plan

Check `assembly_plan.md` before treating the placement files as approved
assembly intent. The plan records the high-risk switch and wire-exit decisions,
required contacts, allowed overlaps, and serviceability assumptions.

## Validate Assembly Intent

```bash
python -m ai_native_cad.assembly_validator examples/assemblies/pet_button/assembly.json
```

The validator writes `assembly_validation.json`, `assembly_validation.md`, and
`assembly_review.md`.

## FreeCAD Handoff

```bash
freecadcmd scripts/freecad_assembly.py examples/assemblies/pet_button/assembly.json
freecadcmd scripts/freecad_constraint_assembly.py examples/assemblies/pet_button/constraint_assembly.json
```

## Notes

This is still an L0 concept assembly. It reserves space for the switch and
wire harness, but it is not chew-proof, waterproof, certified, or ready for
production.
